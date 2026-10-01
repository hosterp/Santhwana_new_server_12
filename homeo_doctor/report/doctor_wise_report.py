from odoo import models, fields, api
from datetime import date, datetime, time as dt_time
from collections import defaultdict
from odoo.exceptions import ValidationError


class DoctorBillingReportWizard(models.TransientModel):
    _name = 'doctor.billing.report.wizard'
    _description = 'Doctor Billing Report Wizard'

    from_date = fields.Date(required=True)
    to_date = fields.Date(required=True)
    doctor = fields.Many2one('doctor.profile', string='Doctor')

    @api.constrains('to_date')
    def _check_to_date_not_future(self):
        today = date.today()
        for rec in self:
            if rec.to_date and rec.to_date > today:
                raise ValidationError(
                    "Future dates are not allowed. Please select today's date or earlier."
                )

    def generate_report(self):
        return self.env.ref('homeo_doctor.action_doctor_billing_pdf_report').report_action(self, data={
            'from_date': self.from_date,
            'to_date': self.to_date,
        })

    def _set_summary_amount(self, result, doctor, key, amount):
        result.setdefault(doctor or 'Unknown', {})
        result[doctor or 'Unknown'][key] = result[doctor or 'Unknown'].get(key, 0.0) + (amount or 0.0)

    def _columns_exist(self, target, columns, require_stored=True):
        if hasattr(target, '_fields'):
            for col in columns:
                if col not in target._fields:
                    return False
                if require_stored and not target._fields[col].store:
                    return False
            table = target._table
        else:
            table = target
        self.env.cr.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = ANY(%s)
        """, (table, list(columns)))
        existing = {row[0] for row in self.env.cr.fetchall()}
        return set(columns).issubset(existing)

    def _paid_vssc_where(self, table_alias, vssc_field='vssc_boolean'):
        """Include unpaid + paid (incl. VSSC); exclude cancelled only."""
        return """
            COALESCE({alias}.status, '') <> 'cancelled'
        """.format(alias=table_alias)

    # ------------------------------------------------------------------
    # Fast doctor cache (one preload for all billing sections)
    # ------------------------------------------------------------------
    def _preload_doctor_cache(self, patient_ids, from_date, to_date, patient_names=None):
        """Load appointments / registrations / admissions once for bulk resolve."""
        cache = {
            'appt_by_patient_date': defaultdict(list),   # (pid, date) -> [(id, [doc_ids])]
            'appt_before': defaultdict(list),            # pid -> [(date, id, [doc_ids])]
            'reg_by_patient_date': defaultdict(list),    # (pid, date) -> [(id, doctor_id, doctor_name_char)]
            'reg_by_patient': defaultdict(list),         # pid -> [(date, id, doctor_id, status, doctor_name_char)]
            # Extended rows for pharmacy (date desc / ctid tie-break matches ORM search)
            'reg_by_patient_full': defaultdict(list),    # pid -> [(date, id, doctor_id, status, doctor_name_char, ctid, preg_patient_id)]
            'reg_by_name_date': defaultdict(list),       # (name, date) -> [(id, doctor_id, doctor_name_char)]
            'reg_by_name': defaultdict(list),            # name -> [(date, id, doctor_id, status, doctor_name_char)]
            'reg_by_name_full': defaultdict(list),       # name -> [(date, id, doctor_id, status, doctor_name_char, ctid)]
            'admission_by_patient': defaultdict(list),    # pid -> [(adm_date, dis_date, doctor_id)]
            'discharge_hist': defaultdict(list),         # pid -> [(adm_dt, dis_dt, doctor_id)]
            'master': {},                                # pid -> (doc_name_id, doctor_id)
            'doctor_names': {},                          # doctor_id -> name
            'doctor_by_name': {},                        # name -> doctor_id
        }
        if not patient_ids and not patient_names:
            cr = self.env.cr
            cr.execute("SELECT id, name FROM doctor_profile")
            for did, name in cr.fetchall():
                cache['doctor_names'][did] = name or 'Unknown'
            return cache

        pids = list(patient_ids or [])
        cr = self.env.cr

        cr.execute("""
            SELECT id, name, consultation_fee_doctor
              FROM doctor_profile
        """)
        for did, name, _fee in cr.fetchall():
            cache['doctor_names'][did] = name or 'Unknown'
            if name:
                cache['doctor_by_name'][name] = did

        if pids:
            cr.execute("""
                SELECT id, doc_name, doctor
                  FROM patient_reg
                 WHERE id = ANY(%s)
            """, (pids,))
            for pid, doc_name, doctor in cr.fetchall():
                cache['master'][pid] = (doc_name, doctor)

            # Appointments in/around range (also need history before from_date)
            cr.execute("""
                SELECT a.id, a.patient_id, a.appointment_date, rel.doctor_profile_id
                  FROM patient_appointment a
                  JOIN doctor_profile_patient_appointment_rel rel
                    ON rel.patient_appointment_id = a.id
                 WHERE a.patient_id = ANY(%s)
                   AND a.status = 'confirmed'
                   AND a.appointment_date <= %s
                 ORDER BY a.patient_id, a.appointment_date, a.id, rel.doctor_profile_id
            """, (pids, to_date))
            appt_docs = defaultdict(list)
            appt_meta = {}
            for aid, pid, adate, doc_id in cr.fetchall():
                appt_docs[aid].append(doc_id)
                appt_meta[aid] = (pid, adate)
            for aid, (pid, adate) in appt_meta.items():
                docs = appt_docs[aid]
                cache['appt_by_patient_date'][(pid, adate)].append((aid, docs))
                cache['appt_before'][pid].append((adate, aid, docs))

            # Registrations / consultations for known patients
            cr.execute("""
                SELECT preg.id, preg.patient_id, preg.user_id, preg.date, preg.doctor,
                       preg.doctor_id, preg.status, pr.patient_id AS patient_name,
                       preg.ctid::text AS ctid
                  FROM patient_registration preg
             LEFT JOIN patient_reg pr ON pr.id = COALESCE(preg.user_id, preg.patient_id)
                 WHERE (preg.patient_id = ANY(%s) OR preg.user_id = ANY(%s))
                   AND preg.date <= %s
                 ORDER BY preg.date, preg.id
            """, (pids, pids, to_date))
            for rid, patient_id, user_id, rdate, doctor, doctor_char, status, pname, ctid in cr.fetchall():
                for pid in {patient_id, user_id}:
                    if not pid or pid not in patient_ids:
                        continue
                    cache['reg_by_patient_date'][(pid, rdate)].append((rid, doctor, doctor_char))
                    cache['reg_by_patient'][pid].append((rdate, rid, doctor, status, doctor_char))
                    cache['reg_by_patient_full'][pid].append(
                        (rdate, rid, doctor, status, doctor_char, ctid or '', patient_id))
                if pname:
                    cache['reg_by_name_date'][(pname, rdate)].append((rid, doctor, doctor_char))
                    cache['reg_by_name'][pname].append((rdate, rid, doctor, status, doctor_char))

            # Admissions
            cr.execute("""
                SELECT patient_id, admission_date, discharge_date, attending_doctor
                  FROM hospital_admitted_patient
                 WHERE patient_id = ANY(%s)
                 ORDER BY admission_date, id
            """, (pids,))
            for pid, adm, dis, doc in cr.fetchall():
                adm_d = adm.date() if hasattr(adm, 'date') else adm
                dis_d = dis.date() if hasattr(dis, 'date') and dis else dis
                cache['admission_by_patient'][pid].append((adm_d, dis_d, doc))

            # Discharged history (patient_id is reference_no)
            cr.execute("""
                SELECT pr.id, dpr.admitted_date, dpr.discharge_date, dpr.doctor
                  FROM discharged_patient_record dpr
                  JOIN patient_reg pr ON pr.reference_no = dpr.patient_id
                 WHERE pr.id = ANY(%s)
            """, (pids,))
            for pid, adm, dis, doc in cr.fetchall():
                cache['discharge_hist'][pid].append((adm, dis, doc))

        # Casualty / name-based registration lookup (may be other UHIDs with same name)
        names = [n for n in (patient_names or []) if n]
        if names:
            cr.execute("""
                SELECT preg.id, preg.patient_id, preg.user_id, preg.date, preg.doctor,
                       preg.doctor_id, preg.status, pr.patient_id AS patient_name,
                       preg.ctid::text AS ctid
                  FROM patient_registration preg
                  JOIN patient_reg pr ON pr.id = preg.user_id
                 WHERE pr.patient_id = ANY(%s)
                   AND preg.date <= %s
                 ORDER BY preg.date, preg.id
            """, (names, to_date))
            for rid, patient_id, user_id, rdate, doctor, doctor_char, status, pname, ctid in cr.fetchall():
                if not pname:
                    continue
                cache['reg_by_name_date'][(pname, rdate)].append((rid, doctor, doctor_char))
                cache['reg_by_name'][pname].append((rdate, rid, doctor, status, doctor_char))
                cache['reg_by_name_full'][pname].append(
                    (rdate, rid, doctor, status, doctor_char, ctid or ''))

        return cache

    def _resolve_reg_doctor(self, cache, entries):
        """Pick doctor from registration rows.

        Matches Odoo ``search(..., order='date desc', limit=1)``.
        Same-day tie-break uses ``id asc`` (typical PostgreSQL order when
        no secondary sort is given).
        ``entries`` items: ``(rid, doctor_id, doctor_name_char)``.
        """
        if not entries:
            return False
        entries = sorted(entries, key=lambda e: e[0])  # id asc
        _rid, doctor, doctor_char = entries[0]
        if doctor:
            return doctor
        if doctor_char:
            return cache['doctor_by_name'].get(doctor_char)
        return False

    def _pick_reg_on_or_before(self, cache, patient_id, bill_date, exclude_statuses=None):
        """Latest registration on/before bill_date (date desc, id asc)."""
        hist = [
            (d, rid, doc, st, dchar)
            for d, rid, doc, st, dchar in cache['reg_by_patient'].get(patient_id, [])
            if d and d <= bill_date
            and (not exclude_statuses or (st or '') not in exclude_statuses)
        ]
        if not hist:
            return False
        # date desc, id asc (align with order='date desc' without secondary id)
        hist.sort(key=lambda x: (-x[0].toordinal(), x[1]))
        return self._resolve_reg_doctor(cache, [(hist[0][1], hist[0][2], hist[0][4])])

    def _resolve_standard_doctor(self, cache, patient_id, bill_date, bill_type, patient_name=None):
        if not patient_id or not bill_date:
            return False
        if hasattr(bill_date, 'date'):
            bill_date = bill_date.date()

        doctor = False
        if bill_type == 'admitted':
            for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                if adm_d and adm_d <= bill_date and (not dis_d or bill_date <= dis_d):
                    doctor = doc
                    break
            if not doctor:
                for adm, dis, doc in cache['discharge_hist'].get(patient_id, []):
                    if adm and dis and adm <= datetime.combine(bill_date, dt_time.max) and dis >= datetime.combine(bill_date, dt_time.min):
                        doctor = doc
                        break

        if not doctor and bill_type != 'admitted':
            appts = cache['appt_by_patient_date'].get((patient_id, bill_date), [])
            if appts:
                # latest appointment id, first doctor
                appts_sorted = sorted(appts, key=lambda x: x[0], reverse=True)
                if appts_sorted[0][1]:
                    doctor = appts_sorted[0][1][0]

        if not doctor:
            entries = cache['reg_by_patient_date'].get((patient_id, bill_date), [])
            if not entries and patient_name:
                entries = [
                    (rid, doc, dchar)
                    for rid, doc, dchar in cache['reg_by_name_date'].get((patient_name, bill_date), [])
                ]
            doctor = self._resolve_reg_doctor(cache, entries)

        if not doctor:
            # historical registration (date < bill_date), date desc / id asc
            hist = [
                (d, rid, doc, st, dchar)
                for d, rid, doc, st, dchar in cache['reg_by_patient'].get(patient_id, [])
                if d and d < bill_date
            ]
            if hist:
                hist.sort(key=lambda x: (-x[0].toordinal(), x[1]))
                doctor = self._resolve_reg_doctor(cache, [(hist[0][1], hist[0][2], hist[0][4])])

        if not doctor and bill_type != 'admitted':
            befores = [x for x in cache['appt_before'].get(patient_id, []) if x[0] and x[0] < bill_date]
            if befores:
                befores.sort(key=lambda x: (x[0], x[1]))
                docs = befores[-1][2]
                if docs:
                    doctor = docs[0]

        if not doctor:
            master = cache['master'].get(patient_id, (None, None))
            doctor = master[1] if bill_type == 'admitted' else master[0]
            if not doctor:
                doctor = master[0] or master[1]

        return doctor or False

    def _resolve_pharmacy_doctor(self, cache, row):
        """Match pharmacy.description._compute_doctor_name (report-only).

        ``row`` keys: patient_id, bill_date, bill_type (op_category), order_doctor,
        doc_name, master_doctor.
        """
        patient_id = row.get('patient_id')
        bill_date = row.get('bill_date')
        op_category = row.get('bill_type')
        if not patient_id or not bill_date:
            return False
        if hasattr(bill_date, 'date'):
            bill_date = bill_date.date()

        def _doc_from_reg(doc, dchar):
            return doc or cache['doctor_by_name'].get(dchar) or False

        def _pick_op_reg():
            # search | user_id OR patient_id, order date desc (ctid tie-break)
            hist = [
                (d, rid, doc, dchar, ct)
                for d, rid, doc, st, dchar, ct, _ppid in cache['reg_by_patient_full'].get(patient_id, [])
                if d and d <= bill_date
            ]
            if not hist:
                return False
            hist.sort(key=lambda x: (-x[0].toordinal(), x[4]))
            return _doc_from_reg(hist[0][2], hist[0][3])

        def _pick_ip_reg():
            # patient_id = uhid only, status not in admitted/proceed_discharge, doctor M2O only
            hist = [
                (d, rid, doc, ct)
                for d, rid, doc, st, dchar, ct, ppid in cache['reg_by_patient_full'].get(patient_id, [])
                if d and d <= bill_date
                and ppid == patient_id
                and (st or '') not in ('admitted', 'proceed_discharge')
                and doc
            ]
            if not hist:
                return False
            hist.sort(key=lambda x: (-x[0].toordinal(), x[3]))
            return hist[0][2]

        if op_category == 'op':
            doctor = _pick_op_reg()
            if doctor:
                return doctor
            return row.get('doc_name') or False

        doctor = False
        if op_category == 'admitted':
            for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                if adm_d and adm_d <= bill_date and (not dis_d or bill_date <= dis_d):
                    doctor = doc
                    break
            if not doctor:
                for adm, dis, doc in cache['discharge_hist'].get(patient_id, []):
                    if adm and dis and adm <= datetime.combine(bill_date, dt_time.max) and dis >= datetime.combine(bill_date, dt_time.min):
                        doctor = doc
                        break

        if not doctor and row.get('order_doctor'):
            doctor = row['order_doctor']

        if not doctor:
            doctor = _pick_ip_reg()

        if not doctor:
            doctor = row.get('doc_name') or row.get('master_doctor')

        if not doctor:
            befores = [x for x in cache['appt_before'].get(patient_id, []) if x[0] and x[0] <= bill_date]
            if befores:
                befores.sort(key=lambda x: (x[0], x[1]))
                docs = befores[-1][2]
                if docs:
                    doctor = docs[0]
        return doctor or False

    def _resolve_lab_doctor(self, cache, row):
        """Match doctor.lab.report._compute_doctor_name (report-only, no form changes).

        ``row`` keys from lab SQL: patient_id, bill_date, bill_type, admitted_check,
        user_status, order_doctor, reg_doctor, doc_name, master_doctor.
        """
        patient_id = row.get('patient_id')
        bill_date = row.get('bill_date')
        bill_type = row.get('bill_type')
        if not patient_id or not bill_date:
            return False
        if hasattr(bill_date, 'date'):
            bill_date = bill_date.date()

        doctor = False

        # Priority 0: discharged restore
        if row.get('user_status') == 'discharged':
            if row.get('admitted_check'):
                doctor = row.get('master_doctor') or row.get('doc_name')
            else:
                for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                    if adm_d and adm_d <= bill_date and dis_d and bill_date <= dis_d:
                        doctor = doc
                        break
            if doctor:
                return doctor

        # Priority 1: consultant on linked patient.registration (order)
        if row.get('order_doctor'):
            doctor = row['order_doctor']

        if bill_type == 'admitted':
            for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                if adm_d and adm_d <= bill_date and (
                        not dis_d or bill_date <= dis_d
                        or row.get('user_status') == 'discharged'):
                    doctor = doc
                    break
            if not doctor:
                for adm, dis, doc in cache['discharge_hist'].get(patient_id, []):
                    if adm and dis and adm <= datetime.combine(bill_date, dt_time.max) and dis >= datetime.combine(bill_date, dt_time.min):
                        doctor = doc
                        break

        # OP / fallback: latest registration by patient_id only (date desc; ctid tie-break)
        if not doctor and row.get('reg_doctor'):
            doctor = row['reg_doctor']

        if not doctor:
            doctor = row.get('master_doctor') or row.get('doc_name')

        if not doctor:
            befores = [x for x in cache['appt_before'].get(patient_id, []) if x[0] and x[0] <= bill_date]
            if befores:
                befores.sort(key=lambda x: (x[0], x[1]))
                docs = befores[-1][2]
                if docs:
                    doctor = docs[0]
        return doctor or False

    def _resolve_casualty_doctor(self, cache, patient_id, bill_date, bill_type, patient_name=None):
        """Match casuality.billing._compute_doctor_name (report-only).

        Registration pick uses date desc + ctid (same as Odoo order='date desc'
        LIMIT 1), including patient_name OR matches.
        """
        if not patient_id or not bill_date:
            return False
        if hasattr(bill_date, 'date'):
            bill_date = bill_date.date()

        def _doc(doc, dchar):
            return doc or cache['doctor_by_name'].get(dchar) or False

        def _pick_reg(before_only=False):
            hist = []
            seen = set()
            for d, rid, doc, st, dchar, ct, _ppid in cache['reg_by_patient_full'].get(patient_id, []):
                if not d:
                    continue
                if before_only:
                    if not (d < bill_date):
                        continue
                else:
                    if not (d <= bill_date):
                        continue
                hist.append((d, rid, doc, dchar, ct))
                seen.add(rid)
            if patient_name:
                for d, rid, doc, st, dchar, ct in cache['reg_by_name_full'].get(patient_name, []):
                    if not d or rid in seen:
                        continue
                    if before_only:
                        if not (d < bill_date):
                            continue
                    else:
                        if not (d <= bill_date):
                            continue
                    hist.append((d, rid, doc, dchar, ct))
                    seen.add(rid)
            if not hist:
                return False
            hist.sort(key=lambda x: (-x[0].toordinal(), x[4]))  # date desc, ctid asc
            return _doc(hist[0][2], hist[0][3])

        # Compute first looks same-day, then historical — equivalent to date <= bill_date
        reg_doctor = _pick_reg(before_only=False)

        doctor = False
        if bill_type == 'admitted':
            for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                if adm_d and adm_d <= bill_date and (not dis_d or bill_date <= dis_d):
                    doctor = doc
                    break
            if not doctor:
                doctor = reg_doctor
            if not doctor:
                for adm, dis, doc in cache['discharge_hist'].get(patient_id, []):
                    if adm and dis and adm <= datetime.combine(bill_date, dt_time.max) and dis >= datetime.combine(bill_date, dt_time.min):
                        doctor = doc
                        break
            if not doctor:
                master = cache['master'].get(patient_id, (None, None))
                doctor = master[1] or master[0]
            return doctor or False

        # OP: appointment today → reg (same-day/hist) → historical appt → master → admission
        appts = cache['appt_by_patient_date'].get((patient_id, bill_date), [])
        if appts:
            appts_sorted = sorted(appts, key=lambda x: x[0], reverse=True)
            if appts_sorted[0][1]:
                doctor = appts_sorted[0][1][0]

        if not doctor and reg_doctor:
            doctor = reg_doctor

        if not doctor:
            befores = [x for x in cache['appt_before'].get(patient_id, []) if x[0] and x[0] < bill_date]
            if befores:
                befores.sort(key=lambda x: (x[0], x[1]))
                docs = befores[-1][2]
                if docs:
                    doctor = docs[0]

        if not doctor:
            master = cache['master'].get(patient_id, (None, None))
            doctor = master[0]  # doc_name

        if not doctor:
            for adm_d, dis_d, doc in reversed(cache['admission_by_patient'].get(patient_id, [])):
                if adm_d and adm_d <= bill_date and (not dis_d or bill_date <= dis_d):
                    doctor = doc
                    break

        return doctor or False

    def _doctor_name(self, cache, doctor_id):
        if not doctor_id:
            return 'Unknown'
        return cache['doctor_names'].get(doctor_id) or 'Unknown'

    def _aggregate_rows(self, result, result_key, rows, cache, resolve_fn, doctor_filter_id=False):
        """rows: iterable of dicts with amount + fields needed by resolve_fn."""
        for row in rows:
            amount = row.get('amount') or 0.0
            if not amount:
                continue
            doc_id = resolve_fn(row, cache)
            if doctor_filter_id and doc_id != doctor_filter_id:
                continue
            self._set_summary_amount(result, self._doctor_name(cache, doc_id), result_key, amount)

    # ------------------------------------------------------------------
    # Existing fast SQL for OP registration / revisit
    # ------------------------------------------------------------------
    def _sql_op_registration_sum(self, result, from_date, to_date, doctor_id=False):
        if not self._columns_exist(self.env['patient.reg'], {
            'time', 'doc_name', 'consultation_fee', 'registration_fee', 'status', 'vssc_boolean'
        }):
            return False
        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND pr.doc_name = %s"
            params.append(doctor_id)
        query = """
            SELECT COALESCE(dp.name, 'Unknown'),
                   COALESCE(SUM(pr.consultation_fee), 0.0),
                   COALESCE(SUM(prf.fee), 0.0)
              FROM patient_reg pr
         LEFT JOIN doctor_profile dp ON dp.id = COALESCE(pr.doc_name, pr.doctor)
         LEFT JOIN patient_registration_fee prf ON prf.id = pr.registration_fee
             WHERE pr.time >= %s AND pr.time <= %s
               AND COALESCE(pr.status, '') <> 'cancelled'
               {doctor_filter}
          GROUP BY dp.name
        """.format(doctor_filter=doctor_filter)
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(query, params)
                for doctor_name, consultation_amount, registration_fee in self.env.cr.fetchall():
                    self._set_summary_amount(result, doctor_name, 'consultation_amount', consultation_amount)
                    self._set_summary_amount(result, doctor_name, 'registration_fee', registration_fee)
        except Exception:
            return False
        return True

    def _sql_revisit_sum(self, result, from_date, to_date, doctor_id=False):
        """Revisit = appointment consultation fee only (matches Doctor Billing PDF).

        Fee formula: fee_applied → VSSC 400 / doctor consultation_fee_doctor, else 0.
        Attributed to first doctor (lowest doctor_profile_id).
        """
        Appointment = self.env['patient.appointment']
        doctor_field = Appointment._fields['doctor_ids']
        table = Appointment._table
        relation_table = doctor_field.relation
        column1 = doctor_field.column1
        column2 = doctor_field.column2
        if (not self._columns_exist(Appointment, {
            'appointment_date', 'status', 'patient_id', 'fee_applied'
        }) or not self._columns_exist(relation_table, {column1, column2}, require_stored=False)):
            return False

        status_sql = "COALESCE(a.status, '') <> 'cancelled'"
        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND fd.doctor_id = %s"
            params.append(doctor_id)

        assigned_query = """
            WITH first_doctor AS (
                SELECT DISTINCT ON ({column1})
                       {column1} AS appointment_id,
                       {column2} AS doctor_id
                  FROM {relation_table}
              ORDER BY {column1}, {column2}
            )
            SELECT COALESCE(dp.name, 'Unknown'),
                   COALESCE(SUM(
                       CASE WHEN COALESCE(a.fee_applied, FALSE) THEN
                           CASE WHEN COALESCE(patient.vssc_boolean, FALSE) THEN 400
                                ELSE COALESCE(fee_doc.consultation_fee_doctor, 0) END
                       ELSE 0 END
                   ), 0.0)
              FROM {table} a
              JOIN first_doctor fd ON fd.appointment_id = a.id
         LEFT JOIN doctor_profile dp ON dp.id = fd.doctor_id
         LEFT JOIN doctor_profile fee_doc ON fee_doc.id = fd.doctor_id
         LEFT JOIN patient_reg patient ON patient.id = a.patient_id
             WHERE a.appointment_date >= %s AND a.appointment_date <= %s
               AND {status_sql}
               {doctor_filter}
          GROUP BY dp.name
        """.format(
            table=table, relation_table=relation_table, column1=column1, column2=column2,
            status_sql=status_sql, doctor_filter=doctor_filter,
        )
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(assigned_query, params)
                rows = self.env.cr.fetchall()
                unknown_amount = 0.0
                if not doctor_id:
                    # Appointments with no doctor: keep prior behaviour (registration_fee bucket)
                    self.env.cr.execute("""
                        SELECT COALESCE(SUM(COALESCE(a.registration_fee, 0)), 0.0)
                          FROM {table} a
                         WHERE a.appointment_date >= %s AND a.appointment_date <= %s
                           AND {status_sql}
                           AND NOT EXISTS (
                               SELECT 1 FROM {relation_table} r WHERE r.{column1} = a.id
                           )
                    """.format(
                        table=table, relation_table=relation_table, column1=column1,
                        status_sql=status_sql,
                    ), [from_date, to_date])
                    unknown_amount = self.env.cr.fetchone()[0] or 0.0
        except Exception:
            return False
        for doctor_name, amount in rows:
            self._set_summary_amount(result, doctor_name, 'revisit_amount', amount)
        if unknown_amount:
            self._set_summary_amount(result, 'Unknown', 'revisit_amount', unknown_amount)
        return True

    def _fetch_bill_rows(self, query, params):
        self.env.cr.execute(query, params)
        cols = [d[0] for d in self.env.cr.description]
        return [dict(zip(cols, row)) for row in self.env.cr.fetchall()]

    def get_doctor_billing_summary(self, from_date, to_date):
        result = {}
        doctor_id = self.doctor.id if self.doctor else False
        cr = self.env.cr

        # 1-2: OP registration + revisit (already SQL-fast)
        if not self._sql_op_registration_sum(result, from_date, to_date, doctor_id):
            consults = self.env['patient.reg'].search([
                ('time', '>=', from_date), ('time', '<=', to_date),
                ('status', '!=', 'cancelled'),
            ] + ([('doc_name', '=', doctor_id)] if doctor_id else []))
            for rec in consults:
                doctor_obj = rec.doc_name or rec.doctor
                doctor = doctor_obj.name if doctor_obj else 'Unknown'
                self._set_summary_amount(result, doctor, 'consultation_amount', rec.consultation_fee or 0.0)
                if rec.registration_fee:
                    self._set_summary_amount(result, doctor, 'registration_fee', rec.registration_fee.fee)

        if not self._sql_revisit_sum(result, from_date, to_date, doctor_id):
            rev = self.env['patient.appointment'].search([
                ('appointment_date', '>=', from_date), ('appointment_date', '<=', to_date),
                ('status', '!=', 'cancelled'),
            ] + ([('doctor_ids', '=', doctor_id)] if doctor_id else []))
            for rec in rev:
                if rec.doctor_ids:
                    doctor = rec.doctor_ids.sorted('id')[:1]
                    if doctor_id and doctor.id != doctor_id:
                        continue
                    self._set_summary_amount(
                        result, doctor.name, 'revisit_amount', rec.consultation_fee or 0.0)
                else:
                    self._set_summary_amount(
                        result, 'Unknown', 'revisit_amount', rec.registration_fee or 0.0)

        paid_vssc = self._paid_vssc_where('t')

        # Fetch all other bill rows first, then one shared doctor cache
        general_rows = self._fetch_bill_rows("""
            SELECT t.mrd_no AS patient_id, t.bill_date, t.bill_type,
                   t.patient_name, COALESCE(t.total_amount, 0) AS amount
              FROM general_billing t
             WHERE t.bill_date >= %s AND t.bill_date <= %s AND """ + paid_vssc, [from_date, to_date])

        lab_rows = self._fetch_bill_rows("""
            SELECT p.id AS lab_id,
                   p.user_ide AS patient_id,
                   p.date AS bill_date,
                   p.bill_type,
                   COALESCE(p.admitted_check, false) AS admitted_check,
                   preg_order.doctor AS order_doctor,
                   pr.status AS user_status,
                   pr.doc_name AS doc_name,
                   pr.doctor AS master_doctor,
                   reg.doctor AS reg_doctor,
                   COALESCE(line_amt.amount, 0) - COALESCE(p.discount, 0) AS amount
              FROM doctor_lab_report p
         LEFT JOIN patient_reg pr ON pr.id = p.user_ide
         LEFT JOIN patient_registration preg_order ON preg_order.id = p.patient_id
         LEFT JOIN (
                    SELECT DISTINCT ON (p2.id)
                           p2.id AS lab_id,
                           preg.doctor AS doctor
                      FROM doctor_lab_report p2
                 LEFT JOIN patient_registration preg
                        ON preg.patient_id = p2.user_ide
                       AND preg.date <= p2.date
                     WHERE p2.date >= %s AND p2.date <= %s
                       AND COALESCE(p2.status, '') <> 'cancelled'
                  ORDER BY p2.id, preg.date DESC NULLS LAST, preg.ctid
                   ) reg ON reg.lab_id = p.id
         LEFT JOIN (
                    SELECT l.lab_billing_id,
                           COALESCE(SUM(COALESCE(li.rate, 0)), 0) AS amount
                      FROM lab_billing_page l
                 LEFT JOIN lab_investigation li ON li.id = l.lab_type_id
                  GROUP BY l.lab_billing_id
                   ) line_amt ON line_amt.lab_billing_id = p.id
             WHERE p.date >= %s AND p.date <= %s
               AND COALESCE(p.status, '') <> 'cancelled'
        """, [from_date, to_date, from_date, to_date])

        pharm_rows = self._fetch_bill_rows("""
            SELECT p.id AS pharmacy_id,
                   p.uhid_id AS patient_id,
                   p.date AS bill_date,
                   p.op_category AS bill_type,
                   preg_order.doctor AS order_doctor,
                   pr.doc_name AS doc_name,
                   pr.doctor AS master_doctor,
                   COALESCE(line_amt.amount, 0) AS amount
              FROM pharmacy_description p
         LEFT JOIN patient_reg pr ON pr.id = p.uhid_id
         LEFT JOIN patient_registration preg_order ON preg_order.id = p.patient_id
         LEFT JOIN (
                    SELECT pharmacy_id,
                           COALESCE(SUM(COALESCE(rate, 0)), 0) AS amount
                      FROM pharmacy_prescription_line
                  GROUP BY pharmacy_id
                   ) line_amt ON line_amt.pharmacy_id = p.id
             WHERE p.date >= %s AND p.date <= %s AND """ + self._paid_vssc_where('p'), [from_date, to_date])

        discharge_rows = self._fetch_bill_rows("""
            SELECT t.doctor AS doctor_id, COALESCE(t.net_amount, 0) AS amount
              FROM discharge_billing t
             WHERE t.bill_date >= %s AND t.bill_date <= %s
               AND COALESCE(t.status, '') <> 'cancelled'
        """, [from_date, to_date])

        casualty_rows = self._fetch_bill_rows("""
            SELECT t.id AS casualty_id,
                   t.mrd_no AS patient_id, t.bill_date, t.bill_type,
                   t.patient_name, COALESCE(t.net_amount, 0) AS amount
              FROM casuality_billing t
             WHERE t.bill_date >= %s AND t.bill_date <= %s AND """ + paid_vssc, [from_date, to_date])

        ot_rows = self._fetch_bill_rows("""
            SELECT t.mrd_no AS patient_id, t.bill_date, t.bill_type,
                   t.doctor_override AS override_doctor,
                   COALESCE(t.total_amount, 0) AS amount
              FROM ot_billing t
             WHERE t.bill_date >= %s AND t.bill_date <= %s AND """ + paid_vssc, [from_date, to_date])

        xray_rows = self._fetch_bill_rows("""
            SELECT t.mrd_no AS patient_id, t.bill_date, t.bill_type,
                   COALESCE(t.total_amount, 0) AS amount
              FROM xray_billing t
             WHERE t.bill_date >= %s AND t.bill_date <= %s AND """ + paid_vssc, [from_date, to_date])

        audio_rows = self._fetch_bill_rows("""
            SELECT t.mrd_no AS patient_id, t.bill_date, t.bill_type,
                   GREATEST(
                       COALESCE(line_amt.amount, 0) + COALESCE(t.rent, 0)
                       - COALESCE(t.discount, 0)
                       - COALESCE(t.advance_amount, 0)
                   , 0) AS amount
              FROM audiology_billing t
         LEFT JOIN (
                    SELECT l.bill_line_id,
                           COALESCE(SUM(
                               COALESCE(l.rate, 0) * COALESCE(l.quantity, 1)
                               * (1 + COALESCE(dt.tax, 0) / 100.0)
                           ), 0) AS amount
                      FROM audiology_bill_line l
                 LEFT JOIN dept_tax dt ON dt.id = l.tax
                  GROUP BY l.bill_line_id
                   ) line_amt ON line_amt.bill_line_id = t.id
             WHERE t.bill_date >= %s AND t.bill_date <= %s AND """ + paid_vssc, [from_date, to_date])

        patient_ids = set()
        for rows in (general_rows, lab_rows, pharm_rows, casualty_rows, ot_rows, xray_rows, audio_rows):
            for row in rows:
                if row.get('patient_id'):
                    patient_ids.add(row['patient_id'])

        # Name-based registration lookup only for casualty (form matches by patient name)
        casualty_names = {
            row.get('patient_name') for row in casualty_rows if row.get('patient_name')
        }

        cache = self._preload_doctor_cache(patient_ids, from_date, to_date, casualty_names)

        self._aggregate_rows(
            result, 'general_amount', general_rows, cache,
            lambda row, c: self._resolve_standard_doctor(
                c, row['patient_id'], row['bill_date'], row.get('bill_type'), row.get('patient_name')),
            doctor_id)

        # Lab / Pharmacy / Casualty: fast cache resolve (same rules as form computes,
        # avoids slow per-row ORM computes that block production).
        self._aggregate_rows(
            result, 'lab_amount', lab_rows, cache,
            lambda row, c: self._resolve_lab_doctor(c, row),
            doctor_id)

        self._aggregate_rows(
            result, 'pharmacy_amount', pharm_rows, cache,
            lambda row, c: self._resolve_pharmacy_doctor(c, row),
            doctor_id)

        # Discharge uses stored doctor
        for row in discharge_rows:
            amount = row.get('amount') or 0.0
            if not amount:
                continue
            doc_id = row.get('doctor_id')
            if doctor_id and doc_id != doctor_id:
                continue
            self._set_summary_amount(
                result, self._doctor_name(cache, doc_id) if doc_id else 'Unknown',
                'ip_part_amount', amount)

        self._aggregate_rows(
            result, 'casuality_amount', casualty_rows, cache,
            lambda row, c: self._resolve_casualty_doctor(
                c, row['patient_id'], row['bill_date'], row.get('bill_type'), row.get('patient_name')),
            doctor_id)

        def _resolve_ot(row, c):
            if row.get('override_doctor'):
                return row['override_doctor']
            return self._resolve_standard_doctor(
                c, row['patient_id'], row['bill_date'], row.get('bill_type'))

        self._aggregate_rows(result, 'ot_amount', ot_rows, cache, _resolve_ot, doctor_id)

        self._aggregate_rows(
            result, 'xray_amount', xray_rows, cache,
            lambda row, c: self._resolve_standard_doctor(
                c, row['patient_id'], row['bill_date'], row.get('bill_type')),
            doctor_id)

        self._aggregate_rows(
            result, 'audiology_amount', audio_rows, cache,
            lambda row, c: self._resolve_standard_doctor(
                c, row['patient_id'], row['bill_date'], row.get('bill_type')),
            doctor_id)

        return result


class DoctorBillingReport(models.AbstractModel):
    _name = "report.homeo_doctor.doctor_billing_pdf_template"
    _description = 'Doctor Billing PDF Report'

    def _get_report_values(self, docids, data=None):
        active_id = self.env.context.get('active_id')
        wizard = self.env['doctor.billing.report.wizard'].browse(active_id)

        from_date = data.get('from_date')
        to_date = data.get('to_date')

        report_data = wizard.get_doctor_billing_summary(from_date, to_date)

        total_row = {
            'consultation_amount': 0.0,
            'registration_fee': 0.0,
            'revisit_amount': 0.0,
            'general_amount': 0.0,
            'lab_amount': 0.0,
            'pharmacy_amount': 0.0,
            'ip_part_amount': 0.0,
            'casuality_amount': 0.0,
            'ot_amount': 0.0,
            'xray_amount': 0.0,
            'audiology_amount': 0.0,
        }

        for values in report_data.values():
            for key in total_row:
                total_row[key] += values.get(key, 0.0)

        total_row['row_total'] = sum(total_row.values())

        return {
            'doc_ids': [wizard.id],
            'doc_model': 'doctor.billing.report.wizard',
            'data': data,
            'report_data': report_data,
            'total_row': total_row,
        }

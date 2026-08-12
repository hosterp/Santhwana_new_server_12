from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError

class DoctorBillingReportWizard(models.TransientModel):
    _name = 'doctor.billing.report.wizard'
    _description = 'Doctor Billing Report Wizard'

    from_date = fields.Date(required=True)
    to_date = fields.Date(required=True)
    doctor=fields.Many2one('doctor.profile',string='Doctor')

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

    def _columns_exist(self, target, columns):
        """Check if columns exist in DB AND (if target is a model) are explicitly stored in the current Odoo code."""
        # Use Odoo's _fields if target is a model object
        if hasattr(target, '_fields'):
            for col in columns:
                if col not in target._fields:
                    return False
                if not target._fields[col].store:
                    return False
            table = target._table
        else:
            table = target # Case for pure SQL table names (like M2M relation tables)
                
        # Also check the DB schema
        self.env.cr.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = ANY(%s)
        """, (table, list(columns)))
        existing = {row[0] for row in self.env.cr.fetchall()}
        return set(columns).issubset(existing)

    def _paid_vssc_where(self, table_alias, vssc_field='vssc_boolean'):
        return """
            (
                {alias}.status NOT IN ('unpaid', 'cancelled')
                OR ({alias}.{vssc_field} = TRUE AND {alias}.status != 'cancelled')
            )
        """.format(alias=table_alias, vssc_field=vssc_field)

    def _sql_parent_sum(self, result, model_name, date_field, doctor_field, amount_field, result_key,
                        from_date, to_date, status_sql, doctor_id=False):
        Model = self.env[model_name]
        table = Model._table
        required_columns = {date_field, doctor_field, amount_field, 'status'}
        if not self._columns_exist(Model, required_columns):
            return False

        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND t.{doctor_field} = %s".format(doctor_field=doctor_field)
            params.append(doctor_id)

        query = """
            SELECT COALESCE(dp.name, 'Unknown') AS doctor_name,
                   COALESCE(SUM(t.{amount_field}), 0.0) AS amount
              FROM {table} t
         LEFT JOIN doctor_profile dp ON dp.id = t.{doctor_field}
             WHERE t.{date_field} >= %s
               AND t.{date_field} <= %s
               AND {status_sql}
               {doctor_filter}
          GROUP BY dp.name
        """.format(
            table=table,
            amount_field=amount_field,
            doctor_field=doctor_field,
            date_field=date_field,
            status_sql=status_sql,
            doctor_filter=doctor_filter,
        )
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(query, params)
                rows = self.env.cr.fetchall()
        except Exception:
            return False
        for doctor_name, amount in rows:
            self._set_summary_amount(result, doctor_name, result_key, amount)
        return True

    def _sql_op_registration_sum(self, result, from_date, to_date, doctor_id=False):
        table = self.env['patient.reg']._table
        required_columns = {'time', 'doc_name', 'consultation_fee', 'registration_fee', 'status', 'vssc_boolean'}
        if not self._columns_exist(self.env['patient.reg'], required_columns):
            return False

        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND pr.doc_name = %s"
            params.append(doctor_id)

        query = """
            SELECT COALESCE(dp.name, 'Unknown') AS doctor_name,
                   COALESCE(SUM(pr.consultation_fee), 0.0) AS consultation_amount,
                   COALESCE(SUM(prf.fee), 0.0) AS registration_fee
              FROM patient_reg pr
         LEFT JOIN doctor_profile dp ON dp.id = COALESCE(pr.doc_name, pr.doctor)
         LEFT JOIN patient_registration_fee prf ON prf.id = pr.registration_fee
             WHERE pr.time >= %s
               AND pr.time <= %s
               AND (
                    pr.status NOT IN ('unpaid', 'cancelled')
                    OR (pr.vssc_boolean = TRUE AND pr.status != 'cancelled')
               )
               {doctor_filter}
          GROUP BY dp.name
        """.format(doctor_filter=doctor_filter)
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(query, params)
                rows = self.env.cr.fetchall()
        except Exception:
            return False
        for doctor_name, consultation_amount, registration_fee in rows:
            self._set_summary_amount(result, doctor_name, 'consultation_amount', consultation_amount)
            self._set_summary_amount(result, doctor_name, 'registration_fee', registration_fee)
        return True

    def _sql_line_sum(self, result, parent_model, line_model, parent_link_field, line_amount_field,
                      date_field, doctor_field, result_key, from_date, to_date, status_sql, doctor_id=False,
                      parent_adjust_field=False):
        Parent = self.env[parent_model]
        Line = self.env[line_model]
        parent_table = Parent._table
        line_table = Line._table
        parent_columns = {date_field, doctor_field, 'status'}
        if parent_adjust_field:
            parent_columns.add(parent_adjust_field)
        line_columns = {parent_link_field, line_amount_field}
        if not self._columns_exist(Parent, parent_columns) or not self._columns_exist(Line, line_columns):
            return False

        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND p.{doctor_field} = %s".format(doctor_field=doctor_field)
            params.append(doctor_id)

        parent_adjust_sql = ""
        parent_adjust_group = ""
        if parent_adjust_field:
            parent_adjust_sql = " - COALESCE(p.{parent_adjust_field}, 0.0)".format(
                parent_adjust_field=parent_adjust_field)
            parent_adjust_group = ", p.{parent_adjust_field}".format(parent_adjust_field=parent_adjust_field)

        query = """
            SELECT COALESCE(dp.name, 'Unknown') AS doctor_name,
                   COALESCE(SUM(lines.parent_amount), 0.0) AS amount
              FROM (
                    SELECT p.id,
                           p.{doctor_field} AS doctor_id,
                           COALESCE(SUM(l.{line_amount_field}), 0.0){parent_adjust_sql} AS parent_amount
                      FROM {parent_table} p
                 LEFT JOIN {line_table} l ON l.{parent_link_field} = p.id
                     WHERE p.{date_field} >= %s
                       AND p.{date_field} <= %s
                       AND {status_sql}
                       {doctor_filter}
                  GROUP BY p.id, p.{doctor_field}{parent_adjust_group}
                   ) lines
         LEFT JOIN doctor_profile dp ON dp.id = lines.doctor_id
          GROUP BY dp.name
        """.format(
            parent_table=parent_table,
            line_table=line_table,
            line_amount_field=line_amount_field,
            parent_link_field=parent_link_field,
            doctor_field=doctor_field,
            date_field=date_field,
            status_sql=status_sql,
            doctor_filter=doctor_filter,
            parent_adjust_sql=parent_adjust_sql,
            parent_adjust_group=parent_adjust_group,
        )
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(query, params)
                rows = self.env.cr.fetchall()
        except Exception:
            return False
        for doctor_name, amount in rows:
            self._set_summary_amount(result, doctor_name, result_key, amount)
        return True

    def _sql_revisit_sum(self, result, from_date, to_date, doctor_id=False):
        Appointment = self.env['patient.appointment']
        doctor_field = Appointment._fields['doctor_ids']
        table = Appointment._table
        relation_table = doctor_field.relation
        column1 = doctor_field.column1
        column2 = doctor_field.column2
        if (not self._columns_exist(Appointment, {
            'appointment_date', 'status', 'patient_id', 'fee_applied'
        }) or not self._columns_exist(relation_table, {column1, column2})):
            return False

        status_sql = "(a.status = 'confirmed' OR (COALESCE(patient.vssc_boolean, FALSE) = TRUE AND a.status != 'cancelled'))"
        params = [from_date, to_date]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND r.{column2} = %s".format(column2=column2)
            params.append(doctor_id)

        assigned_query = """
            WITH first_doctor AS (
                SELECT {column1} AS appointment_id,
                       MIN({column2}) AS doctor_id
                  FROM {relation_table}
                 GROUP BY {column1}
            )
            SELECT COALESCE(dp.name, 'Unknown') AS doctor_name,
                   COALESCE(SUM(
                       CASE
                           WHEN COALESCE(a.fee_applied, FALSE) THEN
                               CASE
                                   WHEN COALESCE(patient.vssc_boolean, FALSE) THEN 400
                                   ELSE COALESCE(first_doc.consultation_fee_doctor, 0)
                               END
                           ELSE 0
                       END
                   ), 0.0) AS amount
              FROM {table} a
              JOIN {relation_table} r ON r.{column1} = a.id
         LEFT JOIN doctor_profile dp ON dp.id = r.{column2}
         LEFT JOIN patient_reg patient ON patient.id = a.patient_id
         LEFT JOIN first_doctor fd ON fd.appointment_id = a.id
         LEFT JOIN doctor_profile first_doc ON first_doc.id = fd.doctor_id
             WHERE a.appointment_date >= %s
               AND a.appointment_date <= %s
               AND {status_sql}
               {doctor_filter}
          GROUP BY dp.name
        """.format(
            table=table,
            relation_table=relation_table,
            column1=column1,
            column2=column2,
            status_sql=status_sql,
            doctor_filter=doctor_filter,
        )

        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(assigned_query, params)
                rows = self.env.cr.fetchall()
                unknown_amount = 0.0
                if not doctor_id:
                    unknown_query = """
                        SELECT COALESCE(SUM(a.registration_fee), 0.0) AS amount
                          FROM {table} a
                     LEFT JOIN patient_reg patient ON patient.id = a.patient_id
                         WHERE a.appointment_date >= %s
                           AND a.appointment_date <= %s
                           AND {status_sql}
                           AND NOT EXISTS (
                               SELECT 1
                                 FROM {relation_table} r
                                WHERE r.{column1} = a.id
                           )
                    """.format(
                        table=table,
                        relation_table=relation_table,
                        column1=column1,
                        status_sql=status_sql,
                    )
                    self.env.cr.execute(unknown_query, [from_date, to_date])
                    unknown_amount = self.env.cr.fetchone()[0] or 0.0
        except Exception:
            return False

        for doctor_name, amount in rows:
            self._set_summary_amount(result, doctor_name, 'revisit_amount', amount)
        if unknown_amount:
            self._set_summary_amount(result, 'Unknown', 'revisit_amount', unknown_amount)
        return True

    def _orm_sum_records(self, result, model_name, domain, doctor_field, amount_field, result_key):
        """Fallback method using ORM when SQL fails or for complex computed fields."""
        # Remove doctor filter from domain for un-stored search
        final_domain = []
        filter_doctor_id = False
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and leaf[0] == doctor_field:
                filter_doctor_id = leaf[2]
            else:
                final_domain.append(leaf)
        
        records = self.env[model_name].sudo().search(final_domain)
        
        for rec in records:
            # 1. Try primary field
            doctor_obj = getattr(rec, doctor_field, False)
            
            # 2. Strong Fallback: check all possible UHID links
            if not doctor_obj:
                uhid = False
                # Try every possible link field name across all billing models
                for fname in ['uhid_id', 'mrd_no', 'user_ide', 'patient_id', 'patient_reg_id']:
                    try:
                        val = getattr(rec, fname, False)
                        if val and (hasattr(val, 'doc_name') or hasattr(val, 'doctor')):
                            uhid = val
                            break
                    except Exception:
                        continue
                
                if uhid:
                    # patient.reg usually has doc_name (OP) and doctor (IP)
                    doctor_obj = getattr(uhid, 'doc_name', False) or getattr(uhid, 'doctor', False)
            
            doctor_name = doctor_obj.name if doctor_obj else 'Unknown'
            
            # Filter by doctor if wizard specified one
            if filter_doctor_id:
                if doctor_obj and doctor_obj.id == filter_doctor_id:
                    pass
                else:
                    continue

            self._set_summary_amount(result, doctor_name, result_key, rec[amount_field])

    def get_doctor_billing_summary(self, from_date, to_date):
        result = {}

        # 1. Consultation (patient.reg)
        consult_domain = [
            ('time', '>=', from_date),
            ('time', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            consult_domain += [('doc_name', '=', self.doctor.id)]

        if not self._sql_op_registration_sum(result, from_date, to_date, self.doctor.id if self.doctor else False):
            consults = self.env['patient.reg'].search(consult_domain)
            for rec in consults:
                doctor_obj = rec.doc_name or rec.doctor
                doctor = doctor_obj.name if doctor_obj else 'Unknown'
                self._set_summary_amount(result, doctor, 'consultation_amount', rec.consultation_fee or 0.0)
                if rec.registration_fee:
                    self._set_summary_amount(result, doctor, 'registration_fee', rec.registration_fee.fee)

        # for rec in consults:
        #     doctor = rec.doc_name.name if rec.doc_name else 'Unknown'
        #     set_result(doctor, 'consultation_amount', rec.consultation_fee)


        # 2. Revisit (patient.appointment)
        revisits =[
            ('appointment_date', '>=', from_date),
            ('appointment_date', '<=', to_date),
            '|',
            ('status', '=', 'confirmed'),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),

        ]
        if self.doctor:
            revisits += [('doctor_ids', '=', self.doctor.id)]
        if not self._sql_revisit_sum(result, from_date, to_date, self.doctor.id if self.doctor else False):
            rev=self.env['patient.appointment'].with_context(prefetch_fields=False).search(revisits)
            for rec in rev:
                if rec.doctor_ids:
                    for doctor in rec.doctor_ids:
                        self._set_summary_amount(result, doctor.name, 'revisit_amount', rec.consultation_fee)
                else:
                    self._set_summary_amount(result, 'Unknown', 'revisit_amount', rec.register_total_amount)

        # for rec in revisits:
        #     doctor = rec.doctor_ids.name if rec.doctor_ids else 'Unknown'
        #     set_result(doctor, 'revisit_amount', rec.register_total_amount)

        # 3. General Billing
        generals = [
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            generals += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'general.billing', 'bill_date', 'doctor', 'total_amount', 'general_amount',
                from_date, to_date, self._paid_vssc_where('t'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'general.billing', generals, 'doctor', 'total_amount', 'general_amount')

        # 4. Lab Billing
        labs = [
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            '|',
            ('status', '=', 'paid'),
            '&',
            ('vssc_check', '=', True),
            ('status', '!=', 'cancelled'),

        ]
        if self.doctor:
            labs += [('doctor_id', '=', self.doctor.id)]
        if not self._sql_line_sum(
                result, 'doctor.lab.report', 'lab.billing.page', 'lab_billing_id', 'total_amount',
                'date', 'doctor_id', 'lab_amount', from_date, to_date,
                "(p.status = 'paid' OR (p.vssc_check = TRUE AND p.status != 'cancelled'))",
                self.doctor.id if self.doctor else False, parent_adjust_field='discount'):
            self._orm_sum_records(result, 'doctor.lab.report', labs, 'doctor_id', 'total_bill_amount', 'lab_amount')

        # 5. Pharmacy Billing
        pharmacies = [
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            pharmacies += [('doctor_name', '=', self.doctor.id)]
        if not self._sql_line_sum(
                result, 'pharmacy.description', 'pharmacy.prescription.line', 'pharmacy_id', 'rate',
                'date', 'doctor_name', 'pharmacy_amount', from_date, to_date,
                self._paid_vssc_where('p'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'pharmacy.description', pharmacies, 'doctor_name', 'total_amount',
                                  'pharmacy_amount')

        ip_part = [
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', 'not in', ['unpaid', 'cancelled']),

        ]
        if self.doctor:
            ip_part += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'discharge.billing', 'bill_date', 'doctor', 'total_amount', 'ip_part_amount',
                from_date, to_date, "t.status NOT IN ('unpaid', 'cancelled')",
                self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'discharge.billing', ip_part, 'doctor', 'total_amount', 'ip_part_amount')
        casuality_bill = [
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            casuality_bill += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'casuality.billing', 'bill_date', 'doctor', 'net_amount', 'casuality_amount',
                from_date, to_date, self._paid_vssc_where('t'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'casuality.billing', casuality_bill, 'doctor', 'net_amount',
                                  'casuality_amount')
        ot_bill =[
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            ot_bill += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'ot.billing', 'bill_date', 'doctor', 'total_amount', 'ot_amount',
                from_date, to_date, self._paid_vssc_where('t'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'ot.billing', ot_bill, 'doctor', 'total_amount', 'ot_amount')
        xray_bill = [
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            xray_bill += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'xray.billing', 'bill_date', 'doctor', 'total_amount', 'xray_amount',
                from_date, to_date, self._paid_vssc_where('t'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'xray.billing', xray_bill, 'doctor', 'total_amount', 'xray_amount')
        audiology_bill =[
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.doctor:
            audiology_bill += [('doctor', '=', self.doctor.id)]
        if not self._sql_parent_sum(
                result, 'audiology.billing', 'bill_date', 'doctor', 'total_amount', 'audiology_amount',
                from_date, to_date, self._paid_vssc_where('t'), self.doctor.id if self.doctor else False):
            self._orm_sum_records(result, 'audiology.billing', audiology_bill, 'doctor', 'total_amount',
                                  'audiology_amount')

        return result


class DoctorBillingReport(models.AbstractModel):
    _name = "report.homeo_doctor.doctor_billing_pdf_template"
    _description = 'Doctor Billing PDF Report'

    def _get_report_values(self, docids, data=None):
        # Get wizard record using context
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

        # Loop through each doctor's values and add to column totals
        for values in report_data.values():
            for key in total_row:
                total_row[key] += values.get(key, 0.0)

        # ✅ Now compute overall row_total (sum of all column totals)
        total_row['row_total'] = sum(total_row.values())

        return {
            'doc_ids': [wizard.id],
            'doc_model': 'doctor.billing.report.wizard',
            'data': data,
            'report_data': report_data,
            'total_row': total_row,
        }

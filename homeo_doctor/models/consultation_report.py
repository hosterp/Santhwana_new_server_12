from odoo import api, fields, models
from odoo.fields import Datetime


class PatientReportWizard(models.TransientModel):
    _name = 'patient.report.wizard'
    _description = 'Patient Report Wizard'

    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    department_id = fields.Many2one(
        'doctor.department',
        string='Department',
        related='doctor_id.department_id',
        store=True,
    )

    @api.onchange('doctor_id')
    def onchange_doctor_id(self):
        if self.doctor_id and self.doctor_id.department_id:
            return {
                'domain': {
                    'department_id': [('id', '=', self.doctor_id.department_id.id)]
                },
                'value': {
                    'department_id': self.doctor_id.department_id.id
                }
            }
        return {
            'domain': {'department_id': []},
            'value': {'department_id': False}
        }

    def action_generate_report(self):
        report_data = self._get_report_data()
        return self.env.ref('homeo_doctor.patient_pdf_report_action').report_action(self, data={
            'report_data': report_data,
            'total_fee': report_data['total_fee'],
            'date_from': self.date_from,
            'date_to': self.date_to,
        })

    def _fetch_op_report_rows(self):
        """Fast SQL fetch for OP registration + revisit rows.

        Same amounts as ``register_total_amount`` compute:
        - patient.reg: VSSC → 400, else registration fee + consultation fee
        - patient.appointment: registration_fee + (fee_applied ? VSSC 400 /
          doctor consultation fee : 0)
        No ORM per-row computes — Excel/PDF stay in sync without changing data.
        """
        self.ensure_one()
        date_from = self.date_from
        date_to = self.date_to
        date_from_dt = Datetime.to_datetime(date_from).replace(hour=0, minute=0, second=0)
        date_to_dt = Datetime.to_datetime(date_to).replace(hour=23, minute=59, second=59)
        doctor_id = self.doctor_id.id if self.doctor_id else False
        cr = self.env.cr
        rows = []

        # 1) New OP registrations (patient.reg)
        params = [date_from_dt, date_to_dt]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = " AND pr.doc_name = %s"
            params.append(doctor_id)
        cr.execute("""
            SELECT pr.reference_no,
                   pr.time AS appt_date,
                   pr.patient_id AS patient_name,
                   pr.age,
                   pr.gender,
                   pr.phone_number,
                   COALESCE(dp.name, '') AS doctor_name,
                   CASE
                       WHEN COALESCE(pr.vssc_boolean, FALSE) THEN 400
                       ELSE COALESCE(prf.fee, 0) + COALESCE(pr.consultation_fee, 0)
                   END AS consultation_fee,
                   pr.bill_number,
                   'Registration' AS source
              FROM patient_reg pr
         LEFT JOIN doctor_profile dp ON dp.id = pr.doc_name
         LEFT JOIN patient_registration_fee prf ON prf.id = pr.registration_fee
             WHERE pr.time >= %s
               AND pr.time <= %s
               AND COALESCE(pr.status, '') <> 'cancelled'
               """ + doctor_filter + """
          ORDER BY pr.bill_number ASC NULLS LAST, pr.id
        """, params)
        rows.extend(cr.dictfetchall())

        # 2) Revisits (patient.appointment)
        params = [date_from, date_to]
        doctor_filter = ""
        if doctor_id:
            doctor_filter = """
               AND EXISTS (
                   SELECT 1
                     FROM doctor_profile_patient_appointment_rel rel
                    WHERE rel.patient_appointment_id = a.id
                      AND rel.doctor_profile_id = %s
               )
            """
            params.append(doctor_id)
        cr.execute("""
            SELECT preg.reference_no,
                   a.appointment_date AS appt_date,
                   preg.patient_id AS patient_name,
                   preg.age,
                   preg.gender,
                   preg.phone_number,
                   COALESCE((
                       SELECT string_agg(dp.name, ', ' ORDER BY dp.name)
                         FROM doctor_profile_patient_appointment_rel rel
                         JOIN doctor_profile dp ON dp.id = rel.doctor_profile_id
                        WHERE rel.patient_appointment_id = a.id
                   ), '') AS doctor_name,
                   COALESCE(a.registration_fee, 0) + CASE
                       WHEN COALESCE(a.fee_applied, FALSE) THEN
                           CASE
                               WHEN COALESCE(preg.vssc_boolean, FALSE) THEN 400
                               ELSE COALESCE((
                                   SELECT dp.consultation_fee_doctor
                                     FROM doctor_profile_patient_appointment_rel rel
                                     JOIN doctor_profile dp ON dp.id = rel.doctor_profile_id
                                    WHERE rel.patient_appointment_id = a.id
                                    ORDER BY rel.doctor_profile_id
                                    LIMIT 1
                               ), 0)
                           END
                       ELSE 0
                   END AS consultation_fee,
                   a.payment_receipt_number AS bill_number,
                   'Appointment' AS source
              FROM patient_appointment a
         LEFT JOIN patient_reg preg ON preg.id = a.patient_id
             WHERE a.appointment_date >= %s
               AND a.appointment_date <= %s
               AND COALESCE(a.status, '') <> 'cancelled'
               """ + doctor_filter + """
          ORDER BY a.payment_receipt_number ASC NULLS LAST, a.id
        """, params)
        rows.extend(cr.dictfetchall())

        rows.sort(key=lambda r: (r.get('appt_date') or date_from, r.get('bill_number') or ''))
        return rows

    def _get_report_data(self):
        report_rows = self._fetch_op_report_rows()
        report_data = []
        for rec in report_rows:
            report_data.append({
                'source': rec.get('source') or '',
                'reference_no': rec.get('reference_no') or '',
                'date': rec.get('appt_date'),
                'patient_name': rec.get('patient_name') or '',
                'age': rec.get('age') or 0,
                'gender': rec.get('gender') or '',
                'phone': rec.get('phone_number') or '',
                'doctor_name': rec.get('doctor_name') or '',
                'consultation_fee': rec.get('consultation_fee') or 0,
                'bill_number': rec.get('bill_number') or '',
            })
        total_fee = sum(item.get('consultation_fee', 0) or 0 for item in report_data)
        return {
            'report_data': report_data,
            'total_fee': total_fee,
        }

    def print_excel(self):
        base_url = '/patient/excel_report'
        params = '?date_from=%s&date_to=%s&doctor_id=%s' % (
            self.date_from,
            self.date_to,
            self.doctor_id.id if self.doctor_id else ''
        )
        return {
            'type': 'ir.actions.act_url',
            'url': base_url + params,
            'target': 'new',
        }

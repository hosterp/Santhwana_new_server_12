from odoo import api, fields, models
from odoo.fields import Datetime
import pytz

class PatientReportWizard(models.TransientModel):
    _name = 'patient.report.wizard'
    _description = 'Patient Report Wizard'

    date_from = fields.Date(string='From Date', required=True,default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True,default=fields.Date.today)
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
        # Code to generate report
        report_data = self._get_report_data()  # Call a method to get the report data
        return self.env.ref('homeo_doctor.patient_pdf_report_action').report_action(self, data={
            'report_data': report_data,
            'total_fee': report_data['total_fee'],
            'date_from': self.date_from,
            'date_to': self.date_to,
        })

    def _get_report_data(self):


        date_from_dt = Datetime.to_datetime(self.date_from).replace(hour=0, minute=0, second=0)
        date_to_dt = Datetime.to_datetime(self.date_to).replace(hour=23, minute=59, second=59)

        domain = [
            ('time', '>=', date_from_dt),
            ('time', '<=', date_to_dt),
            ('status','!=','cancelled')
        ]
        domain2 = [
            ('appointment_date', '>=', date_from_dt),
            ('appointment_date', '<=', date_to_dt),
            ('status', '!=', 'cancelled')
        ]

        # Add doctor filter only when selected
        if self.doctor_id:
            domain.append(('doc_name', '=', self.doctor_id.id))
            domain2.append(('doctor_ids', '=', self.doctor_id.id))

        # 1️⃣ Fetch from patient.reg
        patients_reg = self.env['patient.reg'].search(domain,order='bill_number asc')

        # 2️⃣ Fetch from patient.appointment
        patients_app = self.env['patient.appointment'].search(domain2,order='payment_receipt_number asc')

        report_data = []

        # 3️⃣ Append patient.reg data
        for patient in patients_reg:
            report_data.append({
                'source': 'Registration',
                'reference_no': patient.reference_no,
                'date': patient.time,
                'patient_name': patient.patient_id,
                'age': patient.age,
                'gender': patient.gender,
                'phone': patient.phone_number,
                'doctor_name': patient.doc_name.name,
                'consultation_fee': patient.register_total_amount,
                'bill_number': patient.bill_number,
            })

        # 4️⃣ Append patient.appointment data
        for app in patients_app:
            report_data.append({
                'source': 'Appointment',
                'reference_no': app.patient_id.reference_no,
                'date': app.appointment_date,
                'patient_name': app.patient_name,
                'age': app.age,
                'gender': app.gender,
                'phone': app.phone_number,
                'doctor_name': app.doctor_ids.name if app.doctor_ids else '',
                'consultation_fee': app.register_total_amount,
                'bill_number': app.payment_receipt_number,
            })
        total_fee = sum(item.get('consultation_fee', 0) for item in report_data)
        report_data.sort(key=lambda x: x['date'])
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

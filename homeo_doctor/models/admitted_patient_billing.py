from odoo import models, fields, api
from datetime import datetime

class AdmissionBillingWizard(models.TransientModel):
    _name = 'admission.billing.wizard'

    date_from = fields.Date(string="From Date", required=True,default=fields.Date.today)
    date_to = fields.Date(string="To Date", required=True,default=fields.Date.today)

    def action_generate_report(self):
        patient_records = self.env['patient.reg'].search([
            ('admitted_date', '>=', self.date_from),
            ('admitted_date', '<=', self.date_to),
            ('status', '=', 'admitted')
        ])

        report_data = []
        for patient in patient_records:
            report_data.append({
                'patient_name': patient.patient_id,
                'admitted_date': patient.admitted_date,
                'room': patient.room_number_new.room_number if patient.room_number_new else '',
                'total_amount': patient.admission_total_amount,
                'uhid': patient.reference_no,
            })

        return self._generate_pdf_report(report_data)

    def _generate_pdf_report(self, report_data):
        return self.env.ref('homeo_doctor._action_report_patient_admission_pdf').report_action(self, data={
            'report_data': report_data,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })

    def action_download_excel(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/export_patient_admission_report?date_from={self.date_from}&date_to={self.date_to}',
            'target': 'self',
        }

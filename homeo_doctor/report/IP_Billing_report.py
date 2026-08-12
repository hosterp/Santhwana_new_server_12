from odoo import models, fields, api
import base64
import io
import xlsxwriter
from odoo.http import request

class IPBillingReport(models.TransientModel):
    _name = 'ip.discharge.billing.report.wizard'
    _description = 'IP Billing Report'

    from_date = fields.Date(string="From Date", required=True, default=fields.Date.today)
    to_date = fields.Date(string="To Date", required=True, default=fields.Date.today)
    xlsx_file = fields.Binary(string="Download Report")
    file_name = fields.Char(string="File Name")
    def action_generate_report(self):
        domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
        ]

        discharge_records = self.env['discharge.billing'].search(domain, order='bill_date asc')

        report_lines = []
        grand_total = 0.0

        for rec in discharge_records:
            line_total = sum(rec.general_bill_line_ids.mapped('total_amt'))
            grand_total += line_total

            report_lines.append({
                'id': rec.id,
                'date': rec.bill_date.strftime('%d-%m-%Y') if rec.bill_date else '',
                'bill_number': rec.bill_number or '',
                'mrd_no': rec.mrd_no.reference_no or '',
                'patient_name': rec.patient_name or '',
                'mode_pay': rec.mode_pay or '',
                'doctor': rec.doctor.name or '',
                'total_amount': line_total,
            })

        report_data = {
            'report_data': report_lines,
            'total_sum': grand_total,
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
        }

        # Pass 'data' key explicitly
        return self.env.ref('homeo_doctor.action_report_discharge_billing_pdf').report_action(
            self, data={'data': report_data}
        )

    def action_download_excel(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/homeo_doctor/ip_billing_excel?from_date={self.from_date}&to_date={self.to_date}',
            'target': 'new',
        }

from odoo import models, fields, api
from odoo.exceptions import UserError


class LabPaidWizard(models.TransientModel):
    _name = 'lab.paid.wizard'
    _description = 'Lab Paid Bills Report Wizard'

    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)
    staff_id = fields.Many2one('hr.employee', string='Staff')

    def action_generate_pdf(self):
        # Search paid pharmacy bills in date range
        bills = self.env['doctor.lab.report'].search([
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status', '=', 'paid')
        ], order='date asc')

        if not bills:
            raise UserError('No paid pharmacy bills found in this date range.')

        # Pass the wizard record to the report
        return self.env.ref('homeo_doctor.lab_paid_pdf_report_action').report_action(self)


# 2. Create Report Model to Handle Data
class LabPaidReport(models.AbstractModel):
    _name = 'report.homeo_doctor.lab_paid_pdf_report'
    _description = 'Lab Paid Bills Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Get the wizard record
        wizard = self.env['lab.paid.wizard'].browse(docids)

        # Search paid pharmacy bills in date range
        domain = [
            ('date', '>=', wizard.from_date),
            ('date', '<=', wizard.to_date),
            ('status', '=', 'paid')
        ]
        if wizard.staff_id:
            domain.append(('staff_name', '=', wizard.staff_id.id))

        bills = self.env['doctor.lab.report'].search(domain, order='date asc')

        # Prepare data for template
        bill_data = []
        for idx, bill in enumerate(bills, start=1):
            bill_data.append({
                'sl_no': idx,
                'bill_number': bill.report_reference,
                'status': bill.status,
                'date': bill.date.strftime('%d-%m-%Y') if bill.date else '',
                'staff_name': bill.staff_name.name if bill.staff_name else '',
            })

        return {
            'doc_ids': docids,
            'doc_model': 'pharmacy.paid.wizard',
            'docs': wizard,
            'data': {
                'bills': bill_data,
                'from_date': wizard.from_date.strftime('%d-%m-%Y'),
                'to_date': wizard.to_date.strftime('%d-%m-%Y'),
            }
        }

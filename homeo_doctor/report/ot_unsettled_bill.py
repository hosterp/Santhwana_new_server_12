
from odoo import models, fields, api
from odoo.exceptions import UserError


class OTUnpaidWizard(models.TransientModel):
    _name = 'ot.unpaid.wizard'
    _description = 'OT Unpaid Bills Report Wizard'

    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)
    staff_id = fields.Many2one('hr.employee', string='Staff')

    def action_generate_pdf(self):
        # Search unpaid pharmacy bills in date range
        bills = self.env['ot.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', '=', 'unpaid')
        ], order='bill_date asc')

        if not bills:
            raise UserError('No unpaid general bills found in this date range.')

        # Pass the wizard record to the report
        return self.env.ref('homeo_doctor.ot_unpaid_pdf_report_action').report_action(self)


# 2. Create Report Model to Handle Data
class OTUnpaidReport(models.AbstractModel):
    _name = 'report.homeo_doctor.ot_unpaid_pdf_report'
    _description = 'X Ray Unpaid Bills Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Get the wizard record
        wizard = self.env['ot.unpaid.wizard'].browse(docids)

        # Search unpaid pharmacy bills in date range
        domain = [
            ('bill_date', '>=', wizard.from_date),
            ('bill_date', '<=', wizard.to_date),
            ('status', '=', 'unpaid')
        ]
        if wizard.staff_id:
            domain.append(('staff_name', '=', wizard.staff_id.id))

        bills = self.env['ot.billing'].search(domain, order='bill_date asc')

        # Prepare data for template
        bill_data = []
        for idx, bill in enumerate(bills, start=1):
            bill_data.append({
                'sl_no': idx,
                'bill_number': bill.bill_number,
                'name': bill.patient_name,
                'status': bill.status,
                'date': bill.bill_date.strftime('%d-%m-%Y') if bill.bill_date else '',
                'staff_name': bill.staff_name.name if bill.staff_name else '',
            })

        return {
            'doc_ids': docids,
            'doc_model': 'ot.unpaid.wizard',
            'docs': wizard,
            'data': {
                'bills': bill_data,
                'from_date': wizard.from_date.strftime('%d-%m-%Y'),
                'to_date': wizard.to_date.strftime('%d-%m-%Y'),
            }
        }

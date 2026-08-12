from odoo import models, fields, api
from odoo.exceptions import UserError


class PharmacyUnpaidWizard(models.TransientModel):
    _name = 'pharmacy.unpaid.wizard'
    _description = 'Pharmacy Unpaid Bills Report Wizard'

    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)
    staff_id = fields.Many2one('hr.employee', string='Staff')

    def action_generate_pdf(self):
        # Search unpaid pharmacy bills in date range
        bills = self.env['pharmacy.description'].search([
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status', '=', 'unpaid')
        ], order='date asc')

        if not bills:
            raise UserError('No unpaid pharmacy bills found in this date range.')

        # Pass the wizard record to the report
        return self.env.ref('homeo_doctor.pharmacy_unpaid_pdf_report_action').report_action(self)


# 2. Create Report Model to Handle Data
class PharmacyUnpaidReport(models.AbstractModel):
    _name = 'report.homeo_doctor.pharmacy_unpaid_pdf_report'
    _description = 'Pharmacy Unpaid Bills Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Get the wizard record
        wizard = self.env['pharmacy.unpaid.wizard'].browse(docids)

        # Search unpaid pharmacy bills in date range
        domain = [
            ('date', '>=', wizard.from_date),
            ('date', '<=', wizard.to_date),
            ('status', '=', 'unpaid')
        ]
        if wizard.staff_id:
            domain.append(('staff_name', '=', wizard.staff_id.id))

        bills = self.env['pharmacy.description'].search(domain, order='date asc')

        # Prepare data for template
        bill_data = []
        for idx, bill in enumerate(bills, start=1):
            bill_data.append({
                'sl_no': idx,
                'bill_number': bill.bill_number,
                'name': bill.name,
                'status': bill.status,
                'date': bill.date.strftime('%d-%m-%Y') if bill.date else '',
                'staff_name': bill.staff_name.name if bill.staff_name else '',
            })

        return {
            'doc_ids': docids,
            'doc_model': 'pharmacy.unpaid.wizard',
            'docs': wizard,
            'data': {
                'bills': bill_data,
                'from_date': wizard.from_date.strftime('%d-%m-%Y'),
                'to_date': wizard.to_date.strftime('%d-%m-%Y'),
            }
        }

class BillTypeWizard(models.TransientModel):
    _name = 'bill.type.wizard'
    _description = 'Bill Type Selector Wizard'

    bill_type = fields.Selection([
        ('pharmacy', 'Pharmacy Bills'),
        ('lab', 'Lab Bills'),
        ('general', 'General Bills'),
        ('casualty', 'Casualty Bills'),
        ('audiology', 'Audiology Bills'),
        ('xray', 'X-Ray Bills'),
        ('ot', 'OT Bills'),
    ], string="Select Bill Type", required=True)

    def action_open_report(self):
        """Redirect to correct wizard/action based on bill_type"""
        if self.bill_type == 'pharmacy':
            return self.env.ref('homeo_doctor.action_pharmacy_unpaid_wizard').read()[0]
        elif self.bill_type == 'lab':
            return self.env.ref('homeo_doctor.action_lab_unpaid_wizard').read()[0]
        elif self.bill_type == 'general':
            return self.env.ref('homeo_doctor.action_general_unpaid_wizard').read()[0]
        elif self.bill_type == 'casualty':
            return self.env.ref('homeo_doctor.action_casualty_unpaid_wizard').read()[0]
        elif self.bill_type == 'audiology':
            return self.env.ref('homeo_doctor.action_audiology_unpaid_wizard').read()[0]
        elif self.bill_type == 'xray':
            return self.env.ref('homeo_doctor.action_xray_unpaid_wizard').read()[0]
        elif self.bill_type == 'ot':
            return self.env.ref('homeo_doctor.action_ot_unpaid_wizard').read()[0]
        else:
            raise UserError("Unknown Bill Type")
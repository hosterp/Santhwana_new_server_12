from odoo import models, fields, api
from odoo.exceptions import UserError
class PharmacyBillGSTReport(models.TransientModel):
    _name = 'pharmacy.bill.gst.report'
    _description = 'Pharmacy Bill GST Report'

    from_date = fields.Date("From Date", required=True,default=fields.Date.today)
    to_date = fields.Date("To Date", required=True,default=fields.Date.today)
    op_category = fields.Selection([('op', 'OP'), ('admitted', 'IP'), ('others', 'OTHERS')])
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('credit', 'Credit')
    ], string='Payment Method')

    def print_report(self):
        return self.env.ref('homeo_doctor.action_report_bill_gst').report_action(self)

    def download_gst_excel(self):
        if not self.from_date or not self.to_date:
            raise UserError("Please provide both From and To dates.")

        # Build base URL
        url = '/report/generate/bill_gst_excel?from_date=%s&to_date=%s' % (
            self.from_date.isoformat(),
            self.to_date.isoformat()
        )

        # Append op_category if provided
        if self.op_category:
            url += '&op_category=%s' % self.op_category

        # Append payment_method if provided
        if self.payment_method:
            url += '&payment_method=%s' % self.payment_method

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }


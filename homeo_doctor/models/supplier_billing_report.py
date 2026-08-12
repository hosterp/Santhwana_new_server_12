from odoo import api, fields, models, _


class InInvoiceReportWizard(models.TransientModel):
    _name = 'in.invoice.report.wizard'
    _description = 'Vendor Bill Report Wizard'

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.today)
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method')

    def action_print_pdf(self):
        domain = [
            ('move_type', '=', 'in_invoice'),
            ('invoice_date', '>=', self.from_date),
            ('invoice_date', '<=', self.to_date),
        ]

        if self.mode_pay:
            domain.append(('pay_mode', '=', self.mode_pay))

        records = self.env['account.move'].search(domain)

        bills = []
        for rec in records:
            bills.append({
                'supplier_name': rec.supplier_name.name if rec.supplier_name else '',
                'supplier_invoice': rec.supplier_invoice or '',
                'supplier_phone': rec.supplier_phone or '',
                'supplier_email': rec.supplier_email or '',
                'supplier_gst': rec.supplier_gst or '',
                'supplier_dl': rec.supplier_dl or '',
                'bill_date': rec.supplier_bill_date.strftime('%d-%m-%Y') if rec.supplier_bill_date else '',
                'po_number': rec.po_number.name if rec.po_number else '',
            })
            # print(bills,'billsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbillsbills')
        data = {
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
            'bills': bills,
        }

        return self.env.ref('homeo_doctor.in_invoice_pdf_report_action').report_action(self, data={'data': data})

    def action_print_excel(self):
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/vendor/bill/excel'
                f'?from_date={self.from_date}'
                f'&to_date={self.to_date}'
                f'&mode_pay={self.mode_pay or ""}'
            ),
            'target': 'self',
        }

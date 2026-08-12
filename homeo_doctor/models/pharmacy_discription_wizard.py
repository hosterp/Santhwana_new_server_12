from odoo import models, fields


class PharmacyDescriptionWizard(models.TransientModel):
    _name = 'pharmacy.description.wizard'
    _description = 'Pharmacy Description Wizard'

    from_date = fields.Date(string="From Date", required=True,default=fields.Date.today)
    to_date = fields.Date(string="To Date", required=True,default=fields.Date.today)
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method')
    op_category = fields.Selection([('op', 'OP'), ('admitted', 'IP'), ('others', 'OTHERS')])
    def action_generate_report(self):
        domain = [
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status','!=','cancelled')
        ]
        if self.mode_pay:
            domain.append(('payment_mathod', '=', self.mode_pay))
        if self.op_category:
            domain.append(('op_category', '=', self.op_category))
        pharmacy_records = self.env['pharmacy.description'].search(domain, order='date asc')

        report_data = []
        sl_no = 1

        for rec in pharmacy_records:
            report_data.append({
                'sl_no': sl_no,
                'receipt_no': rec.bill_number,
                'date_time': rec.date.strftime('%Y-%m-%d %H:%M:%S') if rec.date else '',
                'name': rec.name,
                'payment_mathod': rec.payment_mathod,
                'uhid_id': rec.uhid_id.id,
                'payable_amount': rec.bill_amount,
                'paying_amount': rec.paid_amount,
                'balance_amount': rec.balance,
            })
            sl_no += 1

        data = {
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
            'report_data': report_data,
        }
        payable_total = sum(line['payable_amount'] for line in data['report_data'])
        paying_total = sum(line['paying_amount'] for line in data['report_data'])
        balance_total = sum(line['balance_amount'] for line in data['report_data'])

        data.update({
            'payable_total': payable_total,
            'paying_total': paying_total,
            'balance_total': balance_total,
        })

        return self.env.ref('homeo_doctor.action_report_pharmacy_description').report_action(self, data={'data': data})

    def action_generate_excel_report(self):
        base_url = '/pharmacy_description/download_excel'
        url = (
            f"{base_url}"
            f"?from_date={self.from_date.strftime('%Y-%m-%d')}"
            f"&to_date={self.to_date.strftime('%Y-%m-%d')}"
        )

        # Add filters ONLY if selected
        if self.mode_pay:
            url += f"&mode_pay={self.mode_pay}"

        if self.op_category:
            url += f"&op_category={self.op_category}"

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

from odoo import models, fields, api
from datetime import datetime

class CombinedReportWizard(models.TransientModel):
    _name = 'combined.report.wizard'
    _description = 'Combined Report Wizard'

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.today)
    mode_pay = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
        ('upi', 'UPI'),
        ('card', 'Card'),
    ], string='Payment Method')

    def action_generate_combined_pdf(self):
        payment_methods = [
            ('cash', 'Cash'),
            ('credit', 'Credit'),
            ('upi', 'UPI'),
            ('card', 'Card'),
        ]
        payment_codes = [m[0] for m in payment_methods]
        department_totals = {}

        # Pre-initialize in desired order from user screenshot
        desired_order = [
            'OP', 'Revisit', 'Advance Amount', 'Refund Amount',
            'Discharge Billing', 'Xray Billing', 'Audiology Billing', 
            'Casuality Billing', 'OT Billing', 'Lab Billing', 
            'Pharmacy Sales', 'General Billing', 'Pharmacy Return'
        ]
        for dname in desired_order:
            department_totals[dname] = {m[0]: 0.0 for m in payment_methods}

        def add_to_totals(dept, rec, amount_field, mode_field):
            total = getattr(rec, amount_field, 0.0) or 0.0
            if not total:
                return

            # Check for split payment (cash + upi + card mixed)
            is_split = getattr(rec, 'payment_method_split', False)
            if is_split:
                department_totals[dept]['cash'] += getattr(rec, 'cash_amount', 0.0) or 0.0
                department_totals[dept]['upi'] += getattr(rec, 'upi_amount', 0.0) or 0.0
                department_totals[dept]['card'] += getattr(rec, 'card_amount', 0.0) or 0.0
            else:
                # Trust the payment mode field directly.
                # For pharmacy: payment_mathod is already set to 'credit' for IP/VSSC patients
                # at bill creation time, so no override is needed here.
                mode = (getattr(rec, mode_field, 'cash') or 'cash').strip().lower()
                if mode not in payment_codes:
                    mode = 'cash'
                department_totals[dept][mode] += float(total)

        # Date range for search
        from_datetime = datetime.combine(self.from_date, datetime.min.time())
        to_datetime = datetime.combine(self.to_date, datetime.max.time())

        # 1. OP Registration
        for rec in self.env['patient.reg'].search([
            ('time', '>=', self.from_date),
            ('time', '<=', self.to_date),
            ('register_bool', '=', True),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('OP', rec, 'register_total_amount', 'register_mode_payment')

        # 2. Revisit / Appointment
        for rec in self.env['patient.appointment'].search([
            ('appointment_date', '>=', self.from_date),
            ('appointment_date', '<=', self.to_date),
            ('status', '=', 'confirmed'),
        ]):
            add_to_totals('Revisit', rec, 'register_total_amount', 'register_mode_payment')

        # # 3. IP Records
        # for rec in self.env['discharged.patient.record'].search([
        #     ('admitted_date', '>=', self.from_date),
        #     ('admitted_date', '<=', self.to_date),
        # ]):
        #     add_to_totals('Discharge Billing', rec, 'total_amount', 'pay_mode')

        # 4. Patient Wallet (Advance / Refund)
        for rec in self.env['patient.wallet'].search([
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            # Skip wallet deductions (usage in discharge bill)
            if not rec.refund and (not rec.amount_added or rec.amount_added <= 0):
                continue
            if rec.refund and rec.refund <= 0:
                continue

            dept = 'Advance Amount' if not rec.refund else 'Refund Amount'
            if not rec.refund and getattr(rec, 'payment_method_split', False):
                department_totals[dept]['cash'] += getattr(rec, 'cash_amount', 0.0)
                department_totals[dept]['upi'] += getattr(rec, 'upi_amount', 0.0)
                department_totals[dept]['card'] += getattr(rec, 'card_amount', 0.0)
            else:
                pay_method = (rec.payment_mode or 'cash').strip().lower()
                if pay_method not in payment_codes: pay_method = 'cash'
                amount = rec.amount_added if not rec.refund else -(rec.refund or 0.0)
                department_totals[dept][pay_method] += amount

        # 5. Discharge Billing
        for rec in self.env['discharge.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', 'in', ['paid', 'discharged']),
        ]):
            add_to_totals('Discharge Billing', rec, 'total_amount', 'mode_pay')

        # 6. Xray Billing
        for rec in self.env['xray.billing'].search([
            ('bill_date', '>=', from_datetime),
            ('bill_date', '<=', to_datetime),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('Xray Billing', rec, 'total_amount', 'mode_pay')

        # 7. Audiology Billing
        for rec in self.env['audiology.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('Audiology Billing', rec, 'total_amount', 'mode_pay')

        # 8. Casuality Billing
        for rec in self.env['casuality.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('Casuality Billing', rec, 'net_amount', 'mode_pay')

        # 9. OT Billing
        for rec in self.env['ot.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('OT Billing', rec, 'total_amount', 'mode_pay')

        # 10. Lab Billing
        for rec in self.env['doctor.lab.report'].search([
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status', 'not in', ['cancelled']),
        ]):
            add_to_totals('Lab Billing', rec, 'total_bill_amount', 'mode_of_payment')

        # 11. Pharmacy Sales (all categories: OP + IP admitted)
        # IP pharmacy bills have payment_mathod='credit' already set at creation.
        # They are separate records from discharge.billing totals.
        for rec in self.env['pharmacy.description'].search([
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('Pharmacy Sales', rec, 'total_amount', 'payment_mathod')

        # 12. General Billing
        for rec in self.env['general.billing'].search([
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', '!=', 'cancelled'),
        ]):
            add_to_totals('General Billing', rec, 'total_amount', 'mode_pay')

        # 13. Pharmacy Returns
        for rec in self.env['pharmacy.return'].search([
            ('return_date', '>=', self.from_date),
            ('return_date', '<=', self.to_date),
        ]):
            dept = 'Pharmacy Return'
            mode = (rec.original_sale_id.payment_mathod if rec.original_sale_id else 'cash') or 'cash'
            if mode not in payment_codes: mode = 'cash'
            department_totals[dept][mode] -= rec.total_return_amount or 0.0

        data = {
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
            'departments': department_totals,
            'payment_labels': [label for code, label in payment_methods],
            'payment_codes': [code for code, label in payment_methods],
        }

        return self.env.ref('homeo_doctor.combined_report_action').report_action(self, data={'data': data})

import logging

from odoo import models, fields, api


class PatientWallet(models.Model):
    _name = "patient.wallet"
    _description = "Patient Wallet"
    _rec_name = 'uhid'
    # _order = 'bill_number desc ,date desc'
    _order = "fiscal_year_end desc, bill_sequence desc ,id desc"

    patient_id = fields.Many2one("res.partner", string="Patient")
    uhid = fields.Many2one("patient.reg", string="UHID", required=True,
                           domain=[('status', 'in', ['proceed_admit', 'admitted', 'proceed_discharge'])])
    patient_name = fields.Char(string="Name", required=True)
    balance = fields.Float(string="Balance", store=True)
    line_ids = fields.One2many("patient.wallet.line", "wallet_id", string="Transactions")
    amount_in_inr = fields.Float(string='Amount in INR')
    payment_mode = fields.Selection([('cash', 'Cash'),
                                     ('credit', 'Credit'),
                                     ('card', 'Card'),
                                     ('upi', 'Mobile Pay'), ], string='Payment Method', default='cash')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")
    Staff_name = fields.Many2one('hr.employee', "Staff Name", default=lambda self: self._default_staff())
    amount_refund = fields.Float('Amount in INR')
    amount_added = fields.Float('Amount Added')
    refund = fields.Float('Amount Refund')
    bill_number = fields.Char(string="Bill Number", readonly=True, copy=False)
    date = fields.Date(string='Date',default=fields.Date.context_today)
    bill_sequence = fields.Integer(string="Bill Sequence", compute='_compute_bill_parts', store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute='_compute_bill_parts', store=True)
    status = fields.Selection([
        ('cancelled', 'Cancelled'),
    ], string="Status", tracking=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0

    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    def amount_to_text_indian(self):
        """Convert amount to words in Indian format (Rupees and Paise)."""
        try:
            from num2words import num2words
            if self.amount_added:
                amount_int = int(self.amount_added)
                decimal_part = int(round((self.amount_added - amount_int) * 100))

                rupees_text = num2words(amount_int, lang='en_IN').title()
                result = f" {rupees_text}"

                if decimal_part:
                    paise_text = num2words(decimal_part, lang='en_IN').title()
                    result += f" and {paise_text} Paise"

                return result + " Only"
        except Exception as e:
            # Optional: log the error for debugging
            _logger = logging.getLogger(__name__)
            _logger.warning("Failed to convert amount to Indian text: %s", e)

            # Fallback
            return self.currency_id.amount_to_text(self.amount_added)

        return ""

    def patient_advance_a5_new(self):
        return self.env.ref('homeo_doctor.report_patient_a5_wallet').report_action(self)

    def patient_advance_DMP_new(self):
        return self.env.ref('homeo_doctor.report_patient_wallet').report_action(self)

    @api.onchange('payment_method_split', 'cash_amount', 'upi_amount', 'card_amount')
    def _onchange_split_amounts(self):
        # When the payment is split across methods, the amount actually credited
        # must be the SUM of the split parts (cash + upi + card). Without this the
        # balance would only ever be credited with ``amount_in_inr``, silently
        # dropping the parts the user entered in the split fields (e.g. crediting
        # 5000 when 5000 cash + 1000 upi = 6000 was paid).
        if self.payment_method_split:
            self.amount_in_inr = (self.cash_amount or 0.0) + \
                                 (self.upi_amount or 0.0) + \
                                 (self.card_amount or 0.0)

    @api.onchange('uhid')
    def onchange_uhid(self):
        if self.uhid:
            self.patient_name = self.uhid.patient_id if self.uhid.patient_id else ''
            latest_wallet = self.env['patient.wallet'].search(
                [('uhid', '=', self.uhid.id)],
                order='id desc',
                limit=1
            )
            if latest_wallet:
                self.balance = latest_wallet.balance
                self.amount_refund = latest_wallet.balance
            else:
                self.balance = 0.0
                self.amount_refund = 0.0
        else:
            self.patient_name = ''
            self.balance = 0.0

    @api.model
    def create(self, vals):
        if not vals.get('bill_number'):
            # vals['bill_number'] = self.env['ir.sequence'].next_by_code('patient.wallet') or '/'

            today = fields.Date.context_today(self)
            raw_seq = self.env['ir.sequence'].with_context(ir_sequence_date=today).next_by_code('patient.wallet')
            if today.month >= 4:
                start_year, end_year = today.year, today.year + 1
            else:
                start_year, end_year = today.year - 1, today.year
            fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"
            vals['bill_number'] = f"{str(raw_seq).zfill(4)}/{fiscal_suffix}"

        if 'uhid' in vals:
            latest_wallet = self.env['patient.wallet'].search(
                [('uhid', '=', vals['uhid'])],
                order='id desc',
                limit=1
            )
            prev_balance = latest_wallet.balance if latest_wallet else 0.0
            # Add amount_in_inr to previous balance
            vals['balance'] = prev_balance
            # vals['amount_refund']= prev_balance

        return super(PatientWallet, self).create(vals)

    def action_add_amount(self):
        """Button to add amount_in_inr to current balance"""
        for rec in self:
            if rec.amount_in_inr:
                # Add amount_in_inr to balance
                rec.balance += rec.amount_in_inr
                # Store the amount added in a separate field (optional)
                rec.amount_added = (rec.amount_added or 0.0) + rec.amount_in_inr
                # Reset the input
                rec.amount_in_inr = 0.0

    def action_refund_amount(self):
        """Button to subtract amount_refund from balance"""
        for rec in self:
            if rec.amount_refund:
                # Subtract refund from balance
                rec.balance -= rec.amount_refund
                # Store the total refunded amount (optional)
                rec.refund = (rec.refund or 0.0) + rec.amount_refund
                # Reset the input
                rec.amount_refund = 0.0

    # @api.depends("line_ids.amount", "line_ids.type")
    # def _compute_balance(self):
    #     for wallet in self:
    #         balance = 0.0
    #         for line in wallet.line_ids:
    #             if line.type == "credit":
    #                 balance += line.amount
    #             elif line.type == "debit":
    #                 balance -= line.amount
    #         wallet.balance = balance
    #
    # def action_add_to_wallet(self):
    #     for rec in self:
    #         wallet = self.env["patient.wallet"].search(
    #             [("patient_id", "=", rec.patient_id.id)], limit=1
    #         )
    #         if not wallet:
    #             wallet = self.env["patient.wallet"].create(
    #                 {"patient_id": rec.patient_id.id, "uhid": rec.uhid.id}
    #             )
    #         self.env["patient.wallet.line"].create({
    #             "wallet_id": wallet.id,
    #             "amount": rec.advance_amount,
    #             "type": "credit",
    #             "description": "Advance payment for appointment %s" % rec.name,
    #         })
    #
    # def credit_wallet(self, amount, description="Advance Payment", move=None):
    #     for wallet in self:
    #         self.env['patient.wallet.line'].create({
    #             'wallet_id': wallet.id,
    #             'amount': amount,
    #             'type': 'credit',   # ✅ important
    #             'description': description,
    #         })
    #
    # def debit_wallet(self, amount, description="Used for Bill", move=None):
    #     for wallet in self:
    #         self.env['patient.wallet.line'].create({
    #             'wallet_id': wallet.id,
    #             'amount': amount,
    #             'type': 'debit',   # ✅ important
    #             'description': description,
    #         })

    def action_print_wallet(self):
        return self.env.ref('homeo_doctor.report_patient_wallet').report_action(self)


class PatientWalletLine(models.Model):
    _name = "patient.wallet.line"
    _description = "Patient Wallet Transaction"
    _order = 'date desc'

    wallet_id = fields.Many2one("patient.wallet", string="Wallet", ondelete="cascade")
    date = fields.Datetime(string="Date", default=fields.Datetime.now)
    amount = fields.Float(string="Amount", required=True)
    type = fields.Selection([
        ("credit", "Credit (Advance/Top-up)"),
        ("debit", "Debit (Used in Bill)"),
    ], string="Transaction Type", required=True)
    description = fields.Char(string="Description")
    pay_mode = fields.Selection([('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI')], string='Mode of Pay')

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec.wallet_id._compute_balance()
        return rec

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec.wallet_id._compute_balance()
        return res

    def unlink(self):
        wallets = self.mapped("wallet_id")
        res = super().unlink()
        for wallet in wallets:
            wallet._compute_balance()
        return res

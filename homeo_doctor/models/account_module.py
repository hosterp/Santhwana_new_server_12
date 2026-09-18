from datetime import date, timedelta

from odoo import models, fields,api,_
from odoo.exceptions import ValidationError

import math

from odoo.tools import float_round

import logging

_logger = logging.getLogger(__name__)
# from odoo.odoo.exceptions import ValidationError

class ProductProduct(models.Model):
    _inherit = 'product.product'

    stock_in_hand = fields.Float(string='Stock In Hand', compute='_compute_stock_in_hand')
    zero_stock_date = fields.Date(string='Zero Stock Date')

    def _compute_stock_in_hand(self):
        for product in self:
            stock_entries = self.env['stock.entry'].search([
                ('product_id', '=', product.id),
                ('quantity', '>', 0)
            ])
            product.stock_in_hand = sum(stock_entries.mapped('quantity'))


class AccountMove(models.Model):
    _inherit = 'account.move'

    # partner_id = fields.Many2one('res.partner', string='Customer', required=False)

    custom_reference = fields.Char(string="Custom Reference")
    doctor=fields.Many2one('doctor.profile',string='Doctor')
    uhid=fields.Many2one('patient.reg',string='UHID')
    patient_name=fields.Char(related='uhid.patient_id',string='Patient Name')
    address=fields.Text(related='uhid.address',string='Address')
    mobile=fields.Char(related='uhid.phone_number',string='Mobile No')
    invoice_line_ids=fields.One2many('account.move.line','move_id')
    supplier_name = fields.Many2one('res.partner',string='Supplier Name')
    supplier_invoice = fields.Char('Invoice No', required=True)
    supplier_phone = fields.Char('Phone No')
    supplier_email = fields.Char('Email Id')
    supplier_gst = fields.Char('GST No')
    supplier_dl = fields.Char('DL/REG No')
    supplier_bill_date = fields.Date(string='Bill Date', default=lambda self: date.today())
    po_number=fields.Many2one('purchase.order',string='PO Number', domain="[('state', '=', 'purchase')]",)
    with_po=fields.Boolean()
    without_po=fields.Boolean()
    invoice_date = fields.Date(
        string="Date",
        default=lambda self: date.today()
    )
    pay_mode = fields.Selection([
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('credit', 'Credit'),
    ], string='Payment Mode',default='cash')
    global_discount = fields.Float(string='Discount (%)', digits=(16, 2), default=0.0)
    amount_before_discount = fields.Monetary(string='Amount Before Discount',
                                             store=True, readonly=True, compute='_compute_amount')
    discount_amount = fields.Monetary(string='Discount Amount',
                                      store=True, readonly=True, compute='_compute_amount')
    cgst_amount = fields.Monetary(string="CGST Amount", compute="_compute_tax_split", store=True)
    sgst_amount = fields.Monetary(string="SGST Amount", compute="_compute_tax_split", store=True)
    amount_total_with_gst = fields.Monetary(
        string='Total (Incl. GST)',
        compute='_compute_tax_split',
        store=True,
        currency_field='currency_id'
    )
    is_verified = fields.Boolean(string='Verified', default=False, copy=False)
    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True, copy=False)
    verified_person_name = fields.Char(string='Verified Person Name', readonly=True, copy=False)
    verified_date = fields.Datetime(string='Verified Date', readonly=True, copy=False)

    def action_verify_invoice(self):
        self.ensure_one()
        return {
            'name': _('Verify Supplier Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'supplier.invoice.verify.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_user_id': self.env.user.id,
            }
        }

    def button_draft(self):
        res = super(AccountMove, self).button_draft()
        self.write({
            'is_verified': False,
            'verified_by': False,
            'verified_person_name': False,
            'verified_date': False
        })
        return res


    @api.depends('invoice_line_ids.gst', 'invoice_line_ids.price_subtotal')
    def _compute_tax_split(self):
        for move in self:
            cgst = 0.0
            sgst = 0.0
            currency = move.currency_id
            base_total = move.amount_before_discount

            for line in move.invoice_line_ids:
                if line.gst and line.price_subtotal:
                    gst_amt = (line.price_subtotal * line.gst) / 100.0
                    # print(gst_amt,'gst_amt....................................................')
                    half_gst = gst_amt / 2.0
                    cgst += half_gst
                    sgst += half_gst
                    # print(cgst,sgst,'gst...................................................')
            move.cgst_amount = float_round(cgst, precision_rounding=currency.rounding)
            move.sgst_amount = float_round(sgst, precision_rounding=currency.rounding)
            move.amount_total_with_gst = round(base_total + move.cgst_amount + move.sgst_amount)

            # print(move.cgst_amount, move.sgst_amount, '✅ CGST/SGST split')
            # print(move.amount_total_with_gst, '✅ Total Incl. GST')
    def _verify_no_duplicate_supplier_invoice(self):
        """Raise ValidationError if supplier_invoice is empty or already exists on any vendor bill."""
        for rec in self:
            if rec.move_type != 'in_invoice':
                continue
            if not rec.supplier_invoice or not str(rec.supplier_invoice).strip():
                raise ValidationError(_("Invoice No is required for Vendor Bills."))

            inv_no = str(rec.supplier_invoice).strip()
            domain = [
                ('id', '!=', rec.id),
                ('move_type', '=', 'in_invoice'),
                ('supplier_invoice', '=ilike', inv_no),
            ]

            duplicate = self.env['account.move'].sudo().search(domain, limit=1)
            if duplicate:
                dup_supplier = (duplicate.supplier_name.name if duplicate.supplier_name else False) or \
                               (duplicate.partner_id.name if duplicate.partner_id else False) or "N/A"
                raise ValidationError(
                    _("Invoice No '%s' already exists in Bill '%s' (Supplier: %s). "
                      "Duplicate invoice numbers are not allowed!")
                    % (inv_no, duplicate.name or duplicate.id, dup_supplier)
                )

    @api.constrains('supplier_invoice', 'supplier_name', 'partner_id', 'move_type')
    def _check_unique_supplier_invoice(self):
        self.filtered(lambda m: m.move_type == 'in_invoice')._verify_no_duplicate_supplier_invoice()

    @api.onchange('supplier_name')
    def _onchange_supplier_name(self):
        for rec in self:
            rec.supplier_gst = rec.supplier_name.gst_no
            rec.supplier_dl = rec.supplier_name.reg_no
            rec.supplier_phone = rec.supplier_name.mobile

    @api.depends('invoice_line_ids', 'global_discount', 'amount_untaxed')
    def _compute_amount(self):
        # First call the original method to calculate base amounts
        super(AccountMove, self)._compute_amount()

        for move in self:
            # Only apply to supplier invoices
            if move.move_type != 'in_invoice':
                amount_before_discount = sum(
                    move.invoice_line_ids.mapped('price_subtotal')
                )

                move.discount_amount = 0.0
                continue

            amount_before_discount = sum(
                move.invoice_line_ids.mapped('price_subtotal')
            )

            move.amount_before_discount = amount_before_discount

            # Calculate discount amount
            discount_amount = amount_before_discount * (move.global_discount / 100.0)
            move.discount_amount = discount_amount

            # Update total after discount
            move.amount_total = move.amount_total_with_gst
            # Update amount_residual to match the discounted total for unpaid/partially paid invoices
            if move.state == 'posted' and move.payment_state in ['not_paid', 'partial']:
                if move.payment_state == 'partial' and move.amount_residual != 0 and amount_before_discount != 0:
                    paid_ratio = 1 - (move.amount_residual / amount_before_discount)
                    move.amount_residual = (amount_before_discount - discount_amount) * (1 - paid_ratio)
                else:
                    move.amount_residual = amount_before_discount - discount_amount

                move.amount_residual_signed = -move.amount_residual if move.is_inbound() else move.amount_residual

    @api.onchange('po_number')
    def _onchange_po_number(self):
        """ Fetch purchase order lines and replace the existing invoice lines """
        if self.po_number:
            self.supplier_name = self.po_number.supplier_name.display_name
            self.invoice_line_ids = [(5, 0, 0)]

            invoice_lines = []
            for line in self.po_number.order_line:
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'quantity': line.qty_received,
                    'price_unit': line.price_unit,
                    'account_id': line.product_id.property_account_expense_id.id or line.product_id.categ_id.property_account_expense_categ_id.id,
                    'tax_ids': [(6, 0, line.taxes_id.ids)],
                    'product_uom_id': line.product_uom.id,
                }))

            self.invoice_line_ids = invoice_lines
        else:
            self.invoice_line_ids = [(5, 0, 0)]

    def _default_partner(self):
        return self.env['res.partner'].search([], limit=1)

    partner_id = fields.Many2one('res.partner', string="Customer", required=True, default=_default_partner)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = args[:]
        if name:
            domain += ['|', '|', ('name', operator, name), ('supplier_invoice', operator, name), ('supplier_name', operator, name)]
        records = self.search(domain, limit=limit)
        return records.name_get()

    @api.model
    def create(self, vals):
        if vals.get('move_type') == 'in_invoice':
            vals['name'] = False
            raw_seq = self.env['ir.sequence'].next_by_code('in.invoice') or '0'
            padded_seq = str(raw_seq).zfill(4)
            today = fields.Date.context_today(self)
            year_start = today.year % 100
            year_end = (today.year + 1) % 100
            fiscal_suffix = f"{year_start:02d}-{year_end:02d}"
            vals['name'] = f"{padded_seq}/{fiscal_suffix}"

        res = super(AccountMove, self).create(vals)
        if res.move_type == 'in_invoice':
            res._verify_no_duplicate_supplier_invoice()
        return res

    def action_post(self):
        for move in self:
            if move.move_type == 'in_invoice' and not move.is_verified:
                raise ValidationError(_("Supplier Invoice '%s' must be verified before confirmation.") % (move.name or move.supplier_invoice or move.id))

        res = super(AccountMove, self).action_post()


        for move in self:
            if move.move_type == 'in_invoice' and move.global_discount > 0:
                move.amount_residual = move.amount_total
                move.amount_residual_signed = -move.amount_residual if move.is_inbound() else move.amount_residual

            if move.move_type == 'in_invoice':
                for line in move.invoice_line_ids:
                    total_qty = line.quantity or 0
                    if line.free_qty:
                        total_qty += line.free_qty

                    data=self.env['stock.entry'].create({
                        'invoice_id': move.id,
                        'product_id': line.product_id.id,
                        'quantity': line.total_pack_qty,
                        'qty': line.total_pack_qty,
                        'hsn': line.hsn,
                        'company': line.manufacturing_company,
                        'manf_date': line.manufacturing_date,
                        'exp_date': line.expiry_date,
                        'batch': line.batch,
                        'uom_id': line.product_uom_id.id,
                        'rate': line.price_unit,
                        'date': move.invoice_date,
                        'pack': line.pack,
                        'pup': line.supplier_mrp/line.pack,
                        'supplier_name':move.supplier_name.name,
                        'supplier_mrp': line.supplier_mrp,
                        'gst':line.gst,
                        'category':line.category.id,
                        'state': 'confirmed',
                    })

                    stock_entries = self.env['stock.entry'].search([
                        ('product_id', '=', line.product_id.id),
                        ('state', '=', 'confirmed'),
                        ('quantity', '>', 0),
                    ])
                    line.stock_in_hand = sum(stock_entries.mapped('quantity'))
        return res

    def write(self, vals):
        result = super(AccountMove, self).write(vals)

        # Verify duplicate invoice on any write to vendor bills
        in_invoices = self.filtered(lambda m: m.move_type == 'in_invoice')
        if in_invoices:
            in_invoices._verify_no_duplicate_supplier_invoice()

        if 'global_discount' in vals and any(move.state == 'posted' for move in self):
            for move in self.filtered(lambda m: m.state == 'posted' and m.move_type == 'in_invoice'):
                discount_amount = move.amount_before_discount * (move.global_discount / 100.0)
                new_total = move.amount_before_discount - discount_amount

                if move.payment_state == 'not_paid':
                    move.amount_residual = new_total
                elif move.payment_state == 'partial':
                    paid_amount = move.amount_before_discount - move.amount_residual
                    if move.amount_before_discount != 0:
                        paid_ratio = paid_amount / move.amount_before_discount
                        move.amount_residual = new_total * (1 - paid_ratio)

                move.amount_residual_signed = -move.amount_residual if move.is_inbound() else move.amount_residual

        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'


    gst=fields.Integer(string='GST Rate(%)')
    hsn=fields.Char(string='HSN')
    move_id=fields.Many2one('account.move')
    category = fields.Many2one(
        'medicine.category',
        string="Category",
        store=True,
        ondelete="set null"
    )
    manufacturing_company = fields.Char(string='MFC',store=True)
    batch = fields.Char(string='Batch',store=True)
    manufacturing_date = fields.Date(string='M.Date',store=True)
    expiry_date = fields.Date(string='Exp.Date',store=True)
    move_type = fields.Selection(related='move_id.move_type', store=True)
    ord_qty = fields.Integer(string='Ord.QTY',store=True)
    to_be_received = fields.Integer(string='To Be Rec.',store=True)
    free_qty = fields.Integer(string='Free',store=True)
    rejected_qty = fields.Integer(string='Rejected',store=True)
    supplier_mrp = fields.Float(string='MRP',store=True)
    quantity = fields.Integer(string='Quantity',store=True)
    supplier_packing = fields.Many2one('supplier.packing', string='Packing')
    stock_in_hand=fields.Char(string='Stock In Hand', compute="_compute_stock_in_hand", store=True)
    product_uom_category_id = fields.Many2one('uom.category', string="Category")
    supplier_rack=fields.Many2one('supplier.rack')
    reason_for_rejection=fields.Char('Reason For Rejection')
    pack = fields.Integer('Pack',default=1)
    pup = fields.Float('PUP',compute="pup_calculation")
    price_subtotal = fields.Monetary(
        compute="_compute_price_subtotal",
        store=True,
        readonly=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='move_id.currency_id',
        store=True,
        readonly=True,
    )
    total_pack_qty = fields.Integer("Total Pack",compute="_total_pack")

    @api.depends('pack','quantity','free_qty')
    def _total_pack(self):
        for line in self:
            if line.free_qty > 0:
             line.total_pack_qty = line.pack * (line.quantity + line.free_qty)
            else:
                line.total_pack_qty = line.pack * line.quantity


    @api.depends('price_unit', 'quantity', 'discount', 'gst')
    def _compute_price_subtotal(self):
        for line in self:
            base = line.price_unit * (1 - (line.discount or 0.0) / 100.0) * line.quantity
            gst_amount = base * (line.gst or 0.0) / 100.0
            # line.price_subtotal = math.ceil(base + gst_amount)
            line.price_subtotal = base


    @api.depends('pack','supplier_mrp')
    def pup_calculation(self):
        for line in self:
            line.pup = line.supplier_mrp/line.pack

    @api.onchange('product_id')
    def _onchange_product_id_hsn(self):
        for line in self:
            if line.product_id and line.product_id.l10n_in_hsn_code:
                line.hsn = line.product_id.l10n_in_hsn_code

    @api.depends('product_id')
    def _compute_stock_in_hand(self):
        """Fetch the total available quantity from stock.entry for the selected product."""
        for record in self:
            if record.product_id:
                total_quantity = sum(self.env['stock.entry'].search([
                    ('product_id', '=', record.product_id.id)
                ]).mapped('quantity'))  # Summing up all quantities

                record.stock_in_hand = total_quantity
            else:
                record.stock_in_hand = 0.0

    @api.onchange('quantity')
    def _onchange_ord_qty_quantity(self):
        for line in self:
            if line.ord_qty is not None and line.quantity is not None:
                line.to_be_received = line.ord_qty - line.quantity

            if (line.ord_qty < line.quantity )and (line.ord_qty >0):
                line.free_qty = line.quantity - line.ord_qty
                line.quantity = line.ord_qty
            else:
                line.to_be_received = 0

    @api.onchange('ord_qty')
    def _onchange_ord_qty(self):
        for line in self:
            if line.ord_qty is not None and line.quantity is not None:
                line.to_be_received = line.ord_qty - line.quantity
            else:
                line.to_be_received = 0  # Reset if either field is empty

    @api.onchange('quantity')
    def _onchange_quantity(self):
        for line in self:
            if line.ord_qty is not None and line.quantity is not None:
                line.to_be_received = line.ord_qty - line.quantity
            else:
                line.to_be_received = 0  # Reset if either field is empty

    @api.onchange('quantity')
    def _onchange_quantity_update_stock(self):
        if self.product_id and self.move_type == 'out_invoice':
            stock_entries = self.env['stock.entry'].search([
                ('product_id', '=', self.product_id.id)
            ], order='id asc')

            qty_to_reduce = self.quantity

            for stock in stock_entries:
                if qty_to_reduce <= 0:
                    break

                if stock.quantity >= qty_to_reduce:
                    stock.quantity -= qty_to_reduce
                    qty_to_reduce = 0
                else:
                    qty_to_reduce -= stock.quantity
                    stock.quantity = 0

            if qty_to_reduce > 0:
                raise ValidationError(_("Not enough stock available for %s!") % self.product_id.name)


class SupplierRack(models.Model):
    _name='supplier.rack'
    _rec_name='rack'
    rack=fields.Char('Rack')

class UoMCategory(models.Model):
    _inherit = 'uom.category'
    _description = 'Product UoM Categories'
    _rec_name='name'

    name = fields.Char('Category', required=True, translate=True)


class MedicineCategory(models.Model):
    _name = 'medicine.category'
    _rec_name = 'medicine_category'

    medicine_category = fields.Char(string='Category', required=True)
    sequence = fields.Char(string='Category Code', readonly=True)

    @api.model
    def create(self, vals):
        vals['sequence'] = self.env['ir.sequence'].next_by_code('medicine.category') or '/'
        return super(MedicineCategory, self).create(vals)

class SupplierPacking(models.Model):
    _name='supplier.packing'
    _rec_name = 'supplier_packing'

    supplier_packing=fields.Char(string='Packing')


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    pay_mode = fields.Selection([('cash', 'Cash'), ('upi', 'UPI'), ('card', 'Card'), ('credit', 'Credit')],
                                default='cash', string='Payment Mode')
    move_id = fields.Many2one('account.move', string='Invoice')

    uhid = fields.Many2one(related='move_id.uhid', string='UHID', store=True, readonly=True)
    patient_name = fields.Char(related='move_id.patient_name', string='Patient Name', store=True, readonly=True)
    global_discount = fields.Float(related='move_id.global_discount', string='Discount (%)', readonly=True)
    amount_before_discount = fields.Monetary(related='move_id.amount_before_discount', string='Amount Before Discount',
                                             readonly=True)
    discount_amount = fields.Monetary(related='move_id.discount_amount', string='Discount Amount', readonly=True)


    @api.model
    def default_get(self, fields_list):
        res = super(AccountPaymentRegister, self).default_get(fields_list)
        active_ids = self._context.get('active_ids')

        if active_ids and len(active_ids) == 1:
            move = self.env['account.move'].browse(active_ids[0])
            res.update({
                'move_id': move.id,
                'uhid': move.uhid.id if move.uhid else False,
                'patient_name': move.patient_name,
            })

            # If there's a discount, explicitly set the amount
            if move.global_discount > 0:
                res['amount'] = move.amount_total
                # Also update payment_difference if it's in the fields
                if 'payment_difference' in fields_list:
                    res['payment_difference'] = 0.0
            else:
                res['amount'] = move.amount_total
                # Also update payment_difference if it's in the fields
                if 'payment_difference' in fields_list:
                    res['payment_difference'] = 0.0
        return res

    def write(self, vals):
        res = super(AccountPaymentRegister, self).write(vals)
        if 'pay_mode' in vals and self.move_id:
            self.move_id.write({'pay_mode': vals['pay_mode']})
        return res

    @api.model
    def create(self, vals):
        record = super(AccountPaymentRegister, self).create(vals)
        if 'pay_mode' in vals and record.move_id:
            record.move_id.write({'pay_mode': vals['pay_mode']})
        return record

    @api.onchange('source_amount', 'source_currency_id', 'company_id', 'currency_id', 'payment_date')
    def _onchange_amount(self):
        if hasattr(super(AccountPaymentRegister, self), '_onchange_amount'):
            super(AccountPaymentRegister, self)._onchange_amount()

        # After any amount calculation, apply discount if necessary
        if self.move_id and self.move_id.global_discount > 0:
            self.amount = self.move_id.amount_total

    @api.onchange('journal_id')
    def _onchange_journal(self):
        # After journal change, reapply discount if necessary
        if self.move_id and self.move_id.global_discount > 0:
            self.amount = self.move_id.amount_total

    # Override the _create_payment_vals_from_wizard method to use the correct amount
    def _create_payment_vals_from_wizard(self):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard()

        # Check if payment_vals is a dictionary (single payment)
        if isinstance(payment_vals, dict):
            # If we're paying an invoice with a discount, make sure we use the discounted amount
            if self.move_id and self.move_id.global_discount > 0:
                payment_vals['amount'] = self.move_id.amount_total

        # Check if payment_vals is a list of dictionaries (batch payments)
        elif isinstance(payment_vals, list) and all(isinstance(item, dict) for item in payment_vals):
            # If we're paying an invoice with a discount, make sure we use the discounted amount
            if self.move_id and self.move_id.global_discount > 0:
                for val in payment_vals:
                    if 'amount' in val:
                        val['amount'] = self.move_id.amount_total

        return payment_vals

    # This method is called when the form is initialized
    def _compute_payment_amount(self):
        for wizard in self:
            # Call the original method
            super(AccountPaymentRegister, wizard)._compute_payment_amount()

            # Then override the amount if there's a discount
            if wizard.move_id and wizard.move_id.global_discount > 0:
                wizard.amount = wizard.move_id.amount_total

class StockEntry(models.Model):
    _name = 'stock.entry'
    _description = 'Stock Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'product_id'

    name = fields.Char(string="Reference", required=True, copy=False, default=lambda self: _('New'))
    invoice_id = fields.Many2one('account.move', string="Invoice", domain=[('type', '=', 'in_invoice'), ('state', '=', 'posted')])
    product_id = fields.Many2one('product.product', string="Product", required=True)
    quantity = fields.Float(string="Stock In Hand", required=True)
    manf_date=fields.Date(string='M.Date')
    hsn=fields.Char(string='HSN')
    exp_date=fields.Date(string='Exp.date')
    rack=fields.Char(string='Rack Position')
    batch=fields.Char(string='Batch Number')
    company=fields.Char(string='Company')
    qty=fields.Integer(string='QTY')
    dispensed=fields.Integer('Dispensed',compute='_compute_dispensed')
    rate = fields.Float(string="Rate", required=True)
    supplier_mrp = fields.Float(string="MRP")
    uom_id = fields.Many2one('uom.uom', string="Unit of Measure")
    date=fields.Date(string='Date')
    pack = fields.Integer(string="Pack",default=1)
    pup = fields.Float(string="PUP",compute='_compute_pup')
    gst = fields.Integer(string="GST")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done')
    ], string="Status", default="draft", tracking=True)

    is_expired = fields.Boolean(string="Is Expired", compute="_compute_is_expired")
    category=fields.Many2one('medicine.category')
    expiry_status = fields.Selection([
        ('safe', 'Safe'),
        ('30', 'Expiring in 30 Days'),
        ('60', 'Expiring in 60 Days'),
        ('90', 'Expiring in 90 Days'),
        ('120', 'Expiring in 120 Days'),
        ('expired', 'Expired'),
    ], string="Expiry Status", compute="_compute_expiry_status", store=True)
    supplier_name=fields.Char(string="Supplier name")
    zero_stock_date = fields.Date(string='Zero Stock Date')
    @api.depends('exp_date', 'quantity')
    def _compute_expiry_status(self):
        today = date.today()
        for rec in self:
            if not rec.exp_date or rec.quantity <= 0:
                rec.expiry_status = 'safe'
                continue
            delta = (rec.exp_date - today).days
            if delta < 0:
                rec.expiry_status = 'expired'
            elif delta <= 30:
                rec.expiry_status = '30'
            elif delta <= 60:
                rec.expiry_status = '60'
            elif delta <= 90:
                rec.expiry_status = '90'
            elif delta <= 120:
                rec.expiry_status = '120'
            else:
                rec.expiry_status = 'safe'
    @api.depends('exp_date', 'quantity')
    def _compute_expiry_status(self):
        today = date.today()
        for rec in self:
            if not rec.exp_date or rec.quantity <= 0:
                rec.expiry_status = 'safe'
                continue
            delta = (rec.exp_date - today).days
            if delta < 0:
                rec.expiry_status = 'expired'
            elif delta <= 30:
                rec.expiry_status = '30'
            elif delta <= 60:
                rec.expiry_status = '60'
            elif delta <= 90:
                rec.expiry_status = '90'
            elif delta <= 120:
                rec.expiry_status = '120'
            else:
                rec.expiry_status = 'safe'
    @api.depends('exp_date')
    def _compute_is_expired(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_expired = rec.exp_date and rec.exp_date < today
    @api.depends('quantity')
    def _compute_dispensed(self):
        for record in self:
            record.dispensed=record.qty-record.quantity
    def name_get(self):
        result = []
        hide_details = self.env.context.get('hide_stock_details')
        for rec in self:
            prod_name = rec.product_id.display_name if rec.product_id else (rec.name or '')
            if hide_details:
                result.append((rec.id, prod_name))
                continue
            details = []
            if rec.batch:
                details.append(f"Batch: {rec.batch}")
            if rec.exp_date:
                details.append(f"Exp: {rec.exp_date.strftime('%m/%Y')}")
            if rec.supplier_mrp is not None:
                details.append(f"MRP: {rec.supplier_mrp:.2f}")
            if rec.quantity is not None:
                details.append(f"Stock: {int(rec.quantity)}")

            if details:
                name = f"{prod_name} [{', '.join(details)}]"
            else:
                name = prod_name
            result.append((rec.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = args[:]
        if name:
            domain += ['|', ('product_id.name', operator, name), ('batch', operator, name)]

        records = self.search(domain, limit=limit)
        return records.name_get()

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.entry') or 'New'
        res = super(StockEntry, self).create(vals)
        res._update_zero_stock_date()
        return res

    def write(self, vals):
        res = super(StockEntry, self).write(vals)
        if 'quantity' in vals:
            for rec in self:
                rec._update_zero_stock_date()
        return res

    def _update_zero_stock_date(self):
        for rec in self:
            # Update entry-level zero stock date
            if rec.quantity <= 0:
                if not rec.zero_stock_date:
                    rec.sudo().write({'zero_stock_date': fields.Date.today()})
            else:
                if rec.zero_stock_date:
                    rec.sudo().write({'zero_stock_date': False})

            if rec.product_id:
                # Use a fresh search to get accurate stock_in_hand after recent changes
                stock_entries = self.env['stock.entry'].search([
                    ('product_id', '=', rec.product_id.id),
                    ('quantity', '>', 0)
                ])
                total_stock = sum(stock_entries.mapped('quantity'))
                
                if total_stock <= 0:
                    if not rec.product_id.zero_stock_date:
                        rec.product_id.sudo().write({'zero_stock_date': fields.Date.today()})
                else:
                    if rec.product_id.zero_stock_date:
                        rec.product_id.sudo().write({'zero_stock_date': False})

    @api.model
    def send_expiry_notifications(self):
        today = date.today()
        Stock = self.env['stock.entry']

        count_30 = Stock.search_count(
            [('exp_date', '>=', today), ('exp_date', '<=', today + timedelta(days=30)), ('quantity', '>', 0)])
        count_60 = Stock.search_count(
            [('exp_date', '>', today + timedelta(days=30)), ('exp_date', '<=', today + timedelta(days=60)),
             ('quantity', '>', 0)])
        count_90 = Stock.search_count(
            [('exp_date', '>', today + timedelta(days=60)), ('exp_date', '<=', today + timedelta(days=90)),
             ('quantity', '>', 0)])
        count_120 = Stock.search_count(
            [('exp_date', '>', today + timedelta(days=90)), ('exp_date', '<=', today + timedelta(days=120)),
             ('quantity', '>', 0)])

        message = []
        if count_30:
            message.append(f"{count_30} medicines expiring in 30 days")
        if count_60:
            message.append(f"{count_60} medicines expiring in 60 days")
        if count_90:
            message.append(f"{count_90} medicines expiring in 90 days")
        if count_120:
            message.append(f"{count_120} medicines expiring in 120 days")

        if not message:
            return

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Expiry Warning"),
                'message': "<br/>".join(message),
                'type': 'warning',
                'sticky': True,
            }
        }

    @api.depends('rate', 'gst', 'supplier_mrp')
    def _compute_pup(self):
        """Apply 7% reduction only if GST = 12"""
        for rec in self:
            base_value = rec.supplier_mrp or rec.rate or 0.0

            if rec.gst == 12:
                # Apply 7% reduction
                rec.pup = base_value * 0.93
            else:
                # Keep original value
                rec.pup = rec.supplier_mrp/rec.pack


# def write(self, vals):
    #     """Ensure stock quantity doesn't go negative and delete if zero."""
    #     for record in self:
    #         new_qty = vals.get('quantity', record.quantity)
    #         if new_qty < 0:
    #             raise ValidationError(_("Stock quantity cannot be negative!"))
    #
    #     res = super(StockEntry, self).write(vals)
    #
    #     # Delete records where quantity = 0
    #     for record in self:
    #         if record.quantity == 0:
    #             record.unlink()
    #
    #     return res





class StockExpiryAlert(models.Model):
    _name = 'stock.expiry.alert'
    _description = 'Stock Expiry Alert'

    user_id = fields.Many2one('res.users', string='User')
    count_30 = fields.Integer(string='Expiring in 30 Days', compute='_compute_counts')
    count_60 = fields.Integer(string='Expiring in 60 Days', compute='_compute_counts')
    count_90 = fields.Integer(string='Expiring in 90 Days', compute='_compute_counts')
    count_120 = fields.Integer(string='Expiring in 120 Days', compute='_compute_counts')

    @api.depends()
    def _compute_counts(self):
        today = date.today()
        Stock = self.env['stock.entry']
        for rec in self:
            rec.count_30 = Stock.search_count([
                ('exp_date', '>=', today),
                ('exp_date', '<=', today + timedelta(days=30)),
                ('quantity', '>', 0),
            ])
            rec.count_60 = Stock.search_count([
                ('exp_date', '>', today + timedelta(days=30)),
                ('exp_date', '<=', today + timedelta(days=60)),
                ('quantity', '>', 0),
            ])
            rec.count_90 = Stock.search_count([
                ('exp_date', '>', today + timedelta(days=60)),
                ('exp_date', '<=', today + timedelta(days=90)),
                ('quantity', '>', 0),
            ])
            rec.count_120 = Stock.search_count([
                ('exp_date', '>', today + timedelta(days=90)),
                ('exp_date', '<=', today + timedelta(days=120)),
                ('quantity', '>', 0),
            ])

    def send_expiry_notifications(self):
        today = date.today()
        Stock = self.env['stock.entry']
        users = self.env['hr.employee'].search([])

        for user in users:
            count_30 = Stock.search_count(
                [('exp_date', '>=', today), ('exp_date', '<=', today + timedelta(days=30)), ('quantity', '>', 0)])
            count_60 = Stock.search_count(
                [('exp_date', '>', today + timedelta(days=30)), ('exp_date', '<=', today + timedelta(days=60)),
                 ('quantity', '>', 0)])
            count_90 = Stock.search_count(
                [('exp_date', '>', today + timedelta(days=60)), ('exp_date', '<=', today + timedelta(days=90)),
                 ('quantity', '>', 0)])
            count_120 = Stock.search_count(
                [('exp_date', '>', today + timedelta(days=90)), ('exp_date', '<=', today + timedelta(days=120)),
                 ('quantity', '>', 0)])

            message = []
            if count_30:
                message.append(f"{count_30} medicines expiring in 30 days")
            if count_60:
                message.append(f"{count_60} medicines expiring in 60 days")
            if count_90:
                message.append(f"{count_90} medicines expiring in 90 days")
            if count_120:
                message.append(f"{count_120} medicines expiring in 120 days")

            if message:
                self.env['mail.message'].create({
                    'message_type': 'notification',
                    'subtype_id': self.env.ref('mail.mt_note').id,
                    'res_id': user.id,
                    'res_model': 'res.users',
                    'body': "<br/>".join(message),
                })

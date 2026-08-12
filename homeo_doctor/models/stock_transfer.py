from datetime import date

from odoo import models, fields,api,_
from odoo.exceptions import ValidationError, UserError


class StockTransfer(models.Model):
    _name = 'stock.transfer'
    _description = 'Stock Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Reference", required=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Date', default=fields.Date.context_today)
    location_from = fields.Char(string='From Location')
    location_to = fields.Char(string='To Location')
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done')
    ], string="Status", default="draft", tracking=True)

    # One2many relationship with StockTransferLine
    line_ids = fields.One2many('stock.transfer.line', 'transfer_id', string='Transfer Lines')

    # Sequence generation
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.transfer') or _('New')
        return super(StockTransfer, self).create(vals)

    # State transition buttons
    def action_confirm(self):
        """Mark record as confirmed."""
        self.ensure_one()
        self.state = 'confirmed'

    def action_done(self):
        """Finalize transfer and update stock entries."""
        for record in self:
            for line in record.line_ids:
                if line.is_addition:
                    record._add_to_stock(line)
                else:
                    record._remove_from_stock(line)
            record.state = 'done'

        # -------------------------------------------------------------------------
        # STOCK OPERATIONS
        # -------------------------------------------------------------------------

    def _add_to_stock(self, line):
        """Add product to stock."""
        self.env['stock.entry'].create({
            'name': self.env['ir.sequence'].next_by_code('stock.entry') or _('New'),
            'product_id': line.products_id.product_id.id,
            'quantity': line.total,
            'qty': line.total,
            'rate': line.rate,
            'supplier_mrp': line.supplier_mrp,
            'pup': line.rate,
            'uom_id': line.uom_id.id,
            'date': self.date,
            'manf_date': line.manf_date,
            'exp_date': line.exp_date,
            'hsn': line.hsn,
            'rack': line.rack,
            'batch': line.batch,
            'pack': line.pack,
            'company': line.mfc,
            'gst': line.gst,
            'category': line.category.id,
            'state': 'confirmed',
        })

    def _remove_from_stock(self, line):
        """Remove product from stock."""
        StockEntry = self.env['stock.entry']
        stock_entries = StockEntry.search([
            ('product_id', '=', line.products_id.product_id.id),
            ('quantity', '>', 0),
        ],  order='exp_date asc')

        remaining_qty = line.quantity  # ✅ remove this much from stock

        total_available = sum(stock_entries.mapped('quantity'))  # ✅ sum all quantities
        # print(total_available,'total_availabletotal_availabletotal_available')
        if total_available < remaining_qty:
            raise UserError(
                _('Not enough stock available for %s. Short by %s units.') %
                (line.products_id.name, remaining_qty - total_available)
            )

        for entry in stock_entries:
            if remaining_qty <= 0:
                break

            if entry.quantity > remaining_qty:
                entry.write({'quantity': entry.quantity - remaining_qty})
                remaining_qty = 0
            else:
                remaining_qty -= entry.quantity
                entry.write({'quantity': 0, 'state': 'done'})


class StockTransferLine(models.Model):
    _name = 'stock.transfer.line'
    _description = 'Stock Transfer Line'

    transfer_id = fields.Many2one('stock.transfer', string='Transfer Reference')
    product_id = fields.Many2one('product.product', string="Product",ondelete='set null')
    products_id = fields.Many2one('stock.entry', string="Medicine", required=True)
    is_addition = fields.Boolean(string="Add to Stock", help="Check if adding to stock, uncheck if removing")
    quantity = fields.Float(string="Quantity", required=True)
    rate = fields.Float(string="Rate", required=True)
    supplier_mrp = fields.Float(string="MRP", required=True)
    uom_id = fields.Many2one('uom.uom', string="Unit of Measure")
    manf_date = fields.Date(string='M.Date')
    hsn = fields.Char(string='HSN')
    exp_date = fields.Date(string='Exp.date')
    rack = fields.Char(string='Rack Position')
    batch = fields.Char(string='Batch Number')
    pack = fields.Integer(string="Pack", default=1)
    category = fields.Many2one('medicine.category', string='Category')
    stock_in_hand = fields.Char(string='Stock In Hand', compute="_compute_stock_in_hand", store=True)
    gst = fields.Integer(string='GST Rate(%)')
    mrp = fields.Float(string="MRP")
    total = fields.Integer(string="Total Pack", compute="total_calculation")
    mfc = fields.Char(string='MFC')

    @api.onchange('products_id', 'category')
    def _onchange_products_id(self):
        return {
            'domain': {'products_id': [('quantity', '>', 0)]}
        }
    @api.depends('products_id')
    def _compute_stock_in_hand(self):
        """Fetch the total available quantity from stock.entry for the selected product."""
        for record in self:
            if record.products_id:
                total_quantity = sum(self.env['stock.entry'].search([
                    ('product_id', '=', record.products_id.product_id.id),
                ]).mapped('quantity'))  # Summing up all quantities

                record.stock_in_hand = total_quantity
                # record.per_ped = record.product_id.lst_price
                # record.supplier_rate = record.product_id.standard_price


            else:
                record.stock_in_hand = 0.0
    @api.onchange('products_id')
    def _onchange_product_id(self):
        for line in self:
            if line.products_id:
                stock_entry = self.env['stock.entry'].search([
                    ('product_id', '=', line.products_id.product_id.id),
                    ('quantity', '>', 0),
                    # ('state', '=', 'confirmed'),
                    # ('exp_date', '>', fields.Date.today()),
                ], order='exp_date asc', limit=1)

                if stock_entry:
                    line.batch = stock_entry.batch
                    line.manf_date = stock_entry.manf_date
                    line.exp_date = stock_entry.exp_date
                    line.rate = stock_entry.rate
                    line.supplier_mrp = stock_entry.supplier_mrp
                    line.hsn = stock_entry.hsn
                    line.mfc = stock_entry.company
                    line.gst = stock_entry.gst

    @api.onchange('category')
    def _onchange_category(self):
        if self.category:
            return {
                'domain': {
                    'products_id': [('category', '=', self.category.id)]
                }
            }
        else:
            return {
                'domain': {
                    'products_id': []
                }
            }

    @api.depends('pack', 'quantity')
    def total_calculation(self):
        for line in self:
            if line.pack and line.quantity:
                line.total = line.pack * line.quantity
            else:
                line.total = 0.0
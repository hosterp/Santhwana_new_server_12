from datetime import date

from odoo import models, fields, api

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    custom_note = fields.Char(string="Custom Note")
    supplier_id= fields.Many2one('account.move',string='Supplier No',domain="[('move_type', '=', 'in_invoice')]")
    supplier_name= fields.Many2one('res.partner',string='Supplier Name')
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        default=lambda self: self.env["res.partner"].search([], limit=1).id,
    )
    order_date=fields.Date(string="Order Date",default=lambda self: fields.Date.today())
    store_in_charge=fields.Many2one('store.incharge',string='Store in charge')
    approved_by=fields.Many2one('approved.store.person',string='Approved By')
    STATE_SELECTION = [
        ('draft', 'Draft'),
        ('requested', 'Requested'),
        ('sent', 'Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('approved', 'Approved'),  # Add the new state
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ]
    state = fields.Selection(STATE_SELECTION, string='Status', default='draft',store=True)
    intent_priority=fields.Char(string='Priority')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            seq = self.env['ir.sequence'].next_by_code('purchase.order.custom') or '0000'
            today = date.today()
            year_start = today.year % 100
            year_end = (today.year + 1) % 100
            fiscal_suffix = f"{year_start:02d}-{year_end:02d}"
            vals['name'] = f"{seq}/{fiscal_suffix}"
        return super(PurchaseOrderInherit, self).create(vals)

    def button_confirm(self):
        for order in self:
            order.state = 'purchase'
        return True

    def action_create_invoice(self):
        super(PurchaseOrderInherit, self).action_create_invoice()

        for order in self:
            if order.invoice_ids:
                invoice = order.invoice_ids[0]
                order.state = 'approved'
                # Update invoice fields
                invoice.write({
                    'supplier_name': order.supplier_name.id,
                    'po_number': order.id,
                })


                # if invoice.state == 'draft':
                #     invoice.action_post()

        return True
class ApprovedPerson(models.Model):
    _name='approved.store.person'
    _rec_name='approved_by'

    approved_by=fields.Char(string='Approved By')


class StoreInCharge(models.Model):
    _name='store.incharge'
    _rec_name='store_incharge'


    store_incharge= fields.Char(string='Store In Charge')


class PurchaseOrderLine(models.Model):
    _inherit='purchase.order.line'

    company=fields.Char(string='Company')
    current_stock=fields.Char(string='Current Stock',compute='_compute_stock_in_hand')

    @api.depends('product_id')
    def _compute_stock_in_hand(self):
        """Fetch the total available quantity from stock.entry for the selected product."""
        for record in self:
            if record.product_id:
                total_quantity = sum(self.env['stock.entry'].search([
                    ('product_id', '=', record.product_id.id)
                ]).mapped('quantity'))

                record.current_stock = total_quantity


            else:
                record.current_stock = 0.0

class SupplierCreation(models.Model):
    _name = 'supplier.name'
    _rec_name = 'supplier'

    supplier=fields.Char('Supplier')
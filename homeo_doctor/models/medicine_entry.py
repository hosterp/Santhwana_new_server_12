from odoo import api, fields, models, tools
import odoo.addons
from datetime import datetime, date

class MedicineEntry(models.Model):
    _name = 'medicine.entry'
    _description = 'Medicine Entry'

    name = fields.Many2one("res.partner", required=True, string="Supplier")
    date = fields.Date(string="Date", default=date.today())
    address = fields.Char(required=True, string="Address")
    phone_number = fields.Char(string="Phone No:", size=12)
    stock_id = fields.One2many("stock.entry.lines", 'stock_line_id', string="Stock Entry Lines")


class StockEntryLine(models.Model):
    _name = 'stock.entry.lines'
    _description = 'Stock Entry Line'

    stock_line_id = fields.Many2one("medicine.entry", string="Medicine Entry")
    product_id = fields.Many2one('product.product', string="Product")
    stock = fields.Integer("Number Of Product")



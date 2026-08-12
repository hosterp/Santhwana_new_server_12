from odoo import models, fields, api
from datetime import date

class ZeroStockReport(models.TransientModel):
    _name = 'zero.stock.report'
    _description = 'Zero Stock Report'


    name = fields.Char(string="Name", default="Zero Stock Report")
    date = fields.Date(string="Date", default=fields.Date.context_today)
    line_ids = fields.One2many('zero.stock.report.line', 'report_id', string="Zero Stock Lines")

    def action_generate_report(self):
        self.line_ids.unlink()

        # Find all stock.entry records where quantity <= 0 (zero or negative stock)
        # We include all records for active products that are not services
        zero_entries = self.env['stock.entry'].search([
            ('quantity', '<=', 0),
            ('product_id.type', '!=', 'service'),
        ])

        # To avoid performance issues, we use SQL to batch-retrieve the historical dates
        # 1. Map for Audit Logs (FAST SQL)
        query = """
            SELECT al.res_id, MAX(al.create_date)
            FROM auditlog_log al
            JOIN auditlog_log_line alline ON alline.log_id = al.id
            WHERE al.model_model = 'stock.entry'
              AND alline.field_name = 'quantity'
              AND (alline.new_value = '0.0' OR alline.new_value = '0' OR alline.new_value = '0.00' OR alline.new_value = '0.000')
            GROUP BY al.res_id
        """
        self.env.cr.execute(query)
        audit_res = self.env.cr.fetchall()
        audit_map = {r[0]: r[1].date() if r[1] else False for r in audit_res}

        # 2. Map for Stock Transfer Records (FAST SQL) - Good for older 2025 movements
        query_transfer = """
            SELECT stl.products_id, MAX(st.date)
            FROM stock_transfer_line stl
            JOIN stock_transfer st ON stl.transfer_id = st.id
            WHERE stl.products_id IS NOT NULL AND stl.is_addition = false
            GROUP BY stl.products_id
        """
        self.env.cr.execute(query_transfer)
        transfer_res = self.env.cr.fetchall()
        transfer_map = {r[0]: r[1] for r in transfer_res}

        vals = []
        for entry in zero_entries:
            # We ignore any previously saved zero_stock_date and re-calculate every time
            # to ensure the data is coming strictly and accurately from Audit or Transfers.
            zero_date = audit_map.get(entry.id) or transfer_map.get(entry.id)

            vals.append((0, 0, {
                'stock_entry_id': entry.id,
                'product_id': entry.product_id.id,
                'date': entry.date,
                'zero_stock_date': zero_date,
                'current_stock': entry.quantity,
                'batch': entry.batch or '',
                'category_id': entry.category.id if entry.category else False,
            }))

        self.write({'line_ids': vals})
        return True

    @api.model
    def action_open_zero_stock(self):
        wizard = self.create({})
        wizard.action_generate_report()

        return {
            'name': 'Zero Stock Report',
            'type': 'ir.actions.act_window',
            'res_model': 'zero.stock.report.line',
            'view_mode': 'tree',
            'domain': [('report_id', '=', wizard.id)],
            'context': self.env.context,
            'target': 'current',
        }

class ZeroStockReportLine(models.TransientModel):
    _name = 'zero.stock.report.line'
    _description = 'Zero Stock Report Line'
    _order = 'zero_stock_date asc'

    report_id = fields.Many2one('zero.stock.report', string="Report")
    stock_entry_id = fields.Many2one('stock.entry', string="Stock Entry")
    product_id = fields.Many2one('product.product', string="Medicine Name")
    date = fields.Date(string="Stock Entry Date")
    zero_stock_date = fields.Date(string="Zero Stock Date")
    current_stock = fields.Float(string="Current Stock")
    batch = fields.Char(string="Batch No")
    category_id = fields.Many2one('medicine.category', string="Category")

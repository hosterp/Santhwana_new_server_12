from odoo import models, fields, api
from datetime import date, timedelta, datetime


class MedicineReorderForm(models.TransientModel):
    _name = 'medicine.reorder.form'
    _description = 'Medicine Reorder Form (Past 6 Months)'

    name = fields.Char(default='Medicine Reorder Report')
    from_date = fields.Date(required=True, default=lambda self: date.today() - timedelta(days=180))
    to_date = fields.Date(required=True, default=lambda self: date.today())
    line_ids = fields.One2many('medicine.reorder.form.line', 'form_id', string="Medicine Usage")

    def compute_reorder_report(self):
        self.ensure_one()
        self.line_ids.unlink()  # clear old lines

        six_months_ago = self.from_date
        today = self.to_date

        six_months_ago = fields.Date.to_string(datetime.today() - timedelta(days=180))

        query = """
        SELECT 
            aml.product_id,
            pt.name AS product_name,
            COUNT(aml.id) AS usage_count
        FROM account_move_line aml
        JOIN product_product pp ON pp.id = aml.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        JOIN account_move am ON am.id = aml.move_id
        WHERE am.date >= %s
        GROUP BY aml.product_id, pt.name
        HAVING COUNT(aml.id) > 1
        ORDER BY usage_count DESC
        """

        self.env.cr.execute(query, [six_months_ago])  # <-- only one param for one %s
        result = self.env.cr.dictfetchall()

        # Create lines
        for r in result:
            self.env['medicine.reorder.form.line'].create({
                'form_id': self.id,
                'product_id': r['product_id'],
                'usage_count': r['usage_count'],
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'medicine.reorder.form',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def print_reorder_report(self):
        self.ensure_one()
        self.compute_reorder_report()
        return self.env.ref('homeo_doctor.action_report_medicine_reorder').report_action(self)


class MedicineReorderFormLine(models.TransientModel):
    _name = 'medicine.reorder.form.line'
    _description = 'Medicine Reorder Form Line'

    form_id = fields.Many2one('medicine.reorder.form', ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Medicine")
    usage_count = fields.Integer(string="Used in Last 6 Months")

from odoo import models, fields,api


class Intent(models.Model):
    _name = 'intent.record'
    _rec_name = 'doctor_name'

    date = fields.Date(default=fields.Date.context_today, readonly=True)
    doctor_name = fields.Many2one('doctor.profile','Doctor Name')
    medicine = fields.Many2many('product.product',string="Medicine")
    quantity = fields.Char('Required Quantity')
    urgent = fields.Boolean('Urgent')
    very_urgent = fields.Boolean('Very Urgent')
    normal = fields.Boolean('Normal')
    current_stock = fields.Text(string='Current Stock', store=False)
    stock_in_hand = fields.Float(string="Total Stock in Hand", compute="_compute_stock_in_hand", store=True)
    stock_in_hand_display = fields.Text(string="Stock Breakdown", compute="_compute_stock_in_hand", store=True)
    department=fields.Many2one('doctor.department',string='Department')
    priority=fields.Char(string='Priority')

    @api.model
    def create(self, vals):
        # Create the intent record
        record = super(Intent, self).create(vals)

        # Determine priority text based on boolean fields
        priority = ''
        if record.urgent:
            priority = 'Urgent'
        elif record.very_urgent:
            priority = 'Very Urgent'
        elif record.normal:
            priority = 'Normal'

        if record.medicine and record.quantity:
            order_lines = []


            qty_list = [float(q.strip()) for q in record.quantity.split(',')]

            # Check: number of quantities must match number of medicines
            if len(qty_list) != len(record.medicine):
                raise ValueError("Mismatch between number of medicines and quantities.")


            for med, qty in zip(record.medicine, qty_list):
                order_lines.append((0, 0, {
                    'product_id': med.id,
                    'name': med.name,
                    'product_qty': qty,
                    'date_planned': fields.Date.context_today(self),
                }))

            self.env['purchase.order'].create({
                'order_line': order_lines,
                'origin': f"Intent by {record.doctor_name.name}",
                'intent_priority': priority,
                'state': 'requested',
            })

        return record

    @api.depends('medicine')
    def _compute_stock_in_hand(self):
        for record in self:
            stock_lines = []
            total_quantity = 0.0

            if record.medicine:
                print("Selected Medicine IDs:", record.medicine.ids)


                entries = self.env['stock.entry'].search([
                    ('product_id', 'in', record.medicine.ids),
                ])
                print("Stock Entries Found:", entries)


                product_totals = {}

                for entry in entries:
                    product_id = entry.product_id.id
                    product_name = entry.product_id.name
                    qty = entry.quantity

                    if product_id in product_totals:
                        product_totals[product_id]['qty'] += qty
                    else:
                        product_totals[product_id] = {'name': product_name, 'qty': qty}


                for product_id, data in product_totals.items():
                    line = f"{data['name']}: {data['qty']}"
                    stock_lines.append(line)
                    total_quantity += data['qty']
                    print(line)

                record.stock_in_hand_display = "\n".join(stock_lines)
                record.stock_in_hand = total_quantity
            else:
                record.stock_in_hand_display = 0
                record.stock_in_hand = 0.0


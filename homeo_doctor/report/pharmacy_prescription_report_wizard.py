from odoo import models, fields, api

class PharmacyPrescriptionReportWizard(models.TransientModel):
    _name = 'pharmacy.prescription.report.wizard'
    _description = 'Pharmacy Prescription Report Wizard'

    date_from = fields.Date(string='Date From', required=True,default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True,default=fields.Date.today)
    medicine_id = fields.Many2one('product.product', string='Medicine')
    medicines_id = fields.Many2one('stock.entry', string='Medicine Batch')
    with_patient_name = fields.Boolean(string="Include Patient Name", default=False)

    def print_report_html(self):
        self.ensure_one()
        return self.env.ref('homeo_doctor.report_pharmacy_html_prescription').report_action(
            self.with_context(report_type='qweb-html'),
            config=False,
            data=None
        )

    def print_report(self):
        self.ensure_one()
        return self.env.ref('homeo_doctor.report_pharmacy_prescription').report_action(self)

    def _get_prescription_lines(self):
        domain = [
            ('pharmacy_id.date', '>=', self.date_from),
            ('pharmacy_id.date', '<=', self.date_to),
            ('pharmacy_id.status', 'not in', ['cancelled', 'returned']),
        ]
        if self.medicine_id:
            domain.extend(['|', ('product_id', '=', self.medicine_id.id), ('products_id.product_id', '=', self.medicine_id.id)])
        elif self.medicines_id:
            domain.append(('products_id.product_id', '=', self.medicines_id.product_id.id))
        return self.env['pharmacy.prescription.line'].search(domain)

    def _get_grouped_prescription_lines(self):
        lines = self._get_prescription_lines()
        grouped = {}
        for line in lines:
            prod = line.product_id or (line.products_id.product_id if line.products_id else False)
            med_name = prod.display_name if prod else 'Unknown Medicine'
            if med_name not in grouped:
                grouped[med_name] = {
                    'medicine_name': med_name,
                    'lines': [],
                    'total_qty': 0,
                }
            grouped[med_name]['lines'].append(line)
            grouped[med_name]['total_qty'] += (line.qty or 0)
            
        return [grouped[k] for k in sorted(grouped.keys())]




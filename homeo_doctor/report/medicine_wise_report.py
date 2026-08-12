from odoo import api, fields, models


class PharmacyPrescriptionReportWizard(models.TransientModel):
    _name = 'pharmacy.prescription.report.wizard'
    _description = 'Wizard: Prescription Report'

    from_date = fields.Date(string="From Date", required=True)
    to_date = fields.Date(string="To Date", required=True)
    medicine_id = fields.Many2one(
        'product.product',
        string="Medicine",
        help="Leave empty to include all medicines",
    )

    def action_print_report(self):
        pass
        # """
        # Called by the “Print PDF” button. It returns
        # an action that will render the QWeb report.
        # """
        # data = {
        #     'from_date': self.from_date,
        #     'to_date': self.to_date,
        #     'medicine_id': self.medicine_id.id or False,
        # }
        # return self.env.ref('your_module_name.report_pharmacy_prescription').report_action(
        #     self, data=data
        # )

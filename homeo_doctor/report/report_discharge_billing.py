from odoo import models

class ReportDischargeBilling(models.AbstractModel):
    _name = 'report.homeo_doctor.report_discharge_billing_pdf'
    _description = 'Discharge Billing Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        model_name = data.get('model_name')
        date_field = data.get('date_field')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        # Fetch records for discharge billing
        docs = self.env[model_name].search([
            (date_field, '>=', from_date),
            (date_field, '<=', to_date)
        ])

        return {
            'docs': docs,
            'data': data,
            'res_company': self.env.company,
        }

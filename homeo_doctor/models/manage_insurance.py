from odoo import models, fields


class ManageInsurance(models.Model):
    _name = 'manage.insurance'
    _description = 'Manage Insurance'
    _rec_name = 'company'

    company = fields.Char(string='Company', required=True)
    category = fields.Char(string='Category')
    percentage = fields.Float(string='Percentage')

    category_ids = fields.One2many(
        'manage.insurance.category',
        'company_id',
        string='Categories'
    )

    def action_open_subcategories(self):
        self.ensure_one()
        return {
            'name': 'Subcategories',
            'type': 'ir.actions.act_window',
            'res_model': 'manage.insurance.category',
            'view_mode': 'tree,form',
            'domain': [('company_id', '=', self.id)],
            'context': {
                'default_company_id': self.id,
            },
        }


class ManageInsuranceCategory(models.Model):
    _name = 'manage.insurance.category'
    _description = 'Insurance Subcategory'

    company_id = fields.Many2one(
        'manage.insurance',
        string='Company',
        ondelete='cascade'
    )
    code = fields.Char(string='Code')
    item = fields.Char(string='Item')
    amount = fields.Float(string='Amount')
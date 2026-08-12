from odoo import api, fields, models, _



class GeneralDeptCosting(models.Model):
    _name = 'general.dept.costing'
    _rec_name = 'particular_name'



    department = fields.Many2one('general.department',string='Department')
    code = fields.Char(string='Code')
    particular_name = fields.Char(string='Particular Name')
    amount=fields.Float(string='Amount')
    tax= fields.Many2one('dept.tax',string='Tax(%)')
    tax_type= fields.Selection([('inclusive','Inclusive'),('exclusive','Exclusive')],default='inclusive')


class DepartmentTax(models.Model):
    _name = 'dept.tax'
    _rec_name= 'tax'


    tax= fields.Integer(string='Tax')
from odoo import api, fields, models, _



class GeneralDepartment(models.Model):
    _name = 'general.department'
    _rec_name = 'department_name'



    department_name = fields.Char(string='Department Name')
    code = fields.Char(string='Code')
    dept_billing=fields.Selection([('yes','YES'),('no','NO')],string='Dept.Billing',default='yes')
    inventory= fields.Selection([('yes','YES'),('no','NO')],string='Inventory',default='yes')
    show_in_sale=fields.Selection([('yes','YES'),('no','NO')],string='Show in Sale',default='yes')
    show_in_all_in_one_report = fields.Selection([('yes','YES'),('no','NO')],string='Show in All in One report',default='no')
    separate_report = fields.Selection([('yes','YES'),('no','NO')],string='Separate Report',default='no')
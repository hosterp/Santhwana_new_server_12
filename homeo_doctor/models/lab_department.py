from odoo import api, fields, models, _



class LabDepartment(models.Model):
    _name = 'lab.department'
    _rec_name = 'department_name'
    _order = 'department_name asc'


    department_name=fields.Char(string='Department Name')
    order_no=fields.Integer(string='Order Number')


class LabInvestigation(models.Model):
    _name = 'lab.investigation'
    _rec_name = 'investigation_name'
    _order = 'lab_department asc'



    lab_department=fields.Many2one('lab.department',string='Lab Department')
    investigation_name= fields.Char(string = 'Investigation Name')
    bill_code = fields.Char(string = 'Bill Code')
    rate= fields.Float(string='Rate')
    related_test_ids = fields.Many2many("lab.resultant.confi", string="Related Test Names")
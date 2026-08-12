from odoo import api, fields, models, _

class HrDepartment(models.Model):
    _inherit = 'hr.department'


    custom_field = fields.Char(string="Custom Field")

    def custom_method(self):

        pass
from odoo import models, fields, api


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    staff_password_hash = fields.Char(string='Staff Password')


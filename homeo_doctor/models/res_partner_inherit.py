from odoo import models, fields

class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'


    gst_no = fields.Char(string="GST No")
    reg_no = fields.Char(string="DL/REG No")


from email.policy import default

from odoo import api, fields, models, _


class labResultantConfi(models.Model):
    _name = 'lab.resultant.confi'
    _description = 'Lab Resultant Configuration'
    _rec_name = 'test_name'
    _order = 'order ASC'

    test_name_bill_code = fields.Many2one('lab.investigation',string='Select Test Name/Bill Code')
    main_group = fields.Many2one('lab.main.group',String='Select Main Group')
    sub_group = fields.Many2one('lab.sub.group',string='Select Sub Group')
    test_name = fields.Char(string='Test Name')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'),('both','Both')], string="Gender")
    order = fields.Integer(string='Order')
    age_from = fields.Integer(string='Age From')
    age_to = fields.Integer(string='Age To')
    type = fields.Selection([('year','Year'),('month','Month'),('day','Day'),('hour','Hour')],string='Type')
    unit = fields.Char(string='Unit')
    referral_range = fields.Char(string='Referral Range')
    min_val = fields.Char("Min Val")
    max_val = fields.Char("Max Val")
    remarks = fields.Text("Remarks")


class labMainGroup(models.Model):
    _name = 'lab.main.group'
    _rec_name = 'main_group'

    main_group= fields.Char("Name")


class labSubGroup(models.Model):
    _name = 'lab.sub.group'
    _rec_name = 'name'

    name =fields.Char("Name")
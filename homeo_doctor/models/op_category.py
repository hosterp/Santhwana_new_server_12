from odoo import api, fields, models



class OpCategory(models.Model):
    _name = 'op.category'
    _rec_name = 'category_name'



    category_name = fields.Char(string='Category Name')
    code = fields.Char(string='Code')
    parent_category = fields.Char(string='Parent Category')
    ip_link=fields.Selection([('no','No'),('yes','YES')],string='Ip Link')
    have_reg_fee=fields.Selection([('yes','YES'),('no','No')],string='Have Registration Fee?')
    reg_fee=fields.Integer(string='Registration Fee')
    reg_validity=fields.Integer(string='Registration Validity')
    mode_of_pay = fields.Selection([('cash','Cash'),('credit','Credit'),('card','Card'),('free','Free'),('cheque','Cheque'),('upi','UPI')])
    have_consultation_fee=fields.Selection([('no','NO'),('yes','YES'),('takefromdoctor','Take From Doctor')],string='Have Consultation Fee?')
    consultation_fee=fields.Integer(string='Consultation Fee')
    consultation_validity=fields.Integer(string='Consultation Validity')
    revaluation_fee=fields.Integer(string='Revaluation Fee')
    revaluation_validity=fields.Integer(string='Revaluation Validity')
    have_credit_limit=fields.Selection([('no','NO'),('yes','YES')],string='Have Credit Limit')
    credit_limit_type=fields.Selection([('monthly','Monthly'),('yearly','Yearly')],string='Credit Limit Type')
    credit_amount=fields.Integer(string='Credit Limit Amount')
    have_discount_limit=fields.Selection([('no','NO'),('yes','YES')],string='Have Discount Limit')
    discount_limit_type=fields.Selection([('monthly','Monthly'),('yearly','Yearly')],string='Discount Limit Type')
    discount_limit_calculation_type=fields.Selection([('amount','Amount'),('percentage','Percentage')],string='Discount Limit Calculation Type')
    discount_limit_amount=fields.Integer(string='Discount Limit Amount')

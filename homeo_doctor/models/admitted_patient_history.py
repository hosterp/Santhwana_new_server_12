from odoo import api, fields, models, _

class DischargedPatientRecord(models.Model):
    _name = 'discharged.patient.record'
    _description = 'Discharged Patient Record'
    _order='admitted_date desc'

    patient_id = fields.Char(string='UHID')
    name = fields.Char(string='Patient Name')
    discharge_date = fields.Datetime(string='Discharge Date')
    admitted_date = fields.Datetime(string='Admitted Date')
    room_number = fields.Many2one('hospital.room', string='Room')
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    total_amount = fields.Float(string='Total Amount')
    room_category_new = fields.Many2one('hospital.room.type',string='Room Category')
    new_block = fields.Many2one('hospital.block',string='Floor')
    bed_id = fields.Many2one('hospital.bed',string='Bed')
    amount_in_advance = fields.Char(string='Advance Amount')
    bystander_name=fields.Char(string='Bystander Name')
    relation=fields.Char(string='Relation')
    email=fields.Char(string='Email ID')
    bystander_mobile=fields.Char(string='Bystander mobile')
    alternate_no=fields.Char(string='Alternate Number')
    pay_mode=fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
        ('card', 'Card'),
        ('cheque', 'Cheque'),
        ('upi', 'UPI')
    ], string='Payment Method')
    op_category=fields.Many2one('op.category',string='OP Category')


class AdmittedAdvanceAmount(models.Model):
    _name = 'advance.patient.record'
    _description = 'Advance Patient Record'
    _order = 'admitted_date desc'

    patient_id = fields.Char(string='UHID')
    name = fields.Char(string='Patient Name')
    discharge_date = fields.Datetime(string='Discharge Date')
    admitted_date = fields.Datetime(string='Admitted Date')
    room_number = fields.Many2one('hospital.room', string='Room')
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    total_amount = fields.Float(string='Total Amount')
    room_category_new = fields.Many2one('hospital.room.type', string='Room Category')
    new_block = fields.Many2one('hospital.block', string='Floor')
    bed_id = fields.Many2one('hospital.bed', string='Bed')
    amount_in_advance = fields.Integer(string='Advance Amount')
    bystander_name = fields.Char(string='Bystander Name')
    relation = fields.Char(string='Relation')
    email = fields.Char(string='Email ID')
    bystander_mobile = fields.Char(string='Bystander mobile')
    alternate_no = fields.Char(string='Alternate Number')
    pay_mode = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
        ('card', 'Card'),
        ('cheque', 'Cheque'),
        ('upi', 'UPI')
    ], string='Payment Method')
    op_category = fields.Many2one('op.category', string='OP Category')

from odoo import models, fields

class PatientInsurance(models.Model):
    _name = 'hospital.insurance'
    _description = 'Patient Insurance Information'

    patient_id = fields.Many2one('patient.reg', string='Patient', required=True)
    insurance_provider = fields.Char(string='Insurance Provider', required=True)
    policy_number = fields.Char(string='Policy Number', required=True)
    coverage_type = fields.Selection([
        ('basic', 'Basic Coverage'),
        ('premium', 'Premium Coverage'),
        ('comprehensive', 'Comprehensive Coverage')
    ], string='Coverage Type', required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)
    coverage_amount = fields.Float(string='Coverage Amount')
    remarks = fields.Text(string='Remarks')

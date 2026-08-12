from odoo import models, fields, api


class OTManagement(models.Model):
    _name = 'hospital.ot'
    _description = 'Operation Theatre Management'

    patient_id = fields.Many2one('patient.reg', string='Patient', required=True)
    operation_type = fields.Selection([
        ('minor', 'Minor Surgery'),
        ('major', 'Major Surgery')],
        string='Operation Type', required=True)
    doctor_name = fields.Many2one('doctor.profile',string='Doctor Name', required=True)
    operation_date = fields.Datetime(string='Operation Date & Time', required=True)
    status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')],
        string='Status', default='scheduled')
    remarks = fields.Text(string='Remarks')
    medical_record_ids = fields.One2many('hospital.admitted.patient', 'medical_records', string="Medical Records")

    @api.onchange('patient_id')
    def _onchange_patient_id(self):
        if self.patient_id:
            medical_records = self.env['hospital.admitted.patient'].search([('patient_id', '=', self.patient_id.id)])
            self.medical_record_ids = [(6, 0, medical_records.ids)]




class OTTest(models.Model):
    _name = 'ot.test'
    _description = 'OT Test'

    name = fields.Char(string='Test Name', required=True)
    test_code = fields.Char(string='Test Code')
    price = fields.Float(string='Rate')
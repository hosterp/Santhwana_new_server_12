from odoo import api, fields, models, _


class RegisterPaymentWizard(models.TransientModel):
    _name = 'register.payment.wizard'
    _description = 'Register Payment Wizard'

    patient_id = fields.Many2one('patient.reg', string='Patient', readonly=True)
    patient_name = fields.Char(string='Patient Name', readonly=True)
    register_id = fields.Many2one('patient.reg', string='Register', readonly=True)
    doctor_ids = fields.Many2many('doctor.profile', string='Doctors', readonly=True)
    consultation_fee_ids = fields.One2many('wizard.register.fee', 'wizard_id', string='Consultation Fees')
    total_fee = fields.Float(string='Total Fee', compute='_compute_total_fee')
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card')
    ], string='Payment Method', required=True, default='cash')
    payment_reference = fields.Char(string='Payment Reference')

    @api.depends('consultation_fee_ids.fee_amount')
    def _compute_total_fee(self):
        for record in self:
            record.total_fee = sum(line.fee_amount for line in record.consultation_fee_ids)

    def action_confirm_payment(self):
        self.ensure_one()
        register = self.appointment_id
        
        # Update register with payment information
        payment_vals = {
            'payment_method': self.payment_method,
            'payment_reference': self.payment_reference,
            'status': 'confirmed'
        }
        register.write(payment_vals)
        
        # Continue with the original confirmation process
        register.button_visible = False
        
        # Check if patient.registration model has payment_method field
        has_payment_fields = all(field in self.env['patient.reg']._fields 
                                for field in ['payment_method', 'payment_reference'])
        
        # Create registrations for each doctor
        for doctor in register.doctor_ids:
            # Start with base registration values that exist in all cases
            registration_vals = {
                'user_id': register.patient_id.reference_no,
                'patient_id': register.patient_id.id,
                'token_no': register.token_no,
                'address': register.patient_id.address,
                'age': register.patient_id.age,
                'phone_number': register.patient_id.phone_number,
                'doctor_id': doctor.display_name,
                'appointment_date': register.appointment_date,
                'status': 'confirmed'
            }
            
            # Add payment fields only if they exist in the model
            if has_payment_fields:
                registration_vals.update({
                    'payment_method': self.payment_method,
                    'payment_reference': self.payment_reference,
                })
            
            # Create patient registration
            patient_registration = self.env['patient.reg'].create(registration_vals)
            
        return {'type': 'ir.actions.act_window_close'}

class WizardRegisterFee(models.TransientModel):
    _name = 'wizard.register.fee'
    _description = 'Wizard Register Fee'

    wizard_id = fields.Many2one('register.payment.wizard', string='Wizard')
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    fee_amount = fields.Float(string='Fee Amount')
from odoo import api, fields, models, _


class AppointmentPaymentWizard(models.TransientModel):
    _name = 'appointment.payment.wizard'
    _description = 'Appointment Payment Wizard'

    patient_id = fields.Many2one('patient.reg', string='Patient', readonly=True)
    patient_name = fields.Char(string='Patient Name', readonly=True)
    appointment_id = fields.Many2one('patient.appointment', string='Appointment', readonly=True)
    doctor_ids = fields.Many2many('doctor.profile', string='Doctors', readonly=True)
    consultation_fee_ids = fields.One2many('wizard.appointment.fee', 'wizard_id', string='Consultation Fees')
    total_fee = fields.Float(string='Total Fee')
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card')
    ], string='Payment Method', required=True, default='cash')
    payment_reference = fields.Char(string='Payment Reference')

    # @api.depends('consultation_fee_ids.fee_amount')
    # def _compute_total_fee(self):
    #     for record in self:
    #         record.total_fee = sum(line.fee_amount for line in record.consultation_fee_ids)

    def action_confirm_payment(self):
        self.ensure_one()
        appointment = self.appointment_id

        # Update appointment with payment information
        payment_vals = {
            'payment_method': self.payment_method,
            'payment_reference': self.payment_reference,
            'status': 'confirmed'
        }
        appointment.write(payment_vals)

        # Continue with the original confirmation process
        appointment.button_visible = False

        # Check if patient.registration model has payment_method field
        has_payment_fields = all(field in self.env['patient.registration']._fields
                                 for field in ['payment_method', 'payment_reference'])

        # Parse token numbers - split by comma and remove spaces
        token_numbers = [token.strip() for token in appointment.token_no.split(',')]

        # Create registrations for each doctor
        for index, doctor in enumerate(appointment.doctor_ids):
            # Assign the correct token number based on index
            # If there are fewer token numbers than doctors, use the last token number
            token_no = token_numbers[min(index, len(token_numbers) - 1)] if token_numbers else appointment.token_no

            # Start with base registration values that exist in all cases
            registration_vals = {
                'user_id': appointment.patient_id.id,
                'patient_id': appointment.patient_id.id,
                'token_no': token_no,  # Assign individual token number
                'address': appointment.patient_id.address,
                'age': appointment.patient_id.age,
                'phone_number': appointment.patient_id.phone_number,
                'doctor': doctor.id,
                'appointment_date': appointment.appointment_date,
                'status': 'confirmed'
            }

            # Add payment fields only if they exist in the model
            if has_payment_fields:
                registration_vals.update({
                    'payment_method': self.payment_method,
                    'payment_reference': self.payment_reference,
                })

            # Create patient registration
            patient_registration = self.env['patient.registration'].create(registration_vals)

        return {'type': 'ir.actions.act_window_close'}

class WizardAppointmentFee(models.TransientModel):
    _name = 'wizard.appointment.fee'
    _description = 'Wizard Appointment Fee'

    wizard_id = fields.Many2one('appointment.payment.wizard', string='Wizard')
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    fee_amount = fields.Float(string='Fee Amount')
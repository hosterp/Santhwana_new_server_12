from email.policy import default
from odoo import api, fields, models


class DoctorProfile(models.Model):
    _name = 'doctor.profile'
    _description = 'Doctor Profile'
    _rec_name = 'name'

    # [existing fields remain unchanged]
    name = fields.Char(string='Doctor Name', required=True)
    specialization = fields.Char(string='Specialization')
    phone = fields.Char(string='Phone Number')
    email = fields.Char(string='Email')
    qualification = fields.Char(string='Qualification')
    joining_date = fields.Date(string='Joining Date', default=fields.Date.context_today)
    department_id = fields.Many2one('doctor.department', string='Department', required=True)
    doctor_id = fields.Char(string="Doctor ID", readonly=True, copy=False, default="New")
    user_id = fields.Many2one('res.users', string="Assigned User", ondelete='set null')
    experience_years = fields.Integer(string='Years of Experience')
    available_days = fields.Many2many('doctor.available.day', string='Available Days')
    available_hours = fields.Char(string='Available Hours')
    bio = fields.Text(string='Doctor Bio')
    consultation_fee_doctor = fields.Integer(string='Consultation Fee')
    consultation_fee_limit = fields.Integer(string='Consultation Fee Day Limit', default=7)
    is_doctor = fields.Boolean(default=False)
    token_no = fields.Char("Token No")
    age = fields.Integer("Age")

    # Remove these fields as we'll track tokens in a separate model
    # last_token_number = fields.Integer(string="Last Token Number", default=0)
    # last_token_date = fields.Date(string="Last Token Date")

    token_sequence_ids = fields.One2many('doctor.token.sequence', 'doctor_id', string='Token Sequences')
    list_one=fields.Boolean()
    list_two=fields.Boolean()
    # Method to get the next token number
    def get_next_token_number(self, appointment_date=None):
        self.ensure_one()
        today = appointment_date or fields.Date.context_today(self)

        # Find or create sequence record for this date
        TokenSequence = self.env['doctor.token.sequence']
        sequence = TokenSequence.search([
            ('doctor_id', '=', self.id),
            ('sequence_date', '=', today)
        ], limit=1)

        if not sequence:
            sequence = TokenSequence.create({
                'doctor_id': self.id,
                'sequence_date': today,
                'last_number': 0
            })

        # Increment the counter
        next_number = sequence.last_number + 1
        sequence.write({
            'last_number': next_number
        })

        # Format the token number as a 4-digit number (0001 format)
        token = f"{next_number:04d}"
        return token

    @api.model
    def create(self, vals):
        if vals.get('doctor_id', 'New') == 'New':
            user_id = vals.get('user_id')
            if user_id:
                vals['doctor_id'] = f"DOCTOR-{user_id}"
            else:
                vals['doctor_id'] = self.env['ir.sequence'].next_by_code('doctor.profile') or 'New'
        return super(DoctorProfile, self).create(vals)


# New model to track token sequences by date and doctor
class DoctorTokenSequence(models.Model):
    _name = 'doctor.token.sequence'
    _description = 'Doctor Token Sequence'
    _rec_name = 'sequence_date'

    doctor_id = fields.Many2one('doctor.profile', string='Doctor', required=True, ondelete='cascade')
    sequence_date = fields.Date(string='Date', required=True)
    last_number = fields.Integer(string='Last Number', default=0)

    _sql_constraints = [
        ('unique_doctor_date', 'UNIQUE(doctor_id, sequence_date)',
         'Token sequence must be unique per doctor and date!')
    ]


class DoctorAvailableDay(models.Model):
    _name = 'doctor.available.day'
    _rec_name = 'day'

    day = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday')
    ], string='Day', required=True)


class DoctorDepartment(models.Model):
    _name = 'doctor.department'
    _description = 'Doctor Department'
    _rec_name = 'department'
    department = fields.Char(string='Department Name', required=True)
    doctor_ids = fields.One2many('doctor.profile', 'department_id', string="Doctors")
    code=fields.Char(string='Code')
    validity=fields.Integer(string='Validity')
    def action_show_doctors(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Doctors',
            'res_model': 'doctor.profile',
            'view_mode': 'tree,form',
            'domain': [('department_id', '=', self.id)],
            'target': 'current',
        }
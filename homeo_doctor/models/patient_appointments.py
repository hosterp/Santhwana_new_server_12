from odoo import api, fields, models, _
import datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.test_convert.tests.test_env import record
import logging
from odoo.exceptions import ValidationError

class PatientAppointment(models.Model):
    _name = 'patient.appointment'
    _description = 'Patient Appointment'
    _rec_name = 'appointment_reference'
    _order = 'id desc'

    appointment_reference = fields.Char(string="Appointment No", readonly=True)
    token_no = fields.Char("Token No")
    patient_id = fields.Many2one('patient.reg', string='UHID', required=True)
    patient_name = fields.Char(related='patient_id.patient_id', string='Patient Name', required=True)
    appointment_date = fields.Date(string="Date", default=fields.Date.context_today)
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    department = fields.Many2one('doctor.department', string='Department')
    departments = fields.Many2many('doctor.department', string='Departments')
    reason = fields.Text(string="Reason for Appointment")
    status = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled')],
        default='draft', string="Status")
    notes = fields.Text(string="Appointment Notes")
    created_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    consultation_fee = fields.Integer(string='Consultation Fee', compute='_compute_consultation_fee')
    address = fields.Text(related='patient_id.address', string='Address')
    age = fields.Integer(related='patient_id.age', string='Age')
    phone_number = fields.Char(related='patient_id.phone_number', string='Phone Number')
    gender = fields.Selection(related='patient_id.gender', string='Gender')
    button_visible = fields.Boolean(default=True)
    doctor_ids = fields.Many2many('doctor.profile', string='Doctors')
    consultation_fee_ids = fields.One2many('appointment.fee', 'appointment_id', string='Consultation Fees')
    registration_fee = fields.Integer(
        string="Registration Fee",
        store=True
    )
    status = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled')],
        default='draft', string="Status")
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card')
    ], string='Payment Method')
    payment_reference = fields.Char(string='Payment Reference')

    register_total_amount = fields.Integer(string="Total Amount", compute="_compute_register_total")
    register_amount_paid = fields.Integer(string="Amount Paid")
    register_balance = fields.Integer(string="Balance")
    register_staff_name = fields.Many2one('hr.employee', "Staff Name",default=lambda self: self._default_staff(), required=True)
    register_staff_password = fields.Char("Password", required=True)
    register_mode_payment = fields.Selection([('cash', 'Cash'),
                                              ('card', 'Card'),
                                              ('cheque', 'Cheque'),
                                              ('credit', 'Credit'),
                                              ('upi', 'Mobile Pay'), ], string='Payment Method', default='cash')
    register_card_no = fields.Char(string="Card No")
    register_bank_name = fields.Char(string="Bank")
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")
    vssc_boolean = fields.Boolean(related='patient_id.vssc_boolean', string='VSSC')
    differance_appointment_days = fields.Integer("No of Days")
    fee_applied = fields.Boolean(string="Fee Applied", default=False, store=True)




    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id
    @api.onchange('patient_id')
    def payment_mode_changes(self):
        if self.vssc_boolean:
            self.register_mode_payment = 'credit'

    def patient_challan_new(self):
        return self.env.ref('homeo_doctor.action_report_patient_appointment').report_action(self)
    def patient_challan_new_normal(self):
        return self.env.ref('homeo_doctor.action_report_patient_appointment_a5_print').report_action(self)

    def amount_to_text_indian(self):
        """Convert amount to words in Indian format (Rupees and Paise)."""
        try:
            from num2words import num2words
            if self.register_total_amount:
                amount_int = int(self.register_total_amount)
                decimal_part = int(round((self.register_total_amount - amount_int) * 100))

                rupees_text = num2words(amount_int, lang='en_IN').title()
                result = f" {rupees_text}"

                if decimal_part:
                    paise_text = num2words(decimal_part, lang='en_IN').title()
                    result += f" and {paise_text} Paise"

                return result + " Only"
        except Exception as e:
            # Optional: log the error for debugging
            _logger = logging.getLogger(__name__)
            _logger.warning("Failed to convert amount to Indian text: %s", e)

            # Fallback
            return self.currency_id.amount_to_text(self.register_total_amount)

        return ""

    def cancel_appointment(self):

        for appointment in self:

            # Update this appointment's status

            appointment.write({

                'status': 'cancelled',

                'button_visible': False

            })

            # Find all patient.registration records created from this appointment

            # by matching patient_id and appointment_date

            related_registrations = self.env['patient.registration'].search([

                ('patient_id', '=', appointment.patient_id.id),

                ('appointment_date', '=', appointment.appointment_date),

                ('doctor', 'in', appointment.doctor_ids.ids),

                ('status', 'in', ['confirmed', 'completed'])

            ])

            if related_registrations:
                related_registrations.write({'status': 'cancelled'})

        return True

    @api.depends('registration_fee', 'consultation_fee')
    def _compute_register_total(self):
        for rec in self:
            reg_fee = rec.registration_fee if rec.registration_fee else 0
            rec.register_total_amount = reg_fee + (rec.consultation_fee or 0)

    @api.onchange('register_amount_paid')
    def _onchage_amount_paid(self):
        for rec in self:
            if (rec.register_amount_paid < rec.register_total_amount and rec.register_amount_paid > 0):
                rec.register_balance = rec.register_total_amount - rec.register_amount_paid
            elif (rec.register_amount_paid > rec.register_total_amount and rec.register_amount_paid > 0):
                rec.register_balance = rec.register_amount_paid - rec.register_total_amount
            else:
                rec.register_balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount', 'payment_method_split', 'register_total_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            if rec.payment_method_split:
                cash = rec.cash_amount or 0.0
                upi = rec.upi_amount or 0.0
                card = rec.card_amount or 0.0
                total = float(rec.register_total_amount or 0.0)

                rec.register_amount_paid = int(cash + upi + card)
                rec.register_balance = int(total - (cash + upi + card))

    appointment_id = fields.Many2one('patient.appointment', string='Appointment', readonly=True)

    payment_receipt_number = fields.Char(
        string="Receipt Number",
        readonly=True,
        copy=False,
        default='/',
    )

    def action_confirm_payment(self):
        if self.register_staff_name and self.register_staff_password:
            employee = self.register_staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.register_staff_password != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for appointment in self:
            if not appointment.payment_receipt_number or appointment.payment_receipt_number == '/':
                # Fetch next from sequence 'payment.receipt'
                today = fields.Date.context_today(self)
                # raw_seq = self.env['ir.sequence'].next_by_code('payment.receipt') or '0'
                raw_seq = self.env['ir.sequence'].with_context(
                    ir_sequence_date=today
                ).next_by_code('payment.receipt')
                # Zero-pad to 4 digits
                padded_seq = str(raw_seq).zfill(4)

                # Compute fiscal year suffix (e.g. if today is June 2025 → "25-26")
                # today = datetime.date.today()
                # year_start = today.year % 100
                # year_end = (today.year + 1) % 100
                # fiscal_suffix = f"{year_start:02d}-{year_end:02d}"

                #james
                # today = datetime.date.today()
                # today = fields.Date.context_today(self)

                if today.month >= 4:  # April–December
                    start_year = today.year
                    end_year = today.year + 1
                else:  # January–March
                    start_year = today.year - 1
                    end_year = today.year

                fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"

                appointment.payment_receipt_number = f"{padded_seq}/{fiscal_suffix}"

            # Update appointment with payment information
            appointment.write({
                'payment_method': appointment.payment_method,
                'payment_reference': appointment.payment_reference,
                'status': 'confirmed',
                'button_visible': False
            })

            # Check if patient.registration model has payment_method and payment_reference
            registration_model = self.env['patient.registration']
            has_payment_fields = all(field in registration_model._fields
                                     for field in ['payment_method', 'payment_reference'])

            # Parse token numbers
            token_numbers = [token.strip() for token in (appointment.token_no or '').split(',') if token.strip()]

            # Create registrations for each doctor
            for index, doctor in enumerate(appointment.doctor_ids):
                token_no = token_numbers[min(index, len(token_numbers) - 1)] if token_numbers else appointment.token_no

                registration_vals = {
                    'user_id': appointment.patient_id.id,
                    'patient_id': appointment.patient_id.id,
                    'token_no': token_no,
                    'address': appointment.patient_id.address,
                    'age': appointment.patient_id.age,
                    'phone_number': appointment.patient_id.phone_number,
                    'doctor': doctor.id,
                    'appointment_date': appointment.appointment_date,
                    'status': 'confirmed',
                }

                if has_payment_fields:
                    registration_vals.update({
                        'payment_method': appointment.payment_method,
                        'payment_reference': appointment.payment_reference,
                    })

                registration_model.create(registration_vals)
        return self.env.ref('homeo_doctor.action_report_patient_appointment').report_action(appointment)

        # return {'type': 'ir.actions.act_window_close'}

    @api.onchange('appointment_date', 'doctor_ids')
    def _compute_registration_fee(self):
        for record in self:
            record.registration_fee = 0
            patient = record.patient_id

            if not patient or not record.appointment_date:
                continue

            appointment_date = record.appointment_date
            if hasattr(appointment_date, 'date'):
                appointment_date = appointment_date.date()

            # 🔹 VSSC patients → always free
            if patient.vssc_boolean:
                if not patient.track_registration_date:
                    patient.track_registration_date = appointment_date
                continue

            # 1️⃣ Get last registration from patient.reg
            last_reg = self.env['patient.reg'].search([
                ('reference_no', '=', patient.reference_no)
            ], order='time desc', limit=1)
            last_reg_date = last_reg.time.date() if last_reg and hasattr(last_reg.time, 'date') else last_reg.time

            # 2️⃣ Get last appointment that had a registration fee
            last_fee_appointment = self.env['patient.appointment'].search([
                ('patient_id', '=', patient.id),
                ('registration_fee', '>', 0),

            ], order='appointment_date desc', limit=1)
            last_fee_date = last_fee_appointment.appointment_date.date() if last_fee_appointment and hasattr(
                last_fee_appointment.appointment_date, 'date') else last_fee_appointment.appointment_date

            # 3️⃣ Pick the latest of both
            valid_dates = [d for d in [last_reg_date, last_fee_date] if d]
            last_fee_base_date = max(valid_dates) if valid_dates else None

            if not last_fee_base_date:
                # No previous fee → apply now
                fee_rec = self.env['patient.registration.fee'].search([], limit=1)
                record.registration_fee = fee_rec.fee if fee_rec else 0
                patient.track_registration_date = appointment_date
                continue

            # 4️⃣ Compute next fee applicable date
            next_fee_applicable_date = last_fee_base_date + datetime.timedelta(days=30)
            day_diff = (appointment_date - last_fee_base_date).days



            # 5️⃣ Apply fee when due
            if appointment_date >= next_fee_applicable_date:
                fee_rec = self.env['patient.registration.fee'].search([], limit=1)
                record.registration_fee = fee_rec.fee if fee_rec else 0
                patient.track_registration_date = appointment_date
            else:
                record.registration_fee = 0

            # print(f"""
            #           🧾 Patient: {patient.reference_no}
            #           Last Fee Base Date: {last_fee_base_date}
            #           Appointment Date: {appointment_date}
            #           Day Difference: {day_diff}
            #           Next Fee Applicable Date: {next_fee_applicable_date}
            #           """)

    def action_cancel(self):
        for record in self:
            record.status = 'cancelled'

    @api.onchange('departments')
    def _onchange_departments(self):
        if self.departments:
            department_ids = self.departments.ids

            doctors = self.env['doctor.profile'].search([('department_id', 'in', department_ids)])

            return {
                'domain': {'doctor_ids': [('id', 'in', doctors.ids)]}
            }
        else:

            return {
                'domain': {'doctor_ids': []}
            }
    # new revist code added

    @api.depends('appointment_date', 'doctor_ids', 'patient_id')
    @api.onchange('appointment_date', 'doctor_ids', 'patient_id')
    def _compute_consultation_fee(self):
        for record in self:
            record.consultation_fee = 0
            record.differance_appointment_days = 0

            # Support both doctor_id and doctor_ids, prioritizing doctor_ids
            doctors = record.doctor_ids
            if not doctors and record.doctor_id:
                doctors = record.doctor_id

            if not doctors or not record.patient_id or not record.appointment_date:
                continue

            doctor = doctors[0]
            fee_value = doctor.consultation_fee_doctor or 0
            fee_limit = int(doctor.consultation_fee_limit or 7)
            is_vssc = record.patient_id.vssc_boolean

            # Normalize appointment date
            appt_date = record.appointment_date
            if hasattr(appt_date, 'date'):
                appt_date = appt_date.date()
            if isinstance(appt_date, str):
                appt_date = fields.Date.from_string(appt_date)

            # --- Get last registration ---
            # Use patient's ID directly if available
            patient_id_int = record.patient_id.id
            if isinstance(patient_id_int, models.NewId):
                patient_id_int = patient_id_int.origin or 0

            last_reg = self.env['patient.reg'].sudo().search(
                [('id', '=', patient_id_int)],
                limit=1
            )
            # If search by ID fails or it's not the one we want, fallback to reference_no
            if not last_reg or last_reg.reference_no != record.patient_id.reference_no:
                last_reg = self.env['patient.reg'].sudo().search(
                    [('reference_no', '=', record.patient_id.reference_no)],
                    order='time desc', limit=1
                )

            last_reg_date = None
            if last_reg and last_reg.time:
                last_reg_date = last_reg.time.date() if hasattr(last_reg.time, 'date') else last_reg.time
                if isinstance(last_reg_date, str):
                    last_reg_date = fields.Date.from_string(last_reg_date)

            # Extract doctor from registration
            last_reg_doctor_id = None
            last_reg_doctor_name = ""
            if last_reg:
                if hasattr(last_reg, 'doc_name') and hasattr(last_reg.doc_name, 'id'):
                    last_reg_doctor_id = last_reg.doc_name.id
                    last_reg_doctor_name = last_reg.doc_name.name
                elif hasattr(last_reg, 'doctor_id') and hasattr(last_reg.doctor_id, 'id'):
                    last_reg_doctor_id = last_reg.doctor_id.id
                    last_reg_doctor_name = last_reg.doctor_id.name
                else:
                    last_reg_doctor_name = str(last_reg.doc_name) if last_reg.doc_name else ""

            # --- Find last paid consultation for SAME doctor ---
            domain_same_doc = [
                ('patient_id', '=', patient_id_int),
                ('fee_applied', '=', True),
                ('appointment_date', '<=', record.appointment_date),
            ]

            # Exclude current record correctly (works for NewId too)
            real_id = record._origin.id if hasattr(record, '_origin') else record.id
            if real_id and isinstance(real_id, int):
                domain_same_doc.append(('id', '!=', real_id))

            # Filter by same doctor
            domain_same_doc.append(('doctor_ids', 'in', doctor.ids))

            last_same_doc_consult = self.env['patient.appointment'].sudo().search(domain_same_doc,
                                                                                  order='appointment_date desc',
                                                                                  limit=1)

            base_date = None
            base_source = ""

            if last_same_doc_consult:
                base_date = last_same_doc_consult.appointment_date
                if hasattr(base_date, 'date'):
                    base_date = base_date.date()
                if isinstance(base_date, str):
                    base_date = fields.Date.from_string(base_date)
                base_source = "same doctor consult"
            else:
                base_date = last_reg_date
                base_source = "registration"

            # --- Compute day difference ---
            day_diff = 9999  # Default large
            if base_date and appt_date:
                day_diff = (appt_date - base_date).days

            if day_diff < 0:
                day_diff = 0
            record.differance_appointment_days = day_diff if day_diff < 9999 else 0

            # --- FEE DECISION LOGIC ---
            apply_fee = False

            if not base_date:
                apply_fee = True
            elif last_same_doc_consult:
                # Based on same doctor history
                apply_fee = (day_diff > fee_limit)
            elif last_reg:
                # Based on initial registration
                curr_doc_name = doctor.name.strip().lower() if doctor.name else ""
                prev_doc_name = last_reg_doctor_name.strip().lower() if last_reg_doctor_name else ""

                # Check if it is the same doctor (by ID or name)
                is_same_doc = (last_reg_doctor_id == doctor.id)
                if not is_same_doc and curr_doc_name and prev_doc_name:
                    is_same_doc = (curr_doc_name == prev_doc_name)

                if not is_same_doc:
                    apply_fee = True  # Different doctor
                else:
                    apply_fee = (day_diff > fee_limit)
            else:
                apply_fee = True

            # --- Final Fee ---
            final_fee_amount = 400 if is_vssc else fee_value
            record.consultation_fee = final_fee_amount if apply_fee else 0
            record.fee_applied = bool(record.consultation_fee > 0)

            # # --- Debug log ---
            # if debug_mode:
            #     print(
            #         f"[CONSULT-FEE] Patient: {record.patient_id.reference_no}, "
            #         f"ApptDate: {appt_date}, "
            #         f"BaseDate: {base_date}, "
            #         f"BaseSource: {base_source}, "
            #         f"DaysDiff: {day_diff}, "
            #         f"FeeLimit: {fee_limit}, "
            #         f"ApplyFee: {apply_fee}, "
            #         f"Reason: {reason}, "
            #         f"FinalFee: {record.consultation_fee}"
            #     )

            # if debug_mode:
            #     print(f"""
            #     🧾 Patient: {record.patient_id.reference_no}
            #     Appointment Date: {appt_date}
            #     Last Reg Date: {last_reg_date}
            #     Last Paid Consult Date (past): {last_consult_date}
            #     Base Date Used: {base_date}
            #     Day Difference: {day_diff}
            #     Fee Limit: {fee_limit}
            #     Fee Applied (amount): {record.consultation_fee}
            #     Fee Applied (flag): {record.fee_applied}
            #     =============================
            #     """)

    # @api.depends('appointment_date', 'doctor_ids', 'patient_id')
    # def _compute_consultation_fee(self):
    #     debug_mode = True
    #
    #     for record in self:
    #         record.consultation_fee = 0
    #         record.differance_appointment_days = 0
    #
    #         if not record.doctor_ids or not record.patient_id or not record.appointment_date:
    #             continue
    #
    #         doctor = record.doctor_ids[0]
    #         fee_value = doctor.consultation_fee_doctor or 0
    #         fee_limit = int(doctor.consultation_fee_limit or 7)
    #         is_vssc = record.patient_id.vssc_boolean
    #
    #         # Normalize appointment date
    #         appt_date = record.appointment_date.date() if hasattr(record.appointment_date,
    #                                                               'date') else record.appointment_date
    #         current_doctor = doctor
    #
    #         # --- Get last registration ---
    #         last_reg = self.env['patient.reg'].search(
    #             [('reference_no', '=', record.patient_id.reference_no)],
    #             order='time desc', limit=1
    #         )
    #         last_reg_date = last_reg.time.date() if last_reg and hasattr(last_reg.time, 'date') else (
    #             last_reg.time if last_reg else None
    #         )
    #
    #         # Extract doctor from registration (Many2one or Char)
    #         last_doctor = None
    #         if last_reg:
    #             if hasattr(last_reg, 'doc_name') and hasattr(last_reg.doc_name, 'id'):
    #                 last_doctor = last_reg.doc_name
    #             elif hasattr(last_reg, 'doctor_id') and hasattr(last_reg.doctor_id, 'id'):
    #                 last_doctor = last_reg.doctor_id
    #             else:
    #                 last_doctor = last_reg.doc_name  # Char
    #
    #         # --- Find last paid consultation for SAME doctor ---
    #         domain_same_doc = [
    #             ('patient_id', '=', record.patient_id.id),
    #             ('fee_applied', '=', True),
    #             #james
    #             ('appointment_date', '<=', record.appointment_date),
    #         ]
    #         if record.id and isinstance(record.id, int):
    #             domain_same_doc.append(('id', '!=', record.id))
    #
    #         # Filter by same doctor id
    #         domain_same_doc.append(('doctor_ids', 'in', [current_doctor.id]))
    #         last_same_doc_consult = self.env['patient.appointment'].search(domain_same_doc,
    #                                                                        order='appointment_date desc', limit=1)
    #
    #         # --- If not found, fallback to ANY previous paid consult ---
    #         if last_same_doc_consult:
    #             base_date = last_same_doc_consult.appointment_date.date() if hasattr(
    #                 last_same_doc_consult.appointment_date, 'date') else last_same_doc_consult.appointment_date
    #             base_source = "same doctor consult"
    #         else:
    #             # fallback to last registration date
    #             base_date = last_reg_date
    #             base_source = "registration"
    #
    #         # --- Compute day difference ---
    #         day_diff = (appt_date - base_date).days if base_date else 0
    #         if day_diff < 0:
    #             day_diff = 0
    #         record.differance_appointment_days = day_diff
    #
    #         # --- FEE DECISION LOGIC ---
    #         apply_fee = False
    #         reason = ""
    #
    #         # Case 1: No base date
    #         if not base_date:
    #             apply_fee = True
    #             reason = "no base date"
    #
    #         # Case 2: Found last same-doctor consult
    #         elif last_same_doc_consult:
    #             if day_diff > fee_limit:
    #                 apply_fee = True
    #                 reason = "beyond limit (same doctor)"
    #             else:
    #                 apply_fee = False
    #                 reason = "within limit (same doctor)"
    #
    #         # Case 3: No same-doctor consult, fallback to registration
    #         elif last_reg:
    #             last_doc_name = ""
    #             curr_doc_name = current_doctor.name.strip().lower() if current_doctor.name else ""
    #             if last_doctor and hasattr(last_doctor, "name"):
    #                 last_doc_name = last_doctor.name.strip().lower()
    #             elif isinstance(last_doctor, str):
    #                 last_doc_name = last_doctor.strip().lower()
    #             same_doctor = (last_doc_name == curr_doc_name)
    #
    #             if not same_doctor:
    #                 apply_fee = True
    #                 reason = "different doctor (from registration)"
    #             elif day_diff > fee_limit:
    #                 apply_fee = True
    #                 reason = "beyond limit (from registration)"
    #             else:
    #                 apply_fee = False
    #                 reason = "within limit (from registration)"
    #
    #         # --- Apply fee ---
    #         final_fee = 400 if is_vssc else fee_value
    #         record.consultation_fee = final_fee if apply_fee else 0
    #
    #         # --- Persist fee_applied flag ---
    #         fee_flag = bool(record.consultation_fee and record.consultation_fee > 0)
    #         if record.id and isinstance(record.id, int):
    #             if record.fee_applied != fee_flag:
    #                 record.sudo().write({'fee_applied': fee_flag})
    #         else:
    #             record.fee_applied = fee_flag
    #
    #         # # --- Debug log ---
    #         # if debug_mode:
    #         #     print(
    #         #         f"[CONSULT-FEE] Patient: {record.patient_id.reference_no}, "
    #         #         f"ApptDate: {appt_date}, "
    #         #         f"BaseDate: {base_date}, "
    #         #         f"BaseSource: {base_source}, "
    #         #         f"DaysDiff: {day_diff}, "
    #         #         f"FeeLimit: {fee_limit}, "
    #         #         f"ApplyFee: {apply_fee}, "
    #         #         f"Reason: {reason}, "
    #         #         f"FinalFee: {record.consultation_fee}"
    #         #     )
    #
    #         # if debug_mode:
    #         #     print(f"""
    #         #     🧾 Patient: {record.patient_id.reference_no}
    #         #     Appointment Date: {appt_date}
    #         #     Last Reg Date: {last_reg_date}
    #         #     Last Paid Consult Date (past): {last_consult_date}
    #         #     Base Date Used: {base_date}
    #         #     Day Difference: {day_diff}
    #         #     Fee Limit: {fee_limit}
    #         #     Fee Applied (amount): {record.consultation_fee}
    #         #     Fee Applied (flag): {record.fee_applied}
    #         #     =============================
    #         #     """)
    #
    # @api.onchange('appointment_date','doctor_ids')
    # def _compute_consultation_fee(self):
    #     for record in self:
    #         record.consultation_fee = 0
    #         record.differance_appointment_days = 0
    #
    #         # if record.spl_boolean:
    #         #     record.consultation_fee = 0
    #         #     continue
    #         # if record.staff_boolean:
    #         #     record.consultation_fee = 150
    #         #     continue
    #
    #         for doctor in record.doctor_ids:
    #             if not (record.patient_id and doctor and record.appointment_date):
    #                 continue
    #
    #             # Check if VSSC is enabled
    #             is_vssc = record.patient_id.vssc_boolean
    #             consultation_fee_limit = doctor.consultation_fee_limit or 7
    #             consultation_fee = 400 if is_vssc else (doctor.consultation_fee_doctor or 0)
    #
    #             # Fetch all past appointments (including current one in order)
    #             all_appts = self.env['patient.appointment'].search([
    #                 ('patient_id', '=', record.patient_id.id),
    #                 ('doctor_ids', '=', doctor.id),
    #             ], order='appointment_date asc')
    #
    #             last_fee_date = None
    #             fee_to_apply = 0
    #             delta_days = 0
    #
    #             for appt in all_appts:
    #                 if not last_fee_date:
    #                     # First ever appointment → apply fee
    #                     fee_to_apply = consultation_fee
    #                     last_fee_date = appt.appointment_date
    #                     if appt.id == record.id:
    #                         record.consultation_fee = fee_to_apply
    #                         record.differance_appointment_days = 0
    #                         # print(f"[{appt.appointment_date}] First visit → Fee {fee_to_apply}")
    #                 else:
    #                     delta_days = (appt.appointment_date - last_fee_date).days
    #
    #                     if delta_days > consultation_fee_limit:
    #                         # Reset cycle → charge again
    #                         fee_to_apply = consultation_fee
    #                         last_fee_date = appt.appointment_date
    #                         if appt.id == record.id:
    #                             record.consultation_fee = fee_to_apply
    #                             record.differance_appointment_days = delta_days
    #                             # print(
    #                             #     f"[{appt.appointment_date}] Beyond limit ({consultation_fee_limit}) → Fee {fee_to_apply}, reset baseline")
    #                     else:
    #                         # Within limit → no fee
    #                         fee_to_apply = 0
    #                         if appt.id == record.id:
    #                             record.consultation_fee = fee_to_apply
    #                             record.differance_appointment_days = delta_days
    # @api.depends('doctor_ids', 'appointment_date', 'patient_id')
    # def _compute_consultation_fee(self):
    #     for record in self:
    #
    #         record.consultation_fee = 0.0
    #
    #
    #         if record.patient_id and record.appointment_date:
    #             appointment_date = record.appointment_date.date()
    #
    #
    #             if record.doctor_id:
    #             #     doctors_to_process = [record.doctor_id]
    #             # else:
    #                 doctors_to_process = record.doctor_ids
    #
    #             total_fee = 0.0
    #
    #
    #             print(f"Doctors to process: {doctors_to_process}")
    #
    #
    #             for doctor in doctors_to_process:
    #                 print(f"Processing doctor: {doctor.name}")
    #
    #
    #                 consultation_fee_limit = doctor.consultation_fee_limit or 0
    #                 consultation_fee = doctor.consultation_fee_doctor or 0
    #
    #
    #                 last_appointment = self.env['patient.appointment'].search([
    #                     ('patient_id', '=', record.patient_id.id),
    #                     ('doctor_id', '=', doctor.id),
    #                     ('id', '!=', record.id) if record.id else ('id', '!=', False),
    #                 ], order='appointment_date desc', limit=1)
    #
    #                 last_appointment_day = (
    #                     (appointment_date - last_appointment.appointment_date.date()).days
    #                     if last_appointment else float('inf')
    #                 )
    #
    #
    #                 last_registration = self.env['patient.reg'].search([
    #                     ('patient_id', '=', record.patient_id.patient_id),
    #                     ('doc_name', '=', doctor.id),
    #                 ], order='formatted_date desc', limit=1)
    #
    #                 last_registration_day = (
    #                     (appointment_date - last_registration.date).days
    #                     if last_registration else float('inf')
    #                 )
    #
    #
    #                 delta_days = min(last_appointment_day, last_registration_day)
    #
    #
    #                 fee = 0.0 if delta_days <= consultation_fee_limit else consultation_fee
    #
    #
    #                 total_fee += fee
    #
    #
    #                 self.env['appointment.fee'].create({
    #                     'appointment_id': record.id,
    #                     'doctor_id': doctor.id,
    #                     'consultation_fee': fee,
    #                 })
    #
    #
    #             print(f"Total consultation fee for this appointment: {total_fee}")
    #
    #
    #             record.consultation_fee = total_fee
    #             print( record.consultation_fee,' record.consultation_fee...............................')

    def action_appointment_confirm(self):
        self.ensure_one()

        # Only set status and button_visible, don't create registrations yet
        self.status = 'confirmed'
        self.button_visible = False

        # Create wizard
        wizard_vals = {
            'patient_id': self.patient_id.id,
            'patient_name': self.patient_name,
            'appointment_id': self.id,
            'total_fee': self.consultation_fee,
            'doctor_ids': [(6, 0, self.doctor_ids.ids)],
        }

        wizard = self.env['appointment.payment.wizard'].create(wizard_vals)

        # Create fee lines
        for doctor in self.doctor_ids:
            # Get consultation fee for this doctor
            doc_fee = 0
            for fee in self.consultation_fee_ids:
                if fee.doctor_id.id == doctor.id:
                    doc_fee = fee.consultation_fee
                    break

            # If no fee found in consultation_fee_ids, calculate it
            if doc_fee == 0 and hasattr(doctor, 'consultation_fee_doctor'):
                doc_fee = doctor.consultation_fee_doctor

            # Create fee line
            self.env['wizard.appointment.fee'].create({
                'wizard_id': wizard.id,
                'doctor_id': doctor.id,
                'fee_amount': doc_fee
            })

        return {
            'name': 'Appointment Payment',
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.payment.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id}
        }
        # return {
        #     'type': 'ir.actions.act_window',
        #     'name': 'Patient Registration',
        #     'res_model': 'patient.registration',
        #     'view_mode': 'form',
        #     'res_id': patient_registration.id,
        #     'target': 'new',
        # }

    @api.model
    def create(self, vals):
        # Automatically compute the consultation fee before saving
        if 'doctor_ids' in vals and 'patient_id' in vals and 'appointment_date' in vals:
            doctor = self.env['doctor.profile'].browse(vals['doctor_id'])
            consultation_fee_limit = doctor.consultation_fee_limit or 0
            consultation_fee = doctor.consultation_fee_doctor or 0

            # Search for the last appointment for the same patient and doctor
            last_appointment = self.search(
                [
                    ('patient_id', '=', vals['patient_id']),
                    ('doctor_ids', '=', vals['doctor_id']),
                ],
                order='appointment_date desc',
                limit=1
            )

            if last_appointment:
                # Calculate the difference in days
                delta_days = (
                        fields.Date.from_string(vals['appointment_date']) - last_appointment.appointment_date).days
                if delta_days <= consultation_fee_limit:
                    vals['consultation_fee'] = 0.0
                else:
                    vals['consultation_fee'] = consultation_fee
            else:
                # No previous appointment found; apply the default consultation fee
                vals['consultation_fee'] = consultation_fee

        return super(PatientAppointment, self).create(vals)

    @api.onchange('department')
    def _onchange_department_id(self):
        if self.department:
            return {
                'domain': {
                    'doctor_ids': [('department_id', '=', self.department.id)],
                }
            }
        return {
            'domain': {
                'doctor_ids': []
            }
        }
    def password_validation(self):
        if self.register_staff_name and self.register_staff_password:
            employee = self.register_staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.register_staff_password != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")


    @api.model
    def create(self, vals):
        if vals.get('appointment_reference', 'New') == 'New':
            appointment_ref = self.env['ir.sequence'].next_by_code('patient.appointment.sequence')
            vals['appointment_reference'] = appointment_ref or 'New'

        # For multiple doctors, generate token for each doctor
        if vals.get('doctor_ids') and isinstance(vals['doctor_ids'], list):
            token_numbers = []
            appointment_date = fields.Date.from_string(vals.get('appointment_date')) if vals.get(
                'appointment_date') else None

            for cmd in vals['doctor_ids']:
                if cmd[0] == 6 and cmd[2]:  # Command 6 is set
                    doctor_ids = cmd[2]
                    for doctor_id in doctor_ids:
                        doctor = self.env['doctor.profile'].browse(doctor_id)
                        if doctor:
                            token_number = doctor.get_next_token_number(appointment_date)
                            if token_number:
                                token_numbers.append(token_number)

            if token_numbers:
                vals['token_no'] = ", ".join(token_numbers)
        res = super(PatientAppointment, self).create(vals)
        res.password_validation()
        return res

    @api.model
    def search_appointments_by_patient(self, patient_id):

        return self.search([('patient_id', '=', patient_id)])


class AppointmentFee(models.Model):
    _name = 'appointment.fee'
    _description = 'Consultation Fee Per Doctor'

    appointment_id = fields.Many2one('patient.appointment', string='Appointment')
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    consultation_fee = fields.Float(string='Consultation Fee')

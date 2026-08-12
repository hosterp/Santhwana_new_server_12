from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AdmittedPatient(models.Model):
    _name = 'hospital.admitted.patient'
    _description = 'Admitted Patient Details'
    _rec_name = 'patient_id'
    _order = 'admission_date desc'

    patient_id = fields.Many2one('patient.reg', string="Patient", required=True)
    name = fields.Char(related='patient_id.patient_id', string="Patient Name", required=True)
    age = fields.Integer(related='patient_id.age', string="Age", readonly=True)
    gender = fields.Selection(related='patient_id.gender', string="Gender", readonly=True)
    phone_number = fields.Char(related='patient_id.phone_number', string="Phone Number", readonly=True)
    email = fields.Char(related='patient_id.email', string="Email", readonly=True)
    address = fields.Text(related='patient_id.address', string="Address", readonly=True)
    medical_records=fields.Many2one('hospital.ot')
    dob=fields.Date(related='patient_id.dob',string='Date of Birth')

    emergency_contact_name = fields.Char(string="Emergency Contact Name")
    emergency_contact_phone = fields.Char(string="Emergency Contact Phone")
    emergency_contact_relation = fields.Char(string="Relationship to Patient")

    bed_id = fields.Many2one('hospital.bed')
    room_id = fields.Many2one(related='bed_id.room_id', store=True)
    admission_date = fields.Date(string="Admission Date", required=True, default=fields.Date.today())
    room_number = fields.Many2one('hospital.room',string="Room Number")
    bed_number = fields.Char(string="Bed Number")
    admitting_department = fields.Selection([
        ('general', 'General'),
        ('surgery', 'Surgery'),
        ('icu', 'ICU'),
        ('emergency', 'Emergency'),
    ], string="Admitting Department",)
    attending_doctor = fields.Many2one('doctor.profile', string="Attending Doctor", required=True)
    visited_doctor_ids = fields.Many2many('doctor.profile', string='Visited Doctors')
    reason_for_admission = fields.Text(string="Reason for Admission")
    admission_status = fields.Selection([
        ('regular', 'Regular'),
        ('emergency', 'Emergency'),
        ('icu', 'ICU'),
    ], string="Admission Status")


    current_diagnosis = fields.Text(string="Current Diagnosis")
    medications_prescribed = fields.Text(string="Medications Prescribed")
    allergies = fields.Text(string="Allergies")
    test_results = fields.Text(string="Test Results")


    procedures_scheduled = fields.Text(string="Scheduled Procedures")
    treatment_description = fields.Text(string="Treatment Description")
    daily_progress_notes = fields.Text(string="Daily Progress Notes")
    consultation_notes = fields.Text(string="Consultation Notes")


    insurance_provider = fields.Char(string="Insurance Provider")
    insurance_policy_number = fields.Char(string="Policy Number")
    advance_payment = fields.Float(string="Advance Payment")
    billing_summary = fields.Text(string="Billing Summary")

    discharge_summary = fields.Text(string="Discharge Summary")
    surgery_date = fields.Date(string="Surgery Date")
    history = fields.Text(string="History")
    clinical_findings = fields.Text(string="Clinical findings")
    relevant_investigation = fields.Text(string="Relevant Investigation")
    surgery = fields.Text(string="Surgery")
    surgery_detail = fields.Text(string="Surgery")
    course_of_hospital = fields.Text(string="Course")
    advice_on_discharge = fields.Text(string="Advice")
    next_visit = fields.Text(string="Next Visit")
    Emergency_no = fields.Text(string="Emergency no" ,default="0471-2432121")


    discharge_date = fields.Date(string="Discharge Date")
    final_diagnosis = fields.Text(string="Final Diagnosis")
    discharge_prescriptions = fields.Text(string="Discharge Prescriptions")
    follow_up_instructions = fields.Text(string="Follow-Up Instructions")
    summary_report = fields.Text(string="Summary Report")
    room_category = fields.Many2one('room.category', string='Room Category')
    room_category_new = fields.Many2one('hospital.room.type', string='Room Category')
    advance_amount = fields.Integer(string='Advance Amount')
    status=fields.Selection([('admitted','Admitted'),('proceed_discharge','Proceed to Discharge'),('discharged','Discharged')],default='admitted')
    consultation_id = fields.Many2one('patient.registration', string="Consultation Reference")

    previous_conditions = fields.Text(string="Previous Conditions", compute='_compute_previous_conditions')

    previous_consultation_ids = fields.One2many(
        'patient.registration', 'admitted_id',
        string='Previous Consultations',
        compute='_compute_previous_consultations',
        store=False  # You can make it stored if you want to cache the results
    )
    past_prescription_ids = fields.One2many(
        'prescription.entry.lines','admitted_id', string="Past Prescriptions"
    )
    lab_report_reg_admitted_ids = fields.One2many('lab.result.page', compute='_compute_lab_reports', string="Lab")
    lab_report_test_ids = fields.One2many(
        'doctor.lab.report',
        compute='_compute_lab_test',
        string="Lab"
    )

    def action_move_to_pharmacy(self):
        any_medicine_moved = False
        for rec in self:
            today = fields.Date.today()
            matching_prescriptions = rec.past_prescription_ids.filtered(lambda l: l.date == today and l.medicine_move==False)
            # print(matching_prescriptions,'matching_prescriptionsmatching_prescriptionsmatching_prescriptionsmatching_prescriptions')
            if matching_prescriptions:
                pharmacy = self.env['pharmacy.description'].create({
                    'uhid_id': rec.patient_id.id,
                    'name':rec.name,
                    'doctor_name':rec.attending_doctor.id,
                    'payment_mathod':'credit',
                    'status_admitted':'admitted'
                })
                print(pharmacy,'pharmacypharmacypharmacypharmacypharmacypharmacypharmacypharmacypharmacypharmacypharmacy')
                line_vals = []
                for line in matching_prescriptions:
                    line_vals.append((0, 0, {
                        'product_id': line.product_id.id,
                        'morn': line.morn,
                        'noon': line.noon,
                        'night': line.night,
                        'qty': line.qty,
                    }))
                    line.medicine_move=True
                    any_medicine_moved = True
                pharmacy.prescription_line_ids = line_vals
            if any_medicine_moved:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'Pharmacy record sent successfully!',
                        'sticky': False,
                        'warning': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Info',
                        'message': 'Medicine already moved to pharmacy.',
                        'sticky': False,
                        'warning': True,
                    }
                }
    def create_referral_lab(self):
        for consultation in self:
            if not consultation.patient_id:
                raise UserError("Patient not selected.")

            doctor = self.env['doctor.profile'].search([('name', '=', consultation.attending_doctor.name)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")

            referral = self.env['lab.referral'].create({
                'doctor': doctor.id,
                'user_ide': consultation.patient_id.id,
                'patient_name': consultation.name,
                'referral_type': 'lab',
            })

            return {
                'type': 'ir.actions.act_window',
                'name': 'Lab Referral',
                'res_model': 'lab.referral',
                'view_mode': 'form',
                'res_id': referral.id,
                'target': 'new',
            }

    @api.depends('patient_id')
    def _compute_lab_test(self):
        for record in self:
            record.lab_report_test_ids = self.env['doctor.lab.report'].search([
                ('user_ide', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_lab_reports(self):
        for record in self:
            record.lab_report_reg_admitted_ids = self.env['lab.result.page'].search([
                ('patient_id', '=', record.patient_id.id)
            ])
    def action_discharged(self):
        for record in self:
            record.status = 'proceed_discharge'
            current_datetime = fields.Datetime.now()
            record.discharge_date = current_datetime.date()
            if record.patient_id:
                record.patient_id.status = 'proceed_discharge'
                record.patient_id.discharge_date = current_datetime.date()

    @api.depends('patient_id')
    def _compute_past_prescriptions(self):
        for rec in self:
            prescriptions = self.env['prescription.entry.lines'].search([
                ('prescription_line_id.patient_id', '=', rec.patient_id.id)
            ])
            rec.past_prescription_ids = prescriptions

    @api.depends('patient_id')
    def _compute_previous_consultations(self):
        for record in self:
            # Only proceed if the record has been saved (i.e., has an id)
            if record.id:
                previous_consultations = self.env['patient.registration'].search([
                    ('patient_id', '=', record.patient_id.id),
                    ('id', '!=', record.id)  # Ensure the current record is excluded
                ])
                record.previous_consultation_ids = previous_consultations
            else:
                # For unsaved records, set to False or an empty record set
                record.previous_consultation_ids = False

    def get_previous_medical_history(self):
        history = ''
        for consultation in self.previous_consultation_ids:
            if consultation.present_medications:
                history += f"Medications: {consultation.present_medications}\n"
            if consultation.allergies:
                history += f"Allergies: {consultation.allergies}\n"
            if consultation.previous_conditions:
                history += f"Previous Conditions: {consultation.previous_conditions}\n"

        return history if history else "No previous medical history available."

    @api.onchange('room_category')
    def onchange_advance_amount(self):
        for i in self:
            if i.room_category:
                i.advance_amount = i.room_category.advance_amount
                i.advance_payment=  i.advance_amount
            else:
                pass
    def action_print_patient_report(self):
        # This will trigger the report action
        return self.env.ref('homeo_doctor.action_admitted_patient_report').report_action(self)
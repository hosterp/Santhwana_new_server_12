from datetime import datetime
from email.policy import default

import dateutil.utils
from odoo import api, fields, models, tools, _
import odoo.addons
from odoo.exceptions import UserError


# from datetime import datetime, date
# default=date.today()
class PatientRegistration(models.Model):
    _name = 'patient.registration'
    _description = 'Patient Registration'
    _rec_name = 'reference_no'
    _order = 'appointment_date desc, id desc'

    reference_no = fields.Char(string="Reference")
    token_no = fields.Char(string="Token No")
    date = fields.Date(default=dateutil.utils.today())
    formatted_date = fields.Char(string='Formatted Date', compute='_compute_formatted_date')
    user_id = fields.Many2one('patient.reg', string='Name', required=True)
    patient_id = fields.Many2one('patient.reg', string='Patient ID', required=True)
    patient_name = fields.Char(string='Name', required=True, related='user_id.patient_id')
    doctor_id = fields.Char(string='Doctor name')
    doctor = fields.Many2one('doctor.profile',string='Doctor name')
    address = fields.Text(string='Address', required=True, related='user_id.address')
    age = fields.Integer(string='Age', required=True, related='user_id.age')
    phone_number = fields.Char(string='Phone No', size=12, related='user_id.phone_number')
    gender = fields.Selection(string='Gender', related='user_id.gender')
    presenting_complaints = fields.Text('Presenting Complaints')
    allergies = fields.Text('Allergies id any')
    present_medications = fields.Text('Present Medications')
    general_examination = fields.Text('General Examination')
    past_medical_history = fields.Text('Past Medical History')
    local_and_systemic = fields.Text('Local & Systemic Examination')
    investigation = fields.Text('Investigation')
    endoscopy_finding = fields.Text('Endoscopy/EUN Finding')
    review_date = fields.Date('Review Date')
    review = fields.Text('Review')
    review_note = fields.Text('Review Note')
    symptoms = fields.Text(string="Symptoms")
    professional_diagnosis = fields.Text(string='Professional Diagnosis & Treatment Plan')
    remark = fields.Text(string="Remark")
    consultation_fee = fields.Integer(related='user_id.consultation_fee', string='Consultation Fee')
    checkup_reports = fields.Text(string='Checkup Details')
    med_ids = fields.One2many("prescription.entry.lines", 'prescription_line_id', string="Prescription Entry Lines")
    lab_report_count = fields.Integer(string="Lab Reports", compute='_compute_lab_report_count')
    move_to_pharmacy_clicked = fields.Boolean(string="Move to Pharmacy Clicked", default=False)
    move_to_admission_clicked = fields.Boolean(string="Move to Patient Reg  Clicked", default=False)
    blood_pressure = fields.Char(string='BP')
    blood_pressure_low = fields.Char(string='BP')
    sugar_level = fields.Integer(string='Sugar Level (mg/dl)')
    ppbs = fields.Integer(string='PPBS (mg/dl)')
    weight = fields.Float(string='Weight (kg)')
    spo = fields.Char(string='SPO2')
    pulse_rate = fields.Char(string='Pulse Rate')
    mri_report_ids = fields.One2many('scanning.mri', 'patient_id', string="MRI")
    ct_report_ids = fields.One2many('scanning.ct', 'patient_id', string="CT")
    xray_report_ids = fields.One2many('scanning.x.ray', 'patient_id', string="X-Ray")
    lab_report_ids = fields.One2many('lab.result.page', 'patient_id_name', string="Lab")
    audiology_report_ids = fields.One2many('audiology.ref', 'patient_id', string="Audiology")
    temperature = fields.Char(string='Temp')
    medicine_course = fields.Char(string='medicine course')
    appointment_date = fields.Date('Appointment Date')
    doctor_remark_ids = fields.One2many('consultation.remark', 'consultation_id', string='Doctor Remarks')
    vssc_check = fields.Boolean(related='patient_id.vssc_boolean')
    status = fields.Selection(
        [('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),('admitted','ADMITTED')],
        default='confirmed', string="Status")
    previous_consultation_ids = fields.One2many(
        'patient.registration', 'id',
        string='Previous Consultations',
        compute='_compute_previous_consultations',
        store=False
    )
    admitted_id=fields.Many2one('hospital.admitted.patient')
    referred_doctor_ids = fields.Many2many(
        'doctor.profile',
        # 'doctor_consultation_referred_rel',
        # 'consultation_id',
        # 'doctor_id',
        string='Referred Doctors',
    )
    referred_department_ids = fields.Many2many(
        'doctor.department',
        # 'doctor_consultation_referred_rel',
        # 'consultation_id',
        # 'doctor_id',
        string='Referred Department',
    )
    remark_boolean = fields.Boolean(default=False)

    def get_previous_medical_history(self):
        history = ''
        for record in self.previous_consultation_ids:
            if record.present_medications:  # Assuming "present_medications" is part of the history
                history += f"Medications: {record.present_medications}\n"
            if record.allergies:  # Add allergies if available
                history += f"Allergies: {record.allergies}\n"
            if record.previous_conditions:  # Add previous conditions if available
                history += f"Previous Conditions: {record.previous_conditions}\n"
        return history if history else "No previous medical history available."
    @api.onchange('referred_doctor_ids')
    def _onchange_referred_doctor_ids(self):
        if self.referred_doctor_ids:
            self.remark_boolean = True
            existing_doctors = self.doctor_remark_ids.mapped('doctor_id')
            new_remark_lines = [(0, 0, {'doctor_id': doctor.id}) for doctor in self.referred_doctor_ids if
                                doctor not in existing_doctors]

            if new_remark_lines:
                self.doctor_remark_ids = [(5,)] + new_remark_lines
        else:
            self.remark_boolean = False

    @api.onchange('referred_department_ids')
    def _onchange_referred_department_ids(self):
        if self.referred_department_ids:
            return {
                'domain': {
                    'referred_doctor_ids': [
                        ('department_id', 'in', self.referred_department_ids.ids)
                    ]
                }
            }
        else:
            return {
                'domain': {
                    'referred_doctor_ids': []
                }
            }

    @api.depends('patient_id')
    def _compute_previous_consultations(self):
        for record in self:
            # Fetch all previous consultations for the same patient, excluding the current record
            record.previous_consultation_ids = self.search([
                ('user_id', '=', record.user_id.id),
                ('id', '!=', record.id)
            ])

    def _compute_lab_report_count(self):
        for record in self:
            # Count the lab reports for this patient
            record.lab_report_count = self.env['doctor.lab.report'].search_count(
                [('patient_id', '=', self.reference_no)])

    def action_view_lab_reports(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lab Reports',
            'res_model': 'doctor.lab.report',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.reference_no)],
            'context': dict(self.env.context, default_patient_id=self.reference_no),
        }

    def action_reffer_move(self):
        self.env['patient.appointment'].create({
            'patient_id': self.patient_id.id,
            'address': self.address,
            'age': self.age,
            'doctor_ids': [(6, 0, self.referred_doctor_ids.ids)],  # Correct format for Many2many field
            'departments': [(6, 0, self.referred_department_ids.ids)],  # Correct format for Many2many field
            'phone_number': self.phone_number,
            'appointment_date': fields.Datetime.now(),
        })
        return

    @api.model
    def create(self, vals):
        if vals.get('reference_no', _('New')) == _('New'):
            vals['reference_no'] = self.env['ir.sequence'].next_by_code(
                'patient.registration.group') or _('New')
        res = super(PatientRegistration, self).create(vals)
        # print("val", res)
        return res

    def _compute_formatted_date(self):
        for record in self:
            if record.date:
                formatted_date = record.date.strftime('%d/%m/%Y')
                record.formatted_date = formatted_date
            else:
                record.formatted_date = ''

    def admission_button(self):
        self.move_to_admission_clicked = True
        self.status = 'admitted'
        # Prepare admission values for prescription lines
        # admission_vals = {
        #     'prescription_line_ids': [(0, 0, {
        #         'product_id': line.product_id.id,
        #         'total_med': line.total_med,
        #         'per_ped': line.per_ped,
        #         'morn': line.morn,
        #         'noon': line.noon,
        #         'night': line.night,
        #     }) for line in self.med_ids],
        # }
        # result = {
        #     'lab_report_reg_ids': [(0, 0, {
        #         'report_details': line.report_details,
        #         'date': line.date,
        #         'doctor_id': line.doctor_id.id,
        #         'patient_id': line.patient_id.id,
        #
        #     }) for line in self.lab_report_ids],
        # }
        # mri_result = {
        #     'mri_report_reg_ids': [(0, 0, {
        #         'report_details': line.report_details,
        #         'date': line.date,
        #         'doctor_id': line.doctor_id.id,
        #         'patient_id': line.patient_id.id,
        #
        #     }) for line in self.mri_report_ids],
        # }
        # ct_result = {
        #     'ct_report_reg_ids': [(0, 0, {
        #         'report_details': line.report_details,
        #         'date': line.date,
        #         'doctor_id': line.doctor_id.id,
        #         'patient_id': line.patient_id.id,
        #
        #     }) for line in self.ct_report_ids],
        # }

        admission_record = self.env['patient.reg'].search([('reference_no', '=', self.patient_id.reference_no)],
                                                          limit=1)
        # lab_record = self.env['patient.reg'].search([('reference_no', '=', self.patient_id)], limit=1)
        # mri_record = self.env['patient.reg'].search([('reference_no', '=', self.patient_id)], limit=1)
        # ct_record = self.env['patient.reg'].search([('reference_no', '=', self.patient_id)], limit=1)
        admission_record.admission_boolean = True
        if admission_record.admission_boolean:
            admission_record.status = 'admitted'
            admission_record.doctor= self.doctor.id
            admission_record.write({'admitted_date': fields.Datetime.now()})

        else:
            admission_record.status = False
        # if admission_record:

        # for line_vals in admission_vals['prescription_line_ids']:
        #     admission_record.prescription_line_ids = [(0, 0, line_vals[2])]
        # if lab_record:
        #     for line_vals in result['lab_report_reg_ids']:
        #         lab_record.lab_report_reg_ids = [(0, 0, line_vals[2])]
        # if mri_record:
        #     for line_vals in mri_result['mri_report_reg_ids']:
        #         mri_record.mri_report_reg_ids = [(0, 0, line_vals[2])]
        # if ct_record:
        #     for line_vals in ct_result['ct_report_reg_ids']:
        #         ct_record.ct_report_reg_ids = [(0, 0, line_vals[2])]
        # else:

        # admission_record = self.env['patient.reg'].create(admission_vals)

        # Notify the user about the success
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Record updated or created successfully!',
                'sticky': False,
                'warning': False,
            }
        }

    def action_move_to_pharmacy(self):
        self.move_to_pharmacy_clicked = True
        pharmacy_vals = {
            'name': self.patient_name,
            'uhid_id': self.patient_id.id,
            'phone_number': self.phone_number,
            'doctor_name': self.doctor.id,
            'prescription_line_ids': [(0, 0, {
                'products_id': line.products_id.id,
                'category': line.category.id,
                'per_ped': line.per_ped,
                'morn': line.morn,
                'noon': line.noon,
                'night': line.night,
                'rate': line.per_ped*line.total_med,
            }) for line in self.med_ids],
        }

        pharmacy_record = self.env['pharmacy.description'].create(pharmacy_vals)
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

        # return {
        #     'type': 'ir.actions.act_window',
        #     'name': 'Pharmacy Description',
        #     'res_model': 'pharmacy.description',
        #     'view_mode': 'form',
        #     'res_id': pharmacy_record.id,
        #     'target': 'current',
        # }

    def action_create_referral_lab(self):
        return self._create_referral_lab()

    def action_create_referral_xray(self, scan_type='xray'):
        for consultation in self:
            if not consultation.user_id:  # Assuming user_id is the patient
                raise UserError("Patient not selected.")

            # Debugging output
            # print("User  ID:", consultation.user_id)
            # print("User  Reference No:", consultation.user_id.reference_no)
            doctor = self.env['doctor.profile'].search([('name', '=', consultation.doctor_id)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")
            # Create the referral record
            referral = self.env['doctor.referral'].create({
                'doctor_id': doctor.id,
                'user_ide': consultation.user_id.id,
                'patient_id': consultation.reference_no,
                'patient_name': consultation.patient_name,
                'referral_type': 'scanning',
                'details': f'Refer for {scan_type.replace("_", " ").title()}',
                'scan_type': scan_type,
            })

            # # Create the xray scan record and link it to the reference_no
            # x_ray_vals = {
            #     'patient_id': consultation.user_id.id,
            #     'doctor_id': doctor.id,
            #     'reference_no': consultation.reference_no,  # Ensure this is the correct reference_no
            #     'scan_registered_date': fields.Date.today(),
            #     # Add other necessary fields...
            # }
            #
            # # Debugging output for xray scan values
            # print("MRI Scan Values:", x_ray_vals)
            #
            # # Create the xray scan record
            # xray_scan = self.env['scanning.x.ray'].create(x_ray_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Referral',
            'res_model': 'doctor.referral',
            'view_mode': 'form',
            'res_id': referral.id,
            'target': 'new',
        }

    def action_create_referral_mri(self, scan_type='mri'):
        for consultation in self:
            if not consultation.user_id:  # Assuming user_id is the patient
                raise UserError("Patient not selected.")

            # Debugging output
            # print("User  ID:", consultation.user_id)
            # print("User  Reference No:", consultation.user_id.reference_no)
            doctor = self.env['doctor.profile'].search([('name', '=', consultation.doctor_id)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")
            # Create the referral record
            referral = self.env['doctor.referral'].create({
                'doctor_id': doctor.id,
                'user_ide': consultation.user_id.id,
                'patient_id': consultation.reference_no,
                'referral_type': 'scanning',
                'details': f'Refer for {scan_type.replace("_", " ").title()}',
                'scan_type': scan_type,
            })

            # Create the MRI scan record and link it to the reference_no
            # mri_scan_vals = {
            #     'patient_id': consultation.user_id.id,
            #     'doctor_id': doctor.id,
            #     'reference_no': consultation.reference_no,  # Ensure this is the correct reference_no
            #     'scan_registered_date': fields.Date.today(),
            #     # Add other necessary fields...
            # }
            #
            # # Debugging output for MRI scan values
            # print("MRI Scan Values:", mri_scan_vals)
            #
            # # Create the MRI scan record
            # mri_scan = self.env['scanning.mri'].create(mri_scan_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Referral',
            'res_model': 'doctor.referral',
            'view_mode': 'form',
            'res_id': referral.id,
            'target': 'new',
        }

    def action_create_referral_ct(self, scan_type='ct'):
        for consultation in self:
            if not consultation.user_id:
                raise UserError("Patient not selected.")

            # Debugging output
            # print("User  ID:", consultation.user_id)
            # print("User  Reference No:", consultation.user_id.reference_no)
            doctor = self.env['doctor.profile'].search([('name', '=', consultation.doctor_id)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")

            # Create the referral record
            referral = self.env['doctor.referral'].create({
                'doctor_id': doctor.id,
                'user_ide': consultation.user_id.id,
                'patient_id': consultation.reference_no,
                'referral_type': 'scanning',
                'details': f'Refer for {scan_type.replace("_", " ").title()}',
                'scan_type': scan_type,
            })


            # ct_vals = {
            #     'patient_id': consultation.user_id.id,
            #     'doctor_id': doctor.id,
            #     'reference_no': consultation.reference_no,
            #     'scan_registered_date': fields.Date.today(),
            #     # Add other necessary fields...
            # }
            #
            # # Debugging output for ct scan values
            # print("ct Scan Values:", ct_vals)
            #
            # # Create the ct scan record
            # ct_scan = self.env['scanning.ct'].create(ct_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Referral',
            'res_model': 'doctor.referral',
            'view_mode': 'form',
            'res_id': referral.id,
            'target': 'new',
        }

    def action_create_referral_audiology(self, scan_type='audiology'):
        for consultation in self:
            if not consultation.user_id:  # Assuming user_id is the patient
                raise UserError("Patient not selected.")

            # Debugging output
            # print("User  ID:", consultation.user_id)
            # print("User  Reference No:", consultation.user_id.reference_no)
            doctor = self.env['doctor.profile'].search([('name', '=', consultation.doctor_id)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")
            # Create the referral record
            referral = self.env['doctor.referral'].create({
                'doctor_id': doctor.id,
                'user_ide': consultation.user_id.id,
                'patient_id': consultation.reference_no,
                'referral_type': 'scanning',
                'details': f'Refer for {scan_type.replace("_", " ").title()}',
                'scan_type': scan_type,
            })


            # audiology_vals = {
            #     'patient_id': consultation.user_id.id,
            #     'doctor_id': doctor.id,
            #     'reference_no': consultation.reference_no,
            #     'scan_registered_date': fields.Date.today(),
            #
            # }
            #
            #
            # print("Audiology Scan Values:", audiology_vals)
            #
            #
            # audio_scan = self.env['audiology.ref'].create(audiology_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Referral',
            'res_model': 'doctor.referral',
            'view_mode': 'form',
            'res_id': referral.id,
            'target': 'new',
        }


    def _create_referral_lab(self):
        for consultation in self:
            if not consultation.user_id:
                raise UserError("Patient not selected.")
            doctor = self.env['doctor.profile'].search([('name', '=', consultation.doctor.name)], limit=1)
            if not doctor:
                raise UserError("Doctor not found in the system.")


            referral = self.env['lab.referral'].create({
                'doctor': doctor.id,
                'user_ide': consultation.user_id.id,
                # 'patient_id': consultation.reference_no,
                'patient_name': consultation.patient_name,
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

    def action_view_consultations(self):
        if not self.patient_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Previous Consultations',
            'res_model': 'patient.registration',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('homeo_doctor.view_patient_registration_tree').id, 'tree'),
                (self.env.ref('homeo_doctor.patient_registration_form').id, 'form'),
            ],
            'domain': [('patient_id', '=', self.patient_id.id)],
            'context': {'default_patient_id': self.patient_id.id},
            'target': 'new',
        }

    def action_view_consultation_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Consultation',
            'res_model': 'patient.registration',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('homeo_doctor.patient_registration_form').id, 'form')],
            'target': 'new',  # Opens in modal
        }


class PrescriptionEntryLine(models.Model):
    _name = 'prescription.entry.lines'
    _description = 'Prescription Entry Line'

    prescription_line_id = fields.Many2one("patient.registration", string="Prescription Entry")
    product_id = fields.Many2one('product.product', string="Medicine")
    products_id = fields.Many2one('stock.entry', string="Medicine")
    total_med = fields.Integer("Tot Med", compute="_compute_total_med", store=True)
    per_ped = fields.Integer(relate='product_id.lst_price',string="Per Med")
    morn = fields.Integer("Morn")
    noon = fields.Integer("Noon")
    night = fields.Integer("Night")
    stock_in_hand = fields.Char(string='Stock In Hand', compute="_compute_stock_in_hand", store=True)
    admitted_id = fields.Many2one('hospital.admitted.patient')
    date=fields.Date(default=dateutil.utils.today())
    qty=fields.Integer(string='QTY')
    medicine_move=fields.Boolean()
    category = fields.Many2one('medicine.category', string='Category')
    duration=fields.Many2one('number.of.day',string='Duration')
    remarks = fields.Many2one('remarks.time',string='Remarks')
    reg_time = fields.Many2one('reg.time', string='Regtime')
    generic=fields.Many2one('generic.medicine', string='Generic')
    @api.onchange('category')
    def _onchange_category(self):
        if self.category:
            return {
                'domain': {
                    'products_id': [('category', '=', self.category.id)]
                }
            }
        else:
            return {
                'domain': {
                    'products_id': []
                }
            }

    @api.depends('products_id')
    def _compute_stock_in_hand(self):
        """Fetch the total available quantity from stock.entry for the selected product."""
        for record in self:
            if record.products_id:
                total_quantity = sum(self.env['stock.entry'].search([
                    ('product_id', '=', record.products_id.product_id.id),
                ]).mapped('quantity'))  # Summing up all quantities

                record.stock_in_hand = total_quantity


    # @api.depends('morn', 'noon', 'night', 'per_ped')
    # def _compute_total_med(self):
    #     for rec in self:
    #         rec.total_med = (rec.morn + rec.noon + rec.night) * rec.per_ped if rec.per_ped else 0
    @api.depends('morn', 'noon', 'night', 'prescription_line_id.medicine_course')
    def _compute_total_med(self):
        for rec in self:
            morn = rec.morn or 0
            noon = rec.noon or 0
            night = rec.night or 0
            medicine_course = rec.prescription_line_id.medicine_course or 0

            # Ensure integer conversion
            try:
                total_per_day = int(morn) + int(noon) + int(night)
                medicine_course = int(medicine_course)
                rec.total_med = total_per_day * medicine_course
            except ValueError:
                rec.total_med = 0

    @api.onchange('product_id')
    def _onchange_product_id(self):

        for rec in self:
            rec.per_ped = rec.product_id.lst_price if rec.product_id else 0

class DoctorReferral(models.Model):
    _name = 'doctor.referral'
    _rec_name = 'reference_no'

    reference_no = fields.Char(string="Reference", readonly=True)
    user_ide = fields.Many2one('patient.reg', string="Patient", readonly=True)
    doctor_id = fields.Many2one('doctor.profile', string="Doctor", readonly=True)
    patient_id = fields.Many2one('patient.registration', string="Consultation ID", readonly=True)
    referral_type = fields.Selection([('scanning', 'Scanning'), ('consultation', 'Consultation')],
                                     default='scanning')
    details = fields.Text(string="Referral Details")
    scan_type = fields.Selection([('mri', 'MRI'), ('ct', 'CT Scan'), ('xray', 'X-Ray'), ('audiology', 'Audiology')],
                                 string="Scan Type", readonly=True)
    patient_name = fields.Char(related='patient_id.patient_name', string='Patient Name')

    mri_report_id = fields.Many2one('scanning.mri', string="MRI Report", readonly=True)
    ct_report_id = fields.Many2one('scanning.ct', string="CT Report", readonly=True)
    xray_report_id = fields.Many2one('scanning.x.ray', string="X-Ray Report", readonly=True)
    audiology_report_id = fields.Many2one('audiology.ref', string="Audiology Report", readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('reference_no', _('New')) == _('New'):
            vals['reference_no'] = self.env['ir.sequence'].next_by_code(
                'doctor.referral.group') or _('New')
        res = super(DoctorReferral, self).create(vals)
        return res

    def action_submit(self):
        for record in self:
            patient_registration = self.env['patient.registration'].search([
                ('user_id', '=', record.user_ide.id)
            ], limit=1)

            if not patient_registration:
                patient_registration = self.env['patient.registration'].create({
                    'user_id': record.user_ide.id,
                    'patient_name': record.patient_name,
                    'phone_number': record.user_ide.phone_number,
                    'address': record.user_ide.address,
                    'age': record.user_ide.age,
                    'gender': record.user_ide.gender,
                    'consultation_fee': record.user_ide.consultation_fee,
                })

            record.patient_id = patient_registration.id

            if record.referral_type == 'scanning':
                report = None
                report_values = {
                    'user_ide': record.user_ide.id,
                    'doctor_id': record.doctor_id.id,
                    'patient_name': record.patient_name,
                    'reference_no': record.reference_no,
                    'details': record.details,
                    'scan_registered_date': fields.Date.today(),
                    'patient_id': patient_registration.id,
                }

                if record.scan_type == 'mri':
                    report = self.env['scanning.mri'].create(report_values)
                    record.mri_report_id = report.id
                elif record.scan_type == 'ct':
                    report = self.env['scanning.ct'].create(report_values)
                    record.ct_report_id = report.id
                elif record.scan_type == 'xray':
                    report = self.env['scanning.x.ray'].create(report_values)
                    record.xray_report_id = report.id
                elif record.scan_type == 'audiology':
                    report = self.env['audiology.ref'].create(report_values)
                    record.audiology_report_id = report.id

                if report:
                    report.register_visible = False


class LabReferral(models.Model):
    _name = 'lab.referral'
    _rec_name = 'reference_no'

    reference_no = fields.Char(string="Reference", readonly=True)
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    user_ide = fields.Many2one('patient.reg', string="Patient", readonly=True)
    patient_id = fields.Many2one('patient.registration', string='Patient')
    patient_name = fields.Char(related='user_ide.patient_id', string='Patient Name')
    lab_test = fields.Many2many('lab.department', string='Lab Department')
    test_type = fields.Many2many('lab.investigation', string='Investigation Name')
    test_names = fields.Text(string='Test Names')
    referral_type = fields.Selection([('scanning', 'Scanning'), ('consultation', 'Consultation'), ('lab', 'LAB')],
                                     default='lab')
    details = fields.Text(string="Referral Details")

    lab_report_id = fields.Many2one('doctor.lab.report', string="Lab Report", readonly=True)


    @api.onchange('test_type')
    def _onchange_test_type(self):
        """ Fetch corresponding test names from lab.resultant.confi """
        if self.test_type:
            resultant_tests = self.env['lab.resultant.confi'].search([
                ('test_name_bill_code', 'in', self.test_type.ids)
            ])

            # print("🔍 Found Tests: %s", resultant_tests)  # Log test records


            self.test_names = ', '.join(resultant_tests.mapped('test_name')) if resultant_tests else False
            print(  self.test_names,'  self.test_names  self.test_names  self.test_names  self.test_names  self.test_names  self.test_names  self.test_names')
        else:
            self.test_names = False  # Clear field if no test type is selected

    # @api.onchange('lab_test')
    # def _onchange_lab_test(self):
    #     """ Update test_type options based on selected lab_test """
    #     if self.lab_test:
    #         return {
    #             'domain': {
    #                 'test_type': [('lab_department', 'in', self.lab_test.ids)]
    #             }
    #         }
    #     else:
    #         return {
    #             'domain': {'test_type': []}
    #         }
    @api.onchange('lab_test', 'test_type')
    def _onchange_tests(self):
        lab_test_department = ', '.join(self.lab_test.exists().mapped('department_name'))
        investigation = ', '.join(self.test_type.exists().mapped('investigation_name'))

        details_list = []
        if lab_test_department:
            details_list.append(f"Lab Test Department: {lab_test_department}")
        if investigation:
            details_list.append(f"investigation: {investigation}")

        self.details = "\n".join(details_list)

    def action_submit(self):
        for record in self:
            # Look for existing patient registration
            patient_registration = self.env['patient.registration'].search([
                ('user_id', '=', record.user_ide.id)
            ], limit=1)

            # Update or create patient registration
            if patient_registration:
                patient_registration.write({
                    'patient_name': record.patient_name,
                    'phone_number': record.user_ide.phone_number,
                    'address': record.user_ide.address,
                    'age': record.user_ide.age,
                    'gender': record.user_ide.gender,
                    'consultation_fee': record.user_ide.consultation_fee,
                })
            else:
                patient_registration = self.env['patient.registration'].create({
                    'user_id': record.user_ide.id,
                    'patient_id': record.user_ide.id,
                    'patient_name': record.patient_name,
                    'phone_number': record.user_ide.phone_number,
                    'address': record.user_ide.address,
                    'age': record.user_ide.age,
                    'gender': record.user_ide.gender,
                    'consultation_fee': record.user_ide.consultation_fee,
                })

            # Create lab report
            lab_report = self.env['doctor.lab.report'].create({
                'referral_details': record.details,
                'reference_no': record.reference_no,
                'user_ide': record.user_ide.id,
                'doctor_id': record.doctor.id,
                'patient_name': record.patient_name,
                'patient_id': patient_registration.id,
                'age': record.user_ide.age,
                'gender': record.user_ide.gender,
            })
            lab_report.register_visible = False

            # Process test names only once
            test_names_list = record.test_names.split(', ') if record.test_names else []

            # Create billing entries for each test type
            for test in record.test_type:
                self.env['lab.billing.page'].create({
                    'lab_billing_id': lab_report.id,
                    'lab_type_id': test.id,
                })
            lab_report.generate_lab_scan_lines()

            # Optional: Link the report to the referral
            record.lab_report_id = lab_report.id
            # # FIXED: Process test names separately, assigning each to the appropriate test type and unit
            # # Inside the loop for test_names_list
            # # Inside the loop for test_names_list
            # for test_name in test_names_list:
            #     test_name = test_name.strip()  # Clean whitespace
            #     print(f"🔍 Searching for test_name: {test_name}")
            #
            #     # Search for test configs that either match the patient's gender OR are gender-neutral
            #     test_results = self.env['lab.resultant.confi'].search([
            #         ('test_name', '=', test_name),
            #         '|',
            #         ('gender', '=', record.user_ide.gender),
            #         ('gender', '=', False)
            #     ], limit=1)
            #
            #     # Only create a lab scan line if we found a matching test configuration
            #     if test_results and record.test_type:
            #         referral_range = test_results.referral_range
            #         unit = test_results.unit
            #         print(f"✅ Found: {test_name} | Referral Range: {referral_range} | Unit: {unit}")
            #
            #         # Create the lab scan line
            #         self.env['lab.scan.line'].create({
            #             'lab_id': lab_report.id,
            #             'lab_type_id': record.test_type[0].id,
            #             'lab_test_name': test_name,
            #             'lab_reference_range': referral_range,
            #             'unit': unit,
            #         })
            #     else:
            #         print(f"❌ Skipping test: {test_name} - No configuration matching gender: {record.user_ide.gender}")
            #         # No lab scan line is created for this test

    @api.model
    def create(self, vals):
        if vals.get('reference_no', _('New')) == _('New'):
            vals['reference_no'] = self.env['ir.sequence'].next_by_code('lab.referral') or _('New')
        return super(LabReferral, self).create(vals)



class LabTest(models.Model):
    _name = 'labtest.type'
    _rec_name = 'lab_test'

    lab_test = fields.Char('Lab Test')


class TestType(models.Model):
    _name = 'test.type'
    _rec_name = 'test_type'

    test_type = fields.Char('Test Type')


class ConsultationRemark(models.Model):
    _name = 'consultation.remark'

    consultation_id = fields.Many2one('patient.registration', string='Consultation', ondelete='cascade')
    doctor_id = fields.Many2one('doctor.profile', string='Doctor')
    remark = fields.Text(string='Remark')



class DurationOFCourse(models.Model):
    _name = 'number.of.day'
    _rec_name = 'duration'


    duration=fields.Char(string='Duration')

class RemarksCourse(models.Model):
    _name = 'remarks.time'
    _rec_name = 'remarks'


    remarks=fields.Char(string='Duration')

class RegTime(models.Model):
    _name = 'reg.time'
    _rec_name = 'regtime'


    regtime=fields.Char(string='Regtime')

class GenericMedicine(models.Model):
    _name = 'generic.medicine'
    _rec_name = 'generic'


    generic=fields.Char(string='Generic')
from odoo import api, fields, models, _
from datetime import datetime



class Audiology(models.Model):
    _name = 'audiology.ref'
    _rec_name = 'patient_id'

    user_ide = fields.Many2one('patient.reg', string="Patient")
    user_ide_discharge = fields.Many2one('discharge.billing', string="Patient")
    patient_id = fields.Many2one('patient.registration', string="Consultation ID")
    patient_name = fields.Char(related='patient_id.patient_name', string="Patient Name")
    reference_no = fields.Char(string="Reference No")
    age = fields.Integer(string='Age', related='patient_id.age')
    gender = fields.Selection(string='Gender', related='patient_id.gender')
    doctor_id = fields.Many2one('doctor.profile', string="Doctor", compute="_compute_doctor_name", store=True, readonly=False)
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type", default='op')
    admission = fields.Boolean(string="Admission")

    @api.onchange('user_ide', 'patient_id', 'scan_registered_date', 'bill_type')
    def _onchange_user_ide_update_doctor(self):
        for rec in self:
            # 1. ABSOLUTE HISTORICAL LOCK (IP ONLY)
            if rec.doctor_id and rec.user_ide and rec.user_ide.status == 'discharged':
                if (rec.bill_type == 'admitted') or (rec.patient_id and rec.patient_id.status == 'admitted'):
                    return

            doctor = False
            if rec.user_ide and rec.scan_registered_date:
                bill_date = rec.scan_registered_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # 0️⃣ Priority 0: Discharged Doctor Restore (Specific User Request)
                if not rec.doctor_id and rec.user_ide.status == 'discharged':
                    dis_doctor = False
                    if rec.admission:
                        # Take OP doctor
                        if rec.user_ide.doctor:
                            dis_doctor = rec.user_ide.doctor.id
                        elif rec.user_ide.doc_name:
                            dis_doctor = rec.user_ide.doc_name.id
                    else:
                        # Take IP doctor from hospital.admitted.patient
                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.user_ide.id),
                            ('admission_date', '<=', bill_date),
                            ('discharge_date', '>=', bill_date)
                        ], limit=1)
                        if admission_log and admission_log.attending_doctor:
                            dis_doctor = admission_log.attending_doctor.id
                    
                    if dis_doctor:
                        rec.doctor_id = dis_doctor
                        return

                # 1️⃣ Priority 1: Linked Consultant (Highest Accuracy)
                if rec.patient_id and rec.patient_id.doctor:
                    doctor = rec.patient_id.doctor.id

                # 2️⃣ Priority 2: IP Context Search
                if not doctor and rec.bill_type == 'admitted':
                    # A. Latest IP session (Round) - ensures we follow doctor changes during admission
                    session = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('date', '<=', bill_date),
                        ('status', '=', 'admitted')
                    ], order='date desc, id desc', limit=1)
                    if session and session.doctor:
                        doctor = session.doctor.id

                    # B. Admission Log
                    if not doctor:
                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.user_ide.id),
                            ('admission_date', '<=', bill_date)
                        ], order='admission_date desc', limit=1)
                        if admission_log:
                            adm_dis_date = admission_log.discharge_date
                            if isinstance(adm_dis_date, datetime):
                                adm_dis_date = adm_dis_date.date()
                            is_late_ip = (rec.user_ide.status == 'discharged')
                            if not adm_dis_date or bill_date <= adm_dis_date or is_late_ip:
                                if admission_log.attending_doctor:
                                    doctor = admission_log.attending_doctor.id

                # 3️⃣ Priority 3: Discharged History (IP)
                if not doctor and rec.bill_type == 'admitted':
                    history = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.user_ide.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if history and history.doctor:
                        doctor = history.doctor.id

                # 4️⃣ Priority 4: OP Context Search
                if not doctor:
                    reg = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('date', '<=', bill_date),
                        ('status', 'not in', ['admitted', 'proceed_discharge'])
                    ], order='date desc', limit=1)
                    if reg and reg.doctor:
                        doctor = reg.doctor.id

                # 5️⃣ Priority 5: Latest Consultation (Any)
                if not doctor:
                    if rec.user_ide.doctor:
                        doctor = rec.user_ide.doctor.id
                    elif rec.user_ide.doc_name:
                        doctor = rec.user_ide.doc_name.id

                # 6️⃣ Priority 6: Appointments
                if not doctor:
                    appt = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('appointment_date', '<=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt and appt.doctor_ids:
                        doctor = appt.doctor_ids[0].id

            rec.doctor_id = doctor

    @api.depends('user_ide', 'user_ide.status', 'patient_id', 'scan_registered_date', 'bill_type')
    def _compute_doctor_name(self):
        for rec in self:
            # 1. ABSOLUTE HISTORICAL LOCK (IP ONLY)
            if rec.doctor_id and rec.user_ide and rec.user_ide.status == 'discharged':
                if (rec.bill_type == 'admitted') or (rec.patient_id and rec.patient_id.status == 'admitted'):
                    continue

            # 2. Status Lock
            if rec.status == 'paid' and rec.doctor_id:
                continue

            # 3. Sync with DB
            if not rec.doctor_id and isinstance(rec.id, int):
                existing = self.sudo().browse(rec.id).doctor_id
                if existing:
                    rec.doctor_id = existing.id
                    if rec.user_ide and rec.user_ide.status == 'discharged' and (rec.bill_type == 'admitted' or (rec.patient_id and rec.patient_id.status == 'admitted')):
                        continue

            doctor = False
            if rec.user_ide and rec.scan_registered_date:
                bill_date = rec.scan_registered_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # 0️⃣ Priority 0: Discharged Doctor Restore (Specific User Request)
                if not rec.doctor_id and rec.user_ide.status == 'discharged':
                    if rec.admission:
                        # Take OP doctor
                        if rec.user_ide.doctor:
                            doctor = rec.user_ide.doctor.id
                        elif rec.user_ide.doc_name:
                            doctor = rec.user_ide.doc_name.id
                    else:
                        # Take IP doctor from hospital.admitted.patient
                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.user_ide.id),
                            ('admission_date', '<=', bill_date),
                            ('discharge_date', '>=', bill_date)
                        ], limit=1)
                        if admission_log and admission_log.attending_doctor:
                            doctor = admission_log.attending_doctor.id
                    
                    if doctor:
                        rec.doctor_id = doctor
                        continue

                # 1️⃣ Priority 1: Linked Consultant (Explicit)
                if rec.patient_id and rec.patient_id.doctor:
                    doctor = rec.patient_id.doctor.id

                # 2️⃣ Priority 2: IP Context Search
                if not doctor and rec.bill_type == 'admitted':
                    session = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('date', '<=', bill_date),
                        ('status', '=', 'admitted')
                    ], order='date desc, id desc', limit=1)
                    if session and session.doctor:
                        doctor = session.doctor.id

                    if not doctor:
                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.user_ide.id),
                            ('admission_date', '<=', bill_date)
                        ], order='admission_date desc', limit=1)
                        if admission_log:
                            adm_dis_date = admission_log.discharge_date
                            if isinstance(adm_dis_date, datetime):
                                adm_dis_date = adm_dis_date.date()
                            is_late_ip = (rec.user_ide.status == 'discharged')
                            if not adm_dis_date or bill_date <= adm_dis_date or is_late_ip:
                                if admission_log.attending_doctor:
                                    doctor = admission_log.attending_doctor.id

                # 3️⃣ Priority 3: Discharged History (IP)
                if not doctor and rec.bill_type == 'admitted':
                    history = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.user_ide.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if history and history.doctor:
                        doctor = history.doctor.id

                # 4️⃣ Priority 4: OP Fallback
                if not doctor:
                    reg = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('date', '<=', bill_date),
                        ('status', 'not in', ['admitted', 'proceed_discharge'])
                    ], order='date desc', limit=1)
                    if reg and reg.doctor:
                        doctor = reg.doctor.id

                # 5️⃣ Priority 5: Latest Consultation (Any)
                if not doctor:
                    if rec.user_ide.doctor:
                        doctor = rec.user_ide.doctor.id
                    elif rec.user_ide.doc_name:
                        doctor = rec.user_ide.doc_name.id

                # 6️⃣ Priority 6: Appointments
                if not doctor:
                    appt = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.user_ide.id),
                        ('appointment_date', '<=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt and appt.doctor_ids:
                        doctor = appt.doctor_ids[0].id

            rec.doctor_id = doctor
    scan_registered_date = fields.Date(string="Registered Date", default=fields.Date.context_today)
    scan_report_date = fields.Date(string="Report Date")
    file_report = fields.Binary(string="Result")
    file_report_name = fields.Char(string="Result")
    investigation = fields.Text(string="Investigation")
    details = fields.Text(string="Details")
    impression = fields.Text(string="Impression")
    referral_id = fields.Many2one('doctor.referral', string="Referral ID")
    report_details = fields.Text(string="Audiology Report Details")
    therapy_line_ids = fields.One2many('audiology.therapy.line', 'audiology_id', string='Therapy Details')
    # with register
    register_visible = fields.Boolean(default=True)
    register_patient_name = fields.Char("Patient Name")
    register_address = fields.Text(string="Address")
    register_age = fields.Integer(string="Age", store=True)
    register_phone_number = fields.Char(string="Mobile No", size=12)
    register_email = fields.Char(string="Email ID")
    # register_pin_code = fields.Integer(string="PIN Code")
    register_id_proof = fields.Binary(string='Upload ID Proof')
    register_vssc_id = fields.Char(string="VSSC ID No")
    # register_department_id = fields.Many2one('doctor.department', string='Department')
    # register_doc_name = fields.Many2one('doctor.profile', string='Doctor')
    registration_fee = fields.Float(string="Registration Fee", default=50.0)
    walk_in_audio = fields.Boolean(default=False)


    def action_walk_in_patient(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Walk-in Patients',
            'res_model': 'audiology.ref',
            'view_mode': 'tree,form',
            'views': [(self.env.ref('homeo_doctor.view_audiology_walk_in_tree').id, 'tree'),
                      (self.env.ref('homeo_doctor.view_audiology_form').id, 'form')],
            'domain': [('register_visible', '=', True)],
            'target': 'current',
        }

    @api.model
    def create(self, vals):
        # # Generate report reference if not provided
        # if vals.get('report_reference', _('New')) == _('New'):
        #     vals['report_reference'] = self.env['ir.sequence'].next_by_code('audiology.ref') or _('New')

        # Check if registration is visible and patient name is provided
        if vals.get('register_visible', True) and vals.get('register_patient_name'):
            # Prepare patient registration values
            patient_reg_vals = {
                'patient_id': vals.get('register_patient_name'),
                'address': vals.get('register_address'),
                'age': vals.get('register_age'),
                'email': vals.get('register_email'),
                'phone_number': vals.get('register_phone_number'),
                # 'registration_fee': vals.get('registration_fee', 50.0),
                'consultation_check': vals.get('consultation_check', True),
                'walk_in': True

            }
            print(patient_reg_vals)

            # Create patient registration
            patient_reg = self.env['patient.reg'].create(patient_reg_vals)
            vals['user_ide'] = patient_reg.id


        return super(Audiology, self).create(vals)

    def write(self, vals):
        res = super(Audiology, self).write(vals)
        for record in self:
            # Sync back to patient.reg if details changed in the scan record
            if record.user_ide and ('register_patient_name' in vals or 'register_phone_number' in vals or 'register_age' in vals or 'register_address' in vals):
                reg_vals = {}
                if 'register_patient_name' in vals:
                    reg_vals['patient_id'] = vals['register_patient_name']
                if 'register_phone_number' in vals:
                    reg_vals['phone_number'] = vals['register_phone_number']
                if 'register_age' in vals:
                    reg_vals['age'] = vals['register_age']
                if 'register_address' in vals:
                    reg_vals['address'] = vals['register_address']
                
                if reg_vals:
                    record.user_ide.sudo().write(reg_vals)
        return res

    def print_invoice(self):
        return self.env.ref('homeo_doctor.action_report_audiology_invoice').report_action(self)



    def action_add_report(self, report_details):

        for scan in self:

            report = self.env['audiology.ref'].create({
                'referral_id': scan.referral_id.id,
                'patient_id': scan.patient_id.id,
                'report_details': report_details,
            })


            scan.referral_id.write({
                'ct_report_id': report.id
            })

        return True

    @api.onchange('user_ide')
    def _onchange_patient_id(self):
        if self.user_ide:
            # Domain for latest referral
            ref_domain = [('user_ide', '=', self.user_ide.id), ('scan_type', '=', 'audiology')]
            
            latest_referral = self.env['doctor.referral'].search(
                ref_domain, order='create_date desc', limit=1
            )
            
            # REFINEMENT: If patient is discharged, do NOT auto-link a referral from a previous IP session
            if latest_referral and self.user_ide.status == 'discharged':
                if latest_referral.status == 'admitted':
                    latest_referral = False

            self.referral_id = latest_referral.id if latest_referral else False
            self.details = latest_referral.details if latest_referral else False
            self.patient_id = latest_referral.patient_id if latest_referral else False


class AudiologyService(models.Model):
    _name = 'audiology.service.type'
    _description = 'Type of Audiology Therapy'

    name = fields.Char(string='Service', required=True)

class Session(models.Model):
    _name = 'audiology.session'
    _description = 'Audiology Sessions'
    _rec_name = 'session'

    session = fields.Integer(string='Session', required=True)

class AudiologyRate(models.Model):
    _name = 'audiology.rate'
    _description = 'Audiology Therapy Rate'
    _rec_name = 'amount'  # This will display the amount in Many2one fields

    amount = fields.Float(string='Amount', required=True)

class AudiologyTherapyLine(models.Model):
    _name = 'audiology.therapy.line'
    _description = 'Audiology Therapy Line'

    audiology_id = fields.Many2one('audiology.ref', string='Audiology Therapy')
    service_id = fields.Many2one('audiology.service.type', string='Service', required=True)
    session_id = fields.Many2one('audiology.session', string='Session', required=True)
    rate_id = fields.Many2one('audiology.rate', string='Rate/Session', required=True)



class AudiologyTest(models.Model):
    _name = 'audiology.test'
    _description = 'Audiology Test'

    name = fields.Char(string='Test Name', required=True)
    test_code = fields.Char(string='Test Code')
    price = fields.Float(string='Rate')
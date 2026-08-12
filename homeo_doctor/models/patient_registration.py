import re
from datetime import date, datetime
import logging
from gevent.util import print_run_info
from collections import defaultdict
from odoo.exceptions import UserError

import dateutil.utils
from odoo import api, fields, models, tools, _
import odoo.addons
from odoo.exceptions import ValidationError

from datetime import datetime
import pytz

# from odoo.odoo.exceptions import ValidationError


# from datetime import datetime, date
# default=date.today()

class PatientRegistration(models.Model):
    _name = 'patient.reg'
    _description = 'Patient Registration'
    _rec_name = 'reference_no'
    _order = 'reference_no desc,formatted_date desc'

    reference_no = fields.Char(string="Reference")
    token_no = fields.Char(string="Token No")
    date = fields.Date(default=dateutil.utils.today(), readonly=True)
    formatted_date = fields.Char(string='Formatted Date', compute='_compute_formatted_date', store=True)
    track_registration_date = fields.Date(default=dateutil.utils.today())
    patient_id = fields.Char(string="Name")
    address = fields.Text(string="Address")
    age = fields.Integer(string="Age", store=True)
    phone_number = fields.Char(string="Mobile No", size=12)
    email = fields.Char(string="Email ID")
    pin_code = fields.Char(string="PIN Code")
    id_proof = fields.Binary(string='VSSC ID Proof')
    vssc_id = fields.Char(string="VSSC ID No")
    department_id = fields.Many2one('doctor.department', string='Department')
    doc_name = fields.Many2one('doctor.profile', string='Doctor')
    registration_fee = fields.Many2one('patient.registration.fee', string="Registration Fee", )
    remark = fields.Text(string="Remark")
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string="Gender")
    lab_report_count = fields.Integer(string="Lab Reports", compute='_compute_lab_report_count')
    time = fields.Date(string="Date", default=fields.Date.context_today)
    mri_report_ids = fields.One2many('scanning.mri', 'patient_id', string="MRI Reports")
    ct_report_ids = fields.One2many('scanning.ct', 'patient_id', string="CT Reports")
    xray_report_ids = fields.One2many('scanning.x.ray', 'patient_id', string="X-Ray Reports")
    audiology_report_ids = fields.One2many('audiology.ref', 'patient_id', string="Audiology")
    consultation_fee = fields.Integer(string='Consultation Fee', compute='_compute_consultation_fee', store=True)
    # prescription_line_ids = fields.One2many('pharmacy.prescription.line', 'admission_id', string="Prescriptions")
    lab_report_reg_ids = fields.One2many('lab.result.page', 'patient_re_id_name', string="Lab")
    mri_report_reg_ids = fields.One2many('scanning.mri', 'user_ide', string="MRI")
    ct_report_reg_ids = fields.One2many('scanning.ct', 'user_ide', string="CT")
    audiology_report_reg_ids = fields.One2many('audiology.ref', 'user_ide', string="Audiology")
    xray_report_reg_ids = fields.One2many('scanning.x.ray', 'user_ide', string="X Ray")

    bystander_name = fields.Char(string="Bystander Name")
    bystander_mobile = fields.Char(string="Bystander Mobile No")
    bystander_relation = fields.Char(string="Relation")
    bystander_email = fields.Char(string="Email ID")
    room_category = fields.Many2one('room.category', string='Room Category')
    room_category_new = fields.Many2one('hospital.room.type', string='Room Category')
    room_id = fields.Many2one('hospital.room', string="Room")

    bed_id = fields.Many2one('hospital.bed', string="Bed", )
    advance_amount = fields.Integer(string='Per Day')
    # bed_id = fields.Many2one('hospital.bed', string='Bed')
    nurse_charge = fields.Float(string='Nursing Charge')
    doctor_visiting_charge = fields.Float("Doctor Charge")
    service_charge = fields.Float("Service Charge")
    alternate_no = fields.Char(string='Alternate Number')
    no_days = fields.Integer(string='Number Of Days', compute='_compute_no_days', store=True)
    admitted_date = fields.Date(string='Admitted Date')
    temp_admitted_date = fields.Datetime(string='Admitted Date')
    admission_boolean = fields.Boolean(default=False)
    dob = fields.Date(string='DOB')
    discharge_date = fields.Datetime(string='Discharge Date')
    temp_discharge_date = fields.Datetime(string='Discharge Date')
    vssc_boolean = fields.Boolean(string='VSSC', default=False)
    consultation_check = fields.Boolean(default=False)
    temp_reference_no = fields.Char(string=" Temporary Reference")
    no_consultation = fields.Boolean(default=True)
    walk_in = fields.Boolean(default=False)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    block = fields.Many2one('block', string='Floor')
    new_block = fields.Many2one('hospital.block', string='Floor')
    room_number_new = fields.Many2one('hospital.room', string="Room")
    room_number = fields.Char(string="Room")
    room_transfer_date = fields.Datetime(string="Transfer Date")
    transferred_block = fields.Many2one('block', string='Floor')
    transferred_room_category = fields.Many2one('room.category', string='Room Category')
    transferred_room_number = fields.Integer(string='Room No')
    transferred_bed_number = fields.Integer(string='Bed Number')
    amount_in_advance = fields.Integer(string="Advance Amount")
    advance_mode_payment = fields.Selection([('cash', 'Cash'),
                                             ('credit', 'Credit'),
                                             ('card', 'Card'),
                                             ('cheque', 'Cheque'),
                                             ('upi', 'Mobile Pay'), ], string='Payment Method', default='cash')
    admit_payment_method_split = fields.Boolean(string="Split Payment")
    admit_cash_amount = fields.Float(string="Cash Amount")
    admit_upi_amount = fields.Float(string="UPI Amount")
    admit_card_amount = fields.Float(string="Card Amount")
    advance_remark = fields.Text(string="Remarks")
    advance_date = fields.Datetime(string="Date")
    admission_total_amount = fields.Integer(string="Total Amount", compute='_compute_total_unpaid_amount', compute_sudo=True)
    temp_admission_total_amount = fields.Integer("Total Amount")
    admission_amount_paid = fields.Integer(string="Amount Paid")
    admission_balance = fields.Integer(string="Balance")
    Staff_name = fields.Many2one('hr.employee', "Staff Name",default=lambda self: self._default_staff())
    staff_password = fields.Char("Password")
    admit_card_no = fields.Char(string="Card No")
    admit_bank = fields.Char(string="Bank")
    rent_half = fields.Char('Rent Half Day')
    rent_full = fields.Char('Rent Full Day')
    status = fields.Selection(
        [('unpaid', 'Unpaid'), ('paid', 'Paid'), ('cancelled', 'Cancelled'),  ('proceed_admit', 'Proceed to Admit'), ('admitted', 'Admitted'),
         ('proceed_discharge', 'Proceed to Discharge'), ('discharged', 'Discharged')], default='unpaid')

    unpaid_general_ids = fields.One2many('general.billing', compute='_compute_all_totals', string="Unpaid General", compute_sudo=True)
    # unpaid_lab_ids = fields.One2many('doctor.lab.report', compute='_compute_unpaid_lab', string="Unpaid Lab")
    # unpaid_pharmacy_ids = fields.One2many('pharmacy.description', compute='_compute_unpaid_pharmacy',
    #                                       string="Unpaid Pharmacy")

    paid_general_ids = fields.One2many('general.billing', 'mrd_no', string='Paid Bills',
                                       compute='_compute_all_totals', compute_sudo=True)
    # unpaid_general_ids = fields.One2many('general.billing', 'mrd_no', string='Unpaid Bills',
    #                                      compute='_compute_unpaid_general')
    paid_lab_ids = fields.One2many(
        'doctor.lab.report', 'user_ide', string="Paid Lab Bills", compute='_compute_all_totals', store=False, compute_sudo=True)

    unpaid_lab_ids = fields.One2many(
        'doctor.lab.report', 'user_ide', string="Unpaid Lab Bills", compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_lab_total = fields.Float(string="Paid Lab Total", compute='_compute_all_totals', store=False, compute_sudo=True)
    unpaid_lab_total = fields.Float(string="Unpaid Lab Total", compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_total = fields.Float(string="Total Paid", compute="_compute_all_totals", store=True, compute_sudo=True)
    unpaid_total = fields.Float(string="Total Unpaid", compute="_compute_all_totals", store=True, compute_sudo=True)
    grant_total = fields.Float(string="Grand Total", compute="_compute_all_totals", store=True, compute_sudo=True)
    room_rent = fields.Float(string="Room Rent", compute="_compute_total_unpaid_amount", compute_sudo=True)
    paid_room_rent = fields.Float(string="Paid Room Rent", store=True)
    register_bool = fields.Boolean(default=False)
    unpaid_pharmacy_ids = fields.One2many(
        'pharmacy.description', 'uhid_id', string="Unpaid Pharmacy Bills", compute='_compute_all_totals',
        store=False, compute_sudo=True)

    paid_pharmacy_ids = fields.One2many(
        'pharmacy.description', 'uhid_id', string="Paid Pharmacy Bills", compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_ip_ids = fields.Many2many(
        'ip.part.billing', string="Paid IP Bills", compute="_compute_all_totals", compute_sudo=True
    )
    unpaid_ip_ids = fields.Many2many(
        'ip.part.billing', string="Unpaid IP Bills", compute="_compute_all_totals", compute_sudo=True
    )
    referred = fields.Boolean('Referred')
    tt = fields.Boolean('TT')
    walk_in_patient = fields.Boolean('Walk-in patient')
    discount = fields.Integer('Discount')
    insurance_name = fields.Many2one('insurance.model', string='Insurance')
    admission_visibilty_boolean = fields.Boolean(default=False, string='View Details')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type")


    time_new = fields.Char(
        string='Time',
        default=lambda self: self._get_indian_time()
    )


    def _get_indian_time(self):
        india = pytz.timezone('Asia/Kolkata')
        now = datetime.now(india)
        return now.strftime('%I:%M %p')

    def write(self, vals):
        if self.env.context.get('no_sync'):
            return super(PatientRegistration, self).write(vals)

        employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.env.uid)], limit=1)
        if employee:
            for rec in self:
                if not rec.Staff_name and not vals.get('Staff_name'):
                    vals['Staff_name'] = employee.id
                if not rec.register_staff_name and not vals.get('register_staff_name'):
                    vals['register_staff_name'] = employee.id

        # Removed internal doctor/doc_name sync to keep OP and IP doctors separate as requested.
        
        res = super(PatientRegistration, self).write(vals)

        # ── Sync patient details (name/phone/age/address/gender) to all dept records ──
        patient_detail_fields = {'patient_id', 'phone_number', 'age', 'address', 'gender'}
        if patient_detail_fields & set(vals.keys()):
            for rec in self:
                # 1. Build sync dicts for different models
                
                # Scan models (mri, ct, xray, audiology) use register_ prefix
                scan_sync = {}
                if 'patient_id' in vals: scan_sync['register_patient_name'] = rec.patient_id
                if 'phone_number' in vals: scan_sync['register_phone_number'] = rec.phone_number
                if 'age' in vals: scan_sync['register_age'] = rec.age
                if 'address' in vals: scan_sync['register_address'] = rec.address
                # Note: scan models don't seem to have gender fields in many cases, but we verify later
                
                # Pharmacy uses name and phone_number
                pharmacy_sync = {}
                if 'patient_id' in vals: pharmacy_sync['name'] = rec.patient_id
                if 'phone_number' in vals: pharmacy_sync['phone_number'] = rec.phone_number
                
                # Lab Report uses patient_name, patient_phone, age, gender
                lab_sync = {}
                if 'patient_id' in vals: lab_sync['patient_name'] = rec.patient_id
                if 'phone_number' in vals: lab_sync['patient_phone'] = rec.phone_number
                if 'age' in vals: lab_sync['age'] = rec.age
                if 'gender' in vals: lab_sync['gender'] = rec.gender
                
                # General Billing and IP Part Billing use patient_name, age, gender, mobile
                billing_sync = {}
                if 'patient_id' in vals: billing_sync['patient_name'] = rec.patient_id
                if 'age' in vals: billing_sync['age'] = rec.age
                if 'gender' in vals: billing_sync['gender'] = rec.gender
                if 'phone_number' in vals: billing_sync['mobile'] = rec.phone_number
                
                # Casualty uses patient_id, address, age, phone_number, gender
                casualty_sync = {}
                if 'patient_id' in vals: casualty_sync['patient_id'] = rec.patient_id
                if 'address' in vals: casualty_sync['address'] = rec.address
                if 'age' in vals: casualty_sync['age'] = str(rec.age) # age is Char in casualty
                if 'phone_number' in vals: casualty_sync['phone_number'] = rec.phone_number
                if 'gender' in vals: casualty_sync['gender'] = rec.gender

                # 2. Apply updates to models (linked via rec.id)
                sync_configs = [
                    ('pharmacy.description', 'uhid_id', pharmacy_sync),
                    ('doctor.lab.report', 'user_ide', lab_sync),
                    ('general.billing', 'mrd_no', billing_sync),
                    ('ip.part.billing', 'mrd_no', billing_sync),
                    ('casualty.reg', 'user_ide', casualty_sync),
                    ('lab.result.page', 'patient_re_id_name', lab_sync),
                    ('scanning.mri', 'user_ide', scan_sync),
                    ('scanning.ct', 'user_ide', scan_sync),
                    ('scanning.x.ray', 'user_ide', scan_sync),
                    ('audiology.ref', 'user_ide', scan_sync),
                    ('ot.billing', 'mrd_no', billing_sync),
                    ('audiology.billing', 'mrd_no', billing_sync),
                    ('xray.billing', 'mrd_no', billing_sync),
                    ('casuality.billing', 'mrd_no', billing_sync),
                    ('discharge.billing', 'mrd_no', billing_sync),
                    ('patient.wallet', 'uhid', lab_sync),
                ]
                
                for model_name, link_field, sync_vals in sync_configs:
                    if sync_vals:
                        try:
                            # Search for records linked to this patient
                            recs = self.env[model_name].sudo().search([
                                (link_field, '=', rec.id)
                            ])
                            if recs:
                                # Filter sync_vals to only include fields that exist in the target model
                                model_fields = self.env[model_name]._fields
                                filtered_sync_vals = {k: v for k, v in sync_vals.items() if k in model_fields}
                                
                                if filtered_sync_vals:
                                    recs.with_context(no_sync=True).write(filtered_sync_vals)
                        except Exception:
                            pass

        if 'doctor' in vals or 'doc_name' in vals or 'department_id' in vals:
            for rec in self:
                # 0. Sync Consultation records (OP ONLY)
                if 'doc_name' in vals:
                    new_op_doc = vals.get('doc_name')
                    if new_op_doc:
                        # Consultation records link back via patient_id or user_id
                        # Only update today's consultations to prevent overwriting history
                        op_consultations = self.env['patient.registration'].sudo().search([
                            ('user_id', '=', rec.id),
                            ('date', '=', date.today())
                        ])
                        if op_consultations:
                            op_consultations.write({'doctor': new_op_doc})

                # 1. Update active admission doctor if patient is admitted (IP ONLY)
                if rec.status == 'admitted' and 'doctor' in vals:
                    new_ip_doc = vals.get('doctor')
                    admitted_patient = self.env['hospital.admitted.patient'].search([
                        ('patient_id', '=', rec.id),
                        ('status', '=', 'admitted')
                    ], limit=1)
                    if admitted_patient and new_ip_doc:
                        old_doctor_id = admitted_patient.attending_doctor.id
                        write_vals = {
                            'attending_doctor': new_ip_doc,
                            'visited_doctor_ids': [(4, new_ip_doc)],
                        }
                        if old_doctor_id:
                            write_vals['visited_doctor_ids'].append((4, old_doctor_id))
                        admitted_patient.write(write_vals)

                # 2. Synchronize billing models (Context-aware: IP doc to IP bills, OP doc to OP bills)
                if rec.status != 'discharged':
                    print(f"DEBUG: Starting Billing Sync for Patient {rec.reference_no} (Status: {rec.status})")
                    billing_models = [
                        ('pharmacy.description', 'uhid_id', 'date'),
                        ('general.billing', 'mrd_no', 'bill_date'),
                        ('ip.part.billing', 'mrd_no', 'bill_date'),
                        ('doctor.lab.report', 'user_ide', 'date'),
                        ('scanning.ct', 'user_ide', 'scan_registered_date'),
                        ('scanning.mri', 'user_ide', 'scan_registered_date'),
                        ('scanning.x.ray', 'user_ide', 'scan_registered_date'),
                        ('audiology.ref', 'user_ide', 'scan_registered_date'),
                        ('casualty.reg', 'user_ide', 'date'),
                        ('ot.billing', 'mrd_no', 'bill_date'),
                        ('casuality.billing', 'mrd_no', 'bill_date'),
                        ('audiology.billing', 'mrd_no', 'bill_date'),
                        ('xray.billing', 'mrd_no', 'bill_date'),
                        ('lab.result.page', 'patient_re_id_name', 'date'),
                        ('discharge.billing', 'mrd_no', 'bill_date'),
                    ]
                    
                    # Session start for filtering
                    ip_session_start = False
                    if rec.admitted_date:
                        ip_session_start = rec.admitted_date
                    
                    op_session_start = date.today()

                    # Prepare department sync
                    target_general_dept_id = False
                    if 'department_id' in vals:
                        new_dept_reg = self.env['doctor.department'].browse(vals['department_id'])
                        target_dept = self.env['general.department'].sudo().search([
                            '|', ('department_name', '=', new_dept_reg.department),
                            ('code', '=', new_dept_reg.code)
                        ], limit=1)
                        if target_dept:
                            target_general_dept_id = target_dept.id

                    for model_name, patient_field, date_field in billing_models:
                        try:
                            # Direct search to find all potentially relevant records
                            records = self.env[model_name].sudo().search([(patient_field, '=', rec.id)])
                            for record in records:
                                update_doc_id = False
                                
                                # Date Check
                                r_date = record[date_field]
                                if isinstance(r_date, datetime):
                                    r_date = r_date.date()

                                # Strict Context Identification
                                is_ip_bill = False
                                r_bill_type = record.bill_type if 'bill_type' in record._fields else False
                                r_op_cat = record.op_category if 'op_category' in record._fields else False
                                
                                if r_bill_type in ['admitted', 'ip'] or r_op_cat in ['admitted', 'ip']:
                                    is_ip_bill = True
                                
                                # Filtering logic: Only update records from the current session
                                if is_ip_bill:
                                    if ip_session_start and r_date and r_date < ip_session_start:
                                        continue # Skip old IP records
                                else:
                                    if op_session_start and r_date and r_date < op_session_start:
                                        continue # Skip old OP records

                                # Apply IP doctor change ONLY to IP bills
                                if is_ip_bill and 'doctor' in vals:
                                    update_doc_id = vals.get('doctor')
                                # Apply OP doctor change ONLY to OP bills
                                elif not is_ip_bill and 'doc_name' in vals:
                                    update_doc_id = vals.get('doc_name')

                                if update_doc_id:
                                    if model_name == 'ot.billing':
                                        continue

                                    # Trigger recomputation
                                    for method_name in ['_compute_doctor_name', '_compute_doctor_name_ip', '_compute_doctor_id', '_compute_doctor']:
                                        if hasattr(record, method_name):
                                            getattr(record, method_name)()
                                    
                                    # Force direct write
                                    doc_f = 'doctor' if 'doctor' in record._fields else ('doctor_id' if 'doctor_id' in record._fields else ('doctor_name' if 'doctor_name' in record._fields else False))
                                    if doc_f:
                                        record.write({doc_f: update_doc_id})

                                # Update Department (Specific to general billing models)
                                if target_general_dept_id and model_name in ['general.billing', 'ip.part.billing', 'ot.billing', 'casuality.billing', 'audiology.billing', 'xray.billing']:
                                    if 'department' in record._fields:
                                        record.write({'department': target_general_dept_id})

                        except Exception:
                            continue
        return res

    def patient_challan_new(self):
        return self.env.ref('homeo_doctor.patient_challan_report').report_action(self)
    def patient_challan_new_normal(self):
        return self.env.ref('homeo_doctor.report_patient_challan_action').report_action(self)


    def patient_advance_challan_new(self):
        return self.env.ref('homeo_doctor.patient_challan_advance_report').report_action(self)

    def get_grouped_general_lines(self):
        grouped = defaultdict(lambda: {'quantity': 0, 'total_amt': 0})
        for line in self.unpaid_general_ids.mapped('general_bill_line_ids'):
            key = line.particulars.display_name
            grouped[key]['quantity'] += line.quantity or 0
            grouped[key]['total_amt'] += line.total_amt or 0
        return [{'name': k, 'quantity': v['quantity'], 'total_amt': v['total_amt']}
                for k, v in grouped.items()]

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.register_mode_payment = 'credit'
                rec.status = 'unpaid'

    def consolidated_bill(self):
        self.action_discharged_patient_reg()
        return self.env.ref('homeo_doctor.action_report_consolidated_discharge_challan').report_action(self)

    @api.onchange('insurance_name')
    def _onchange_insurance_id(self):
        for rec in self:
            if rec.insurance_name:
                rec.advance_mode_payment = 'credit'

    @api.onchange('referred', 'tt','walk_in_patient')
    def _onchange_refferd_boolean_and_tt(self):
        for rec in self:
            if rec.referred or rec.tt or rec.walk_in_patient:
                rec.consultation_fee = 0.0
                fee = self.env['patient.registration.fee'].search([('fee', '=', 100)], limit=1)
                if fee:
                    rec.registration_fee = fee.id
                else:
                    rec.registration_fee = self._default_registration_fee()

            if rec.walk_in_patient:
                walkin_doctor = self.env['doctor.profile'].search(
                    [('name', '=', 'Walk-in Patient')], limit=1
                )
                if walkin_doctor:
                    rec.doc_name = walkin_doctor.id

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
            'domain': [('patient_id', '=', self.reference_no)],
            'context': {'default_patient_id': self.reference_no},
            'target': 'new',
        }

    def cancel_appointment(self):

        """Cancel the appointment and only the specific related patient registration record"""

        self.status = "cancelled"

        # Find only the specific related patient.registration record for this appointment

        # by matching both user_id and patient_id with the current record's id

        related_registration = self.env['patient.registration'].search([

            ('user_id', '=', self.id),

            ('patient_id', '=', self.id),

            ('status', 'in', ['confirmed', 'completed'])

        ], limit=1)

        if related_registration:
            related_registration.write({'status': 'cancelled'})

    # @api.depends('reference_no')
    # def _compute_unpaid_general(self):
    #     for rec in self:
    #         rec.unpaid_general_ids = self.env['general.billing'].search([
    #             ('mrd_no', '=', rec.id),
    #             ('status', '!=', 'paid')
    #         ])
    @api.depends('reference_no', 'admitted_date', 'vssc_boolean')
    def _compute_all_totals(self):
        today = fields.Date.today()
        # print(today, 'todaytodaytodaytodaytodaytodaytodaytodaytodaytodaytodaytodaytodaytodaytoday')
        for rec in self:
            # Initialize
            rec.paid_total = 0.0
            rec.unpaid_total = 0.0
            rec.grant_total = 0.0
            rec.paid_lab_total = 0.0
            rec.unpaid_lab_total = 0.0
            paid_general = 0.0
            unpaid_general = 0.0
            today = fields.Date.today()
            # -----------------------------
            # General Billing
            # -----------------------------
            end_date = rec.discharge_date or fields.Date.today()
            if rec.admitted_date:
                today = fields.Date.today()

                paid_general = self.env['general.billing'].search([
                    ('mrd_no', '=', rec.id),
                    ('status', '=', 'paid'),
                    ('bill_date', '>=', rec.admitted_date),
                    ('bill_date', '<=',end_date),
                    # ('bill_date', '<=', fields.Date.today()),
                ])
                unpaid_general = self.env['general.billing'].search([
                    ('mrd_no', '=', rec.id),
                    ('status', '!=', 'paid'),
                    ('bill_date', '>=', rec.admitted_date),
                    ('bill_date', '<=', end_date),
                    # ('bill_date', '<=', fields.Date.today()),
                ])
                rec.paid_general_ids = paid_general
                rec.unpaid_general_ids = unpaid_general

            # -----------------------------
            # Pharmacy Billing
            # -----------------------------
            paid_pharmacy = self.env['pharmacy.description'].search([
                ('uhid_id', '=', rec.id),
                ('status', '=', 'paid'),
                ('date', '>=', rec.admitted_date),
                ('date', '<=', end_date),
                # ('date', '<=', today),
            ])
            unpaid_pharmacy = self.env['pharmacy.description'].search([
                ('uhid_id', '=', rec.id),
                ('status', '=', 'unpaid'),
                ('date', '>=', rec.admitted_date),
                ('date', '<=', end_date),
                # ('date', '<=', today),
            ])
            rec.paid_pharmacy_ids = paid_pharmacy
            rec.unpaid_pharmacy_ids = unpaid_pharmacy
            paid_ip = self.env['ip.part.billing'].search([
                ('mrd_no', '=', rec.id),
                ('status', '=', 'paid'),
                ('bill_date', '>=', rec.admitted_date),
                ('bill_date', '<=', end_date),
                # ('bill_date', '<=', today),
            ])
            unpaid_ip = self.env['ip.part.billing'].search([
                ('mrd_no', '=', rec.id),
                ('status', '=', 'unpaid'),
                ('bill_date', '>=', rec.admitted_date),
                ('bill_date', '<=', end_date),
                # ('bill_date', '<=', today),
            ])
            rec.paid_ip_ids = paid_ip
            rec.unpaid_ip_ids = unpaid_ip
            # -----------------------------
            # Lab Billing (Both Paid & Unpaid)
            # -----------------------------
            paid_lab = self.env['doctor.lab.report'].search([
                ('user_ide', '=', rec.id),
                ('status', '=', 'paid'),
                ('date', '>=', rec.admitted_date),
                ('date', '<=', end_date),
                # ('date', '<=', today),
            ])
            if not rec.vssc_boolean:
                unpaid_lab = self.env['doctor.lab.report'].search([
                    ('user_ide', '=', rec.id),
                    ('status', '=', 'unpaid'),
                    ('mode_of_payment', '=', 'credit'),
                    ('date', '>=', rec.admitted_date),
                    ('date', '<=', end_date),
                    # ('date', '<=', today),
                ])
            else:
                unpaid_lab = self.env['doctor.lab.report'].search([
                    ('user_ide', '=', rec.id),
                    '|',
                    ('status', '!=', 'paid'),
                    '&',
                    ('status', '=', 'paid'),
                    ('mode_of_payment', '=', 'credit'),
                    ('status', '!=', 'credit'),
                    ('date', '>=', rec.admitted_date),
                    ('date', '<=', end_date),
                    # ('date', '<=', today),
                ])

            rec.paid_lab_ids = paid_lab
            rec.unpaid_lab_ids = unpaid_lab
            rec.paid_lab_total = sum(l.total_bill_amount for l in paid_lab)
            rec.unpaid_lab_total = sum(l.total_bill_amount for l in unpaid_lab)

            # -----------------------------
            # Totals
            # -----------------------------
            rec.paid_total = (
                    sum(p.total_amount or 0.0 for p in rec.paid_general_ids) +
                    sum(p.total_amount or 0.0 for p in rec.paid_pharmacy_ids) +
                    sum(p.total_amount or 0.0 for p in rec.paid_ip_ids) -
                    sum(p.room_rent_total or 0.0 for p in rec.paid_ip_ids) +
                    rec.paid_lab_total
            )

            rec.unpaid_total = (
                    sum(u.total_amount or 0.0 for u in rec.unpaid_general_ids) +
                    sum(u.total_amount or 0.0 for u in rec.unpaid_pharmacy_ids) +
                    sum(u.total_amount or 0.0 for u in rec.unpaid_ip_ids) +
                    rec.unpaid_lab_total
            )

            rec.grant_total = rec.paid_total + rec.unpaid_total + (rec.room_rent or 0.0)
            rec.paid_room_rent = sum(p.room_rent_total or 0.0 for p in rec.paid_ip_ids)

    # @api.depends('reference_no')
    # def _compute_unpaid_general(self):
    #     for rec in self:
    #         rec.paid_general_ids = False
    #         rec.unpaid_general_ids = False
    #         rec.paid_total = 0.0
    #         rec.unpaid_total = 0.0
    #         rec.grant_total = 0.0
    #
    #         if rec.admitted_date:
    #             today = fields.Date.today()
    #
    #             paid_bills = self.env['general.billing'].search([
    #                 ('mrd_no', '=', rec.id),
    #                 ('status', '=', 'paid'),
    #                 ('bill_date', '>=', rec.admitted_date),
    #                 ('bill_date', '<=', today),
    #             ])
    #
    #             unpaid_bills = self.env['general.billing'].search([
    #                 ('mrd_no', '=', rec.id),
    #                 ('status', '!=', 'paid'),
    #                 ('bill_date', '>=', rec.admitted_date),
    #                 ('bill_date', '<=', today),
    #             ])
    #
    #             rec.paid_general_ids = paid_bills
    #             rec.unpaid_general_ids = unpaid_bills
    #
    #             rec.paid_total = sum(p.total_amount for p in paid_bills)
    #             rec.unpaid_total = sum(u.total_amount for u in unpaid_bills)
    #             rec.grant_total= rec.grant_total = rec.paid_total + rec.unpaid_total + rec.room_rent

    @api.depends('reference_no', 'vssc_boolean')
    def _compute_unpaid_lab(self):
        for rec in self:
            # base_domain = [('user_ide', '=', rec.id)]

            if not rec.vssc_boolean:
                # Show only status unpaid and paid
                # print("vssc boolean not")
                status_domain = [
                    ('user_ide', '=', rec.id),
                    ('status', '=', 'unpaid'),
                    ('mode_of_payment', '=', 'credit'),
                ]
            else:
                # print("vssc boolean yes")
                # Show only unpaid (including credit payments that are not credited)
                status_domain = [
                    ('user_ide', '=', rec.id),
                    '|',
                    ('status', '!=', 'paid'),
                    '&',
                    ('status', '=', 'paid'),
                    ('mode_of_payment', '=', 'credit'),
                    ('status', '!=', 'credit')
                ]

            final_domain = status_domain
            rec.unpaid_lab_ids = self.env['doctor.lab.report'].search(final_domain)

    register_total_amount = fields.Integer(string="Total Amount", compute="_compute_register_total")
    register_amount_paid = fields.Integer(string="Amount Paid")
    register_balance = fields.Integer(string="Balance")
    register_staff_name = fields.Many2one('hr.employee', "Staff Name", default=lambda self: self._default_staff())
    register_staff_password = fields.Char("Password")
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


    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    # @api.onchange('doctor_visiting_charge','service_charge','nurse_charge')
    # def charges_add(self):
    #     for rec in self:
    #         rec.admission_total_amount = rec.admission_total_amount + rec.doctor_visiting_charge + rec.service_charge + rec.nurse_charge
    @api.onchange('nurse_charge', 'doctor_visiting_charge', 'service_charge')
    def _onchange_charges(self):
        """Calculate total amount when charge fields change"""
        # Manually trigger the computation for immediate UI feedback
        self._compute_total_unpaid_amount()

    def admit_reception(self):
        self.admission_boolean = True
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)

        if employee:
            self.Staff_name = employee.id

        self.status = 'proceed_admit'
        self.admitted_date = fields.Datetime.now()
        self.bill_type = 'admitted'

    @api.onchange('register_amount_paid')
    def _onchange_register_amount_paid(self):
        for rec in self:
            total = rec.register_total_amount
            paid = rec.register_amount_paid
            if (paid < total and paid > 0):
                rec.register_balance = total - paid
            elif (paid > total and paid > 0):
                rec.register_balance = paid - total
            else:
                rec.register_balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount', 'payment_method_split')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.register_total_amount or 0.0

            rec.register_amount_paid = int(cash + upi + card)
            rec.register_balance = int(total - (cash + upi + card))


    @api.depends('vssc_boolean', 'doc_name')
    def _compute_consultation_fee(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.consultation_fee = 400
            else:
                # You might want to add your logic here for non-VSSC patients
                # For now, I'm leaving it as is (presumably set by another method)
                rec.consultation_fee = 0  # or whatever default you want

    @api.depends('vssc_boolean')
    def _default_registration_fee(self):
        # Return false/None if VSSC, otherwise return your default registration fee
        if self.vssc_boolean:
            return False
        else:
            # Return your default registration fee record
            registration_fee = self.env['patient.registration.fee'].search([], limit=1)
            return registration_fee.id if registration_fee else False

    @api.onchange('vssc_boolean')
    def _onchange_vssc_boolean(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.registration_fee = False  # Set to None/False when VSSC is True
                rec.consultation_fee = 400
            else:
                # Reset to default registration fee
                default_fee = self._default_registration_fee()
                rec.registration_fee = default_fee
                # Reset consultation fee if needed
                # rec.consultation_fee = 0  # or compute based on your business logic

    @api.onchange('registration_fee', 'consultation_fee', 'vssc_boolean')
    def _onchange_total_amount(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.register_total_amount = 400  # Only consultation fee for VSSC
            else:
                reg_fee = rec.registration_fee.fee if rec.registration_fee else 0
                rec.register_total_amount = reg_fee + (rec.consultation_fee or 0)

    @api.depends('registration_fee', 'consultation_fee', 'vssc_boolean')
    def _compute_register_total(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.register_total_amount = 400  # Only consultation fee for VSSC
            else:
                reg_fee = rec.registration_fee.fee if rec.registration_fee else 0
                rec.register_total_amount = reg_fee + (rec.consultation_fee or 0)

    # @api.depends('reference_no', 'admitted_date')
    # def _compute_unpaid_pharmacy(self):
    #     today = fields.Date.today()
    #     unpaid_total=0
    #     for rec in self:
    #         domain = [
    #             ('uhid_id', '=', rec.id),
    #             ('status', '=', 'unpaid'),
    #         ]
    #         if rec.admitted_date:
    #             domain.append(('date', '>=', rec.admitted_date))
    #             domain.append(('date', '<=', today))
    #
    #         rec.unpaid_pharmacy_ids = self.env['pharmacy.description'].search(domain)
    #         rec.grant_total += sum(line.total_amount for line in rec.unpaid_pharmacy_ids)
    #         rec.unpaid_total += sum(u.total_amount for u in  rec.unpaid_pharmacy_ids)
    #
    # @api.depends('reference_no', 'admitted_date')
    # def _compute_paid_pharmacy(self):
    #     today = fields.Date.today()
    #     paid_total=0
    #     for rec in self:
    #         domain = [
    #             ('uhid_id', '=', rec.id),
    #             ('status', '=', 'paid'),
    #         ]
    #         if rec.admitted_date:
    #             domain.append(('date', '>=', rec.admitted_date))
    #             domain.append(('date', '<=', today))
    #
    #         rec.paid_pharmacy_ids = self.env['pharmacy.description'].search(domain)
    #         rec.grant_total += sum(line.total_amount for line in rec.paid_pharmacy_ids)
    #         rec.paid_total += sum(p.total_amount for p in rec.paid_pharmacy_ids)
    #         print(rec.paid_total,'paid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_totalpaid_total.................')

    @api.depends('unpaid_general_ids', 'unpaid_lab_ids', 'unpaid_pharmacy_ids', 'admitted_date', 'discharge_date',
                 'rent_half', 'rent_full')
    def _compute_total_unpaid_amount(self):
        for rec in self:
            total = 0.0
            full_days = 0
            rent_full_value = 0
            remaining_hours = 0
            # Calculate service totals
            for general in rec.unpaid_general_ids:
                total += general.total_amount or 0.0

            for lab in rec.unpaid_lab_ids:
                total += lab.total_bill_amount or 0.0

            for pharmacy in rec.unpaid_pharmacy_ids:
                total += pharmacy.total_amount or 0.0

            # Calculate rent if discharge date is present
            rent_half_value = 0.0
            if rec.admitted_date and rec.discharge_date:
                # admitted_date is Date, discharge_date is Datetime — normalize both
                admitted = rec.admitted_date
                discharge = rec.discharge_date
                if isinstance(admitted, str):
                    admitted = fields.Datetime.from_string(admitted)
                elif isinstance(admitted, date) and not isinstance(admitted, datetime):
                    admitted = datetime.combine(admitted, datetime.min.time())
                if isinstance(discharge, str):
                    discharge = fields.Datetime.from_string(discharge)
                elif isinstance(discharge, date) and not isinstance(discharge, datetime):
                    discharge = datetime.combine(discharge, datetime.min.time())

                # Calculate the duration in days (including partial days)
                duration_hours = (discharge - admitted).total_seconds() / 3600

                # Calculate full days and remaining hours
                full_days = int(duration_hours / 24)
                remaining_hours = duration_hours % 24

                # Add full day rent - convert Char field to float for calculation
                rent_full_value = float(rec.rent_full or 0) if rec.rent_full and rec.rent_full.strip() else 0
                total += full_days * rent_full_value - (rec.paid_room_rent)

                # Add half day rent if remaining hours > 0
                if remaining_hours > 0:
                    rent_half_value = float(rec.rent_half or 0) if rec.rent_half and rec.rent_half.strip() else 0
                    total += rent_half_value

            total += (rec.nurse_charge or 0) + (rec.doctor_visiting_charge or 0) + (rec.service_charge or 0)
            if rec.discount and rec.discount > 0:
                total -= rec.discount

                # Prevent negative totals
            if rec.amount_in_advance > 0:
                final_amount = total - rec.amount_in_advance
                # Prevent negative final amount
                final_amount = final_amount
            else:
                final_amount = total

            # Assign to record
            rec.admission_total_amount = final_amount
            rec.room_rent = full_days * rent_full_value + (rent_half_value if remaining_hours > 0 else 0.0)

    discharge_bill_number = fields.Char(
        string="Discharge Bill #",
        readonly=True,
        copy=False,
        default='/'
    )

    def action_discharged_patient_reg(self):
        if self.Staff_name and self.staff_password:
            employee = self.Staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_password != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'discharged'
            # record.admission_boolean = False
            record.temp_admission_total_amount = record.admission_total_amount
            record.temp_admitted_date = record.admitted_date
            record.temp_discharge_date = record.discharge_date

            # Mark the room as available
            if record.room_number_new:
                record.room_number_new.is_available = False

            admitted_patient = self.env['hospital.admitted.patient'].search([('patient_id', '=', record.id)], limit=1)
            if not record.discharge_bill_number or record.discharge_bill_number == '/':
                # a) grab next sequence (must exist in Settings → Technical → Sequences)
                raw_seq = self.env['ir.sequence'].next_by_code('discharge.bill') or '0'
                padded_seq = str(raw_seq).zfill(4)

                # b) compute fiscal year suffix: e.g. if today is July 2025 ⇒ "25-26"
                # today = date.today()
                today = fields.Date.context_today(self)
                year_start = today.year % 100
                year_end = (today.year + 1) % 100
                fiscal_suffix = f"{year_start:02d}-{year_end:02d}"

                # c) assign it
                record.discharge_bill_number = f"{padded_seq}/{fiscal_suffix}"

                #james

                today = date.today()

                # # Indian Fiscal Year calculation (April 1 – March 31)
                # if today.month >= 4:  # April–December
                #     start_year = today.year
                #     end_year = today.year + 1
                # else:  # January–March
                #     start_year = today.year - 1
                #     end_year = today.year
                #
                # fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"
                #
                # # assign it
                # record.discharge_bill_number = f"{padded_seq}/{fiscal_suffix}"

            if admitted_patient:
                admitted_patient.status = 'discharged'
                self.env['discharged.patient.record'].create({
                    'patient_id': record.reference_no,
                    'name': record.patient_id,
                    'discharge_date': record.discharge_date,
                    'admitted_date': record.admitted_date,
                    'room_number': record.room_number_new.id,
                    'doctor': record.doctor.id,
                    'total_amount': record.admission_total_amount,
                    'room_category_new': record.room_category_new.id,
                    'new_block': record.new_block.id,
                    'bed_id': record.bed_id.id,
                    'amount_in_advance': record.amount_in_advance,
                    'bystander_name': record.bystander_name,
                    'relation': record.bystander_relation,
                    'email': record.bystander_email,
                    'bystander_mobile': record.bystander_mobile,
                    'alternate_no': record.alternate_no,
                    'op_category': record.op_category.id,
                    'pay_mode': record.advance_mode_payment,

                })
                # record.unpaid_general_ids.write({'status': 'paid'})
                # if record.vssc_boolean:
                #     record.unpaid_lab_ids.write({'status': 'credit'})
                #     record.paid_lab_ids.write({'status': 'credit'})
                # else:
                #     record.unpaid_lab_ids.write({'status': 'paid'})
                # record.unpaid_pharmacy_ids.write({'status': 'paid'})
        return self.env.ref('homeo_doctor.action_report_discharge_challan').report_action(self)

    def finalize_discharge_cleanup(self):
        for record in self:
            record.unpaid_general_ids.write({'status': 'paid'})
            if record.vssc_boolean:
                record.unpaid_lab_ids.write({'status': 'credit'})
                record.paid_lab_ids.write({'status': 'credit'})
                record.audiology_report_reg_ids.write({'status': 'paid'})
                record.xray_report_reg_ids.write({'status': 'paid'})
            else:
                record.unpaid_lab_ids.write({'status': 'paid'})
                record.audiology_report_reg_ids.write({'status': 'paid'})
                record.xray_report_reg_ids.write({'status': 'paid'})
            record.unpaid_pharmacy_ids.write({'status': 'paid'})
            record.admission_boolean = False
            record.update({
                'room_number_new': False,
                'bed_id': False,
                'admitted_date': False,
                'discharge_date': False,
                'room_category_new': False,
                'bystander_name': False,
                'bystander_mobile': False,
                'bystander_relation': False,
                'bystander_email': False,
                'rent_full': False,
                'rent_half': False,
                'Staff_name': False,
                'staff_password': False,

            })

        return

    @api.onchange('room_category_new')
    def _onchange_room_category_new(self):
        if self.room_category_new:
            # Filter rooms by the selected room category
            return {
                'domain': {
                    'room_number_new': [('room_type_new', '=', self.room_category_new.id), ('is_available', '=', False)]
                }
            }
        return {'domain': {'room_number_new': []}}

    @api.onchange('room_number_new')
    def _onchange_room_number(self):
        if self.room_number_new:
            self.bed_id = self.room_number_new.bed_number_new
            self.new_block = self.room_number_new.block_new
            self.rent_half = self.room_number_new.rent_half
            self.rent_full = self.room_number_new.rent_full
        else:
            self.bed_id = False
            self.new_block = False

    @api.onchange('amount_in_advance')
    def _onchage_amount_advance(self):
        for rec in self:
            rec.admission_total_amount = rec.amount_in_advance

    @api.onchange('admission_amount_paid')
    def _onchage_amount_paid(self):
        for rec in self:
            if (rec.admission_amount_paid < rec.admission_total_amount and rec.admission_amount_paid > 0):
                rec.admission_balance = rec.admission_total_amount - rec.admission_amount_paid
            elif (rec.admission_amount_paid > rec.admission_total_amount and rec.admission_amount_paid > 0):
                rec.admission_balance = rec.admission_amount_paid - rec.admission_total_amount
            else:
                rec.admission_balance = 0

    @api.onchange('admit_cash_amount', 'admit_upi_amount', 'admit_card_amount', 'admit_payment_method_split', 'amount_in_advance')
    def _onchange_admit_payment_amounts(self):
        for rec in self:
            rec.admission_total_amount = rec.amount_in_advance
            if rec.admit_payment_method_split:
                cash = rec.admit_cash_amount or 0.0
                upi = rec.admit_upi_amount or 0.0
                card = rec.admit_card_amount or 0.0
                total = float(rec.amount_in_advance or 0.0)

                rec.admission_amount_paid = int(cash + upi + card)
                rec.admission_balance = int(total - (cash + upi + card))

    @api.depends('room_category')
    def _compute_available_room_ids(self):
        for rec in self:
            domain = [('room_type', '=', rec.room_category), ('is_available', '=', True)]
            rec.available_room_ids = self.env['hospital.room'].search(domain)

    # payment_method = fields.Selection([
    # ('cash', 'Cash'),
    # ('upi', 'UPI'),
    # ('card', 'Card')
    # ], string='Payment Method')
    # payment_reference = fields.Char(string='Payment Reference')

    def _default_registration_fee(self):
        """Fetch the first registration fee as the default"""
        return self.env['patient.registration.fee'].search([], limit=1).id

    def action_walk_in_patient(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Walk-in Patients',
            'res_model': 'patient.reg',
            'view_mode': 'tree,form',
            'views': [(self.env.ref('homeo_doctor.patient_reg_walk_in_tree').id, 'tree')],
            'domain': [('walk_in', '=', True)],
            'target': 'current',
        }

    bill_number = fields.Char(string="Bill Number", readonly=True, copy=False, default='/')

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

    def action_register_pay(self):
        self.ensure_one()

        # ── Duplicate Patient Check before Pay ────────────────────────────────
        self._check_duplicate_patient(record_id=self.id)

        if self.register_staff_name and self.register_staff_password:
            employee = self.register_staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.register_staff_password != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")

        if not self.bill_number or self.bill_number == '/':
            today = fields.Date.context_today(self)
            raw_seq = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('patient.bill')
            # raw_seq = self.env['ir.sequence'].next_by_code('patient.bill') or '0'
            padded_seq = str(raw_seq).zfill(4)

            # today = date.today()
            # year_start = today.year % 100
            # year_end = (today.year + 1) % 100
            # fiscal_suffix = f"{year_start:02d}-{year_end:02d}"
            #
            # self.bill_number = f"{padded_seq}/{fiscal_suffix}"

            #james
            # today = date.today()
            # today = fields.Date.context_today(self)

            # Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"

            self.bill_number = f"{padded_seq}/{fiscal_suffix}"

        self.status = 'paid'
        self.register_bool = True

        if self.vssc_boolean :
            self.status = 'unpaid'
            self.registration_fee = False
            self.consultation_fee = 400

        # self.register_staff_name = False
        self.register_staff_password = False

        return self.env.ref('homeo_doctor.report_patient_challan_action').report_action(self)

    admitted_bill_number = fields.Char(string="Bill Number", readonly=True, copy=False, default='/')

    def action_create_admission(self):
        if self.Staff_name and self.staff_password:
            employee = self.Staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_password != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        if not self.admitted_bill_number or self.admitted_bill_number == '/':
            raw_seq = self.env['ir.sequence'].next_by_code('admitted.bill') or '0'
            padded_seq = str(raw_seq).zfill(4)

            # today = date.today()
            # year_start = today.year % 100
            # year_end = (today.year + 1) % 100
            # fiscal_suffix = f"{year_start:02d}-{year_end:02d}"
            #
            # self.admitted_bill_number = f"{padded_seq}/{fiscal_suffix}"
            #james
            # today = date.today()
            today = fields.Date.context_today(self)


            # Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"

            self.admitted_bill_number = f"{padded_seq}/{fiscal_suffix}"

        admission_model = self.env['hospital.admitted.patient']
        patient_wallet = self.env['patient.wallet']
        # discharge_model = self.env['discharge.billing']
        registration_model = self.env['patient.reg']
        room_model = self.env['hospital.room']
        advance_model = self.env['advance.patient.record']
        wallet_rec = False
        for rec in self:
            rec.admission_total_amount = False
            patient = registration_model.search([('reference_no', '=', rec.reference_no)], limit=1)
            if not patient:
                raise UserError(f"No patient found with reference no: {rec.reference_no}")
            if rec.amount_in_advance >0:
                wallet_rec=patient_wallet.create({
                    'uhid': patient.id,
                    'patient_name':rec.patient_id,
                    'amount_in_inr':rec.amount_in_advance,
                    'Staff_name':rec.Staff_name.id,
                    'payment_mode':rec.advance_mode_payment,
                    'payment_method_split': rec.admit_payment_method_split,
                    'cash_amount': rec.admit_cash_amount,
                    'upi_amount': rec.admit_upi_amount,
                    'card_amount': rec.admit_card_amount,
                })
                wallet_rec.action_add_amount()
            admission_model.create({
                'patient_id': patient.id,
                'admission_date': fields.Datetime.now(),
                'room_number': rec.room_number_new.id,
                'room_category_new': rec.room_category_new.id,
                'bed_id': rec.bed_id.id,
                'attending_doctor': rec.doctor.id,
                'visited_doctor_ids': [(4, rec.doctor.id)] if rec.doctor else [],
            })
            advance_model.create({
                'patient_id': rec.reference_no,
                'name': rec.patient_id,
                'discharge_date': rec.discharge_date,
                'admitted_date': rec.admitted_date,
                'room_number': rec.room_number_new.id,
                'doctor': rec.doctor.id,
                'total_amount': rec.admission_total_amount,
                'room_category_new': rec.room_category_new.id,
                'new_block': rec.new_block.id,
                'bed_id': rec.bed_id.id,
                'amount_in_advance': rec.amount_in_advance,
                'bystander_name': rec.bystander_name,
                'relation': rec.bystander_relation,
                'email': rec.bystander_email,
                'bystander_mobile': rec.bystander_mobile,
                'alternate_no': rec.alternate_no,
                'op_category': rec.op_category.id,
                'pay_mode': rec.advance_mode_payment,

            })

            if rec.room_number_new:
                room = room_model.browse(rec.room_number_new.id)
                if room:
                    room.write({'is_available': True})

            rec.status = 'admitted'
        if wallet_rec:
            return self.env.ref('homeo_doctor.report_patient_a5_wallet').report_action(wallet_rec)


    def _get_report_values(self, docids, data=None):
        docs = self.env['patient.reg'].browse(docids)
        return {
            'docs': docs,
            'company_logo': self.env.user.company_id.logo,  # Ensure logo is included
        }

    def action_register_confirm(self):
        payment_vals = {
            'payment_method': self.payment_method,
            'payment_reference': self.payment_reference,
        }
        for record in self:
            # Create wizard
            wizard_vals = {
                'patient_id': record.patient_id.id,
                'patient_name': record.patient_name,
                'register_id': record.id,
                'doctor_ids': [(6, 0, record.doctor_ids.ids)],
            }

            # Create wizard
            wizard = self.env['register.payment.wizard'].create(wizard_vals)

            # Create fee lines
            for doctor in record.doctor_ids:
                # Get consultation fee for this doctor
                doc_fee = 0
                for fee in record.consultation_fee_ids:
                    if fee.doctor_id.id == doctor.id:
                        doc_fee = fee.consultation_fee
                        break

                # If no fee found in consultation_fee_ids, calculate it
                if doc_fee == 0 and hasattr(doctor, 'consultation_fee_doctor'):
                    doc_fee = doctor.consultation_fee_doctor

                # Create fee line
                self.env['wizard.register.fee'].create({
                    'wizard_id': wizard.id,
                    'doctor_id': doctor.id,
                    'fee_amount': doc_fee
                })

            # Return action to open wizard
            return {
                'name': 'Register Payment',
                'type': 'ir.actions.act_window',
                'res_model': 'register.payment.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'active_id': record.id}
            }

    def action_report_patient_card(self):
        return self.env.ref('homeo_doctor.report_patient_card').report_action(self)

    @api.onchange('vssc_boolean')
    def _onchange_vssc_boolean(self):
        if self.vssc_boolean:
            self.registration_fee = False

    @api.depends('discharge_date', 'admitted_date')
    def _compute_no_days(self):
        for record in self:
            if record.admitted_date and record.discharge_date:
                admitted = record.admitted_date
                discharge = record.discharge_date
                if isinstance(admitted, str):
                    admitted = fields.Datetime.from_string(admitted)
                elif isinstance(admitted, date) and not isinstance(admitted, datetime):
                    admitted = datetime.combine(admitted, datetime.min.time())
                if isinstance(discharge, str):
                    discharge = fields.Datetime.from_string(discharge)
                elif isinstance(discharge, date) and not isinstance(discharge, datetime):
                    discharge = datetime.combine(discharge, datetime.min.time())
                record.no_days = (discharge - admitted).days + 1
            else:
                record.no_days = 0

    @api.onchange('no_days')
    def _admission_button_active(self):
        vals = self.env['patient.registration'].search([('patient_id', '=', self.reference_no)])
        vals.move_to_admission_clicked = False

    @api.constrains('email')
    def _check_email(self):
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for record in self:
            if record.email and not re.match(email_regex, record.email):
                raise UserError("⚠️ Warning: The email address '%s' is invalid." % record.email)

    @api.constrains('patient_id', 'address', 'phone_number', 'email', 'pin_code')
    def _check_unique_patient(self):
        for record in self:
            if not record.patient_id:
                continue

            name = (record.patient_id or '').strip()
            phone = (record.phone_number or '').strip()
            email = (record.email or '').strip()
            address = (record.address or '').strip()
            pin = (record.pin_code or '').strip()

            domain = [
                ('patient_id', '=ilike', name),
                ('phone_number', '=', phone),
                ('status', '!=', 'cancelled'),
                ('id', '!=', record.id)
            ]

            # Adding other fields to domain if they match
            domain.append(('email', '=', email) if email else ('email', 'in', [False, '']))
            domain.append(('address', '=ilike', address) if address else ('address', 'in', [False, '']))
            domain.append(('pin_code', '=', pin) if pin else ('pin_code', 'in', [False, '']))

            duplicate = self.search(domain, limit=1)
            if duplicate:
                raise ValidationError(_("A patient with the same Name, Mobile, Email, Address, and PIN Code already exists! (Reference No: %s)") % duplicate.reference_no)

    @api.onchange('patient_id', 'address', 'phone_number', 'email', 'pin_code')
    def _onchange_unique_patient(self):
        if self.patient_id and self.phone_number:
            name = (self.patient_id or '').strip()
            phone = (self.phone_number or '').strip()
            email = (self.email or '').strip()
            address = (self.address or '').strip()
            pin = (self.pin_code or '').strip()

            domain = [
                ('patient_id', '=ilike', name),
                ('phone_number', '=', phone),
                ('status', '!=', 'cancelled'),
            ]
            domain.append(('email', '=', email) if email else ('email', 'in', [False, '']))
            domain.append(('address', '=ilike', address) if address else ('address', 'in', [False, '']))
            domain.append(('pin_code', '=', pin) if pin else ('pin_code', 'in', [False, '']))

            duplicate = self.search(domain, limit=1)
            if duplicate:
                return {
                    'warning': {
                        'title': _("Duplicate Record Found"),
                        'message': _("A patient with this Name, Mobile, Email, Address, and PIN Code already exists (Reference No: %s).") % duplicate.reference_no,
                    }
                }

    @api.onchange('dob')
    def _compute_age(self):
        for record in self:
            if record.dob:
                today = date.today()
                dob = record.dob

                record.age = today.year - dob.year - (
                        (today.month, today.day) < (dob.month, dob.day)
                )
            else:
                record.age = 0

    # @api.onchange('room_category')
    # def onchange_advance_amount(self):
    #     for i in self:
    #         if i.room_category:
    #             i.advance_amount = i.room_category.advance_amount
    #             i.nurse_charge = i.room_category.nursing_fee
    #
    #         else:
    #             pass

    @api.depends('doc_name', 'referred', 'tt', 'vssc_boolean')
    def _compute_consultation_fee(self):
        for record in self:
            if record.doc_name:
                if record.vssc_boolean:
                    zero_fee = self.env['patient.registration.fee'].search([('fee', '=', 0)], limit=1)
                    record.registration_fee = zero_fee.id if zero_fee else False
                    record.consultation_fee = 400
                    record.register_total_amount = 400

                else:
                    # Automatically populate consultation_fee from the selected doctor's record
                    record.consultation_fee = record.doc_name.consultation_fee_doctor
                if record.doc_name:
                    if record.referred or record.tt:
                        record.consultation_fee = 0
                        # Set registration_fee to the one with fee = 100
                        fee = self.env['patient.registration.fee'].search([('fee', '=', 100)], limit=1)
                        record.registration_fee = fee.id if fee else record._default_registration_fee()
                    else:
                        # Normal case: use doctor's consultation fee and default reg fee
                        record.consultation_fee = record.doc_name.consultation_fee_doctor
                        record.registration_fee = record._default_registration_fee()

    @api.onchange('department_id')
    def _onchange_department_id(self):
        if self.department_id:
            return {
                'domain': {
                    'doc_name': [('department_id', '=', self.department_id.id)],
                }
            }
        return {
            'domain': {
                'doc_name': []
            }
        }

    def _compute_lab_report_count(self):
        for record in self:
            # Count the lab reports for this patient
            record.lab_report_count = self.env['doctor.lab.report'].search_count([('patient_id', '=', record.id)])

    def action_view_lab_reports(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lab Reports',
            'res_model': 'doctor.lab.report',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.id)],
            'context': dict(self.env.context, default_patient_id=self.id),
        }

    def _check_duplicate_patient(self, vals=None, record_id=False):
        """Check if a patient with same Name, Phone, Email, Address & PIN already exists (skips cancelled)."""
        def safe(v):
            return str(v or '').strip().lower()

        name = safe(vals.get('patient_id') if vals else self.patient_id)
        phone = safe(vals.get('phone_number') if vals else self.phone_number)
        email = safe(vals.get('email') if vals else self.email)
        address = safe(vals.get('address') if vals else self.address)
        pin = safe(vals.get('pin_code') if vals else self.pin_code)

        if not name:
            return

        # Search only by Name + Phone among non-cancelled records
        domain = [
            ('patient_id', '=ilike', name),
            ('phone_number', '=', phone),
            ('status', '!=', 'cancelled'),
        ]
        if record_id:
            domain.append(('id', '!=', record_id))

        candidates = self.sudo().search(domain)

        # Python-level comparison for email, address, pin (handles False/None/empty uniformly)
        for rec in candidates:
            rec_email = safe(rec.email)
            rec_address = safe(rec.address)
            rec_pin = safe(rec.pin_code)
            if email == rec_email and address == rec_address and pin == rec_pin:
                raise ValidationError(
                    _("⚠️ Patient Already Exists!\n\nA patient with the same Name, Mobile, Email, Address, and PIN Code already exists.\n\nExisting Reference No: %s") % rec.reference_no
                )

    @api.model
    def create(self, vals):
        year_prefix = datetime.today().strftime("%y")  # Get last two digits of the year (e.g., "25" for 2025)

        def format_sequence(sequence):
            """Ensure sequence has at least 7 digits and prepend year prefix."""
            sequence_str = str(sequence).zfill(7)  # Ensure at least 7 digits
            return f"{year_prefix}/{sequence_str}"  # Format as "25/0012332"

        # ── Duplicate Patient Check ──────────────────────────────────────────
        self._check_duplicate_patient(vals=vals)

        # Generate token number if doctor is selected
        if vals.get('no_consultation', False):
            vals['token_no'] = False  # Do not generate token number
            if vals.get('reference_no', _('New')) == _('New'):
                sequence = self.env['ir.sequence'].next_by_code('patient.reg.group') or _('New')
                vals['reference_no'] = format_sequence(sequence)  # Apply formatting
                return super(PatientRegistration, self).create(vals)

        if vals.get('doc_name'):
            doctor = self.env['doctor.profile'].browse(vals.get('doc_name'))
            appointment_date = vals.get('time') if vals.get('time') else fields.Date.context_today(self)
            if doctor:
                vals['token_no'] = doctor.get_next_token_number(appointment_date)

        # Check if consultation_check is False before generating reference_no
        if not vals.get('consultation_check'):
            if vals.get('reference_no', _('New')) == _('New'):
                sequence = self.env['ir.sequence'].next_by_code('patient.reg.group') or _('New')
                vals['reference_no'] = format_sequence(sequence)  # Apply formatting
        else:
            # If consultation_check is True, generate a temporary reference number with formatting
            if vals.get('temp_reference_no', _('New')) == _('New'):
                temp_sequence = self.env['ir.sequence'].next_by_code('patient.reg.temp') or _('New')
                vals['temp_reference_no'] = format_sequence(temp_sequence)  # Apply formatting

        # Create the main patient registration record
        record = super(PatientRegistration, self).create(vals)
        # After record creation, check if consultation_check is False
        if not vals.get('admission_boolean', False) and not record.consultation_check:
            self.env['patient.registration'].create({
                'user_id': record.id,
                'patient_id': record.id,
                'token_no': record.token_no,
                'address': record.address,
                'age': record.age,
                'phone_number': record.phone_number,
                'doctor': record.doc_name.id,
                'appointment_date': record.time,
            })

        return record

    @api.depends('date', 'time')
    def _compute_formatted_date(self):
        for record in self:
            if record.date:
                formatted_date = record.date.strftime('%d/%m/%Y')
                record.formatted_date = formatted_date
            else:
                record.formatted_date = ''

    @api.model
    def search_patient_by_phone(self, phone_number):
        return self.search([('phone_number', 'ilike', phone_number)])

    def action_create_appointment(self):
        appointment_vals = {
            'patient_id': self.id,
            'appointment_date': fields.Datetime.now(),
            'doctor_id': self.doc_name.id,
            'department': self.department_id.id,
            'status': 'draft',
        }
        appointment = self.env['patient.appointment'].create(appointment_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Patient Appointment',
            'res_model': 'patient.appointment',
            'view_mode': 'form',
            'res_id': appointment.id,
            'target': 'current',
        }

    def open_patient_history(self):

        self.ensure_one()

        # Create history wizard
        history_wizard = self.env['patient.history.wizard'].create({
            'patient_id': self.id
        })

        # Return action to open wizard
        return {
            'name': f'Patient History - {self.patient_id}',
            'type': 'ir.actions.act_window',
            'res_model': 'patient.history.wizard',
            'res_id': history_wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }


class RoomCategory(models.Model):
    _name = 'room.category'
    _rec_name = 'room_category'

    room_category = fields.Char(string='Room Category')
    advance_amount = fields.Integer(string='Advance Amount')
    nursing_fee = fields.Integer(string='Nursing Fee')


class PatientRegistrationFee(models.Model):
    _name = 'patient.registration.fee'
    _rec_name = 'fee'

    fee = fields.Integer(string='Patient Registration Fee')


class PatientHistoryWizard(models.TransientModel):
    _name = 'patient.history.wizard'
    _description = 'Patient History Wizard'

    patient_id = fields.Many2one('patient.reg', string='Patient', required=True)

    # Consultation History
    consultation_history_ids = fields.One2many(
        'patient.registration',
        compute='_compute_consultation_history',
        string='Consultation History'
    )

    # Lab Reports
    lab_report_ids = fields.One2many(
        'doctor.lab.report',
        compute='_compute_lab_reports',
        string='Lab Reports'
    )

    # MRI Reports
    mri_report_ids = fields.One2many(
        'scanning.mri',
        compute='_compute_mri_reports',
        string='MRI Reports'
    )

    # CT Reports
    ct_report_ids = fields.One2many(
        'scanning.ct',
        compute='_compute_ct_reports',
        string='CT Reports'
    )

    # X-Ray Reports
    x_ray_report_ids = fields.One2many(
        'scanning.x.ray',
        compute='_compute_x_ray_reports',
        string='X-Ray Reports'
    )
    # Pharmacy History
    pharmacy_history_ids = fields.One2many(
        'pharmacy.description',
        compute='_compute_pharmacy_history',
        string='Pharmacy History'
    )

    @api.depends('patient_id')
    def _compute_consultation_history(self):
        for record in self:
            record.consultation_history_ids = self.env['patient.registration'].search([
                ('user_id', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_lab_reports(self):
        for record in self:
            record.lab_report_ids = self.env['doctor.lab.report'].search([
                ('user_ide', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_mri_reports(self):
        for record in self:
            record.mri_report_ids = self.env['scanning.mri'].search([
                ('user_ide', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_ct_reports(self):
        for record in self:
            record.ct_report_ids = self.env['scanning.ct'].search([
                ('user_ide', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_x_ray_reports(self):
        for record in self:
            record.x_ray_report_ids = self.env['scanning.x.ray'].search([
                ('user_ide', '=', record.patient_id.id)
            ])

    @api.depends('patient_id')
    def _compute_pharmacy_history(self):
        for record in self:
            record.pharmacy_history_ids = self.env['pharmacy.description'].search([
                ('patient_id', '=', record.patient_id.id)
            ])


class OpCategory(models.Model):
    _name = 'block'
    _rec_name = 'block'

    block = fields.Char(string='block')


class Insurancemodel(models.Model):
    _name = 'insurance.model'
    _rec_name = 'ins_name'

    ins_name = fields.Char(string='Insurance Company')
    ins_id = fields.Char(string='Insurance ID')
    policy_no = fields.Char(string='Policy Number')
    claim_no = fields.Char(string='Claim Number')

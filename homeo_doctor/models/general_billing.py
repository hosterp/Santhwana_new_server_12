import base64
from collections import defaultdict

from num2words import num2words

from odoo import models, fields, api
from datetime import datetime

# from odoo.odoo.tools.safe_eval import dateutil

from datetime import datetime, date

# from odoo.odoo.exceptions import UserError


# from odoo.odoo.exceptions import UserError


# from odoo.odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo import api, fields, models
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class GeneralBilling(models.Model):
    _name = 'general.billing'
    _description = 'General Billing'
    _rec_name = 'bill_number'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID')
    mrd_discharge_no = fields.Many2one('discharge.billing', string='UHID')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Date(string='Bill Date', default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name", 
                             readonly=False)
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_types = fields.Many2one('bill.type', string='Bill Type')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type",required=True)
    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('general.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Integer(string='Total Amount')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff())
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('observation', 'Observation'),
        ('discharge', 'Discharge'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    vssc_boolean = fields.Boolean(string='VSSC')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0


    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    @api.onchange('mrd_no', 'bill_date', 'bill_type')
    def _onchange_mrd_no_update_doctor(self):
        for rec in self:
            # 1. Historical Lock: If bill is finalized (paid/discharge/cancelled), never recompute doctor.
            if rec.doctor and rec.status in ['paid', 'discharge', 'cancelled']:
                continue

            # 2. Sync with DB if empty
            if not rec.doctor and isinstance(rec.id, int):
                existing = self.sudo().browse(rec.id).doctor
                if existing:
                    rec.doctor = existing.id
                    # If it's an IP bill and discharged, lock it now.
                    if rec.mrd_no and rec.mrd_no.status == 'discharged' and rec.bill_type == 'admitted':
                        return

            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                if rec.bill_type == 'admitted':
                    # Priority 1: Admission Logs (IP Priority)
                    admission_log = self.env['hospital.admitted.patient'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('admission_date', '<=', bill_date)
                    ], order='admission_date desc', limit=1)
                    
                    if admission_log:
                        adm_dis_date = admission_log.discharge_date
                        if isinstance(adm_dis_date, datetime):
                            adm_dis_date = adm_dis_date.date()
                        
                        # Match if within bounds OR if IP bill for a now discharged patient
                        if not adm_dis_date or bill_date <= adm_dis_date or (rec.mrd_no.status == 'discharged' and rec.bill_type == 'admitted'):
                            if admission_log.attending_doctor:
                                doctor = admission_log.attending_doctor.id

                    # Priority 2: Discharged History Records (Only for IP bills)
                    if not doctor and rec.bill_type == 'admitted':
                        historical_admission = self.env['discharged.patient.record'].sudo().search([
                            ('patient_id', '=', rec.mrd_no.reference_no),
                            ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                            ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                        ], limit=1)
                        if historical_admission and historical_admission.doctor:
                            doctor = historical_admission.doctor.id
                
                # Fallback / OP Logic
                if not doctor:
                    # 1️⃣ Priority: Appointment for TODAY
                    appt_today = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='id desc', limit=1)
                    if appt_today and appt_today.doctor_ids:
                        doctor = appt_today.doctor_ids[0].id

                if not doctor:
                    # 2️⃣ Priority: Consultation log for TODAY
                    reg_today = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '=', bill_date),
                        # ('status', 'not in', ['admitted', 'proceed_discharge']) # Removed to allow picking doctor even if admitted
                    ], order='id desc', limit=1)
                    if reg_today and reg_today.doctor:
                        doctor = reg_today.doctor.id

                if not doctor:
                    # 3️⃣ Priority: Historical Consultation log
                    reg_prev = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '<', bill_date),
                        ('status', 'not in', ['admitted', 'proceed_discharge'])
                    ], order='date desc', limit=1)
                    if reg_prev and reg_prev.doctor:
                        doctor = reg_prev.doctor.id

                if not doctor:
                    # 4️⃣ Priority: Historical Appointment
                    appt_prev = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '<', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt_prev and appt_prev.doctor_ids:
                        doctor = appt_prev.doctor_ids[0].id

                if not doctor:
                    # 5️⃣ Priority: Master Record (Context-specific)
                    if rec.bill_type == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.status', 'mrd_no.admitted_date', 'mrd_no.doctor', 'mrd_no.doc_name', 'bill_date', 'bill_type')
    def _compute_doctor_name(self):
        for rec in self:
            # 1. Historical Lock: If bill is finalized (paid/discharged/cancelled), never recompute doctor.
            if rec.doctor and rec.status in ['paid', 'discharge', 'cancelled']:
                continue
            
            # 2. Sync with DB if empty
            if not rec.doctor and isinstance(rec.id, int):
                existing = self.sudo().browse(rec.id).doctor
                if existing:
                    rec.doctor = existing.id
                    continue

            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                
                # Normalize bill_date to date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # 2️⃣ Priority 2: Admission logs (Highest priority for IP services)
                if not doctor and rec.bill_type == 'admitted':
                    admission_log = self.env['hospital.admitted.patient'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('admission_date', '<=', bill_date)
                    ], order='admission_date desc', limit=1)
                    
                    if admission_log:
                        adm_dis_date = admission_log.discharge_date
                        if isinstance(adm_dis_date, datetime):
                            adm_dis_date = adm_dis_date.date()
                        
                        # Match if within bounds OR if IP bill for a now discharged patient
                        if not adm_dis_date or bill_date <= adm_dis_date or (rec.mrd_no.status == 'discharged' and rec.bill_type == 'admitted'):
                            if admission_log.attending_doctor:
                                doctor = admission_log.attending_doctor.id

                # 3️⃣ Priority 3: Discharged History Records (Only for IP bills)
                if not doctor and rec.bill_type == 'admitted':
                    historical_admission = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if historical_admission and historical_admission.doctor:
                        doctor = historical_admission.doctor.id
                
                # Fallback / OP Logic
                if not doctor:
                    # 1️⃣ Priority: Appointment for TODAY
                    appt_today = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='id desc', limit=1)
                    if appt_today and appt_today.doctor_ids:
                        doctor = appt_today.doctor_ids[0].id

                if not doctor:
                    # 2️⃣ Priority: Consultation log for TODAY
                    reg_today = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '=', bill_date),
                        # ('status', 'not in', ['admitted', 'proceed_discharge']) # Removed to allow picking doctor even if admitted
                    ], order='id desc', limit=1)
                    if reg_today and reg_today.doctor:
                        doctor = reg_today.doctor.id

                if not doctor:
                    # 3️⃣ Priority: Historical Consultation log
                    reg_prev = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '<', bill_date),
                        ('status', 'not in', ['admitted', 'proceed_discharge'])
                    ], order='date desc', limit=1)
                    if reg_prev and reg_prev.doctor:
                        doctor = reg_prev.doctor.id

                if not doctor:
                    # 4️⃣ Priority: Historical Appointment
                    appt_prev = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '<', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt_prev and appt_prev.doctor_ids:
                        doctor = appt_prev.doctor_ids[0].id

                # 5️⃣ Priority 5: Fallback to Master Record doctor (Context-specific)
                if not doctor:
                    if rec.bill_type == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    # @api.depends('mrd_no', 'bill_date')
    # def _compute_doctor_name(self):
    #     """Fetch doctor name from patient.reg or patient.revisit for current UHID and date"""
    #     for rec in self:
    #         doctor = False
    #         if rec.mrd_no and rec.bill_date:
    #             # Search patient.reg first
    #             reg = self.env['patient.reg'].search([
    #                 ('id', '=', rec.mrd_no.id),
    #                 ('time', '=', rec.bill_date)
    #             ], limit=1)
    #
    #             if reg and reg.doc_name:
    #                 doctor = reg.doc_name.id
    #
    #             else:
    #                 # Search in patient.revisit
    #                 revisit = self.env['patient.appointment'].search([
    #                     ('patient_id', '=', rec.mrd_no.id),
    #                     ('appointment_date', '=', rec.bill_date),
    #                     ('status', '=', 'confirmed')
    #                 ], limit=1)
    #                 if revisit and revisit.doctor_ids:
    #                     doctor = revisit.doctor_ids.id
    #
    #         rec.doctor = doctor

    def action_cancel(self):
        for rec in self:
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'
            self.status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        self.status = 'discharge'
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount

    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if (rec.amount_paid < rec.net_amount and rec.amount_paid > 0):
                rec.balance = rec.net_amount - rec.amount_paid
            elif (rec.amount_paid > rec.net_amount and rec.amount_paid > 0):
                rec.balance = rec.amount_paid - rec.net_amount
            else:
                rec.balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.net_amount or 0.0

            rec.amount_paid = int(cash + upi + card)
            rec.balance = int(total - (cash + upi + card))

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'
        return self.env.ref('homeo_doctor.report_general_bill_report').report_action(self)

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
                 'rent')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name # Removed to allow compute/specialized onchange to handle doctor assignment
            self.vssc_boolean = self.mrd_no.vssc_boolean
            if self.mrd_no.status == 'admitted':
                self.bill_type = 'admitted'
                self.mode_pay = 'credit'
            else:
                self.bill_type = 'op'
                self.mode_pay = 'cash'

    # @api.model
    # def create(self, vals):
    #     """Generate a unique billing number in the format: 000001/24-25"""
    #     if vals.get('bill_number', 'New') == 'New':
    #         current_year = datetime.now().year
    #         next_year = current_year + 1
    #         year_range = f"{str(current_year)[-2:]}-{str(next_year)[-2:]}"
    #
    #         # Get the next sequence number
    #         sequence_number = self.env['ir.sequence'].next_by_code('general.billing')
    #
    #         # Ensure sequence exists
    #         if not sequence_number:
    #             sequence_number = '1'
    #         formatted_seq = str(sequence_number).zfill(4)
    #         vals['bill_number'] = f"{formatted_seq}/{year_range}"
    #
    #     return super(GeneralBilling, self).create(vals)

    #james
    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 000001/24-25"""
        if vals.get('bill_number', 'New') == 'New':
            # current_year = datetime.now().year
            # next_year = current_year + 1
            # year_range = f"{str(current_year)[-2:]}-{str(next_year)[-2:]}"

            # today = datetime.now()

            today = fields.Date.context_today(self)

            if today.month >= 4:
                start_year = today.year
                end_year = today.year + 1
            else:
                start_year = today.year - 1
                end_year = today.year
            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # Get the next sequence number
            # sequence_number = self.env['ir.sequence'].next_by_code('general.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('general.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        return super(GeneralBilling, self).create(vals)

    def write(self, vals):
        res = super(GeneralBilling, self).write(vals)
        for record in self:
            # Sync back to patient.reg if details changed in the bill
            if record.mrd_no and ('patient_name' in vals or 'mobile' in vals or 'age' in vals or 'gender' in vals):
                reg_vals = {}
                if 'patient_name' in vals:
                    reg_vals['patient_id'] = vals['patient_name']
                if 'mobile' in vals:
                    reg_vals['phone_number'] = vals['mobile']
                if 'age' in vals:
                    reg_vals['age'] = vals['age']
                if 'gender' in vals:
                    reg_vals['gender'] = vals['gender']
                
                if reg_vals:
                    record.mrd_no.sudo().write(reg_vals)
        return res


    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    def action_print_general_bill(self):
        return self.env.ref('homeo_doctor.report_general_bill_report').report_action(self)


class BillTYpe(models.Model):
    _name = 'bill.type'
    _rec_name = 'bill_type'

    bill_type = fields.Char(string='Bill Type')


class GeneralBillLine(models.Model):
    _name = 'general.bill.line'

    bill_line_id = fields.Many2one('general.billing')
    particulars = fields.Many2one('general.dept.costing', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Integer(string='Qty')
    total_amt = fields.Integer(string='Amount', compute="_compute_total")

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate * line.quantity * (1 + tax_amount / 100)

    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            rec.rate = rec.particulars.amount


class IPPartBilling(models.Model):
    _name = 'ip.part.billing'
    _description = 'IP Part Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)
                # fy example: 25-26 → take end year (26)
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0

    mrd_no = fields.Many2one('patient.reg', string='UHID')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Datetime(string='Bill Date', default=lambda self: datetime.today())
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name_ip", readonly=False)

    @api.onchange('mrd_no', 'bill_date')
    def _onchange_mrd_no_update_doctor_ip(self):
        for rec in self:
            # Historical Guard: IP Part Billing is strictly for IP. Lock on discharge.
            if rec.doctor and rec.mrd_no and rec.mrd_no.status == 'discharged':
                continue

            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # IP Logic: Admission Logs
                admission_log = self.env['hospital.admitted.patient'].sudo().search([
                    ('patient_id', '=', rec.mrd_no.id),
                    ('admission_date', '<=', bill_date)
                ], order='admission_date desc', limit=1)

                if admission_log:
                    adm_dis_date = admission_log.discharge_date
                    if isinstance(adm_dis_date, datetime):
                        adm_dis_date = adm_dis_date.date()
                    
                    if not adm_dis_date or bill_date <= adm_dis_date:
                        if admission_log.attending_doctor:
                            doctor = admission_log.attending_doctor.id

                # IP Fallback: Historical Snapshot
                if not doctor:
                    historical_admission = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if historical_admission and historical_admission.doctor:
                        doctor = historical_admission.doctor.id

                # Fallback to Consultation
                if not doctor:
                    reg = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '<=', bill_date)
                    ], order='date desc', limit=1)
                    if reg and reg.doctor:
                        doctor = reg.doctor.id

                if not doctor:
                    if rec.mrd_no.status == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.status', 'mrd_no.admitted_date', 'mrd_no.doctor', 'mrd_no.doc_name', 'bill_date')
    def _compute_doctor_name_ip(self):
        for rec in self:
            # 1. Standard Guard: Locked if explicitly paid.
            if rec.status == 'paid' and rec.doctor:
                continue
            
            # 2. Historical Guard: IP Part Billing is strictly IP. Lock once discharged.
            if rec.doctor and rec.mrd_no and rec.mrd_no.status == 'discharged':
                continue

            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # IP Logic: Admission Logs
                admission_log = self.env['hospital.admitted.patient'].sudo().search([
                    ('patient_id', '=', rec.mrd_no.id),
                    ('admission_date', '<=', bill_date)
                ], order='admission_date desc', limit=1)

                if admission_log:
                    adm_dis_date = admission_log.discharge_date
                    if isinstance(adm_dis_date, datetime):
                        adm_dis_date = adm_dis_date.date()
                    
                    if not adm_dis_date or bill_date <= adm_dis_date:
                        if admission_log.attending_doctor:
                            doctor = admission_log.attending_doctor.id

                # IP Fallback: Historical Snapshot
                if not doctor:
                    historical_admission = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if historical_admission and historical_admission.doctor:
                        doctor = historical_admission.doctor.id

                # Fallback to Consultation
                if not doctor:
                    reg = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('date', '<=', bill_date)
                    ], order='date desc', limit=1)
                    if reg and reg.doctor:
                        doctor = reg.doctor.id

                if not doctor:
                    if rec.mrd_no.status == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_type = fields.Many2one('bill.type', string='Bill Type')

    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('ip.part.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Integer(string='Total Amount')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")


    def write(self, vals):
        res = super(IPPartBilling, self).write(vals)
        for record in self:
            # Sync back to patient.reg if details changed in the bill
            if record.mrd_no and ('patient_name' in vals or 'mobile' in vals or 'age' in vals or 'gender' in vals):
                reg_vals = {}
                if 'patient_name' in vals:
                    reg_vals['patient_id'] = vals['patient_name']
                if 'mobile' in vals:
                    reg_vals['phone_number'] = vals['mobile']
                if 'age' in vals:
                    reg_vals['age'] = vals['age']
                if 'gender' in vals:
                    reg_vals['gender'] = vals['gender']
                
                if reg_vals:
                    record.mrd_no.sudo().write(reg_vals)
        return res
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name')
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")
    vssc_boolean = fields.Boolean(string='VSSC')

    def action_cancel(self):
        for rec in self:
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount

    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if (rec.amount_paid < rec.net_amount and rec.amount_paid > 0):
                rec.balance = rec.net_amount - rec.amount_paid
            elif (rec.amount_paid > rec.net_amount and rec.amount_paid > 0):
                rec.balance = rec.amount_paid - rec.net_amount
            else:
                rec.balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.net_amount or 0.0

            rec.amount_paid = int(cash + upi + card)
            rec.balance = int(total - (cash + upi + card))


    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'

        # Return action to print PDF and show notification
        return {
            'type': 'ir.actions.report',
            'report_name': 'homeo_doctor.report_ip_part_billing_document',
            'report_type': 'qweb-pdf',
            'context': {
                'active_ids': self.ids,
                'active_model': 'ip.part.billing',
            },
            'target': 'new',
        }

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
                 'rent')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name  <-- REMOVED TO SUPPORT REVISIT DOCTOR
            self.vssc_boolean = self.mrd_no.vssc_boolean
            self.admitted_date = self.mrd_no.admitted_date
            self.rent_full_day = self.mrd_no.rent_full
            self.rent_half_day = self.mrd_no.rent_half

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars.particular_name == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.particular_name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('particular_name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.particular_name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    # @api.model
    # def create(self, vals):
    #     """Generate a unique billing number in the format: 0001/24-25"""
    #     if vals.get('bill_number', 'New') == 'New':
    #         current_year = datetime.now().year
    #         next_year = current_year + 1
    #         year_range = f"{str(current_year)[-2:]}-{str(next_year)[-2:]}"
    #
    #         # Get the next sequence number
    #         sequence_number = self.env['ir.sequence'].next_by_code('ip.part.billing')
    #
    #         if not sequence_number:
    #             raise ValueError("Sequence 'ip.part.billing' is not defined.")
    #
    #         vals['bill_number'] = f"{sequence_number}/{year_range}"
    #
    #     return super(IPPartBilling, self).create(vals)

    #james

    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 0001/25-26"""
        if vals.get('bill_number', 'New') == 'New':
            today = datetime.now()

            # Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            # Get the next sequence number
            sequence_number = self.env['ir.sequence'].next_by_code('ip.part.billing')
            if not sequence_number:
                raise ValueError("Sequence 'ip.part.billing' is not defined.")

            # Set bill_number in vals
            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"
            vals['bill_number'] = f"{sequence_number}/{year_range}"

        return super(IPPartBilling, self).create(vals)

    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    def action_ip_print_general_bill(self):
        return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)


class IPPartBillLine(models.Model):
    _name = 'ip.part.bill.line'

    bill_line_id = fields.Many2one('ip.part.billing')
    particulars = fields.Many2one('general.dept.costing', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Float(string='Qty')
    total_amt = fields.Integer(string='Amount', compute="_compute_total")

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate * line.quantity * (1 + tax_amount / 100)

    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            rec.rate = rec.particulars.amount


class CasualityBilling(models.Model):
    _name = 'casuality.billing'
    _description = 'Casuality Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID')
    casualty_no = fields.Many2one('discharge.billing', string='UHID')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Date(string='Bill Date', default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name", 
                             readonly=False,)
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_types = fields.Many2one('bill.type', string='Bill Type')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type",required=True)
    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('casuality.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Integer(string='Total Amount')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff(),required=True)
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")

    vssc_boolean = fields.Boolean(string='VSSC')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    def write(self, vals):
        if self.env.context.get('no_sync'):
            return super(CasualityBilling, self).write(vals)
        res = super(CasualityBilling, self).write(vals)
        patient_fields = {'patient_name', 'mobile', 'age', 'gender'}
        if patient_fields & set(vals.keys()):
            for rec in self:
                if rec.mrd_no:
                    sync_vals = {}
                    if 'patient_name' in vals: sync_vals['patient_id'] = vals['patient_name']
                    if 'mobile' in vals: sync_vals['phone_number'] = vals['mobile']
                    if 'age' in vals: sync_vals['age'] = vals['age']
                    if 'gender' in vals: sync_vals['gender'] = vals['gender']
                    if sync_vals:
                        rec.mrd_no.sudo().write(sync_vals)
        return res

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0


    @api.model
    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.user.id)],
            limit=1
        )
        return employee.id or False

    def patient_challan_new_dmp(self):
        return self.env.ref('homeo_doctor.report_casuality_bill_dot_metrix_report').report_action(self)
    def patient_challan_new(self):
        return self.env.ref('homeo_doctor.report_casuality_bill_report').report_action(self)

    @api.onchange('mrd_no', 'bill_date')
    def _onchange_mrd_no_update_doctor(self):
        for rec in self:
            rec.doctor = False

            if not rec.mrd_no or not rec.bill_date:
                continue

            bill_date = rec.bill_date
            admitted_date = rec.mrd_no.admitted_date
            discharge_date = rec.mrd_no.discharge_date  # add this field if it exists in patient model

            # Normalize dates
            if admitted_date and isinstance(admitted_date, datetime):
                admitted_date = admitted_date.date()
            if discharge_date and isinstance(discharge_date, datetime):
                discharge_date = discharge_date.date()
            # Normalize dates
            if admitted_date and isinstance(admitted_date, datetime):
                admitted_date = admitted_date.date()
            if discharge_date and isinstance(discharge_date, datetime):
                discharge_date = discharge_date.date()
            if isinstance(bill_date, datetime):
                bill_date = bill_date.date()

            # Context-Aware Selection
            if rec.bill_type == 'admitted':
                # Use admitted doctor
                if (rec.mrd_no.admission_boolean and admitted_date and admitted_date <= bill_date and (not discharge_date or bill_date <= discharge_date)):
                     rec.doctor = rec.mrd_no.doctor.id
                else:
                     rec.doctor = rec.mrd_no.doctor.id
            else:
                # 1. Try Consultation log
                reg_log = self.env['patient.registration'].search([
                    '|', ('user_id', '=', rec.mrd_no.id), ('patient_id', '=', rec.mrd_no.id),
                    ('date', '<=', bill_date)
                ], order='date desc', limit=1)
                
                if reg_log and reg_log.doctor:
                    rec.doctor = reg_log.doctor.id
                else:
                    # 2. Try Appointment fallback
                    appt = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '<=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt and appt.doctor_ids:
                        rec.doctor = appt.doctor_ids[0].id
                    else:
                        # 3. Use master registration doctor
                        rec.doctor = rec.mrd_no.doc_name.id

    # @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.admitted_date', 'mrd_no.doctor', 'bill_date')
    # def _compute_doctor_name(self):
    #     for rec in self:
    #         doctor = False
    #         print('rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr')
    #         if rec.mrd_no and rec.bill_date:
    #             bill_date = rec.bill_date
    #             admitted_date = rec.mrd_no.admitted_date
    #             print('ffffffffffffffffffffffffffffffffffffffffffffffffff')
    #             # Convert datetime → date if needed
    #             if admitted_date and isinstance(admitted_date, datetime):
    #                 admitted_date = admitted_date.date()
    #                 print('vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv')
    #             # 1️⃣ Priority 1: Admitted doctor
    #             if rec.mrd_no.admission_boolean and admitted_date and admitted_date <= bill_date:
    #                 if rec.mrd_no.doctor:
    #                     doctor = rec.mrd_no.doctor.id
    #                     _logger.warning('Admitted patient: using admitted doctor %s for record %s', doctor, rec.id)
    #                     print('dddddddddddddddddddddddddddddddddd')
    #                 else:
    #                     _logger.warning('Admitted patient has no doctor assigned! Record %s', rec.id)
    #
    #             # 2️⃣ Priority 2: Outpatient reg doc_name (only if doctor not assigned yet)
    #             if not doctor:
    #                 reg = self.env['patient.reg'].search([
    #                     ('id', '=', rec.mrd_no.id),
    #                     ('time', '<=', bill_date)
    #                 ], limit=1)
    #                 if reg and reg.doc_name:
    #                     doctor = reg.doc_name.id
    #                     _logger.warning('Outpatient: using reg doctor %s for record %s', doctor, rec.id)
    #                 print('cccccccccccccccccccccccccccccccccccccccccccccccc',doctor)
    #             # 3️⃣ Priority 3: Fallback to patient.appointment
    #             if not doctor:
    #                 revisit = self.env['patient.appointment'].search([
    #                     ('patient_id', '=', rec.mrd_no.id),
    #                     ('appointment_date', '<=', bill_date),
    #                     ('status', '=', 'confirmed')
    #                 ], limit=1)
    @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.admitted_date', 'mrd_no.doctor', 'mrd_no.doc_name', 'bill_date', 'bill_type')
    def _compute_doctor_name(self):
        for rec in self:
            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # Determine Priority based on Bill Type
                # Lookup Consultation (Revisit)
                reg_log = self.env['patient.registration'].search([
                    '|', '|', ('user_id', '=', rec.mrd_no.id), ('patient_id', '=', rec.mrd_no.id), ('patient_name', '=', rec.patient_name),
                    ('date', '=', bill_date)
                ], order='date desc', limit=1)
                
                if not reg_log:
                    reg_log = self.env['patient.registration'].search([
                        '|', '|', ('user_id', '=', rec.mrd_no.id), ('patient_id', '=', rec.mrd_no.id), ('patient_name', '=', rec.patient_name),
                        ('date', '<', bill_date)
                    ], order='date desc', limit=1)

                if rec.bill_type == 'admitted':
                    # 1️⃣ IP Priority: Admission logs
                    admission_log = self.env['hospital.admitted.patient'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('admission_date', '<=', bill_date)
                    ], order='admission_date desc', limit=1)
                    if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                        doctor = admission_log.attending_doctor.id
                    
                    # 2️⃣ Fallback to Consultation
                    if not doctor and reg_log:
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            f_doc = self.env["doctor.profile"].search([("name", "=", reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        doctor = target_doctor
                else:
                    # 1️⃣ OP Priority: Appointment for TODAY
                    appt_today = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='id desc', limit=1)
                    if appt_today and appt_today.doctor_ids:
                        doctor = appt_today.doctor_ids[0].id

                    # 2️⃣ OP Priority: Consultation logs for TODAY
                    if not doctor and (reg_log and reg_log.date == bill_date):
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        if target_doctor:
                            doctor = target_doctor
                    
                    # 3️⃣ Historical Consultation logs
                    if not doctor and reg_log:
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and (hasattr(reg_log, 'doctor_id') and reg_log.doctor_id):
                            f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        if target_doctor:
                            doctor = target_doctor
                    
                    # 4️⃣ Historical Appointment Fallback (Latest confirmed)
                    if not doctor:
                        appt_prev = self.env['patient.appointment'].search([
                            ('patient_id', '=', rec.mrd_no.id),
                            ('appointment_date', '<', bill_date),
                            ('status', '=', 'confirmed')
                        ], order='appointment_date desc', limit=1)
                        if appt_prev and appt_prev.doctor_ids:
                            doctor = appt_prev.doctor_ids[0].id
                    
                    # 5️⃣ UHID Master Record (The main OP doctor)
                    if not doctor:
                        doctor = rec.mrd_no.doc_name.id

                    # 6️⃣ Fallback to Admission (only if UHID master has no doctor, which is unlikely)
                    if not doctor:
                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.mrd_no.id),
                            ('admission_date', '<=', bill_date)
                        ], order='admission_date desc', limit=1)
                        if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                            doctor = admission_log.attending_doctor.id

                # 3️⃣ Historical Snapshot (Only for IP bills)
                if not doctor and rec.bill_type == 'admitted':
                    historical_admission = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if historical_admission: doctor = historical_admission.doctor.id

                # 4️⃣ Master Record Fallback (Context-specific)
                if not doctor:
                    if rec.bill_type == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    def action_cancel(self):
        for rec in self:
            # Update current record
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount

    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if not rec.payment_method_split:
                if (rec.amount_paid < rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.net_amount - rec.amount_paid
                elif (rec.amount_paid > rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.amount_paid - rec.net_amount
                else:
                    rec.balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.net_amount or 0.0

            rec.amount_paid = int(cash + upi + card)
            rec.balance = int(total - (cash + upi + card))

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.net_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'

        # Return action to print PDF and show notification
        # return {
        #     'type': 'ir.actions.report',
        #     'report_name': 'homeo_doctor.report_casuality_Bill',
        #     'report_type': 'qweb-pdf',
        #     'context': {
        #         'active_ids': self.ids,
        #         'active_model': 'casuality.billing',
        #     },
        #     'target': 'new',
        # }

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
                 'rent')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name  <-- REMOVED TO SUPPORT REVISIT DOCTOR
            self.vssc_boolean = self.mrd_no.vssc_boolean
            self.admitted_date = self.mrd_no.admitted_date
            self.rent_full_day = self.mrd_no.rent_full
            self.rent_half_day = self.mrd_no.rent_half
            if self.mrd_no.status == 'admitted':
                self.bill_type = self.mrd_no.bill_type
                self.mode_pay = 'credit'
            else :
                self.bill_type = 'op'
                self.mode_pay = 'cash'

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars.particular_name == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.particular_name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('particular_name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.particular_name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    def password_validation(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 000001/24-25"""
        # ✅ FIX: Validate password BEFORE consuming sequence or creating the record.
        # If password_validation() is called after super().create(), a failed password
        # still increments the PostgreSQL sequence (sequences don't rollback!) → gaps in bill numbers.
        temp_record = self.new(vals)
        temp_record.password_validation()

        if vals.get('bill_number', 'New') == 'New':
            # today = datetime.now()
            today = fields.Date.context_today(self)

            # ✅ Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # Get the next sequence number
            # sequence_number = self.env['ir.sequence'].next_by_code('casuality.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('casuality.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        return super(CasualityBilling, self).create(vals)

    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    # def action_ip_print_general_bill(self):
    #     return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)


class CasualityBillLine(models.Model):
    _name = 'casuality.bill.line'

    bill_line_id = fields.Many2one('casuality.billing')
    particulars = fields.Many2one('general.dept.costing', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Float(string='Qty')
    total_amt = fields.Integer(string='Amount', compute="_compute_total")

    @api.onchange('rate')
    def _total_calculation(self):
        for line in self:
            # remove old total from parent first
            if line.id and line.total_amt:  # if record already has a value
                line.bill_line_id.total_amount -= line.total_amt

            # update line total
            line.total_amt = line.rate

            # add new total to parent
            line.bill_line_id.total_amount += line.total_amt

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            # tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate
            line.bill_line_id.total_amount += line.total_amt

    def unlink(self):
        for line in self:
            if line.bill_line_id:
                line.bill_line_id.total_amount -= line.total_amt
        return super(CasualityBillLine, self).unlink()


    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            rec.rate = rec.particulars.amount


class AudiologyBilling(models.Model):
    _name = 'audiology.billing'
    _description = 'Audiology Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID')
    audio_discharge = fields.Many2one('discharge.billing', string='UHID')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Date(string='Bill Date',default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name", 
                             readonly=False,)
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_types = fields.Many2one('bill.type', string='Bill Type')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type",required=True)
    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('audiology.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Float(string='Total Amount', compute='_compute_totals')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Float(string='Net Bill Amount', compute='_compute_totals')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff())
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")
    vssc_boolean = fields.Boolean(string='VSSC')
    advance_amount=fields.Integer(string='Advance amount')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    def write(self, vals):
        if self.env.context.get('no_sync'):
            return super(AudiologyBilling, self).write(vals)
        res = super(AudiologyBilling, self).write(vals)
        patient_fields = {'patient_name', 'mobile', 'age', 'gender'}
        if patient_fields & set(vals.keys()):
            for rec in self:
                if rec.mrd_no:
                    sync_vals = {}
                    if 'patient_name' in vals: sync_vals['patient_id'] = vals['patient_name']
                    if 'mobile' in vals: sync_vals['phone_number'] = vals['mobile']
                    if 'age' in vals: sync_vals['age'] = vals['age']
                    if 'gender' in vals: sync_vals['gender'] = vals['gender']
                    if sync_vals:
                        rec.mrd_no.sudo().write(sync_vals)
        return res

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)


    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0


    @api.model
    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.user.id)],
            limit=1
        )
        return employee.id or False
    @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.admitted_date', 'mrd_no.doctor', 'mrd_no.doc_name', 'bill_date', 'bill_type')
    def _compute_doctor_name(self):
        for rec in self:
            doctor = False
            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # Lookup Consultation (Revisit)
                reg_log = self.env["patient.registration"].search([
                    "|", ("user_id", "=", rec.mrd_no.id), ("patient_id", "=", rec.mrd_no.id),
                    ("date", "=", bill_date)
                ], order="date desc", limit=1)

                if not reg_log:
                    reg_log = self.env["patient.registration"].search([
                        "|", ("user_id", "=", rec.mrd_no.id), ("patient_id", "=", rec.mrd_no.id),
                        ("date", "<", bill_date)
                    ], order="date desc", limit=1)

                # Determine Priority based on Bill Type
                if rec.bill_type == 'admitted':
                    # 1️⃣ IP Priority: Admission logs
                    admission_log = self.env["hospital.admitted.patient"].sudo().search([
                        ("patient_id", "=", rec.mrd_no.id),
                        ("admission_date", "<=", bill_date)
                    ], order="admission_date desc", limit=1)
                    if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                        doctor = admission_log.attending_doctor.id

                    # 2. Fallback to Consultation
                    if not doctor and reg_log:
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            f_doc = self.env["doctor.profile"].search([("name", "=", reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        doctor = target_doctor
                    if not doctor:
                        reg_log = self.env['patient.registration'].search([
                            ('patient_id', '=', rec.mrd_no.id),
                            ('date', '<=', bill_date)
                        ], order='date desc', limit=1)
                        if reg_log: doctor = reg_log.doctor.id
                else:
                    # 1️⃣ OP Priority: Appointment for TODAY
                    appt_today = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='id desc', limit=1)
                    if appt_today and appt_today.doctor_ids:
                        doctor = appt_today.doctor_ids[0].id

                    # 2️⃣ OP Priority: Consultation logs for TODAY
                    if not doctor and (reg_log and reg_log.date == bill_date):
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        if target_doctor:
                            doctor = target_doctor
                    
                    # 3️⃣ Historical Consultation logs
                    if not doctor and reg_log:
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                            if f_doc: target_doctor = f_doc.id
                        if target_doctor:
                            doctor = target_doctor
                    
                    # 4️⃣ Historical Appointment Fallback (Latest confirmed)
                    if not doctor:
                        appt_prev = self.env['patient.appointment'].search([
                            ('patient_id', '=', rec.mrd_no.id),
                            ('appointment_date', '<', bill_date),
                            ('status', '=', 'confirmed')
                        ], order='appointment_date desc', limit=1)
                        if appt_prev and appt_prev.doctor_ids:
                            doctor = appt_prev.doctor_ids[0].id
                    
                    # 5️⃣ UHID Master Record (The main OP doctor)
                    if not doctor:
                        doctor = rec.mrd_no.doc_name.id

                        admission_log = self.env['hospital.admitted.patient'].sudo().search([
                            ('patient_id', '=', rec.mrd_no.id),
                            ('admission_date', '<=', bill_date)
                        ], order='admission_date desc', limit=1)
                        if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                            doctor = admission_log.attending_doctor.id

                # 3️⃣ Historical Snapshot (Only for IP bills)
                if not doctor and rec.bill_type == 'admitted':
                    historical_admission = self.env['discharged.patient.record'].sudo().search([
                        ('patient_id', '=', rec.mrd_no.reference_no),
                        ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                        ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                    ], limit=1)
                    if historical_admission: doctor = historical_admission.doctor.id

                # 4️⃣ Master Record Fallback (Context-specific)
                if not doctor:
                    if rec.bill_type == 'admitted':
                        doctor = rec.mrd_no.doctor.id
                    else:
                        doctor = rec.mrd_no.doc_name.id

            rec.doctor = doctor

    def action_cancel(self):
        for rec in self:
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount

    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if not rec.payment_method_split:
                if (rec.amount_paid < rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.net_amount - rec.amount_paid
                elif (rec.amount_paid > rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.amount_paid - rec.net_amount
                else:
                    rec.balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.net_amount or 0.0

            rec.amount_paid = int(cash + upi + card)
            rec.balance = int(total - (cash + upi + card))

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'

        # Return action to print PDF and show notification
        # return {
        #     'type': 'ir.actions.report',
        #     'report_name': 'homeo_doctor.report_ip_part_billing_document',
        #     'report_type': 'qweb-pdf',
        #     'context': {
        #         'active_ids': self.ids,
        #         'active_model': 'audiology.billing',
        #     },
        #     'target': 'new',
        # }

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
                 'rent',  'discount', 'advance_amount')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
            original = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
            discount = record.discount or 0
            advance = record.advance_amount or 0

            record.total_amount = original - discount - advance

            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name  <-- REMOVED TO SUPPORT REVISIT DOCTOR
            self.vssc_boolean = self.mrd_no.vssc_boolean
            self.admitted_date = self.mrd_no.admitted_date
            self.rent_full_day = self.mrd_no.rent_full
            self.rent_half_day = self.mrd_no.rent_half
            if self.mrd_no.status == 'admitted':
                self.bill_type = self.mrd_no.bill_type
                self.mode_pay = 'credit'
            else :
                self.bill_type = 'op'
                self.mode_pay = 'cash'

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars.name == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    def password_validation(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")

    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 000001/24-25"""
        # ✅ FIX: Validate password BEFORE consuming sequence or creating the record.
        # If password_validation() is called after super().create(), a failed password
        # still increments the PostgreSQL sequence (sequences don't rollback!) → gaps in bill numbers.
        temp_record = self.new(vals)
        temp_record.password_validation()

        if vals.get('bill_number', 'New') == 'New':
            # today = datetime.now()
            today = fields.Date.context_today(self)

            # ✅ Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # Get the next sequence number
            # sequence_number = self.env['ir.sequence'].next_by_code('audiology.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('audiology.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        return super(AudiologyBilling, self).create(vals)

    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars', 'general_bill_line_ids')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    # def action_ip_print_general_bill(self):
    #     return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)

    def action_print_audiology_disc_bill(self):
        return self.env.ref('homeo_doctor.report_audiology_bill_report_a5').report_action(self)

class audiologyBillLine(models.Model):
    _name = 'audiology.bill.line'

    bill_line_id = fields.Many2one('audiology.billing')
    particulars = fields.Many2one('audiology.test', string='Select particulars')
    rate = fields.Float(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Float(string='Qty', default=1.0)
    total_amt = fields.Float(string='Amount', compute="_compute_total")

    @api.onchange('particulars',)
    def _rate_auto_fill(self):
        for rec in self:
            if rec.particulars:
                rec.rate = rec.particulars.price

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate * (line.quantity or 1.0) * (1 + tax_amount / 100)


class XRAYBilling(models.Model):
    _name = 'xray.billing'
    _description = 'X Ray Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID')
    xray_id = fields.Many2one('discharge.billing', string='Discharge')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Date(string='Bill Date',default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name", 
                             readonly=False,)
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_types = fields.Many2one('bill.type', string='Bill Type')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type",required=True)
    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('xray.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Integer(string='Total Amount')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff())
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")
    vssc_boolean = fields.Boolean(string='VSSC')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    def action_print_xray_disc_bill(self):
        return self.env.ref('homeo_doctor.report_xray_bill_report').report_action(self)

    def write(self, vals):
        if self.env.context.get('no_sync'):
            return super(XRAYBilling, self).write(vals)
        res = super(XRAYBilling, self).write(vals)
        patient_fields = {'patient_name', 'mobile', 'age', 'gender'}
        if patient_fields & set(vals.keys()):
            for rec in self:
                if rec.mrd_no:
                    sync_vals = {}
                    if 'patient_name' in vals: sync_vals['patient_id'] = vals['patient_name']
                    if 'mobile' in vals: sync_vals['phone_number'] = vals['mobile']
                    if 'age' in vals: sync_vals['age'] = vals['age']
                    if 'gender' in vals: sync_vals['gender'] = vals['gender']
                    if sync_vals:
                        rec.mrd_no.sudo().write(sync_vals)
        return res

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0


    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id



    @api.depends('mrd_no', 'bill_date', 'bill_type')
    def _compute_doctor_name(self):
        import logging
        _logger = logging.getLogger(__name__)
        for rec in self:
            doctor_id = False
            if rec.mrd_no and rec.bill_date:
                # 0️⃣ Setup Patient & Date Context
                patient = rec.mrd_no
                # In Odoo 14 onchange/compute, use _origin to get the database ID
                patient_db_id = patient._origin.id if hasattr(patient, '_origin') and patient._origin.id else patient.id
                
                # If it's still a NewId (not yet saved), try to get the real ID from database by reference_no
                if not isinstance(patient_db_id, int):
                    real_p = self.env['patient.reg'].sudo().search([('reference_no', '=', patient.reference_no)], limit=1)
                    patient_db_id = real_p.id if real_p else 0

                bill_date = rec.bill_date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                _logger.info("[XRAY-DOC] Computing doctor for Patient: %s, BillDate: %s, BillType: %s",
                            patient.patient_id, bill_date, rec.bill_type)

                # 1️⃣ ADMITTED PATIENT PRIORITY
                if rec.bill_type == 'admitted':
                    admission_log = self.env["hospital.admitted.patient"].sudo().search([
                        ("patient_id", "=", patient_db_id),
                        ("admission_date", "<=", bill_date)
                    ], order="admission_date desc", limit=1)
                    
                    if admission_log:
                        if not admission_log.discharge_date or bill_date <= admission_log.discharge_date:
                            doctor_id = admission_log.attending_doctor.id
                            _logger.info("[XRAY-DOC] Priority 1 (IP): Active admission doctor")

                # 2️⃣ OP REVISIT PRIORITY (Check Appointments & Consultations)
                if not doctor_id:
                    # Priority A: Confirmed Appointment for TODAY
                    appt_today = self.env['patient.appointment'].sudo().search([
                        ('patient_id', '=', patient_db_id),
                        ('appointment_date', '=', bill_date),
                        ('status', 'in', ['confirmed', 'completed'])
                    ], order='id desc', limit=1)
                    
                    if appt_today and appt_today.doctor_ids:
                        doctor_id = appt_today.doctor_ids[0].id
                        _logger.info("[XRAY-DOC] Priority 2A: Today's appointment doctor")

                if not doctor_id:
                    # Priority B: Consultation Log (patient.registration) for TODAY
                    reg_today = self.env['patient.registration'].sudo().search([
                        '|', ('user_id', '=', patient_db_id), ('patient_id', '=', patient_db_id),
                        ('date', '=', bill_date)
                    ], order='id desc', limit=1)
                    
                    if reg_today and reg_today.doctor:
                        doctor_id = reg_today.doctor.id
                        _logger.info("[XRAY-DOC] Priority 2B: Today's consultation log doctor")

                if not doctor_id:
                    # Priority C: Latest Confirmed Appointment <= Today
                    appt_latest = self.env['patient.appointment'].sudo().search([
                        ('patient_id', '=', patient_db_id),
                        ('appointment_date', '<=', bill_date),
                        ('status', 'in', ['confirmed', 'completed'])
                    ], order='appointment_date desc, id desc', limit=1)
                    
                    if appt_latest and appt_latest.doctor_ids:
                        doctor_id = appt_latest.doctor_ids[0].id
                        _logger.info("[XRAY-DOC] Priority 2C: Latest past appointment doctor")

                if not doctor_id:
                    # Priority D: Latest Consultation Log <= Today
                    reg_prev = self.env['patient.registration'].sudo().search([
                        '|', ('user_id', '=', patient_db_id), ('patient_id', '=', patient_db_id),
                        ('date', '<=', bill_date)
                    ], order='date desc, id desc', limit=1)
                    
                    if reg_prev and reg_prev.doctor:
                        doctor_id = reg_prev.doctor.id
                        _logger.info("[XRAY-DOC] Priority 2D: Latest past consultation doctor")

                # 3️⃣ MASTER RECORD FALLBACK
                if not doctor_id:
                    if rec.bill_type == 'admitted' and patient.doctor:
                        doctor_id = patient.doctor.id
                    elif patient.doc_name:
                        doctor_id = patient.doc_name.id
                    _logger.info("[XRAY-DOC] Fallback: Master record doctor")

                _logger.info("[XRAY-DOC] Final Doctor ID: %s", doctor_id)

            rec.doctor = doctor_id

    def action_cancel(self):
        for rec in self:
            # Update current record
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount','quantity')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount


    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if not rec.payment_method_split:
                if (rec.amount_paid < rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.net_amount - rec.amount_paid
                elif (rec.amount_paid > rec.net_amount and rec.amount_paid > 0):
                    rec.balance = rec.amount_paid - rec.net_amount
                else:
                    rec.balance = 0

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.net_amount or 0.0

            rec.amount_paid = int(cash + upi + card)
            rec.balance = int(total - (cash + upi + card))

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'

        # Return action to print PDF and show notification
        # return {
        #     'type': 'ir.actions.report',
        #     'report_name': 'homeo_doctor.report_ip_part_billing_document',
        #     'report_type': 'qweb-pdf',
        #     'context': {
        #         'active_ids': self.ids,
        #         'active_model': 'ip.part.billing',
        #     },
        #     'target': 'new',
        # }

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
                 'rent')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name  <-- REMOVED TO SUPPORT REVISIT DOCTOR
            self.vssc_boolean = self.mrd_no.vssc_boolean
            self.admitted_date = self.mrd_no.admitted_date
            self.rent_full_day = self.mrd_no.rent_full
            self.rent_half_day = self.mrd_no.rent_half
            if self.mrd_no.status == 'admitted':
                self.bill_type = self.mrd_no.bill_type
                self.mode_pay = 'credit'
            else:
                self.bill_type = 'op'
                self.mode_pay = 'cash'

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars.name == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    def password_validation(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 000001/24-25"""
        # ✅ FIX: Validate password BEFORE consuming sequence or creating the record.
        # If password_validation() is called after super().create(), a failed password
        # still increments the PostgreSQL sequence (sequences don't rollback!) → gaps in bill numbers.
        temp_record = self.new(vals)
        temp_record.password_validation()

        if vals.get('bill_number', 'New') == 'New':
            # today = datetime.now()
            today = fields.Date.context_today(self)

            # ✅ Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # sequence_number = self.env['ir.sequence'].next_by_code('xray.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('xray.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        return super(XRAYBilling, self).create(vals)
    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    # def action_ip_print_general_bill(self):
    #     return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)


class XRAYBillLine(models.Model):
    _name = 'xray.bill.line'

    bill_line_id = fields.Many2one('xray.billing')
    particulars = fields.Many2one('xray.test', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Float(string='Qty')
    total_amt = fields.Integer(string='Amount', compute="_compute_total")


    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate * line.quantity * (1 + tax_amount / 100)

    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            rec.rate = rec.particulars.price


class OTBilling(models.Model):
    _name = 'ot.billing'
    _description = 'ot Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID')
    ot_discharge = fields.Many2one('discharge.billing', string='UHID')
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    bill_date = fields.Date(string='Bill Date',default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    doctor_manual = fields.Boolean(default=False, copy=False)
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_types = fields.Many2one('bill.type', string='Bill Type')
    bill_type = fields.Selection([
        ('op', 'OP'), ('admitted', 'IP'), ('others', 'Others')], string="Bill Type",required=True)
    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('ot.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', compute="_compute_totals")
    total_qty = fields.Char(string='Total Qty', compute="_compute_totals")
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Integer(string='Total Amount')
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff(), required=True)
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")
    vssc_boolean = fields.Boolean(string='VSSC')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    def write(self, vals):
        if self.env.context.get('no_sync'):
            return super(OTBilling, self).write(vals)

        res = super(OTBilling, self).write(vals)

        patient_fields = {'patient_name', 'mobile', 'age', 'gender'}
        if patient_fields & set(vals.keys()):
            for rec in self:
                if rec.mrd_no:
                    sync_vals = {}
                    if 'patient_name' in vals: sync_vals['patient_id'] = vals['patient_name']
                    if 'mobile' in vals: sync_vals['phone_number'] = vals['mobile']
                    if 'age' in vals: sync_vals['age'] = vals['age']
                    if 'gender' in vals: sync_vals['gender'] = vals['gender']

                    if sync_vals:
                        rec.mrd_no.sudo().write(sync_vals)
        return res

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0

    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    def _lookup_ot_doctor(self):
        self.ensure_one()
        if not self.mrd_no or not self.bill_date:
            return False

        bill_date = self.bill_date
        if isinstance(bill_date, datetime):
            bill_date = bill_date.date()

        reg_log = self.env['patient.registration'].search([
            '|', ('user_id', '=', self.mrd_no.id), ('patient_id', '=', self.mrd_no.id),
            ('date', '=', bill_date)
        ], order='date desc', limit=1)
        if not reg_log:
            reg_log = self.env['patient.registration'].search([
                '|', ('user_id', '=', self.mrd_no.id), ('patient_id', '=', self.mrd_no.id),
                ('date', '<', bill_date)
            ], order='date desc', limit=1)

        doctor = False
        if self.bill_type == 'admitted':
            admission_log = self.env['hospital.admitted.patient'].sudo().search([
                ('patient_id', '=', self.mrd_no.id),
                ('admission_date', '<=', bill_date)
            ], order='admission_date desc', limit=1)
            if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                doctor = admission_log.attending_doctor.id

            if not doctor and reg_log:
                target_doctor = reg_log.doctor.id
                if not target_doctor and getattr(reg_log, 'doctor_id', False):
                    f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                    if f_doc:
                        target_doctor = f_doc.id
                doctor = target_doctor
        else:
            appt_today = self.env['patient.appointment'].search([
                ('patient_id', '=', self.mrd_no.id),
                ('appointment_date', '=', bill_date),
                ('status', '=', 'confirmed')
            ], order='id desc', limit=1)
            if appt_today and appt_today.doctor_ids:
                doctor = appt_today.doctor_ids[0].id

            if not doctor and reg_log and reg_log.date == bill_date:
                target_doctor = reg_log.doctor.id
                if not target_doctor and reg_log.doctor_id:
                    f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                    if f_doc:
                        target_doctor = f_doc.id
                if target_doctor:
                    doctor = target_doctor

            if not doctor and reg_log:
                target_doctor = reg_log.doctor.id
                if not target_doctor and reg_log.doctor_id:
                    f_doc = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                    if f_doc:
                        target_doctor = f_doc.id
                if target_doctor:
                    doctor = target_doctor

            if not doctor:
                appt_prev = self.env['patient.appointment'].search([
                    ('patient_id', '=', self.mrd_no.id),
                    ('appointment_date', '<', bill_date),
                    ('status', '=', 'confirmed')
                ], order='appointment_date desc', limit=1)
                if appt_prev and appt_prev.doctor_ids:
                    doctor = appt_prev.doctor_ids[0].id

            if not doctor:
                doctor = self.mrd_no.doc_name.id

            if not doctor:
                admission_log = self.env['hospital.admitted.patient'].sudo().search([
                    ('patient_id', '=', self.mrd_no.id),
                    ('admission_date', '<=', bill_date)
                ], order='admission_date desc', limit=1)
                if admission_log and (not admission_log.discharge_date or bill_date <= admission_log.discharge_date):
                    doctor = admission_log.attending_doctor.id

        if not doctor and self.bill_type == 'admitted':
            historical_admission = self.env['discharged.patient.record'].sudo().search([
                ('patient_id', '=', self.mrd_no.reference_no),
                ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
            ], limit=1)
            if historical_admission:
                doctor = historical_admission.doctor.id

        if not doctor:
            doctor = self.mrd_no.doctor.id or self.mrd_no.doc_name.id

        return doctor or False

    @api.onchange('mrd_no')
    def _onchange_mrd_no_update_doctor(self):
        for rec in self:
            if rec.status in ['paid', 'cancelled']:
                continue
            if not rec.mrd_no or not rec.bill_date:
                continue
            rec.doctor = rec._lookup_ot_doctor()

    @api.onchange('bill_date', 'bill_type')
    def _onchange_bill_date_update_doctor(self):
        for rec in self:
            if rec.status in ['paid', 'cancelled'] or rec.doctor:
                continue
            if not rec.mrd_no or not rec.bill_date:
                continue
            rec.doctor = rec._lookup_ot_doctor()

    def action_cancel(self):
        for rec in self:
            # Update current record
            rec.status = 'cancelled'

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        self.observation = False
        if self.observation:
            self.observation_status = 'discharge'

    @api.onchange('discount', 'discount_type', 'total_amount')
    def _onchange_discount(self):
        """Calculate discount amount and net payable amount based on discount"""
        if self.total_amount:
            if self.discount_type == 'percentage' and self.discount:
                self.discount_amount = (self.total_amount * self.discount) / 100
            elif self.discount_type == 'amount' and self.discount:
                self.discount_amount = self.discount
            else:
                self.discount_amount = 0

            # Calculate net amount (payable amount after discount)
            self.net_amount = self.total_amount - self.discount_amount

    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if not rec.payment_method_split:
                total = rec.total_amount or 0.0
                paid = rec.amount_paid or 0.0
                rec.balance = int(total - paid)

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            if rec.payment_method_split:
                cash = rec.cash_amount or 0.0
                upi = rec.upi_amount or 0.0
                card = rec.card_amount or 0.0
                total = rec.total_amount or 0.0

                rec.amount_paid = int(cash + upi + card)
                rec.balance = int(total - (cash + upi + card))

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record.status = 'paid'

        # Return action to print PDF and show notification
        return self.env.ref('homeo_doctor.report_ot_bill_report').report_action(self)
    def action_print_ot_disc_bill(self):
        return self.env.ref('homeo_doctor.report_ot_bill_report').report_action(self)

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax','discount',
                 'rent')
    def _compute_totals(self):
        for record in self:
            record.total_item = len(record.general_bill_line_ids)
            record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
            record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
            original = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
            if record.discount >=0:
                record.total_amount = original-record.discount
            else:
                record.total_amount = original
            record.total_tax = sum(
                line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)

            record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent

    total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if self.mrd_no:
            self.patient_name = self.mrd_no.patient_id
            self.age = self.mrd_no.age
            self.gender = self.mrd_no.gender
            self.mobile = self.mrd_no.phone_number
            # self.doctor = self.mrd_no.doc_name  <-- REMOVED TO SUPPORT REVISIT DOCTOR
            self.vssc_boolean = self.mrd_no.vssc_boolean
            self.admitted_date = self.mrd_no.admitted_date
            self.rent_full_day = self.mrd_no.rent_full
            self.rent_half_day = self.mrd_no.rent_half
            if self.mrd_no.status == 'admitted':
                self.bill_type = self.mrd_no.bill_type
                self.mode_pay = 'credit'
            else:
                self.bill_type = 'op'
                self.mode_pay = 'cash'

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars.name == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    def password_validation(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
    @api.model
    def create(self, vals):
        # ✅ FIX 1: Validate password BEFORE consuming any sequence number or creating the record.
        # Previously, password_validation() was called AFTER super().create() which means:
        # - The PostgreSQL sequence was already incremented (sequences don't roll back on error!)
        # - Each failed password attempt permanently consumed a bill number → gaps like 3620 → 3626
        # By validating first, no sequence is wasted on failed attempts.
        temp_record = self.new(vals)
        temp_record.password_validation()

        if vals.get('bill_number', 'New') == 'New':
            # today = datetime.now()
            today = fields.Date.context_today(self)

            # ✅ Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # ✅ FIX 2: Get the next sequence number and assign it to vals BEFORE calling super().create()
            # Previously, vals['bill_number'] was set AFTER super().create(), so the DB record
            # was saved with bill_number = 'New' and never properly updated.
            # sequence_number = self.env['ir.sequence'].next_by_code('ot.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('ot.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        res = super(OTBilling, self).create(vals)
        return res
    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    # def action_ip_print_general_bill(self):
    #     return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)


class OTBillLine(models.Model):
    _name = 'ot.bill.line'
    _rec_name = 'particulars'

    bill_line_id = fields.Many2one('ot.billing')
    particulars = fields.Many2one('ot.test', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Float(string='Qty')
    total_amt = fields.Integer(string='Amount', compute="_compute_total")

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            line.total_amt = line.rate * line.quantity * (1 + tax_amount / 100)

    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            rec.rate = rec.particulars.price


class DischargeBilling(models.Model):
    _name = 'discharge.billing'
    _description = 'Discharge Billing'
    _rec_name = 'mrd_no'
    # _order = 'bill_date desc, bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"

    bill_number = fields.Char(string='Bill Number', copy=False, default='New')
    mrd_no = fields.Many2one('patient.reg', string='UHID',domain=[('status', 'in', ['admitted', 'proceed_discharge'])])
    patient_name = fields.Char(string='Patient Name')
    age = fields.Integer(string='Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    mobile = fields.Char(string='Mobile')
    # bill_date = fields.Date(string='Bill Date', default=lambda self: date.today())
    bill_date = fields.Date(string='Bill Date', default=fields.Date.context_today)
    op_category = fields.Many2one('op.category', string='OP Category')
    doctor = fields.Many2one('doctor.profile', string='Doctor')
    department = fields.Many2one('general.department', string='Department')
    particulars = fields.Many2one('general.dept.costing', string='Select Particulars')
    bill_type = fields.Many2one('bill.type', string='Bill Type')

    ip_no = fields.Char(string='IP No')
    general_bill_line_ids = fields.One2many('discharge.bill.line', 'bill_line_id')
    total_item = fields.Char(string='Total Item', )
    total_qty = fields.Char(string='Total Qty',)
    total_tax = fields.Char(string='Total Tax')
    total_amount = fields.Float(
        string='Total Amount',
        compute='_compute_total_unpaid_amount',
        compute_sudo=True,
    )
    settled_total_amount = fields.Float(
        string='Settled Total Amount', copy=False, readonly=True,
        help='Total frozen at discharge so it does not drop after department bills are marked paid.',
    )
    discount_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='percentage')
    discount = fields.Integer(string='Discount')
    oc_type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], default='amount',
                               string='O.C Type')
    oc = fields.Integer(string='O.C')
    reference = fields.Selection([('no', 'No'), ('yes', 'YES')], default='no', string='Reference')
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', default='cash')
    net_amount = fields.Integer(string='Net Bill Amount')
    payment_method_split = fields.Boolean(string="Payment Method Split")
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")

    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')

    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff())
    amount_paid = fields.Integer(string="Amount Paid")
    balance = fields.Integer(string="Balance")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('discharged', 'Discharged'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default="unpaid", tracking=True)

    amount_in_words = fields.Char("Total in Words", compute="_compute_amount_in_words")
    discount_amount = fields.Integer(string="Discount amount")
    rent = fields.Integer(string="Rent", Default=0)
    observation = fields.Boolean(string="Observation")
    observation_status = fields.Selection([
        ('observation', 'Observation'),
        ('discharge', 'Discharge')
    ], string="Status")
    admitted_date = fields.Date('Admitted Date')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('to Date')
    rent_full_day = fields.Float(string="Full Day Rent")
    rent_half_day = fields.Float(string="Half Day Rent")
    vssc_boolean = fields.Boolean(string='VSSC')
    admission_date = fields.Date(string='Admitted Date')
    insurance_name = fields.Many2one('insurance.model', string='Insurance')
    doctor_visiting_charge = fields.Float("Doctor Charge")
    service_charge = fields.Float("Service Charge")
    nurse_charge = fields.Float(string='Nursing Charge')
    rent_half = fields.Char('Rent Half Day')
    rent_full = fields.Char('Rent Full Day')
    # unpaid_general_ids = fields.One2many('general.billing','mrd_discharge_no', compute='_compute_all_totals', string="Unpaid General")
    # # unpaid_lab_ids = fields.One2many('doctor.lab.report', compute='_compute_unpaid_lab', string="Unpaid Lab")
    # # unpaid_pharmacy_ids = fields.One2many('pharmacy.description', compute='_compute_unpaid_pharmacy',
    # #                                       string="Unpaid Pharmacy")unpaid_general_ids
    #
    # paid_general_ids = fields.One2many('general.billing', 'mrd_discharge_no', string='Paid Bills',
    #                                    compute='_compute_all_totals')
    # # unpaid_general_ids = fields.One2many('general.billing', 'mrd_no', string='Unpaid Bills',
    # #                                      compute='_compute_unpaid_general')
    # paid_lab_ids = fields.One2many(
    #     'doctor.lab.report', 'user_ide_discharge', string="Paid Lab Bills", compute='_compute_all_totals', store=False)
    #
    # unpaid_lab_ids = fields.One2many(
    #     'doctor.lab.report', 'user_ide_discharge', string="Unpaid Lab Bills", compute='_compute_all_totals', store=False)
    # paid_lab_total = fields.Float(string="Paid Lab Total", compute='_compute_all_totals', store=False)
    # unpaid_lab_total = fields.Float(string="Unpaid Lab Total", compute='_compute_all_totals', store=False)
    # unpaid_general_total = fields.Float(string="Unpaid Lab Total", compute='_compute_all_totals', store=False)
    # paid_general_total = fields.Float(string="paid Lab Total", compute='_compute_all_totals', store=False)
    # paid_total = fields.Float(string="Total Paid", compute="_compute_all_totals")
    # unpaid_total = fields.Float(string="Total Unpaid", compute="_compute_all_totals")
    # grant_total = fields.Float(string="Grand Total", compute="_compute_all_totals")
    room_rent = fields.Float(string="Room Rent", compute="_compute_total_unpaid_amount", compute_sudo=True)
    paid_room_rent = fields.Float(string="Paid Room Rent")
    # unpaid_pharmacy_ids = fields.One2many(
    #     'pharmacy.description', 'uhid_id_discharge', string="Unpaid Pharmacy Bills", compute='_compute_all_totals',
    #     store=False)
    #
    # paid_pharmacy_ids = fields.One2many(
    #     'pharmacy.description', 'uhid_id_discharge', string="Paid Pharmacy Bills", compute='_compute_all_totals', store=False)
    paid_ip_ids = fields.Many2many(
        'ip.part.billing', string="Paid IP Bills", compute="_compute_all_totals", compute_sudo=True
    )
    unpaid_ip_ids = fields.One2many(
        'ip.part.billing', string="Unpaid IP Bills", compute="_compute_all_totals", compute_sudo=True
    )
    # unpaid_ot_ids = fields.One2many(
    #     'ot.billing', 'ot_discharge',string="Unpaid OT Bills", compute="_compute_all_totals",store=False,
    #
    # )
    # paid_ot_ids = fields.One2many(
    #     'ot.billing','ot_discharge', string="Paid OT Bills", compute="_compute_all_totals",store=False,
    #
    # )
    # unpaid_audiology_ids = fields.One2many(
    #     'audiology.billing','audio_discharge', string="Unpaid Audiology Bills", compute="_compute_all_totals",store=False,
    # )
    # paid_audiology_ids = fields.One2many(
    #     'audiology.billing', 'audio_discharge',string="Paid Audiology Bills", compute="_compute_all_totals",store=False,
    # )
    # unpaid_xray_ids = fields.One2many(
    #     'xray.billing','xray_id', string="Unpaid Xray Bills", compute="_compute_all_totals", store=False,
    # )
    # paid_xray_ids = fields.One2many(
    #     'xray.billing','xray_id', string="Paid Xray Bills", compute="_compute_all_totals", store=False,
    # )
    # unpaid_casualty_ids = fields.One2many(
    #     'casuality.billing','casualty_no', string="Unpaid Casualty Bills", compute="_compute_all_totals", store=False,
    # )
    # paid_casualty_ids = fields.One2many(
    #     'casuality.billing','casualty_no', string="Paid Casualty Bills", compute="_compute_all_totals", store=False,
    # )
    # paid_xray_total = fields.Float(string="Paid XRay Total", compute="_compute_all_totals")
    # unpaid_xray_total = fields.Float(string="Unpaid XRay Total", compute="_compute_all_totals")
    # paid_casualty_total = fields.Float(string="Paid Casualty Total", compute="_compute_all_totals")
    # unpaid_casualty_total = fields.Float(string="Unpaid Casualty Total", compute="_compute_all_totals")
    # paid_audiology_total = fields.Float(string="Paid Audiology Total", compute="_compute_all_totals")
    # unpaid_audiology_total = fields.Float(string="Unpaid Audiology Total", compute="_compute_all_totals")
    # paid_ot_total = fields.Float(string="Paid OT Total", compute="_compute_all_totals")
    # unpaid_ot_total = fields.Float(string="Unpaid OT Total", compute="_compute_all_totals")
    discharge_date = fields.Date(string='Discharge Date',default=fields.Date.today)
    admission_date_date = fields.Date(string='Admission Date')
    amount_in_advance = fields.Integer(string="Advance Amount",)
    admission_boolean = fields.Boolean(default=False)

    paid_general_ids = fields.One2many('general.billing', 'mrd_discharge_no', string='Paid Bills',
                                       compute='_compute_all_totals', store=False, compute_sudo=True)
    unpaid_general_ids = fields.One2many('general.billing', 'mrd_discharge_no', string='Unpaid Bills',
                                         compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_pharmacy_ids = fields.One2many('pharmacy.description', 'uhid_id_discharge', string="Paid Pharmacy",
                                        compute='_compute_all_totals', store=False, compute_sudo=True)
    unpaid_pharmacy_ids = fields.One2many('pharmacy.description', 'uhid_id_discharge', string="Unpaid Pharmacy",
                                          compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_lab_ids = fields.One2many('doctor.lab.report', 'user_ide_discharge', string="Paid Lab Bills",
                                   compute='_compute_all_totals', store=False, compute_sudo=True)
    unpaid_lab_ids = fields.One2many('doctor.lab.report', 'user_ide_discharge', string="Unpaid Lab Bills",
                                     compute='_compute_all_totals', store=False, compute_sudo=True)
    paid_ot_ids = fields.One2many('ot.billing', 'ot_discharge', string="Paid OT Bills", compute="_compute_all_totals",
                                  store=False, compute_sudo=True)
    unpaid_ot_ids = fields.One2many('ot.billing', 'ot_discharge', string="Unpaid OT Bills",
                                    compute="_compute_all_totals", store=False, compute_sudo=True)
    paid_audiology_ids = fields.One2many('audiology.billing', 'audio_discharge', string="Paid Audiology",
                                         compute="_compute_all_totals", store=False, compute_sudo=True)
    unpaid_audiology_ids = fields.One2many('audiology.billing', 'audio_discharge', string="Unpaid Audiology",
                                           compute="_compute_all_totals", store=False, compute_sudo=True)
    paid_xray_ids = fields.One2many('xray.billing', 'xray_id', string="Paid Xray", compute="_compute_all_totals",
                                    store=False, compute_sudo=True)
    unpaid_xray_ids = fields.One2many('xray.billing', 'xray_id', string="Unpaid Xray", compute="_compute_all_totals",
                                      store=False, compute_sudo=True)
    paid_casualty_ids = fields.One2many('casuality.billing', 'casualty_no', string="Paid Casualty",
                                        compute="_compute_all_totals", store=False, compute_sudo=True)
    unpaid_casualty_ids = fields.One2many('casuality.billing', 'casualty_no', string="Unpaid Casualty",
                                          compute="_compute_all_totals", store=False, compute_sudo=True)

    paid_total = fields.Float(string="Total Paid", compute="_compute_all_totals", store=False, compute_sudo=True)
    unpaid_total = fields.Float(string="Total Unpaid", compute="_compute_all_totals", store=False, compute_sudo=True)
    grant_total = fields.Float(string="Grand Total", compute="_compute_all_totals", store=False, compute_sudo=True)
    paid_lab_total = fields.Float(string="Paid Lab Total", compute="_compute_all_totals", store=False, compute_sudo=True)
    unpaid_lab_total = fields.Float(string="Unpaid Lab Total", compute="_compute_all_totals", store=False, compute_sudo=True)
    time=fields.Char(string='Time')
    reason_for_admission = fields.Text(
        string="Reason for Admission",
        compute="_compute_reason_for_admission",
        readonly=True,
    )

    @api.depends('mrd_no', 'bill_date')
    def _compute_reason_for_admission(self):
        for rec in self:
            rec.reason_for_admission = False

            if not rec.mrd_no:
                continue

            domain = [('patient_id', '=', rec.mrd_no.id)]
            if rec.bill_date:
                domain.append(('admission_date', '<=', rec.bill_date))

            admission_log = self.env['hospital.admitted.patient'].sudo().search(
                domain,
                order='admission_date desc, id desc',
                limit=1,
            )

            rec.reason_for_admission = admission_log.reason_for_admission or False



    def write(self, vals):
        if self.env.context.get('computing_discharge_totals'):
            return super(DischargeBilling, self).write(vals)
        if self.env.context.get('no_sync'):
            return super(DischargeBilling, self).write(vals)
        res = super(DischargeBilling, self).write(vals)
        patient_fields = {'patient_name', 'mobile', 'age', 'gender'}
        if patient_fields & set(vals.keys()):
            for rec in self:
                if rec.mrd_no:
                    sync_vals = {}
                    if 'patient_name' in vals: sync_vals['patient_id'] = vals['patient_name']
                    if 'mobile' in vals: sync_vals['phone_number'] = vals['mobile']
                    if 'age' in vals: sync_vals['age'] = vals['age']
                    if 'gender' in vals: sync_vals['gender'] = vals['gender']
                    if sync_vals:
                        rec.mrd_no.sudo().write(sync_vals)
        return res

    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                rec.fiscal_year_end = int(fy.split('-')[1])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0

    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    @api.onchange('mrd_no', 'bill_date')
    def _onchange_mrd_no_update_doctor(self):
        for rec in self:
            rec.doctor = False

            if not rec.mrd_no or not rec.bill_date:
                continue

            bill_date = rec.bill_date
            admitted_date = rec.mrd_no.admitted_date
            discharge_date = rec.mrd_no.discharge_date  # add this field if it exists in patient model

            # Normalize dates
            if admitted_date and isinstance(admitted_date, datetime):
                admitted_date = admitted_date.date()
            if discharge_date and isinstance(discharge_date, datetime):
                discharge_date = discharge_date.date()
            if isinstance(bill_date, datetime):
                bill_date = bill_date.date()

            # 1️⃣ Use admitted doctor only if bill_date is between admission and discharge
            if (
                    rec.mrd_no.admission_boolean
                    and admitted_date
                    and admitted_date <= bill_date
                    and (not discharge_date or bill_date <= discharge_date)
            ):
                if rec.mrd_no.doctor:
                    rec.doctor = rec.mrd_no.doctor.id
                    continue

            # 2️⃣ After discharge → find latest doctor from patient.reg or appointment
            latest_doc = False
            latest_date = None

            # Latest revisit (patient.reg)
            reg = self.env['patient.reg'].search([
                ('id', '=', rec.mrd_no.id if rec.mrd_no else rec.mrd_no.id),
                ('time', '<=', bill_date)
            ], order='time desc', limit=1)

            if reg and reg.doc_name:
                reg_date = reg.time.date() if isinstance(reg.time, datetime) else reg.time
                latest_doc = reg.doc_name.id
                latest_date = reg_date

            # Latest confirmed appointment (patient.appointment)
            appt = self.env['patient.appointment'].search([
                ('patient_id', '=', rec.mrd_no.id),
                ('appointment_date', '<=', bill_date),
                ('status', '=', 'confirmed')
            ], order='appointment_date desc', limit=1)

            if appt and appt.doctor_ids:
                appt_date = appt.appointment_date.date() if isinstance(appt.appointment_date,
                                                                       datetime) else appt.appointment_date
                # choose the most recent between revisit and appointment
                if not latest_date or appt_date > latest_date:
                    latest_doc = appt.doctor_ids[0].id
                    latest_date = appt_date

            rec.doctor = latest_doc

    @api.depends('mrd_no', 'mrd_no.admission_boolean', 'mrd_no.admitted_date', 'mrd_no.doctor', 'bill_date')
    def _compute_doctor_name(self):
        for rec in self:
            doctor = False

            if rec.mrd_no and rec.bill_date:
                bill_date = rec.bill_date
                admitted_date = rec.mrd_no.admitted_date

                # Convert datetime → date if needed
                if admitted_date and isinstance(admitted_date, datetime):
                    admitted_date = admitted_date.date()

                # 1️⃣ Priority 1: Admitted doctor
                if rec.mrd_no.admission_boolean and admitted_date and admitted_date <= bill_date:
                    if rec.mrd_no.doctor:
                        doctor = rec.mrd_no.doctor.id
                        _logger.warning('Admitted patient: using admitted doctor %s for record %s', doctor, rec.id)
                    else:
                        _logger.warning('Admitted patient has no doctor assigned! Record %s', rec.id)

                # 2️⃣ Priority 2: Outpatient reg doc_name (only if doctor not assigned yet)
                if not doctor:
                    reg = self.env['patient.reg'].search([
                        ('id', '=', rec.mrd_no.id),
                        ('time', '<=', bill_date)
                    ], limit=1)
                    if reg and reg.doc_name:
                        doctor = reg.doc_name.id
                        _logger.warning('Outpatient: using reg doctor %s for record %s', doctor, rec.id)

                # 3️⃣ Priority 3: Fallback to patient.appointment
                if not doctor:
                    revisit = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.mrd_no.id),
                        ('appointment_date', '<=', bill_date),
                        ('status', '=', 'confirmed')
                    ], limit=1)
                    if revisit and revisit.doctor_ids:
                        doctor = revisit.doctor_ids[0].id
                        _logger.warning('Fallback: using appointment doctor %s for record %s', doctor, rec.id)

            rec.doctor = doctor

    def _discharge_date_range_domain(self, date_field, admitted_date, end_date):
        domain = []
        if admitted_date:
            domain.append((date_field, '>=', admitted_date))
        if end_date:
            domain.append((date_field, '<=', end_date))
        return domain

    def _discharge_bill_date_domain(self, model_name, date_field, admitted_date, end_date):
        """All department bills within the admission → discharge window.

        Every bill (Cash, Credit, OP and IP) is fetched so the tree views show
        them. Whether a bill is *added to the Total Amount* is decided separately
        by ``_count_in_total`` (only IP credit bills are added).
        """
        Model = self.env[model_name]
        if date_field not in Model._fields:
            return []

        return self._discharge_date_range_domain(date_field, admitted_date, end_date)

    def _count_in_total(self, bill):
        """Only IP *credit* department bills are added to the discharge Total
        Amount. OP bills and Cash bills are still shown in the tree views but are
        NOT added to the total.
        """
        # OP bills never count toward the discharge total.
        if 'bill_type' in bill._fields:
            bt = bill.bill_type
            if isinstance(bt, str) and bt == 'op':
                return False
        elif 'op_category' in bill._fields:
            oc = bill.op_category
            if oc:
                name = oc if isinstance(oc, str) else (getattr(oc, 'name', '') or '')
                if (name or '').strip().lower() == 'op':
                    return False

        # Cash bills are excluded; only credit bills are added to the total.
        # (Pharmacy stores the mode in the misspelled field ``payment_mathod``.)
        mode = None
        for fname in ('mode_of_payment', 'mode_pay', 'payment_mathod'):
            if fname in bill._fields:
                mode = bill[fname]
                break
        if mode is None:
            return True
        return mode == 'credit'

    def _bill_amount(self, bill):
        if 'total_amount' in bill._fields:
            return bill.total_amount or 0
        if 'total_bill_amount' in bill._fields:
            return bill.total_bill_amount or 0
        return 0

    def _credit_total(self, bills):
        """Sum of the bills that count toward the discharge total (IP credit)."""
        return sum(self._bill_amount(b) for b in bills if self._count_in_total(b))

    @api.model
    def _discharge_dept_bill_specs(self):
        return {
            'general': ('general.billing', 'mrd_no', 'mrd_discharge_no', 'bill_date'),
            'pharmacy': ('pharmacy.description', 'uhid_id', 'uhid_id_discharge', 'date'),
            'lab': ('doctor.lab.report', 'user_ide', 'user_ide_discharge', 'date'),
            'ip': ('ip.part.billing', 'mrd_no', None, 'bill_date'),
            'ot': ('ot.billing', 'mrd_no', 'ot_discharge', 'bill_date'),
            'audiology': ('audiology.billing', 'mrd_no', 'audio_discharge', 'bill_date'),
            'xray': ('xray.billing', 'mrd_no', 'xray_id', 'bill_date'),
            'casualty': ('casuality.billing', 'mrd_no', 'casualty_no', 'bill_date'),
        }

    def _patient_or_discharge_domain(self, model_name, patient_field, discharge_field=None):
        self.ensure_one()
        Model = self.env[model_name]
        clauses = []
        if self.mrd_no and patient_field in Model._fields:
            clauses.append((patient_field, '=', self.mrd_no.id))
        if discharge_field and discharge_field in Model._fields:
            clauses.append((discharge_field, '=', self.id))
        if not clauses:
            return [('id', '=', False)]
        if len(clauses) == 1:
            return clauses
        return ['|'] + clauses

    def _search_discharge_dept_bills(
        self, model_name, patient_field, discharge_field,
        status_domain, date_field, admitted_date, end_date,
    ):
        self.ensure_one()
        if date_field not in self.env[model_name]._fields:
            return self.env[model_name]
        domain = self._patient_or_discharge_domain(model_name, patient_field, discharge_field)
        domain += list(status_domain)
        domain += self._discharge_bill_date_domain(model_name, date_field, admitted_date, end_date)
        return self.env[model_name].search(domain)

    def _assign_computed_x2many(self, record, field_name, recordset):
        """Set a computed x2many in cache (tuple of ids) without triggering write()."""
        field = record._fields[field_name]
        record.env.cache.set(record, field, tuple(recordset._ids))

    @api.depends('mrd_no', 'admitted_date', 'discharge_date', 'vssc_boolean')
    def _compute_all_totals(self):
        empty = {
            'general.billing': self.env['general.billing'],
            'pharmacy.description': self.env['pharmacy.description'],
            'doctor.lab.report': self.env['doctor.lab.report'],
            'ip.part.billing': self.env['ip.part.billing'],
            'ot.billing': self.env['ot.billing'],
            'audiology.billing': self.env['audiology.billing'],
            'xray.billing': self.env['xray.billing'],
            'casuality.billing': self.env['casuality.billing'],
        }

        for rec in self:
            if not rec.mrd_no:
                rec._assign_computed_x2many(rec, 'paid_general_ids', empty['general.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_general_ids', empty['general.billing'])
                rec._assign_computed_x2many(rec, 'paid_pharmacy_ids', empty['pharmacy.description'])
                rec._assign_computed_x2many(rec, 'unpaid_pharmacy_ids', empty['pharmacy.description'])
                rec._assign_computed_x2many(rec, 'paid_lab_ids', empty['doctor.lab.report'])
                rec._assign_computed_x2many(rec, 'unpaid_lab_ids', empty['doctor.lab.report'])
                rec._assign_computed_x2many(rec, 'paid_ip_ids', empty['ip.part.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_ip_ids', empty['ip.part.billing'])
                rec._assign_computed_x2many(rec, 'paid_ot_ids', empty['ot.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_ot_ids', empty['ot.billing'])
                rec._assign_computed_x2many(rec, 'paid_audiology_ids', empty['audiology.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_audiology_ids', empty['audiology.billing'])
                rec._assign_computed_x2many(rec, 'paid_xray_ids', empty['xray.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_xray_ids', empty['xray.billing'])
                rec._assign_computed_x2many(rec, 'paid_casualty_ids', empty['casuality.billing'])
                rec._assign_computed_x2many(rec, 'unpaid_casualty_ids', empty['casuality.billing'])
                rec.paid_lab_total = 0.0
                rec.unpaid_lab_total = 0.0
                rec.paid_total = 0.0
                rec.unpaid_total = 0.0
                rec.grant_total = 0.0
                continue

            admitted_date = rec.admission_date or rec.mrd_no.admitted_date
            end_date = rec.discharge_date or fields.Date.today()
            specs = rec._discharge_dept_bill_specs()

            def _fetch(key, paid_status):
                model, pat, dis, date_field = specs[key]
                return rec._search_discharge_dept_bills(
                    model, pat, dis, [paid_status], date_field, admitted_date, end_date,
                )

            paid_general = _fetch('general', ('status', '=', 'paid'))
            unpaid_general = _fetch('general', ('status', '=', 'unpaid'))
            paid_pharmacy = _fetch('pharmacy', ('status', '=', 'paid'))
            unpaid_pharmacy = _fetch('pharmacy', ('status', '=', 'unpaid'))
            paid_lab = _fetch('lab', ('status', '=', 'paid'))

            l_model, l_pat, l_dis, l_date = specs['lab']
            if not rec.vssc_boolean:
                unpaid_lab = rec._search_discharge_dept_bills(
                    l_model, l_pat, l_dis,
                    [('status', '=', 'unpaid'), ('mode_of_payment', '=', 'credit')],
                    l_date, admitted_date, end_date,
                )
            else:
                unpaid_lab = rec._search_discharge_dept_bills(
                    l_model, l_pat, l_dis,
                    [
                        '|',
                        ('status', '=', 'unpaid'),
                        '&',
                        ('status', '=', 'paid'),
                        ('mode_of_payment', '=', 'credit'),
                    ],
                    l_date, admitted_date, end_date,
                )

            paid_ip = _fetch('ip', ('status', '=', 'paid'))
            unpaid_ip = _fetch('ip', ('status', '=', 'unpaid'))
            paid_ot = _fetch('ot', ('status', '=', 'paid'))
            unpaid_ot = _fetch('ot', ('status', '=', 'unpaid'))
            paid_audiology = _fetch('audiology', ('status', '=', 'paid'))
            unpaid_audiology = _fetch('audiology', ('status', '=', 'unpaid'))
            paid_xray = _fetch('xray', ('status', '=', 'paid'))
            unpaid_xray = _fetch('xray', ('status', '=', 'unpaid'))
            paid_casualty = _fetch('casualty', ('status', '=', 'paid'))
            unpaid_casualty = _fetch('casualty', ('status', '=', 'unpaid'))

            rec._assign_computed_x2many(rec, 'paid_general_ids', paid_general)
            rec._assign_computed_x2many(rec, 'unpaid_general_ids', unpaid_general)
            rec._assign_computed_x2many(rec, 'paid_pharmacy_ids', paid_pharmacy)
            rec._assign_computed_x2many(rec, 'unpaid_pharmacy_ids', unpaid_pharmacy)
            rec._assign_computed_x2many(rec, 'paid_lab_ids', paid_lab)
            rec._assign_computed_x2many(rec, 'unpaid_lab_ids', unpaid_lab)
            rec._assign_computed_x2many(rec, 'paid_ip_ids', paid_ip)
            rec._assign_computed_x2many(rec, 'unpaid_ip_ids', unpaid_ip)
            rec._assign_computed_x2many(rec, 'paid_ot_ids', paid_ot)
            rec._assign_computed_x2many(rec, 'unpaid_ot_ids', unpaid_ot)
            rec._assign_computed_x2many(rec, 'paid_audiology_ids', paid_audiology)
            rec._assign_computed_x2many(rec, 'unpaid_audiology_ids', unpaid_audiology)
            rec._assign_computed_x2many(rec, 'paid_xray_ids', paid_xray)
            rec._assign_computed_x2many(rec, 'unpaid_xray_ids', unpaid_xray)
            rec._assign_computed_x2many(rec, 'paid_casualty_ids', paid_casualty)
            rec._assign_computed_x2many(rec, 'unpaid_casualty_ids', unpaid_casualty)

            # Tree views show ALL bills (the x2many fields above), but only IP
            # credit bills are summed into the totals (Cash / OP excluded).
            rec.paid_lab_total = rec._credit_total(paid_lab)
            rec.unpaid_lab_total = rec._credit_total(unpaid_lab)
            rec.paid_total = (
                rec._credit_total(paid_general)
                + rec._credit_total(paid_pharmacy)
                + rec._credit_total(paid_ip)
                + rec._credit_total(paid_ot)
                + rec._credit_total(paid_audiology)
                + rec._credit_total(paid_xray)
                + rec._credit_total(paid_casualty)
                + rec.paid_lab_total
            )
            rec.unpaid_total = (
                rec._credit_total(unpaid_general)
                + rec._credit_total(unpaid_pharmacy)
                + rec._credit_total(unpaid_ip)
                + rec._credit_total(unpaid_ot)
                + rec._credit_total(unpaid_audiology)
                + rec._credit_total(unpaid_xray)
                + rec._credit_total(unpaid_casualty)
                + rec.unpaid_lab_total
            )
            rec.grant_total = rec.paid_total + rec.unpaid_total

    def _get_discharge_date_range(self):
        """Return (admitted_date, end_date) used to filter IP bills."""
        self.ensure_one()
        admitted_date = self.admission_date or (
            self.mrd_no.admitted_date if self.mrd_no else False
        )
        end_date = self.discharge_date or fields.Date.today()
        return admitted_date, end_date

    def _get_patient_charge_vals(self):
        """Copy charge/rent fields from patient.reg when missing on discharge bill."""
        self.ensure_one()
        if not self.mrd_no:
            return {}
        mrd = self.mrd_no
        vals = {}
        field_map = {
            'admission_date': mrd.admitted_date,
            'rent_full': mrd.rent_full,
            'rent_half': mrd.rent_half,
            'nurse_charge': mrd.nurse_charge or 0.0,
            'doctor_visiting_charge': mrd.doctor_visiting_charge or 0.0,
            'service_charge': mrd.service_charge or 0.0,
        }
        for field, value in field_map.items():
            if value and not self[field]:
                vals[field] = value
        if mrd.vssc_boolean and not self.vssc_boolean:
            vals['vssc_boolean'] = True
        if mrd.rent_full and not self.rent_full_day:
            try:
                vals['rent_full_day'] = float(mrd.rent_full)
            except (TypeError, ValueError):
                pass
        if mrd.rent_half and not self.rent_half_day:
            try:
                vals['rent_half_day'] = float(mrd.rent_half)
            except (TypeError, ValueError):
                pass
        return vals

    def _sync_patient_charges(self):
        """Persist patient charge defaults before print / after UHID selection."""
        for rec in self:
            vals = rec._get_patient_charge_vals()
            # Discharged AND cancelled bills are frozen: their advance must stay at
            # the value applied while the bill was active. Cancelling re-credits the
            # advance to the wallet as an (undated) reversal row, so re-resolving it
            # here would wrongly drag the advance down to the registration baseline.
            if rec.status not in ('discharged', 'cancelled', 'paid'):
                # UNPAID bills show the patient's actual wallet balance as the
                # advance (same as normal billing). PAID / discharged / cancelled
                # bills keep the advance frozen — Pay consumes the wallet entry,
                # so re-resolving from wallet would wrongly drop advance to 0.
                if rec.status == 'unpaid':
                    advance = rec._resolve_wallet_balance_advance()
                else:
                    advance = rec._resolve_advance_amount()
                if rec.amount_in_advance != advance:
                    vals['amount_in_advance'] = advance
            if vals:
                rec.write(vals)

    def _resolve_advance_paid_during_stay(self):
        """Net advance (payments − refunds) recorded on the patient wallet during
        the admission → discharge window. Refunds reduce the advance, never a
        negative figure."""
        self.ensure_one()
        if not self.mrd_no:
            return 0
        admitted_date, end_date = self._get_discharge_date_range()
        if not admitted_date or not end_date:
            return 0
        wallet_records = self.env['patient.wallet'].search([
            ('uhid', '=', self.mrd_no.id),
            ('date', '>=', admitted_date),
            ('date', '<=', end_date),
        ])
        total_added = sum(wallet_records.mapped('amount_added') or [0.0])
        total_refunded = sum(wallet_records.mapped('refund') or [0.0])
        net = total_added - total_refunded
        return int(net) if net > 0 else 0

    def _resolve_cancelled_advance(self):
        """Advance actually retained by the patient on a CANCELLED bill.

        Same base as the normal advance — ``max(registration advance, positive
        wallet additions in the admission window)`` — but a refund recorded
        IN-WINDOW (either the ``refund`` field or a NEGATIVE ``amount_added``
        row, which is how this DB books advance reversals) is subtracted.
        Without this, ``max(registration, additions)`` floors the advance at the
        registration value even after the patient was fully refunded, so an
        already-refunded advance would wrongly wipe out the real charges (e.g. a
        5,000 advance refunded via a -10,000 row would still deduct 5,000 and
        zero a 3,001 bill).

        Only IN-WINDOW wallet rows are considered: undated / out-of-window
        refunds are deliberately ignored because they cannot be attributed to
        this admission (a patient with several admissions would otherwise have an
        unrelated refund cancel out this episode's genuine advance). Scoped to
        the cancelled flow only so unpaid/paid/discharged behaviour is unchanged.
        """
        self.ensure_one()
        if not self.mrd_no:
            return 0
        admitted_date, end_date = self._get_discharge_date_range()
        if not (admitted_date and end_date):
            return 0
        positive_added = 0
        refunds = 0
        wallet_records = self.env['patient.wallet'].search([
            ('uhid', '=', self.mrd_no.id),
            ('date', '>=', admitted_date),
            ('date', '<=', end_date),
        ])
        for row in wallet_records:
            added = row.amount_added or 0
            if added > 0:
                positive_added += added
            else:
                # Negative amount_added == advance reversal / refund.
                refunds += -added
            refunds += row.refund or 0

        base = max(int(self.mrd_no.amount_in_advance or 0), int(positive_added))
        net = base - int(refunds)
        return net if net > 0 else 0

    def _resolve_historical_advance_amount(self):
        """Restore advance for discharged bills from history or wallet."""
        self.ensure_one()
        if self.amount_in_advance:
            return int(self.amount_in_advance)

        DischargedRecord = self.env['discharged.patient.record'].sudo()
        history = DischargedRecord.browse()
        if self.mrd_no:
            history = DischargedRecord.search([
                ('patient_id', '=', self.mrd_no.reference_no),
            ], order='discharge_date desc', limit=1)
            if not history:
                history = DischargedRecord.search([
                    ('name', '=', self.mrd_no.patient_id),
                ], order='discharge_date desc', limit=1)
        elif self.patient_name:
            history = DischargedRecord.search([
                ('name', '=', self.patient_name),
            ], order='discharge_date desc', limit=1)

        if history and history.amount_in_advance:
            try:
                return int(float(history.amount_in_advance))
            except (TypeError, ValueError):
                pass

        return self._resolve_advance_paid_during_stay()

    def _resolve_advance_amount(self):
        """Advance shown on the bill.

        The advance BASE is the larger of the registration advance
        (``mrd_no.amount_in_advance``) and the wallet advances actually recorded
        during the admission → discharge window. Refunds recorded in that window
        are then subtracted, clamped at >= 0. Using ``max(base) − refund`` keeps
        a normal advance intact (refund 0 → full advance) even when the
        admission advance was never written as a dated wallet ``amount_added``
        row, while still reflecting refunds (full refund → 0).
        """
        self.ensure_one()
        if self.status == 'discharged':
            return self._resolve_historical_advance_amount()
        if not self.mrd_no:
            return 0

        total_added = 0
        total_refunded = 0
        admitted_date, end_date = self._get_discharge_date_range()
        if admitted_date and end_date:
            wallet_records = self.env['patient.wallet'].search([
                ('uhid', '=', self.mrd_no.id),
                ('date', '>=', admitted_date),
                ('date', '<=', end_date),
            ])
            total_added = sum(wallet_records.mapped('amount_added') or [0.0])
            total_refunded = sum(wallet_records.mapped('refund') or [0.0])

        # Undated refund rows (date == False) never match the dated window above,
        # so a refund saved without a date would otherwise be ignored and leave
        # the advance overstated. Include such refunds once for this patient so a
        # refund always reduces the advance regardless of the row's date.
        undated_refunds = self.env['patient.wallet'].search([
            ('uhid', '=', self.mrd_no.id),
            ('date', '=', False),
            ('refund', '!=', 0),
        ])
        total_refunded += sum(undated_refunds.mapped('refund') or [0.0])

        base = max(int(self.mrd_no.amount_in_advance or 0), int(total_added))
        net = base - int(total_refunded)
        if net > 0:
            return net

        # Nothing recorded anywhere: fall back to the latest wallet balance.
        if base == 0 and int(total_refunded) == 0:
            wallet = self.env['patient.wallet'].search(
                [('uhid', '=', self.mrd_no.id)],
                order='id desc',
                limit=1,
            )
            return int(wallet.balance or 0) if wallet else 0

        # Advance was fully refunded.
        return 0

    def _resolve_wallet_balance_advance(self):
        """Advance = the patient's ACTUAL cumulative wallet balance (latest
        ``patient.wallet`` row's ``balance`` for this UHID).

        This is the single source of truth for the advance, used for unpaid bills
        (onchange / save) AND captured at discharge before the value is frozen.
        Because it reads the running ``balance`` it inherently sums every deposit
        (e.g. 10,000 across two 5,000 deposits) instead of collapsing to the first
        deposit / registration figure (5,000) the window-based resolver returns.
        Falls back to the registration advance only when no wallet row exists.
        """
        self.ensure_one()
        if self.mrd_no:
            wallet = self.env['patient.wallet'].search(
                [('uhid', '=', self.mrd_no.id)],
                order='id desc',
                limit=1,
            )
            if wallet:
                return int(wallet.balance or 0)
        # No wallet row at all: fall back to the registration advance.
        return int(self.mrd_no.amount_in_advance or 0) if self.mrd_no else 0

    def _get_advance_amount(self):
        """Advance shown on bill — stored value, else resolved."""
        self.ensure_one()
        if self.amount_in_advance:
            return self.amount_in_advance
        if self.status == 'discharged':
            return self._resolve_historical_advance_amount()
        return self._resolve_advance_amount()

    def _get_room_rent_and_extras(self):
        """Room rent and nurse/doctor/service charges for discharge total."""
        self.ensure_one()
        rent_full_value = 0.0
        rent_half_value = 0.0
        if self.rent_full:
            try:
                rent_full_value = float(self.rent_full)
            except (TypeError, ValueError):
                pass
        elif self.rent_full_day:
            rent_full_value = self.rent_full_day

        if self.rent_half:
            try:
                rent_half_value = float(self.rent_half)
            except (TypeError, ValueError):
                pass
        elif self.rent_half_day:
            rent_half_value = self.rent_half_day

        room_rent = 0.0
        if self.admission_date and self.discharge_date:
            admitted = self.admission_date
            discharge = self.discharge_date
            if isinstance(admitted, str):
                admitted = fields.Date.from_string(admitted)
            if isinstance(discharge, str):
                discharge = fields.Date.from_string(discharge)
            if hasattr(admitted, 'date'):
                admitted = admitted.date()
            if hasattr(discharge, 'date'):
                discharge = discharge.date()

            delta_days = (discharge - admitted).days
            room_rent = (max(delta_days, 0) * rent_full_value) - (self.paid_room_rent or 0.0)
            if delta_days == 0 and rent_half_value:
                room_rent += rent_half_value

        extra_charges = (
            (self.nurse_charge or 0.0)
            + (self.doctor_visiting_charge or 0.0)
            + (self.service_charge or 0.0)
        )
        return room_rent, extra_charges

    def _search_department_bills_for_discharge(self):
        """All department IP bills from admission date through discharge date."""
        self.ensure_one()
        if not self.mrd_no:
            return {}

        admitted_date, end_date = self._get_discharge_date_range()

        def _dept_domain(date_field):
            domain = [
                ('mrd_no', '=', self.mrd_no.id),
                ('status', '!=', 'cancelled'),
            ]
            if admitted_date:
                domain.append((date_field, '>=', admitted_date))
            if end_date:
                domain.append((date_field, '<=', end_date))
            return domain

        lab_domain = [
            ('user_ide', '=', self.mrd_no.id),
            ('status', '!=', 'cancelled'),
        ]
        if admitted_date:
            lab_domain.append(('date', '>=', admitted_date))
        if end_date:
            lab_domain.append(('date', '<=', end_date))

        pharmacy_domain = [
            ('uhid_id', '=', self.mrd_no.id),
            ('status', '!=', 'cancelled'),
        ]
        if admitted_date:
            pharmacy_domain.append(('date', '>=', admitted_date))
        if end_date:
            pharmacy_domain.append(('date', '<=', end_date))

        ip_domain = [
            ('mrd_no', '=', self.mrd_no.id),
            ('status', '!=', 'cancelled'),
        ]
        if admitted_date:
            ip_domain.append(('bill_date', '>=', admitted_date))
        if end_date:
            ip_domain.append(('bill_date', '<=', end_date))

        return {
            'general': self.env['general.billing'].search(_dept_domain('bill_date')),
            'pharmacy': self.env['pharmacy.description'].search(pharmacy_domain),
            'lab': self.env['doctor.lab.report'].search(lab_domain),
            'ip': self.env['ip.part.billing'].search(ip_domain),
            'ot': self.env['ot.billing'].search(_dept_domain('bill_date')),
            'audiology': self.env['audiology.billing'].search(_dept_domain('bill_date')),
            'xray': self.env['xray.billing'].search(_dept_domain('bill_date')),
            'casualty': self.env['casuality.billing'].search(_dept_domain('bill_date')),
        }

    def _search_unpaid_bills_for_discharge(self):
        """Unpaid (or paid when discharged) department bills — used by bill tabs."""
        self.ensure_one()
        if not self.mrd_no:
            return {}

        admitted_date, end_date = self._get_discharge_date_range()
        # Only switch to paid-bill search after discharge settles department bills.
        # Status 'paid' means discharge bill was paid — dept bills may still be unpaid.
        bills_settled = self.status == 'discharged'

        def _unpaid_domain(date_field):
            domain = [('mrd_no', '=', self.mrd_no.id)]
            if bills_settled:
                domain.append(('status', '=', 'paid'))
            else:
                domain.append(('status', '=', 'unpaid'))
            if admitted_date:
                domain.append((date_field, '>=', admitted_date))
            if end_date:
                domain.append((date_field, '<=', end_date))
            return domain

        lab_domain = [('user_ide', '=', self.mrd_no.id)]
        if admitted_date:
            lab_domain.append(('date', '>=', admitted_date))
        if end_date:
            lab_domain.append(('date', '<=', end_date))
        if bills_settled:
            lab_domain.append(('status', '=', 'paid'))
        elif not self.vssc_boolean:
            lab_domain.extend([('status', '=', 'unpaid'), ('mode_of_payment', '=', 'credit')])
        else:
            lab_domain.extend([
                '|',
                ('status', '=', 'unpaid'),
                '&',
                ('status', '=', 'paid'),
                ('mode_of_payment', '=', 'credit'),
            ])

        pharmacy_domain = [('uhid_id', '=', self.mrd_no.id)]
        if bills_settled:
            pharmacy_domain.append(('status', '=', 'paid'))
        else:
            pharmacy_domain.append(('status', '=', 'unpaid'))
        if admitted_date:
            pharmacy_domain.append(('date', '>=', admitted_date))
        if end_date:
            pharmacy_domain.append(('date', '<=', end_date))

        ip_domain = [('mrd_no', '=', self.mrd_no.id)]
        if bills_settled:
            ip_domain.append(('status', '=', 'paid'))
        else:
            ip_domain.append(('status', '=', 'unpaid'))
        if admitted_date:
            ip_domain.append(('bill_date', '>=', admitted_date))
        if end_date:
            ip_domain.append(('bill_date', '<=', end_date))

        return {
            'general': self.env['general.billing'].search(_unpaid_domain('bill_date')),
            'pharmacy': self.env['pharmacy.description'].search(pharmacy_domain),
            'lab': self.env['doctor.lab.report'].search(lab_domain),
            'ip': self.env['ip.part.billing'].search(ip_domain),
            'ot': self.env['ot.billing'].search(_unpaid_domain('bill_date')),
            'audiology': self.env['audiology.billing'].search(_unpaid_domain('bill_date')),
            'xray': self.env['xray.billing'].search(_unpaid_domain('bill_date')),
            'casualty': self.env['casuality.billing'].search(_unpaid_domain('bill_date')),
        }

    def _compute_historical_discharge_total(self):
        """Rebuild total for old discharged records that have no frozen amount."""
        self.ensure_one()
        if self.net_amount:
            return float(self.net_amount)
        return self._calculate_discharge_amounts()['net_amount']

    def _get_discharged_display_total(self):
        """Net total for discharged records — always deduct advance if present."""
        self.ensure_one()
        return self._calculate_discharge_amounts()['net_amount']

    @api.model
    def _backfill_settled_totals(self):
        """Persist totals for discharged records created before settled_total_amount existed."""
        records = self.search([
            ('status', '=', 'discharged'),
            '|',
            ('settled_total_amount', '=', False),
            ('settled_total_amount', '=', 0),
        ])
        for rec in records:
            total = rec._get_discharged_display_total()
            if total:
                rec.write({'settled_total_amount': total})

    @api.model
    def _restore_discharge_advance_amounts(self):
        """Backfill advance on old discharged bills from history / wallet."""
        for rec in self.search([('status', '=', 'discharged')]):
            advance = rec._resolve_historical_advance_amount()
            if advance and rec.amount_in_advance != advance:
                rec.write({'amount_in_advance': advance})

    @api.model
    def _restore_discharge_list_totals(self):
        """Recalculate and store totals (with advance deducted) for discharged bills."""
        for rec in self.search([('status', '=', 'discharged')]):
            net = rec._calculate_discharge_amounts()['net_amount']
            vals = {}
            if abs((rec.settled_total_amount or 0) - net) > 0.01:
                vals['settled_total_amount'] = net
            if vals:
                rec.write(vals)
            elif abs((rec.total_amount or 0) - net) > 0.01:
                rec.write({'settled_total_amount': rec.settled_total_amount or net})

    def init(self):
        super(DischargeBilling, self).init()

    @api.model
    def _run_discharge_data_migrations(self):
        """One-time data fixes — run on module upgrade only, not every server start."""
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param('homeo_doctor.discharge_totals_backfilled') != '1':
            self._backfill_settled_totals()
            icp.set_param('homeo_doctor.discharge_totals_backfilled', '1')
        if icp.get_param('homeo_doctor.discharge_list_totals_restored') != '3':
            self._restore_discharge_list_totals()
            icp.set_param('homeo_doctor.discharge_list_totals_restored', '3')
        if icp.get_param('homeo_doctor.discharge_advance_restored') != '1':
            self._restore_discharge_advance_amounts()
            icp.set_param('homeo_doctor.discharge_advance_restored', '1')

    def _calculate_discharge_amounts(self):
        """Single source of truth — dept bills + tree + room/charges − advance − discount."""
        self.ensure_one()

        if self.status not in ('discharged', 'paid'):
            self._sync_patient_charges()
        self._compute_all_totals()

        discharge_lines_total = sum(self.general_bill_line_ids.mapped('total_amt') or [0.0])
        room_rent, extra_charges = self._get_room_rent_and_extras()
        advance = self._get_advance_amount()

        if self.status in ('discharged', 'paid', 'cancelled'):
            # Settled bills: count ALL department bills (paid + unpaid) so the
            # total stays stable once bills get marked paid.
            department_bills_total = self.grant_total
        else:
            department_bills_total = self.unpaid_total

        gross_total = (
            department_bills_total
            + discharge_lines_total
            + room_rent
            + extra_charges
        )

        discount = self.discount if (self.discount and self.discount > 0) else 0

        # Full bill after discount, advance NOT deducted (shown for paid bills).
        settled_amount = gross_total - discount
        # Outstanding balance — advance also deducted (shown for unpaid bills).
        net_amount = settled_amount
        if advance > 0:
            net_amount -= advance

        return {
            'department_bills_total': department_bills_total,
            'unpaid_bills_total': department_bills_total,
            'room_rent': room_rent,
            'extra_charges': extra_charges,
            'discharge_lines_total': discharge_lines_total,
            'gross_total': gross_total,
            'settled_amount': settled_amount,
            'net_amount': net_amount,
        }

    def get_discharge_bill_line_total(self):
        """Discharge Bill PDF total — sum of tree view lines only."""
        self.ensure_one()
        return sum(self.general_bill_line_ids.mapped('total_amt') or [0.0])

    def get_discharge_report_totals(self):
        """Totals for consolidated PDF — gross before deductions, net after.

        ``net_amount`` is the Total Amount shown on the bill, which already
        reflects the mode-based advance rule (credit bills keep the advance
        separate; cash / card / upi / cheque bills subtract the stored advance).
        ``gross_total = net + advance + discount`` so the report's
        "Grand Total − Discount − Advance = Net Payable" stays consistent and the
        value never depends on the (now unused) frozen ``settled_total_amount``.
        """
        self.ensure_one()
        amounts = self._calculate_discharge_amounts()
        settled = amounts['settled_amount']           # true gross − discount
        discount = self.discount or 0
        # True grand total before any deduction (never inflated by the advance).
        gross_total = settled + discount

        # Net = the Total Amount shown on the form, which already applies the
        # mode-based advance rule so the PDF and the form always agree.
        net_amount = self.total_amount
        if net_amount is None or net_amount is False:
            net_amount = settled - (self.amount_in_advance or 0)

        # Advance actually applied on this bill = the part that reduced the net.
        # Derived so the printed "Grand − Discount − Advance = Net" always ties
        # out: credit bills (net == settled) show 0, cash bills show the advance,
        # and over-paid cash bills show only the consumed portion.
        advance = settled - net_amount
        if advance < 0:
            advance = 0

        return {
            'gross_total': gross_total,
            'net_amount': net_amount,
            'advance': advance,
        }

    @api.depends(
        'mrd_no',
        'mrd_no.admitted_date',
        'bill_date',
        'vssc_boolean',
        'admission_date',
        'discharge_date',
        'status',
        'settled_total_amount',
        'rent_half',
        'rent_full',
        'rent_full_day',
        'rent_half_day',
        'nurse_charge',
        'doctor_visiting_charge',
        'service_charge',
        'discount',
        'amount_in_advance',
        'amount_paid',
        'mode_pay',
        'paid_room_rent',
        'general_bill_line_ids.total_amt',
    )
    def _compute_total_unpaid_amount(self):
        for rec in self:
            if not rec.mrd_no:
                rec.total_amount = sum(rec.general_bill_line_ids.mapped('total_amt') or [0.0])
                rec.net_amount = rec.total_amount
                rec.room_rent = 0.0
                continue

            if rec.status == 'discharged':
                # Total = gross − discount, then subtract the advance ONLY for
                # non-credit bills. Credit bills are billed in full to the
                # insurance/company so the advance is kept separate (not deducted);
                # cash / card / upi / cheque bills are paid by the patient, so the
                # advance stored on the bill is subtracted from the total.
                total = rec._calculate_discharge_amounts()['settled_amount']
                if rec.mode_pay != 'credit':
                    total -= (rec.amount_in_advance or 0)
                rec.total_amount = total
                rec.net_amount = int(total)
                room_rent, _extras = rec._get_room_rent_and_extras()
                rec.room_rent = room_rent
                continue

            if rec.status == 'paid':
                # Same rule as discharged: credit bills keep the advance separate,
                # non-credit (cash/card/upi/cheque) bills subtract the stored advance.
                total = rec._calculate_discharge_amounts()['settled_amount']
                if rec.mode_pay != 'credit':
                    total -= (rec.amount_in_advance or 0)
                rec.total_amount = total
                rec.net_amount = int(total)
                rec.room_rent = rec._get_room_rent_and_extras()[0]
                continue

            if rec.status == 'cancelled':
                # A genuinely frozen positive total must not change after cancel
                # (advance refund / reverting dept bills to unpaid must not move
                # it), so keep it as-is when one was stored.
                if rec.settled_total_amount:
                    total = rec.settled_total_amount
                else:
                    # No positive frozen total: derive it from the real charges
                    # minus the advance the patient ACTUALLY retained. A refund
                    # booked as a negative amount_added must reduce the advance,
                    # otherwise an already-refunded advance wrongly zeroes out the
                    # real billable charges (e.g. shows 0 instead of the tree
                    # amount). settled_amount is gross − discount, advance NOT yet
                    # deducted; subtract the refund-aware advance here.
                    amounts = rec._calculate_discharge_amounts()
                    total = amounts['settled_amount'] - rec._resolve_cancelled_advance()
                # Cancelled totals never go negative: clamp at 0.
                if total < 0:
                    total = 0
                rec.total_amount = total
                rec.net_amount = int(total)
                rec.room_rent = rec._get_room_rent_and_extras()[0]
                continue

            # Unpaid: Total Amount = bill charges (gross − discount) with the
            # advance already applied, mirroring the paid/discharged branches so
            # the figure the cashier collects reflects the advance. Credit bills
            # are billed in full to the insurance/company, so the advance is kept
            # separate (not deducted); cash / card / upi / cheque bills net the
            # stored advance. A negative total means advance exceeds charges
            # (refund due to the patient).
            amounts = rec._calculate_discharge_amounts()
            total = amounts['settled_amount']
            advance = 0 if rec.mode_pay == 'credit' else (rec.amount_in_advance or 0)
            total -= advance
            rec.total_amount = total
            rec.net_amount = int(total)
            rec.room_rent = amounts['room_rent']
            # Balance / net payable = Total − Amount Paid (advance already netted).
            rec.balance = int(total) - int(rec.amount_paid or 0)
    def get_grouped_general_lines(self):
        grouped = defaultdict(lambda: {'quantity': 0, 'total_amt': 0})
        for line in self.unpaid_general_ids.mapped('general_bill_line_ids'):
            key = line.particulars.display_name
            grouped[key]['quantity'] += line.quantity or 0
            grouped[key]['total_amt'] += line.total_amt or 0
        return [{'name': k, 'quantity': v['quantity'], 'total_amt': v['total_amt']}
                for k, v in grouped.items()]

    # def action_cancel(self):
    #     for rec in self:
    #         rec.status = 'cancelled'
    #         rec.mrd_no.status = 'admitted'
    #
    #         all_bill_groups = [
    #             rec.paid_general_ids,
    #             rec.paid_pharmacy_ids,
    #             rec.paid_lab_ids,
    #             rec.paid_ot_ids,
    #             rec.paid_audiology_ids,
    #             rec.paid_xray_ids,
    #             rec.paid_casualty_ids,
    #         ]
    #
    #         for group in all_bill_groups:
    #             paid_bills = group.filtered(lambda b: b.status == 'paid')
    #             paid_bills.write({'status': 'unpaid'})

    def action_cancel(self):
        for rec in self:
            prev_status = rec.status
            # Freeze the total at its pre-cancel value so refunding the advance
            # and reverting dept bills to unpaid does not change the Total Amount.
            frozen_total = rec.total_amount
            rec.status = 'cancelled'
            rec.settled_total_amount = frozen_total

            # 2️⃣ Restore patient to admitted
            if rec.mrd_no:
                rec.mrd_no.status = 'admitted'
                rec.mrd_no.admission_boolean = True

                # 3️⃣ Restore hospital admission record
                admitted_patient = self.env['hospital.admitted.patient'].search([
                    ('patient_id', '=', rec.mrd_no.id)
                ], limit=1)
                if admitted_patient:
                    admitted_patient.status = 'admitted'

            if rec.amount_in_advance > 0 and prev_status !='unpaid':

                wallet_rec = self.env['patient.wallet'].create({
                    'uhid': rec.mrd_no.id,
                    'patient_name': rec.patient_name,
                    'amount_in_inr': rec.amount_in_advance,
                    'Staff_name': rec.staff_name.id if rec.staff_name else False,
                    'payment_mode': rec.mode_pay,
                    'date':False,
                    'status':rec.status,
                })
                wallet_rec.action_add_amount()

        all_bill_groups = [
            rec.paid_general_ids,
            rec.paid_pharmacy_ids,
            rec.paid_lab_ids,
            rec.paid_ot_ids,
            rec.paid_audiology_ids,
            rec.paid_xray_ids,
            rec.paid_casualty_ids,
        ]
        for group in all_bill_groups:

            for bill in group:

                if bill.status != 'paid':
                    continue

                # Skip OP bills
                if 'bill_type' in bill._fields and bill.bill_type == 'op':
                    continue

                if 'op_category' in bill._fields and bill.op_category == 'op':
                    continue

                bill.write({'status': 'unpaid'})

                print('UPDATED:', bill)
        # for group in all_bill_groups:
        #     paid_bills = group.filtered(
        #         lambda b: b.status == 'paid' and b.bill_type != 'op'  or
        #         ('op_category' in b._fields and b.op_category != 'op')
        #     )
        #
        #     paid_bills.write({'status': 'unpaid'})
        #     print('jhdhjsfhjsdhfgjsdg',  paid_bills)
        #

    def action_reopen(self):
        """Re-open a CANCELLED discharge bill so it can be paid again like a
        normal unpaid bill. Mirrors / undoes what ``action_cancel`` did:

        - status: cancelled → unpaid, so the normal Pay flow (``action_pay_button``)
          and the live total recompute apply again.
        - advance: ``action_cancel`` re-credited the advance to the patient wallet
          (an undated, ``status='cancelled'`` row whose ``action_add_amount`` added
          ``amount_in_advance`` back to the balance). Re-opening posts an equal,
          offsetting negative wallet row so the cancel→reopen pair nets to zero and
          the subsequent Pay consumes the advance exactly once (never lost, never
          doubled). ``amount_in_advance`` itself is left untouched here and is
          re-resolved by the normal unpaid path (``_sync_patient_charges``).
        - settled_total_amount: cleared so the total recomputes live for unpaid.
        - patient / admission status: restored to the proceed-discharge state so
          the bill behaves like a normal payable discharge bill again.

        Department bills were reverted to 'unpaid' by cancel, which is already the
        correct state for an unpaid re-opened bill, so they are left as-is.
        """
        for rec in self:
            # Guard against double-processing: only cancelled bills re-open.
            if rec.status != 'cancelled':
                continue

            # 1️⃣ Reverse the advance refund that cancel credited to the wallet.
            # Find the undated cancelled row cancel created (positive amount_added)
            # and post an equal negative row so the net wallet effect is zero.
            if rec.mrd_no and rec.amount_in_advance > 0:
                refund_row = self.env['patient.wallet'].search([
                    ('uhid', '=', rec.mrd_no.id),
                    ('status', '=', 'cancelled'),
                    ('date', '=', False),
                    ('amount_added', '>', 0),
                ], order='id desc', limit=1)
                if refund_row:
                    reversal = self.env['patient.wallet'].create({
                        'uhid': rec.mrd_no.id,
                        'patient_name': rec.patient_name,
                        'amount_in_inr': -(refund_row.amount_added or 0.0),
                        'Staff_name': rec.staff_name.id if rec.staff_name else False,
                        'payment_mode': rec.mode_pay,
                        'date': False,
                    })
                    reversal.action_add_amount()

            # 2️⃣ Restore patient / admission record to the pre-discharge state.
            if rec.mrd_no:
                rec.mrd_no.status = 'proceed_discharge'
                rec.mrd_no.admission_boolean = True
                admitted_patient = self.env['hospital.admitted.patient'].search([
                    ('patient_id', '=', rec.mrd_no.id)
                ], limit=1)
                if admitted_patient:
                    admitted_patient.status = 'proceed_discharge'

            # 3️⃣ Clear the frozen total and re-open as a normal unpaid bill.
            rec.write({
                'status': 'unpaid',
                'settled_total_amount': 0,
            })
        return True

    @api.onchange('vssc_boolean')
    def _onchange_vssc_id(self):
        for rec in self:
            if rec.vssc_boolean:
                rec.mode_pay = 'credit'

    def action_observation(self):
        """Method to toggle observation field when Observation button is clicked"""
        self.observation = True
        # If observation is True, set observation_status to 'observation'
        if self.observation:
            self.observation_status = 'observation'

    def action_observation_discharge(self):
        today = fields.Date.today()

        for rec in self:
            prev_status = rec.status
            # Capture unpaid bills before status changes or they are marked paid
            if prev_status != 'paid':
                rec._sync_patient_charges()
            rec._compute_all_totals()
            bills_to_settle = [
                rec.unpaid_general_ids,
                rec.unpaid_pharmacy_ids,
                rec.unpaid_lab_ids,
                rec.unpaid_ip_ids,
                rec.unpaid_ot_ids,
                rec.unpaid_audiology_ids,
                rec.unpaid_xray_ids,
                rec.unpaid_casualty_ids,
            ]

            # Freeze total and advance before department bills are marked paid.
            if prev_status == 'paid':
                # Pay already applied the advance (wallet debited) and froze
                # amount_in_advance on the bill. Wallet balance is now 0, so
                # re-reading it would wipe the advance and recalculate the total.
                advance_amount = rec.amount_in_advance or 0
                settled_total = rec.total_amount
            else:
                # Unpaid → discharge: resolve from live wallet balance.
                advance_amount = rec._resolve_wallet_balance_advance()
                if rec.amount_in_advance != advance_amount:
                    rec.amount_in_advance = advance_amount
                settled_total = rec._calculate_discharge_amounts()['net_amount']

            # 1️⃣ Discharge current record
            rec.write({
                'status': 'discharged',
                'settled_total_amount': settled_total,
                'amount_in_advance': advance_amount,
            })

            # 2️⃣ Update MRD record status
            if rec.mrd_no:
                # 📝 Capture historical record before clearing active fields
                # This ensures compute methods can still find the doctor in DischargedPatientRecord
                self.env['discharged.patient.record'].sudo().create({
                    'patient_id': rec.mrd_no.reference_no,
                    'name': rec.mrd_no.patient_id,
                    'discharge_date': rec.mrd_no.discharge_date or fields.Datetime.now(),
                    'admitted_date': rec.mrd_no.admitted_date,
                    'room_number': rec.mrd_no.room_number_new.id,
                    'doctor': rec.mrd_no.doctor.id,
                    'total_amount': settled_total,
                    'room_category_new': rec.mrd_no.room_category_new.id,
                    'new_block': rec.mrd_no.new_block.id,
                    'bed_id': rec.mrd_no.bed_id.id,
                    'amount_in_advance': rec.mrd_no.amount_in_advance,
                    'bystander_name': rec.mrd_no.bystander_name,
                    'relation': rec.mrd_no.bystander_relation,
                    'email': rec.mrd_no.bystander_email,
                    'bystander_mobile': rec.mrd_no.bystander_mobile,
                    'alternate_no': rec.mrd_no.alternate_no,
                    'op_category': rec.mrd_no.op_category.id,
                    'pay_mode': rec.mrd_no.advance_mode_payment,
                })

                rec.mrd_no.status = 'discharged'
                rec.mrd_no.write({
                    'status': 'discharged',
                    'admission_boolean': False,
                    'doctor': None,
                    'amount_in_advance': 0.0,
                    'insurance_name':None,
                })

            admitted_patient = self.env['hospital.admitted.patient'].search([
                ('patient_id', '=', rec.mrd_no.id)
            ], limit=1)
            if admitted_patient:
                admitted_patient.status = 'discharged'

            # 3️⃣ Mark captured unpaid department bills as paid
            for group in bills_to_settle:
                for bill in group:
                    bill.status = 'paid'

        return True

    # @api.onchange('discount', 'discount_type', 'total_amount')
    # def _onchange_discount(self):
    #     """Calculate discount amount and net payable amount based on discount"""
    #     if self.total_amount:
    #         if self.discount_type == 'percentage' and self.discount:
    #             self.discount_amount = (self.total_amount * self.discount) / 100
    #         elif self.discount_type == 'amount' and self.discount:
    #             self.discount_amount = self.discount
    #         else:
    #             self.discount_amount = 0
    #
    #         # Calculate net amount (payable amount after discount)
    #         self.net_amount = self.total_amount - self.discount_amount

    # def action_create_admission(self):
    #     admitted_any = False
    #     warnings = []
    #
    #     for rec in self:
    #         if not rec.mrd_no:
    #             continue
    #
    #         patient = rec.mrd_no  # patient.reg record
    #
    #         if patient.status != 'admitted' and not patient.admission_boolean:
    #             patient.admission_boolean = True
    #             patient.status = 'admitted'
    #             admitted_any = True
    #         else:
    #             warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")
    #
    #     if warnings:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Warning',
    #                 'message': '\n'.join(warnings),
    #                 'sticky': True,
    #                 'type': 'warning',
    #             }
    #         }
    #
    #     if not admitted_any:
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Info',
    #                 'message': 'No valid billing records with UHID found for admission.',
    #                 'sticky': True,
    #                 'type': 'info',
    #             }
    #         }
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'Success',
    #             'message': 'Admission created successfully.',
    #             'sticky': False,
    #             'type': 'success',
    #         }
    #     }
    def action_create_admission(self):
        admitted_any = False
        warnings = []

        for rec in self:
            if not rec.mrd_no:

                vals = {
                    'patient_id': rec.patient_name or 'Unknown',
                    'age': rec.age,
                    'gender': rec.gender,
                    'phone_number': rec.mobile,

                }

                patient = self.env['patient.reg'].create(vals)
                rec.mrd_no = patient
            else:
                patient = rec.mrd_no

            if patient.status != 'admitted' and not patient.admission_boolean:
                patient.admission_boolean = True
                patient.status = 'admitted'
                admitted_any = True
            else:
                warnings.append(f"Patient {patient.patient_id or patient.id} is already admitted.")

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': '\n'.join(warnings),
                    'sticky': True,
                    'type': 'warning',
                }
            }

        if not admitted_any:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No valid billing records with UHID found for admission.',
                    'sticky': True,
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Admission created successfully.',
                'sticky': False,
                'type': 'success',
            }
        }

    def _unpaid_advance_for_balance(self):
        """Advance applied to the Balance for an unpaid bill (0 for credit)."""
        self.ensure_one()
        if self.status == 'unpaid' and self.mode_pay != 'credit':
            return int(self.amount_in_advance or 0)
        return 0

    @api.onchange('amount_paid')
    def onchange_amount_paid(self):
        for rec in self:
            if not rec.payment_method_split:
                total = rec.total_amount or 0.0
                paid = rec.amount_paid or 0.0
                # Total Amount already nets the advance, so Balance = Total − Paid.
                rec.balance = int(total - paid)

    @api.onchange('cash_amount', 'upi_amount', 'card_amount', 'payment_method_split')
    def _onchange_payment_amounts(self):
        for rec in self:
            if rec.payment_method_split:
                cash = rec.cash_amount or 0.0
                upi = rec.upi_amount or 0.0
                card = rec.card_amount or 0.0
                total = rec.total_amount or 0.0

                rec.amount_paid = int(cash + upi + card)
                # Total Amount already nets the advance, so Balance = Total − Paid.
                rec.balance = int(total - (cash + upi + card))
            else:
                # If split is turned off, maybe we should clear the amounts? 
                # For now just let the regular amount_paid onchange handle it.
                pass

    @api.depends('total_amount')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = num2words(record.total_amount, lang='en').title() + " Only"

    consolidated_pdf = fields.Binary("Consolidated Bill PDF", attachment=True)

    consolidated_pdf_filename = fields.Char("PDF Filename")
    def action_pay_button(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            raise ValidationError("Please enter both staff name and password.")
        for record in self:
            record._sync_patient_charges()
            # Resolve the advance the SAME way the unpaid bill (display / sync) and
            # the discharge path do — from the patient's actual running wallet
            # balance — so the value does not change the moment Pay is clicked.
            # Previously this used the windowed ``_resolve_advance_amount`` which
            # ignores undated / out-of-window wallet rows and floors at the
            # registration advance, making the advance (and the derived total)
            # jump on Pay whenever the wallet balance differed from that window.
            advance_amount = record._resolve_wallet_balance_advance()
            # Freeze the full bill (gross − discount). The advance is applied as a
            # payment (wallet entry below), so it is NOT deducted from the total.
            settled_total = record._calculate_discharge_amounts()['settled_amount']
            record.write({
                'status': 'paid',
                'settled_total_amount': settled_total,
                'amount_in_advance': advance_amount,
            })
        if self.amount_in_advance > 0:
            patient_wallet = self.env['patient.wallet']
            wallet_rec = patient_wallet.create({
                'uhid': self.mrd_no.id,
                'patient_name': self.patient_name,
                'amount_in_inr': -(self.amount_in_advance or 0.0),
                'Staff_name': self.staff_name.id,
                'payment_mode': self.mode_pay
            })
            wallet_rec.action_add_amount()
        report = record.env.ref('homeo_doctor.action_report_consolidated_discharge_menu_challan')  # Replace with actual report XML ID
        pdf_content, _ = report._render_qweb_pdf(record.id)

        # ✅ Encode and store in Binary field
        record.consolidated_pdf = base64.b64encode(pdf_content)
        record.consolidated_pdf_filename = f"Bill_{record.id or record.id}.pdf"
        # Return action to print PDF and show notification
        # return {
        #     'type': 'ir.actions.report',
        #     'report_name': 'homeo_doctor.report_ip_part_billing_document',
        #     'report_type': 'qweb-pdf',
        #     'context': {
        #         'active_ids': self.ids,
        #         'active_model': 'ip.part.billing',
        #     },
        #     'target': 'new',
        # }

    # @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.total_amt', 'general_bill_line_ids.tax',
    #              'rent')
    # def _compute_totals(self):
    #     for record in self:
    #         record.total_item = len(record.general_bill_line_ids)
    #         record.total_qty = sum(record.general_bill_line_ids.mapped('quantity'))
    #         record.total_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
    #
    #         record.total_tax = sum(
    #             line.tax.tax * line.total_amt / 100 for line in record.general_bill_line_ids if line.tax)
    #
    #         record.net_amount = sum(record.general_bill_line_ids.mapped('total_amt')) + record.rent
    #
    # total_rent_amount = fields.Float(string='Total Rent Amount', compute='_compute_rent_amount')

    # @api.onchange('mrd_no')
    # def _onchange_mrd_no(self):
    #     if self.mrd_no:
    #         self.patient_name = self.mrd_no.patient_id
    #         self.age = self.mrd_no.age
    #         self.gender = self.mrd_no.gender
    #         self.mobile = self.mrd_no.phone_number
    #         self.doctor = self.mrd_no.doc_name
    #         self.admitted_date = self.mrd_no.admitted_date
    #         self.rent_full_day = self.mrd_no.rent_full
    #         self.rent_half_day = self.mrd_no.rent_half
    #         self.vssc_boolean = self.mrd_no.vssc_boolean

    def consolidated_bill(self):
        self._sync_patient_charges()
        return self.env.ref('homeo_doctor.action_report_consolidated_discharge_menu_challan').report_action(self)

    def discharge_bill(self):
        self._sync_patient_charges()
        return self.env.ref('homeo_doctor.action_report_discharge_menu_challan').report_action(self)

    @api.onchange('mrd_no')
    def _onchange_mrd_no(self):
        if not self.mrd_no:
            # Clear fields if no MRD selected
            self.patient_name = False
            self.age = False
            self.gender = False
            self.mobile = False
            self.doctor = False
            self.admitted_date = False
            self.discharge_date = fields.Date.today()
            self.rent_full_day = False
            self.rent_half_day = False
            self.vssc_boolean = False
            self.insurance_name = False
            return

        # Basic patient details
        self.patient_name = self.mrd_no.patient_id
        self.age = self.mrd_no.age
        self.gender = self.mrd_no.gender
        self.mobile = self.mrd_no.phone_number
        # 1️⃣ Priority 1: Cross-check with Admission Logs (IP Source of Truth)
        bill_date = self.bill_date or fields.Date.today()
        admission_log = self.env['hospital.admitted.patient'].sudo().search([
            ('patient_id', '=', self.mrd_no.id),
            ('admission_date', '<=', bill_date)
        ], order='admission_date desc', limit=1)
        
        doctor = False
        if admission_log:
            if not admission_log.discharge_date or bill_date <= admission_log.discharge_date:
                if admission_log.attending_doctor:
                    doctor = admission_log.attending_doctor.id

        # 2️⃣ Priority 2: Use consultant from Master Record (Patient List)
        if not doctor:
            if self.mrd_no.doctor:
                doctor = self.mrd_no.doctor.id
            elif self.mrd_no.doc_name:
                doctor = self.mrd_no.doc_name.id

        self.doctor = doctor

        # If patient is admitted, get additional fields
        if getattr(self.mrd_no, 'admission_boolean', False):
            self.admission_date = self.mrd_no.admitted_date
            self.insurance_name = getattr(self.mrd_no, 'insurance_name', False)
            if self.mrd_no.discharge_date:
                self.discharge_date = self.mrd_no.discharge_date
            else:
                self.discharge_date = fields.Date.today()
        else:
            # If not admitted, clear these fields
            self.admitted_date = False
            self.discharge_date = fields.Date.today()
            self.insurance_name = False

        charge_vals = self._get_patient_charge_vals()
        for field, value in charge_vals.items():
            setattr(self, field, value)

        # On UHID selection the bill is unpaid: show the patient's actual current
        # wallet balance as the advance (same as normal billing).
        self.amount_in_advance = self._resolve_wallet_balance_advance()

    @api.depends('mrd_no', 'admission_date', 'discharge_date')
    def _compute_patient_wallet_value(self):
        for rec in self:
            rec.amount_in_advance = 0.0

            if rec.mrd_no and rec.admission_date and rec.discharge_date:
                wallet_records = self.env['patient.wallet'].search([
                    ('uhid', '=', rec.mrd_no.id),
                    ('date', '>=', rec.admission_date),
                    ('date', '<=', rec.discharge_date),
                ])
                # sum all wallet additions
                total_added = sum(wallet_records.mapped('amount_added') or [0.0])

                # Sum of all refunded amounts (if such a field exists)
                total_refunded = sum(wallet_records.mapped('refund') or [0.0])

                # Compute net advance amount
                rec.amount_in_advance = total_added - total_refunded

    @api.depends('from_date', 'to_date', 'rent_full_day', 'rent_half_day')
    def _compute_rent_amount(self):
        for rec in self:
            if rec.from_date and rec.to_date:
                delta = rec.to_date - rec.from_date
                total_days = delta.days
                seconds = delta.seconds

                if seconds == 0:
                    half_day = False
                elif seconds <= 12 * 3600:
                    half_day = True
                else:
                    total_days += 1
                    half_day = False

                rent = total_days * (rec.rent_full_day or 0)
                if half_day:
                    rent += (rec.rent_half_day or 0)

                rec.total_rent_amount = rent
                print(rec.total_rent_amount,
                      ' rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount rec.total_rent_amount')
            else:
                rec.total_rent_amount = 0

    from datetime import datetime, timedelta
    room_rent_total = fields.Float(string='Room Rent Total', compute='_compute_room_rent_total')

    @api.depends('general_bill_line_ids.quantity', 'general_bill_line_ids.rate', 'general_bill_line_ids.particulars')
    def _compute_room_rent_total(self):
        for rec in self:
            total = 0.0
            for line in rec.general_bill_line_ids:
                if line.particulars and line.particulars == 'Room Rent':
                    total += (line.quantity or 0.0) * (line.rate or 0.0)
            rec.room_rent_total = total

    @api.onchange('from_date', 'to_date', 'total_rent_amount')
    def _onchange_dates_update_rent_line(self):
        for rec in self:
            if rec.total_rent_amount > 0 and rec.from_date and rec.to_date:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )

                rent_particular = self.env['general.dept.costing'].search(
                    [('name', '=', 'Room Rent')],
                    limit=1
                )
                if not rent_particular:
                    return

                delta = rec.to_date - rec.from_date
                total_days = delta.days

                # Determine if the checkout time (to_date) is before 12 PM
                half_day = rec.to_date.hour < 12

                # Final quantity logic
                qty = total_days + (0.5 if half_day else 1)

                # Remove old rent lines
                lines = [(2, line.id) for line in rent_lines]

                vals = {
                    'particulars': rent_particular.id,
                    'quantity': qty,
                    'rate': rec.rent_full_day,
                }
                lines.append((0, 0, vals))

                print("Assigning One2many commands with qty:", qty, lines)

                rec.general_bill_line_ids = lines
            else:
                rent_lines = rec.general_bill_line_ids.filtered(
                    lambda l: l.particulars.name == 'Room Rent'
                )
                if rent_lines:
                    lines = [(2, line.id) for line in rent_lines]
                    rec.general_bill_line_ids = lines

    @api.model
    def create(self, vals):
        """Generate a unique billing number in the format: 000001/24-25"""
        if vals.get('bill_number', 'New') == 'New':
            # current_year = datetime.now().year
            # next_year = current_year + 1
            # year_range = f"{str(current_year)[-2:]}-{str(next_year)[-2:]}"
            #james

            # today = datetime.now()
            today = fields.Date.context_today(self)

            # ✅ Indian Fiscal Year calculation (April 1 – March 31)
            if today.month >= 4:  # April–December
                start_year = today.year
                end_year = today.year + 1
            else:  # January–March
                start_year = today.year - 1
                end_year = today.year

            year_range = f"{start_year % 100:02d}-{end_year % 100:02d}"

            # Get the next sequence number
            # sequence_number = self.env['ir.sequence'].next_by_code('discharge.billing')
            sequence_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('discharge.billing')

            # Ensure sequence exists
            if not sequence_number:
                sequence_number = '1'
            formatted_seq = str(sequence_number).zfill(4)
            vals['bill_number'] = f"{formatted_seq}/{year_range}"

        return super(DischargeBilling, self).create(vals)

    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            return {'domain': {'particulars': [('department', '=', self.department.id)]}}
        else:
            return {'domain': {'particulars': []}}

    @api.onchange('particulars')
    def _onchange_particulars(self):
        if self.particulars:
            rate = self.particulars.amount if self.particulars.amount else 0.0
            tax_amount = self.particulars.tax.tax if self.particulars.tax else 0.0
            tax_type = self.particulars.tax_type

            if tax_type == 'inclusive':
                total = rate
            else:
                total = rate + (rate * tax_amount / 100)

            self.general_bill_line_ids = [(0, 0, {
                'particulars': self.particulars.id,
                'rate': rate,
                'tax': self.particulars.tax.id,
                'quantity': 1,
                'total_amt': total,
            })]

    # def action_ip_print_general_bill(self):
    #     return self.env.ref('homeo_doctor.action_report_ip_part_billing').report_action(self)


class DischargeBillLine(models.Model):
    _name = 'discharge.bill.line'
    _rec_name = 'particulars'

    bill_line_id = fields.Many2one('discharge.billing')
    particulars = fields.Many2one('general.dept.costing', string='Select particulars')
    rate = fields.Integer(string='Rate')
    tax = fields.Many2one('dept.tax', string='Tax(%)')
    quantity = fields.Integer(string='Qty', default=1)
    total_amt = fields.Integer(string='Amount', compute="_compute_total")

    @api.depends('rate', 'tax', 'quantity')
    def _compute_total(self):
        for line in self:
            tax_amount = line.tax.tax if line.tax else 0.0
            qty = line.quantity or 1
            line.total_amt = int(line.rate * qty * (1 + tax_amount / 100))

    @api.onchange('particulars')
    def _rate_auto_fill(self):
        for rec in self:
            if rec.particulars:
                rec.rate = rec.particulars.amount

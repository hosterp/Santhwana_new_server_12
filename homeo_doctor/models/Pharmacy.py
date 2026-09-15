import logging
from collections import defaultdict
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from html import escape

from odoo import api, fields, models
from odoo.exceptions import ValidationError, _logger, UserError
import math


class PharmacyDescription(models.Model):
    _name = 'pharmacy.description'
    _description = 'Pharmacy Description'
    # _order = 'date desc,bill_number desc'
    _order = "fiscal_year_end desc, bill_sequence desc"
    _rec_name = 'bill_number'

    patient_id = fields.Many2one('patient.registration', string="UHID")
    uhid_id = fields.Many2one('patient.reg', string="UHID", ondelete='set null')
    uhid_id_discharge = fields.Many2one('discharge.billing', string="UHID", ondelete='set null')
    name = fields.Char(string="Patient Name")
    phone_number = fields.Char(string="Phone Number")
    # bill_amount=fields.Integer(string='Bill Amount')
    doctor_name = fields.Many2one('doctor.profile', string='Doctor', compute="_compute_doctor_name", 
                                  readonly=False)
    date = fields.Date(string="Date", default=fields.Date.context_today)
    prescription_line_ids = fields.One2many('pharmacy.prescription.line', 'pharmacy_id', string="Prescriptions")
    bill_amount = fields.Float(string="Total Bill Amount", compute="_compute_bill_amount")
    partner_id = fields.Many2one('res.partner', string="Related Partner")
    total_item = fields.Integer(string='Total Item', compute="_compute_totals")
    total_qty = fields.Integer(string='Total Qty', compute="_compute_totals")
    total_amount = fields.Float(string='Total Amount', compute="_compute_totals")
    payment_mathod = fields.Selection([('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI'), ('credit', 'Credit')],
                                      string='Payment Method', default='cash')
    paid_amount = fields.Integer(string='Paid Amount')
    balance = fields.Integer(string='Balance Amount')
    status = fields.Selection([('unpaid', 'Unpaid'), ('paid', 'Paid'), ('cancelled', 'Cancelled')], default='unpaid',
                              string='Payment Status')
    status_admitted = fields.Selection([('admitted', 'Admitted')], string='Status')
    bill_by = fields.Char(string='Bill By')
    remarks = fields.Char(string='Remarks')
    staff_pwd = fields.Char(string='Staff Password')
    staff_name = fields.Many2one('hr.employee', string='Staff Name',default=lambda self: self._default_staff(), required=True)
    description_line_ids = fields.One2many('pharmacy.prescription.line', 'description_id', string="Lines")
    bill_number = fields.Char(string="Bill Number", readonly=True, copy=False, default='New')
    admitted_boolean = fields.Boolean('Admitted')
    patient_type = fields.Selection([('insurance', 'Insurance Patient'), ('normal', 'Normal Patient')])
    cash_amount = fields.Float(string="Cash Amount")
    upi_amount = fields.Float(string="UPI Amount")
    card_amount = fields.Float(string="Card Amount")


    bill_sequence = fields.Integer(string="Bill Sequence", compute="_compute_bill_parts", store=True)
    fiscal_year_end = fields.Integer(string="Fiscal Year End", compute="_compute_bill_parts", store=True)
    payment_method_split=fields.Boolean()

    @api.depends('bill_number')
    def _compute_bill_parts(self):
        for rec in self:
            if rec.bill_number and '/' in rec.bill_number:
                seq, fy = rec.bill_number.split('/')
                rec.bill_sequence = int(seq)

                # fy example: 25-26 → take 26
                fy_parts = fy.split('-')
                rec.fiscal_year_end = int(fy_parts[1]) if len(fy_parts) > 1 else int(fy_parts[0])
            else:
                rec.bill_sequence = 0
                rec.fiscal_year_end = 0


    # @api.model
    # def create(self, vals):
    #     if vals.get('bill_number', 'New') == 'New':
    #         seq = self.env['ir.sequence'].next_by_code('pharmacy.description')
    #         print(f"Generated sequence: {seq}")
    #         vals['bill_number'] = seq or 'New'
    #     return super(PharmacyDescription, self).create(vals)

    active = fields.Boolean(default=True)
    op_category = fields.Selection([('op', 'OP'), ('admitted', 'IP'), ('others', 'OTHERS')], required=True)
    vssc_boolean = fields.Boolean(string='VSSC')
    insurance_name = fields.Many2one('insurance.model', string='Insurance')


    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid)
        ], limit=1)
        return employee.id

    @api.depends('uhid_id', 'uhid_id.admission_boolean', 'uhid_id.status', 'uhid_id.admitted_date', 'uhid_id.doctor', 'uhid_id.doc_name', 'patient_id', 'date', 'op_category')
    def _compute_doctor_name(self):
        for rec in self:
            # 1. Standard Guard: paid bills never change
            if rec.status == 'paid' and rec.doctor_name:
                continue

            # 2. Historical Guard: IP pharmacy records lock on discharge
            if rec.doctor_name and rec.uhid_id and rec.uhid_id.status == 'discharged':
                if rec.op_category == 'admitted':
                    continue

            doctor = False
            if rec.uhid_id and rec.date:
                bill_date = rec.date
                if isinstance(bill_date, datetime):
                    bill_date = bill_date.date()

                # ── OP SAME-DATE PRIORITY ──────────────────────────────────
                # If this is an OP bill on the same date as the patient
                # registration, always follow the current doc_name on patient.reg.
                # This makes changing doc_name on patient.reg immediately
                # update all same-date unpaid OP bills.
                if rec.op_category == 'op':
                    # Search for the latest consultation (Revisit) on or before bill date
                    # Checking both user_id and patient_id to be safe
                    reg_log = self.env['patient.registration'].search([
                        '|', ('user_id', '=', rec.uhid_id.id), ('patient_id', '=', rec.uhid_id.id),
                        ('date', '<=', bill_date)
                    ], order='date desc', limit=1)
                    
                    if reg_log:
                        # Try Many2one first, then search by name from Char field
                        target_doctor = reg_log.doctor.id
                        if not target_doctor and reg_log.doctor_id:
                            found_doctor = self.env['doctor.profile'].search([('name', '=', reg_log.doctor_id)], limit=1)
                            if found_doctor:
                                target_doctor = found_doctor.id
                        
                        if target_doctor:
                           # print(f"DEBUG: Pharmacy {rec.id} found Revisit Doctor ID {target_doctor} from {reg_log.date}")
                            rec.doctor_name = target_doctor
                        else:
                            print(f"DEBUG: Pharmacy {rec.id} Revisit found but no doctor ID/name")
                            rec.doctor_name = rec.uhid_id.doc_name.id
                    else:
                        print(f"DEBUG: Pharmacy {rec.id} no Revisit found, using Master Doctor")
                        rec.doctor_name = rec.uhid_id.doc_name.id
                    continue

                # ── IP LOGIC ───────────────────────────────────────────────
                if rec.op_category == 'admitted':
                    admission_log = self.env['hospital.admitted.patient'].sudo().search([
                        ('patient_id', '=', rec.uhid_id.id),
                        ('admission_date', '<=', bill_date)
                    ], order='admission_date desc', limit=1)
                    if admission_log:
                        adm_dis_date = admission_log.discharge_date
                        if isinstance(adm_dis_date, datetime):
                            adm_dis_date = adm_dis_date.date()
                        if not adm_dis_date or bill_date <= adm_dis_date:
                            if admission_log.attending_doctor:
                                doctor = admission_log.attending_doctor.id
                    
                    if not doctor:
                        historical_admission = self.env['discharged.patient.record'].sudo().search([
                            ('patient_id', '=', rec.uhid_id.reference_no),
                            ('admitted_date', '<=', datetime.combine(bill_date, datetime.max.time())),
                            ('discharge_date', '>=', datetime.combine(bill_date, datetime.min.time()))
                        ], limit=1)
                        if historical_admission and historical_admission.doctor:
                            doctor = historical_admission.doctor.id
                
                # ── OP FALLBACK CHAIN ──────────────────────────────────────
                if not doctor:
                    if rec.patient_id and rec.patient_id.doctor:
                        doctor = rec.patient_id.doctor.id

                # 4️⃣ Priority 4: Look for any OP consultation for this date (EXCLUDING IP sessions)
                if not doctor:
                    reg = self.env['patient.registration'].search([
                        ('patient_id', '=', rec.uhid_id.id),
                        ('date', '<=', bill_date),
                        ('status', 'not in', ['admitted', 'proceed_discharge'])
                    ], order='date desc', limit=1)
                    if reg and reg.doctor:
                        doctor = reg.doctor.id

                if not doctor:
                    if rec.uhid_id.doc_name:
                        doctor = rec.uhid_id.doc_name.id
                    elif rec.uhid_id.doctor:
                        doctor = rec.uhid_id.doctor.id

                if not doctor:
                    appt = self.env['patient.appointment'].search([
                        ('patient_id', '=', rec.uhid_id.id),
                        ('appointment_date', '<=', bill_date),
                        ('status', '=', 'confirmed')
                    ], order='appointment_date desc', limit=1)
                    if appt and appt.doctor_ids:
                        doctor = appt.doctor_ids[0].id

            rec.doctor_name = doctor

    # @api.depends('uhid_id', 'date')
    # def _compute_doctor_name(self):
    #     """Fetch doctor name from patient.reg or patient.revisit for current UHID and date"""
    #     for rec in self:
    #         doctor = False
    #         if rec.uhid_id and rec.date:
    #             # Search patient.reg first
    #             reg = self.env['patient.reg'].search([
    #                 ('id', '=', rec.uhid_id.id),
    #                 ('time', '=', rec.date)
    #             ], limit=1)
    #
    #             if reg and reg.doc_name:
    #                 doctor = reg.doc_name.id
    #
    #             else:
    #                 # Search in patient.revisit
    #                 revisit = self.env['patient.appointment'].search([
    #                     ('patient_id', '=', rec.uhid_id.id),
    #                     ('appointment_date', '=', rec.date),
    #                     ('status','=','confirmed')
    #                 ], limit=1)
    #                 if revisit and revisit.doctor_ids:
    #                     doctor = revisit.doctor_ids.id
    #
    #         rec.doctor_name = doctor

    @api.onchange('patient_type')
    def _onchange_patient_type(self):
        for rec in self:
            if rec.patient_type == 'insurance':
                rec.payment_mathod = 'credit'

    def action_cancel(self):
        for record in self:
            if record.status == 'cancelled':
                continue
            record._restore_all_lines_stock()
            record.status = 'cancelled'

    def _get_all_prescription_lines(self):
        self.ensure_one()
        return self.prescription_line_ids | self.description_line_ids

    def _restore_all_lines_stock(self):
        for line in self._get_all_prescription_lines():
            line.restore_all_deducted_stock()

    def get_cancelled_bills(self):
        return self.search([('active', '=', False)])

    def get_modified_bills(self):
        return self.search([('write_date', '!=', False), ('write_date', '!=', 'create_date')])

    def get_active_bills(self):
        return self.search([('active', '=', True)])

    def unlink(self):
        for rec in self:
            rec.active = False
        return True

    @api.onchange('uhid_id')
    def _onchange_uhid_id(self):
        if self.uhid_id:
            self.name = self.uhid_id.patient_id
            self.phone_number = self.uhid_id.phone_number
            self.vssc_boolean = self.uhid_id.vssc_boolean

            if self.uhid_id.status == 'admitted':
                self.op_category = self.uhid_id.bill_type
                self.insurance_name = self.uhid_id.insurance_name.id
                self.payment_mathod = 'credit'
            else:
                self.op_category = 'op'
                self.payment_mathod = 'cash'

            # self.patient_age = self.uhid_id.age
            # self.patient_gender = self.uhid_id.gender

    @api.onchange('paid_amount')
    def _onchange_paymode(self):
        for rec in self:
            if rec.total_amount and rec.paid_amount:
                rec.balance = abs(rec.total_amount - rec.paid_amount)

    # @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    # def _onchange_payment_amounts(self):
    #     for rec in self:
    #         rec.paid_amount = rec.cash_amount + rec.upi_amount + rec.card_amount

    @api.onchange('cash_amount', 'upi_amount', 'card_amount')
    def _onchange_payment_amounts(self):
        for rec in self:
            cash = rec.cash_amount or 0.0
            upi = rec.upi_amount or 0.0
            card = rec.card_amount or 0.0
            total = rec.total_amount or 0.0

            rec.paid_amount = cash + upi + card
            rec.balance = total - cash - upi - card

    @api.depends('prescription_line_ids')
    def _compute_totals(self):
        for rec in self:
            rec.total_item = len(rec.prescription_line_ids)
            rec.total_qty = sum(line.qty for line in rec.prescription_line_ids)
            rec.total_amount = sum(line.rate for line in rec.prescription_line_ids)

    def password_validation(self):
        if self.staff_name and self.staff_pwd:
            employee = self.staff_name

            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")

            if self.staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            if not self.staff_name:
                raise ValidationError("Please Select staff Name.")
            elif not self.staff_pwd:
                raise ValidationError("Please Enter Password.")
            else:
                raise ValidationError("Please enter both staff name and password.")
    @api.model
    def create(self, vals):
        # ✅ Validate password FIRST before consuming the sequence number
        # This prevents sequence gaps when validation fails
        staff_name_id = vals.get('staff_name') or self._default_staff()
        staff_pwd = vals.get('staff_pwd')
        if staff_name_id and staff_pwd:
            employee = self.env['hr.employee'].browse(staff_name_id)
            if not employee.staff_password_hash:
                raise ValidationError("This staff has no password set.")
            if staff_pwd != employee.staff_password_hash:
                raise ValidationError("The password does not match.")
        else:
            if not staff_name_id:
                raise ValidationError("Please Select staff Name.")
            elif not staff_pwd:
                raise ValidationError("Please Enter Password.")
            else:
                raise ValidationError("Please enter both staff name and password.")

        if vals.get('bill_number', 'New') == 'New':
            today = fields.Date.context_today(self)
            # seq_number = self.env['ir.sequence'].next_by_code('pharmacy.description') or '0000'
            seq_number = self.env['ir.sequence'].with_context(
                ir_sequence_date=today
            ).next_by_code('pharmacy.description')

            # today = datetime.now()
            # today = fields.Date.context_today(self)

            if today.month >= 4:
                start_year = today.year
                end_year = today.year + 1
            else:
                start_year = today.year - 1
                end_year = today.year
            fiscal_suffix = f"{start_year % 100:02d}-{end_year % 100:02d}"

            vals['bill_number'] = f"{seq_number}/{fiscal_suffix}"
        res = super(PharmacyDescription, self).create(vals)
        res._process_payment()

        # # Ensure partner creation is only done if necessary
        # if not res.partner_id and res.name:
        #     partner = self.env['res.partner'].search([
        #         ('name', '=', res.name),
        #         # Add other fields to match if needed
        #     ], limit=1)
        #
        #     if not partner:
        #         partner = self.env['res.partner'].create({
        #             'name': res.name,
        #             # Add other values as needed
        #         })
        #
        #     res.partner_id = partner.id
        #
        return res

    def write(self, vals):
        if vals.get('status') == 'cancelled':
            for record in self:
                if record.status != 'cancelled':
                    record._restore_all_lines_stock()

        res = super(PharmacyDescription, self).write(vals)
        for record in self:
            record._process_payment()
            
            # Sync back to patient.reg if name or phone changed in the bill
            if record.uhid_id and ('name' in vals or 'phone_number' in vals):
                reg_vals = {}
                if 'name' in vals:
                    reg_vals['patient_id'] = vals['name']
                if 'phone_number' in vals:
                    reg_vals['phone_number'] = vals['phone_number']
                
                if reg_vals:
                    # Use sudo to ensure we can update the master record
                    # Use no_sync context to prevent infinite loops (Master -> Dept -> Master)
                    record.uhid_id.sudo().write(reg_vals)
                    
        return res

    @api.depends('prescription_line_ids.rate', 'prescription_line_ids.gst')
    def _compute_bill_amount(self):
        for rec in self:
            rec.bill_amount = sum(line.rate for line in rec.prescription_line_ids)  # Excluding GST

    def _process_payment(self):
        if self.env.context.get('payment_processed'):
            return
        self = self.with_context(payment_processed=True)
        if self.payment_mathod == 'credit' and self.status != 'cancelled':
            self._sync_credit_stock()

    def _sync_credit_stock(self):
        for line in self._get_all_prescription_lines():
            line.sync_stock_deduction()

    def _validate_stock_availability(self):
        for line in self._get_all_prescription_lines():
            line._check_stock_availability()

    def action_register_payment(self):
        self.password_validation()
        for record in self:
            if record.status == 'paid':
                raise ValidationError("This bill is already paid.")
            if record.status == 'cancelled':
                raise ValidationError("Cannot pay a cancelled bill.")
            record._validate_stock_availability()
            for line in record._get_all_prescription_lines():
                line.sync_stock_deduction()
            record.status = 'paid'

        return self.env.ref('homeo_doctor.action_pharmacy_report').report_action(self)

    def action_print_pharmacy_disc_bill(self):
        return self.env.ref('homeo_doctor.action_pharmacy_report').report_action(self)

    def view_prescription_details(self):
        """
        Open a view of prescription details for this pharmacy record
        """
        self.ensure_one()
        return {
            'name': 'Prescription Details',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'pharmacy.prescription.line',
            'domain': [('pharmacy_id', '=', self.id)],
            'target': 'new',
            'context': self.env.context,
        }

    def amount_to_text_indian(self):
        """Convert amount to words in Indian format (Rupees and Paise)."""
        try:
            from num2words import num2words
            if self.total_amount:
                amount_int = int(self.total_amount)
                decimal_part = int(round((self.total_amount - amount_int) * 100))

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
            return self.currency_id.amount_to_text(self.total_amount)

        return ""


class PharmacyPrescriptionLine(models.Model):
    _name = 'pharmacy.prescription.line'
    _description = 'Pharmacy Prescription Line'

    pharmacy_id = fields.Many2one('pharmacy.description', string="Pharmacy")
    admission_id = fields.Many2one('patient.reg', string='Patient Registration')
    product_id = fields.Many2one('product.product', string="Medicine")
    products_id = fields.Many2one('stock.entry', string="Medicine", )
    total_med = fields.Integer("Total Medicine")
    per_ped = fields.Float("Per Medicine")
    morn = fields.Integer("Morning")
    noon = fields.Integer("Noon")
    night = fields.Integer("Night")
    category = fields.Many2one('medicine.category', string='Category')
    batch = fields.Char(string="Batch", compute="_compute_product_details")
    manf_date = fields.Date(string="Manufacturing Date", compute="_compute_product_details")
    exp_date = fields.Date(string="Expiry Date", compute="_compute_product_details")
    rate = fields.Float(string="Rate")
    supplier_rate = fields.Float(string="Rate")
    hsn = fields.Char(string="HSN Code", compute="_compute_product_details")
    packing = fields.Char(string='Packing')
    mfc = fields.Char(string='Manufacturer')
    qty = fields.Integer(string='QTY')
    qty_deducted = fields.Float(string='Qty Deducted', default=0.0, copy=False)
    gst = fields.Integer(string='GST Rate(%)')
    discount = fields.Float(string='Disc %')
    stock_in_hand = fields.Char(string='Stock In Hand', compute="_compute_stock_in_hand")
    # rate = fields.Float(string='Rate')
    description_id = fields.Many2one('pharmacy.description', string="Sale Reference")

    def _get_pharmacy_bill(self):
        self.ensure_one()
        return self.pharmacy_id or self.description_id

    def _get_product(self):
        self.ensure_one()
        if self.products_id and self.products_id.product_id:
            return self.products_id.product_id
        return False

    def _get_available_stock_qty(self):
        product = self._get_product()
        if not product:
            return 0.0
        entries = self.env['stock.entry'].search([
            ('product_id', '=', product.id),
            ('quantity', '>', 0),
        ])
        return sum(entries.mapped('quantity'))

    def _get_stock_entries_for_deduct(self, product):
        if self.products_id and self.products_id.quantity > 0:
            other_entries = self.env['stock.entry'].search([
                ('product_id', '=', product.id),
                ('id', '!=', self.products_id.id),
                ('quantity', '>', 0),
            ], order='exp_date asc, id asc')
            return self.products_id | other_entries
        return self.env['stock.entry'].search([
            ('product_id', '=', product.id),
            ('quantity', '>', 0),
        ], order='exp_date asc, id asc')

    def _deduct_stock_quantity(self, qty):
        self.ensure_one()
        product = self._get_product()
        if not product or qty <= 0:
            return
        remaining = qty
        for entry in self._get_stock_entries_for_deduct(product):
            if remaining <= 0:
                break
            if entry.quantity >= remaining:
                entry.quantity -= remaining
                remaining = 0
            else:
                remaining -= entry.quantity
                entry.quantity = 0
        if remaining > 0:
            raise ValidationError(
                "Not enough stock for %s. Short by %s unit(s)."
                % (product.display_name, int(remaining))
            )

    def _restore_stock_quantity(self, qty):
        self.ensure_one()
        if qty <= 0:
            return
        product = self._get_product()
        if not product:
            return
        StockEntry = self.env['stock.entry']
        entry = False
        if self.batch:
            entry = StockEntry.search([
                ('product_id', '=', product.id),
                ('batch', '=', self.batch),
            ], limit=1)
        if not entry:
            entry = StockEntry.search([
                ('product_id', '=', product.id),
            ], order='exp_date asc, id asc', limit=1)
        if entry:
            entry.quantity += qty
        else:
            StockEntry.create({
                'product_id': product.id,
                'quantity': qty,
                'rate': self.supplier_rate or self.per_ped or 0,
                'batch': self.batch,
                'manf_date': self.manf_date,
                'exp_date': self.exp_date,
                'hsn': self.hsn,
                'company': self.mfc,
                'gst': self.gst or 0,
                'date': fields.Date.context_today(self),
                'state': 'confirmed',
            })

    def _check_stock_availability(self, extra_qty=0):
        self.ensure_one()
        if not self.products_id or not self.qty:
            return
        needed = (self.qty or 0) - (self.qty_deducted or 0) + extra_qty
        if needed <= 0:
            return
        available = self._get_available_stock_qty()
        if available < needed:
            product_name = self._get_product().display_name if self._get_product() else 'Medicine'
            raise ValidationError(
                "Not enough stock for %s. Available: %s, Required: %s."
                % (product_name, int(available), int(needed))
            )

    def sync_stock_deduction(self):
        self.ensure_one()
        if self.env.context.get('skip_stock_sync'):
            return
        bill = self._get_pharmacy_bill()
        if not bill or bill.status == 'cancelled':
            return
        if not self.products_id:
            return

        target = int(self.qty or 0)
        current = int(self.qty_deducted or 0)
        delta = target - current
        if delta > 0:
            self._check_stock_availability()
            self._deduct_stock_quantity(delta)
            super(PharmacyPrescriptionLine, self.with_context(skip_stock_sync=True)).write({
                'qty_deducted': current + delta,
            })
        elif delta < 0:
            self._restore_stock_quantity(abs(delta))
            super(PharmacyPrescriptionLine, self.with_context(skip_stock_sync=True)).write({
                'qty_deducted': current + delta,
            })

    def restore_all_deducted_stock(self):
        for line in self:
            deducted = line.qty_deducted or 0
            if deducted > 0:
                line._restore_stock_quantity(deducted)
                super(PharmacyPrescriptionLine, line.with_context(skip_stock_sync=True)).write({
                    'qty_deducted': 0,
                })

    @api.onchange('products_id', 'category')
    def _onchange_products_id(self):
        domain = [('quantity', '>', 0)]

        if self.category:
            domain.append(('category', '=', self.category.id))

        return {
            'domain': {
                'products_id': domain
            }
        }

    @api.onchange('qty', 'products_id', 'per_ped')
    def _onchange_qty(self):
        for rec in self:
            if rec.qty and rec.stock_in_hand is not None:
                if rec.qty > float(rec.stock_in_hand or 0):
                    return {
                        'warning': {
                            'title': "Not enough stock",
                            'message': "Only %s units available in stock!" % rec.stock_in_hand,
                        },
                        'value': {'qty': 0},
                    }
            if rec.qty and rec.per_ped:
                rec.rate = math.ceil(rec.per_ped * rec.qty)

    @api.depends('rate', 'gst')
    def _compute_tax_components(self):
        for rec in self:
            if rec.gst:
                base = rec.rate / (1 + rec.gst / 100.0)
                rec.taxable = base
                rec.cgst = base * (rec.gst / 200.0)
                rec.sgst = base * (rec.gst / 200.0)
            else:
                rec.taxable = rec.rate
                rec.cgst = 0.0
                rec.sgst = 0.0

    taxable = fields.Float("Taxable Amount", compute="_compute_tax_components")
    cgst = fields.Float("CGST", compute="_compute_tax_components")
    sgst = fields.Float("SGST", compute="_compute_tax_components")

    @api.onchange('products_id')
    def _onchange_product_id(self):
        for line in self:
            if line.products_id:
                stock_entry = line.products_id
                line.batch = stock_entry.batch
                line.manf_date = stock_entry.manf_date
                line.exp_date = stock_entry.exp_date
                line.per_ped = stock_entry.pup
                line.supplier_rate = stock_entry.rate
                line.hsn = stock_entry.hsn
                line.mfc = stock_entry.company
                line.gst = stock_entry.gst

    @api.depends('products_id')
    def _compute_product_details(self):
        for line in self:
            if line.products_id:
                stock_entry = line.products_id
                line.batch = stock_entry.batch
                line.manf_date = stock_entry.manf_date
                line.exp_date = stock_entry.exp_date
                line.hsn = stock_entry.hsn
                line.per_ped = stock_entry.pup
                line.supplier_rate = stock_entry.rate
            else:
                line.batch = False
                line.manf_date = False
                line.exp_date = False
                line.hsn = False

    @api.depends('products_id')
    def _compute_stock_in_hand(self):
        """Fetch available quantity from stock.entry for the selected batch."""
        for record in self:
            if record.products_id:
                record.stock_in_hand = record.products_id.quantity
            else:
                record.stock_in_hand = 0.0

    def _auto_init(self):
        res = super(PharmacyPrescriptionLine, self)._auto_init()
        self._cr.execute("""
            UPDATE pharmacy_prescription_line pl
               SET qty_deducted = pl.qty
              FROM pharmacy_description pd
             WHERE pl.pharmacy_id = pd.id
               AND pl.qty > 0
               AND COALESCE(pl.qty_deducted, 0) = 0
               AND pd.status != 'cancelled'
               AND (pd.payment_mathod = 'credit' OR pd.status = 'paid')
        """)
        self._cr.execute("""
            UPDATE pharmacy_prescription_line pl
               SET qty_deducted = pl.qty
              FROM pharmacy_description pd
             WHERE pl.description_id = pd.id
               AND pl.qty > 0
               AND COALESCE(pl.qty_deducted, 0) = 0
               AND pd.status != 'cancelled'
               AND (pd.payment_mathod = 'credit' OR pd.status = 'paid')
        """)
        return res

    @api.model
    def create(self, vals):
        record = super(PharmacyPrescriptionLine, self).create(vals)
        bill = record._get_pharmacy_bill()
        if bill and bill.payment_mathod == 'credit' and bill.status != 'cancelled':
            record.sync_stock_deduction()
        return record

    def write(self, vals):
        if self.env.context.get('skip_stock_sync'):
            return super(PharmacyPrescriptionLine, self).write(vals)

        for line in self:
            if 'products_id' in vals and line.qty_deducted:
                line._restore_stock_quantity(line.qty_deducted)
                super(PharmacyPrescriptionLine, line.with_context(skip_stock_sync=True)).write({
                    'qty_deducted': 0,
                })

        res = super(PharmacyPrescriptionLine, self).write(vals)

        for line in self:
            bill = line._get_pharmacy_bill()
            if bill and bill.payment_mathod == 'credit' and bill.status != 'cancelled':
                line.sync_stock_deduction()
        return res

    def unlink(self):
        for line in self:
            if line.qty_deducted:
                line._restore_stock_quantity(line.qty_deducted)
        return super(PharmacyPrescriptionLine, self).unlink()

    # @api.depends('product_id', 'total_med')
    # def _compute_rate(self):
    #     for record in self:
    #         if record.product_id and record.total_med:
    #             record.rate = record.product_id.list_price * record.total_med
    #         else:
    #             record.rate = 0.0


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')
    ], default='draft')
    pharm_id = fields.Many2one('pharmacy.description', string="Pharmacy Record")
    name = fields.Char(string="Patient Name")  # Make this a regular field, not related
    uhid = fields.Many2one('patient.registration', string="UHID")  # Make this a regular field, not related
    pay_mode = fields.Selection([('cash', 'Cash'), ('upi', 'UPI'), ('card', 'Card')])
    paid_mount = fields.Integer(string='Paid Amount')
    balance = fields.Integer(string='Balance Amount')

    @api.onchange('pharm_id')
    def _onchange_pharm_id(self):
        if self.pharm_id:
            self.name = self.pharm_id.name  # Changed from patient_name to name
            self.uhid = self.pharm_id.patient_id.id if self.pharm_id.patient_id else False
            # Set the partner_id from the patient if it exists
            if self.pharm_id.patient_id and hasattr(self.pharm_id.patient_id, 'partner_id'):
                self.partner_id = self.pharm_id.patient_id.partner_id.id
            # If patient has no partner_id, create a partner or find existing one
            elif self.pharm_id.patient_id:
                # Look for existing partner with the same name/phone
                partner = self.env['res.partner'].search([
                    ('name', '=', self.pharm_id.name),
                    ('phone', '=', self.pharm_id.phone_number)
                ], limit=1)

                if not partner:
                    # Create a new partner
                    partner = self.env['res.partner'].create({
                        'name': self.pharm_id.name,
                        'phone': self.pharm_id.phone_number,
                    })

                self.partner_id = partner.id

    # Override the action_post method to ensure partner_id is set
    def action_post(self):

        # If this payment is linked to a pharmacy record, generate PDF
        if self.pharm_id:
            # Create report action context
            context = dict(self.env.context)

            # Get the pharmacy report action
            report_action = self.env.ref('homeo_doctor.action_pharmacy_report')

            # Return the report action with the pharmacy record
            return report_action.with_context(active_model='pharmacy.description',
                                              active_ids=[self.pharm_id.id]).report_action(self.pharm_id)

        return

    @api.onchange('paid_mount', 'balance')
    def _onchange_paymode(self):
        for rec in self:
            if rec.amount > 0:
                if rec.paid_mount > 0:
                    rec.balance = rec.amount - rec.paid_mount
                    # Ensure amount remains consistent
                    if rec.balance < 0:
                        rec.balance = 0

    @api.depends('paid_mount')
    def _compute_balance(self):
        for rec in self:
            rec.balance = max(0, rec.amount - rec.paid_mount)


class PharmacyReturn(models.Model):
    _name = 'pharmacy.return'
    _description = 'Pharmacy Sales Return'
    _order = 'return_date desc'
    _rec_name = 'return_number'

    return_date = fields.Date(string="Return Date", default=fields.Date.today)
    original_sale_id = fields.Many2one('pharmacy.description', string="Original Bill")
    return_line_ids = fields.One2many('pharmacy.return.line', 'return_id', string="Return Lines")
    total_return_amount = fields.Float(string="Total Return Amount", compute="_compute_return_amount")
    patient_id = fields.Many2one(related='original_sale_id.uhid_id', string="UHID",  readonly=True)
    patient_name = fields.Char(related='original_sale_id.name', string="Patient Name",  readonly=True)
    phone_number = fields.Char(related='original_sale_id.phone_number', string="Phone Number", 
                               readonly=True)
    doctor_name = fields.Many2one(related='original_sale_id.doctor_name', string="Doctor",  readonly=True)
    return_number = fields.Char(
        string="Return No",
        readonly=True,
        copy=False,
        default='/',
    )
    is_return_validated = fields.Boolean(default=False)

    def print_original_bill(self):
        self.ensure_one()
        return self.env.ref('homeo_doctor.action_pharmacy_report').report_action(self.original_sale_id)

    @api.onchange('original_sale_id')
    def _onchange_original_sale_id(self):
        self.return_line_ids = [(5, 0, 0)]  # Clear existing return lines
        if self.original_sale_id:
            lines = []
            for line in self.original_sale_id.prescription_line_ids:
                lines.append((0, 0, {
                    'category': line.category.id,
                    'product_id': line.products_id.product_id.id,
                    'return_quantity': line.qty,
                    'unit_price': line.per_ped,
                    'manf_date': line.manf_date,
                    'exp_date': line.exp_date,
                    'batch': line.batch,
                    'hsn': line.hsn,
                    'mfc': line.mfc,
                    'rate': line.supplier_rate,
                    'gst': line.gst,
                    'actual_total': line.rate,
                }))
            self.return_line_ids = lines

    @api.model
    def create(self, vals):

        if not vals.get('return_number') or vals.get('return_number') == '/':
            raw_seq = self.env['ir.sequence'].next_by_code('pharmacy.return.bill') or '1'
            padded_seq = str(raw_seq).zfill(4)

            today = date.today()
            year_start = today.year % 100
            year_end = (today.year + 1) % 100
            fiscal_suffix = f"{year_start:02d}-{year_end:02d}"

            vals['return_number'] = f"{padded_seq}/{fiscal_suffix}"

        return super().create(vals)

    @api.depends('return_line_ids.subtotal')
    def _compute_return_amount(self):
        for rec in self:
            rec.total_return_amount = sum(line.subtotal for line in rec.return_line_ids)

    def action_validate_return(self):
        StockEntry = self.env['stock.entry']
        for rec in self:
            rec.is_return_validated = True
            if rec.original_sale_id:
                original = rec.original_sale_id
                original.bill_amount -= rec.total_return_amount
                original.write({'bill_amount': original.bill_amount})

                # Create Stock Entry for each returned line
                for line in rec.return_line_ids:
                    if not line.product_id:
                        continue
                    if line.quantity > 0:
                        StockEntry.create({
                            'category': line.category.id,
                            'product_id': line.product_id.id,
                            'quantity': line.quantity,
                            'qty': line.quantity,
                            'pup': line.unit_price,
                            'supplier_mrp': line.unit_price,
                            'rate': line.rate,
                            'gst': line.gst,
                            'manf_date': line.manf_date,
                            'exp_date': line.exp_date,
                            'batch': line.batch,
                            'hsn': line.hsn,
                            'company': line.mfc,
                            'rack': 'Returned',  # optional: mark returned rack
                            'date': fields.Date.today(),
                            'uom_id': line.product_id.uom_id.id if line.product_id.uom_id else False,
                            'state': 'confirmed',
                        })
            return self.env.ref('homeo_doctor.action_pharmacy_return_report').report_action(self)


class PharmacyReturnLine(models.Model):
    _name = 'pharmacy.return.line'
    _description = 'Pharmacy Return Line'

    product_id = fields.Many2one('product.product', string="Product")
    return_quantity = fields.Float(string="Quantity")
    quantity = fields.Float(string="Returned Quantity")
    unit_price = fields.Float(string="MRP")
    manf_date = fields.Date(string='M.Date')
    exp_date = fields.Date(string='Exp. Date')
    batch = fields.Char(string='Batch Number')
    hsn = fields.Char(string='HSN')
    mfc = fields.Char(string='Mfc')
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal")
    return_id = fields.Many2one('pharmacy.return', string="Return")
    rate = fields.Float(string="Rate")
    actual_total = fields.Float(string="Total")
    gst = fields.Integer(string="GST")
    total_quantity = fields.Integer(string='Total Quantity')
    category = fields.Many2one('medicine.category', string='Category')

    @api.depends('quantity', 'unit_price', 'return_quantity')
    def _compute_subtotal(self):
        for line in self:
            product = line.quantity * line.unit_price
            line.subtotal = math.ceil(product)
            if line.return_quantity < line.quantity:
                raise UserError("Return quantity cannot be greater than issued quantity!")

            line.total_quantity = line.return_quantity
            line.total_quantity = (line.return_quantity or 0) - (line.quantity or 0)

    balance_total = fields.Float(string="Balance Total", compute="_compute_balance_total")

    @api.depends('total_quantity', 'unit_price')
    def _compute_balance_total(self):
        for line in self:
            value = (line.total_quantity or 0) * (line.unit_price or 0)
            line.balance_total = math.ceil(value)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id or not self.return_id.original_sale_id:
            return

        sale = self.return_id.original_sale_id
        matched_line = sale.description_line_ids.filtered(lambda l: l.product_id.id == self.product_id.id)
        if matched_line:
            line = matched_line[0]  # take the first match
            self.unit_price = line.unit_price or 0.0
            self.quantity = line.quantity or 0.0
            self.manf_date = line.manf_date
            self.exp_date = line.exp_date
            self.batch = line.batch
            self.hsn = line.hsn
            self.rate = line.supplier_rate
            self.gst = line.gst
            self.actual_total = line.rate
        else:
            self.unit_price = 0.0
            self.quantity = 0.0
            self.manf_date = False
            self.exp_date = False
            self.batch = False
            self.hsn = False
            self.gst = 0.0
            self.rate = False


class BillStatusWizard(models.TransientModel):
    _name = 'bill.status.wizard'
    _description = 'Bill Status Wizard'

    view_type = fields.Selection([
        ('modified', 'Modified Bills'),
        ('cancelled', 'Cancelled/Deleted Bills'),
    ], string="Bill Type", required=True)

    date_from = fields.Date(string="From Date")
    date_to = fields.Date(string="To Date")

    def fetch_bills(self):
        domain = []

        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        # Include both active and inactive records
        domain.append(('active', 'in', [True, False]))

        # Fetch records with context to include inactive ones
        bills = self.env['pharmacy.description'].with_context(active_test=False).search(domain)

        if self.view_type == 'modified':
            # Filter records where write_date != create_date
            bills = bills.filtered(lambda b: b.write_date and b.create_date and b.write_date != b.create_date)
        elif self.view_type == 'cancelled':
            # Filter records with status 'cancelled' or 'returned'
            bills = bills.filtered(lambda b: b.status in ['cancelled', 'returned'])

        # Clear old results so the tree view shows fresh data
        self.env['bill.status.wizard.line'].search([]).unlink()

        # Create new records to show in the tree view
        for b in bills:
            self.env['bill.status.wizard.line'].create({
                'patient_name': b.name,
                'bill_amount': b.bill_amount,
                'date': b.date,
                'status': b.status,
                'doctor_name': b.doctor_name.name if b.doctor_name else '',
                'pharmacy_description_id': b.id,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Bill Status',
            'res_model': 'bill.status.wizard.line',
            'view_mode': 'tree',
            'target': 'current',
            'context': {'active_test': False},
        }


class BillStatusWizardLine(models.TransientModel):
    _name = 'bill.status.wizard.line'
    _description = 'Bill Status Wizard Line'

    wizard_id = fields.Many2one('bill.status.wizard', string='Wizard Reference')
    patient_name = fields.Char("Patient Name")
    doctor_name = fields.Char("Doctor")
    date = fields.Datetime("Date")
    bill_amount = fields.Float("Bill Amount")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], string="Status")
    pharmacy_description_id = fields.Many2one('pharmacy.description', string="Pharmacy Description")

    def action_open_pharmacy_description(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pharmacy Description',
            'res_model': 'pharmacy.description',
            'view_mode': 'form',
            'res_id': self.pharmacy_description_id.id,
            'target': 'current',
        }


class BillStatus(models.Model):
    _name = 'bill.status'
    _description = 'Bill Status'


class IPReturn(models.Model):
    _name = 'ip.return'
    _description = 'IP Patient Medicine Return'
    _order = 'return_date desc'
    _rec_name = 'return_number'

    patient_id = fields.Many2one('patient.registration', string="UHID")
    uhid = fields.Many2one('patient.reg', string="UHID")
    uhids = fields.Many2one('pharmacy.description', string="Orginal Bill", required=True)
    patient_uhid = fields.Char(string="UHID")
    name = fields.Char(string="Patient Name")
    phone_number = fields.Char(string="Phone Number")
    original_bill_id = fields.Many2one('pharmacy.description', string="Original Bill",
                                       domain="[('op_category', '=', 'ip')]")
    return_line_ids = fields.One2many('ip.return.line', 'return_id', string="Return Lines")
    return_date = fields.Datetime(string="Return Date", default=fields.Datetime.now)
    total_return_qty = fields.Integer(string="Total Return Qty", compute='_compute_totals')
    total_return_amount = fields.Float(string="Total Return Amount", compute='_compute_totals')
    remarks = fields.Text(string="Remarks")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled')
    ], default='draft', string="Status")
    return_number = fields.Char(
        string="Return Number",
        readonly=True,
        copy=False,
        default='/',
    )

    @api.model
    def create(self, vals):

        if not vals.get('return_number') or vals.get('return_number') == '/':
            raw_seq = self.env['ir.sequence'].next_by_code('ip.return.bill') or '1'
            padded_seq = str(raw_seq).zfill(4)

            today = date.today()
            year_start = today.year % 100
            year_end = (today.year + 1) % 100
            fiscal_suffix = f"{year_start:02d}-{year_end:02d}"

            vals['return_number'] = f"{padded_seq}/{fiscal_suffix}"

        return super(IPReturn, self).create(vals)

    @api.onchange('uhids')
    def _onchange_uhids(self):
        for rec in self:
            if rec.uhids:
                rec.name = rec.uhids.name
                rec.patient_uhid = rec.uhids.uhid_id.reference_no
                rec.phone_number = rec.uhids.phone_number

    @api.depends('return_line_ids.quantity', 'return_line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_return_qty = sum(line.quantity for line in rec.return_line_ids)
            rec.total_return_amount = sum(line.amount for line in rec.return_line_ids)

    def action_validate_return(self):
        StockEntry = self.env['stock.entry']
        for rec in self:
            # Deduct return amount from the original bill if it exists
            if rec.original_bill_id:
                original = rec.original_bill_id
                original.bill_amount -= rec.total_return_amount
                original.write({'bill_amount': original.bill_amount})

            # Create Stock Entry for each returned line
            for line in rec.return_line_ids:
                if not line.medicine_id:
                    continue

                StockEntry.create({
                    'product_id': line.medicine_id.id,
                    'quantity': line.quantity,
                    'rate': line.unit_price,
                    'manf_date': line.manf_date,
                    'exp_date': line.exp_date,
                    'batch': line.batch,
                    'hsn': line.hsn,
                    'rack': 'Returned',
                    'date': fields.Date.today(),
                    'uom_id': line.medicine_id.uom_id.id if line.medicine_id.uom_id else False,
                    'state': 'confirmed',
                })
            rec.write({'state': 'returned'})


class IPReturnLine(models.Model):
    _name = 'ip.return.line'
    _description = 'IP Return Line'

    return_id = fields.Many2one('ip.return', string="Return Ref", required=True, ondelete='cascade')
    medicine_id = fields.Many2one('product.product', string="Medicine", required=True)
    manf_date = fields.Date(string='M.Date')
    exp_date = fields.Date(string='Exp. Date')
    batch = fields.Char(string='Batch Number')
    hsn = fields.Char(string='HSN')
    quantity = fields.Integer(string="Return Qty", required=True)
    unit_price = fields.Float(string="Unit Price")
    amount = fields.Float(string="Amount", compute='_compute_amount')

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.unit_price


class FastMovingMedicineForm(models.TransientModel):
    _name = 'fast.moving.medicine.form'
    _description = 'Fast Moving Medicine Form'

    name = fields.Char(default='Fast Moving Report')
    from_date = fields.Date(required=True, default=lambda self: fields.Date.today() - relativedelta(months=6))
    to_date = fields.Date(required=True, default=fields.Date.today)
    line_ids = fields.One2many('fast.moving.medicine.line', 'form_id', string="Medicines")

    def compute_fast_moving(self):
        self.ensure_one()
        lines = self.env['pharmacy.prescription.line'].search([
            ('pharmacy_id.date', '>=', self.from_date),
            ('pharmacy_id.date', '<=', self.to_date),
        ])

        grouped = defaultdict(int)
        for l in lines:
            actual_product = l.product_id or l.products_id.product_id
            if actual_product:
                grouped[actual_product.id] += l.qty or 0

        # Clear previous lines
        self.line_ids.unlink()

        # Create new lines
        for product_id, total_qty in grouped.items():
            if total_qty > 20:
                self.env['fast.moving.medicine.line'].create({
                    'form_id': self.id,
                    'product_id': product_id,
                    'total_qty': total_qty,
                })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fast Moving Medicines',
            'res_model': 'fast.moving.medicine.form',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def print_fast_moving_report(self):
        self.ensure_one()
        self.compute_fast_moving()
        return self.env.ref('homeo_doctor.action_report_fast_moving').report_action(self)

    def action_view_selected_monthly_sales(self):
        self.ensure_one()
        selected_lines = self.line_ids.filtered('is_selected')
        if not selected_lines:
            raise UserError("Select at least one medicine.")

        detail_wizard = self.env['fast.moving.medicine.selected.monthly.form'].create({
            'parent_form_id': self.id,
            'reference_date': self.to_date,
        })
        detail_wizard.compute_selected_monthly_sales_lines(selected_lines)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Selected Medicine Monthly Sales',
            'res_model': 'fast.moving.medicine.selected.monthly.form',
            'res_id': detail_wizard.id,
            'view_mode': 'form',
            'target': 'current',
        }


class FastMovingMedicineLine(models.TransientModel):
    _name = 'fast.moving.medicine.line'
    _description = 'Fast Moving Medicine Line'
    _order = 'total_qty desc'

    form_id = fields.Many2one('fast.moving.medicine.form', string="Form")
    is_selected = fields.Boolean(string="Select")
    product_id = fields.Many2one('product.product', string="Medicine Name")
    total_qty = fields.Integer(string="Total Sale Qty")

    def action_open_monthly_sales(self):
        self.ensure_one()

        detail_wizard = self.env['fast.moving.medicine.monthly.form'].create({
            'monthly_product_id': self.product_id.id,
            'parent_form_id': self.form_id.id,
            'reference_date': self.form_id.to_date,
        })
        detail_wizard.compute_monthly_sales_lines()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Monthly Sales',
            'res_model': 'fast.moving.medicine.monthly.form',
            'res_id': detail_wizard.id,
            'view_mode': 'form',
            'target': 'current',
        }


class FastMovingMedicineMonthlyForm(models.TransientModel):
    _name = 'fast.moving.medicine.monthly.form'
    _description = 'Fast Moving Medicine Monthly Sales'

    monthly_product_id = fields.Many2one('product.product', string="Medicine Name", readonly=True)
    parent_form_id = fields.Many2one('fast.moving.medicine.form', string="Source Wizard", readonly=True)
    reference_date = fields.Date(string="Reference Date", readonly=True)
    month_1_label = fields.Char(string="Month 1", readonly=True)
    month_2_label = fields.Char(string="Month 2", readonly=True)
    month_3_label = fields.Char(string="Month 3", readonly=True)
    month_4_label = fields.Char(string="Month 4", readonly=True)
    month_5_label = fields.Char(string="Month 5", readonly=True)
    month_6_label = fields.Char(string="Month 6", readonly=True)
    month_1_qty = fields.Integer(string="Month 1 Qty", readonly=True)
    month_2_qty = fields.Integer(string="Month 2 Qty", readonly=True)
    month_3_qty = fields.Integer(string="Month 3 Qty", readonly=True)
    month_4_qty = fields.Integer(string="Month 4 Qty", readonly=True)
    month_5_qty = fields.Integer(string="Month 5 Qty", readonly=True)
    month_6_qty = fields.Integer(string="Month 6 Qty", readonly=True)
    total_sale_qty = fields.Integer(string="Total Sale Qty", compute='_compute_total_sale_qty', readonly=True)
    average_sale_qty = fields.Float(string="Average Sale Quantity", compute='_compute_average_sale_qty', readonly=True)
    dashboard_html = fields.Html(string="Monthly Dashboard", compute='_compute_dashboard_html', sanitize=False)

    @api.depends('month_1_qty', 'month_2_qty', 'month_3_qty', 'month_4_qty', 'month_5_qty', 'month_6_qty')
    def _compute_total_sale_qty(self):
        for rec in self:
            rec.total_sale_qty = (
                rec.month_1_qty + rec.month_2_qty + rec.month_3_qty +
                rec.month_4_qty + rec.month_5_qty + rec.month_6_qty
            )

    @api.depends('total_sale_qty')
    def _compute_average_sale_qty(self):
        for rec in self:
            rec.average_sale_qty = rec.total_sale_qty / 6.0 if rec.total_sale_qty else 0.0

    @api.depends(
        'monthly_product_id', 'month_1_label', 'month_2_label', 'month_3_label', 'month_4_label', 'month_5_label',
        'month_6_label', 'month_1_qty', 'month_2_qty', 'month_3_qty', 'month_4_qty', 'month_5_qty', 'month_6_qty',
        'total_sale_qty', 'average_sale_qty'
    )
    def _compute_dashboard_html(self):
        for rec in self:
            medicine_name = escape(rec.monthly_product_id.display_name or '')
            rec.dashboard_html = """
                <div style="overflow:auto;">
                    <table style="width:100%; border-collapse:collapse; table-layout:fixed;">
                        <thead>
                            <tr>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center; vertical-align:middle;">Medicine Name</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_1}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_2}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_3}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_4}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_5}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_6}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">Total Sale Qty</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">Average</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center; vertical-align:middle;">{medicine_name}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_1_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_2_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_3_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_4_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_5_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_6_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center; font-weight:600;">{total_sale_qty}</td>
                                <td style="border:1px solid #d9d9d9; padding:8px; text-align:center; font-weight:600;">{average_sale_qty}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            """.format(
                medicine_name=medicine_name,
                month_1=escape(rec.month_1_label or 'Month 1'),
                month_2=escape(rec.month_2_label or 'Month 2'),
                month_3=escape(rec.month_3_label or 'Month 3'),
                month_4=escape(rec.month_4_label or 'Month 4'),
                month_5=escape(rec.month_5_label or 'Month 5'),
                month_6=escape(rec.month_6_label or 'Month 6'),
                month_1_qty=rec.month_1_qty,
                month_2_qty=rec.month_2_qty,
                month_3_qty=rec.month_3_qty,
                month_4_qty=rec.month_4_qty,
                month_5_qty=rec.month_5_qty,
                month_6_qty=rec.month_6_qty,
                total_sale_qty=rec.total_sale_qty,
                average_sale_qty=f"{rec.average_sale_qty:.2f}",
            )

    def print_monthly_sales_report(self):
        self.ensure_one()
        self.compute_monthly_sales_lines()
        return self.env.ref('homeo_doctor.action_report_fast_moving_monthly').report_action(self)

    def compute_monthly_sales_lines(self):
        self.ensure_one()
        if not self.monthly_product_id or not self.reference_date:
            return

        reference_date = fields.Date.to_date(self.reference_date)
        current_month_start = reference_date.replace(day=1)
        first_month_start = current_month_start - relativedelta(months=5)

        sale_lines = self.env['pharmacy.prescription.line'].search([
            ('pharmacy_id.date', '>=', first_month_start),
            ('pharmacy_id.date', '<=', reference_date),
        ])

        qty_by_month = defaultdict(int)
        for sale_line in sale_lines:
            actual_product = sale_line.product_id or sale_line.products_id.product_id
            if actual_product == self.monthly_product_id and sale_line.pharmacy_id.date:
                month_key = fields.Date.to_date(sale_line.pharmacy_id.date).strftime('%Y-%m')
                qty_by_month[month_key] += sale_line.qty or 0

        month_starts = []
        month_quantities = []
        for month_offset in range(5, -1, -1):
            month_start = current_month_start - relativedelta(months=month_offset)
            month_key = month_start.strftime('%Y-%m')
            month_starts.append(month_start)
            month_quantities.append(qty_by_month.get(month_key, 0))

        self.write({
            'month_1_label': month_starts[0].strftime('%b %Y'),
            'month_2_label': month_starts[1].strftime('%b %Y'),
            'month_3_label': month_starts[2].strftime('%b %Y'),
            'month_4_label': month_starts[3].strftime('%b %Y'),
            'month_5_label': month_starts[4].strftime('%b %Y'),
            'month_6_label': month_starts[5].strftime('%b %Y'),
            'month_1_qty': month_quantities[0],
            'month_2_qty': month_quantities[1],
            'month_3_qty': month_quantities[2],
            'month_4_qty': month_quantities[3],
            'month_5_qty': month_quantities[4],
            'month_6_qty': month_quantities[5],
        })


class FastMovingMedicineSelectedMonthlyForm(models.TransientModel):
    _name = 'fast.moving.medicine.selected.monthly.form'
    _description = 'Selected Medicine Monthly Sales'

    parent_form_id = fields.Many2one('fast.moving.medicine.form', string="Source Wizard", readonly=True)
    reference_date = fields.Date(string="Reference Date", readonly=True)
    month_1_label = fields.Char(string="Month 1", readonly=True)
    month_2_label = fields.Char(string="Month 2", readonly=True)
    month_3_label = fields.Char(string="Month 3", readonly=True)
    month_4_label = fields.Char(string="Month 4", readonly=True)
    month_5_label = fields.Char(string="Month 5", readonly=True)
    month_6_label = fields.Char(string="Month 6", readonly=True)
    line_ids = fields.One2many(
        'fast.moving.medicine.selected.monthly.line',
        'form_id',
        string="Monthly Sales",
        readonly=True,
    )
    total_sale_qty = fields.Integer(string="Total Sale Qty", compute='_compute_total_sale_qty', readonly=True)
    average_sale_qty = fields.Float(string="Average Sale Quantity", compute='_compute_average_sale_qty', readonly=True)
    dashboard_html = fields.Html(string="Monthly Dashboard", compute='_compute_dashboard_html', sanitize=False)

    @api.depends('line_ids.total_qty')
    def _compute_total_sale_qty(self):
        for rec in self:
            rec.total_sale_qty = sum(rec.line_ids.mapped('total_qty'))

    @api.depends('total_sale_qty')
    def _compute_average_sale_qty(self):
        for rec in self:
            rec.average_sale_qty = rec.total_sale_qty / 6.0 if rec.total_sale_qty else 0.0

    @api.depends(
        'month_1_label', 'month_2_label', 'month_3_label', 'month_4_label', 'month_5_label', 'month_6_label',
        'line_ids.product_id', 'line_ids.month_1_qty', 'line_ids.month_2_qty', 'line_ids.month_3_qty',
        'line_ids.month_4_qty', 'line_ids.month_5_qty', 'line_ids.month_6_qty', 'line_ids.total_qty'
    )
    def _compute_dashboard_html(self):
        for rec in self:
            headers = [
                escape(rec.month_1_label or 'Month 1'),
                escape(rec.month_2_label or 'Month 2'),
                escape(rec.month_3_label or 'Month 3'),
                escape(rec.month_4_label or 'Month 4'),
                escape(rec.month_5_label or 'Month 5'),
                escape(rec.month_6_label or 'Month 6'),
            ]
            body_rows = []
            for line in rec.line_ids:
                medicine_name = escape(line.product_id.display_name or '')
                body_rows.append(
                    "<tr>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center; vertical-align:middle;'>{medicine_name}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_1_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_2_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_3_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_4_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_5_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center;'>{line.month_6_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center; font-weight:600;'>{line.total_qty}</td>"
                    f"<td style='border:1px solid #d9d9d9; padding:8px; text-align:center; font-weight:600;'>{line.total_qty / 6.0:.2f}</td>"
                    "</tr>"
                )

            if not body_rows:
                body_rows.append(
                    "<tr><td colspan='9' style='text-align:center;'>No data available.</td></tr>"
                )

            rec.dashboard_html = """
                <div style="overflow:auto;">
                    <table style="width:100%; border-collapse:collapse; table-layout:fixed;">
                        <thead>
                            <tr>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center; vertical-align:middle;">Medicine Name</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_1}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_2}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_3}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_4}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_5}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">{month_6}</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">Total Sale Qty</th>
                                <th style="border:1px solid #d9d9d9; padding:8px; text-align:center;">Average</th>
                            </tr>
                        </thead>
                        <tbody>{body_rows}</tbody>
                    </table>
                </div>
            """.format(
                month_1=headers[0],
                month_2=headers[1],
                month_3=headers[2],
                month_4=headers[3],
                month_5=headers[4],
                month_6=headers[5],
                body_rows=''.join(body_rows),
            )

    def print_selected_monthly_sales_report(self):
        self.ensure_one()
        self.compute_selected_monthly_sales_lines()
        return self.env.ref('homeo_doctor.action_report_fast_moving_selected_monthly').report_action(self)

    def _get_month_starts(self):
        self.ensure_one()
        reference_date = fields.Date.to_date(self.reference_date)
        current_month_start = reference_date.replace(day=1)
        return [current_month_start - relativedelta(months=offset) for offset in range(5, -1, -1)]

    def compute_selected_monthly_sales_lines(self, selected_lines=None):
        self.ensure_one()
        self.line_ids.unlink()

        selected_lines = selected_lines or self.parent_form_id.line_ids.filtered('is_selected')
        selected_products = selected_lines.mapped('product_id').filtered(lambda p: p)
        if not selected_products or not self.reference_date:
            return

        month_starts = self._get_month_starts()
        month_keys = [month_start.strftime('%Y-%m') for month_start in month_starts]
        first_month_start = month_starts[0]
        reference_date = fields.Date.to_date(self.reference_date)

        sale_lines = self.env['pharmacy.prescription.line'].search([
            ('pharmacy_id.date', '>=', first_month_start),
            ('pharmacy_id.date', '<=', reference_date),
        ])

        selected_product_ids = set(selected_products.ids)
        qty_by_product_month = defaultdict(int)
        for sale_line in sale_lines:
            actual_product = sale_line.product_id or sale_line.products_id.product_id
            if actual_product and actual_product.id in selected_product_ids and sale_line.pharmacy_id.date:
                month_key = fields.Date.to_date(sale_line.pharmacy_id.date).strftime('%Y-%m')
                qty_by_product_month[(actual_product.id, month_key)] += sale_line.qty or 0

        line_values = []
        for product in selected_products:
            month_quantities = [qty_by_product_month.get((product.id, month_key), 0) for month_key in month_keys]
            line_values.append((0, 0, {
                'product_id': product.id,
                'month_1_qty': month_quantities[0],
                'month_2_qty': month_quantities[1],
                'month_3_qty': month_quantities[2],
                'month_4_qty': month_quantities[3],
                'month_5_qty': month_quantities[4],
                'month_6_qty': month_quantities[5],
                'total_qty': sum(month_quantities),
            }))

        self.write({
            'month_1_label': month_starts[0].strftime('%b %Y'),
            'month_2_label': month_starts[1].strftime('%b %Y'),
            'month_3_label': month_starts[2].strftime('%b %Y'),
            'month_4_label': month_starts[3].strftime('%b %Y'),
            'month_5_label': month_starts[4].strftime('%b %Y'),
            'month_6_label': month_starts[5].strftime('%b %Y'),
            'line_ids': line_values,
        })


class FastMovingMedicineSelectedMonthlyLine(models.TransientModel):
    _name = 'fast.moving.medicine.selected.monthly.line'
    _description = 'Selected Medicine Monthly Sales Line'
    _order = 'product_id'

    form_id = fields.Many2one('fast.moving.medicine.selected.monthly.form', string="Form", ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Medicine Name", readonly=True)
    month_1_qty = fields.Integer(string="Month 1", readonly=True)
    month_2_qty = fields.Integer(string="Month 2", readonly=True)
    month_3_qty = fields.Integer(string="Month 3", readonly=True)
    month_4_qty = fields.Integer(string="Month 4", readonly=True)
    month_5_qty = fields.Integer(string="Month 5", readonly=True)
    month_6_qty = fields.Integer(string="Month 6", readonly=True)
    total_qty = fields.Integer(string="Total Sale Qty", readonly=True)


class DeadStockMedicineForm(models.TransientModel):
    _name = 'dead.stock.medicine.form'
    _description = 'Dead Stock Medicine Form'

    name = fields.Char(default='Dead Stock Report')
    from_date = fields.Date(required=True, default=fields.Date.today)
    to_date = fields.Date(required=True, default=fields.Date.today)
    line_ids = fields.One2many('dead.stock.medicine.line', 'form_id', string="Dead Stock Medicines")

    def compute_dead_stock(self):
        self.ensure_one()

        StockEntry = self.env['stock.entry']

        one_year_ago = date.today() - timedelta(days=365)
        today = date.today()
        # Search stock entries where dispensed = 0, quantity > 0, and deposit_date >= one_year_ago
        dead_entries = StockEntry.search([
            ('dispensed', '=', 0),
            ('quantity', '>', 0),
            ('date', '>=', one_year_ago),
            ('date', '<=', today),
        ])

        # Clear old lines
        self.line_ids.unlink()

        # Create new lines from stock entries
        for entry in dead_entries:
            self.env['dead.stock.medicine.line'].create({
                'form_id': self.id,
                'stock_entry_id': entry.id,  # link to stock.entry
                'date': entry.date,
                'quantity': entry.quantity,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Dead Stock Medicines',
            'res_model': 'dead.stock.medicine.form',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def print_dead_stock_report(self):
        self.ensure_one()
        self.compute_dead_stock()
        return self.env.ref('homeo_doctor.action_report_dead_stock').report_action(self)


class DeadStockMedicineLine(models.TransientModel):
    _name = 'dead.stock.medicine.line'
    _description = 'Dead Stock Medicine Line'

    form_id = fields.Many2one('dead.stock.medicine.form', ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Medicine")
    stock_entry_id = fields.Many2one('stock.entry', string="Medicine")
    date = fields.Date(string='Date')
    quantity = fields.Float(string='Quantity')


class SlowMovingStockMedicineForm(models.TransientModel):
    _name = 'slow.moving.stock.medicine.form'
    _description = 'Slow Moving Stock Medicine Form'

    name = fields.Char(default='Dead Stock Report')
    from_date = fields.Date(required=True, default=fields.Date.today)
    to_date = fields.Date(required=True, default=fields.Date.today)
    line_ids = fields.One2many('slow.moving.stock.medicine.line', 'form_id', string="Dead Stock Medicines")

    def compute_dead_stock(self):
        self.ensure_one()

        StockEntry = self.env['stock.entry']

        # Calculate the date 6 months ago

        # Find products that have NOT been dispensed in the last 6 months
        # dispensed = 0, quantity > 0, and last entry date <= six_months_ago
        today = date.today()  # 2025-08-20
        six_months_ago = today - timedelta(days=180)  # approx 6 months → 2025-02-20

        StockEntry = self.env['stock.entry']

        slow_moving = StockEntry.search([
            ('dispensed', '=', 0),
            ('quantity', '>', 0),
            ('date', '>=', six_months_ago),
            ('date', '<=', today),
        ])

        # Clear old lines
        self.line_ids.unlink()

        # Create new lines from stock entries
        for entry in slow_moving:
            self.env['slow.moving.stock.medicine.line'].create({
                'form_id': self.id,
                'product_id': entry.product_id.id,  # medicine
                'stock_entry_id': entry.id,  # link to stock.entry
                'date': entry.date,
                'quantity': entry.quantity,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Slow Moving Stock Medicines',
            'res_model': 'slow.moving.stock.medicine.form',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def print_dead_stock_report(self):
        self.ensure_one()
        self.compute_dead_stock()
        return self.env.ref('homeo_doctor.action_report_slow_moving_stock').report_action(self)


class SlowMovingStockMedicineLine(models.TransientModel):
    _name = 'slow.moving.stock.medicine.line'
    _description = 'Slow Moving Stock Medicine Line'
    _order = 'quantity asc'

    form_id = fields.Many2one('slow.moving.stock.medicine.form', ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Medicine")
    stock_entry_id = fields.Many2one('stock.entry', string="Medicine")
    date = fields.Date(string='Date')
    quantity = fields.Float(string='Quantity')

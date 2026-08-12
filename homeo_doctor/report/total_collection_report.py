from datetime import datetime, date
import pytz
from odoo import models, fields, api


class StaffWiseReportWizard(models.TransientModel):
    _name = 'staff.report.wizard'
    _description = 'Staff Wise Report Wizard'

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.today)
    staff_id = fields.Many2one('hr.employee', string='Staff',default=lambda self: self._default_staff())

    @api.model
    def _default_staff(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.user.id)],
            limit=1
        )
        return employee.id or False

    def action_generate_staff_pdf(self):
        payment_methods = [
            ('cash', 'Cash'),
            ('credit', 'Credit'),
            ('card', 'Card'),
            ('cheque', 'Cheque'),
            ('upi', 'UPI'),
        ]

        staff_totals = {}

        def normalize_payment_method(value):
            value = (value or 'cash').strip().lower()
            return value if value in [m[0] for m in payment_methods] else 'cash'

        def add_to_totals(staff, dept, rec, amount_field, mode_field):
            """
            Helper that adds billing amounts to the staff_totals dict.
            Handles split payments (cash_amount, upi_amount, card_amount)
            when payment_method_split is True.
            """
            s_name = rec.staff_name.name if rec.staff_name else 'Unknown'
            staff_totals.setdefault(s_name, {})
            staff_totals[s_name].setdefault(dept, {m[0]: 0.0 for m in payment_methods})

            # Check for split payment
            is_split = False
            if hasattr(rec, 'payment_method_split'):
                is_split = rec.payment_method_split
            elif getattr(rec, 'payment_method_split', False):
                is_split = True

            if is_split:
                # Distribute into individual buckets
                staff_totals[s_name][dept]['cash'] += getattr(rec, 'cash_amount', 0.0)
                staff_totals[s_name][dept]['upi'] += getattr(rec, 'upi_amount', 0.0)
                staff_totals[s_name][dept]['card'] += getattr(rec, 'card_amount', 0.0)
            else:
                total = getattr(rec, amount_field, 0.0) or 0.0
                mode = normalize_payment_method(getattr(rec, mode_field, None))
                if mode not in staff_totals[s_name][dept]:
                    staff_totals[s_name][dept][mode] = 0.0
                staff_totals[s_name][dept][mode] += float(total)

        domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['general.billing'].search(domain):
            add_to_totals(rec.staff_name, 'General Billing', rec, 'total_amount', 'mode_pay')

        lab_domain = [
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_check', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            lab_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['doctor.lab.report'].search(lab_domain):
            add_to_totals(rec.staff_name, 'Lab Billing', rec, 'total_bill_amount', 'mode_of_payment')

        pharmacy_domain = [
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            pharmacy_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['pharmacy.description'].search(pharmacy_domain):
            add_to_totals(rec.staff_name, 'Pharmacy Billing', rec, 'total_amount', 'payment_mathod')

        casualty_domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            casualty_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['casuality.billing'].search(casualty_domain):
            add_to_totals(rec.staff_name, 'Casualty Billing', rec, 'net_amount', 'mode_pay')

        audiology_domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            audiology_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['audiology.billing'].search(audiology_domain):
            add_to_totals(rec.staff_name, 'Audiology Billing', rec, 'total_amount', 'mode_pay')

        xray_domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            xray_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['xray.billing'].search(xray_domain):
            add_to_totals(rec.staff_name, 'X-Ray Billing', rec, 'total_amount', 'mode_pay')

        ot_domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            ot_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['ot.billing'].search(ot_domain):
            add_to_totals(rec.staff_name, 'OT Billing', rec, 'total_amount', 'mode_pay')

        patient_wallet_domain = [
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
        ]
        if self.staff_id:
            patient_wallet_domain.append(('Staff_name', '=', self.staff_id.id))

        billings = self.env['patient.wallet'].search(patient_wallet_domain)
        for rec in billings:
            if not rec.refund and (not rec.amount_added or rec.amount_added <= 0):
                continue
            if rec.refund and rec.refund <= 0:
                continue

            s_name = rec.Staff_name.name if rec.Staff_name else 'Unknown'

            if rec.refund:
                dept = 'Refund Amount'
                amount = -(rec.refund or 0.0)
                pay_method = normalize_payment_method(rec.payment_mode)
                staff_totals.setdefault(s_name, {})
                staff_totals[s_name].setdefault(dept, {m[0]: 0.0 for m in payment_methods})
                staff_totals[s_name][dept][pay_method] += amount
            else:
                dept = 'Advance Amount'
                staff_totals.setdefault(s_name, {})
                staff_totals[s_name].setdefault(dept, {m[0]: 0.0 for m in payment_methods})
                if getattr(rec, 'payment_method_split', False):
                    staff_totals[s_name][dept]['cash'] += getattr(rec, 'cash_amount', 0.0)
                    staff_totals[s_name][dept]['upi'] += getattr(rec, 'upi_amount', 0.0)
                    staff_totals[s_name][dept]['card'] += getattr(rec, 'card_amount', 0.0)
                else:
                    pay_method = normalize_payment_method(rec.payment_mode)
                    staff_totals[s_name][dept][pay_method] += rec.amount_added or 0.0

        reception_domain = [
            ('time', '>=', self.from_date),
            ('time', '<=', self.to_date),
            '|',
            ('status', 'not in', ['unpaid', 'cancelled']),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            reception_domain.append(('register_staff_name', '=', self.staff_id.id))

        for rec in self.env['patient.reg'].search(reception_domain):
            s_name = rec.register_staff_name.name if rec.register_staff_name else 'Unknown'
            dept = 'Reception Billing'
            staff_totals.setdefault(s_name, {})
            staff_totals[s_name].setdefault(dept, {m[0]: 0.0 for m in payment_methods})

            if getattr(rec, 'payment_method_split', False):
                staff_totals[s_name][dept]['cash'] += getattr(rec, 'cash_amount', 0.0)
                staff_totals[s_name][dept]['upi'] += getattr(rec, 'upi_amount', 0.0)
                staff_totals[s_name][dept]['card'] += getattr(rec, 'card_amount', 0.0)
            else:
                pay_method = normalize_payment_method(rec.register_mode_payment)
                staff_totals[s_name][dept][pay_method] += rec.register_total_amount or 0.0

        discharge_domain = [
            ('bill_date', '>=', self.from_date),
            ('bill_date', '<=', self.to_date),
            ('status', 'not in', ['unpaid', 'paid', 'cancelled']),
        ]
        if self.staff_id:
            discharge_domain.append(('staff_name', '=', self.staff_id.id))

        for rec in self.env['discharge.billing'].search(discharge_domain):
            add_to_totals(rec.staff_name, 'Discharge Billing', rec, 'total_amount', 'mode_pay')

        appt_domain = [
            ('appointment_date', '>=', self.from_date),
            ('appointment_date', '<=', self.to_date),
            '|',
            ('status', '=', 'confirmed'),
            '&',
            ('vssc_boolean', '=', True),
            ('status', '!=', 'cancelled'),
        ]
        if self.staff_id:
            appt_domain.append(('register_staff_name', '=', self.staff_id.id))

        for rec in self.env['patient.appointment'].search(appt_domain):
            s_name = rec.register_staff_name.name if rec.register_staff_name else 'Unknown'
            dept = 'Reception Billing'
            staff_totals.setdefault(s_name, {})
            staff_totals[s_name].setdefault(dept, {m[0]: 0.0 for m in payment_methods})

            if getattr(rec, 'payment_method_split', False):
                staff_totals[s_name][dept]['cash'] += getattr(rec, 'cash_amount', 0.0)
                staff_totals[s_name][dept]['upi'] += getattr(rec, 'upi_amount', 0.0)
                staff_totals[s_name][dept]['card'] += getattr(rec, 'card_amount', 0.0)
            else:
                pay_method = normalize_payment_method(rec.register_mode_payment)
                staff_totals[s_name][dept][pay_method] += rec.register_total_amount or 0.0

        # 📊 Compute grand totals
        grand_totals = {code: 0.0 for code, _ in payment_methods}

        for staff_data in staff_totals.values():
            for dept_data in staff_data.values():
                for code in grand_totals.keys():
                    grand_totals[code] += dept_data.get(code, 0.0)

        # 📦 Prepare data dict
        data = {
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
            'staff_totals': staff_totals,
            'payment_labels': [label for code, label in payment_methods],
            'payment_codes': [code for code, label in payment_methods],
            'grand_totals': grand_totals,
        }

        # ✅ Pass `data` directly
        return self.env.ref('homeo_doctor.staff_report_action').report_action([], data=data)


class ReportStaffWise(models.AbstractModel):
    _name = 'report.homeo_doctor.staff_report_template'
    _description = 'Staff Wise Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            'data': data or {},   # direct access to data dict
        }

class CollectionReportWizard(models.TransientModel):
    _name = 'collection.report.wizard'
    _description = 'Total Collection Report Wizard'

    from_date = fields.Date(required=True, default=fields.Date.context_today)
    to_date = fields.Date(required=True, default=fields.Date.context_today)
    report_type = fields.Selection([
        ('daily', 'Daily Collection Report'),
        ('summary', 'Summary Report')
    ], default='daily', string='Report Type')

    def generate_report(self):
        return self.env.ref('homeo_doctor.action_collection_pdf_report').report_action(self, data={
            'from_date': self.from_date,
            'to_date': self.to_date,
            'report_type': self.report_type,
        })

    def get_collection_data(self, from_date, to_date):
        """Get collection data from all billing modules"""
        collection_data = []

        # 1. Consultation (patient.reg)
        consultations = self._get_consultation_data(from_date, to_date)
        collection_data.extend(consultations)

        # 2. Casualty Billing
        casualty_data = self._get_casualty_data(from_date, to_date)
        collection_data.extend(casualty_data)

        # 3. Lab Billing
        lab_data = self._get_lab_data(from_date, to_date)
        collection_data.extend(lab_data)

        # 4. Pharmacy Billing
        pharmacy_data = self._get_pharmacy_data(from_date, to_date)
        collection_data.extend(pharmacy_data)

        # 5. X-Ray Billing
        xray_data = self._get_xray_data(from_date, to_date)
        collection_data.extend(xray_data)

        # 6. Audiology Billing
        audio_data = self._get_audiology_data(from_date, to_date)
        collection_data.extend(audio_data)

        # 7. General Billing
        general_data = self._get_general_data(from_date, to_date)
        collection_data.extend(general_data)

        # 8. IP Part Billing
        ip_data = self._get_ip_data(from_date, to_date)
        collection_data.extend(ip_data)

        # 9. OT Billing
        ot_data = self._get_ot_data(from_date, to_date)
        collection_data.extend(ot_data)

        # 10. Discharge Billing
        discharge_data = self._get_discharge_data(from_date, to_date)
        collection_data.extend(discharge_data)

        # Sort by date and type
        collection_data.sort(key=lambda x: (x['date'], x['type']))

        return collection_data

    def _get_payment_amounts(self, rec):
        cash = card = upi = credit = 0.0
        
        # 1. Handle Split Payment if enabled
        if getattr(rec, 'payment_method_split', False):
            cash = getattr(rec, 'cash_amount', 0.0)
            upi = getattr(rec, 'upi_amount', 0.0)
            card = getattr(rec, 'card_amount', 0.0)
            # If there's a credit portion or other modes not explicitly split, 
            # we might need to handle them, but usually split only covers these three.
            return cash, card, upi, credit

        # 2. Handle Single Payment Mode (Fallback)
        mode = False
        if hasattr(rec, 'payment_mode'):
            mode = rec.payment_mode
        elif hasattr(rec, 'mode_pay'):
            mode = rec.mode_pay
        elif hasattr(rec, 'register_mode_payment'):
            mode = rec.register_mode_payment
        elif hasattr(rec, 'payment_mathod'):
            mode = rec.payment_mathod

        amount = 0.0
        if hasattr(rec, 'amount_paid'):
            amount = rec.amount_paid
        elif hasattr(rec, 'paid_amount'):
            amount = rec.paid_amount
        elif hasattr(rec, 'register_amount_paid'):
            amount = rec.register_amount_paid

        if mode == 'cash':
            cash = amount
        elif mode == 'card':
            card = amount
        elif mode == 'upi':
            upi = amount
        elif mode == 'credit':
            credit = amount
            
        return cash, card, upi, credit

    def get_collection_data(self, from_date, to_date):
        """Get collection data from all billing modules"""
        collection_data = []

        collection_data.extend(self._get_consultation_data(from_date, to_date))
        collection_data.extend(self._get_casualty_data(from_date, to_date))
        collection_data.extend(self._get_lab_data(from_date, to_date))
        collection_data.extend(self._get_pharmacy_data(from_date, to_date))
        collection_data.extend(self._get_xray_data(from_date, to_date))
        collection_data.extend(self._get_audiology_data(from_date, to_date))
        collection_data.extend(self._get_general_data(from_date, to_date))
        collection_data.extend(self._get_ip_data(from_date, to_date))
        collection_data.extend(self._get_ot_data(from_date, to_date))
        collection_data.extend(self._get_discharge_data(from_date, to_date))

        # Sort by date and type
        collection_data.sort(
            key=lambda x: (
                datetime.combine(x['date'], datetime.min.time()) if isinstance(x['date'], date) else x['date'],
                x['type']
            )
        )

        return collection_data

    def _get_consultation_data(self, from_date, to_date):
        data = []
        records = self.env['patient.reg'].search([
            ('time', '>=', from_date),
            ('time', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.time if rec.time else from_date,
                'type': 'reception',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'total': rec.register_total_amount or 0.0,
            })
        return data

    def _get_casualty_data(self, from_date, to_date):
        data = []
        records = self.env['casuality.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'casualty',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_lab_data(self, from_date, to_date):
        data = []
        records = self.env['doctor.lab.report'].search([
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.date,
                'type': 'lab',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_bill_amount or 0.0,
            })
        return data

    def _get_pharmacy_data(self, from_date, to_date):
        data = []
        records = self.env['pharmacy.description'].search([
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.date,
                'type': 'pharmacy',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_xray_data(self, from_date, to_date):
        data = []
        records = self.env['xray.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'xray',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_audiology_data(self, from_date, to_date):
        data = []
        records = self.env['audiology.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'audio',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_general_data(self, from_date, to_date):
        data = []
        records = self.env['general.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'general',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_ip_data(self, from_date, to_date):
        data = []
        records = self.env['ip.part.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'ip_part',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_ot_data(self, from_date, to_date):
        data = []
        records = self.env['ot.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'ot',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    def _get_discharge_data(self, from_date, to_date):
        data = []
        records = self.env['discharge.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '=', 'paid'),
        ])
        for rec in records:
            cash, card, upi, credit = self._get_payment_amounts(rec)
            data.append({
                'date': rec.bill_date,
                'type': 'discharge',
                'user': rec.create_uid.name or 'Unknown',
                'cash': cash,
                'card': card,
                'upi': upi,
                'credit': credit,
                'others': getattr(rec, 'other_amount', 0.0),
                'total': rec.total_amount or 0.0,
            })
        return data

    # def get_totals(self, collection_data):
    #     totals = {
    #         'cash': 0.0,
    #         '




    def get_totals(self, collection_data):
        """Calculate totals for the report"""
        totals = {
            'cash': 0.0,
            'card': 0.0,
            'upi': 0.0,
            'credit': 0.0,
            'others': 0.0,
            'total': 0.0,
        }

        for record in collection_data:
            totals['cash'] += record.get('cash', 0.0)
            totals['card'] += record.get('card', 0.0)
            totals['upi'] += record.get('upi', 0.0)
            totals['credit'] += record.get('credit', 0.0)
            totals['others'] += record.get('others', 0.0)
            totals['total'] += record.get('total', 0.0)

        return totals


class CollectionReport(models.AbstractModel):
    _name = "report.homeo_doctor.collection_pdf_template"
    _description = 'Collection PDF Report'

    def _get_report_values(self, docids, data=None):
        active_id = self.env.context.get('active_id')
        wizard = self.env['collection.report.wizard'].browse(active_id)

        from_date = data.get('from_date')
        to_date = data.get('to_date')
        report_type = data.get('report_type', 'daily')

        collection_data = wizard.get_collection_data(from_date, to_date)
        totals = wizard.get_totals(collection_data)

        return {
            'doc_ids': [wizard.id],
            'doc_model': 'collection.report.wizard',
            'data': data,
            'collection_data': collection_data,
            'totals': totals,
            'from_date': from_date,
            'to_date': to_date,
            'report_type': report_type,
            'company_name': 'Dr.Reach Hospital',  # You can make this dynamic
        }



# -*- coding: utf-8 -*-
from odoo import models, fields, api
from collections import defaultdict
from datetime import datetime, date


class RevenueReportWizard(models.TransientModel):
    _name = 'revenue.report.wizard'
    _description = 'Revenue Report Wizard'

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.context_today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.context_today)

    # -------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------
    def _get_revenue_data(self):
        """
        Collect all revenue grouped by date, matching the Combined Report (all_in_one.py)
        domain filters and calculation rules 100% to guarantee grand total alignment.
        Returns a list of dicts sorted by date.
        """
        from_date = self.from_date
        to_date = self.to_date
        date_totals = defaultdict(float)

        from_datetime = datetime.combine(from_date, datetime.min.time())
        to_datetime = datetime.combine(to_date, datetime.max.time())

        def get_record_amount(rec, amount_field):
            if getattr(rec, 'payment_method_split', False):
                return (getattr(rec, 'cash_amount', 0.0) or 0.0) + \
                       (getattr(rec, 'upi_amount', 0.0) or 0.0) + \
                       (getattr(rec, 'card_amount', 0.0) or 0.0)
            return float(getattr(rec, amount_field, 0.0) or 0.0)

        def add_records(records, date_field, amount_field, sign=1):
            for rec in records:
                d_val = getattr(rec, date_field, False)
                if not d_val:
                    continue
                if isinstance(d_val, datetime):
                    d_val = d_val.date()
                if callable(amount_field):
                    amt = amount_field(rec)
                else:
                    amt = get_record_amount(rec, amount_field)
                if amt:
                    date_totals[d_val] += sign * amt

        # 1. OP Registration
        add_records(self.env['patient.reg'].search([
            ('time', '>=', from_date),
            ('time', '<=', to_date),
            ('register_bool', '=', True),
            ('status', '!=', 'cancelled'),
        ]), 'time', 'register_total_amount')

        # 2. Revisit / Appointment
        add_records(self.env['patient.appointment'].search([
            ('appointment_date', '>=', from_date),
            ('appointment_date', '<=', to_date),
            ('status', '=', 'confirmed'),
        ]), 'appointment_date', 'register_total_amount')

        # 3. Patient Wallet (Advance / Refund)
        wallet_recs = self.env['patient.wallet'].search([
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ])
        for rec in wallet_recs:
            if not rec.refund and (not rec.amount_added or rec.amount_added <= 0):
                continue
            if rec.refund and rec.refund <= 0:
                continue
            d_val = rec.date
            if isinstance(d_val, datetime):
                d_val = d_val.date()

            if not rec.refund:
                if getattr(rec, 'payment_method_split', False):
                    amt = (getattr(rec, 'cash_amount', 0.0) or 0.0) + \
                          (getattr(rec, 'upi_amount', 0.0) or 0.0) + \
                          (getattr(rec, 'card_amount', 0.0) or 0.0)
                else:
                    amt = float(rec.amount_added or 0.0)
            else:
                amt = -float(rec.refund or 0.0)

            if amt and d_val:
                date_totals[d_val] += amt

        # 4. Discharge Billing
        add_records(self.env['discharge.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', 'in', ['paid', 'discharged']),
        ]), 'bill_date', 'total_amount')

        # 5. X-Ray Billing
        add_records(self.env['xray.billing'].search([
            ('bill_date', '>=', from_datetime),
            ('bill_date', '<=', to_datetime),
            ('status', '!=', 'cancelled'),
        ]), 'bill_date', 'total_amount')

        # 6. Audiology Billing
        add_records(self.env['audiology.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]), 'bill_date', 'total_amount')

        # 7. Casualty Billing
        add_records(self.env['casuality.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]), 'bill_date', 'net_amount')

        # 8. OT Billing
        add_records(self.env['ot.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]), 'bill_date', 'total_amount')

        # 9. Lab Billing
        add_records(self.env['doctor.lab.report'].search([
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', 'not in', ['cancelled']),
        ]), 'date', 'total_bill_amount')

        # 10. Pharmacy Sales
        add_records(self.env['pharmacy.description'].search([
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]), 'date', 'total_amount')

        # 11. General Billing
        add_records(self.env['general.billing'].search([
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]), 'bill_date', 'total_amount')

        # 12. Pharmacy Return
        add_records(self.env['pharmacy.return'].search([
            ('return_date', '>=', from_date),
            ('return_date', '<=', to_date),
        ]), 'return_date', lambda rec: float(rec.total_return_amount or 0.0), sign=-1)

        # Build list sorted by date
        rows = []
        for sl, (dt, total) in enumerate(sorted(date_totals.items()), start=1):
            rows.append({
                'sl_no': sl,
                'date': dt.strftime('%d-%m-%Y') if dt else '',
                'grand_total': round(total, 2),
            })
        return rows

    def _prepare_report_payload(self):
        rows = self._get_revenue_data()
        grand_total = sum(r['grand_total'] for r in rows)

        return {
            'from_date': self.from_date.strftime('%d-%m-%Y'),
            'to_date': self.to_date.strftime('%d-%m-%Y'),
            'rows': rows,
            'grand_total': round(grand_total, 2),
        }

    # -------------------------------------------------------
    # Button actions
    # -------------------------------------------------------
    def action_print_report(self):
        """Print / Download PDF report."""
        report_action = self.env.ref('homeo_doctor.action_revenue_report_pdf', raise_if_not_found=False)
        paperformat = self.env.ref('homeo_doctor.revenue_report_paperformat', raise_if_not_found=False)
        if report_action and paperformat:
            paperformat.sudo().write({'orientation': 'Portrait', 'format': 'A4'})
            report_action.sudo().write({'paperformat_id': paperformat.id})

        data = self._prepare_report_payload()
        return report_action.report_action(self, data=data)

    def action_view_report(self):
        """Open HTML preview in browser (qweb-html)."""
        data = self._prepare_report_payload()
        return self.env.ref('homeo_doctor.action_revenue_report_html').report_action(self, data=data)


class RevenueReportPDF(models.AbstractModel):
    _name = 'report.homeo_doctor.revenue_report_pdf_template'
    _description = 'Revenue Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            'data': data or {},
        }


class RevenueReportHTML(models.AbstractModel):
    _name = 'report.homeo_doctor.revenue_report_html_template'
    _description = 'Revenue Report HTML'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            'data': data or {},
        }

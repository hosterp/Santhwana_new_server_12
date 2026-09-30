import io
import base64
from collections import OrderedDict
from datetime import datetime, date
from html import escape

import xlsxwriter

from odoo import models, fields, api


class _ReportLine(object):
    """Plain row for PDF/Excel. Not an Odoo record, so nothing is written back."""

    def __init__(self, report_date, reference_no, bill_number, patient_name,
                 consultation_fee, cash_amount, credit_amount, total_amount):
        self.date = report_date
        self.reference_no = reference_no or ''
        self.bill_number = bill_number or ''
        self.patient_name = patient_name or ''
        self.consultation_fee = consultation_fee or 0
        self.cash_amount = cash_amount or 0.0
        self.credit_amount = credit_amount or 0.0
        self.total_amount = total_amount or 0.0


class DoctorWiseCollectionWizard(models.TransientModel):
    _name = 'doctor.wise.collection.wizard'
    _description = 'Doctor Wise Collection Wizard'

    date_from = fields.Date(string="From Date", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)
    doctor_id = fields.Many2one('doctor.profile', string="Doctor", default=lambda self: self._default_doctor())

    line_ids = fields.One2many(
        'doctor.wise.collection.line',
        'wizard_id',
        string="Collection Lines"
    )

    @api.model
    def _default_doctor(self):
        return self.env['doctor.profile'].search([('name', '=', self.env.user.name)], limit=1)

    def _table_columns(self, table):
        cache = getattr(self.env, '_op_collection_columns', None)
        if cache is None:
            cache = {}
            self.env._op_collection_columns = cache
        if table not in cache:
            self.env.cr.execute("""
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_name = %s
            """, (table,))
            cache[table] = {row[0] for row in self.env.cr.fetchall()}
        return cache[table]

    def _fetch_op_collection_rows(self):
        """
        Same filters as the on-screen report, in one SELECT.
        Amounts come from stored columns when they exist, otherwise from the
        same fee formula (registration fee + consultation / VSSC 400).
        Patient registration and appointment records are not loaded.
        """
        self.ensure_one()
        bucket = getattr(self.env, '_op_collection_rows', None)
        if bucket is None:
            bucket = {}
            self.env._op_collection_rows = bucket
        cache_key = (self.id, self.date_from, self.date_to, self.doctor_id.id or 0)
        if cache_key in bucket:
            return bucket[cache_key]

        reg_cols = self._table_columns('patient_reg')
        app_cols = self._table_columns('patient_appointment')
        if 'register_total_amount' in reg_cols:
            reg_total = 'COALESCE(pr.register_total_amount, 0)'
        else:
            reg_total = (
                "CASE WHEN COALESCE(pr.vssc_boolean, FALSE) THEN 400 "
                "ELSE COALESCE(prf.fee, 0) + COALESCE(pr.consultation_fee, 0) END"
            )
        if 'consultation_fee' in app_cols:
            app_fee = 'COALESCE(pa.consultation_fee, 0)'
            fee_join = ''
        else:
            app_fee = (
                "CASE WHEN COALESCE(pa.fee_applied, FALSE) THEN "
                "CASE WHEN COALESCE(preg.vssc_boolean, FALSE) THEN 400 "
                "ELSE COALESCE(fee_dp.consultation_fee_doctor, 0) END ELSE 0 END"
            )
            fee_join = """
            LEFT JOIN LATERAL (
                SELECT r2.doctor_profile_id AS id
                  FROM doctor_profile_patient_appointment_rel r2
                 WHERE r2.patient_appointment_id = pa.id
                 ORDER BY r2.ctid
                 LIMIT 1
            ) first_doc ON TRUE
            LEFT JOIN doctor_profile fee_dp ON fee_dp.id = first_doc.id
            """
        if 'register_total_amount' in app_cols:
            app_total = 'COALESCE(pa.register_total_amount, 0)'
        else:
            app_total = 'COALESCE(pa.registration_fee, 0) + (%s)' % app_fee

        query = """
            SELECT report_date, reference_no, bill_number, patient_name, doctor_id, doctor_name,
                   consultation_fee, payment_mode,
                   CASE WHEN payment_mode IN ('cash', 'card', 'upi', 'cheque') THEN total_amount
                        ELSE 0 END AS cash_amount,
                   CASE WHEN payment_mode = 'credit' THEN total_amount
                        ELSE 0 END AS credit_amount,
                   total_amount
              FROM (
                    SELECT pr.time AS report_date,
                           COALESCE(pr.reference_no, '') AS reference_no,
                           COALESCE(pr.bill_number, '') AS bill_number,
                           COALESCE(pr.patient_id, '') AS patient_name,
                           pr.doc_name AS doctor_id,
                           COALESCE(dp.name, 'No Doctor') AS doctor_name,
                           COALESCE(pr.consultation_fee, 0) AS consultation_fee,
                           COALESCE(pr.register_mode_payment, 'cash') AS payment_mode,
                           ({reg_total})::double precision AS total_amount
                      FROM patient_reg pr
                 LEFT JOIN doctor_profile dp ON dp.id = pr.doc_name
                 LEFT JOIN patient_registration_fee prf ON prf.id = pr.registration_fee
                     WHERE pr.time >= %(date_from)s
                       AND pr.time <= %(date_to)s
                       AND COALESCE(pr.status, '') <> 'cancelled'
                       AND (%(doctor_id)s IS NULL OR pr.doc_name = %(doctor_id)s)

                    UNION ALL

                    SELECT pa.appointment_date AS report_date,
                           COALESCE(preg.reference_no, '') AS reference_no,
                           COALESCE(pa.payment_receipt_number, '') AS bill_number,
                           COALESCE(preg.patient_id, '') AS patient_name,
                           rel.doctor_profile_id AS doctor_id,
                           COALESCE(dp.name, 'No Doctor') AS doctor_name,
                           ({app_fee})::double precision AS consultation_fee,
                           COALESCE(pa.register_mode_payment, 'cash') AS payment_mode,
                           ({app_total})::double precision AS total_amount
                      FROM patient_appointment pa
                      JOIN doctor_profile_patient_appointment_rel rel
                        ON rel.patient_appointment_id = pa.id
                 LEFT JOIN patient_reg preg ON preg.id = pa.patient_id
                 LEFT JOIN doctor_profile dp ON dp.id = rel.doctor_profile_id
                      {fee_join}
                     WHERE pa.appointment_date >= %(date_from)s
                       AND pa.appointment_date <= %(date_to)s
                       AND pa.status NOT IN ('unpaid', 'cancelled')
                       AND (%(doctor_id)s IS NULL OR rel.doctor_profile_id = %(doctor_id)s)
                   ) lines
             ORDER BY doctor_name, report_date, reference_no
        """.format(reg_total=reg_total, app_fee=app_fee, app_total=app_total, fee_join=fee_join)
        self.env.cr.execute(query, {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'doctor_id': self.doctor_id.id or None,
        })
        rows = self.env.cr.fetchall()
        bucket[cache_key] = rows
        return rows

    def get_lines_grouped_by_doctor(self):
        self.ensure_one()
        grouped = OrderedDict()
        for (report_date, reference_no, bill_number, patient_name, doctor_id,
             doctor_name, consultation_fee, _payment_mode, cash_amount, credit_amount,
             total_amount) in self._fetch_op_collection_rows():
            key = doctor_id or 0
            bucket = grouped.get(key)
            if bucket is None:
                bucket = {
                    'doctor_name': doctor_name or 'No Doctor',
                    'lines': [],
                    'sum_consultation': 0.0,
                    'sum_cash': 0.0,
                    'sum_credit': 0.0,
                    'sum_total': 0.0,
                }
                grouped[key] = bucket
            bucket['lines'].append(_ReportLine(
                report_date, reference_no, bill_number, patient_name,
                consultation_fee, cash_amount, credit_amount, total_amount,
            ))
            bucket['sum_consultation'] += float(consultation_fee or 0.0)
            bucket['sum_cash'] += float(cash_amount or 0.0)
            bucket['sum_credit'] += float(credit_amount or 0.0)
            bucket['sum_total'] += float(total_amount or 0.0)
        return list(grouped.values())

    def get_report_grand_totals(self):
        self.ensure_one()
        groups = self.get_lines_grouped_by_doctor()
        return {
            'consultation': sum(g['sum_consultation'] for g in groups),
            'cash': sum(g['sum_cash'] for g in groups),
            'credit': sum(g['sum_credit'] for g in groups),
            'total': sum(g['sum_total'] for g in groups),
        }

    def action_view_report(self):
        """On-screen lines from the same SQL as PDF. Batch insert, no patient computes."""
        self.ensure_one()
        if self.line_ids:
            self.line_ids.unlink()
        bucket = getattr(self.env, '_op_collection_rows', None)
        if bucket is not None:
            bucket.pop((self.id, self.date_from, self.date_to, self.doctor_id.id or 0), None)

        vals_list = []
        allowed_modes = ('cash', 'card', 'cheque', 'credit', 'upi')
        for (report_date, reference_no, bill_number, patient_name, doctor_id,
             _doctor_name, consultation_fee, payment_mode, cash_amount, credit_amount,
             total_amount) in self._fetch_op_collection_rows():
            vals_list.append({
                'wizard_id': self.id,
                'reference_no': reference_no or '',
                'date': report_date,
                'patient_name': patient_name or '',
                'doctor_id': doctor_id or False,
                'payment_mode': payment_mode if payment_mode in allowed_modes else 'cash',
                'consultation_fee': int(consultation_fee or 0),
                'bill_number': bill_number or '',
                'cash_amount': cash_amount or 0.0,
                'credit_amount': credit_amount or 0.0,
                'total_amount': total_amount or 0.0,
            })
        Line = self.env['doctor.wise.collection.line']
        for start in range(0, len(vals_list), 500):
            Line.create(vals_list[start:start + 500])

        return {
            'type': 'ir.actions.act_window',
            'name': 'OP Collection Report',
            'res_model': 'doctor.wise.collection.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def _fmt_date(self, value):
        if not value:
            return ''
        if isinstance(value, str):
            return value
        return value.strftime('%d/%m/%Y')

    def _fmt_num(self, value):
        number = float(value or 0.0)
        if number.is_integer():
            return str(int(number))
        return '%.2f' % number

    def op_collection_pdf_html(self):
        """One HTML table. The PDF engine does not walk each row in QWeb."""
        self.ensure_one()
        groups = self.get_lines_grouped_by_doctor()
        grand_consultation = grand_cash = grand_credit = grand_total = 0.0
        parts = [
            '<style>'
            'table{width:100%;border-collapse:collapse;font-size:11px;font-family:Arial,sans-serif;}'
            'th,td{border:1px solid #000;padding:2px 4px;}'
            'th{background:#eee;}'
            '.doc{background:#ddd;font-weight:bold;}'
            '.num{text-align:right;}'
            'h2,p{text-align:center;margin:4px 0;font-family:Arial,sans-serif;}'
            '</style>',
            '<h2 style="margin-bottom:0;">SANTHWANA HOSPITAL</h2>',
            '<p>N.C.C Road, Ambalamukku, Trivandrum-695005<br/>'
            'Phone: 0471-2432121, 4223131</p>',
            '<h2>OP Collection Report</h2>',
            '<p><strong>From:</strong> %s &nbsp; <strong>To:</strong> %s</p>' % (
                escape(self._fmt_date(self.date_from)),
                escape(self._fmt_date(self.date_to)),
            ),
            '<table><thead><tr>'
            '<th>Sl No.</th><th>Date</th><th>UHID</th><th>Bill Number</th><th>Patient</th>'
            '<th>Consultation Fee</th><th>Cash/Card/UPI</th><th>Credit</th><th>Others</th><th>Total</th>'
            '</tr></thead><tbody>',
        ]
        sl = 0
        for group in groups:
            parts.append('<tr class="doc"><td colspan="10">%s</td></tr>' % escape(group['doctor_name'] or 'No Doctor'))
            for line in group['lines']:
                sl += 1
                parts.append(
                    '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                    '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>'
                    '<td></td><td class="num">%s</td></tr>' % (
                        sl,
                        escape(self._fmt_date(line.date)),
                        escape(line.reference_no or ''),
                        escape(line.bill_number or ''),
                        escape(line.patient_name or ''),
                        self._fmt_num(line.consultation_fee),
                        self._fmt_num(line.cash_amount),
                        self._fmt_num(line.credit_amount),
                        self._fmt_num(line.total_amount),
                    )
                )
            parts.append(
                '<tr><td></td><td></td><td></td><td></td><td></td>'
                '<td class="num"><strong>%s</strong></td>'
                '<td class="num"><strong>%s</strong></td>'
                '<td class="num"><strong>%s</strong></td><td></td>'
                '<td class="num"><strong>%s</strong></td></tr>' % (
                    self._fmt_num(group['sum_consultation']),
                    self._fmt_num(group['sum_cash']),
                    self._fmt_num(group['sum_credit']),
                    self._fmt_num(group['sum_total']),
                )
            )
            grand_consultation += group['sum_consultation']
            grand_cash += group['sum_cash']
            grand_credit += group['sum_credit']
            grand_total += group['sum_total']
        parts.append('</tbody><tfoot><tr><td></td><td></td><td></td><td></td><td></td>')
        parts.append(
            '<td class="num"><strong>Consultation: %s</strong></td>'
            '<td class="num"><strong>Cash: %s</strong></td>'
            '<td class="num"><strong>Credit: %s</strong></td>'
            '<td><strong>Others:</strong></td>'
            '<td class="num"><strong>Grand Total: %s</strong></td></tr></tfoot></table>' % (
                self._fmt_num(grand_consultation),
                self._fmt_num(grand_cash),
                self._fmt_num(grand_credit),
                self._fmt_num(grand_total),
            )
        )
        return ''.join(parts)

    def action_print_pdf(self):
        """PDF from SQL + one HTML string. Does not render a QWeb row per patient."""
        self.ensure_one()
        html = (
            '<html><head><meta charset="utf-8"/></head><body>%s</body></html>'
            % self.op_collection_pdf_html()
        ).encode('utf-8')
        report = self.env['ir.actions.report'].sudo()
        pdf = report._run_wkhtmltopdf([html])
        attachment = self.env['ir.attachment'].create({
            'name': 'OP_Collection_Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def action_print_excel(self):
        self.ensure_one()
        groups = self.get_lines_grouped_by_doctor()
        grand = self.get_report_grand_totals()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("OP Collection Report")

        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'align': 'center', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        bold_right = workbook.add_format({'bold': True, 'align': 'right', 'border': 1})
        bold_center = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        date_format = workbook.add_format({'num_format': 'dd-mm-yyyy', 'border': 1})

        sheet.merge_range('A1:G1', 'SANTHWANA HOSPITAL', title_format)
        sheet.merge_range('A2:G2', 'N.C.C Road, Ambalamukku, Trivandrum-695005', bold_center)
        sheet.merge_range('A3:G3', 'Phone: 0471-2432121, 4223131', bold_center)
        sheet.merge_range('A4:G4', 'Email: info@santhwanahospital.com | Website: www.santhwanahospital.com',
                          bold_center)
        sheet.merge_range('A5:G5', 'NABH Pre Accredited Hospital | ISO 9001-2015 CERTIFIED', bold_center)
        sheet.merge_range('A6:G6', 'OP COLLECTION REPORT', title_format)

        date_from = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
        date_to = self.date_to.strftime('%d/%m/%Y') if self.date_to else ''
        sheet.merge_range('A7:G7', "From: %s    To: %s" % (date_from, date_to), bold_center)

        headers = ['Sl No.', 'Date', 'Bill Number', 'UHID', 'Patient', 'Consultation Fee',
                   'Cash/Card/UPI', 'Credit', 'Others', 'Total']
        sheet.write_row(8, 0, headers, header_format)
        row = 9
        sl = 1

        for group in groups:
            sheet.merge_range(row, 0, row, 9, "Doctor: %s" % group['doctor_name'], header_format)
            row += 1
            for line in group['lines']:
                sheet.write(row, 0, sl, cell_format)
                if line.date:
                    written = line.date
                    if isinstance(written, date) and not isinstance(written, datetime):
                        written = datetime.combine(written, datetime.min.time())
                    sheet.write_datetime(row, 1, written, date_format)
                else:
                    sheet.write(row, 1, '', cell_format)
                sheet.write(row, 2, line.bill_number or '', cell_format)
                sheet.write(row, 3, line.reference_no or '', cell_format)
                sheet.write(row, 4, line.patient_name or '', cell_format)
                sheet.write(row, 5, line.consultation_fee or 0, cell_format)
                sheet.write(row, 6, line.cash_amount or 0, num_format)
                sheet.write(row, 7, line.credit_amount or 0, num_format)
                sheet.write(row, 8, '', cell_format)
                sheet.write(row, 9, line.total_amount or 0, num_format)
                row += 1
                sl += 1

            sheet.write(row, 0, '', cell_format)
            sheet.write(row, 1, '', cell_format)
            sheet.write(row, 2, '', cell_format)
            sheet.write(row, 3, '', cell_format)
            sheet.write(row, 4, 'Subtotal', bold_right)
            sheet.write(row, 5, group['sum_consultation'], num_format)
            sheet.write(row, 6, group['sum_cash'], num_format)
            sheet.write(row, 7, group['sum_credit'], num_format)
            sheet.write(row, 8, '', cell_format)
            sheet.write(row, 9, group['sum_total'], num_format)
            row += 2

        sheet.write(row, 4, 'Grand Total', bold_right)
        sheet.write(row, 5, grand['consultation'], num_format)
        sheet.write(row, 6, grand['cash'], num_format)
        sheet.write(row, 7, grand['credit'], num_format)
        sheet.write(row, 8, '', cell_format)
        sheet.write(row, 9, grand['total'], num_format)

        sheet.set_column('A:A', 8)
        sheet.set_column('B:B', 15)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:G', 15)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'OP_Collection_Report.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'store_fname': 'OP_Collection_Report.xlsx',
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }


class ReportOpCollectionPdf(models.AbstractModel):
    _name = 'report.homeo_doctor.report_doctor_collection_pdf_template'
    _description = 'OP Collection PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['doctor.wise.collection.wizard'].browse(docids)
        grouped_by_doc = {}
        grand_by_doc = {}
        for doc in docs:
            grouped_by_doc[doc.id] = doc.get_lines_grouped_by_doctor()
            grand_by_doc[doc.id] = doc.get_report_grand_totals()
        return {
            'doc_ids': docids,
            'doc_model': 'doctor.wise.collection.wizard',
            'docs': docs,
            'data': data or {},
            'grouped_by_doc': grouped_by_doc,
            'grand_by_doc': grand_by_doc,
        }


class DoctorWiseCollectionLine(models.TransientModel):
    _name = 'doctor.wise.collection.line'
    _description = 'Doctor Wise Collection Line'
    _order = 'date asc'

    wizard_id = fields.Many2one(
        'doctor.wise.collection.wizard',
        string="Wizard",
        ondelete="cascade"
    )
    reference_no = fields.Char(string="UHID")
    patient_name = fields.Char(string="Patient")
    doctor_id = fields.Many2one('doctor.profile', string="Doctor", ondelete='set null')
    payment_mode = fields.Selection(
        [('cash', 'Cash'),
         ('card', 'Card'),
         ('cheque', 'Cheque'),
         ('credit', 'Credit'),
         ('upi', 'Mobile Pay'), ],
        string="Payment Mode"
    )
    amount = fields.Float(string="Amount")
    cash_amount = fields.Float('Cash Amount')
    credit_amount = fields.Float('Credit Amount')
    total_amount = fields.Float('Total Amount')
    registration_fee = fields.Many2one(
        'patient.registration.fee',
        string="Registration Fee",
        ondelete='set null',
    )

    registration_fee1 = fields.Integer(string='Rev-Registration fee')
    consultation_fee = fields.Integer(string='Consultation Fee')
    bill_number = fields.Char(string="Bill Number")
    date = fields.Date(string='Date')


class PatientRegistrationFee(models.Model):
    _inherit = 'patient.registration.fee'

    def unlink(self):
        """Clear child references safely before deleting parent."""
        DoctorLine = self.env['doctor.wise.collection.line']
        for rec in self:
            lines = DoctorLine.search([('registration_fee', '=', rec.id)])
            if lines:
                lines.write({'registration_fee': False})
                self.env.cr.flush()
        return super(PatientRegistrationFee, self).unlink()

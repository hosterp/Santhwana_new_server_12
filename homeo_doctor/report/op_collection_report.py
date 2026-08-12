import io
import base64
import xlsxwriter
from odoo import models, fields, api
from odoo.exceptions import UserError

class DoctorWiseCollectionWizard(models.TransientModel):
    _name = 'doctor.wise.collection.wizard'
    _description = 'Doctor Wise Collection Wizard'

    date_from = fields.Date(string="From Date", required=True,default=fields.Date.context_today)
    date_to = fields.Date(string="To Date", required=True,default=fields.Date.context_today)
    doctor_id = fields.Many2one('doctor.profile', string="Doctor",default=lambda self: self._default_doctor())

    line_ids = fields.One2many(
        'doctor.wise.collection.line',
        'wizard_id',
        string="Collection Lines"
    )

    @api.model
    def _default_doctor(self):
        user_name = self.env.user.name

        doctor = self.env['doctor.profile'].search(
            [('name', '=', user_name)],
            limit=1
        )

        return doctor
    def action_view_report(self):
        self.ensure_one()  # operate on single wizard instance
        # remove any existing lines
        if self.line_ids:
            self.line_ids.unlink()

        # Build safe base domains (no broken |/& structure)
        domain_reg = [
            ('time', '>=', self.date_from),
            ('time', '<=', self.date_to),
            ('status', '!=', 'cancelled'),
        ]
        domain_app = [
            ('appointment_date', '>=', self.date_from),
            ('appointment_date', '<=', self.date_to),
            ('status', 'not in', ['unpaid', 'cancelled']),
        ]

        # Optional: if you must require vssc_boolean True, uncomment these:
        # domain_reg.append(('vssc_boolean', '=', True))
        # domain_app.append(('vssc_boolean', '=', True))

        # If a doctor is selected, filter results for that doctor
        if self.doctor_id:
            domain_reg.append(('doc_name', '=', self.doctor_id.id))
            domain_app.append(('doctor_ids', 'in', [self.doctor_id.id]))

        # Search
        patients_reg = self.env['patient.reg'].search(domain_reg)
        patients_app = self.env['patient.appointment'].search(domain_app)



        # Helper to resolve patient display name safely
        def _patient_display(rec):
            # handle different shapes of patient relation
            if hasattr(rec, 'patient_id') and rec.patient_id:
                # patient.reg may store patient as Many2one
                return getattr(rec.patient_id, 'name', False) or getattr(rec.patient_id, 'patient_id', False) or False
            return False

        # Create lines from registrations
        for rec in patients_reg:
            payment_mode = rec.register_mode_payment or 'cash'
            amount = float(rec.register_total_amount or 0.0)

            cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
            credit_amount = amount if payment_mode == 'credit' else 0.0

            # If doctor filter is selected, zero out totals per your requirement
            if self.doctor_id:
                cash_amount = 0.0
                credit_amount = 0.0
                amount = 0.0

            # determine doctor id from registration safely
            reg_doctor_id = False
            if hasattr(rec, 'doc_name') and rec.doc_name:
                # doc_name may be many2one or char; prefer id if Many2one
                reg_doctor_id = rec.doc_name.id if hasattr(rec.doc_name, 'id') else False

            # safe patient name
            patient_name = False
            if hasattr(rec, 'patient_id') and rec.patient_id:
                patient_name = getattr(rec.patient_id, 'name', False) or getattr(rec.patient_id, 'patient_id', False)

            self.env['doctor.wise.collection.line'].create({
                'wizard_id': self.id,
                'reference_no': rec.reference_no or '',
                'date': rec.time,
                'patient_name': rec.patient_id,
                'doctor_id': reg_doctor_id,
                'payment_mode': payment_mode,
                'consultation_fee': float(rec.consultation_fee or 0.0),
                'bill_number': rec.bill_number or '',
                'cash_amount': cash_amount,
                'credit_amount': credit_amount,
                'total_amount': amount,
            })

        # Create lines from appointments (one line per doctor in the appointment)
        for rec in patients_app:
            for doc in rec.doctor_ids:
                payment_mode = rec.register_mode_payment or 'cash'
                amount = float(rec.register_total_amount or 0.0)

                cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
                credit_amount = amount if payment_mode == 'credit' else 0.0

                if self.doctor_id:
                    cash_amount = 0.0
                    credit_amount = 0.0
                    amount = 0.0

                # patient display (appointment might reference patient differently)
                patient_name = False
                if hasattr(rec, 'patient_id') and rec.patient_id:
                    patient_name = getattr(rec.patient_id, 'name', False) or getattr(rec.patient_id, 'patient_id', False)

                self.env['doctor.wise.collection.line'].create({
                    'wizard_id': self.id,
                    'reference_no': (rec.patient_id.reference_no if rec.patient_id and hasattr(rec.patient_id, 'reference_no') else ''),
                    'date': rec.appointment_date,
                    'patient_name': patient_name,
                    'doctor_id': doc.id,
                    'payment_mode': payment_mode,
                    'consultation_fee': float(rec.consultation_fee or 0.0),
                    'bill_number': rec.payment_receipt_number or '',
                    'cash_amount': cash_amount,
                    'credit_amount': credit_amount,
                    'total_amount': amount,
                })

        # return wizard form to show populated lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'doctor.wise.collection.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'group_by': 'doctor_id'},
        }

    def action_print_pdf(self):
        """Generate PDF report for doctor wise collection."""
        self.action_view_report()
        return self.env.ref('homeo_doctor.action_report_doctor_collection_pdf').report_action(self)
    def action_print_excel(self):
        """Generate Excel report similar to the PDF layout"""
        self.action_view_report()  # ensure data is prepared

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("OP Collection Report")

        # === Styles ===
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'align': 'center', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        bold_right = workbook.add_format({'bold': True, 'align': 'right', 'border': 1})
        bold_center = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})

        # === Header Section ===
        sheet.merge_range('A1:G1', 'SANTHWANA HOSPITAL', title_format)
        sheet.merge_range('A2:G2', 'N.C.C Road, Ambalamukku, Trivandrum-695005', bold_center)
        sheet.merge_range('A3:G3', 'Phone: 0471-2432121, 4223131', bold_center)
        sheet.merge_range('A4:G4', 'Email: info@santhwanahospital.com | Website: www.santhwanahospital.com',
                          bold_center)
        sheet.merge_range('A5:G5', 'NABH Pre Accredited Hospital | ISO 9001-2015 CERTIFIED', bold_center)
        sheet.merge_range('A6:G6', 'OP COLLECTION REPORT', title_format)

        # Date range
        date_from = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
        date_to = self.date_to.strftime('%d/%m/%Y') if self.date_to else ''
        sheet.merge_range('A7:G7', f"From: {date_from}    To: {date_to}", bold_center)

        # === Table Header ===
        headers = ['Sl No.','Date','Bill Number','UHID', 'Patient','Consultation Fee', 'Cash/Card/UPI', 'Credit', 'Others', 'Total']
        sheet.write_row(8, 0, headers, header_format)
        row = 9
        sl = 1
        date_format = workbook.add_format({'num_format': 'dd-mm-yyyy', 'border': 1})
        # === Group by doctor ===
        grouped = {}
        for line in self.line_ids:
            grouped.setdefault(line.doctor_id, []).append(line)

        # === Populate data ===
        for doctor, lines in grouped.items():
            # Doctor header row
            sheet.merge_range(row, 0, row, 6, f"Doctor: {doctor.name if doctor else 'No Doctor'}", header_format)
            row += 1

            # Lines for each doctor
            for line in lines:
                sheet.write(row, 0, sl, cell_format)
                sheet.write_datetime(row, 1, line.date, date_format)
                sheet.write(row, 2, line.bill_number or '', cell_format)
                sheet.write(row, 3, line.reference_no or '', cell_format)
                sheet.write(row, 4, line.patient_name or '', cell_format)
                sheet.write(row, 5, line.consultation_fee or '', cell_format)
                sheet.write(row, 6, line.cash_amount or 0, num_format)
                sheet.write(row, 7, line.credit_amount or 0, num_format)
                sheet.write(row, 8, '', cell_format)  # Others (empty for now)
                sheet.write(row, 9, line.total_amount or 0, num_format)
                row += 1
                sl += 1

            # Subtotal row per doctor
            sheet.write(row, 0, '', cell_format)
            sheet.write(row, 1, '', cell_format)
            sheet.write(row, 2, '', cell_format)
            sheet.write(row, 3, '', cell_format)
            sheet.write(row, 4, 'Subtotal', bold_right)
            sheet.write(row, 5, sum(l.consultation_fee for l in lines), num_format)
            sheet.write(row, 6, sum(l.cash_amount for l in lines), num_format)
            sheet.write(row, 7, sum(l.credit_amount for l in lines), num_format)
            sheet.write(row, 8, '', cell_format)
            sheet.write(row, 9, sum(l.total_amount for l in lines), num_format)
            row += 2  # space after each doctor

        # === Grand Total ===
        sheet.write(row, 4, 'Grand Total', bold_right)
        sheet.write(row, 5, sum(line.consultation_fee for line in self.line_ids), num_format)
        sheet.write(row, 6, sum(line.cash_amount for line in self.line_ids), num_format)
        sheet.write(row, 7, sum(line.credit_amount for line in self.line_ids), num_format)
        sheet.write(row, 8, '', cell_format)
        sheet.write(row, 9, sum(line.total_amount for line in self.line_ids), num_format)

        # Adjust column widths
        sheet.set_column('A:A', 8)
        sheet.set_column('B:B', 15)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:G', 15)

        workbook.close()
        output.seek(0)

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'OP_Collection_Report.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'store_fname': 'OP_Collection_Report.xlsx',
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Return Excel download link
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
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

    registration_fee1=fields.Integer(string='Rev-Registration fee', ondelete='set null')
    consultation_fee = fields.Integer(string='Consultation Fee',  ondelete='set null')
    bill_number = fields.Char(string="Bill Number",  ondelete='set null')
    date=fields.Date(string='Date')


class PatientRegistrationFee(models.Model):
    _inherit = 'patient.registration.fee'

    def unlink(self):
        """Clear child references safely before deleting parent."""
        DoctorLine = self.env['doctor.wise.collection.line']
        for rec in self:
            lines = DoctorLine.search([('registration_fee', '=', rec.id)])
            if lines:
                lines.write({'registration_fee': False})
                # 🧩 Force database flush before deleting parent
                self.env.cr.flush()
        return super(PatientRegistrationFee, self).unlink()

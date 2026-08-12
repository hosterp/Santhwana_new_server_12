# controllers/main.py
from odoo import http
from odoo.http import request
import io
import xlsxwriter
from datetime import datetime, time
from io import BytesIO
from collections import defaultdict
import base64
from odoo.addons.web.controllers.main import Home
import pytz
from odoo.fields import Datetime
import requests
class PatientExcelReport(http.Controller):

    @http.route('/web/binary/download_patient_excel', type='http', auth="user")
    def download_excel(self, from_date=None, to_date=None, **kwargs):
        from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
        domain = [
            ('time', '>=', from_dt),
            ('time', '<=', to_dt),
            '|',
            '&', ('status', '=', 'unpaid'), ('register_mode_payment', '=', 'credit'),
            ('status', 'not in', ['unpaid', 'cancelled']),
        ]

        if kwargs.get('register_mode_payment'):
            domain.append(('register_mode_payment', '=', kwargs['register_mode_payment']))

        records = request.env['patient.reg'].search(domain)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet("Patient Report")
        bold = workbook.add_format({'bold': True})

        headers = ['UHID', 'Name', 'Age', 'Address', 'Phone', 'Doctor Name','Payment Mode', 'Total Amount']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)


        max_lengths = [len(header) for header in headers] 
        total_amount = 0

        for rec in records:
            row_data = [
                str(rec.reference_no),
                str(rec.patient_id),
                str(rec.age),
                str(rec.address),
                str(rec.phone_number),
                str(rec.doc_name.name),
                str(rec.register_mode_payment),
                str(rec.register_total_amount)
            ]
            for col, value in enumerate(row_data):
                max_lengths[col] = max(max_lengths[col], len(value))


            total_amount += rec.register_total_amount


        for col, max_len in enumerate(max_lengths):
            sheet.set_column(col, col, max_len + 2)


        for row, rec in enumerate(records, start=1):
            sheet.write(row, 0, rec.reference_no)
            sheet.write(row, 1, rec.patient_id)
            sheet.write(row, 2, str(rec.age))
            sheet.write(row, 3, str(rec.address))
            sheet.write(row, 4, rec.phone_number)
            sheet.write(row, 5, rec.doc_name.name)
            sheet.write(row, 6, rec.register_mode_payment)
            sheet.write(row, 7, rec.register_total_amount)


        sheet.write(len(records) + 1, 5, "Total Amount", bold)
        sheet.write(len(records) + 1, 6, total_amount)

        workbook.close()
        output.seek(0)
        response = request.make_response(output.read(),
            headers=[('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                     ('Content-Disposition', 'attachment; filename="patient_report.xlsx"')],
            cookies={'fileToken': '123'})
        return response
class GeneralBillingExcelDownload(http.Controller):

    @http.route('/general_billing_excel/download', type='http', auth="user")
    def download_excel(self, date_from=None, date_to=None, **kwargs):
        # Parse the full datetime and convert to date
        df = datetime.strptime(date_from, '%Y-%m-%d %H:%M:%S').date()
        dt = datetime.strptime(date_to, '%Y-%m-%d %H:%M:%S').date()

        # Search billing records
        domain = [('bill_date', '>=', df), ('bill_date', '<=', dt)]
        records = request.env['general.billing'].sudo().search(domain)

        # Create Excel file in memory
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('General Billing Report')

        # Set styles
        bold = workbook.add_format({'bold': True})

        # Header labels
        headers = [
            'SL No', 'Bill No', 'Bill Date', 'Type', 'Department',
            'Category', 'MRD No', 'Patient Name', 'Gender', 'Doctor','Payment Method', 'Amount'
        ]

        # Track max width for each column
        max_col_widths = defaultdict(int)

        # Write header row
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)
            max_col_widths[col] = len(header)

        # Write data rows and update max column widths
        for row_num, rec in enumerate(records, start=1):
            row_data = [
                str(row_num),
                rec.bill_number or '',
                rec.bill_date.strftime('%d/%m/%Y %H:%M') if rec.bill_date else '',
                rec.bill_type.display_name if rec.bill_type else '',
                rec.department.display_name if hasattr(rec.department, 'display_name') else str(rec.department or ''),
                rec.op_category.display_name if hasattr(rec.op_category, 'display_name') else str(rec.op_category or ''),
                rec.mrd_no.display_name if hasattr(rec.mrd_no, 'display_name') else str(rec.mrd_no or ''),
                rec.patient_name or '',
                dict(rec._fields['gender'].selection).get(rec.gender, ''),
                rec.doctor.display_name if rec.doctor else '',
                rec.mode_pay if rec.mode_pay else '',
                str(rec.total_amount or '')
            ]

            for col, value in enumerate(row_data):
                sheet.write(row_num, col, value)
                max_col_widths[col] = max(max_col_widths[col], len(str(value)))

        # Adjust column widths based on max content width + padding
        for col, width in max_col_widths.items():
            sheet.set_column(col, col, width + 2)

        # Finalize workbook
        workbook.close()
        output.seek(0)

        # Filename
        filename = f"General_Billing_{df.strftime('%d%m%Y')}_{dt.strftime('%d%m%Y')}.xlsx"
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', f'attachment; filename={filename}'),
        ]
        return request.make_response(output.read(), headers)

class DoctorLabReportExcel(http.Controller):

    @http.route('/doctor_lab_report/download_excel', type='http', auth='user')
    def download_excel(self, from_date=None, to_date=None, mode_pay=None, bill_type=None, **kwargs):
        domain = []
        if from_date and to_date:
            domain += [('date', '>=', from_date), ('date', '<=', to_date)]
        if mode_pay:
            domain += [('mode_of_payment', '=', mode_pay)]
        if bill_type:
            domain += [('bill_type', '=', bill_type)]

        lab_reports = request.env['doctor.lab.report'].sudo().search(domain,order='date asc')

        # Create in-memory Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Lab Reports")
        bold_format = workbook.add_format({'bold': True})
        # Headers
        headers = ['Sl No', 'Date', 'Bill Number', 'Patient Name', 'MRD/OP No', 'Total Bill Amount']
        for col, header in enumerate(headers):
            sheet.write(0, col, header,bold_format)

        grand_total = 0  # Initialize grand total

        # Data rows with Sl No starting from 1
        for row_num, report in enumerate(lab_reports, start=1):
            sheet.write(row_num, 0, row_num)  # Sl No
            sheet.write(row_num, 1, report.date.strftime('%d-%m-%Y') if report.date else '')
            sheet.write(row_num, 2, report.report_reference)
            sheet.write(row_num, 3, report.patient_name)
            sheet.write(row_num, 4, report.user_ide.display_name)
            sheet.write(row_num, 5, report.total_bill_amount)

            grand_total += report.total_bill_amount or 0  # Add to grand total

        # Write Grand Total in the next row
        total_row = len(lab_reports) + 1
        sheet.write(total_row, 4, "Grand Total",bold_format)  # Label
        sheet.write(total_row, 5, grand_total,bold_format)  # Total amount

        workbook.close()
        output.seek(0)

        filename = f"Lab_Report_{from_date}_to_{to_date}.xlsx"
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}')
            ]
        )

class PharmacyDescriptionReportController(http.Controller):

    @http.route('/pharmacy_description/download_excel', type='http', auth='user')
    def download_excel(self, mode_pay=None, op_category=None, from_date=None, to_date=None):

        # Convert empty strings to False (Excel filter fix)
        payment_mode = mode_pay or False
        op_category = op_category or False

        # Base domain
        domain = [
            ('date', '>=', from_date),
            ('date', '<=', to_date),
            ('status', '!=', 'cancelled'),
        ]

        # Apply dynamic filters
        if payment_mode:
            domain.append(('payment_mathod', '=', payment_mode))

        if op_category:
            domain.append(('op_category', '=', op_category))

        # Fetch records
        pharmacy_records = request.env['pharmacy.description'].sudo().search(
            domain, order='date asc'
        )

        # Create Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Pharmacy Report')
        bold_format = workbook.add_format({'bold': True})
        # Header row
        headers = [
            'SL No', 'Bill No', 'Date', 'Name',
             'Payment Mode', 'Amount'
        ]
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)

        # Data rows
        row = 1
        sl_no = 1
        total_amount = 0
        for record in pharmacy_records:
            worksheet.write(row, 0, sl_no)
            worksheet.write(row, 1, record.bill_number or '')
            worksheet.write(row, 2, record.date.strftime('%Y-%m-%d') if record.date else '')
            worksheet.write(row, 3, record.name or '')
            # worksheet.write(row, 4, record.id)
            worksheet.write(row, 4, record.payment_mathod or '')
            worksheet.write(row, 5, record.bill_amount or 0)
            total_amount += record.bill_amount
            row += 1
            sl_no += 1

        row += 1
        worksheet.write(row, 4, 'TOTAL', bold_format)
        worksheet.write(row, 5, total_amount, bold_format)

        workbook.close()
        output.seek(0)

        # Response
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition',
                 'attachment; filename="pharmacy_description_report.xlsx"')
            ]
        )

class PatientAdmissionReportController(http.Controller):

    @http.route('/export_patient_admission_report', type='http', auth='user', website=True)
    def export_patient_admission_report(self, date_from, date_to, **kwargs):
        # Get the patient records within the date range
        patient_records = request.env['patient.reg'].search([
            ('admitted_date', '>=', date_from),
            ('admitted_date', '<=', date_to),
            ('status', '=', 'admitted')
        ])

        # Prepare data for the Excel report
        report_data = []
        for patient in patient_records:
            report_data.append({
                'patient_name': patient.patient_id,
                'admitted_date': patient.admitted_date,
                'room': patient.room_number_new.room_number if patient.room_number_new else '',
                'total_amount': patient.admission_total_amount,
                'uhid': patient.reference_no,
            })

        # Generate the Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Patient Admission Report')

        # Set column widths
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 20)

        # Write the headers
        worksheet.write('A1', 'UHID')
        worksheet.write('B1', 'Patient Name')
        worksheet.write('C1', 'Admission Date')
        worksheet.write('D1', 'Room')
        worksheet.write('E1', 'Total Bill Amount')

        # Write the data
        row = 1
        for line in report_data:
            worksheet.write(row, 0, line['uhid'])
            worksheet.write(row, 1, line['patient_name'])
            worksheet.write(row, 2, str(line['admitted_date']))
            worksheet.write(row, 3, line['room'])
            worksheet.write(row, 4, line['total_amount'])
            row += 1

        workbook.close()

        # Get the Excel file from memory
        output.seek(0)
        file_data = output.read()

        # Base64 encode the file content for attachment
        encoded_file_data = base64.b64encode(file_data)

        # Create an attachment (Base64 encoded)
        attachment = request.env['ir.attachment'].create({
            'name': 'Patient_Admission_Report.xlsx',
            'type': 'binary',
            'datas': encoded_file_data,  # Store the Base64 encoded file content
            'store_fname': 'Patient_Admission_Report.xlsx',
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Return the file as a downloadable link
        return request.make_response(
            file_data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="Patient_Admission_Report.xlsx"')
            ]
        )
class PatientReportController(http.Controller):

    @http.route('/patient/excel_report', type='http', auth='user')
    def download_excel_report(self, **kwargs):
        date_from = kwargs.get('date_from')
        date_to = kwargs.get('date_to')
        doctor_id = kwargs.get('doctor_id')

        report_data = []
        user_tz = pytz.timezone(request.env.user.tz or 'Asia/Kolkata')

        date_from_dt = None
        date_to_dt = None

        if date_from:
            date_from_dt = Datetime.to_datetime(date_from).replace(hour=0, minute=0, second=0)
        if date_to:
            date_to_dt = Datetime.to_datetime(date_to).replace(hour=23, minute=59, second=59)
        # -------------------------------
        # 1️⃣ Build domain for patient.reg
        # -------------------------------
        domain_reg = []
        if date_from:
            domain_reg.append(('time', '>=', date_from_dt))
        if date_to:
            domain_reg.append(('time', '<=', date_to_dt))
        if doctor_id:
            domain_reg.append(('doc_name', '=', int(doctor_id)))
        domain_reg.append(('status', '!=', 'cancelled'))

        patients_reg = request.env['patient.reg'].sudo().search(domain_reg,order='bill_number asc')

        for p in patients_reg:
            report_data.append({
                'reference_no': p.reference_no,
                'date': p.time,
                'patient_name': p.patient_id,
                'age': p.age,
                'gender': p.gender,
                'phone': p.phone_number,
                'doctor': p.doc_name.name,
                'consultation_fee': p.register_total_amount or 0,
                'bill_number': p.bill_number,
            })

        # ---------------------------------------
        # 2️⃣ Build domain for patient.appointment
        # ---------------------------------------
        domain_app = []
        if date_from:
            domain_app.append(('appointment_date', '>=', date_from_dt))
        if date_to:
            domain_app.append(('appointment_date', '<=', date_to_dt))
        if doctor_id:
            domain_app.append(('doctor_ids', '=', int(doctor_id)))
        domain_app.append(('status', '!=', 'cancelled'))
        patients_app = request.env['patient.appointment'].sudo().search(domain_app,order='payment_receipt_number asc')

        for a in patients_app:
            report_data.append({
                'reference_no': a.patient_id.reference_no,
                'date': a.appointment_date,
                'patient_name': a.patient_name,
                'age': a.age,
                'gender': a.gender,
                'phone': a.phone_number,
                'doctor': a.doctor_ids.name if a.doctor_ids else '',
                'consultation_fee': a.register_total_amount or 0,
                'bill_number': a.payment_receipt_number,
            })

        # --------------------------------
        # 3️⃣ Generate Excel in memory
        # --------------------------------
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Patient Report')

        bold = workbook.add_format({'bold': True})

        headers = [
            'SL No',
            'Bill Number',
            'UHID',
            'Appointment Date',
            'Patient Name',
            'Age',
            'Gender',
            'Mobile',
            'Doctor',
            'Total'
        ]

        # Write headers
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)

        # -------------------------------
        # 4️⃣ Fill Data
        # -------------------------------
        row = 1
        sl_no = 1
        total_fee = 0
        report_data = sorted(report_data, key=lambda x: x['date'])

        for rec in report_data:
            sheet.write(row, 0, sl_no)
            sheet.write(row, 1, rec['bill_number'])
            sheet.write(row, 2, rec['reference_no'])
            sheet.write(row, 3, rec['date'].strftime('%Y-%m-%d') if rec['date'] else '')
            sheet.write(row, 4, rec['patient_name'])
            sheet.write(row, 5, rec['age'])
            sheet.write(row, 6, rec['gender'])
            sheet.write(row, 7, rec['phone'])
            sheet.write(row, 8, rec['doctor'])
            sheet.write(row, 9, rec['consultation_fee'])

            total_fee += rec['consultation_fee']
            row += 1
            sl_no += 1

        # -------------------------------
        # 5️⃣ Total Row
        # -------------------------------
        sheet.write(row, 8, 'Total', bold)
        sheet.write(row, 9, total_fee, bold)

        workbook.close()
        output.seek(0)

        filename = f"Patient_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )
# class AuthLogin(http.Controller):
#     @http.route('/web/login', type='http', auth="public", website=True)
#     def web_login(self, redirect=None, **kw):
#         recaptcha_response = kw.get('g-recaptcha-response')
#         secret_key = ""
#
#         # Verify reCAPTCHA
#         response = requests.post(
#             'https://www.google.com/recaptcha/api/siteverify',
#             data={'secret': secret_key, 'response': recaptcha_response}
#         ).json()
#
#         if not response.get("success"):
#             return request.render('web.login', {'error': 'Invalid reCAPTCHA. Try again.'})
#
#         return http.redirect_with_hash('/web')


class BillGSTReportExcel(http.Controller):

    @http.route('/report/generate/bill_gst_excel', type='http', auth='user')
    def generate_excel_report(self, from_date, to_date, **kwargs):
        # Convert dates to proper datetime range
        from_date_dt = datetime.combine(datetime.strptime(from_date, '%Y-%m-%d').date(), time.min)
        to_date_dt = datetime.combine(datetime.strptime(to_date, '%Y-%m-%d').date(), time.max)

        # Get filters from the request
        op_category = kwargs.get('op_category')     # e.g., 'op', 'ip', 'others'
        payment_method = kwargs.get('payment_method')  # e.g., 'cash', 'card', 'upi', 'credit'

        # Domain for record search
        domain = [
            ('date', '>=', from_date_dt),
            ('date', '<=', to_date_dt)
        ]
        if op_category == 'op':
            # Include everyone except admitted (IP)
            domain.append(('op_category', '!=', 'admitted'))
        elif op_category == 'admitted':
            # Include only admitted
            domain.append(('op_category', '=', 'admitted'))
        elif op_category:

            domain.append(('pharmacy_id.op_category', '=', op_category))
        if payment_method:
            # NOTE: check model spelling, might be `payment_mathod`
            domain.append(('payment_mathod', '=', payment_method))

        # Search data
        bills = request.env['pharmacy.description'].sudo().search(domain)

        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Bill GST Report")

        # Styles
        bold = workbook.add_format({'bold': True})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        filter_fmt = workbook.add_format({'italic': True, 'align': 'center'})

        # Title and Filters (like your HSN report)
        sheet.merge_range('A1:O1', "GST Bill Summary Report", title_fmt)

        filter_text = f"From {from_date} to {to_date}"
        if op_category:
            filter_text += f" | Type: {op_category.upper()}"
        if payment_method:
            filter_text += f" | Payment: {payment_method.capitalize()}"
        sheet.merge_range('A2:O2', filter_text, filter_fmt)

        # Header
        headers = [
            "Sl No", "Bill No", "Bill Date", "Patient", "Category", "Payment Mode",
            "Non Taxable", "GST 5%", "CGST 2.5%", "SGST 2.5%",
            "GST 12%", "CGST 6%", "SGST 6%",
            "GST 18%", "CGST 9%", "SGST 9%", "Total Amount"
        ]
        for col, header in enumerate(headers):
            sheet.write(3, col, header, bold)

        # Totals
        total_non_taxable = total_gst_5 = total_cgst_2_5 = total_sgst_2_5 = 0.0
        total_gst_12 = total_cgst_6 = total_sgst_6 = 0.0
        total_gst_18 = total_cgst_9 = total_sgst_9 = 0.0
        total_amount = 0.0

        row = 4
        sl = 1

        for bill in bills:
            line_items = bill.prescription_line_ids

            gst_5 = sum(line.rate for line in line_items if line.gst == 5)
            cgst_2_5 = sgst_2_5 = gst_5 * 0.025

            gst_12 = sum(line.rate for line in line_items if line.gst == 12)
            cgst_6 = sgst_6 = gst_12 * 0.06

            gst_18 = sum(line.rate for line in line_items if line.gst == 18)
            cgst_9 = sgst_9 = gst_18 * 0.09

            non_taxable = sum(line.rate for line in line_items if not line.gst)

            # Write row data
            sheet.write(row, 0, sl)
            sheet.write(row, 1, bill.bill_number or '')
            sheet.write(row, 2, str(bill.date or ''))
            sheet.write(row, 3, bill.name or '')
            sheet.write(row, 4, bill.op_category or '')
            sheet.write(row, 5, bill.payment_mathod or '')  # ✅ Added Payment Method
            sheet.write(row, 6, round(non_taxable, 2))
            sheet.write(row, 7, round(gst_5, 2))
            sheet.write(row, 8, round(cgst_2_5, 2))
            sheet.write(row, 9, round(sgst_2_5, 2))
            sheet.write(row, 10, round(gst_12, 2))
            sheet.write(row, 11, round(cgst_6, 2))
            sheet.write(row, 12, round(sgst_6, 2))
            sheet.write(row, 13, round(gst_18, 2))
            sheet.write(row, 14, round(cgst_9, 2))
            sheet.write(row, 15, round(sgst_9, 2))
            sheet.write(row, 16, round(bill.total_amount, 2))

            total_non_taxable += non_taxable
            total_gst_5 += gst_5
            total_cgst_2_5 += cgst_2_5
            total_sgst_2_5 += sgst_2_5
            total_gst_12 += gst_12
            total_cgst_6 += cgst_6
            total_sgst_6 += sgst_6
            total_gst_18 += gst_18
            total_cgst_9 += cgst_9
            total_sgst_9 += sgst_9
            total_amount += bill.total_amount

            row += 1
            sl += 1

        # Totals Row
        sheet.write(row, 3, "Total", bold)
        sheet.write(row, 6, round(total_non_taxable, 2), bold)
        sheet.write(row, 7, round(total_gst_5, 2), bold)
        sheet.write(row, 8, round(total_cgst_2_5, 2), bold)
        sheet.write(row, 9, round(total_sgst_2_5, 2), bold)
        sheet.write(row, 10, round(total_gst_12, 2), bold)
        sheet.write(row, 11, round(total_cgst_6, 2), bold)
        sheet.write(row, 12, round(total_sgst_6, 2), bold)
        sheet.write(row, 13, round(total_gst_18, 2), bold)
        sheet.write(row, 14, round(total_cgst_9, 2), bold)
        sheet.write(row, 15, round(total_sgst_9, 2), bold)
        sheet.write(row, 16, round(total_amount, 2), bold)

        workbook.close()
        output.seek(0)

        filename = f"GST_Bill_Report_{from_date}_to_{to_date}.xlsx"
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}')
            ]
        )

# class BillGSTReportExcel(http.Controller):
#
#     @http.route('/report/generate/bill_gst_excel', type='http', auth='user')
class HSNExcelReportController(http.Controller):

        @http.route(['/report/excel/hsn_gst_summary'], type='http', auth='user')
        def generate_hsn_excel(self, from_date, to_date, **kwargs):
            # Convert dates to datetime
            from_date_dt = datetime.combine(datetime.strptime(from_date, '%Y-%m-%d').date(), time.min)
            to_date_dt = datetime.combine(datetime.strptime(to_date, '%Y-%m-%d').date(), time.max)

            # Extract optional filters from kwargs (same as PDF)
            op_category = kwargs.get('op_category')  # e.g., 'op', 'ip', 'others'
            payment_method = kwargs.get('payment_method')  # e.g., 'cash', 'card', 'upi', 'credit'

            # Build domain filters
            domain = [
                ('pharmacy_id.date', '>=', from_date_dt),
                ('pharmacy_id.date', '<=', to_date_dt)
            ]
            if op_category == 'op':
                # Include everyone except admitted (IP)
                domain.append(('pharmacy_id.op_category', '!=', 'admitted'))
            elif op_category == 'admitted':
                # Include only admitted
                domain.append(('pharmacy_id.op_category', '=', 'admitted'))
            elif op_category:

                domain.append(('pharmacy_id.op_category', '=', op_category))
            if payment_method:
                # Note: Field in PDF is `payment_mathod` (check model spelling)
                domain.append(('pharmacy_id.payment_mathod', '=', payment_method))

            # Fetch lines based on domain
            lines = request.env['pharmacy.prescription.line'].sudo().search(domain)
            print("LINES COUNT:", len(lines))

            # Create Excel file in memory
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('HSN GST Summary')

            # Formats
            bold = workbook.add_format({'bold': True})
            money = workbook.add_format({'num_format': '#,##0.00'})
            bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00'})

            # Optional: Title and filter info like PDF
            worksheet.merge_range('A1:J1', "HSN Wise GST Report",
                                  workbook.add_format({'align': 'center', 'bold': True, 'font_size': 14}))
            filter_text = f"From {from_date} to {to_date}"
            if op_category:
                filter_text += f" | Type: {op_category.upper()}"
            if payment_method:
                filter_text += f" | Payment: {payment_method.capitalize()}"
            worksheet.merge_range('A2:J2', filter_text, workbook.add_format({'align': 'center', 'italic': True}))

            # Header row
            headers = [
                'Sl No', 'HSN Code', 'Description', 'Type', 'Total Qty',
                'GST%', 'Total Value', 'Taxable', 'CGST', 'SGST'
            ]
            for col, header in enumerate(headers):
                worksheet.write(3, col, header, bold)  # Start at row 4 (index 3)

            # Data rows
            total_qty = total_rate = total_taxable = total_cgst = total_sgst = 0.0
            row = 4
            for sl, line in enumerate(lines, start=1):
                pharmacy = line.pharmacy_id
                worksheet.write(row, 0, sl)
                worksheet.write(row, 1, line.hsn or '')
                worksheet.write(row, 2, line.products_id.display_name or '')
                worksheet.write(row, 3, pharmacy.op_category or '')
                worksheet.write(row, 4, line.qty)
                worksheet.write(row, 5, line.gst)
                worksheet.write_number(row, 6, line.rate or 0.0, money)
                worksheet.write_number(row, 7, line.taxable or 0.0, money)
                worksheet.write_number(row, 8, line.cgst or 0.0, money)
                worksheet.write_number(row, 9, line.sgst or 0.0, money)

                total_qty += line.qty or 0
                total_rate += line.rate or 0.0
                total_taxable += line.taxable or 0.0
                total_cgst += line.cgst or 0.0
                total_sgst += line.sgst or 0.0
                row += 1

            # Totals row (bold + numeric formatting)
            worksheet.write(row, 3, 'Total', bold)  # Total label
            worksheet.write(row, 4, total_qty, bold)  # Total Qty (bold)
            worksheet.write_number(row, 6, total_rate, bold_money)  # Total Value
            worksheet.write_number(row, 7, total_taxable, bold_money)  # Taxable
            worksheet.write_number(row, 8, total_cgst, bold_money)  # CGST
            worksheet.write_number(row, 9, total_sgst, bold_money)  # SGST

            # Close workbook and return response
            workbook.close()
            output.seek(0)

            filename = f"HSN_GST_Report_{from_date}_to_{to_date}.xlsx"
            return request.make_response(
                output.read(),
                headers=[
                    ('Content-Disposition', f'attachment; filename={filename}'),
                    ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                ]
            )


class ExcelDownloadController(http.Controller):
    @http.route('/web/report/excel_download', type='http', auth='user')
    def download_excel_report(self, data=None, **kwargs):
        if not data:
            return request.not_found()

        decoded = base64.b64decode(data)
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', 'attachment; filename=Billing_Report.xlsx'),
        ]
        return request.make_response(decoded, headers)



class DashboardController(http.Controller):
    @http.route('/web/dashboard_expiry', type='json', auth='user')
    def dashboard_expiry(self):
        return request.env['dashboard.model'].sudo().send_expiry_notification()

class IPBillingDischargeReportController(http.Controller):

    @http.route('/homeo_doctor/ip_billing_excel', type='http', auth='user')
    def download_ip_billing_excel(self, from_date, to_date, **kwargs):
        domain = [
            ('bill_date', '>=', from_date),
            ('bill_date', '<=', to_date),
        ]
        discharge_records = request.env['discharge.billing'].sudo().search(domain, order='bill_date asc')

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("IP Billing Report")

        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})

        headers = ['Sl No', 'Date', 'Bill No', 'MRD No', 'Patient', 'Mode of Payment', 'Doctor', 'Total Amount']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)

        grand_total = 0.0
        for i, rec in enumerate(discharge_records, start=1):
            line_total = sum(rec.general_bill_line_ids.mapped('total_amt'))
            grand_total += line_total

            sheet.write(i, 0, i)
            sheet.write(i, 1, rec.bill_date.strftime('%d-%m-%Y') if rec.bill_date else '')
            sheet.write(i, 2, rec.bill_number or '')
            sheet.write(i, 3, rec.mrd_no.reference_no if rec.mrd_no else '')
            sheet.write(i, 4, rec.patient_name or '')
            sheet.write(i, 5, rec.mode_pay or '')
            sheet.write(i, 6, rec.doctor.name if rec.doctor else '')
            sheet.write(i, 7, line_total, money)

        sheet.write(len(discharge_records)+1, 6, "Grand Total", bold)
        sheet.write(len(discharge_records)+1, 7, grand_total, money)

        workbook.close()
        output.seek(0)
        data = output.read()

        filename = f"IP_Billing_{from_date}_to_{to_date}.xlsx"
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}'),
            ]
        )

class VendorBillExcelController(http.Controller):

    @http.route('/vendor/bill/excel', type='http', auth='user')
    def download_vendor_bill_excel(self, from_date=None, to_date=None, mode_pay=None, **kwargs):

        domain = [
            ('move_type', '=', 'in_invoice'),
        ]

        if from_date:
            domain.append(('invoice_date', '>=', from_date))
        if to_date:
            domain.append(('invoice_date', '<=', to_date))
        if mode_pay:
            domain.append(('pay_mode', '=', mode_pay))

        records = request.env['account.move'].sudo().search(domain)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Vendor Bills')

        header_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center'
        })
        cell_format = workbook.add_format({'border': 1})

        headers = [
            'Supplier Name', 'Invoice No', 'Phone', 'Email',
            'GST', 'DL', 'Bill Date', 'PO Number'
        ]

        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        row = 1
        for rec in records:
            sheet.write(row, 0, rec.supplier_name.name if rec.supplier_name else '', cell_format)
            sheet.write(row, 1, rec.supplier_invoice or '', cell_format)
            sheet.write(row, 2, rec.supplier_phone or '', cell_format)
            sheet.write(row, 3, rec.supplier_email or '', cell_format)
            sheet.write(row, 4, rec.supplier_gst or '', cell_format)
            sheet.write(row, 5, rec.supplier_dl or '', cell_format)
            sheet.write(row, 6, rec.supplier_bill_date.strftime('%d-%m-%Y') if rec.supplier_bill_date else '', cell_format)
            sheet.write(row, 7, rec.po_number.name if rec.po_number else '', cell_format)
            row += 1

        workbook.close()
        output.seek(0)

        filename = f"Vendor_Bills_{datetime.today().strftime('%d_%m_%Y')}.xlsx"

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename={filename}')
            ]
        )


class CustomAuthLogin(Home):

    @http.route('/web/login', type='http', auth="public", website=True, sitemap=False)
    def web_login(self, redirect=None, **kw):
        # Check if login form is submitted
        if 'login' in kw and 'password' in kw:
            recaptcha_response = kw.get('g-recaptcha-response')
            if not recaptcha_response:
                return request.render('web.login', {
                    'error': "Captcha is required"
                })

            # Google reCAPTCHA Test Secret Key (always valid in local)
            secret_key = "6LctbcorAAAAAHimNdsO5whRfOxAeOjG30pWk3AM"
            verify_url = "https://www.google.com/recaptcha/api/siteverify"
            payload = {'secret': secret_key, 'response': recaptcha_response}
            r = requests.post(verify_url, data=payload)
            result = r.json()

            if not result.get('success'):
                return request.render('web.login', {
                    'error': "Invalid captcha. Please try again."
                })

        # ✅ If captcha passed → call Odoo's original login
        return super(CustomAuthLogin, self).web_login(redirect=redirect, **kw)


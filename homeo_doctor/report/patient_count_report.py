from odoo import models, fields, api
from collections import defaultdict
from datetime import timedelta
import base64
from io import BytesIO
import xlsxwriter

class DoctorWiseReportWizard(models.TransientModel):
    _name = 'doctor.patient.count'
    _description = 'Doctor Wise Patient Count Report'

    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)

    file_data = fields.Binary('File', readonly=True)
    file_name = fields.Char('Filename')
    def action_print_report(self):
        data = {
            'start_date': self.start_date,
            'end_date': self.end_date,
        }
        return self.env.ref('homeo_doctor.action_doctor_wise_patient_report').report_action(self, data=data)


    def action_print_view_report(self):
        data = {
            'start_date': self.start_date,
            'end_date': self.end_date,
        }
        return self.env.ref('homeo_doctor.action_doctor_wise_patient_report_html').report_action(self, data=data)

    def action_export_excel(self):
        start_date = self.start_date
        end_date = self.end_date

        Appointment = self.env['patient.appointment']
        Registration = self.env['patient.reg']

        # Collect data
        appointments = Appointment.search([
            ('appointment_date', '>=', start_date),
            ('appointment_date', '<=', end_date),
            ('status', '!=', 'cancelled')
        ])
        registrations = Registration.search([
            ('time', '>=', start_date),
            ('time', '<=', end_date),
            ('status', '!=', 'cancelled')
        ])

        # Prepare date range
        all_dates = []
        current = fields.Date.from_string(str(start_date))
        end = fields.Date.from_string(str(end_date))
        while current <= end:
            all_dates.append(current)
            current += timedelta(days=1)

        # Combine counts (basic total per day)
        data_map = defaultdict(lambda: defaultdict(int))
        with_fee_map = defaultdict(int)
        without_fee_map = defaultdict(int)

        # From Appointments
        for app in appointments:
            doctor = app.doctor_ids.name if app.doctor_ids else 'Unknown'
            date = fields.Date.from_string(str(app.appointment_date))
            data_map[doctor][date] += 1

            if getattr(app, 'consultation_fee', 0):
                with_fee_map[doctor] += 1
            else:
                without_fee_map[doctor] += 1

        # From Registrations
        for reg in registrations:
            doctor = reg.doc_name.name if hasattr(reg, 'doc_name') and reg.doc_name else 'Unknown'
            date = fields.Date.from_string(str(reg.time))
            data_map[doctor][date] += 1

            if getattr(reg, 'consultation_fee', 0):
                with_fee_map[doctor] += 1
            else:
                without_fee_map[doctor] += 1

        # Create Excel workbook
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Doctor Wise Count')

        # Formats
        bold = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        normal = workbook.add_format({'align': 'center', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})

        # Title
        sheet.merge_range(0, 0, 0, len(all_dates) + 3, 'Doctor Wise Patient Count Report', title_format)
        sheet.write(1, 0, f"From: {start_date}  To: {end_date}")

        # Headers
        sheet.write(3, 0, 'Doctor Name', bold)
        col = 1
        for d in all_dates:
            sheet.write(3, col, d.strftime('%d-%b'), bold)
            col += 1
        sheet.write(3, col, 'Total', bold)
        sheet.write(3, col + 1, 'With Fee', bold)
        sheet.write(3, col + 2, 'Without Fee', bold)

        # Data rows
        row = 4
        for doctor, date_counts in sorted(data_map.items()):
            sheet.write(row, 0, doctor, bold)
            total = 0
            for idx, d in enumerate(all_dates):
                count = date_counts.get(d, 0)
                sheet.write(row, idx + 1, count, normal)
                total += count

            with_fee = with_fee_map.get(doctor, 0)
            without_fee = without_fee_map.get(doctor, 0)

            sheet.write(row, len(all_dates) + 1, total, bold)
            sheet.write(row, len(all_dates) + 2, with_fee, normal)
            sheet.write(row, len(all_dates) + 3, without_fee, normal)
            row += 1

        # Total row
        sheet.write(row, 0, 'Grand Total', bold)
        for i, d in enumerate(all_dates):
            col_total = sum(data_map[doc][d] for doc in data_map)
            sheet.write(row, i + 1, col_total, bold)

        grand_total = sum(sum(v.values()) for v in data_map.values())
        total_with_fee = sum(with_fee_map.values())
        total_without_fee = sum(without_fee_map.values())

        sheet.write(row, len(all_dates) + 1, grand_total, bold)
        sheet.write(row, len(all_dates) + 2, total_with_fee, bold)
        sheet.write(row, len(all_dates) + 3, total_without_fee, bold)

        # Adjust column widths
        sheet.set_column(0, 0, 25)
        sheet.set_column(1, len(all_dates) + 3, 12)

        workbook.close()
        output.seek(0)

        # Save file to binary field
        self.file_data = base64.b64encode(output.read())
        filename = f"Doctor_Wise_Patient_Count_{start_date}_to_{end_date}.xlsx"
        self.file_name = filename

        return {
            'type': 'ir.actions.act_url',
            'url': f"/web/content/?model=doctor.patient.count&id={self.id}&field=file_data&filename={filename}&download=true",
            'target': 'new',
        }


class DoctorWisePatientReport(models.AbstractModel):
    _name = 'report.homeo_doctor.report_doctor_wise_patient_count'
    _description = 'Doctor Wise Patient Count with Consultation Fee Details'

    @api.model
    def _get_report_values(self, docids, data=None):
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        Appointment = self.env['patient.appointment']
        Registration = self.env['patient.reg']

        # 1️⃣ Collect Appointment Data
        appointments = Appointment.search([
            ('appointment_date', '>=', start_date),
            ('appointment_date', '<=', end_date),
            ('status', '!=', 'cancelled')
        ])

        # 2️⃣ Collect Registration Data
        registrations = Registration.search([
            ('time', '>=', start_date),
            ('time', '<=', end_date),
            ('status', '!=', 'cancelled')
        ])

        # 3️⃣ Prepare Date Range
        all_dates = []
        current = fields.Date.from_string(start_date)
        end = fields.Date.from_string(end_date)
        while current <= end:
            all_dates.append(current)
            current += timedelta(days=1)

        # 4️⃣ Data Structure:
        # data_map[doctor][date] = {'with_fee': X, 'without_fee': Y}
        data_map = defaultdict(lambda: defaultdict(lambda: {'with_fee': 0, 'without_fee': 0}))

        # From Appointments
        for app in appointments:
            doctor = app.doctor_ids.name if app.doctor_ids else 'Unknown'
            date = fields.Date.from_string(str(app.appointment_date))
            fee = getattr(app, 'consultation_fee', 0.0)

            if fee and fee > 0:
                data_map[doctor][date]['with_fee'] += 1
            else:
                data_map[doctor][date]['without_fee'] += 1

        # From Registrations
        for reg in registrations:
            doctor = reg.doc_name.name if hasattr(reg, 'doc_name') and reg.doc_name else 'Unknown'
            date = fields.Date.from_string(str(reg.time))
            fee = getattr(reg, 'consultation_fee', 0.0)

            if fee and fee > 0:
                data_map[doctor][date]['with_fee'] += 1
            else:
                data_map[doctor][date]['without_fee'] += 1

        # 5️⃣ Build Doctor Rows
        rows = []
        for doctor, date_counts in sorted(data_map.items()):
            with_fee_counts = [date_counts[d]['with_fee'] for d in all_dates]
            without_fee_counts = [date_counts[d]['without_fee'] for d in all_dates]

            total_with_fee = sum(with_fee_counts)
            total_without_fee = sum(without_fee_counts)

            rows.append({
                'doctor': doctor,
                'with_fee_counts': with_fee_counts,
                'without_fee_counts': without_fee_counts,
                'total_with_fee': total_with_fee,
                'total_without_fee': total_without_fee,
            })

        # 6️⃣ Daily Totals
        total_with_fee_counts = [sum(data_map[doc][d]['with_fee'] for doc in data_map) for d in all_dates]
        total_without_fee_counts = [sum(data_map[doc][d]['without_fee'] for doc in data_map) for d in all_dates]
        grand_total_with_fee = sum(total_with_fee_counts)
        grand_total_without_fee = sum(total_without_fee_counts)

        # 7️⃣ Return Report Data
        return {
            'doc_ids': docids,
            'doc_model': 'patient.appointment',
            'data': data,
            'docs': rows,
            'all_dates': all_dates,
            'start_date': start_date,
            'end_date': end_date,
            'total_with_fee_counts': total_with_fee_counts,
            'total_without_fee_counts': total_without_fee_counts,
            'grand_total_with_fee': grand_total_with_fee,
            'grand_total_without_fee': grand_total_without_fee,
        }

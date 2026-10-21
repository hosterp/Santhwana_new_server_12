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

    def _date_range(self, start_date, end_date):
        all_dates = []
        current = fields.Date.from_string(str(start_date))
        end = fields.Date.from_string(str(end_date))
        while current <= end:
            all_dates.append(current)
            current += timedelta(days=1)
        return all_dates

    def _sql_patient_count_rows(self, start_date, end_date):
        """Aggregate doctor/day with-fee counts in SQL (same rules as before).

        Appointments: first linked doctor (lowest id); with fee = fee_applied
        (stored flag set with consultation_fee compute — avoids recompute).
        Registrations: doc_name; with fee = stored consultation_fee > 0.
        Cancelled excluded. No workflow/data changes.
        """
        self.env.cr.execute("""
            WITH appt AS (
                SELECT DISTINCT ON (pa.id)
                       COALESCE(dp.name, 'Unknown') AS doctor,
                       pa.appointment_date AS dt,
                       CASE WHEN pa.fee_applied IS TRUE THEN 1 ELSE 0 END AS with_fee,
                       CASE WHEN pa.fee_applied IS TRUE THEN 0 ELSE 1 END AS without_fee
                  FROM patient_appointment pa
             LEFT JOIN doctor_profile_patient_appointment_rel rel
                    ON rel.patient_appointment_id = pa.id
             LEFT JOIN doctor_profile dp ON dp.id = rel.doctor_profile_id
                 WHERE pa.appointment_date >= %s
                   AND pa.appointment_date <= %s
                   AND COALESCE(pa.status, '') <> 'cancelled'
              ORDER BY pa.id, rel.doctor_profile_id ASC NULLS LAST
            ),
            reg AS (
                SELECT COALESCE(dp.name, 'Unknown') AS doctor,
                       pr.time AS dt,
                       CASE WHEN COALESCE(pr.consultation_fee, 0) > 0 THEN 1 ELSE 0 END AS with_fee,
                       CASE WHEN COALESCE(pr.consultation_fee, 0) > 0 THEN 0 ELSE 1 END AS without_fee
                  FROM patient_reg pr
             LEFT JOIN doctor_profile dp ON dp.id = pr.doc_name
                 WHERE pr.time >= %s
                   AND pr.time <= %s
                   AND COALESCE(pr.status, '') <> 'cancelled'
            ),
            all_rows AS (
                SELECT * FROM appt
                UNION ALL
                SELECT * FROM reg
            )
            SELECT doctor, dt,
                   SUM(with_fee)::integer AS with_fee,
                   SUM(without_fee)::integer AS without_fee
              FROM all_rows
             GROUP BY doctor, dt
             ORDER BY doctor, dt
        """, (start_date, end_date, start_date, end_date))
        return self.env.cr.fetchall()

    def _build_data_map(self, start_date, end_date):
        """data_map[doctor][date] = {'with_fee': X, 'without_fee': Y}"""
        data_map = defaultdict(lambda: defaultdict(lambda: {'with_fee': 0, 'without_fee': 0}))
        for doctor, dt, with_fee, without_fee in self._sql_patient_count_rows(start_date, end_date):
            if hasattr(dt, 'date'):
                dt = dt.date()
            data_map[doctor or 'Unknown'][dt]['with_fee'] += with_fee or 0
            data_map[doctor or 'Unknown'][dt]['without_fee'] += without_fee or 0
        return data_map

    def action_export_excel(self):
        start_date = self.start_date
        end_date = self.end_date
        all_dates = self._date_range(start_date, end_date)
        data_map = self._build_data_map(start_date, end_date)

        # Excel layout: daily total count; separate with/without fee column totals
        day_map = defaultdict(lambda: defaultdict(int))
        with_fee_map = defaultdict(int)
        without_fee_map = defaultdict(int)
        for doctor, date_counts in data_map.items():
            for d, fees in date_counts.items():
                day_map[doctor][d] = fees['with_fee'] + fees['without_fee']
                with_fee_map[doctor] += fees['with_fee']
                without_fee_map[doctor] += fees['without_fee']

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Doctor Wise Count')

        bold = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        normal = workbook.add_format({'align': 'center', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})

        sheet.merge_range(0, 0, 0, len(all_dates) + 3, 'Doctor Wise Patient Count Report', title_format)
        sheet.write(1, 0, f"From: {start_date}  To: {end_date}")

        sheet.write(3, 0, 'Doctor Name', bold)
        col = 1
        for d in all_dates:
            sheet.write(3, col, d.strftime('%d-%b'), bold)
            col += 1
        sheet.write(3, col, 'Total', bold)
        sheet.write(3, col + 1, 'With Fee', bold)
        sheet.write(3, col + 2, 'Without Fee', bold)

        row = 4
        for doctor, date_counts in sorted(day_map.items()):
            sheet.write(row, 0, doctor, bold)
            total = 0
            for idx, d in enumerate(all_dates):
                count = date_counts.get(d, 0)
                sheet.write(row, idx + 1, count, normal)
                total += count

            sheet.write(row, len(all_dates) + 1, total, bold)
            sheet.write(row, len(all_dates) + 2, with_fee_map.get(doctor, 0), normal)
            sheet.write(row, len(all_dates) + 3, without_fee_map.get(doctor, 0), normal)
            row += 1

        sheet.write(row, 0, 'Grand Total', bold)
        for i, d in enumerate(all_dates):
            col_total = sum(day_map[doc][d] for doc in day_map)
            sheet.write(row, i + 1, col_total, bold)

        grand_total = sum(sum(v.values()) for v in day_map.values())
        sheet.write(row, len(all_dates) + 1, grand_total, bold)
        sheet.write(row, len(all_dates) + 2, sum(with_fee_map.values()), bold)
        sheet.write(row, len(all_dates) + 3, sum(without_fee_map.values()), bold)

        sheet.set_column(0, 0, 25)
        sheet.set_column(1, len(all_dates) + 3, 12)

        workbook.close()
        output.seek(0)

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

        wizard = self.env['doctor.patient.count']
        all_dates = wizard._date_range(start_date, end_date)
        data_map = wizard._build_data_map(start_date, end_date)

        rows = []
        for doctor, date_counts in sorted(data_map.items()):
            with_fee_counts = [date_counts[d]['with_fee'] for d in all_dates]
            without_fee_counts = [date_counts[d]['without_fee'] for d in all_dates]
            rows.append({
                'doctor': doctor,
                'with_fee_counts': with_fee_counts,
                'without_fee_counts': without_fee_counts,
                'total_with_fee': sum(with_fee_counts),
                'total_without_fee': sum(without_fee_counts),
            })

        total_with_fee_counts = [sum(data_map[doc][d]['with_fee'] for doc in data_map) for d in all_dates]
        total_without_fee_counts = [sum(data_map[doc][d]['without_fee'] for doc in data_map) for d in all_dates]

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
            'grand_total_with_fee': sum(total_with_fee_counts),
            'grand_total_without_fee': sum(total_without_fee_counts),
        }

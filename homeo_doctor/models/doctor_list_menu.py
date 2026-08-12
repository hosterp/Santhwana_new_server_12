import io
import base64
import xlsxwriter
from odoo import models, fields, api


class DoctorWiseCollectionCustomWizard(models.TransientModel):
    _name = 'doctor.wise.collection.list'
    _description = 'Doctor Wise Collection Custom Report'

    date_from = fields.Date(string="From Date", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)
    doctor_id = fields.Many2one('doctor.profile', string="Doctor", domain=[('list_one', '=', True)])
    # doctor_id = fields.Many2one('doctor.profile', string="Doctor", domain=[('name', 'in', [
    #     'DR M SUDHAKAR',
    #     'DR C JOHN PANICKER',
    #     'DR M SALIM',
    #     'DR ANWAR RASHEED',
    #     'DR BIJI VARGHESE',
    #     'DR K KAVITHA',
    #     'DR V G ABRAHAM',
    #     'DR ABRAHAM VARGHESE',
    #     'DR RAMEEZ NAJEEB',
    #     'DR JOE JACOB',
    # ])])
    line_ids = fields.One2many(
        'doctor.wise.collection.lines',
        'wizard_id',
        string="Collection Lines"
    )

    def action_view_report(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.unlink()

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

        if self.doctor_id:
            domain_reg.append(('doc_name', '=', self.doctor_id.id))
            domain_app.append(('doctor_ids', 'in', [self.doctor_id.id]))

        patients_reg = self.env['patient.reg'].search(domain_reg)
        patients_app = self.env['patient.appointment'].search(domain_app)

        new_lines_vals = []
        zero_out = bool(self.doctor_id)

        # Create lines from registrations
        for rec in patients_reg:
            payment_mode = rec.register_mode_payment or 'cash'
            amount = float(rec.register_total_amount or 0.0)

            cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
            credit_amount = amount if payment_mode == 'credit' else 0.0

            if zero_out:
                cash_amount = 0.0
                credit_amount = 0.0
                amount = 0.0

            reg_doctor_id = rec.doc_name.id if rec.doc_name else False
            patient_name = rec.patient_id  # patient_id is a Char field in patient.reg

            new_lines_vals.append({
                'wizard_id': self.id,
                'reference_no': rec.reference_no or '',
                'date': rec.time,
                'patient_name': patient_name,
                'doctor_id': reg_doctor_id,
                'payment_mode': payment_mode,
                'registration_fee1': rec.registration_fee.fee if rec.registration_fee else 0,
                'consultation_fee': float(rec.consultation_fee or 0.0),
                'bill_number': rec.bill_number or '',
                'cash_amount': cash_amount,
                'credit_amount': credit_amount,
                'total_amount': amount,
            })

        # Create lines from appointments
        for rec in patients_app:
            for doc in rec.doctor_ids:
                payment_mode = rec.register_mode_payment or 'cash'
                amount = float(rec.register_total_amount or 0.0)

                cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
                credit_amount = amount if payment_mode == 'credit' else 0.0

                if zero_out:
                    cash_amount = 0.0
                    credit_amount = 0.0
                    amount = 0.0

                patient_name = rec.patient_id.patient_id if rec.patient_id else False

                new_lines_vals.append({
                    'wizard_id': self.id,
                    'reference_no': rec.patient_id.reference_no if rec.patient_id else '',
                    'date': rec.appointment_date,
                    'patient_name': patient_name,
                    'doctor_id': doc.id,
                    'payment_mode': payment_mode,
                    'registration_fee1': rec.registration_fee or 0,
                    'consultation_fee': float(rec.consultation_fee or 0.0),
                    'bill_number': rec.payment_receipt_number or '',
                    'cash_amount': cash_amount,
                    'credit_amount': credit_amount,
                    'total_amount': amount,
                })

        if new_lines_vals:
            self.env['doctor.wise.collection.lines'].create(new_lines_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'doctor.wise.collection.list',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'group_by': 'doctor_id'},
        }


    def action_print_excel(self):
        """Optimized SQL approach to avoid ORM overhead for large datasets."""
        self.ensure_one()
        
        date_from = self.date_from
        date_to = self.date_to
        doctor_id = self.doctor_id.id if self.doctor_id else None

        cr = self.env.cr

        # 1. Gather counts/totals from patient_reg (Registrations)
        reg_sql = """
            SELECT 
                dp.id AS doc_id,
                dp.name AS doc_name,
                dp.consultation_fee_doctor AS doc_fee,
                COUNT(*) FILTER (WHERE pr.consultation_fee > 0) AS with_fee,
                COUNT(*) FILTER (WHERE pr.consultation_fee <= 0 OR pr.consultation_fee IS NULL) AS without_fee,
                COALESCE(SUM(pr.consultation_fee), 0) AS total_fee
            FROM patient_reg pr
            JOIN doctor_profile dp ON dp.id = pr.doc_name
            WHERE pr.time >= %s AND pr.time <= %s
              AND pr.status != 'cancelled'
              {doc_filter}
            GROUP BY dp.id, dp.name, dp.consultation_fee_doctor
        """.format(
            doc_filter="AND dp.id = %s" if doctor_id else "AND dp.list_one = TRUE"
        )
        
        params = [date_from, date_to]
        if doctor_id:
            params.append(doctor_id)
            
        cr.execute(reg_sql, params)
        reg_results = cr.dictfetchall()

        m2m_field = self.env['patient.appointment']._fields['doctor_ids']
        rel_table = m2m_field.relation
        col1 = m2m_field.column1
        col2 = m2m_field.column2

        # 2. Gather counts/totals from patient_appointment (Appointments)
        # We join with patient_reg (pr) to get vssc_boolean, as consultation_fee is not stored on pa.
        app_sql = """
            SELECT 
                dp.id AS doc_id,
                dp.name AS doc_name,
                dp.consultation_fee_doctor AS doc_fee,
                COUNT(*) FILTER (WHERE pa.fee_applied = TRUE) AS with_fee,
                COUNT(*) FILTER (WHERE pa.fee_applied = FALSE OR pa.fee_applied IS NULL) AS without_fee,
                COALESCE(SUM(
                    CASE 
                        WHEN pa.fee_applied = TRUE THEN 
                            CASE WHEN pr.vssc_boolean = TRUE THEN 400 ELSE dp.consultation_fee_doctor END
                        ELSE 0 
                    END
                ), 0) AS total_fee
            FROM patient_appointment pa
            JOIN patient_reg pr ON pr.id = pa.patient_id
            JOIN {rel} rel ON rel.{c1} = pa.id
            JOIN doctor_profile dp ON dp.id = rel.{c2}
            WHERE pa.appointment_date >= %s AND pa.appointment_date <= %s
              AND pa.status NOT IN ('unpaid', 'cancelled')
              {doc_filter}
            GROUP BY dp.id, dp.name, dp.consultation_fee_doctor
        """.format(
            rel=rel_table,
            c1=col1,
            c2=col2,
            doc_filter="AND dp.id = %s" if doctor_id else "AND dp.list_one = TRUE"
        )
        
        params_app = [date_from, date_to]
        if doctor_id:
            params_app.append(doctor_id)
            
        cr.execute(app_sql, params_app)
        app_results = cr.dictfetchall()

        # 3. Merge results
        final_data = {}
        for r in reg_results:
            did = r['doc_id']
            if did not in final_data:
                final_data[did] = {'name': r['doc_name'], 'fee': r['doc_fee'], 'with': 0, 'without': 0, 'total': 0.0}
            final_data[did]['with'] += r['with_fee']
            final_data[did]['without'] += r['without_fee']
            final_data[did]['total'] += float(r['total_fee'])

        for r in app_results:
            did = r['doc_id']
            if did not in final_data:
                final_data[did] = {'name': r['doc_name'], 'fee': r['doc_fee'], 'with': 0, 'without': 0, 'total': 0.0}
            final_data[did]['with'] += r['with_fee']
            final_data[did]['without'] += r['without_fee']
            final_data[did]['total'] += float(r['total_fee'])

        # 4. Generate Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Consultation Summary")
        
        # Styles
        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'align': 'center', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        bold_center = workbook.add_format({'bold': True, 'align': 'center'})
        grand_total_format = workbook.add_format({'bold': True, 'border': 1})
        grand_num_format = workbook.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00'})

        sheet.merge_range('A1:F1', 'SANTHWANA HOSPITAL', title_format)
        sheet.merge_range('A2:F2', 'N.C.C Road, Ambalamukku, Trivandrum-695005', bold_center)
        sheet.merge_range('A3:F3', 'Phone: 0471-2432121, 4223131', bold_center)
        sheet.merge_range('A4:F4', 'OP CONSULTATION REPORT', title_format)

        df_str = date_from.strftime('%d/%m/%Y') if date_from else ''
        dt_str = date_to.strftime('%d/%m/%Y') if date_to else ''
        sheet.merge_range('A5:F5', f"From: {df_str}    To: {dt_str}", bold_center)

        headers = ['Sl No', 'Doctor Name', 'Consultation Fee', 'Patient Count with Fee', 'Patient Count without Fee', 'Total Amount']
        sheet.write_row(7, 0, headers, header_format)

        row = 8
        sl = 1
        grand_with = grand_without = 0
        grand_total = 0.0
        
        # Sort doctors by name
        sorted_docs = sorted(final_data.values(), key=lambda x: x['name'] or '')
        
        for data in sorted_docs:
            sheet.write(row, 0, sl, cell_format)
            sheet.write(row, 1, data['name'] or 'No Doctor', cell_format)
            sheet.write(row, 2, data['fee'] or 0, num_format)
            sheet.write(row, 3, data['with'], cell_format)
            sheet.write(row, 4, data['without'], cell_format)
            sheet.write(row, 5, data['total'], num_format)
            
            grand_with += data['with']
            grand_without += data['without']
            grand_total += data['total']
            row += 1
            sl += 1

        # Grand Total
        sheet.write(row, 1, 'Grand Total', grand_total_format)
        sheet.merge_range(row, 2, row, 2, '', cell_format) # empty for fee col
        sheet.write(row, 3, grand_with, grand_total_format)
        sheet.write(row, 4, grand_without, grand_total_format)
        sheet.write(row, 5, grand_total, grand_num_format)

        sheet.set_column('A:A', 8)
        sheet.set_column('B:B', 35)
        sheet.set_column('C:F', 20)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Doctor_Consultation_Report.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }
class DoctorWiseCollectionLine(models.TransientModel):
    _name = 'doctor.wise.collection.lines'
    _description = 'Doctor Wise Collection Line'
    _order = 'date asc'

    wizard_id = fields.Many2one(
        'doctor.wise.collection.list',
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
    list_one=fields.Boolean()
    registration_fee1 = fields.Integer(string='Rev-Registration fee', ondelete='set null')
    consultation_fee = fields.Integer(string='Consultation Fee', ondelete='set null')
    bill_number = fields.Char(string="Bill Number", ondelete='set null')
    date = fields.Date(string='Date')


class PatientRegistrationFee(models.Model):
    _inherit = 'patient.registration.fee'

    def unlink(self):
        """Clear child references safely before deleting parent."""
        DoctorLine = self.env['doctor.wise.collection.lines']
        for rec in self:
            lines = DoctorLine.search([('registration_fee', '=', rec.id)])
            if lines:
                lines.write({'registration_fee': False})
                # 🧩 Force database flush before deleting parent
                self.env.cr.flush()
        return super(PatientRegistrationFee, self).unlink()


# import io
# import base64
# import xlsxwriter
# from odoo import models, fields, api
#
#
# class DoctorWiseCollectionCustomWizard(models.TransientModel):
#     _name = 'doctor.wise.collection.list'
#     _description = 'Doctor Wise Collection Custom Report'
#
#     date_from = fields.Date(string="From Date", required=True, default=fields.Date.context_today)
#     date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)
#     doctor_id = fields.Many2one('doctor.profile', string="Doctor", domain=[('list_one', '=', True)])
#     line_ids = fields.One2many(
#         'doctor.wise.collection.lines',
#         'wizard_id',
#         string="Collection Lines"
#     )
#
#     def _get_patient_name(self, rec):
#         """Safely extract patient name whether patient_id is Many2one or Char."""
#         pid = getattr(rec, 'patient_id', False)
#         if not pid:
#             return ''
#         if isinstance(pid, str):
#             return pid
#         return getattr(pid, 'name', '') or getattr(pid, 'patient_id', '') or ''
#
#     def action_view_report(self):
#         self.ensure_one()
#
#         if self.line_ids:
#             self.line_ids.unlink()
#
#         domain_reg = [
#             ('time', '>=', self.date_from),
#             ('time', '<=', self.date_to),
#             ('status', '!=', 'cancelled'),
#         ]
#         domain_app = [
#             ('appointment_date', '>=', self.date_from),
#             ('appointment_date', '<=', self.date_to),
#             ('status', 'not in', ['unpaid', 'cancelled']),
#         ]
#
#         if self.doctor_id:
#             domain_reg.append(('doc_name', '=', self.doctor_id.id))
#             domain_app.append(('doctor_ids', 'in', [self.doctor_id.id]))
#
#         patients_reg = self.env['patient.reg'].search(domain_reg).with_context(prefetch_fields=True)
#         patients_app = self.env['patient.appointment'].search(domain_app).with_context(prefetch_fields=True)
#
#         vals_list = []
#         zero_amounts = bool(self.doctor_id)
#
#         for rec in patients_reg:
#             payment_mode = rec.register_mode_payment or 'cash'
#             amount = float(rec.register_total_amount or 0.0)
#
#             if zero_amounts:
#                 cash_amount = credit_amount = amount = 0.0
#             else:
#                 cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
#                 credit_amount = amount if payment_mode == 'credit' else 0.0
#
#             reg_doctor_id = rec.doc_name.id if rec.doc_name and hasattr(rec.doc_name, 'id') else False
#
#             vals_list.append({
#                 'wizard_id': self.id,
#                 'reference_no': rec.reference_no or '',
#                 'date': rec.time,
#                 'patient_name': self._get_patient_name(rec),
#                 'doctor_id': reg_doctor_id,
#                 'payment_mode': payment_mode,
#                 'registration_fee1': rec.registration_fee.fee if rec.registration_fee else 0,
#                 'consultation_fee': float(rec.consultation_fee or 0.0),
#                 'bill_number': rec.bill_number or '',
#                 'cash_amount': cash_amount,
#                 'credit_amount': credit_amount,
#                 'total_amount': amount,
#             })
#
#         for rec in patients_app:
#             for doc in rec.doctor_ids:
#                 payment_mode = rec.register_mode_payment or 'cash'
#                 amount = float(rec.register_total_amount or 0.0)
#
#                 if zero_amounts:
#                     cash_amount = credit_amount = amount = 0.0
#                 else:
#                     cash_amount = amount if payment_mode in ['cash', 'card', 'upi', 'cheque'] else 0.0
#                     credit_amount = amount if payment_mode == 'credit' else 0.0
#
#                 vals_list.append({
#                     'wizard_id': self.id,
#                     'reference_no': (
#                         rec.patient_id.reference_no
#                         if rec.patient_id and hasattr(rec.patient_id, 'reference_no')
#                         else ''
#                     ),
#                     'date': rec.appointment_date,
#                     'patient_name': self._get_patient_name(rec),
#                     'doctor_id': doc.id,
#                     'payment_mode': payment_mode,
#                     'registration_fee1': rec.registration_fee or 0,
#                     'consultation_fee': float(rec.consultation_fee or 0.0),
#                     'bill_number': rec.payment_receipt_number or '',
#                     'cash_amount': cash_amount,
#                     'credit_amount': credit_amount,
#                     'total_amount': amount,
#                 })
#
#         if vals_list:
#             self.env['doctor.wise.collection.lines'].create(vals_list)
#
#         return {
#             'type': 'ir.actions.act_window',
#             'res_model': 'doctor.wise.collection.list',
#             'view_mode': 'form',
#             'res_id': self.id,
#             'target': 'new',
#             'context': {'group_by': 'doctor_id'},
#         }
#
#     def action_print_excel(self):
#         """Raw SQL - single aggregated query, no ORM overhead."""
#
#         date_from = self.date_from
#         date_to = self.date_to
#         doctor_id = self.doctor_id.id if self.doctor_id else None
#
#         cr = self.env.cr
#
#         # --- Registrations aggregated query ---
#         reg_sql = """
#             SELECT
#                 dp.id        AS doc_id,
#                 dp.name      AS doc_name,
#                 COUNT(*) FILTER (WHERE pr.consultation_fee > 0)                               AS with_fee,
#                 COUNT(*) FILTER (WHERE pr.consultation_fee <= 0 OR pr.consultation_fee IS NULL) AS without_fee,
#                 COALESCE(SUM(pr.consultation_fee), 0)                                          AS total_fee
#             FROM patient_reg pr
#             JOIN doctor_profile dp ON dp.id = pr.doc_name
#             WHERE pr.time   >= %(date_from)s
#               AND pr.time   <= %(date_to)s
#               AND pr.status != 'cancelled'
#               {doc_filter}
#             GROUP BY dp.id, dp.name
#         """.format(
#             doc_filter="AND pr.doc_name = %(doctor_id)s" if doctor_id else "AND dp.list_one = TRUE"
#         )
#
#         cr.execute(reg_sql, {'date_from': date_from, 'date_to': date_to, 'doctor_id': doctor_id})
#         reg_rows = cr.fetchall()
#
#         # --- Appointments aggregated query ---
#         app_sql = """
#             SELECT
#                 dp.id        AS doc_id,
#                 dp.name      AS doc_name,
#                 COUNT(*) FILTER (WHERE pa.consultation_fee > 0)                          AS with_fee,
#                 COUNT(*) FILTER (WHERE pa.consultation_fee <= 0 OR pa.consultation_fee IS NULL) AS without_fee,
#                 COALESCE(SUM(pa.consultation_fee), 0)                                    AS total_fee
#             FROM patient_appointment pa
#             JOIN doctor_profile dp ON dp.id = pa.doctor_id
#             WHERE pa.appointment_date >= %(date_from)s
#               AND pa.appointment_date <= %(date_to)s
#               AND pa.status != 'cancelled'
#               {doc_filter}
#             GROUP BY dp.id, dp.name
#         """.format(
#             doc_filter="AND pa.doctor_id = %(doctor_id)s" if doctor_id else "AND dp.list_two = TRUE"
#         )
#
#         cr.execute(app_sql, {'date_from': date_from, 'date_to': date_to, 'doctor_id': doctor_id})
#         app_rows = cr.fetchall()
#
#         # --- Merge reg + app results by doctor ---
#         results = {}
#
#         for doc_id, doc_name, with_fee, without_fee, total_fee in reg_rows:
#             results[doc_id] = {
#                 'name': doc_name or '',
#                 'with': with_fee,
#                 'without': without_fee,
#                 'total': float(total_fee),
#             }
#
#         for doc_id, doc_name, with_fee, without_fee, total_fee in app_rows:
#             if doc_id in results:
#                 results[doc_id]['with'] += with_fee
#                 results[doc_id]['without'] += without_fee
#                 results[doc_id]['total'] += float(total_fee)
#             else:
#                 results[doc_id] = {
#                     'name': doc_name or '',
#                     'with': with_fee,
#                     'without': without_fee,
#                     'total': float(total_fee),
#                 }
#
#         # --- Excel Generation ---
#         output = io.BytesIO()
#         workbook = xlsxwriter.Workbook(output, {'in_memory': True})
#         sheet = workbook.add_worksheet("Consultation Summary")
#
#         title_fmt   = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
#         header_fmt  = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'align': 'center', 'border': 1})
#         cell_fmt    = workbook.add_format({'border': 1})
#         num_fmt     = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
#         center_fmt  = workbook.add_format({'bold': True, 'align': 'center'})
#         grand_fmt   = workbook.add_format({'bold': True, 'border': 1})
#         grand_num   = workbook.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00'})
#
#         sheet.merge_range('A1:E1', 'SANTHWANA HOSPITAL', title_fmt)
#         sheet.merge_range('A2:E2', 'N.C.C Road, Ambalamukku, Trivandrum-695005', center_fmt)
#         sheet.merge_range('A3:E3', 'Phone: 0471-2432121, 4223131', center_fmt)
#         sheet.merge_range('A4:E4', 'OP CONSULTATION REPORT', title_fmt)
#
#         date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
#         date_to_str   = self.date_to.strftime('%d/%m/%Y')   if self.date_to   else ''
#         sheet.merge_range('A5:E5', f"From: {date_from_str}    To: {date_to_str}", center_fmt)
#
#         headers = [
#             'Sl No',
#             'Doctor Name',
#             'Patient Count with Consultation Fee',
#             'Patient Count without Consultation Fee',
#             'Total',
#         ]
#         sheet.write_row(7, 0, headers, header_fmt)
#
#         row = 8
#         sl = 1
#         grand_with = grand_without = 0
#         grand_total = 0.0
#
#         for res in sorted(results.values(), key=lambda x: x['name']):
#             sheet.write(row, 0, sl,             cell_fmt)
#             sheet.write(row, 1, res['name'],    cell_fmt)
#             sheet.write(row, 2, res['with'],    cell_fmt)
#             sheet.write(row, 3, res['without'], cell_fmt)
#             sheet.write(row, 4, res['total'],   num_fmt)
#
#             grand_with    += res['with']
#             grand_without += res['without']
#             grand_total   += res['total']
#             row += 1
#             sl  += 1
#
#         # Grand Total row
#         sheet.write(row, 0, '',            grand_fmt)
#         sheet.write(row, 1, 'Grand Total', grand_fmt)
#         sheet.write(row, 2, grand_with,    grand_fmt)
#         sheet.write(row, 3, grand_without, grand_fmt)
#         sheet.write(row, 4, grand_total,   grand_num)
#
#         sheet.set_column('A:A', 8)
#         sheet.set_column('B:B', 30)
#         sheet.set_column('C:D', 35)
#         sheet.set_column('E:E', 18)
#
#         workbook.close()
#         output.seek(0)
#
#         attachment = self.env['ir.attachment'].create({
#             'name': 'Doctor_Consultation_Report.xlsx',
#             'type': 'binary',
#             'datas': base64.b64encode(output.read()),
#             'store_fname': 'Doctor_Consultation_Report.xlsx',
#             'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
#         })
#
#         return {
#             'type': 'ir.actions.act_url',
#             'url': '/web/content/%s?download=true' % attachment.id,
#             'target': 'new',
#         }
#
#
# class DoctorWiseCollectionLine(models.TransientModel):
#     _name = 'doctor.wise.collection.lines'
#     _description = 'Doctor Wise Collection Line'
#     _order = 'date asc'
#
#     wizard_id = fields.Many2one(
#         'doctor.wise.collection.list',
#         string="Wizard",
#         ondelete="cascade"
#     )
#     reference_no = fields.Char(string="UHID")
#     patient_name = fields.Char(string="Patient")
#     doctor_id = fields.Many2one('doctor.profile', string="Doctor", ondelete='set null')
#     payment_mode = fields.Selection(
#         [('cash', 'Cash'),
#          ('card', 'Card'),
#          ('cheque', 'Cheque'),
#          ('credit', 'Credit'),
#          ('upi', 'Mobile Pay')],
#         string="Payment Mode"
#     )
#     amount = fields.Float(string="Amount")
#     cash_amount = fields.Float('Cash Amount')
#     credit_amount = fields.Float('Credit Amount')
#     total_amount = fields.Float('Total Amount')
#     registration_fee = fields.Many2one(
#         'patient.registration.fee',
#         string="Registration Fee",
#         ondelete='set null',
#     )
#     list_one = fields.Boolean()
#     registration_fee1 = fields.Integer(string='Rev-Registration fee')
#     consultation_fee = fields.Integer(string='Consultation Fee')
#     bill_number = fields.Char(string="Bill Number")
#     date = fields.Date(string='Date')
#
#
# class PatientRegistrationFee(models.Model):
#     _inherit = 'patient.registration.fee'
#
#     def unlink(self):
#         DoctorLine = self.env['doctor.wise.collection.lines']
#         for rec in self:
#             lines = DoctorLine.search([('registration_fee', '=', rec.id)])
#             if lines:
#                 lines.write({'registration_fee': False})
#                 self.env.cr.flush()
#         return super(PatientRegistrationFee, self).unlink()
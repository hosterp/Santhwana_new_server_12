from odoo import api, fields, models, _
import io
import base64
import xlsxwriter


class BillingReportWizard(models.TransientModel):
    _name = 'ip.billing.report.wizard'
    _description = 'Billing Report Wizard'

    from_date = fields.Date(string="From Date", required=True, default=fields.Date.today)
    to_date = fields.Date(string="To Date", required=True, default=fields.Date.today)
    bill_type = fields.Selection([
        ('ip_part', 'IP Part Bill'),
        ('discharge', 'Discharge Bill')
    ], string='Bill Type', )
    mode_pay = fields.Selection([('cash', 'Cash'),
                                 ('credit', 'Credit'),
                                 ('card', 'Card'),
                                 ('cheque', 'Cheque'),
                                 ('upi', 'UPI'), ], string='Payment Method', )

    # Show filtered records in tree/form
    @api.model
    def _get_report_values(self, docids, data=None):
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        model_name = data.get('model_name')
        date_field = data.get('date_field')
        pay_field = data.get('pay_field')  # can be 'mode_pay'
        pay_value = data.get('pay_value')  # e.g., 'cash', 'upi'

        domain = [(date_field, '>=', from_date), (date_field, '<=', to_date)]

        if pay_value:
            domain.append((pay_field, '=', pay_value))

        docs = self.env[model_name].search(domain)

        return {
            'doc_ids': docs.ids,
            'doc_model': model_name,
            'docs': docs,
            'data': data,
        }

    # PDF report
    def action_print_report(self):
        if self.bill_type == 'ip_part':
            model_name = 'ip.part.billing'
            report_ref = 'homeo_doctor.action_report_ip_billing'
            date_field = 'bill_date'
            pay_field = 'mode_pay'
        else:
            model_name = 'discharged.patient.record'
            report_ref = 'homeo_doctor.action_report_discharge_billing'
            date_field = 'discharge_date'
            pay_field = 'pay_mode'

        # Pass bill type and date info to the report
        return self.env.ref(report_ref).report_action(
            [],
            data={
                'from_date': str(self.from_date),
                'to_date': str(self.to_date),
                'bill_type': self.bill_type,
                'model_name': model_name,
                'date_field': date_field,
                'pay_field': pay_field,
                'pay_value': self.mode_pay
            }
        )

    # Excel export
    def action_print_excel(self):
        # Select model, report title and payment/date fields
        if self.bill_type == 'ip_part':
            model_name = 'ip.part.billing'
            date_field = 'bill_date'
            pay_field = 'mode_pay'
            report_title = "IP Part Billing Report"
        else:
            model_name = 'discharged.patient.record'
            date_field = 'discharge_date'
            pay_field = 'pay_mode'
            report_title = "Discharge Billing Report"

        # === Build domain dynamically ===
        domain = [
            (date_field, '>=', self.from_date),
            (date_field, '<=', self.to_date)
        ]
        if self.mode_pay:
            domain.append((pay_field, '=', self.mode_pay))

        # Fetch ordered records
        records = self.env[model_name].search(domain, order=f"{date_field} asc")

        # Excel generation
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Report")

        # Formats
        header_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter',
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1
        })
        subtitle_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter',
            'font_size': 12, 'font_color': '#555555'
        })
        total_format = workbook.add_format({
            'align': 'right', 'bold': True, 'border': 1
        })

        # Report title (row 1) and date range (row 2)
        sheet.merge_range('A1:D1', report_title, header_format)
        sheet.merge_range('A2:D2', f"From: {self.from_date}   To: {self.to_date}", subtitle_format)

        # Table headers
        headers = ['Bill No', 'Patient', 'Date', 'Amount']
        row_offset = 4
        for col, header in enumerate(headers):
            sheet.write(row_offset, col, header, header_format)

        # Write data
        total_amount = 0
        row = row_offset + 1
        for rec in records:
            if self.bill_type == 'ip_part':
                sheet.write(row, 0, rec.bill_number or rec.id)
                sheet.write(row, 1, rec.patient_name)
                sheet.write(row, 2, str(rec.bill_date))
                sheet.write(row, 3, rec.net_amount or 0)
                total_amount += rec.net_amount or 0
            else:
                sheet.write(row, 0, rec.patient_id or rec.id)
                sheet.write(row, 1, rec.name)
                sheet.write(row, 2, str(rec.discharge_date))
                sheet.write(row, 3, rec.total_amount or 0)
                total_amount += rec.total_amount or 0
            row += 1

        # Total row
        total_row = row + 1
        sheet.write(total_row, 2, "Total", total_format)
        sheet.write(total_row, 3, total_amount, total_format)

        # Auto column width
        sheet.set_column('A:D', 20)

        workbook.close()
        output.seek(0)

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'Billing_Report_{self.from_date}_to_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': 'ip.billing.report.wizard',
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


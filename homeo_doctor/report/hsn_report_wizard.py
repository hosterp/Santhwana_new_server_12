from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HSNReportWizard(models.TransientModel):
    _name = 'hsn.report.wizard'
    _description = 'HSN Report Wizard'

    from_date = fields.Date(string="From Date", required=True, default=fields.Date.today)
    to_date = fields.Date(string="To Date", required=True, default=fields.Date.today)
    op_category = fields.Selection([('op', 'OP'), ('admitted', 'IP'), ('others', 'OTHERS')])
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('credit', 'Credit')
    ], string='Payment Method')

    def _get_pharmacy_domain(self):
        self.ensure_one()
        domain = [
            ('date', '>=', self.from_date),
            ('date', '<=', self.to_date),
        ]
        if self.op_category:
            domain.append(('op_category', '=', self.op_category))
        if self.payment_method:
            domain.append(('payment_mathod', '=', self.payment_method))
        return domain

    def _get_hsn_report_lines(self):
        """Load HSN report rows via SQL.

        Avoids QWeb/ORM access to non-stored computed fields on
        pharmacy.prescription.line (hsn / taxable / cgst / sgst), which
        cause month-range reports to hang due to N+1 stock.entry searches.
        """
        self.ensure_one()
        pharmacies = self.env['pharmacy.description'].search(self._get_pharmacy_domain())
        if not pharmacies:
            return []

        self.env.cr.execute("""
            SELECT
                COALESCE(se.hsn, '') AS hsn,
                COALESCE(pt.name, '') AS description,
                COALESCE(pd.op_category, '') AS op_category,
                COALESCE(ppl.qty, 0) AS qty,
                COALESCE(ppl.gst, 0) AS gst,
                COALESCE(ppl.rate, 0.0) AS rate
            FROM pharmacy_prescription_line ppl
            JOIN pharmacy_description pd ON pd.id = ppl.pharmacy_id
            LEFT JOIN stock_entry se ON se.id = ppl.products_id
            LEFT JOIN product_product pp ON pp.id = se.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE ppl.pharmacy_id IN %s
            ORDER BY se.hsn NULLS LAST, ppl.id
        """, (tuple(pharmacies.ids),))

        lines = []
        for row in self.env.cr.dictfetchall():
            rate = row['rate'] or 0.0
            gst = row['gst'] or 0
            if gst:
                taxable = rate / (1 + gst / 100.0)
                cgst = taxable * (gst / 200.0)
                sgst = taxable * (gst / 200.0)
            else:
                taxable = rate
                cgst = 0.0
                sgst = 0.0
            lines.append({
                'hsn': row['hsn'] or '',
                'description': row['description'] or '',
                'op_category': row['op_category'] or '',
                'qty': row['qty'] or 0,
                'gst': gst,
                'rate': rate,
                'taxable': taxable,
                'cgst': cgst,
                'sgst': sgst,
            })
        return lines

    def print_report(self):
        self.ensure_one()
        if self.from_date > self.to_date:
            raise UserError("From Date cannot be greater than To Date.")
        return self.env.ref('homeo_doctor.action_report_hsn_gst_summary').report_action(self)

    def action_download_excel(self):
        self.ensure_one()
        if not self.from_date or not self.to_date:
            raise UserError("Please provide From and To dates")
        if self.from_date > self.to_date:
            raise UserError("From Date cannot be greater than To Date.")
        if not xlsxwriter:
            raise UserError("xlsxwriter is required to generate Excel reports.")

        lines = self._get_hsn_report_lines()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('HSN GST Summary')

        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00'})
        title = workbook.add_format({'align': 'center', 'bold': True, 'font_size': 14})
        subtitle = workbook.add_format({'align': 'center', 'italic': True})

        worksheet.merge_range('A1:J1', "HSN Wise GST Report", title)
        filter_text = "From %s to %s" % (self.from_date, self.to_date)
        if self.op_category:
            filter_text += " | Type: %s" % self.op_category.upper()
        if self.payment_method:
            filter_text += " | Payment: %s" % self.payment_method.capitalize()
        worksheet.merge_range('A2:J2', filter_text, subtitle)

        headers = [
            'Sl No', 'HSN Code', 'Description', 'Type', 'Total Qty',
            'GST%', 'Total Value', 'Taxable', 'CGST', 'SGST'
        ]
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, bold)

        total_qty = total_rate = total_taxable = total_cgst = total_sgst = 0.0
        row = 4
        for sl, line in enumerate(lines, start=1):
            worksheet.write(row, 0, sl)
            worksheet.write(row, 1, line['hsn'])
            worksheet.write(row, 2, line['description'])
            worksheet.write(row, 3, line['op_category'])
            worksheet.write(row, 4, line['qty'])
            worksheet.write(row, 5, line['gst'])
            worksheet.write_number(row, 6, line['rate'], money)
            worksheet.write_number(row, 7, line['taxable'], money)
            worksheet.write_number(row, 8, line['cgst'], money)
            worksheet.write_number(row, 9, line['sgst'], money)

            total_qty += line['qty'] or 0
            total_rate += line['rate'] or 0.0
            total_taxable += line['taxable'] or 0.0
            total_cgst += line['cgst'] or 0.0
            total_sgst += line['sgst'] or 0.0
            row += 1

        worksheet.write(row, 3, 'Total', bold)
        worksheet.write(row, 4, total_qty, bold)
        worksheet.write_number(row, 6, total_rate, bold_money)
        worksheet.write_number(row, 7, total_taxable, bold_money)
        worksheet.write_number(row, 8, total_cgst, bold_money)
        worksheet.write_number(row, 9, total_sgst, bold_money)

        workbook.close()
        output.seek(0)

        filename = "HSN_GST_Report_%s_to_%s.xlsx" % (self.from_date, self.to_date)
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }


class ReportHSNGSTSummary(models.AbstractModel):
    _name = 'report.homeo_doctor.report_hsn_gst_summary'
    _description = 'HSN GST Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['hsn.report.wizard'].browse(docids)
        report_lines = []
        for doc in docs:
            report_lines.extend(doc._get_hsn_report_lines())

        totals = {
            'qty': sum(l['qty'] or 0 for l in report_lines),
            'rate': sum(l['rate'] or 0.0 for l in report_lines),
            'taxable': sum(l['taxable'] or 0.0 for l in report_lines),
            'cgst': sum(l['cgst'] or 0.0 for l in report_lines),
            'sgst': sum(l['sgst'] or 0.0 for l in report_lines),
        }
        return {
            'doc_ids': docids,
            'doc_model': 'hsn.report.wizard',
            'docs': docs,
            'report_lines': report_lines,
            'totals': totals,
        }

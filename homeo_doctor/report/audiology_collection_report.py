from odoo import models, fields, api
from datetime import datetime


class AudiologyCollectionReportWizard(models.TransientModel):
    _name = "audiology.collection.report.wizard"
    _description = "X-Ray Collection Report Wizard"

    date_from = fields.Date("From Date", required=True,default=fields.Date.context_today)
    date_to = fields.Date("To Date", required=True,default=fields.Date.context_today)
    doctor_id = fields.Many2one("doctor.profile", string="Doctor")
    report_line_ids = fields.One2many(
        'audiology.billing.line.wizard', 'wizard_id', string="Report Lines"
    )
    def action_print_report(self):
        data = {
            'date_from': self.date_from and str(self.date_from) or False,
            'date_to': self.date_to and str(self.date_to) or False,
            'doctor_id': self.doctor_id.id if self.doctor_id else False,
        }
        return self.env.ref('homeo_doctor.action_audiology_collection_report').report_action(self, data=data)

    def _get_doctor_collection(self, data):
        domain = [
            ('bill_date', '>=', data['date_from']),
            ('bill_date', '<=', data['date_to']),
            ('status', '!=', 'cancelled')
        ]
        records = self.env['audiology.billing'].search(domain)
        if data.get('doctor_id'):
            records = records.filtered(lambda r: r.doctor.id == data['doctor_id'])


        summary = {}
        for rec in records:
            doctor = rec.doctor.name or "Unknown"
            summary.setdefault(doctor, 0.0)
            summary[doctor] += rec.total_amount

        return [{'doctor': k, 'amount': v} for k, v in summary.items()]

    def _prepare_report_lines(self):
        # Clear existing lines to ensure fresh data
        self.report_line_ids.unlink()
        lines = []

        # Add new lines from audiology.billing
        domain = [('bill_date', '>=', self.date_from), ('bill_date', '<=', self.date_to), ('status', '!=', 'cancelled')]
        
        bills = self.env['audiology.billing'].search(domain)
        if self.doctor_id:
            bills = bills.filtered(lambda b: b.doctor.id == self.doctor_id.id)

        for bill in bills:
            # Use total_amount which already includes rent and subtracts discount/advance.
            # Do NOT add rent/discount as separate lines — that causes double-counting.
            bill_label = ', '.join(
                line.particulars.name for line in bill.general_bill_line_ids if line.particulars
            ) or 'Audiology'

            lines.append((0, 0, {
                'wizard_id': self.id,
                'doctor_id': bill.doctor.id if bill.doctor else False,
                'doctor_name': bill.doctor.name if bill.doctor else '',
                'bill_name': bill_label,
                'mrd_no': bill.mrd_no.reference_no if bill.mrd_no else False,
                'patient_name': bill.patient_name or '',
                'bill_date': bill.bill_date if bill.bill_date else False,
                'amount': bill.total_amount or 0.0,
                'deleted': False,
            }))

        # Write back to wizard
        self.write({'report_line_ids': lines})

    def action_show_report(self):
        self.ensure_one()

        # 👉 ensure report lines are created/populated here
        self._prepare_report_lines()
        domain = [('wizard_id', '=', self.id)]

        if self.doctor_id:
            domain.append(('doctor_id', '=', self.doctor_id.id))
        return {
            'type': 'ir.actions.act_window',
            'name': 'audiology Collection Report',
            'res_model': 'audiology.billing.line.wizard',
            'view_mode': 'tree,form',
            'views': [(self.env.ref('homeo_doctor.view_audiology_billing_line_tree').id, 'tree')],
            'search_view_id': self.env.ref('homeo_doctor.view_audiology_billing_line_search').id,
            'target': 'current',
            'context': {
                'search_default_group_doctor': 1,
                'search_default_group_bill': 1,
            },
            'domain': domain,
        }

class ReportAudiologyCollection(models.AbstractModel):
    _name = 'report.homeo_doctor.audiology_collection_report_template'
    _description = 'Audiology Collection Report'

    def _get_report_values(self, docids, data=None):
        date_from_str = data.get('date_from')
        date_to_str = data.get('date_to')
        doctor_id = data.get('doctor_id')

        # Convert string into date object
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else None
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else None

        # Format for report
        formatted_date_from = date_from.strftime("%d/%m/%Y") if date_from else ""
        formatted_date_to = date_to.strftime("%d/%m/%Y") if date_to else ""

        # Build domain
        domain = [('status', '!=', 'cancelled')]
        if date_from_str:
            domain.append(('bill_date', '>=', date_from_str))
        if date_to_str:
            domain.append(('bill_date', '<=', date_to_str))
        
        records = self.env['audiology.billing'].search(domain, order="bill_date asc")
        if doctor_id:
            records = records.filtered(lambda r: r.doctor.id == doctor_id)

        if doctor_id:
            # Group by general_bill_line particulars
            grouped = {}
            for rec in records:
                for line in rec.general_bill_line_ids:
                    bill_key = line.particulars.name or "Unknown Bill"
                    grouped.setdefault(bill_key, {'records': [], 'subtotal': 0.0})
                    grouped[bill_key]['records'].append({
                        'patient': rec.patient_name,
                        'bill_date': rec.bill_date.strftime("%d/%m/%Y") if rec.bill_date else "",
                        'amount': line.total_amt,
                    })
                    grouped[bill_key]['subtotal'] += line.total_amt
                
                if rec.rent:
                    grouped.setdefault("Rent", {'records': [], 'subtotal': 0.0})
                    grouped["Rent"]['records'].append({
                        'patient': rec.patient_name,
                        'bill_date': rec.bill_date.strftime("%d/%m/%Y") if rec.bill_date else "",
                        'amount': rec.rent,
                    })
                    grouped["Rent"]['subtotal'] += rec.rent
                
                if rec.discount:
                    grouped.setdefault("Discount", {'records': [], 'subtotal': 0.0})
                    grouped["Discount"]['records'].append({
                        'patient': rec.patient_name,
                        'bill_date': rec.bill_date.strftime("%d/%m/%Y") if rec.bill_date else "",
                        'amount': -rec.discount,
                    })
                    grouped["Discount"]['subtotal'] -= rec.discount

            bills = []
            total_amount = 0.0
            for idx, (bill, vals) in enumerate(grouped.items(), start=1):
                bills.append({
                    'sl': idx,
                    'bill_name': bill,
                    'patients': vals['records'],
                    'subtotal': vals['subtotal'],
                })
                total_amount += vals['subtotal']

            return {
                'date_from': formatted_date_from,
                'date_to': formatted_date_to,
                'doctor_name': self.env['doctor.profile'].browse(doctor_id).name,
                'bills': bills,
                'total_amount': total_amount,
                'is_grouped': True,
            }
        else:
            # Summary by doctor
            summary = {}
            for rec in records:
                doctor = rec.doctor.name or "Unknown"
                summary.setdefault(doctor, 0.0)
                summary[doctor] += rec.total_amount

            doctors = [
                {'sl': idx, 'doctor': k, 'amount': v}
                for idx, (k, v) in enumerate(summary.items(), start=1)
            ]

            return {
                'date_from': formatted_date_from,
                'date_to': formatted_date_to,
                'doctor_name': "All Doctors",
                'doctors': doctors,
                'is_grouped': False,
            }





class AudiologyBillingLineWizard(models.TransientModel):
    _name = "audiology.billing.line.wizard"
    _description = "audiology Billing Line Wizard"

    wizard_id = fields.Many2one('audiology.collection.report.wizard', string="Wizard")
    doctor_name = fields.Char(string="Doctor")
    doctor_id = fields.Many2one("doctor.profile", "Doctor")  #
    bill_name = fields.Char(string="Bill")
    patient_name = fields.Char(string="Patient")
    bill_date = fields.Date(string="Date")
    amount = fields.Float(string="Amount")
    mrd_no = fields.Char(string="UHID")
    deleted = fields.Boolean(string="Deleted", default=False)

    def unlink_line(self):
        self.unlink()  # removes all selected lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'audiology.collection.report.wizard',
            'res_id': self[0].wizard_id.id if self else False,
            'view_mode': 'form',
            'target': 'new',
            'flags': {'action_buttons': True},
        }

    def action_print_report_from_line(self):
        self.ensure_one()
        if self.wizard_id:
            return self.wizard_id.action_print_report()
        else:
            return False

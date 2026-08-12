from odoo import models, fields, api
from odoo.exceptions import UserError


class CancelledBillWizard(models.TransientModel):
    _name = 'cancelled.bill.wizard'
    _description = 'Cancelled Bills Report Wizard'

    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)
    department = fields.Selection([
        ('general', 'General'),
        ('lab', 'Lab'),
        ('op', 'OP'),
        ('revisit', 'Revisit'),
        ('ot', 'OT'),
        ('xray', 'X-Ray'),
        ('pharmacy', 'Pharmacy'),
        ('casualty', 'Casualty'),
        ('audiology', 'Audiology'),
        ('discharge', 'Discharge'),
    ], string='Department', required=False)

    bill_number = fields.Char("Bill Number")
    patient_name = fields.Char("Patient Name")
    doctor_name = fields.Char("Doctor")
    department_name = fields.Char("Department")
    amount = fields.Float("Amount")
    staff_name = fields.Char("Staff Name")
    remarks = fields.Text("Remarks")
    cancelled_date = fields.Date("Cancelled Date")
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('credit', 'Credit'),
        ('cancelled', 'Cancelled'),
    ])
    def action_generate_pdf(self):
        return self.env.ref('homeo_doctor.cancelled_bill_pdf_report_action').report_action(self)

    def action_generate_html(self):
        return self.env.ref('homeo_doctor.cancelled_bill_pdf_report_action_html').report_action(self)


class CancelledBillReport(models.AbstractModel):
    _name = 'report.homeo_doctor.cancelled_bill_pdf_report'
    _description = 'Cancelled Bills Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['cancelled.bill.wizard'].browse(docids)

        # Map selection to actual models: (model, date_field, doctor_field, department_label_or_field, staff_field, amount_field)
        dept_model_map = {
            'general': ('general.billing', 'bill_date', 'doctor', 'General', 'staff_name', 'total_amount'),
            'lab': ('doctor.lab.report', 'date', 'doctor_id', 'Lab', 'staff_name', 'total_bill_amount'),
            'op': ('patient.reg', 'time', 'doc_name', 'Registration', 'register_staff_name', 'register_total_amount'),
            'revisit': ('patient.appointment', 'appointment_date', 'doctor_ids', 'Revisit', 'register_staff_name', 'register_total_amount'),
            'ot': ('ot.billing', 'bill_date', 'doctor', 'OT', 'staff_name', 'total_amount'),
            'xray': ('xray.billing', 'bill_date', 'doctor', 'X-Ray', 'staff_name', 'total_amount'),
            'pharmacy': ('pharmacy.description', 'date', 'doctor_name', 'Pharmacy', 'staff_name', 'total_amount'),
            'casualty': ('casuality.billing', 'bill_date', 'doctor', 'Casualty', 'staff_name', 'total_amount'),
            'audiology': ('audiology.billing', 'bill_date', 'doctor', 'Audiology', 'staff_name', 'total_amount'),
            'discharge': ('discharge.billing', 'bill_date', 'doctor', 'Discharge', 'staff_name', 'total_amount'),
        }

        bills_list = []

        # Filter selected department or all
        models_to_search = [dept_model_map[wizard.department]] if wizard.department else list(dept_model_map.values())

        for model_info in models_to_search:
            model_name, date_field, doctor_field, dept_field, staff_field, amount_field = model_info

            # Search cancelled bills
            domain = [
                ('status', '=', 'cancelled'),
                (date_field, '>=', wizard.from_date),
                (date_field, '<=', wizard.to_date),
            ]
            bills = self.env[model_name].search(domain, order=f'{date_field} asc')

            for bill in bills:
                # Doctor
                doctor_name = getattr(getattr(bill, doctor_field, None), 'name', '') if doctor_field else ''

                # Department: if dept_field is a string, use it directly; else, treat as relational field
                if dept_field:
                    if isinstance(dept_field, str) and not hasattr(bill, dept_field):
                        department_name = dept_field  # use hardcoded label
                    else:
                        department_name = getattr(getattr(bill, dept_field, None), 'name', '')
                else:
                    department_name = ''

                # Staff
                staff_name = getattr(getattr(bill, staff_field, None), 'name', '') if staff_field else ''

                # Amount
                amount = getattr(bill, amount_field, 0)
                patient_name = ''
                if hasattr(bill, 'patient_name') and bill.patient_name:
                    patient_name = bill.patient_name
                elif hasattr(bill, 'patient_id') and bill.patient_id:
                    patient_name = bill.patient_id
                elif hasattr(bill, 'name') and bill.name:
                    patient_name = bill.name
                bill_number = (
                        getattr(bill, 'bill_number', None)
                        or getattr(bill, 'report_reference', None)
                        or getattr(bill, 'appointment_reference', '')
                )

                bills_list.append({
                    'sl_no': len(bills_list) + 1,
                    'bill_number': bill_number,
                    'patient_name': patient_name,
                    'doctor_name': doctor_name,
                    'department': department_name,
                    'amount': amount,
                    'staff_name': staff_name,
                    'remarks': getattr(bill, 'remarks', ''),
                    'cancelled_date': getattr(bill, date_field, ''),
                })

        if not bills_list:
            raise UserError("No cancelled bills found in the selected date range.")

        return {
            'doc_ids': docids,
            'doc_model': 'cancelled.bill.wizard',
            'docs': wizard,
            'data': {
                'bills': bills_list,
                'from_date': wizard.from_date.strftime('%d-%m-%Y'),
                'to_date': wizard.to_date.strftime('%d-%m-%Y'),
            }
        }


class CancelledBillReportModel(models.TransientModel):
    _name = 'cancelled.bill.report'
    _description = 'Cancelled Bills Report Wizard'
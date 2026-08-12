from odoo import api, models, fields


class PatientRegistrationReportWizard(models.TransientModel):
    _name = 'patient.registration.report.wizard'
    _description = 'Patient Registration Report Wizard'

    from_date = fields.Date(string="From Date", required=True, default=fields.Date.today)
    to_date = fields.Date(string="To Date", required=True, default=fields.Date.today)
    register_mode_payment = fields.Selection([('cash', 'Cash'),
                                              ('card', 'Card'),
                                              ('cheque', 'Cheque'),
                                              ('credit', 'Credit'),
                                              ('upi', 'Mobile Pay'), ], string='Payment Method', default='cash')

    def action_print_pdf(self):
        # Search for patients within the given date range
        domain = [
            ('time', '>=', self.from_date),
            ('time', '<=', self.to_date),
            '|',  # OR condition
            '&', ('status', '=', 'unpaid'), ('register_mode_payment', '=', 'credit'),
            ('status', 'not in', ['unpaid', 'cancelled']),

        ]

        if self.register_mode_payment:
            domain.append(('register_mode_payment', '=', self.register_mode_payment))

        patients = self.env['patient.reg'].search(domain)

        patient_list = []
        sl = 1

        # Prepare data for the report
        for patient in patients:
            patient_list.append({
                'sl': sl,
                'reference_no': patient.reference_no or '',
                'patient_name': patient.patient_id.name if hasattr(patient.patient_id,
                                                                   'name') else patient.patient_id or '',
                'age': patient.age or '',
                'time': patient.time or '',
                'address': patient.address or '',
                'phone': patient.phone_number or '',
                'consultation_fee': patient.consultation_fee or '',
                'registration_fee': patient.registration_fee or '',
                'register_total_amount': patient.register_total_amount or '',
                'mode_of_payment': patient.register_mode_payment or '',
                'doctor': patient.doc_name.name if hasattr(patient.doc_name, 'name') else patient.doc_name or '',
            })
            sl += 1

        # Format dates for display
        from_date_str = self.from_date.strftime('%Y-%m-%d') if self.from_date else ''
        to_date_str = self.to_date.strftime('%Y-%m-%d') if self.to_date else ''

        # Prepare the context for the report
        data = {
            'form': {
                'from_date': from_date_str,
                'to_date': to_date_str,
                'patients': patient_list,
            },
            'docs': self,
        }

        # Return the PDF report action
        return self.env.ref('homeo_doctor.action_patient_registration_pdf').with_context(landscape=True).report_action(
            self, data=data)

    def action_export_excel(self):
        base_url = '/web/binary/download_patient_excel'
        url = f'{base_url}?from_date={self.from_date}&to_date={self.to_date}'

        if self.register_mode_payment:
            url += f'&register_mode_payment={self.register_mode_payment}'

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }


class PatientRegistrationReport(models.AbstractModel):
    _name = 'report.homeo_doctor.patient_registration_pdf_template'
    _description = 'Patient Registration Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        This function ensures data is prepared correctly for the template
        """
        if not data:
            data = {}

        # Get the wizard record
        patient_wizard = self.env['patient.registration.report.wizard'].browse(docids)

        # In case the data wasn't passed from the wizard
        if not data.get('form', {}).get('patients'):
            patients = self.env['patient.reg'].search([
                ('date', '>=', patient_wizard.from_date),
                ('date', '<=', patient_wizard.to_date)
            ])

            patient_list = []
            sl = 1

            for patient in patients:
                patient_list.append({
                    'sl': sl,
                    'reference_no': patient.reference_no or '',
                    'patient_name': patient.patient_id.name if hasattr(patient.patient_id,
                                                                       'name') else patient.patient_id or '',
                    'age': patient.age or '',
                    'address': patient.address or '',
                    'phone': patient.phone_number or '',
                    'doctor': patient.doc_name.name if hasattr(patient.doc_name, 'name') else patient.doc_name or '',
                })
                sl += 1

            # Format dates for display
            from_date_str = patient_wizard.from_date.strftime('%Y-%m-%d') if patient_wizard.from_date else ''
            to_date_str = patient_wizard.to_date.strftime('%Y-%m-%d') if patient_wizard.to_date else ''

            data['form'] = {
                'from_date': from_date_str,
                'to_date': to_date_str,
                'patients': patient_list,
            }

        return {
            'doc_ids': docids,
            'doc_model': 'patient.registration.report.wizard',
            'docs': patient_wizard,
            'data': data,
        }

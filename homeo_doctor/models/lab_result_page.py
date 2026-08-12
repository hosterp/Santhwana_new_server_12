from odoo import api, fields, models, _




class LabResultPage(models.Model):
    _name='lab.result.page'
    _rec_name = 'bill_number'
    _order = 'bill_number asc'

    bill_number=fields.Many2one('doctor.lab.report',string='Bill Number', domain=[('status', '=', 'paid')])
    patient_id=fields.Many2one(related='bill_number.user_ide',string='UHID')
    patient_name = fields.Char(related='bill_number.patient_name')
    doctor=fields.Many2one('doctor.profile',string='Doctor', related='bill_number.doctor_id', store=True, readonly=False)
    sample_collected=fields.Date(string='Sample collection On')
    lab_collection=fields.Date(string='Lab Collection On')
    test_on=fields.Date(string='Test On')
    internal_doctor = fields.Many2one('internal.doctor',string='Select Internal Doctor')
    lab_incharge =fields.Many2one('hr.employee',string='Select Lab In-charge')
    lab_technician = fields.Many2one('hr.employee',string='Select Lab Technician')
    lab_line_ids = fields.One2many('lab.scan.line', 'lab_result_id', string='Lab Result')
    staff=fields.Char(string='Staff')
    from_date = fields.Date(string="From Date")
    to_date = fields.Date(string="To Date")
    patient_phone = fields.Char(string="Mobile No")
    status = fields.Selection([
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", tracking=True)
    sample_status = fields.Selection([
        ('pending', 'Pending'),
        ('sample_collected', 'Sample Collected'),
    ], string="Status", default="pending", tracking=True)
    result_status = fields.Selection([
        ('pending', 'Result Pending'),
        ('result_ready', 'Result Ready'),
    ], string="Status", default="pending", tracking=True)
    patient_id_name = fields.Many2one('patient.registration', string="Patient", ondelete='cascade')
    patient_re_id_name = fields.Many2one('patient.reg', string="Patient", ondelete='cascade')
    patient_id_admitted = fields.Many2one(
        'hospital.admitted.patient',
        string="Admitted Patient",
        ondelete='cascade'
    )
    age = fields.Integer('Age')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string="Gender")


    @api.model
    def create(self, vals):
        # Ensure the bill_number is in the vals
        if vals.get('bill_number'):
            bill = self.env['doctor.lab.report'].browse(vals['bill_number'])
            if bill:
                # Assigning patient_id_name and patient_re_id_name from bill
                if bill.patient_id:
                    vals['patient_id_name'] = bill.patient_id.id
                if bill.user_ide:
                    vals['patient_re_id_name'] = bill.user_ide.id
                    # print('patientreg note................................................................')


                    latest_patient = self.env['hospital.admitted.patient'].search([
                        ('patient_id', '=', bill.patient_id.id),
                    ], order='admission_date desc', limit=1)


                    if latest_patient:
                        vals['patient_id_admitted'] = latest_patient.id
                        # print("Latest Admitted Patient ID: ", latest_patient.id)

        # Debugging: Print final vals before creating record
        # print("Final vals before create:", vals)

        # Call the super method to create the record
        record = super(LabResultPage, self).create(vals)
        # print("Created LabResultPage record with patient_id_admitted: ", record.patient_id_admitted)

        return record

    # @api.model
    # def create(self, vals):
    #     if vals.get('bill_number'):
    #         bill = self.env['doctor.lab.report'].browse(vals['bill_number'])
    #         if bill and bill.patient_id:
    #             vals['patient_id_admitted'] = bill.patient_id.id
    #     return super(LabResultPage, self).create(vals)

    def action_sample_collected(self):
        for record in self:
            record.sudo().write({
                'sample_status': 'sample_collected',
                'sample_collected': fields.Date.today(),
            })
            if record.bill_number:
                record.bill_number.sudo().write({
                    'sample_status': 'sample_collected'
                })

    def action_result_ready(self):
        for record in self:
            record.sudo().write({
                'result_status': 'result_ready',
                'test_on': fields.Date.today(),
            })
            if record.bill_number:
                record.bill_number.sudo().write({
                    'result_status': 'result_ready'
                })

    @api.onchange('from_date', 'to_date')
    def _onchange_date_filter(self):
        domain = [('status', '=', 'paid')]
        if self.from_date:
            domain.append(('date', '>=', self.from_date))
        if self.to_date:
            domain.append(('date', '<=', self.to_date))

        return {'domain': {'bill_number': domain}}

    @api.onchange('bill_number')
    def _onchange_bill_number(self):
        self.patient_id = False
        self.patient_name = False
        self.doctor = False
        self.sample_collected = False
        self.lab_collection = False
        self.test_on = False
        self.internal_doctor = False
        self.lab_incharge = False
        self.lab_technician = False
        self.lab_line_ids = [(5, 0, 0)]

        if self.bill_number:

            lab_report = self.bill_number


            self.patient_id = lab_report.user_ide.id
            self.patient_name = lab_report.patient_name
            self.doctor = lab_report.doctor_id.id
            self.sample_collected = lab_report.date


            lab_lines = []
            for lab_line in lab_report.lab_line_ids:
                lab_lines.append((0, 0, {
                    'lab_result_id': self.id,
                    'lab_test_name': lab_line.lab_test_name,
                    'lab_result': lab_line.lab_result,
                    'unit':lab_line.unit,
                }))


            if lab_lines:
                self.lab_line_ids = lab_lines


class InternalDoctor(models.Model):
    _name = 'internal.doctor'
    _rec_name = 'internal_doctor'


    internal_doctor = fields.Char(string='Internal Doctor')


class labIncharge(models.Model):
    _name = 'lab.incharge'
    _rec_name = 'lab_incharge_name'


    lab_incharge_name=fields.Char(string='Lab Incharge')


class LabTechnician(models.Model):
    _name = 'lab.technician'
    _rec_name='lab_tecnician_name'


    lab_tecnician_name = fields.Char(string='Lab Technician')
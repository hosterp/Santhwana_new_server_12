from odoo import api, fields, models, _


class LabPaymentWizard(models.Model):
    _name = 'lab.payment'



    patient_id=fields.Many2one('doctor.lab.report',string='Patient ID')
    patient_name=fields.Char(related='patient_id.patient_name',string='Patient Name')
    pay_mode = fields.Selection([('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI'),('credit','Credit')], string='Payment Method',
                                default='cash')
    total_amount=fields.Integer(string='Payable Amount')
    amount_paid=fields.Integer(string='Amount Paid')
    balance=fields.Integer(string='Balance')

    @api.onchange('amount_paid')
    def _onchage_amount_paid(self):
        for rec in self:
            if (rec.amount_paid < rec.total_amount and rec.amount_paid > 0):
                rec.balance = rec.total_amount - rec.amount_paid
            elif(rec.amount_paid > rec.total_amount and rec.amount_paid >    0):
                rec.balance = rec.amount_paid -  rec.total_amount

    def action_confirm_payment(self):

        lab_report = self.patient_id

        if lab_report:

            lab_report.write({
                'status': 'paid'
            })


            lab_result_page = self.env['lab.result.page'].create({
                'bill_number': lab_report.id,
                'patient_id': lab_report.user_ide.id,
                'patient_name': lab_report.patient_name,
                'doctor': lab_report.doctor_id.id,
                'sample_collected': fields.Datetime.now(),
                'lab_collection': fields.Datetime.now(),
                'test_on': fields.Datetime.now(),
            })


            lab_lines = []
            for lab_line in lab_report.lab_line_ids:
                lab_lines.append((0, 0, {
                    'lab_result_id': lab_result_page.id,
                    'lab_type_id': lab_line.lab_type_id.id,
                    'lab_test_name': lab_line.lab_test_name,
                    'lab_result': lab_line.lab_result,
                    'unit':lab_line.unit,
                    'lab_reference_range':lab_line.lab_reference_range
                }))


            if lab_lines:
                lab_result_page.write({'lab_line_ids': lab_lines})


        return {'type': 'ir.actions.act_window_close'}




from odoo import models, fields, api, _
from odoo.exceptions import AccessDenied, ValidationError

class SupplierInvoiceVerifyWizard(models.TransientModel):
    _name = 'supplier.invoice.verify.wizard'
    _description = 'Supplier Invoice Verification Wizard'

    def _default_employee(self):
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.env.uid)], limit=1)
        return employee.id if employee else False

    move_id = fields.Many2one('account.move', string='Supplier Invoice', required=True, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Verify Person Name',
        default=_default_employee,
        required=True
    )
    password = fields.Char(string='Billing Password', required=True)

    def action_verify(self):
        self.ensure_one()
        employee = self.employee_id or self.env['hr.employee'].sudo().browse(self._default_employee())
        if not employee or not employee.exists():
            raise ValidationError(_("No employee record found for current user."))
        if not self.password:
            raise ValidationError(_("Please enter the Billing Password."))

        pwd = self.password.strip()

        # 1. Check staff_password_hash on hr.employee
        if employee.staff_password_hash:
            if pwd != employee.staff_password_hash:
                raise ValidationError(_("Invalid Billing Password for '%s'. Verification failed!") % employee.name)
        # 2. Fallback to Odoo system password if staff_password_hash is not set on hr.employee
        elif employee.user_id:
            user = employee.user_id
            db_name = self.env.cr.dbname
            try:
                self.env['res.users'].sudo().authenticate(db_name, user.login, pwd, {'interactive': False})
            except AccessDenied:
                raise ValidationError(_("Invalid Billing Password for '%s'. Verification failed!") % employee.name)
            except Exception as e:
                raise ValidationError(_("Verification failed for '%s': %s") % (employee.name, str(e)))
        else:
            raise ValidationError(_("No Staff/Billing password is set for '%s' in Employee configuration.") % employee.name)

        self.move_id.sudo().write({
            'is_verified': True,
            'verified_by': employee.user_id.id if employee.user_id else self.env.uid,
            'verified_person_name': employee.name,
            'verified_date': fields.Datetime.now(),
        })

        return {'type': 'ir.actions.act_window_close'}

from odoo import api, fields, models


class BillDoctorLock(models.AbstractModel):
    """Keep the doctor that was on a bill when it was saved.

    A later revisit or a later admitted-doctor change must show only on bills
    created after that change.
    """
    _name = 'bill.doctor.lock'
    _description = 'Freeze bill doctor at save'

    locked_doctor = fields.Many2one(
        'doctor.profile', string='Locked Doctor', copy=False,
    )

    def _bill_doctor_field(self):
        return 'doctor'

    def _source_cutoff(self):
        """Ignore revisits and registrations created after this bill was saved."""
        self.ensure_one()
        if isinstance(self.id, int) and self.create_date:
            return [('create_date', '<=', self.create_date)]
        return []

    @api.model
    def create(self, vals):
        records = super(BillDoctorLock, self).create(vals)
        if self.env.context.get('skip_doctor_lock'):
            return records
        doctor_field = records[:1]._bill_doctor_field() if records else False
        if not doctor_field or doctor_field not in records._fields:
            return records
        for rec in records:
            if rec.locked_doctor:
                continue
            doctor = rec[doctor_field]
            if doctor:
                rec.with_context(skip_doctor_lock=True).write({
                    'locked_doctor': doctor.id,
                })
        return records

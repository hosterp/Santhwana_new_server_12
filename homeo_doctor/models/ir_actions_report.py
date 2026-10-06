from odoo import models, _
from odoo.exceptions import UserError


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _raise_print_blocked(self, record):
        status_label = dict(record._fields['status'].selection).get(record.status, record.status)
        raise UserError(_(
            "Print Not Allowed\n\n"
            "This bill status is %s.\n"
            "Please click Pay before printing.\n"
            "(Draft / Unpaid / Cancelled cannot be printed, including VSSC.)"
        ) % status_label)

    def _get_op_revisit_print_blocked_records(self, res_ids):
        if not res_ids:
            return self.env['patient.reg']
        if isinstance(res_ids, models.Model):
            res_ids = res_ids.ids
        elif isinstance(res_ids, int):
            res_ids = [res_ids]
        for report in self:
            if report.model == 'patient.appointment':
                recs = self.env['patient.appointment'].browse(res_ids).exists()
                return recs.filtered(lambda r: r._is_print_blocked())
            if report.model == 'patient.reg':
                recs = self.env['patient.reg'].browse(res_ids).exists()
                return recs.filtered(lambda r: r._is_print_blocked())
        return self.env['patient.reg']

    def _check_op_revisit_print_blocked(self, res_ids):
        bad = self._get_op_revisit_print_blocked_records(res_ids)
        if bad:
            self._raise_print_blocked(bad[0])

    def report_action(self, docids, data=None, config=True):
        self._check_op_revisit_print_blocked(docids)
        # After Pay only: ensure revisit receipt number exists for print
        if docids:
            ids = docids.ids if isinstance(docids, models.Model) else (
                [docids] if isinstance(docids, int) else docids
            )
            for report in self:
                if report.model == 'patient.appointment':
                    recs = self.env['patient.appointment'].browse(ids).exists()
                    recs.filtered(lambda r: not r._is_print_blocked())._ensure_payment_receipt_number()
        return super().report_action(docids, data=data, config=config)

    def _render_qweb_pdf(self, res_ids=None, data=None):
        self._check_op_revisit_print_blocked(res_ids)
        return super()._render_qweb_pdf(res_ids=res_ids, data=data)

    def _render_qweb_html(self, docids, data=None):
        self._check_op_revisit_print_blocked(docids)
        return super()._render_qweb_html(docids, data=data)

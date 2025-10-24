from odoo import models, fields, api, _


class RmcDocketCancelWizard(models.TransientModel):
    _name = 'rmc.docket.cancel.wizard'
    _description = 'Cancel Docket Wizard'

    docket_id = fields.Many2one('rmc.docket', string='Docket', required=True)
    reason_category = fields.Selection([
        ('customer_request', 'Customer Request'),
        ('plant_breakdown', 'Plant Breakdown'),
        ('logistics_issue', 'Logistics Issue'),
        ('quality_issue', 'Quality Issue'),
        ('other', 'Other'),
    ], string='Reason Category', required=True)
    reason = fields.Text(string='Reason', required=False)

    def action_confirm_cancel(self):
        self.ensure_one()
        docket = self.docket_id
        # persist on docket
        docket.write({
            'state': 'cancel',
            'cancel_reason_category': self.reason_category,
            'cancel_reason': self.reason or '',
        })
        # chatter
        msg = _('[Cancelled] Category: %s\nReason: %s') % (self.reason_category, self.reason or '-')
        try:
            docket.message_post(body=msg)
        except Exception:
            pass
        return {'type': 'ir.actions.act_window_close'}

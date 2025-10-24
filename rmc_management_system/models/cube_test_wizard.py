from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class CubeTestWizard(models.TransientModel):
    _name = 'rmc.cube.test.wizard'
    _description = 'Create Cube Test (Select Trigger)'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    trigger_condition = fields.Selection([
        ('workorder', 'Workorder Wise'),
        ('every_truck', 'Every Truck / Docket / Ticket'),
        ('every_six', 'Every 6 Docket / Ticket'),
    ], string='Trigger Condition', required=True)

    assigned_user_id = fields.Many2one('res.users', string='Agent/Inspector', default=lambda self: self.env.user, required=True)
    create_7day = fields.Boolean(string='Create 7-Day?', default=True)
    create_28day = fields.Boolean(string='Create 28-Day?', default=True)
    date_7day = fields.Date(string='Planned Date (7-Day)', default=fields.Date.context_today)
    date_28day = fields.Date(string='Planned Date (28-Day)', default=lambda self: fields.Date.context_today(self) + timedelta(days=27))
    notes = fields.Text(string='Notes')

    # Read-only summary helpers
    summary_domain_scope = fields.Selection([
        ('so', 'This Sale Order'),
        ('global', 'All Orders'),
    ], default='so')

    def _cube_summary_domain(self):
        domain = []
        if self.summary_domain_scope == 'so' and self.sale_order_id:
            domain.append(('sale_order_id', '=', self.sale_order_id.id))
        if self.assigned_user_id:
            domain.append(('user_id', '=', self.assigned_user_id.id))
        return domain

    def action_create(self):
        """Save trigger configuration only; actual cube tests are created by triggers (workorder/docket)."""
        self.ensure_one()
        so = self.sale_order_id
        if not so:
            raise UserError(_('No Sale Order found.'))

        # Persist trigger choice and defaults on SO
        so.write({
            'cube_test_condition': self.trigger_condition,
            'cube_test_user_id': self.assigned_user_id.id,
            'cube_test_notes': self.notes,
        })

        # Provide user feedback
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cube Test Trigger Saved'),
                'message': _('Tests will be created automatically when the %s trigger occurs.') % (dict(self._fields['trigger_condition'].selection).get(self.trigger_condition)),
                'sticky': False,
            }
        }

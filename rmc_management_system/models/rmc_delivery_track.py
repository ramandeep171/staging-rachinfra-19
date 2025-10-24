from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RmcDeliveryTrack(models.Model):
    _name = 'rmc.delivery_track'
    _description = 'RMC Delivery Tracking'

    name = fields.Char(string='Reference', required=True, default='New', copy=False)
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Helpdesk Ticket', ondelete='cascade')
    workorder_ticket_id = fields.Many2one('dropshipping.workorder.ticket', string='Workorder Ticket')
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    batch_id = fields.Many2one('rmc.batch', string='Batch')
    truck_loading_id = fields.Many2one('rmc.truck_loading', string='Truck Loading')
    live_location = fields.Char(string='Live Location')

    # Divert fields
    divert_status = fields.Selection([
        ('pending', 'Pending'),
        ('diverted', 'Diverted'),
        ('cancelled', 'Cancelled'),
    ], string='Divert Status', default='pending')
    new_site_id = fields.Many2one('res.partner', string='New Site')

    date = fields.Datetime(string='Tracking Date', default=fields.Datetime.now)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.delivery_track') or 'DT/0000'
        return super().create(vals_list)

    def action_list_available_workorders(self):
        """Return running workorders available for diversion (in_progress state)."""
        self.ensure_one()
        domain = [('state', 'in', ['in_progress', 'assigned'])]
        # Prefer same company when available
        company = self.sudo().env.company if hasattr(self.sudo(), 'env') else None
        if company:
            domain += [('company_id', '=', company.id)]
        workorders = self.env['dropshipping.workorder'].search(domain)
        return workorders

    def action_divert_to_workorder(self, workorder):
        """Divert this delivery track (and its ticket) to another running workorder.

        Steps:
        - keep original batch_id, truck_loading_id and live_location fields stored
        - update workorder_id and associated workorder_ticket to new workorder
        - set divert_status to 'diverted' and new_site_id if provided on the ticket
        - call delivery variance reconciliation adjustments if needed
        """
        self.ensure_one()
        # TEMP: allow diversion to any workorder state
        if not workorder:
            raise ValidationError(_('Please select a target workorder.'))

        # Keep original references in history fields (already present)
        # Update relations
        self.workorder_id = workorder.id
        if self.workorder_ticket_id:
            # point ticket to new workorder
            self.workorder_ticket_id.workorder_id = workorder.id
            # keep helpdesk ticket link intact
        # Update divert status
        self.divert_status = 'diverted'

        # Recompute related delivery variance if applicable
        try:
            # If associated truck loading has a delivery variance, mark it for re-evaluation
            if self.truck_loading_id and self.truck_loading_id.delivery_variance_id:
                dv = self.truck_loading_id.delivery_variance_id
                # mark as pending reconciliation so the manager can review
                dv.reconciliation_status = 'pending'
        except Exception:
            # Non-fatal
            pass

        return True

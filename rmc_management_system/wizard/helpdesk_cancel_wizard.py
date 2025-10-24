from odoo import models, fields, api, _


class HelpdeskTicketCancelWizard(models.TransientModel):
    _name = 'helpdesk.ticket.cancel.wizard'
    _description = 'Cancel Helpdesk Ticket Wizard'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True)
    reason_category = fields.Selection([
        ('customer_request', 'Customer Request'),
        ('plant_breakdown', 'Plant Breakdown'),
        ('logistics_issue', 'Logistics Issue'),
        ('quality_issue', 'Quality Issue'),
        ('vendor_refuse', 'Vendor Refuse'),
        ('other', 'Other'),
    ], string='Reason Category', required=True)
    reason = fields.Text(string='Reason', required=True)

    def action_confirm_cancel(self):
        self.ensure_one()
        t = self.ticket_id
        # Set to a Cancelled stage if available; else fallback to current behavior
        cancelled_stage = self.env['helpdesk.stage'].search([('name', 'ilike', 'cancel')], limit=1)
        vals = {
            'cancel_reason_category': self.reason_category,
            'cancel_reason': self.reason or '',
        }
        if cancelled_stage:
            vals['stage_id'] = cancelled_stage.id
        t.write(vals)
        # Ensure any additional cancellation side-effects are applied (e.g., sync workorder tickets)
        try:
            t.action_cancel_ticket()
        except Exception:
            pass
        # Create a new follow-up ticket with reference to the cancelled one
        new_vals = {
            'name': _('%s (Recreated)') % (t.name or ''),
            'partner_id': t.partner_id.id if hasattr(t, 'partner_id') else False,
            'team_id': t.team_id.id if hasattr(t, 'team_id') else False,
            'user_id': t.user_id.id if t.user_id else False,
            'priority': t.priority,
            'sale_order_id': t.sale_order_id.id if t.sale_order_id else False,
            'assigned_subcontractor_id': t.assigned_subcontractor_id.id if t.assigned_subcontractor_id else False,
            'transport_subcontractor_id': t.transport_subcontractor_id.id if hasattr(t, 'transport_subcontractor_id') and t.transport_subcontractor_id else False,
            'transporter_id': t.transporter_id.id if t.transporter_id else False,
            'rmc_quantity': t.rmc_quantity,
            'distance_to_site': t.distance_to_site,
            'diverted_from_ticket_id': t.id,
            'diverted_from_ticket_name': t.name,
            'tag_ids': [(6, 0, t.tag_ids.ids)],
            'description': (t.description or '') + "\n" + _('[Auto-created after cancellation] Category: %s | Reason: %s') % (self.reason_category, self.reason),
        }
        # Use a separate sequence for regenerated tickets
        try:
            regen_seq = self.env['ir.sequence'].next_by_code('helpdesk.ticket.regenerated')
        except Exception:
            regen_seq = False
        if regen_seq:
            # Also set a user-facing name if desired; keep original name with suffix
            new_vals['name'] = _('%s (Recreated)') % (t.name or '')
        new_ticket = self.env['helpdesk.ticket'].create(new_vals)
        if regen_seq and new_ticket:
            try:
                new_ticket.sudo().write({'ticket_ref': regen_seq})
            except Exception:
                pass
        # Link regenerated ticket to the same workorder as the original
        try:
            orig_wo = False
            # Prefer computed workorder_id if available
            if getattr(t, 'workorder_id', False):
                orig_wo = t.workorder_id
            if not orig_wo and t.workorder_ticket_ids:
                orig_wo = t.workorder_ticket_ids[:1].workorder_id
            if not orig_wo and t.docket_ids:
                orig_wo = t.docket_ids[:1].workorder_id
            if orig_wo and new_ticket:
                qty = t.rmc_quantity or (t.workorder_ticket_ids[:1].quantity if t.workorder_ticket_ids else 0.0)
                self.env['dropshipping.workorder.ticket'].create({
                    'workorder_id': orig_wo.id,
                    'name': _('Regenerated: %s') % (new_ticket.name or 'Ticket'),
                    'quantity': qty or 0.0,
                    'helpdesk_ticket_id': new_ticket.id,
                    'state': 'draft',
                    'delivery_location': getattr(orig_wo, 'delivery_location', False),
                    'delivery_coordinates': getattr(orig_wo, 'delivery_coordinates', False),
                    'notes': _('Auto-linked to original workorder after cancellation.'),
                })
        except Exception:
            pass
        # chatter
        msg = _('[Cancelled] Category: %s\nReason: %s') % (self.reason_category, self.reason or '-')
        try:
            t.message_post(body=msg)
            if new_ticket:
                t.message_post(body=_('New ticket created: %s (ID %s)') % (new_ticket.name, new_ticket.id))
                new_ticket.message_post(body=_('Created from cancelled ticket: %s (ID %s)') % (t.name, t.id))
        except Exception:
            pass
        return {'type': 'ir.actions.act_window_close'}

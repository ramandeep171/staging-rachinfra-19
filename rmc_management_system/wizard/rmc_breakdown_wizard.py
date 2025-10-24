from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RmcBreakdownWizard(models.TransientModel):
    _name = 'rmc.breakdown.wizard'
    _description = 'RMC Plant Breakdown (Half Load) Wizard'

    truck_loading_id = fields.Many2one('rmc.truck_loading', string='Truck Loading', required=True)
    docket_id = fields.Many2one('rmc.docket', string='Docket', related='truck_loading_id.docket_id', store=False)
    original_subcontractor_id = fields.Many2one('rmc.subcontractor', string='Original Subcontractor',
                                               related='truck_loading_id.subcontractor_id', store=False)
    new_subcontractor_id = fields.Many2one('rmc.subcontractor', string='New Subcontractor', required=True)
    new_site_id = fields.Many2one('res.partner', string='New Site')
    loaded_at_original = fields.Float(string='Loaded at Original (M3)', required=True)
    remaining_to_complete = fields.Float(string='Remaining to Complete (M3)', required=True)
    create_draft = fields.Boolean(string='Create Bills as Draft', default=True)

    # --- Hard cap: Never exceed total ordered quantity ---
    @api.constrains('loaded_at_original', 'remaining_to_complete', 'truck_loading_id')
    def _check_not_exceed_total_ordered(self):
        """Ensure loaded_at_original + remaining_to_complete never exceeds the ordered qty.

        Ordered qty priority:
        1) Ticket.rmc_quantity if available and > 0
        2) Docket.quantity_ordered if available and > 0
        If neither is present (0 or missing), skip the hard cap.
        """
        for rec in self:
            tl = rec.truck_loading_id
            if not tl:
                continue
            docket = tl.docket_id
            # Resolve ordered quantity from ticket first, else docket
            ordered = 0.0
            try:
                ticket = docket.helpdesk_ticket_id if docket else False
            except Exception:
                ticket = False
            if ticket and getattr(ticket, 'rmc_quantity', 0.0) and ticket.rmc_quantity > 0:
                ordered = float(ticket.rmc_quantity)
            elif docket and getattr(docket, 'quantity_ordered', 0.0) and docket.quantity_ordered > 0:
                ordered = float(docket.quantity_ordered)
            # If we have no meaningful ordered qty, do not enforce to avoid false positives
            if not ordered:
                continue
            total_planned = float(rec.loaded_at_original or 0.0) + float(rec.remaining_to_complete or 0.0)
            # Allow tiny epsilon for float arithmetic
            if total_planned > ordered + 1e-6:
                raise ValidationError(_(
                    'Total quantity for breakdown (Loaded %.3f + Remaining %.3f = %.3f) cannot exceed Ordered %.3f.'
                ) % (
                    rec.loaded_at_original or 0.0,
                    rec.remaining_to_complete or 0.0,
                    total_planned,
                    ordered,
                ))

    @api.onchange('truck_loading_id')
    def _onchange_truck_loading_id(self):
        if self.truck_loading_id:
            self.loaded_at_original = float(self.truck_loading_id.total_quantity or 0.0)
            # Estimate remaining from ticket quantity vs delivered
            ticket = False
            try:
                ticket = self.truck_loading_id.docket_id.helpdesk_ticket_id
            except Exception:
                ticket = False
            ordered = float(getattr(ticket, 'rmc_quantity', 0.0) or 0.0)
            delivered = float(getattr(ticket, 'rmc_qty_delivered', 0.0) or 0.0)
            remaining = max(0.0, ordered - delivered)
            self.remaining_to_complete = remaining

    def _get_vendor_price(self, partner, product):
        """Fetch price from vendor price list (product.seller) if available."""
        if not partner or not product:
            return 0.0
        # Prefer a seller line that matches this partner (use partner_id field on supplierinfo)
        try:
            sellers = product.seller_ids.filtered(lambda s: getattr(s, 'partner_id', False) and s.partner_id.id == partner.id)
        except Exception:
            sellers = product.seller_ids
        if sellers:
            s = sellers[0]
            return float((getattr(s, 'price', 0.0) or 0.0))
        return 0.0

    def action_confirm(self):
        self.ensure_one()
        tl = self.truck_loading_id
        if not tl:
            raise ValidationError(_('Missing Truck Loading.'))
        if self.loaded_at_original < 0 or self.remaining_to_complete < 0:
            raise ValidationError(_('Quantities cannot be negative.'))
        if self.loaded_at_original > (tl.total_quantity or 0.0):
            raise ValidationError(_('Loaded at Original cannot exceed the Truck Loading total quantity.'))
        docket = tl.docket_id
        if not docket:
            raise ValidationError(_('Truck Loading is missing a Docket.'))

        # Re-validate hard cap at confirm time as an extra safety net
        ordered = 0.0
        ticket = False
        try:
            ticket = docket.helpdesk_ticket_id
        except Exception:
            ticket = False
        if ticket and getattr(ticket, 'rmc_quantity', 0.0) and ticket.rmc_quantity > 0:
            ordered = float(ticket.rmc_quantity)
        elif docket and getattr(docket, 'quantity_ordered', 0.0) and docket.quantity_ordered > 0:
            ordered = float(docket.quantity_ordered)
        if ordered:
            total_planned = float(self.loaded_at_original or 0.0) + float(self.remaining_to_complete or 0.0)
            if total_planned > ordered + 1e-6:
                raise ValidationError(_(
                    'Total quantity for breakdown (Loaded %.3f + Remaining %.3f = %.3f) cannot exceed Ordered %.3f.'
                ) % (
                    self.loaded_at_original or 0.0,
                    self.remaining_to_complete or 0.0,
                    total_planned,
                    ordered,
                ))
        product = False
        # Reuse DV helper to derive product if possible
        dv_model = self.env['rmc.delivery_variance']
        fake_dv = dv_model.new({'truck_loading_id': tl.id})
        try:
            product = dv_model._get_product(fake_dv)
        except Exception:
            # fallback: attempt from docket or SO line
            product = getattr(docket, 'product_id', False) or False

        # Create DV if none exists for this TL to record breakdown
        dv = self.env['rmc.delivery_variance'].search([('truck_loading_id', '=', tl.id)], limit=1)
        if not dv:
            dv = self.env['rmc.delivery_variance'].create({
                'truck_loading_id': tl.id,
                'approved': True,
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
                'reconciliation_status': 'approved',
            })

        # Prices from vendor price list
        orig_vendor = docket.subcontractor_id.partner_id if docket.subcontractor_id else False
        new_vendor = self.new_subcontractor_id.partner_id if self.new_subcontractor_id else False
        unit_price_orig = self._get_vendor_price(orig_vendor, product) if product else dv._get_vendor_unit_price()
        unit_price_new = self._get_vendor_price(new_vendor, product) if product else dv._get_vendor_unit_price()

        # Create two vendor bills (Draft)
        created_moves = []
        if self.loaded_at_original:
            bill1 = dv._create_generic_move(
                'in_invoice', orig_vendor, _('Vendor Bill (Plant Breakdown - Original)'),
                self.loaded_at_original, unit_price_orig, product=product, origin_move=False
            )
            created_moves.append(bill1.id)
        if self.remaining_to_complete:
            bill2 = dv._create_generic_move(
                'in_invoice', new_vendor, _('Vendor Bill (Plant Breakdown - New Vendor)'),
                self.remaining_to_complete, unit_price_new, product=product, origin_move=False
            )
            created_moves.append(bill2.id)

        # Keep bills as Draft by default (create_draft True). If false, post them.
        if not self.create_draft:
            moves = self.env['account.move'].browse(created_moves)
            moves.action_post()

        # Update DV breakdown fields and reconciliation
        vals = {
            'variance_type': 'plant_breakdown',
            'breakdown_original_qty': self.loaded_at_original,
            'breakdown_new_subcontractor_id': self.new_subcontractor_id.id,
            'breakdown_new_vendor_id': new_vendor.id if new_vendor else False,
            'breakdown_new_qty': self.remaining_to_complete,
            'reconciliation_status': 'reconciled',
            'reconciliation_date': fields.Datetime.now(),
            'reconciled_by': self.env.user.id,
        }
        if created_moves:
            vals['breakdown_vendor_bill_ids'] = [(6, 0, created_moves)]
        dv.write(vals)

        # Delivery Tracking site shift if provided
        if self.new_site_id:
            track = self.env['rmc.delivery_track'].search([('truck_loading_id', '=', tl.id)], limit=1)
            if track:
                track.write({'new_site_id': self.new_site_id.id})

        # Notes on DV and Ticket
        try:
            msg = _(
                'Plant Breakdown processed: Original %.3f M3 billed to %s, New %.3f M3 billed to %s. Truck Loading: %s.'
            ) % (
                self.loaded_at_original,
                orig_vendor.display_name if orig_vendor else '-',
                self.remaining_to_complete,
                new_vendor.display_name if new_vendor else '-',
                tl.display_name,
            )
            dv.message_post(body=msg)
            ticket = docket.helpdesk_ticket_id
            if ticket:
                ticket.message_post(body=msg)
        except Exception:
            pass

        return {'type': 'ir.actions.act_window_close'}

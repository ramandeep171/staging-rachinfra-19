from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class RmcDeliveryVariance(models.Model):
    _name = 'rmc.delivery_variance'
    _description = 'RMC Delivery Variance'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    approved = fields.Boolean(string='Approved', default=False, tracking=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, tracking=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True, tracking=True)

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    truck_loading_id = fields.Many2one('rmc.truck_loading', string='Truck Loading', required=True,
                                       domain="[('loading_status', '=', 'completed')]")
    docket_id = fields.Many2one('rmc.docket', string='Docket', related='truck_loading_id.docket_id', store=True)

    # Weight Information
    site_weight = fields.Float(string='Site Net Weight (KG)', digits=(10, 2))
    weighbridge_weight = fields.Float(string='Weighbridge Weight (KG)',
                                      related='truck_loading_id.plant_check_id.weighbridge_weight',
                                      readonly=True, store=True)
    net_weight = fields.Float(string='Plant Net Weight (KG)',
                              related='truck_loading_id.plant_check_id.net_weight',
                              readonly=True, store=True)

    # Variance Calculation
    variance_kg = fields.Float(string='Variance (KG)', compute='_compute_variance', store=True)
    variance_percentage = fields.Float(string='Variance %', compute='_compute_variance', store=True)
    tolerance_percentage = fields.Float(string='Tolerance %', default=2.0, readonly=True)

    # Situation-driven minimal fields (Ops entry)
    situation = fields.Selection([
        ('weight_variance', 'Weight Variance (Default)'),
        ('rejected_full', 'Rejected Truck (Full)'),
        ('partial_return', 'Partial Truck Return'),
        ('quality_failure', 'Quality Failure at Site'),
        ('delay_unloading', 'Delay in Unloading'),
        ('site_not_ready', 'Site Not Ready'),
        ('weather_issue', 'Weather Issues'),
        ('doc_error', 'Documentation Error'),
        ('payment_dispute', 'Payment Dispute'),
    ], default='weight_variance', required=True)

    expected_qty = fields.Float(string='Expected Qty (kg/MT)')
    actual_qty = fields.Float(string='Actual Qty (kg/MT)')
    variance_qty = fields.Float(string='Variance Qty', compute='_compute_variance_qty', store=True)
    returned_qty = fields.Float(string='Returned Qty')
    failed_qty = fields.Float(string='Failed Qty')
    returned_value = fields.Monetary(string='Returned Value Override', currency_field='currency_id')
    failed_value = fields.Monetary(string='Failed Value Override', currency_field='currency_id')
    diverted = fields.Boolean(string='Diverted?')
    divert_to_partner_id = fields.Many2one('res.partner', string='Divert Destination Partner')
    diverted_qty = fields.Float(string='Diverted Qty')
    wait_hours = fields.Float(string='Wait Hours')
    rate_per_hour = fields.Monetary(string='Rate per Hour', currency_field='currency_id')
    vendor_liability = fields.Boolean(string='Vendor Liability?')
    doc_error_flag = fields.Boolean(string='Documentation Error')
    payment_dispute_flag = fields.Boolean(string='Payment Dispute')

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id)

    # Status and Reconciliation
    reconciliation_status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('reconciled', 'Reconciled'),
        ('diverted', 'Diverted'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', tracking=True)

    delivery_confirmation = fields.Boolean(string='Delivery Confirmed', readonly=True)
    reconciliation_date = fields.Datetime(string='Reconciliation Date', readonly=True)

    # Financial Integration - Client side
    original_invoice_id = fields.Many2one('account.move', string='Original Invoice', 
                                        related='truck_loading_id.docket_id.invoice_id', 
                                         readonly=True, store=True)
    client_debit_note_id = fields.Many2one('account.move', string='Client Debit Note', readonly=True)
    client_credit_note_id = fields.Many2one('account.move', string='Client Credit Note', readonly=True)

    # Financial Integration - Vendor side
    original_vendor_bill_id = fields.Many2one('account.move', string='Original Vendor Bill', readonly=True,
                                              help='Optional link to the vendor bill created for this delivery')
    # Note: Keep technical names for compatibility; adjust labels to match Odoo semantics
    # vendor_debit_note_id holds in_refund (Vendor Credit Note)
    vendor_debit_note_id = fields.Many2one('account.move', string='Vendor Credit Note', readonly=True,
                                           help='Vendor credit note (in_refund) against the original vendor bill')
    # vendor_credit_note_id holds in_invoice (Vendor Debit Note)
    vendor_credit_note_id = fields.Many2one('account.move', string='Vendor Debit Note', readonly=True,
                                            help='Vendor debit note (in_invoice) linked to the original vendor bill')

    # Diversion documents
    diverted_client_invoice_id = fields.Many2one('account.move', string='Diverted Client Invoice', readonly=True)
    diverted_vendor_invoice_id = fields.Many2one('account.move', string='Diverted Vendor Bill', readonly=True)

    # Additional Information
    notes = fields.Text(string='Notes')
    reconciled_by = fields.Many2one('res.users', string='Reconciled By', readonly=True)

    # Plant Breakdown (Half Load) tracking
    variance_type = fields.Selection([
        ('', 'Standard'),
        ('plant_breakdown', 'Plant Breakdown (Half Load)')
    ], string='Variance Type', default='')
    breakdown_original_qty = fields.Float(string='Original Vendor Qty (M3)')
    breakdown_new_subcontractor_id = fields.Many2one('rmc.subcontractor', string='New Subcontractor')
    breakdown_new_vendor_id = fields.Many2one('res.partner', string='New Vendor Partner', readonly=True)
    breakdown_new_qty = fields.Float(string='New Vendor Qty (M3)')
    breakdown_vendor_bill_ids = fields.Many2many('account.move', string='Breakdown Vendor Bills', readonly=True)

    @api.onchange('diverted')
    def _onchange_diverted_update_status(self):
        """When user toggles Diverted in the UI, reflect it on the status bar.
        Move to 'Diverted' if True (unless already terminal), otherwise revert to
        'Approved' if approved else 'Pending'.
        """
        for rec in self:
            if rec.diverted:
                if rec.reconciliation_status not in ('reconciled', 'failed'):
                    rec.reconciliation_status = 'diverted'
            else:
                if rec.reconciliation_status == 'diverted':
                    rec.reconciliation_status = 'approved' if rec.approved else 'pending'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.delivery_variance') or 'New'
        return super(RmcDeliveryVariance, self).create(vals_list)

   
    @api.depends('site_weight', 'net_weight', 'tolerance_percentage')
    def _compute_variance(self):
        for record in self:
            if record.net_weight and record.net_weight != 0:
                record.variance_kg = record.site_weight - record.net_weight
                record.variance_percentage = abs(record.variance_kg / record.net_weight) * 100
            else:
                record.variance_kg = 0
                record.variance_percentage = 0

    @api.depends('expected_qty', 'actual_qty')
    def _compute_variance_qty(self):
        for rec in self:
            if rec.expected_qty or rec.actual_qty:
                rec.variance_qty = (rec.actual_qty or 0.0) - (rec.expected_qty or 0.0)
            else:
                rec.variance_qty = 0.0

    def action_approve(self):
        self.ensure_one()
        # If pending -> approve. If already approved -> run reconciliation and move to reconciled.
        if self.reconciliation_status == 'pending':
            self.approved = True
            self.approved_by = self.env.user
            self.approved_date = fields.Datetime.now()
            self.reconciliation_status = 'approved'
            # On Approved, set the related docket to 'Delivered'
            try:
                if self.docket_id and self.docket_id.state not in ('cancel', 'delivered'):
                    self.docket_id.sudo().write({'state': 'delivered'})
            except Exception:
                pass
            return
        elif self.reconciliation_status == 'approved':
            # Use the same button to finalize reconciliation
            return self.action_reconcile()
        else:
            raise ValidationError(_('Only pending or approved records can be processed with Approve.'))

    def action_confirm_delivery(self):
        """Confirm delivery (on-site). Move to Approved stage; do NOT create notes yet."""
        self.ensure_one()
        # Basic validations for default path
        if self.situation == 'weight_variance':
            if not self.site_weight or self.site_weight <= 0:
                raise ValidationError(_('Please enter a valid site weight before confirming delivery.'))
        self.delivery_confirmation = True
        # Auto-approve on confirm
        self.approved = True
        self.approved_by = self.env.user
        self.approved_date = fields.Datetime.now()
        self.reconciliation_status = 'approved'

        # When Approved, set the related docket to 'Delivered'
        try:
            if self.docket_id and self.docket_id.state not in ('cancel', 'delivered'):
                self.docket_id.sudo().write({'state': 'delivered'})
        except Exception:
            pass

    def action_reconcile(self):
        """Create dual-party accounting documents and mark as Reconciled. Requires Approved."""
        self.ensure_one()
        if not self.approved or self.reconciliation_status != 'approved':
            raise ValidationError(_('Record must be Approved before reconciliation.'))

        # Route to handlers
        handler_map = {
            'weight_variance': self._handle_weight_variance,
            'rejected_full': self._handle_rejected_full,
            'partial_return': self._handle_partial_return,
            'quality_failure': self._handle_quality_failure,
            'delay_unloading': self._handle_delay_unloading,
            'site_not_ready': self._handle_site_not_ready,
            'weather_issue': self._handle_weather_issue,
            'doc_error': self._handle_doc_error,
            'payment_dispute': self._handle_payment_dispute,
        }
        handler = handler_map.get(self.situation or 'weight_variance', self._handle_weight_variance)
        handler()

        self.reconciliation_status = 'reconciled'
        self.reconciliation_date = fields.Datetime.now()
        self.reconciled_by = self.env.user

        # On Reconciled, set the related ticket stage to 'Solved/Done'
        try:
            ticket = self.truck_loading_id and self.truck_loading_id.docket_id and self.truck_loading_id.docket_id.helpdesk_ticket_id
            if ticket:
                # Find a stage that matches Solved/Done/Closed/Complete
                stage = ticket.env['helpdesk.stage'].search([('name', 'ilike', 'solved')], limit=1)
                if not stage:
                    stage = ticket.env['helpdesk.stage'].search([('name', 'ilike', 'done')], limit=1)
                if not stage:
                    stage = ticket.env['helpdesk.stage'].search([('name', 'ilike', 'closed')], limit=1)
                if not stage:
                    stage = ticket.env['helpdesk.stage'].search([('name', 'ilike', 'complete')], limit=1)
                if stage:
                    ticket.sudo().write({'stage_id': stage.id})
        except Exception:
            pass

    def write(self, vals):
        """Keep reconciliation_status in sync with 'diverted' on backend updates too."""
        res = super(RmcDeliveryVariance, self).write(vals)
        if 'diverted' in vals:
            for rec in self:
                try:
                    if rec.diverted and rec.reconciliation_status not in ('reconciled', 'failed'):
                        super(RmcDeliveryVariance, rec).write({'reconciliation_status': 'diverted'})
                    elif not rec.diverted and rec.reconciliation_status == 'diverted':
                        new_state = 'approved' if rec.approved else 'pending'
                        super(RmcDeliveryVariance, rec).write({'reconciliation_status': new_state})
                except Exception:
                    # Avoid raising from a best-effort sync
                    pass
        return res

    # -----------------------------
    # Situation Handlers
    # -----------------------------
    def _handle_weight_variance(self):
        self.ensure_one()
        # Determine variance using explicit fields if provided, else weight
        delta = self.variance_qty if (self.expected_qty or self.actual_qty) else self.variance_kg
        if not delta:
            return
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        description = _('Weight Variance Adjustment')
        if delta > 0:
            # Excess delivered at site
            self.client_debit_note_id = self._create_client_move('out_invoice', description, delta, unit_price_client).id
            # Ensure we have an Original Vendor Bill; create one automatically if missing
            self._ensure_original_vendor_bill()
            # Create a vendor debit note linked to the original bill
            self.vendor_credit_note_id = self._create_vendor_move('in_invoice', description, delta, unit_price_vendor).id
        elif delta < 0:
            # Shortage at site
            qty = abs(delta)
            self.client_credit_note_id = self._create_client_move('out_refund', description, qty, unit_price_client).id
            self._ensure_original_vendor_bill()
            self.vendor_debit_note_id = self._create_vendor_move('in_refund', description, qty, unit_price_vendor).id

        # Diversion handling for weight variance
        if self.diverted and self.divert_to_partner_id and self.diverted_qty:
            prod = self._get_product()
            self.diverted_client_invoice_id = self._create_generic_move(
                'out_invoice', self.divert_to_partner_id, _('Diversion Invoice (Weight Variance)'),
                self.diverted_qty, unit_price_client, product=prod, origin_move=False
            ).id
            vendor = self._get_vendor_partner()
            diverted_bill = self._create_generic_move(
                'in_invoice', vendor, _('Diversion Vendor Bill (Weight Variance)'),
                self.diverted_qty, unit_price_vendor, product=prod, origin_move=False
            )
            self.diverted_vendor_invoice_id = diverted_bill.id
            if not self.original_vendor_bill_id:
                self.original_vendor_bill_id = diverted_bill.id

    def _handle_rejected_full(self):
        self.ensure_one()
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        total_qty = self.actual_qty or self.net_weight or 0.0
        desc = _('Full Truck Rejection')
        if total_qty:
            self.client_credit_note_id = self._create_client_move('out_refund', desc, total_qty, unit_price_client).id
            self._ensure_original_vendor_bill()
            self.vendor_debit_note_id = self._create_vendor_move('in_refund', desc, total_qty, unit_price_vendor).id
        # Diversion handling for rejected full
        if self.diverted and self.divert_to_partner_id and self.diverted_qty:
            prod = self._get_product()
            self.diverted_client_invoice_id = self._create_generic_move(
                'out_invoice', self.divert_to_partner_id, _('Diversion Invoice (Rejected)'),
                self.diverted_qty, unit_price_client, product=prod, origin_move=False
            ).id
            vendor = self._get_vendor_partner()
            diverted_bill = self._create_generic_move(
                'in_invoice', vendor, _('Diversion Vendor Bill (Rejected)'),
                self.diverted_qty, unit_price_vendor, product=prod, origin_move=False
            )
            self.diverted_vendor_invoice_id = diverted_bill.id
            if not self.original_vendor_bill_id:
                self.original_vendor_bill_id = diverted_bill.id

    def _handle_partial_return(self):
        self.ensure_one()
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        qty = self.returned_qty or 0.0
        desc = _('Partial Return')
        if qty:
            self.client_credit_note_id = self._create_client_move('out_refund', desc, qty, unit_price_client).id
            self._ensure_original_vendor_bill()
            self.vendor_debit_note_id = self._create_vendor_move('in_refund', desc, qty, unit_price_vendor).id
        if self.diverted and self.divert_to_partner_id and self.diverted_qty:
            prod = self._get_product()
            self.diverted_client_invoice_id = self._create_generic_move('out_invoice', self.divert_to_partner_id, _('Diversion Invoice'), self.diverted_qty, unit_price_client, product=prod, origin_move=False).id
            vendor = self._get_vendor_partner()
            diverted_bill = self._create_generic_move('in_invoice', vendor, _('Diversion Vendor Bill'), self.diverted_qty, unit_price_vendor, product=prod, origin_move=False)
            self.diverted_vendor_invoice_id = diverted_bill.id
            if not self.original_vendor_bill_id:
                self.original_vendor_bill_id = diverted_bill.id

    def _handle_quality_failure(self):
        self.ensure_one()
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        qty = self.failed_qty or 0.0
        desc = _('Quality Failure')
        if qty:
            amount_override_client = self.failed_value if self.failed_value else False
            amount_override_vendor = self.failed_value if self.failed_value else False
            self.client_credit_note_id = self._create_client_move('out_refund', desc, qty, unit_price_client, amount_override=amount_override_client).id
            self._ensure_original_vendor_bill()
            self.vendor_debit_note_id = self._create_vendor_move('in_refund', desc, qty, unit_price_vendor, amount_override=amount_override_vendor).id
        if self.diverted and self.divert_to_partner_id and self.diverted_qty:
            prod = self._get_product()
            self.diverted_client_invoice_id = self._create_generic_move('out_invoice', self.divert_to_partner_id, _('Diversion Invoice (Quality)'), self.diverted_qty, unit_price_client, product=prod, origin_move=False).id
            vendor = self._get_vendor_partner()
            diverted_bill = self._create_generic_move('in_invoice', vendor, _('Diversion Vendor Bill (Quality)'), self.diverted_qty, unit_price_vendor, product=prod, origin_move=False)
            self.diverted_vendor_invoice_id = diverted_bill.id
            if not self.original_vendor_bill_id:
                self.original_vendor_bill_id = diverted_bill.id

    def _handle_delay_unloading(self):
        self.ensure_one()
        penalty = (self.wait_hours or 0.0) * (self.rate_per_hour or 0.0)
        if penalty > 0:
            # Client debit: demurrage
            self.client_debit_note_id = self._create_client_move('out_invoice', _('Demurrage (Unloading Delay)'), 1.0, penalty, is_service=True).id
            # Vendor debit only if liability flagged
            if self.vendor_liability:
                self._ensure_original_vendor_bill()
                self.vendor_debit_note_id = self._create_vendor_move('in_refund', _('Penalty (Unloading Delay)'), 1.0, penalty, is_service=True).id

    def _handle_site_not_ready(self):
        self.ensure_one()
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        qty = self.actual_qty or self.net_weight or 0.0
        desc = _('Site Not Ready - Full Return')
        if qty:
            self.client_credit_note_id = self._create_client_move('out_refund', desc, qty, unit_price_client).id
            self._ensure_original_vendor_bill()
            self.vendor_debit_note_id = self._create_vendor_move('in_refund', desc, qty, unit_price_vendor).id
        if self.diverted and self.divert_to_partner_id and self.diverted_qty:
            prod = self._get_product()
            self.diverted_client_invoice_id = self._create_generic_move('out_invoice', self.divert_to_partner_id, _('Diversion Invoice (Site Not Ready)'), self.diverted_qty, unit_price_client, product=prod, origin_move=False).id
            vendor = self._get_vendor_partner()
            diverted_bill = self._create_generic_move('in_invoice', vendor, _('Diversion Vendor Bill (Site Not Ready)'), self.diverted_qty, unit_price_vendor, product=prod, origin_move=False)
            self.diverted_vendor_invoice_id = diverted_bill.id
            if not self.original_vendor_bill_id:
                self.original_vendor_bill_id = diverted_bill.id

    def _handle_weather_issue(self):
        self.ensure_one()
        unit_price_client = self._get_client_unit_price()
        unit_price_vendor = self._get_vendor_unit_price()
        qty = self.failed_qty or self.returned_qty or 0.0
        if qty:
            self.client_credit_note_id = self._create_client_move('out_refund', _('Weather Damage'), qty, unit_price_client).id
            if self.vendor_liability:
                self._ensure_original_vendor_bill()
                self.vendor_debit_note_id = self._create_vendor_move('in_refund', _('Weather Damage - Vendor Liability'), qty, unit_price_vendor).id

    def _handle_doc_error(self):
        # No automatic debit/credit; just log
        self.message_post(body=_('Documentation error recorded. No accounting document created automatically.'))

    def _handle_payment_dispute(self):
        self.message_post(body=_('Payment dispute recorded. No automatic accounting; follow escalation workflow.'))

    # -----------------------------
    # Move creators and helpers
    # -----------------------------
    def _get_client_unit_price(self):
        inv = self.original_invoice_id
        if inv and inv.invoice_line_ids:
            qty_sum = sum(l.quantity for l in inv.invoice_line_ids if l.quantity)
            amt_sum = sum(l.price_subtotal for l in inv.invoice_line_ids)
            return (amt_sum / qty_sum) if qty_sum else 0.0
        return 0.0

    def _get_vendor_unit_price(self):
        bill = self.original_vendor_bill_id
        if bill and bill.invoice_line_ids:
            qty_sum = sum(l.quantity for l in bill.invoice_line_ids if l.quantity)
            amt_sum = sum(l.price_subtotal for l in bill.invoice_line_ids)
            return (amt_sum / qty_sum) if qty_sum else 0.0
        # Fallback to client unit price if vendor bill not linked
        return self._get_client_unit_price()

    def _get_client_partner(self):
        if self.original_invoice_id:
            return self.original_invoice_id.partner_id
        so = self.truck_loading_id and self.truck_loading_id.docket_id and self.truck_loading_id.docket_id.sale_order_id
        return so.partner_id if so else False

    def _get_vendor_partner(self):
        docket = self.truck_loading_id.docket_id if self.truck_loading_id else False
        return docket.subcontractor_id.partner_id if docket and docket.subcontractor_id else False

    def _get_product(self):
        docket = self.truck_loading_id and self.truck_loading_id.docket_id
        if not docket:
            return False
        # 1) Use docket.product_id when available
        if getattr(docket, 'product_id', False):
            return docket.product_id
        # 2) Derive from Sale Order: prefer a line marked as RMC/Concrete
        so = getattr(docket, 'sale_order_id', False)
        if so and so.order_line:
            rmc_lines = so.order_line.filtered(lambda l: l.product_id and (
                getattr(l.product_id.categ_id, 'is_rmc_category', False)
                or ('RMC' in (l.product_id.categ_id.name or '').upper())
                or ('CONCRETE' in (l.product_id.categ_id.name or '').upper())
                or getattr(l.product_id.product_tmpl_id, 'is_rmc_product', False)
            ))
            sol = rmc_lines[:1] or so.order_line[:1]
            sol = sol and sol[0] or False
            if sol and sol.product_id:
                return sol.product_id
        return False

    def _ensure_original_vendor_bill(self):
        """Ensure original_vendor_bill_id is set. If missing, create a minimal vendor bill
        based on the delivery context (partner/product/qty/price) and set it.
        This avoids blocking positive variance when a vendor bill hasn't been created upstream.
        """
        if self.original_vendor_bill_id:
            return
        partner = self._get_vendor_partner()
        if not partner:
            raise ValidationError(_('Missing vendor partner to create the Original Vendor Bill.'))
        product = self._get_product()
        base_qty = self.actual_qty or self.net_weight or 0.0
        if base_qty <= 0.0:
            # fallback to site weight if others unavailable
            base_qty = self.site_weight or 0.0
        if base_qty <= 0.0:
            raise ValidationError(_('Cannot determine a base quantity to create the Original Vendor Bill.'))
        unit_price_vendor = self._get_vendor_unit_price() or 0.0
        # If vendor price is zero, fallback to client unit price
        if unit_price_vendor == 0.0:
            unit_price_vendor = self._get_client_unit_price() or 0.0
        desc = _('Original Vendor Bill (Auto)')
        bill = self._create_generic_move('in_invoice', partner, desc, base_qty, unit_price_vendor, product=product, origin_move=False)
        self.original_vendor_bill_id = bill.id

    def _create_client_move(self, move_type, description, qty, unit_price, amount_override=False, is_service=False, link_origin=True):
        partner = self._get_client_partner()
        # For client notes, prefer using the same product as the original client invoice
        if is_service:
            product = False
        else:
            product = False
            inv = self.original_invoice_id
            if inv and inv.invoice_line_ids:
                product = inv.invoice_line_ids[0].product_id
            if not product:
                product = self._get_product()
        origin = self.original_invoice_id if link_origin else False
        return self._create_generic_move(move_type, partner, description, qty, unit_price, amount_override, product, origin_move=origin)

    def _create_vendor_move(self, move_type, description, qty, unit_price, amount_override=False, is_service=False, link_origin=True):
        partner = self._get_vendor_partner()
        # Always attempt to set a concrete product for vendor documents, even for service-type adjustments.
        product = False
        bill = self.original_vendor_bill_id
        if bill and bill.invoice_line_ids and bill.invoice_line_ids[0].product_id:
            product = bill.invoice_line_ids[0].product_id
        if not product:
            product = self._get_product()
        origin = self.original_vendor_bill_id if link_origin else False
        move = self._create_generic_move(move_type, partner, description, qty, unit_price, amount_override, product, origin_move=origin)
        # If a new vendor bill is created and original is not set yet, set it immediately
        if move_type == 'in_invoice' and not self.original_vendor_bill_id:
            self.original_vendor_bill_id = move.id
        return move

    def _create_generic_move(self, move_type, partner, description, qty, unit_price, amount_override=False, product=False, origin_move=False):
        if not partner:
            raise UserError(_('Missing partner to create accounting document.'))
        # Prefer the specific origin move (client/vendor) for currency, taxes, and journal
        currency = (origin_move.currency_id if origin_move else (
            self.original_invoice_id.currency_id if self.original_invoice_id else self.env.company.currency_id
        ))
        account = False
        tax_ids = []
        source_move_for_taxes = origin_move or self.original_invoice_id
        if source_move_for_taxes and source_move_for_taxes.invoice_line_ids:
            tax_ids = source_move_for_taxes.invoice_line_ids[0].tax_ids.ids
        # Gather RMC metadata from current variance context
        docket = self.docket_id
        tl = self.truck_loading_id
        # Prefer plant check on truck loading; else latest completed on docket
        pc = tl.plant_check_id if tl and tl.plant_check_id else False
        if not pc and docket:
            pc = self.env['rmc.plant_check'].search([
                ('docket_id', '=', docket.id)
            ], limit=1, order='check_date desc')
        # Helper formatters
        def _fmt_dt(dt):
            return fields.Datetime.to_string(dt) if dt else False
        def _to_date(dt):
            if not dt:
                return False
            # accept both date and datetime
            try:
                return fields.Date.to_date(dt)
            except Exception:
                return dt.date() if hasattr(dt, 'date') else dt
        line_vals = {
            'name': description,
            'quantity': qty or 1.0,
            'price_unit': (amount_override if amount_override else unit_price) if (amount_override and not product) else unit_price,
        }
        # Account selection: if product provided, let Odoo compute; else pick based on move_type and partner properties
        if not product:
            if move_type in ('out_invoice', 'out_refund') and getattr(partner, 'property_account_income_id', False):
                account = partner.property_account_income_id.id
            elif move_type in ('in_invoice', 'in_refund') and getattr(partner, 'property_account_expense_id', False):
                account = partner.property_account_expense_id.id
            elif self.original_invoice_id and self.original_invoice_id.invoice_line_ids:
                account = self.original_invoice_id.invoice_line_ids[0].account_id.id
            if account:
                line_vals['account_id'] = account
        if tax_ids:
            line_vals['tax_ids'] = [(6, 0, tax_ids)]
        if product:
            line_vals['product_id'] = product.id
        # Choose journal by move_type if not inherited from original
        journal = False
        source_move_for_journal = origin_move or self.original_invoice_id
        if source_move_for_journal and source_move_for_journal.journal_id:
            journal = source_move_for_journal.journal_id.id
        else:
            jtype = 'sale' if move_type in ('out_invoice', 'out_refund') else 'purchase'
            journal = self.env['account.journal'].search([('type', '=', jtype)], limit=1).id
        move_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_origin': (origin_move.name if origin_move else (
                self.original_invoice_id.name if self.original_invoice_id else self.name
            )),
            'ref': f'{description} - {self.name}',
            'invoice_date': fields.Date.today(),
            'journal_id': journal,
            'currency_id': currency.id,
            'line_ids': [(0, 0, line_vals)],
        }
        # Inject RMC details onto the move so vendor/client documents carry operational context
        if docket:
            move_vals['docket_id'] = docket.id
            # Delivery challan number mapped from docket number by default
            if getattr(docket, 'docket_number', False):
                move_vals['delivery_challan_number'] = docket.docket_number
        if pc:
            move_vals['plant_check_id'] = pc.id
        # Dates and times
        if pc and getattr(pc, 'completed_date', False):
            move_vals['delivery_date'] = _to_date(pc.completed_date)
            move_vals['delivery_time'] = _fmt_dt(pc.completed_date)
        elif docket and getattr(docket, 'docket_date', False):
            move_vals['delivery_date'] = _to_date(docket.docket_date)
        # Vehicle and transporter
        if tl and tl.vehicle_id and getattr(tl.vehicle_id, 'license_plate', False):
            move_vals['vehicle_number'] = tl.vehicle_id.license_plate
        if docket and docket.subcontractor_id and docket.subcontractor_id.name:
            move_vals['transporter_name'] = docket.subcontractor_id.name
        # Driver info
        drv_name = (tl and tl.driver_name) or (docket and docket.driver_name)
        if drv_name:
            move_vals['driver_name'] = drv_name
        if tl and tl.driver_mobile:
            move_vals['driver_mobile'] = tl.driver_mobile
        # Batch and batching time
        batch_no = False
        if pc and getattr(pc, 'batch_ids', False) and pc.batch_ids:
            # Prefer explicit batch_number if present, else name
            first_batch = pc.batch_ids[:1]
            if first_batch and first_batch[0].batch_number:
                batch_no = first_batch[0].batch_number
            elif first_batch and first_batch[0].name:
                batch_no = first_batch[0].name
        if not batch_no and docket and docket.docket_batch_ids:
            batch_no = docket.docket_batch_ids[:1].batch_code
        if batch_no:
            move_vals['batch_number'] = batch_no
        if docket and docket.batching_time:
            move_vals['batching_time'] = _fmt_dt(docket.batching_time)
        # Quality
        if pc and getattr(pc, 'quality_slump', False):
            move_vals['slump_at_site'] = pc.quality_slump
        # Receiver contact (fallback to SO partner phone/mobile)
        so = docket.sale_order_id if docket else False
        # Pump propagation onto the move when available
        wo = docket.workorder_id if docket else False
        if wo and getattr(wo, 'pump_required', False):
            # include pump provider and pump code in ref to surface on invoice/bill
            prov = getattr(wo.pump_provider_id, 'name', False)
            pump_code = getattr(wo.pump_id, 'pump_code', False)
            extra = []
            if prov:
                extra.append(f"Pump Provider: {prov}")
            if pump_code:
                extra.append(f"Pump: {pump_code}")
            if extra:
                move_vals['ref'] = f"{move_vals.get('ref','')} | {' | '.join(extra)}".strip()
        if so and so.partner_id:
            recv_mob = getattr(so.partner_id, 'mobile', False) or getattr(so.partner_id, 'phone', False)
            if recv_mob:
                move_vals['receiver_mobile'] = recv_mob
        # Link to original invoices/bills when applicable
        if origin_move:
            if move_type in ('out_refund', 'in_refund'):
                # Credit note / vendor debit note against original
                move_vals['reversed_entry_id'] = origin_move.id
            elif move_type in ('out_invoice', 'in_invoice') and origin_move.partner_id.id == partner.id:
                # Mark as debit note linked to original (only if same partner)
                move_vals['debit_origin_id'] = origin_move.id
        move = self.env['account.move'].create(move_vals)
        # Set pump fields explicitly on the move for consistent visibility
        try:
            if docket and docket.workorder_id and getattr(docket.workorder_id, 'pump_required', False):
                wo = docket.workorder_id
                move.write({
                    'pump_required': True,
                    'pump_provider_name': getattr(wo.pump_provider_id, 'name', False) or False,
                    'pump_code': getattr(wo.pump_id, 'pump_code', False) or False,
                })
        except Exception:
            pass
        return move

    @api.constrains('site_weight')
    def _check_site_weight(self):
        for record in self:
            # Skip validation during initial creation if site_weight is 0.0
            if record.site_weight == 0.0 and not record.delivery_confirmation:
                continue

            # Only require positive weight when delivery is being confirmed or when weight is explicitly set
            if record.delivery_confirmation and record.site_weight <= 0:
                raise ValidationError('Site weight must be greater than zero before confirming delivery.')
            elif record.site_weight < 0:
                raise ValidationError('Site weight cannot be negative.')

    @api.constrains('truck_loading_id')
    def _check_unique_truck_loading(self):
        for record in self:
            if record.truck_loading_id:
                existing = self.search([
                    ('truck_loading_id', '=', record.truck_loading_id.id),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError('A delivery variance already exists for this truck loading.')

    def action_view_debit_note(self):
        """Backward-compat: open client debit note if present"""
        move = self.client_debit_note_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id if move else False,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_credit_note(self):
        """Backward-compat: open client credit note if present"""
        move = self.client_credit_note_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id if move else False,
            'view_mode': 'form',
            'target': 'current',
        }

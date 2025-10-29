# -*- coding: utf-8 -*-
"""
Diesel Log - Track fuel consumption and efficiency
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcDieselLog(models.Model):
    _name = 'rmc.diesel.log'
    _description = 'RMC Diesel Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='restrict',
        tracking=True
    )
    contractor_id = fields.Many2one(
        related='agreement_id.contractor_id',
        string='Contractor',
        store=True
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        help='Optional: link to fleet vehicle'
    )
    driver_id = fields.Many2one(
        'hr.employee',
        string='Driver',
        help='Driver associated with this diesel log entry'
    )
    
    # Diesel Measurements
    opening_ltr = fields.Float(
        string='Opening Stock (Liters)',
        digits='Product Unit of Measure',
        required=True
    )
    issued_ltr = fields.Float(
        string='Issued (Liters)',
        digits='Product Unit of Measure',
        required=True
    )
    closing_ltr = fields.Float(
        string='Closing Stock (Liters)',
        digits='Product Unit of Measure',
        required=True
    )
    
    # Work Done
    work_done_m3 = fields.Float(
        string='Work Done (m³)',
        digits='Product Unit of Measure',
        help='Concrete delivered in cubic meters'
    )
    work_done_km = fields.Float(
        string='Distance Traveled (km)',
        digits='Product Unit of Measure',
        help='Kilometers traveled'
    )
    
    # Efficiency
    diesel_efficiency = fields.Float(
        string='Diesel Efficiency',
        compute='_compute_efficiency',
        store=True,
        digits=(5, 2),
        help='m³/liter or km/liter depending on work type'
    )
    efficiency_unit = fields.Char(
        string='Efficiency Unit',
        compute='_compute_efficiency',
        store=True
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_agreement', 'Pending Agreement Signature'),
        ('validated', 'Validated')
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Additional
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Generate sequence and check agreement signature"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'rmc.diesel.log'
                ) or _('New')

        records = super(RmcDieselLog, self).create(vals_list)
        for record in records:
            record._check_agreement_signature()
            record._validate_agreement_assignments()
            record._default_assignments_from_agreement()
        return records

    def write(self, vals):
        """Check agreement signature on write"""
        res = super(RmcDieselLog, self).write(vals)
        if 'state' not in vals:  # Don't check when updating state
            self._check_agreement_signature()
        if {'agreement_id', 'vehicle_id', 'driver_id'} & set(vals.keys()):
            self._validate_agreement_assignments()
        if 'agreement_id' in vals and not vals.get('vehicle_id'):
            self._default_assignments_from_agreement()
        return res

    @api.onchange('agreement_id')
    def _onchange_agreement_id(self):
        for record in self:
            if not record.agreement_id:
                record.vehicle_id = False
                record.driver_id = False
                continue
            record._default_assignments_from_agreement()

    def _check_agreement_signature(self):
        """
        If agreement is not signed, set state to pending_agreement
        and create activity
        """
        for record in self:
            if not record.agreement_id.is_signed():
                record.state = 'pending_agreement'
                record.message_post(
                    body=_('Diesel log is pending because agreement is not signed yet.'),
                    subject=_('Pending Agreement Signature')
                )
                # Create activity for agreement owner
                record.agreement_id.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('Sign agreement to validate diesel logs'),
                    note=_('Diesel log %s is waiting for agreement signature.') % record.name
                )

    def _validate_agreement_assignments(self):
        """
        Ensure selected vehicle/driver belong to the agreement configuration
        """
        for record in self:
            if record.agreement_id:
                if record.vehicle_id and record.vehicle_id not in record.agreement_id.vehicle_ids:
                    raise ValidationError(
                        _('Vehicle %s is not assigned to agreement %s.') %
                        (record.vehicle_id.display_name, record.agreement_id.name)
                    )
                if record.driver_id and record.driver_id not in record.agreement_id.driver_ids:
                    raise ValidationError(
                        _('Driver %s is not assigned to agreement %s.') %
                        (record.driver_id.name, record.agreement_id.name)
                    )

    def _default_assignments_from_agreement(self):
        for record in self:
            if not record.agreement_id:
                continue
            if not record.vehicle_id and record.agreement_id.vehicle_ids:
                record.vehicle_id = record.agreement_id.vehicle_ids[:1]
            if not record.driver_id and record.agreement_id.driver_ids:
                record.driver_id = record.agreement_id.driver_ids[:1]

    @api.depends('issued_ltr', 'work_done_m3', 'work_done_km')
    def _compute_efficiency(self):
        """Calculate diesel efficiency based on work done"""
        for record in self:
            if record.issued_ltr > 0:
                if record.work_done_m3 > 0:
                    record.diesel_efficiency = record.work_done_m3 / record.issued_ltr
                    record.efficiency_unit = 'm³/liter'
                elif record.work_done_km > 0:
                    record.diesel_efficiency = record.work_done_km / record.issued_ltr
                    record.efficiency_unit = 'km/liter'
                else:
                    record.diesel_efficiency = 0.0
                    record.efficiency_unit = ''
            else:
                record.diesel_efficiency = 0.0
                record.efficiency_unit = ''

    @api.constrains('opening_ltr', 'issued_ltr', 'closing_ltr')
    def _check_positive_liters(self):
        """Ensure non-negative liter values"""
        for record in self:
            if record.opening_ltr < 0 or record.issued_ltr < 0 or record.closing_ltr < 0:
                raise ValidationError(_('Liter values cannot be negative.'))

    @api.constrains('work_done_m3', 'work_done_km')
    def _check_positive_work(self):
        """Ensure non-negative work values"""
        for record in self:
            if record.work_done_m3 < 0 or record.work_done_km < 0:
                raise ValidationError(_('Work done values cannot be negative.'))

    def action_validate(self):
        """Validate diesel log"""
        for record in self:
            if not record.agreement_id.is_signed():
                raise ValidationError(
                    _('Cannot validate: Agreement %s is not signed yet.') % 
                    record.agreement_id.name
                )
            record.state = 'validated'
            record.message_post(body=_('Diesel log validated'))

    def action_reset_to_draft(self):
        """Reset to draft"""
        self.write({'state': 'draft'})

    _sql_constraints = [
        (
            'rmc_diesel_closing_ltr_positive',
            'CHECK(closing_ltr >= 0)',
            'Closing liters must be non-negative.'
        ),
        (
            'rmc_diesel_issued_ltr_positive',
            'CHECK(issued_ltr >= 0)',
            'Issued liters must be non-negative.'
        ),
    ]

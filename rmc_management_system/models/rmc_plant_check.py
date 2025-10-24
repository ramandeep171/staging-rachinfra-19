from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RmcPlantCheck(models.Model):
    _name = 'rmc.plant_check'
    _description = 'RMC Plant Check'
    _order = 'check_date desc'

    name = fields.Char(string='Plant Check Reference', required=True, copy=False, readonly=True, default='New')
    truck_loading_id = fields.Many2one('rmc.truck_loading', string='Truck Loading', required=True)
    docket_id = fields.Many2one('rmc.docket', string='Docket', related='truck_loading_id.docket_id', store=True)

    # Weighbridge Information
    weighbridge_weight = fields.Float(string='Weighbridge Weight (KG)', digits=(10, 2))
    initial_weight = fields.Float(string='Initial Weight (KG)', digits=(10, 2))
    net_weight = fields.Float(string='Net Weight (KG)', compute='_compute_net_weight', store=True)

    # Quality Check Information
    quality_slump = fields.Float(string='Slump (mm)', digits=(5, 1))
    quality_temperature = fields.Float(string='Temperature (°C)', digits=(4, 1))
    quality_remarks = fields.Text(string='Quality Remarks')

    # Status and Timing
    check_status = fields.Selection([
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Check Status', default='in_progress', required=True)

    check_date = fields.Datetime(string='Check Date', default=fields.Datetime.now, required=True)
    completed_date = fields.Datetime(string='Completed Date')
    checked_by = fields.Many2one('res.users', string='Checked By', default=lambda self: self.env.user)

    # Relations
    batch_ids = fields.Many2many('rmc.batch', string='Batches', compute='_compute_batch_ids', store=True)
    quality_check_ids = fields.Many2many('rmc.quality.check', string='Quality Checks', compute='_compute_quality_check_ids', store=True)

    @api.depends('weighbridge_weight', 'initial_weight')
    def _compute_net_weight(self):
        for record in self:
            record.net_weight = record.weighbridge_weight - record.initial_weight

    @api.depends('truck_loading_id.batch_ids')
    def _compute_batch_ids(self):
        for record in self:
            if record.truck_loading_id:
                record.batch_ids = [(6, 0, record.truck_loading_id.batch_ids.ids)]
            else:
                record.batch_ids = [(5, 0, 0)]

    @api.depends('batch_ids')
    def _compute_quality_check_ids(self):
        for record in self:
            quality_checks = self.env['rmc.quality.check'].search([
                ('batch_id', 'in', record.batch_ids.ids)
            ])
            record.quality_check_ids = quality_checks

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.plant_check') or 'New'
        return super().create(vals_list)

    def action_complete_check(self):
        """Complete the plant check and create delivery variance"""
        self.ensure_one()
        if self.check_status != 'in_progress':
            raise ValidationError(_("Plant check is already completed or failed."))

        # Update status and completion date
        self.write({
            'check_status': 'completed',
            'completed_date': fields.Datetime.now(),
        })

        # Create delivery variance record
        self._create_delivery_variance()

        # Move the related docket to 'Dispatched' when plant check completes
        try:
            if self.docket_id and self.docket_id.state not in ('cancel', 'delivered'):
                self.docket_id.sudo().write({'state': 'dispatched'})
        except Exception:
            # Non-blocking
            pass

        # Trigger invoice generation for the related docket
        if self.docket_id:
            self.docket_id.action_generate_invoice()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plant Check Completed'),
                'message': _('Plant check has been completed successfully, delivery variance created, and invoice generation has been triggered.'),
                'type': 'success',
            }
        }

    def action_fail_check(self):
        """Mark the plant check as failed"""
        self.ensure_one()
        self.write({
            'check_status': 'failed',
            'completed_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plant Check Failed'),
                'message': _('Plant check has been marked as failed.'),
                'type': 'warning',
            }
        }

    def _create_delivery_variance(self):
        """Create delivery variance record for this plant check"""
        self.ensure_one()

        # Check if delivery variance already exists for this truck loading
        existing_variance = self.env['rmc.delivery_variance'].search([
            ('truck_loading_id', '=', self.truck_loading_id.id)
        ], limit=1)

        if existing_variance:
            # Update existing variance if needed
            return existing_variance

        # Create new delivery variance
        variance_vals = {
            'truck_loading_id': self.truck_loading_id.id,
            'site_weight': 0.0,  # To be filled by site personnel
            'reconciliation_status': 'pending',
            'delivery_confirmation': False,
        }

        delivery_variance = self.env['rmc.delivery_variance'].create(variance_vals)

        # Link the delivery variance to the truck loading
        self.truck_loading_id.write({
            'delivery_variance_id': delivery_variance.id
        })

        return delivery_variance

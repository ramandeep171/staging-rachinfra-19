from odoo import models, fields, api, _


class RmcTruckLoading(models.Model):
    _name = 'rmc.truck_loading'
    _description = 'RMC Truck Loading'
    _order = 'loading_date desc'

    name = fields.Char(string='Loading Reference', required=True, copy=False, readonly=True, default='New')
    docket_id = fields.Many2one('rmc.docket', string='Docket', required=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=False)
    
    # Subcontractor Transport Integration
    subcontractor_transport_id = fields.Many2one('rmc.subcontractor.transport', string='Subcontractor Transport',
                                                domain="[('subcontractor_id', '=', subcontractor_id)]")
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor', 
                                      related='docket_id.subcontractor_id', store=True)
    
    # Driver Information (auto-populated from subcontractor transport)
    driver_name = fields.Char(string='Driver Name', related='subcontractor_transport_id.driver_name', readonly=True)
    driver_mobile = fields.Char(string='Driver Mobile', related='subcontractor_transport_id.driver_mobile', readonly=True)
    transport_code = fields.Char(string='Transport Code', related='subcontractor_transport_id.transport_code', readonly=True)

    # Loading Information
    loading_date = fields.Datetime(string='Loading Date', default=fields.Datetime.now, required=True)
    loading_start_time = fields.Datetime(string='Loading Start Time')
    loading_end_time = fields.Datetime(string='Loading End Time')
    loading_duration = fields.Float(string='Loading Duration (Hours)', compute='_compute_loading_duration', store=True)

    # Material Information
    batch_ids = fields.Many2many('rmc.batch', string='Batches Loaded')
    total_quantity = fields.Float(string='Total Quantity (M3)', compute='_compute_total_quantity', store=True)

    # Status
    loading_status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Loading Status', default='scheduled', required=True)

    # Relations
    plant_check_id = fields.Many2one('rmc.plant_check', string='Plant Check')
    delivery_variance_id = fields.Many2one('rmc.delivery_variance', string='Delivery Variance', readonly=True)
    loaded_by = fields.Many2one('res.users', string='Loaded By', default=lambda self: self.env.user)

    @api.depends('loading_start_time', 'loading_end_time')
    def _compute_loading_duration(self):
        for record in self:
            if record.loading_start_time and record.loading_end_time:
                duration = record.loading_end_time - record.loading_start_time
                record.loading_duration = duration.total_seconds() / 3600
            else:
                record.loading_duration = 0.0

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Auto-populate subcontractor transport when vehicle is selected"""
        if self.vehicle_id and self.subcontractor_id:
            transport = self.env['rmc.subcontractor.transport'].search([
                ('subcontractor_id', '=', self.subcontractor_id.id),
                ('fleet_vehicle_id', '=', self.vehicle_id.id)
            ], limit=1)
            if transport:
                self.subcontractor_transport_id = transport.id

    @api.onchange('subcontractor_transport_id')
    def _onchange_subcontractor_transport_id(self):
        """When a transport is selected, auto-populate vehicle if available."""
        if self.subcontractor_transport_id and self.subcontractor_transport_id.fleet_vehicle_id:
            self.vehicle_id = self.subcontractor_transport_id.fleet_vehicle_id.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.truck_loading') or 'New'
        records = super().create(vals_list)
        # Enforce that at least one of vehicle or transport must be set
        for rec in records:
            if not rec.vehicle_id and not rec.subcontractor_transport_id:
                # Try to populate from docket transport
                try:
                    transport = rec.docket_id and rec.docket_id.subcontractor_transport_id
                    if transport and transport.fleet_vehicle_id:
                        rec.subcontractor_transport_id = transport.id
                        rec.vehicle_id = transport.fleet_vehicle_id.id
                except Exception:
                    pass
        return records

    def action_start_loading(self):
        """Start the truck loading process"""
        self.ensure_one()
        self.write({
            'loading_status': 'in_progress',
            'loading_start_time': fields.Datetime.now(),
        })

    def action_complete_loading(self):
        """Complete the truck loading and auto-create plant check"""
        self.ensure_one()
        self.write({
            'loading_status': 'completed',
            'loading_end_time': fields.Datetime.now(),
        })

        # Auto-create plant check
        plant_check_vals = {
            'truck_loading_id': self.id,
            'docket_id': self.docket_id.id,
            'initial_weight': 0.0,  # Will be set during plant check
        }
        plant_check = self.env['rmc.plant_check'].create(plant_check_vals)
        self.plant_check_id = plant_check.id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Loading Completed'),
                'message': _('Truck loading completed and plant check has been initiated.'),
                'type': 'success',
            }
        }

    def action_open_breakdown_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plant Breakdown (Half Load)'),
            'res_model': 'rmc.breakdown.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_truck_loading_id': self.id,
            },
        }

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Auto-assign subcontractor transport when vehicle is selected"""
        if self.vehicle_id and self.subcontractor_id:
            # Find the transport record that matches this vehicle and subcontractor
            transport = self.env['rmc.subcontractor.transport'].search([
                ('subcontractor_id', '=', self.subcontractor_id.id),
                ('fleet_vehicle_id', '=', self.vehicle_id.id)
            ], limit=1)
            if transport:
                self.subcontractor_transport_id = transport.id

    @api.depends('batch_ids', 'batch_ids.quantity_produced', 'batch_ids.quantity_ordered')
    def _compute_total_quantity(self):
        """Compute total loaded quantity (M3) from associated batches.

        Prefer actual produced quantity; if unavailable, fall back to ordered quantity.
        """
        for record in self:
            produced_sum = sum((b.quantity_produced or 0.0) for b in record.batch_ids)
            if produced_sum:
                record.total_quantity = produced_sum
            else:
                record.total_quantity = sum((b.quantity_ordered or 0.0) for b in record.batch_ids)

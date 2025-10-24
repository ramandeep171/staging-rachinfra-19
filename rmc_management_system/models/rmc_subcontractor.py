from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RmcSubcontractor(models.Model):
    _name = 'rmc.subcontractor'
    _description = 'RMC Subcontractor'
    _order = 'name'

    name = fields.Char(string='Subcontractor Name', required=True)
    subcontractor_code = fields.Char(string='Subcontractor Code', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    
    # Service Capabilities
    has_plant = fields.Boolean(string='Has Plant Services', default=False)
    has_transport = fields.Boolean(string='Has Transport Services', default=False)
    has_pump = fields.Boolean(string='Has Pump Services', default=False)
    
    # Plant Details (Legacy - for backward compatibility)
    plant_code = fields.Char(string='Plant Code')
    plant_location = fields.Char(string='Plant Location')
    plant_coordinates = fields.Char(string='Plant Coordinates')
    plant_capacity = fields.Float(string='Plant Capacity (M3/batch)')
    
    # Related Records
    plant_ids = fields.One2many('rmc.subcontractor.plant', 'subcontractor_id', string='Plants')
    transport_ids = fields.One2many('rmc.subcontractor.transport', 'subcontractor_id', string='Transports')
    pump_ids = fields.One2many('rmc.subcontractor.pump', 'subcontractor_id', string='Pumps')
    
    # Capabilities
    concrete_grades = fields.Selection([
        ('basic', 'Basic Grades (M7.5-M20)'),
        ('standard', 'Standard Grades (M7.5-M30)'),
        ('high', 'High Grades (M7.5-M40)'),
        ('all', 'All Grades'),
    ], string='Concrete Grades', default='standard')

    # Service Area
    service_radius = fields.Float(string='Service Radius (Km)', default=50)

    # Performance Metrics
    acceptance_rate = fields.Float(string='Acceptance Rate %', compute='_compute_performance_metrics')
    average_response_time = fields.Float(string='Avg Response Time (Hours)', compute='_compute_performance_metrics')
    quality_score = fields.Float(string='Quality Score', compute='_compute_performance_metrics')

    # Equipment (Legacy)
    transit_mixers = fields.Integer(string='Transit Mixers')
    concrete_pumps = fields.Integer(string='Concrete Pumps')

    # Contact Details
    contact_person = fields.Char(string='Contact Person')
    contact_mobile = fields.Char(string='Contact Mobile')
    contact_email = fields.Char(string='Contact Email')
    address = fields.Char(string='Address')
    geo_location = fields.Char(string='Geo Location (lat,lon)', help='Paste coordinates as "lat,lon" to auto-fill geo location')

    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    # Computed HTML fields to render a tab per plant/transport/pump
    plant_tabs_html = fields.Html(string='Plant Tabs', compute='_compute_plant_tabs_html')
    transport_tabs_html = fields.Html(string='Transport Tabs', compute='_compute_transport_tabs_html')
    pump_tabs_html = fields.Html(string='Pump Tabs', compute='_compute_pump_tabs_html')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('subcontractor_code', 'New') == 'New':
                vals['subcontractor_code'] = self.env['ir.sequence'].next_by_code('rmc.subcontractor') or 'New'
            # If name not provided, try to fill from partner_id to satisfy required field
            if not vals.get('name') and vals.get('partner_id'):
                partner = self.env['res.partner'].browse(vals.get('partner_id'))
                if partner and partner.name:
                    vals['name'] = partner.name
        return super(RmcSubcontractor, self).create(vals_list)

    @api.constrains('has_plant', 'plant_ids')
    def _check_plant_requirement(self):
        for record in self:
            if record.has_plant and not record.plant_ids:
                raise ValidationError('At least one plant record is required when "Has Plant Services" is enabled.')

    @api.constrains('has_transport', 'transport_ids')
    def _check_transport_requirement(self):
        for record in self:
            if record.has_transport and not record.transport_ids:
                raise ValidationError('At least one transport record is required when "Has Transport Services" is enabled.')

    @api.constrains('has_pump', 'pump_ids')
    def _check_pump_requirement(self):
        for record in self:
            if record.has_pump and not record.pump_ids:
                raise ValidationError('At least one pump record is required when "Has Pump Services" is enabled.')

    @api.depends()
    def _compute_performance_metrics(self):
        for record in self:
            # These would be computed based on historical data
            # Simplified for demo
            record.acceptance_rate = 85.0
            record.average_response_time = 2.5
            record.quality_score = 4.2

    @api.onchange('partner_id')
    def _onchange_partner_set_name(self):
        for rec in self:
            if rec.partner_id and not rec.name:
                rec.name = rec.partner_id.name

    def action_create_fleet_vehicles(self):
        """Create fleet vehicles for all transport records that don't have one"""
        for transport in self.transport_ids:
            transport._create_fleet_vehicle()
        return True

    @api.depends('has_plant', 'plant_ids.plant_code', 'plant_ids.active')
    def _compute_plant_tabs_html(self):
        for record in self:
            if not record.has_plant:
                record.plant_tabs_html = ''
                continue
            parts = ['<div class="o_plant_tabs">']
            for plant in record.plant_ids:
                label = plant.plant_code or ('Plant %s' % (plant.id or ''))
                href = '/web#id=%s&model=rmc.subcontractor.plant&view_type=form' % (plant.id or 0)
                parts.append('<div class="o_plant_block">')
                parts.append('<h3><a class="o_plant_tab" href="%s">%s</a></h3>' % (href, label))
                # list fleet vehicles for this plant by category
                transport_fleet = self.env['fleet.vehicle'].search([('rmc_plant_id', '=', plant.id), ('rmc_category', '=', 'transport')])
                pump_fleet = self.env['fleet.vehicle'].search([('rmc_plant_id', '=', plant.id), ('rmc_category', '=', 'pump')])
                parts.append('<div class="o_fleet_category"><strong>Transport</strong>: ')
                if transport_fleet:
                    parts.append(', '.join(['<a href="/web#id=%s&model=fleet.vehicle&view_type=form">%s</a>' % (f.id, f.license_plate or f.name) for f in transport_fleet]))
                else:
                    parts.append('No transport fleet')
                parts.append('</div>')
                parts.append('<div class="o_fleet_category"><strong>Pump</strong>: ')
                if pump_fleet:
                    parts.append(', '.join(['<a href="/web#id=%s&model=fleet.vehicle&view_type=form">%s</a>' % (f.id, f.license_plate or f.name) for f in pump_fleet]))
                else:
                    parts.append('No pump fleet')
                parts.append('</div>')
                parts.append('</div>')
            parts.append('</div>')
            record.plant_tabs_html = ''.join(parts)

    @api.depends('has_transport', 'transport_ids.transport_code', 'transport_ids.active')
    def _compute_transport_tabs_html(self):
        for record in self:
            if not record.has_transport:
                record.transport_tabs_html = ''
                continue
            parts = ['<div class="o_transport_tabs">']
            for trans in record.transport_ids:
                label = trans.transport_code or ('Transport %s' % (trans.id or ''))
                href = '/web#id=%s&model=rmc.subcontractor.transport&view_type=form' % (trans.id or 0)
                parts.append('<a class="o_transport_tab" href="%s">%s</a>' % (href, label))
            parts.append('</div>')
            record.transport_tabs_html = ''.join(parts)

    @api.depends('has_pump', 'pump_ids.pump_code', 'pump_ids.active')
    def _compute_pump_tabs_html(self):
        for record in self:
            if not record.has_pump:
                record.pump_tabs_html = ''
                continue
            parts = ['<div class="o_pump_tabs">']
            for pump in record.pump_ids:
                label = pump.pump_code or ('Pump %s' % (pump.id or ''))
                href = '/web#id=%s&model=rmc.subcontractor.pump&view_type=form' % (pump.id or 0)
                parts.append('<a class="o_pump_tab" href="%s">%s</a>' % (href, label))
            parts.append('</div>')
            record.pump_tabs_html = ''.join(parts)


class RmcSubcontractorPlant(models.Model):
    _name = 'rmc.subcontractor.plant'
    _description = 'Subcontractor Plant'
    _order = 'plant_code'
    _rec_name = 'plant_code'

    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor', required=True, ondelete='cascade')
    plant_code = fields.Char(string='Plant Code', required=True)
    location = fields.Char(string='Location')
    address = fields.Char(string='Address')
    geo_location = fields.Char(string='Geo Location (lat,lon)', help='Paste coordinates as "lat,lon" to auto-fill geo location')
    capacity = fields.Float(string='Capacity (M3/batch)')
    contact_person = fields.Char(string='Contact Person')
    contact_mobile = fields.Char(string='Contact Mobile')
    contact_email = fields.Char(string='Contact Email')

    # BOM Integration
    bom_ids = fields.Many2many('mrp.bom', string='BOM Recipes', 
                              domain="[('product_tmpl_id', '!=', False)]",
                              help="BOM recipes available at this plant")

    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_plant_code', 'unique(plant_code)', 'Plant code must be unique!')
    ]

    def name_get(self):
        result = []
        for plant in self:
            code = plant.plant_code or _('Plant')
            if plant.location:
                name = '%s - %s' % (code, plant.location)
            else:
                name = code
            result.append((plant.id, name))
        return result

    @api.onchange('geo_location')
    def _onchange_geo_location_parse(self):
        for rec in self:
            if rec.geo_location:
                # try to parse lat,lon into separate values (store back as normalized)
                parts = [p.strip() for p in rec.geo_location.split(',') if p.strip()]
                if len(parts) == 2:
                    try:
                        lat = float(parts[0])
                        lon = float(parts[1])
                        # normalize and store
                        rec.geo_location = '%.6f,%.6f' % (lat, lon)
                    except Exception:
                        # leave as-is if not parseable
                        pass


class RmcSubcontractorTransport(models.Model):
    _name = 'rmc.subcontractor.transport'
    _description = 'Subcontractor Transport'
    _order = 'transport_code'

    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor', required=True, ondelete='cascade')
    transport_code = fields.Char(string='Transport Code', required=True)
    plant_id = fields.Many2one('rmc.subcontractor.plant', string='Plant')
    vehicle_type = fields.Selection([
        ('transit_mixer', 'Transit Mixer'),
        ('dump_truck', 'Dump Truck'),
        ('concrete_pump', 'Concrete Pump Truck'),
        ('other', 'Other'),
    ], string='Vehicle Type', default='transit_mixer')

    # Fleet Integration
    # Avoid client-side python domain evaluation which fails when subcontractor isn't loaded in JS.
    fleet_vehicle_id = fields.Many2one('fleet.vehicle', string='Fleet Vehicle')
    license_plate = fields.Char(string='License Plate', related='fleet_vehicle_id.license_plate', readonly=True)

    # Driver Information
    driver_name = fields.Char(string='Driver Name')
    driver_mobile = fields.Char(string='Driver Mobile')
    driver_email = fields.Char(string='Driver Email')

    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        """Create corresponding fleet vehicle when transport is created"""
        transports = super().create(vals_list)
        for transport in transports:
            if transport.subcontractor_id and not transport.fleet_vehicle_id:
                transport._create_fleet_vehicle()
        return transports

    def _create_fleet_vehicle(self):
        """Create a fleet vehicle record for this transport"""
        if not self.fleet_vehicle_id:
            fleet_vals = {
                'model_id': self.env['fleet.vehicle.model'].search([('name', 'ilike', self.vehicle_type)], limit=1).id or 1,
                'license_plate': self.transport_code,
                'driver_id': self.subcontractor_id.partner_id.id,  # Link subcontractor as driver/owner
                'active': True,
            }
            # if this transport is associated with a plant, annotate fleet vehicle with that plant
            if self.plant_id:
                fleet_vals['rmc_plant_id'] = self.plant_id.id
            # mark category
            fleet_vals['rmc_category'] = 'transport'
            fleet_vehicle = self.env['fleet.vehicle'].create(fleet_vals)
            self.fleet_vehicle_id = fleet_vehicle.id

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_for_plant(self):
        """When subcontractor changes, limit plant choices to that subcontractor's plants."""
        for rec in self:
            if rec.subcontractor_id:
                return {'domain': {'plant_id': [('subcontractor_id', '=', rec.subcontractor_id.id)]}}
            else:
                return {'domain': {'plant_id': []}}


    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_set_fleet_domain(self):
        """Provide a safe dynamic domain for the fleet_vehicle_id field when subcontractor changes.
        This avoids client-side python expression evaluation which can access undefined attributes.
        """
        for rec in self:
            if rec.subcontractor_id and rec.subcontractor_id.partner_id:
                partner_id = rec.subcontractor_id.partner_id.id
                return {'domain': {'fleet_vehicle_id': [('driver_id', '=', partner_id)]}}
            else:
                return {'domain': {'fleet_vehicle_id': []}}

    @api.onchange('plant_id')
    def _onchange_plant_set_transport_domain(self):
        for rec in self:
            if rec.plant_id:
                domain = [('rmc_plant_id', '=', rec.plant_id.id), ('rmc_category', '=', 'transport')]
            else:
                domain = [('rmc_category', '=', 'transport')]
            return {'domain': {'fleet_vehicle_id': domain}}

    _sql_constraints = [
        ('unique_transport_code', 'unique(transport_code)', 'Transport code must be unique!')
    ]


class RmcSubcontractorPump(models.Model):
    _name = 'rmc.subcontractor.pump'
    _description = 'Subcontractor Pump'
    _order = 'pump_code'
    _rec_name = 'pump_code'

    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor', required=True, ondelete='cascade')
    pump_code = fields.Char(string='Pump Code', required=True)
    plant_id = fields.Many2one('rmc.subcontractor.plant', string='Plant')
    pump_capacity = fields.Float(string='Pump Capacity (M3/hr)')

    # Operator Information
    operator_name = fields.Char(string='Operator Name')
    operator_mobile = fields.Char(string='Operator Mobile')
    operator_email = fields.Char(string='Operator Email')

    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_pump_code', 'unique(pump_code)', 'Pump code must be unique!')
    ]

    def name_get(self):
        result = []
        for pump in self:
            code = pump.pump_code or _('Pump')
            if pump.operator_name:
                name = '%s (%s)' % (code, pump.operator_name)
            else:
                name = code
            result.append((pump.id, name))
        return result

    def _create_fleet_vehicle(self):
        if not getattr(self, 'fleet_vehicle_id', False):
            fleet_vals = {
                'model_id': self.env['fleet.vehicle.model'].search([('name', 'ilike', 'concrete_pump')], limit=1).id or 1,
                'license_plate': self.pump_code,
                'driver_id': self.subcontractor_id.partner_id.id,
                'active': True,
                'rmc_category': 'pump',
            }
            if self.plant_id:
                fleet_vals['rmc_plant_id'] = self.plant_id.id
            fleet_vehicle = self.env['fleet.vehicle'].create(fleet_vals)
            # store fleet vehicle id if transport/pump models had such a field (compat)
            if hasattr(self, 'fleet_vehicle_id'):
                self.fleet_vehicle_id = fleet_vehicle.id

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_for_plant(self):
        for rec in self:
            if rec.subcontractor_id:
                return {'domain': {'plant_id': [('subcontractor_id', '=', rec.subcontractor_id.id)]}}
            else:
                return {'domain': {'plant_id': []}}

    @api.onchange('plant_id')
    def _onchange_plant_set_pump_domain(self):
        for rec in self:
            if rec.plant_id:
                domain = [('rmc_plant_id', '=', rec.plant_id.id), ('rmc_category', '=', 'pump')]
            else:
                domain = [('rmc_category', '=', 'pump')]
            return {'domain': {'fleet_vehicle_id': domain}}

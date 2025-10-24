# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    gaje_liter = fields.Float(
        string='Gaje Liter',
        help='Conversion factor: liters represented by one gaje unit for this vehicle.'
    )
    avg_fuel_efficiency_per_hr = fields.Float(
        string='Average Fuel Efficiency (Per hr)',
        help='Average fuel efficiency per engine hour (custom manual entry usable in diesel logs).'
    )
    fuel_tank_limit = fields.Float(
        string='Fuel Tank Limit',
        help='Maximum capacity of the fuel tank (liters).'
    )
    total_gaje_in_tank = fields.Float(
        string='Total Gaje in Tank',
        help='Total gaje units when tank is full.'
    )
    in_1_gaje_vehicle = fields.Float(
        string='In 1 Gaje',
        compute='_compute_in_1_gaje_vehicle',
        store=True,
        help='Calculated: Fuel Tank Limit / Total Gaje in Tank.'
    )
    
    diesel_log_count = fields.Integer(
        string='Diesel Logs',
        compute='_compute_diesel_log_count',
        help='Number of diesel logs for this vehicle'
    )
    
    last_fuel_date = fields.Datetime(
        string='Last Fueling Date',
        compute='_compute_last_fuel_info',
        store=True,
        help='Date of the last fuel entry'
    )
    
    last_fuel_quantity = fields.Float(
        string='Last Fuel Quantity',
        compute='_compute_last_fuel_info',
        store=True,
        help='Quantity of fuel in the last entry'
    )
    
    total_fuel_consumed = fields.Float(
        string='Total Fuel Consumed',
        compute='_compute_fuel_statistics',
        store=True,
        help='Total fuel consumed by this vehicle'
    )
    
    average_fuel_efficiency = fields.Float(
        string='Average Fuel Efficiency (L/100km)',
        compute='_compute_fuel_statistics',
        store=True,
        help='Average fuel consumption per 100 kilometers'
    )
    target_cost_per_cum = fields.Float(
        string='Target Cost per CuM',
        help='Target diesel cost per cubic meter for this vehicle/project.'
    )

   
    
    
    @api.depends('diesel_log_ids')
    def _compute_diesel_log_count(self):
        for vehicle in self:
            vehicle.diesel_log_count = len(vehicle.diesel_log_ids)
    
    diesel_log_ids = fields.One2many(
        'diesel.log',
        'vehicle_id',
        string='Diesel Logs',
        help='All diesel logs for this vehicle'
    )
    
    @api.depends('diesel_log_ids', 'diesel_log_ids.date', 'diesel_log_ids.quantity', 'diesel_log_ids.state')
    def _compute_last_fuel_info(self):
        for vehicle in self:
            last_log = vehicle.diesel_log_ids.filtered(lambda l: l.state == 'done').sorted('date', reverse=True)[:1]
            if last_log:
                vehicle.last_fuel_date = last_log.date
                vehicle.last_fuel_quantity = last_log.quantity
            else:
                vehicle.last_fuel_date = False
                vehicle.last_fuel_quantity = 0.0
    
    @api.depends('diesel_log_ids', 'diesel_log_ids.quantity', 'diesel_log_ids.fuel_efficiency', 'diesel_log_ids.state')
    def _compute_fuel_statistics(self):
        for vehicle in self:
            confirmed_logs = vehicle.diesel_log_ids.filtered(lambda l: l.state == 'done')
            
            if confirmed_logs:
                vehicle.total_fuel_consumed = sum(confirmed_logs.mapped('quantity'))
                
                # Calculate average fuel efficiency
                efficiency_logs = confirmed_logs.filtered(lambda l: l.fuel_efficiency > 0)
                if efficiency_logs:
                    vehicle.average_fuel_efficiency = sum(efficiency_logs.mapped('fuel_efficiency')) / len(efficiency_logs)
                else:
                    vehicle.average_fuel_efficiency = 0.0
            else:
                vehicle.total_fuel_consumed = 0.0
                vehicle.average_fuel_efficiency = 0.0

    @api.depends('fuel_tank_limit', 'total_gaje_in_tank')
    def _compute_in_1_gaje_vehicle(self):
        for v in self:
            if v.fuel_tank_limit and v.total_gaje_in_tank:
                try:
                    v.in_1_gaje_vehicle = v.fuel_tank_limit / v.total_gaje_in_tank if v.total_gaje_in_tank else 0.0
                except ZeroDivisionError:
                    v.in_1_gaje_vehicle = 0.0
            else:
                v.in_1_gaje_vehicle = 0.0
   
    def action_view_diesel_logs(self):
        """Smart button action to view diesel logs"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Diesel Logs'),
            'res_model': 'diesel.log',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
            'target': 'current',
        }
    
    def action_create_diesel_log(self):
        """Action to create a new diesel log for this vehicle"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Diesel Log'),
            'res_model': 'diesel.log',
            'view_mode': 'form',
            'context': {
                'default_vehicle_id': self.id,
                'default_last_odometer': self.odometer,
            },
            'target': 'current',
        }

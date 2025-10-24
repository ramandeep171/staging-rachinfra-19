from odoo import models, fields


class FleetVehicleExt(models.Model):
    _inherit = 'fleet.vehicle'

    # Link fleet vehicle to an RMC plant for per-plant fleet mapping
    # Link fleet vehicle to an RMC plant for per-plant fleet mapping
    rmc_plant_id = fields.Many2one('rmc.subcontractor.plant', string='RMC Plant')
    # Category for RMC usage: transport or pump
    rmc_category = fields.Selection([('transport', 'Transport'), ('pump', 'Pump')], string='RMC Category')

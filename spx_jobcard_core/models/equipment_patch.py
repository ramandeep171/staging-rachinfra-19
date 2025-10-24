# -*- coding: utf-8 -*-
from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    meter_hours = fields.Float(string="Meter Hours", help="Current running hours")

    x_preferred_vendor_id = fields.Many2one(
        "res.partner",
        string="Preferred Vendor (Emergency)",
        domain=[("is_company", "=", True)],
        help="Default vendor for emergency breakdowns.",
    )

    # RMC batching plant (or any production asset) capacity
    x_capacity_cum_per_hr = fields.Float(
        string="Rated Capacity (cum/hr)",
        help="Production capacity of the equipment. Used to compute production loss from downtime.",
    )

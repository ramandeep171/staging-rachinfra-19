from odoo import fields, models


class GearCycleReason(models.Model):
    """Master table for categorizing production cycle/workorder reasons."""

    _name = "gear.cycle.reason"
    _description = "Gear Cycle Reason"
    _order = "name"

    name = fields.Char(string="Reason", required=True)
    reason_type = fields.Selection(
        selection=[("client", "Client"), ("maintenance", "Maintenance")],
        string="Reason Type",
        required=True,
        default="client",
        help="Classify reasons to control client workflows versus maintenance handling.",
    )
    active = fields.Boolean(default=True)

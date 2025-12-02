from odoo import fields, models


class GearReason(models.Model):
    """Master list of reasons for diesel overrun handling."""

    _name = "gear.reason"
    _description = "Gear Reason"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string="Reason", required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    reason_type = fields.Selection(
        selection=[("client", "Client"), ("maintenance", "Maintenance")],
        string="Reason Type",
        required=True,
        default="client",
        help="Classify the reason to drive client-facing versus maintenance handling.",
    )
    active = fields.Boolean(default=True)

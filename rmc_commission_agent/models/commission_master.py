from odoo import _, fields, models

from .utils import AGENT_CHANNEL_SELECTION


class RmcCommissionMaster(models.Model):
    _name = "rmc.commission.master"
    _description = "Commission Master"

    name = fields.Char(required=True, translate=True)
    country_tag = fields.Selection(
        selection=[("ncr", "NCR"), ("haryana", "Haryana")],
        required=True,
        default="ncr",
        help="Regional tag used to suggest matching agents and orders.",
    )
    applicable_channel = fields.Selection(
        selection=AGENT_CHANNEL_SELECTION,
        help="Optional channel restriction. Leave empty to allow all channels.",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(translate=True)

    _sql_constraints = [
        ("name_country_unique", "unique(name, country_tag)", "Each country tag needs unique name."),
    ]

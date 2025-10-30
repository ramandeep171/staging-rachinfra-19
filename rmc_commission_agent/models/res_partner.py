from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    commission_agent_ids = fields.One2many(
        "rmc.commission.agent",
        "partner_id",
        string="Commission Agents",
    )

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_subcontractor = fields.Boolean(
        string="Is Subcontractor",
        default=False,
        help="Enable this to allow the partner to be selected as a subcontractor "
        "for Brand-specific variant mappings.",
    )

    @api.model
    def _commercial_fields(self):
        """Ensure the flag propagates across contacts in the same company."""
        return super()._commercial_fields() + ["is_subcontractor"]

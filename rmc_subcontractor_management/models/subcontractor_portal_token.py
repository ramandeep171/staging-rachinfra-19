from datetime import timedelta
import secrets

from odoo import api, fields, models


class RmcSubcontractorPortalToken(models.Model):
    _name = "rmc.subcontractor.portal.token"
    _description = "Subcontractor Portal Token"
    _order = "create_date desc"

    name = fields.Char(default=lambda self: secrets.token_hex(16), copy=False, required=True, index=True)
    lead_id = fields.Many2one("crm.lead", string="Lead", ondelete="cascade")
    subcontractor_id = fields.Many2one("rmc.subcontractor", string="Subcontractor", ondelete="cascade")
    profile_id = fields.Many2one("rmc.subcontractor.profile", string="Profile", ondelete="cascade")
    expiration = fields.Datetime(string="Expires On", required=True, default=lambda self: fields.Datetime.now() + timedelta(days=1))
    last_access_date = fields.Datetime()
    is_portal_user_created = fields.Boolean()
    portal_user_id = fields.Many2one("res.users", string="Portal User", readonly=True)
    access_url = fields.Char(compute="_compute_access_url")
    state = fields.Selection(
        [
            ("lead", "Lead"),
            ("profile", "Profile"),
            ("portal", "Portal"),
            ("expired", "Expired"),
        ],
        default="lead",
    )

    _sql_constraints = [
        ("name_unique", "unique(name)", "Tokens must be unique."),
    ]

    def mark_accessed(self):
        self.write({"last_access_date": fields.Datetime.now()})

    def is_valid(self):
        self.ensure_one()
        return self.expiration and self.expiration >= fields.Datetime.now()

    @api.model
    def prune_expired(self):
        expired = self.search([("expiration", "<", fields.Datetime.now()), ("state", "!=", "expired")])
        expired.write({"state": "expired"})
        return expired

    def _compute_access_url(self):
        base = "/subcontractor/more-info/"
        for token in self:
            token.access_url = "%s%s" % (base, token.name if token.name else "")

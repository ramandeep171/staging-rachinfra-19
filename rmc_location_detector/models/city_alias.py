from odoo import api, fields, models


class RmcGeoCityAlias(models.Model):
    _name = "rmc.geo.city.alias"
    _description = "City Alias"
    _order = "alias"

    alias = fields.Char(required=True, translate=True)
    canonical_city = fields.Char(required=True, translate=True)
    website_id = fields.Many2one(
        "website",
        string="Website",
        help="Limit the alias to a specific website. Leave empty to apply globally.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "rmc_geo_city_alias_unique",
            "UNIQUE(alias, website_id)",
            "An alias with the same website already exists.",
        )
    ]

    @api.model
    def canonicalize(self, website, city_name):
        if not city_name:
            return city_name
        normalized = city_name.strip()
        domain = [
            ("alias", "=ilike", normalized),
            ("active", "=", True),
        ]
        if website:
            domain = ["|", ("website_id", "=", False), ("website_id", "=", website.id)] + domain
        alias = self.search(domain, limit=1)
        return alias.canonical_city.strip() if alias else normalized

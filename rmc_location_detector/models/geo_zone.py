from odoo import api, fields, models, tools


class RmcGeoZone(models.Model):
    _name = "rmc.geo.zone"
    _description = "Location-based Pricelist Zone"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    city = fields.Char()
    zip_prefix = fields.Char(help="e.g., 1220 for 1220xx")
    pricelist_id = fields.Many2one(
        "product.pricelist",
        required=True,
        ondelete="restrict",
    )
    website_id = fields.Many2one(
        "website",
        string="Website",
        help="Limit the zone to a specific website. Leave empty for all websites.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "rmc_geo_zone_city_or_zip",
            "CHECK( (city IS NOT NULL AND char_length(trim(city)) > 0)"
            " OR (zip_prefix IS NOT NULL AND char_length(trim(zip_prefix)) > 0) )",
            "Please set a City or a ZIP prefix to define the zone.",
        )
    ]

    @api.model
    def match(self, website, city, zip_code):
        """Resolve the best pricelist for the provided location."""

        zone = self._match_zone(website, city, zip_code)
        if zone:
            return zone.pricelist_id
        if website:
            try:
                pricelist = website._get_and_cache_current_pricelist()
                if pricelist:
                    return pricelist
            except Exception:
                return False
        return False

    def _match_zone(self, website, city, zip_code):
        """Internal helper returning the matching zone record."""

        website_id = website.id if website else False
        domain = [("active", "=", True)]
        if website_id:
            domain = ["&", "|", ("website_id", "=", False), ("website_id", "=", website_id)] + domain
        else:
            domain.append(("website_id", "=", False))

        candidates = self.search(domain)

        normalized_zip = tools.ustr(zip_code or "").strip()
        normalized_city = tools.ustr(city or "").strip().lower()

        best_zone = False
        best_zip_len = -1
        if normalized_zip:
            for zone in candidates:
                if zone.zip_prefix:
                    prefix = zone.zip_prefix.strip()
                    if normalized_zip.startswith(prefix) and len(prefix) > best_zip_len:
                        best_zone = zone
                        best_zip_len = len(prefix)

        if not best_zone and normalized_city:
            for zone in candidates:
                if zone.city and zone.city.strip().lower() == normalized_city:
                    best_zone = zone
                    break

        return best_zone

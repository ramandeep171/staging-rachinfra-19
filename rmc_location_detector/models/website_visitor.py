from odoo import fields, models


class WebsiteVisitor(models.Model):
    _inherit = "website.visitor"

    ri_city = fields.Char(string="Detected City")
    ri_zip = fields.Char(string="Detected ZIP")
    ri_location_method = fields.Selection(
        selection=[
            ("ip", "IP"),
            ("gps", "GPS"),
            ("manual", "Manual"),
        ],
        string="Location Method",
    )
    ri_location_updated = fields.Datetime(string="Location Updated On")

    def _update_visitor_location(self, city, zip_code, method):
        """Persist the detected location details on the visitor."""
        sanitized_city = city or False
        sanitized_zip = zip_code or False
        sanitized_method = method or False
        now = fields.Datetime.now()
        for visitor in self:
            visitor.write(
                {
                    "ri_city": sanitized_city,
                    "ri_zip": sanitized_zip,
                    "ri_location_method": sanitized_method,
                    "ri_location_updated": now,
                }
            )
        return True

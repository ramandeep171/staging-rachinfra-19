from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    rmc_location_mapbox_token = fields.Char(
        string="Mapbox Token",
        config_parameter="rmc_location.mapbox_token",
    )
    rmc_location_google_api_key = fields.Char(
        string="Google Maps API Key",
        config_parameter="rmc_location.google_api_key",
    )
    rmc_location_enable_ip_guess = fields.Boolean(
        string="Enable IP-based Guess",
        config_parameter="rmc_location.enable_ip_guess",
        default=True,
    )
    rmc_location_enable_gps = fields.Boolean(
        string="Enable GPS Reverse Geocoding",
        config_parameter="rmc_location.enable_gps",
        default=True,
    )
    rmc_location_cookie_ttl_days = fields.Integer(
        string="Location Cookie Lifetime (days)",
        config_parameter="rmc_location.cookie_ttl_days",
        default=30,
        help="Number of days to keep the detected location in browser cookies.",
    )

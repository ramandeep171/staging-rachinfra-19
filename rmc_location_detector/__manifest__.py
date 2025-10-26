{
    "name": "rmc_location_detector",
    "version": "19.0.1.0",
    "category": "Website",
    "summary": "City+Pincode detector with session pricelist switch & checkout address based re-evaluation",
    "license": "OPL-1",
    "depends": [
        "website",
        "web",
        "base_geolocalize",
        "website_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/location_settings.xml",
        "views/geo_zone_views.xml",
        "views/city_alias_views.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "rmc_location_detector/static/src/js/location.js",
            "rmc_location_detector/static/src/css/location.css",
        ],
    },
    "installable": True,
    "application": False,
}

import logging
from typing import Optional

import requests

from odoo import fields, http, _
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)


class RmcLocationController(http.Controller):
    COOKIE_KEYS = {
        "city": "ri_loc_city",
        "zip": "ri_loc_zip",
        "method": "ri_loc_method",
        "updated": "ri_loc_updated",
    }
    DEFAULT_COOKIE_TTL_DAYS = 30
    GEO_PARAM_PREFIX = "rmc_location."

    def _get_config_parameter(self, key: str, default: Optional[str] = None) -> str:
        return request.env["ir.config_parameter"].sudo().get_param(key, default)

    def _is_feature_enabled(self, param_key: str, default: str = "1") -> bool:
        value = self._get_config_parameter(param_key, default)
        try:
            return str2bool(str(value))
        except Exception:
            return False

    def _get_cookie_ttl_seconds(self) -> int:
        value = self._get_config_parameter(
            f"{self.GEO_PARAM_PREFIX}cookie_ttl_days",
            str(self.DEFAULT_COOKIE_TTL_DAYS),
        )
        try:
            ttl_days = int(value)
        except (TypeError, ValueError):
            ttl_days = self.DEFAULT_COOKIE_TTL_DAYS
        ttl_days = max(1, ttl_days)
        return ttl_days * 24 * 3600

    def _json_response(self, payload, cookies=None):
        response = request.make_json_response(payload)
        if cookies:
            secure = request.httprequest.scheme == "https"
            max_age = self._get_cookie_ttl_seconds()
            for cookie_name, cookie_value in cookies.items():
                response.set_cookie(
                    cookie_name,
                    cookie_value or "",
                    max_age=max_age,
                    path="/",
                    secure=secure,
                    httponly=False,
                    samesite="Lax",
                )
        return response

    def _get_payload(self):
        payload = {}
        try:
            if request.httprequest.mimetype == "application/json":
                payload = request.get_json_data() or {}
        except Exception as err:
            _logger.debug("[rmc_location_detector] Failed to parse JSON body: %s", err)
            payload = {}
        if not payload:
            payload = request.get_http_params()
        return payload

    def _sanitize_method(self, method: Optional[str]) -> Optional[str]:
        allowed = {"ip", "gps", "manual"}
        if method and method.lower() in allowed:
            return method.lower()
        return None

    def _resolve_pricelist(self, city: Optional[str], zip_code: Optional[str]):
        zone_model = request.env["rmc.geo.zone"].sudo()
        website = request.website
        return zone_model.match(website, city, zip_code)

    def _apply_pricelist_if_needed(self, pricelist):
        current_pl = request.website._get_and_cache_current_pricelist()
        if not pricelist or not pricelist.exists():
            if current_pl:
                WebsiteSale()._apply_pricelist(pricelist=None)
                return True
            return False
        if current_pl and current_pl.id == pricelist.id:
            return False
        WebsiteSale()._apply_pricelist(pricelist=pricelist)
        return True

    def _update_visitor(self, city, zip_code, method):
        visitor_sudo = request.env["website.visitor"].sudo()._get_visitor_from_request(
            force_create=True
        )
        if visitor_sudo:
            visitor_sudo._update_visitor_location(city, zip_code, method)

    def _cookie_payload(self, city, zip_code, method):
        timestamp = fields.Datetime.to_string(fields.Datetime.now())
        return {
            self.COOKIE_KEYS["city"]: city or "",
            self.COOKIE_KEYS["zip"]: zip_code or "",
            self.COOKIE_KEYS["method"]: method or "",
            self.COOKIE_KEYS["updated"]: timestamp,
        }

    def _format_location_response(self, city, zip_code, method, pricelist, repriced=False):
        return {
            "city": city or "",
            "zip": zip_code or "",
            "method": method,
            "pricelist_id": pricelist.id if pricelist else False,
            "pricelist_name": pricelist.name if pricelist else "",
            "repriced": repriced,
        }

    @http.route("/rmc/location/save", type="http", auth="public", methods=["POST"], website=True, csrf=False)
    def save_location(self, **kwargs):
        try:
            payload = self._get_payload()
            _logger.info("[rmc_location_detector] save_location payload=%s", payload)
            city = (payload.get("city") or "").strip()
            zip_code = (payload.get("zip") or "").strip()
            method = self._sanitize_method(payload.get("method")) or "manual"

            pricelist = self._resolve_pricelist(city, zip_code)
            repriced = self._apply_pricelist_if_needed(pricelist)
            self._update_visitor(city, zip_code, method)
            response_payload = self._format_location_response(city, zip_code, method, pricelist, repriced)
        except Exception as err:
            _logger.exception("[rmc_location_detector] Failed to save visitor location")
            response_payload = {"error": _("We could not update your location right now."), "details": str(err)}
            return self._json_response(response_payload)

        cookies = self._cookie_payload(city, zip_code, method)
        return self._json_response(response_payload, cookies=cookies)

    @http.route("/rmc/location/ip_guess", type="http", auth="public", methods=["GET"], website=True)
    def ip_guess(self, **kwargs):
        if not self._is_feature_enabled(f"{self.GEO_PARAM_PREFIX}enable_ip_guess"):
            _logger.info("[rmc_location_detector] ip_guess disabled")
            return self._json_response({"error": _("IP-based detection is disabled.")})

        city = zip_code = None
        try:
            if request.geoip:
                city = getattr(getattr(request.geoip, "city", None), "name", None)
                zip_code = getattr(getattr(request.geoip, "postal", None), "code", None)
        except Exception as err:
            _logger.debug("GeoIP lookup failed: %s", err)

        if not (city or zip_code):
            return self._json_response({"error": _("Location unavailable for your IP.")})

        pricelist = self._resolve_pricelist(city, zip_code)
        response_payload = self._format_location_response(city, zip_code, "ip", pricelist, repriced=False)
        return self._json_response(response_payload)

    @http.route("/rmc/location/reverse", type="http", auth="public", methods=["GET"], website=True)
    def reverse_geocode(self, **kwargs):
        if not self._is_feature_enabled(f"{self.GEO_PARAM_PREFIX}enable_gps"):
            return self._json_response({"error": _("GPS lookup is disabled.")})

        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return self._json_response({"error": _("Invalid coordinates provided.")})

        city = zip_code = None
        error_detail = None
        try:
            city, zip_code = self._reverse_geocode_request(lat, lon)
        except Exception as err:
            error_detail = str(err)
            _logger.exception("[rmc_location_detector] Reverse geocoding failed")

        if not (city or zip_code):
            payload = {"error": _("We could not determine your location."), "details": error_detail}
            return self._json_response(payload)

        pricelist = self._resolve_pricelist(city, zip_code)
        response_payload = self._format_location_response(city, zip_code, "gps", pricelist, repriced=False)
        return self._json_response(response_payload)

    @http.route("/rmc/location/checkout_sync", type="http", auth="public", methods=["POST"], website=True, csrf=False)
    def checkout_sync(self, **kwargs):
        payload = self._get_payload()
        zip_code = (payload.get("zip") or "").strip()
        city = (payload.get("city") or "").strip()

        try:
            pricelist = self._resolve_pricelist(city, zip_code)
            repriced = self._apply_pricelist_if_needed(pricelist)
            response_payload = self._format_location_response(city, zip_code, None, pricelist, repriced=repriced)
        except Exception as err:
            _logger.exception("[rmc_location_detector] Checkout sync failed")
            response_payload = {"error": _("We could not adjust prices for this address."), "details": str(err)}
            return self._json_response(response_payload)

        return self._json_response(response_payload)

    def _reverse_geocode_request(self, lat: float, lon: float):
        google_key = self._get_config_parameter(f"{self.GEO_PARAM_PREFIX}google_api_key")
        mapbox_token = self._get_config_parameter(f"{self.GEO_PARAM_PREFIX}mapbox_token")

        if google_key:
            return self._call_google_reverse(lat, lon, google_key)
        if mapbox_token:
            return self._call_mapbox_reverse(lat, lon, mapbox_token)

        raise ValueError(_("No geocoding service is configured."))

    def _call_google_reverse(self, lat: float, lon: float, api_key: str):
        params = {"latlng": f"{lat},{lon}", "key": api_key}
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK":
            raise ValueError(data.get("error_message") or data.get("status") or "UNKNOWN_ERROR")

        return self._parse_google_components(data.get("results", []))

    def _parse_google_components(self, results):
        city = zip_code = None
        for result in results:
            for component in result.get("address_components", []):
                types = component.get("types", [])
                if "locality" in types or "postal_town" in types:
                    city = city or component.get("long_name")
                if "administrative_area_level_2" in types and not city:
                    city = component.get("long_name")
                if "postal_code" in types and not zip_code:
                    zip_code = component.get("long_name")
            if city or zip_code:
                break
        return city, zip_code

    def _call_mapbox_reverse(self, lat: float, lon: float, token: str):
        params = {"access_token": token, "types": "postcode,place"}
        response = requests.get(
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json",
            params=params,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return self._parse_mapbox_features(data.get("features", []))

    def _parse_mapbox_features(self, features):
        city = zip_code = None
        for feature in features:
            feature_id = feature.get("id", "")
            if feature_id.startswith("place") and not city:
                city = feature.get("text")
            if feature_id.startswith("postcode") and not zip_code:
                zip_code = feature.get("text")

            for context in feature.get("context", []):
                ctx_id = context.get("id", "")
                if ctx_id.startswith("place") and not city:
                    city = context.get("text")
                if ctx_id.startswith("postcode") and not zip_code:
                    zip_code = context.get("text")
            if city and zip_code:
                break
        return city, zip_code

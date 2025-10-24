# -*- coding: utf-8 -*-
import logging

import requests
from requests import exceptions as requests_exceptions

from odoo import _, http
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome, _lt

_logger = logging.getLogger(__name__)


class AuthSignupRecaptcha(AuthSignupHome):

    def _validate_recaptcha(self, response_token):
        """Validate the Google reCAPTCHA response token."""
        params = request.env['ir.config_parameter'].sudo()
        recaptcha_enabled = params.get_param('recaptcha_signup.enabled') == 'True'
        if not recaptcha_enabled:
            return True, None

        secret_key = params.get_param('recaptcha_signup.private_key')
        if not secret_key:
            return False, _("The reCAPTCHA secret key is not configured.")

        if not response_token:
            return False, _("Please complete the reCAPTCHA challenge.")

        try:
            response = requests.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={"secret": secret_key, "response": response_token},
                timeout=5,
            )
            if not response.ok:
                _logger.warning("reCAPTCHA validation failed with HTTP status %s", response.status_code)
                return False, _("Unable to verify reCAPTCHA. Please try again.")
            result = response.json()
        except (requests_exceptions.RequestException, ValueError) as exc:
            _logger.exception("Error while contacting reCAPTCHA verification service: %s", exc)
            return False, _("Unable to verify reCAPTCHA. Please try again later.")

        if not result.get("success"):
            return False, _("Invalid reCAPTCHA. Please try again.")
        return True, None

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False, captcha='signup',
                list_as_website_content=_lt("Sign Up"))
    def web_auth_signup(self, *args, **kw):
        if request.httprequest.method == 'POST':
            recaptcha_response = kw.get("g-recaptcha-response")
            is_valid, error_message = self._validate_recaptcha(recaptcha_response)
            if not is_valid:
                qcontext = self.get_auth_signup_qcontext()
                if error_message:
                    qcontext['error'] = error_message
                response = request.render('auth_signup.signup', qcontext)
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
                return response
        return super().web_auth_signup(*args, **kw)

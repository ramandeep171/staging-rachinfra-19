import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..utils import waha_utils

_logger = logging.getLogger(__name__)
_waha_utils = waha_utils


class WhatsappAccount(models.Model):
    _inherit = "whatsapp.account"

    provider = fields.Selection(
        [
            ("waha", "WAHA (WhatsApp API by Infinys)"),
            ("meta", "Meta Cloud API (Facebook)"),
        ],
        string="Provider",
        default="meta",
        required=True,
        help="Select the transport you configured in Odoo's default WhatsApp module.",
    )
    whatsapp_api_url = fields.Char(
        string="WhatsApp API URL",
        help="Base URL for WAHA / self-hosted API endpoints.",
    )
    webhook_url = fields.Char(
        string="Webhook URL (N8n)",
        help="Endpoint that receives delivery receipts and replies from your WAHA/N8n relay.",
    )
    authentication_user = fields.Char(string="WAHA Auth User / App ID")
    authentication_password = fields.Char(string="WAHA Auth Password / App Secret")
    welcome_message = fields.Html(
        string="Welcome Message",
        sanitize=False,
        help="Optional greeting sent when an unknown contact reaches out.",
    )
    ir_deployment = fields.Char(string="Deployment", compute="_compute_ir_deployment")
    invisible_trial = fields.Boolean(string="Invisible Trial")
    whatsapp_number = fields.Char(
        string="Phone Number ID (WAHA)",
        related="phone_uid",
        store=True,
        readonly=False,
    )

    def btn_test_credential(self):
        """Test the WAHA API connection using the configured settings."""
        self.ensure_one()
        message = _("Testing WAHA API connection : ")
        status = "success"

        if self.provider != "waha":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Non-WAHA Provider"),
                    "message": _(
                        "Default Meta Cloud flow already provides a Test Credentials button."
                    ),
                    "type": "info",
                },
            }

        data = _waha_utils.test_connection(
            whatapp_api_url=self.whatsapp_api_url,
            username=self.authentication_user,
            password=self.authentication_password,
            token=self.token,
            whatsapp_number=self.whatsapp_number,
        )

        if data.get("status") == "success":
            message += _("Connection successful.")
        else:
            status = "warning"
            message += _("Connection failed. Error: %s") % (data.get("message") or _("Unknown error"))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("WAHA Connection Test"),
                "message": message,
                "type": status,
                "sticky": False,
            },
        }

    @api.depends_context("uid")
    def _compute_ir_deployment(self):
        parameter = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("infinys_whatsapp_blasting.deployment")
            or ""
        )
        for account in self:
            account.ir_deployment = parameter
            account.invisible_trial = parameter.lower() == "trial"

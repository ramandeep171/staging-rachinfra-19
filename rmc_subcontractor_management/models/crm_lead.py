from datetime import timedelta
import logging
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv.expression import AND

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    is_subcontractor_lead = fields.Boolean(
        string="Subcontractor Inquiry",
        help="Flag automatically set for leads captured via the subcontractor landing page.",
    )
    subcontractor_token_id = fields.Many2one(
        "rmc.subcontractor.portal.token",
        string="Portal Token",
        copy=False,
    )
    subcontractor_profile_id = fields.Many2one(
        "rmc.subcontractor.profile",
        string="Subcontractor Profile",
        copy=False,
    )
    subcontractor_more_info_deadline = fields.Datetime(
        string="More-Info Access Deadline",
        compute="_compute_subcontractor_deadline",
        store=True,
    )
    subcontractor_city = fields.Char(
        string="Subcontractor City",
        help="City captured from the landing page form.",
    )
    subcontractor_hot_zone_ids = fields.Many2many(
        "rmc.subcontractor.hot.zone",
        string="Hot Zones",
        help="Auto-tagged based on configuration when the inquiry matches configured geographies.",
    )

    @api.depends("subcontractor_token_id.expiration")
    def _compute_subcontractor_deadline(self):
        for lead in self:
            lead.subcontractor_more_info_deadline = lead.subcontractor_token_id.expiration

    @api.model_create_multi
    def create(self, vals_list):
        team = self.env.ref("rmc_subcontractor_management.team_subc", raise_if_not_found=False)
        subcontractor_tag = self.env.ref(
            "rmc_subcontractor_management.crm_tag_subcontractor",
            raise_if_not_found=False,
        )
        created_records = self.env[self._name]
        for vals in vals_list:
            if vals.get("is_subcontractor_lead"):
                # Deduplicate by phone/email
                duplicate = self._find_subcontractor_duplicate(vals)
                if duplicate:
                    _logger.info(
                        "Deduplicated subcontractor inquiry (%s) onto lead %s",
                        vals.get("phone") or vals.get("email_from"),
                        duplicate.display_name,
                    )
                    duplicate.message_post(
                        body=_(
                            "New subcontractor inquiry merged into this lead.<br/>"
                            "<b>Name:</b> %(name)s<br/>"
                            "<b>Phone:</b> %(phone)s<br/>"
                            "<b>City:</b> %(city)s"
                        )
                        % {
                            "name": vals.get("contact_name") or vals.get("name") or _("Unknown"),
                            "phone": vals.get("phone") or _("N/A"),
                            "city": vals.get("subcontractor_city") or vals.get("city") or _("N/A"),
                        }
                    )
                    continue
                if team and not vals.get("team_id"):
                    vals["team_id"] = team.id
                if subcontractor_tag:
                    tag_ids = vals.setdefault("tag_ids", [(6, 0, [])])
                    if isinstance(tag_ids, list):
                        existing_ids = set()
                        for command in tag_ids:
                            if command[0] == 6:
                                existing_ids.update(command[2])
                        if subcontractor_tag.id not in existing_ids:
                            tag_ids.append((4, subcontractor_tag.id))
                vals.setdefault("priority", "3")
                vals.setdefault("type", "lead")
                vals.setdefault("probability", 5.0)
        if not vals_list:
            return created_records
        created_records = super().create(vals_list)
        for lead in created_records.filtered("is_subcontractor_lead"):
            lead._ensure_subcontractor_token()
            lead._schedule_subcontractor_activity()
            template_ack = self.env.ref(
                "rmc_subcontractor_management.mail_template_subcontractor_inquiry_ack",
                raise_if_not_found=False,
            )
            if template_ack:
                template_ack.send_mail(lead.id, force_send=False)
        return created_records

    def _find_subcontractor_duplicate(self, vals):
        """Return an existing lead that matches the provided phone/email."""
        phone = vals.get("phone")
        email = vals.get("email_from")
        domain = [("is_subcontractor_lead", "=", True)]
        if phone:
            normalized = self._normalize_phone_number(phone)
            domain = AND(
                [
                    domain,
                    [
                        "|",
                        ("phone", "ilike", normalized),
                        ("phone_sanitized", "ilike", normalized),
                    ],
                ]
            )
        if email:
            domain = AND([domain, ["|", ("email_from", "=", email), ("email_cc", "ilike", email)]])
        duplicate = self.search(domain, limit=1)
        return duplicate

    def _normalize_phone_number(self, phone):
        return "".join(filter(str.isdigit, phone or ""))

    def _ensure_subcontractor_token(self):
        self.ensure_one()
        if self.subcontractor_token_id:
            return self.subcontractor_token_id
        token_model = self.env["rmc.subcontractor.portal.token"]
        token = token_model.create(
            {
                "lead_id": self.id,
                "name": uuid.uuid4().hex,
                "expiration": fields.Datetime.now() + timedelta(days=1),
            }
        )
        self.subcontractor_token_id = token.id
        template = self.env.ref(
            "rmc_subcontractor_management.mail_template_subcontractor_more_info",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=False)
        return token

    def _schedule_subcontractor_activity(self):
        for lead in self:
            try:
                lead.activity_schedule(
                    activity_type_id=self.env.ref("mail.mail_activity_data_call").id,
                    summary=_("Verify subcontractor inquiry"),
                    note=_("SLA: complete phone verification within 15 minutes of capture."),
                    date_deadline=fields.Date.today(),
                    user_id=lead.user_id.id or False,
                )
            except Exception as exc:
                _logger.warning("Failed to schedule subcontractor SLA activity for lead %s: %s", lead.id, exc)

    def action_open_subcontractor_profile(self):
        self.ensure_one()
        profile = self.subcontractor_profile_id or self._create_subcontractor_profile()
        return {
            "type": "ir.actions.act_window",
            "res_model": "rmc.subcontractor.profile",
            "name": _("Subcontractor Profile"),
            "view_mode": "form",
            "res_id": profile.id,
            "target": "current",
        }

    def _create_subcontractor_profile(self):
        self.ensure_one()
        profile = self.env["rmc.subcontractor.profile"].create(
            {
                "lead_id": self.id,
                "name": self.contact_name or self.partner_name or self.name,
                "mobile": self.phone,
                "city": self.subcontractor_city,
            }
        )
        self.subcontractor_profile_id = profile.id
        return profile

    def action_trigger_more_info_token(self):
        self.ensure_one()
        if not self.is_subcontractor_lead:
            raise UserError(_("Only subcontractor leads support more-info tokens."))
        token = self._ensure_subcontractor_token()
        token.write({"expiration": fields.Datetime.now() + timedelta(hours=12)})
        template = self.env.ref(
            "rmc_subcontractor_management.mail_template_subcontractor_more_info",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)
        return True

    def action_create_subcontractor(self):
        """Button helper to create or open the related subcontractor ops record."""
        self.ensure_one()
        subcontractor = self.env["rmc.subcontractor"].search([("lead_id", "=", self.id)], limit=1)
        if subcontractor:
            action = self.env.ref("rmc_subcontractor_management.action_rmc_subcontractor_pipeline")
            result = action.read()[0]
            result.update({"res_id": subcontractor.id, "view_mode": "form"})
            return result
        profile = self.subcontractor_profile_id or self._create_subcontractor_profile()
        values = profile._prepare_subcontractor_values()
        subcontractor = self.env["rmc.subcontractor"].create(values)
        profile.subcontractor_id = subcontractor.id
        subcontractor.message_post(
            body=_("Subcontractor record created from CRM Lead <a href=\"#\" data-oe-model=\"crm.lead\" data-oe-id=\"%s\">%s</a>")
            % (self.id, self.display_name)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "rmc.subcontractor",
            "res_id": subcontractor.id,
            "view_mode": "form",
        }

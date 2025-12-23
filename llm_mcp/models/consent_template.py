from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LLMConsentTemplate(models.Model):
    _name = "llm.mcp.consent.template"
    _description = "LLM MCP Consent Template"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    scope = fields.Selection(
        [
            ("tool", "Tool"),
            ("tag", "Tag"),
            ("global", "Global"),
        ],
        required=True,
        default="tool",
        tracking=True,
        help="Determines whether the consent applies to a specific tool, matching tags, or all tools.",
    )
    default_opt = fields.Selection(
        [
            ("opt_in", "Opt-in"),
            ("opt_out", "Opt-out"),
        ],
        required=True,
        default="opt_in",
        tracking=True,
        help="Default decision when no ledger entry exists. Opt-in requires explicit consent.",
    )
    message_html = fields.Html(
        string="Consent Message",
        sanitize=True,
        help="Prompt displayed to the user when requesting consent.",
    )
    ttl_days = fields.Integer(
        string="TTL (days)",
        default=0,
        help="Validity period for a granted consent. Zero disables expiration.",
    )
    active = fields.Boolean(default=True, tracking=True)
    tag_ids = fields.Many2many(
        "llm.tool.tag",
        string="Scoped Tags",
        help="If scope is Tag, consent applies when the tool carries any of these tags.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.constrains("ttl_days")
    def _check_ttl_days(self):
        for template in self:
            if template.ttl_days is not None and template.ttl_days < 0:
                raise ValidationError(_("TTL days must be zero or a positive integer."))

    @api.constrains("scope", "tag_ids")
    def _check_tag_scope(self):
        for template in self:
            if template.scope == "tag" and not template.tag_ids:
                raise ValidationError(
                    _("Tag-scoped consent templates must define at least one tag."),
                )

    @api.model
    def _select_template_for_tool(self, tool):
        tool = tool.sudo() if tool else tool
        ConsentTemplate = self.env["llm.mcp.consent.template"]

        if not tool:
            return ConsentTemplate.browse()

        # Prefer explicit mapping on the tool if available
        if getattr(tool, "mcp_consent_template_id", False):
            return tool.mcp_consent_template_id

        # Try tag-based templates
        if getattr(tool, "tag_ids", False):
            tag_template = ConsentTemplate.search(
                [
                    ("scope", "=", "tag"),
                    ("tag_ids", "in", tool.tag_ids.ids),
                    ("active", "=", True),
                    ("company_id", "in", tool.company_id.ids if tool.company_id else self.env.companies.ids),
                ],
                limit=1,
            )
            if tag_template:
                return tag_template

        # Fallback to global templates
        global_template = ConsentTemplate.search(
            [
                ("scope", "=", "global"),
                ("active", "=", True),
                ("company_id", "in", tool.company_id.ids if tool.company_id else self.env.companies.ids),
            ],
            limit=1,
        )
        return global_template


class LLMConsentLedger(models.Model):
    _name = "llm.mcp.consent.ledger"
    _description = "LLM MCP Consent Ledger"
    _order = "timestamp desc"
    _inherit = ["mail.thread"]

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    tool_id = fields.Many2one(
        "llm.tool.definition",
        string="Tool",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    template_id = fields.Many2one(
        "llm.mcp.consent.template",
        string="Consent Template",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    company_id = fields.Many2one(
        related="tool_id.company_id",
        store=True,
        readonly=True,
    )
    decision = fields.Selection(
        [
            ("granted", "Granted"),
            ("denied", "Denied"),
        ],
        required=True,
        tracking=True,
    )
    context_payload = fields.Json(
        default=dict,
        help="Additional context captured at the time of consent (tool parameters, etc.)",
    )
    timestamp = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    expired = fields.Boolean(compute="_compute_expired", store=True)

    @api.depends("timestamp", "template_id.ttl_days", "decision")
    def _compute_expired(self):
        now = fields.Datetime.now()
        for record in self:
            if record.decision != "granted":
                record.expired = True
                continue

            ttl_days = record.template_id.ttl_days or 0
            if ttl_days <= 0 or not record.timestamp:
                record.expired = False
                continue

            expires_at = record.timestamp + timedelta(days=ttl_days)
            record.expired = expires_at < now

    @api.model
    def _ensure_tool_requires_consent(self, tool):
        tool_tags = {tag.name.lower() for tag in getattr(tool, "tag_ids", [])}
        if "user-consent" in tool_tags and not getattr(tool, "mcp_consent_template_id", False):
            raise UserError(
                _("Tool %s requires a consent template due to user-consent tag.")
                % (tool.display_name,),
            )

    @api.model
    def log_decision(self, tool, template, decision, user=None, context_payload=None):
        tool = tool.sudo() if tool else tool
        template = template.sudo() if template else template
        user = user or self.env.user
        context_payload = context_payload or {}

        if not tool or not template:
            raise UserError(_("A tool and consent template are required to log consent."))

        return self.create(
            {
                "tool_id": tool.id,
                "template_id": template.id,
                "decision": decision,
                "user_id": user.id,
                "context_payload": context_payload,
            }
        )

    @api.model
    def enforce_consent(self, tool, user=None, context_payload=None):
        """Check consent for a tool and user, raising if none is valid."""

        tool = tool.sudo()
        user = (user or self.env.user).sudo()
        context_payload = context_payload or {}

        if self.env.context.get("is_mcp"):
            # MCP requests already satisfied consent via administrative token approval.
            return False

        latest_entry = self.search(
            [
                ("tool_id", "=", tool.id),
                ("user_id", "=", user.id),
            ],
            order="timestamp desc",
            limit=1,
        )
        if latest_entry and latest_entry.decision == "denied":
            raise UserError(
                _(
                    "Consent has been revoked for tool %(tool)s.",
                    tool=tool.display_name,
                )
            )

        template_model = self.env["llm.mcp.consent.template"]
        template = template_model._select_template_for_tool(tool)

        self._ensure_tool_requires_consent(tool)

        if not template:
            # If the tool is tagged for consent, absence of template already raised.
            return False

        existing = self.search(
            [
                ("tool_id", "=", tool.id),
                ("template_id", "=", template.id),
                ("user_id", "=", user.id),
                ("decision", "=", "granted"),
                ("expired", "=", False),
            ],
            limit=1,
        )
        if existing:
            return existing

        if template.default_opt == "opt_out":
            return self.log_decision(
                tool,
                template,
                decision="granted",
                user=user,
                context_payload=context_payload,
            )

        raise UserError(
            _(
                "Consent required for tool %(tool)s. Message: %(message)s",
                tool=tool.display_name,
                message=(template.message_html or _("Consent not yet granted")),
            )
        )

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMToolTag(models.Model):
    _name = "llm.tool.tag"
    _description = "LLM Tool Tag"

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _sql_constraints = [
        ("llm_tool_tag_name_unique", "unique(name)", "Tool tag must be unique."),
    ]


class LLMToolRunner(models.Model):
    _name = "llm.tool.runner"
    _description = "LLM Tool Runner"

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    runner_type = fields.Selection(
        [
            ("local", "Local"),
            ("python_subprocess", "Python Subprocess"),
            ("remote_api", "Remote API"),
        ],
        required=True,
        default="local",
    )
    notes = fields.Text(help="Describe how this runner is configured or deployed")


class LLMToolDefinition(models.Model):
    _name = "llm.tool.definition"
    _description = "LLM Tool Definition"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    action_type = fields.Selection(
        [
            ("read", "Read"),
            ("create", "Create"),
            ("update", "Update"),
            ("method", "Call Method"),
            ("external_api", "External API"),
        ],
        required=True,
        tracking=True,
    )
    description = fields.Text(required=True)
    enabled = fields.Boolean(default=True, tracking=True)
    tag_ids = fields.Many2many(
        "llm.tool.tag",
        string="Tags",
        help="Label the tool with behavioral tags (destructive, idempotent, open-world, user-consent)",
    )
    target_model = fields.Char(
        help="Technical model name this tool targets (for CRUD/method actions)",
    )
    schema_json = fields.Json(default=dict, help="JSON schema describing tool inputs")
    redaction_policy_json = fields.Json(
        default=dict,
        help="JSON policy defining which payload fields should be redacted in logs.",
    )
    consent_template_id = fields.Many2one(
        "llm.tool.consent.config",
        string="Consent Template",
        ondelete="restrict",
    )
    is_open_world = fields.Boolean(
        string="Open World",
        help="Allow unauthenticated agent sessions to discover and call this tool when using token access.",
    )
    access_group_ids = fields.Many2many(
        "res.groups",
        string="Allowed Groups",
        help="Restrict tool visibility to specific security groups",
    )
    version_ids = fields.One2many("llm.tool.version", "tool_id", string="Versions")
    binding_ids = fields.One2many("llm.tool.binding", "tool_id", string="Bindings")
    latest_version_id = fields.Many2one(
        "llm.tool.version",
        compute="_compute_latest_version",
        store=True,
    )

    _sql_constraints = [
        (
            "llm_tool_definition_name_unique",
            "unique(name)",
            "Tool definition names must be unique.",
        ),
    ]

    @api.depends("version_ids", "version_ids.created_at")
    def _compute_latest_version(self):
        for record in self:
            latest = False
            if record.version_ids:
                latest = record.version_ids.sorted(
                    key=lambda v: (v.created_at, v.version), reverse=True
                )[:1]
                latest = latest[0]
            record.latest_version_id = latest

    @staticmethod
    def _compute_schema_hash(schema):
        normalized = schema or {}
        serialized = json.dumps(normalized, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _requires_target_model(self):
        return self.action_type in {"read", "create", "update", "method"}

    @api.constrains("action_type", "target_model")
    def _check_target_model_required(self):
        for record in self:
            if record._requires_target_model() and not record.target_model:
                raise ValidationError(
                    _(
                        "Target model is required for read, create, update, or method actions."
                    )
                )

    def _has_any_consent_template(self):
        self.ensure_one()
        return bool(self.consent_template_id)

    @api.constrains("tag_ids", "consent_template_id")
    def _check_consent_tags(self):
        for record in self:
            tag_names = {tag.name.lower() for tag in record.tag_ids}
            if "user-consent" in tag_names and not record._has_any_consent_template():
                raise ValidationError(
                    _("A consent template is required when the user-consent tag is set."),
                )

    def next_version_number(self):
        self.ensure_one()
        if not self.version_ids:
            return 1
        return max(self.version_ids.mapped("version")) + 1

    def _ensure_schema_version_on_save(self, change_log=None):
        version_model = self.env["llm.tool.version"]
        for record in self:
            current_hash = record._compute_schema_hash(record.schema_json)
            if record.latest_version_id and record.latest_version_id.schema_hash == current_hash:
                continue
            version_model.create(
                {
                    "tool_id": record.id,
                    "schema_hash": current_hash,
                    "change_log": change_log or _("Schema snapshot"),
                }
            )

    def validate_payload(self, payload):
        builder = self.env["llm.tool.schema.builder"]
        for record in self:
            builder.validate_payload(record.schema_json, payload)

    @api.model_create_multi
    def create(self, vals_list):
        builder = self.env["llm.tool.schema.builder"]
        prepared_vals = []
        for vals in vals_list:
            vals = dict(vals)
            vals["schema_json"] = builder.prepare_schema_for_create(vals)
            prepared_vals.append(vals)
        tools = super().create(prepared_vals)
        tools._ensure_schema_version_on_save(change_log=_("Initial schema version"))
        return tools

    def write(self, vals):
        if self.env.context.get("skip_schema_autogen"):
            return super().write(vals)

        builder = self.env["llm.tool.schema.builder"]
        vals = dict(vals)
        previous_hashes = {
            tool.id: tool._compute_schema_hash(tool.schema_json) for tool in self
        }

        result = super().write(vals)

        for tool in self:
            target_schema = builder.prepare_schema_for_write(tool, vals)
            if target_schema != tool.schema_json:
                tool.with_context(skip_schema_autogen=True).write(
                    {"schema_json": target_schema}
                )
            new_hash = tool._compute_schema_hash(tool.schema_json)
            if new_hash != previous_hashes.get(tool.id):
                tool._ensure_schema_version_on_save(
                    change_log=_("Schema updated after save")
                )
        return result


class LLMToolVersion(models.Model):
    _name = "llm.tool.version"
    _description = "LLM Tool Version"
    _order = "created_at desc, version desc"

    tool_id = fields.Many2one(
        "llm.tool.definition",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="tool_id.company_id",
        store=True,
        readonly=True,
    )
    version = fields.Integer(required=True)
    schema_hash = fields.Char(required=True)
    change_log = fields.Text()
    created_at = fields.Datetime(default=fields.Datetime.now, required=True)

    _sql_constraints = [
        (
            "llm_tool_version_unique",
            "unique(tool_id, version)",
            "A version number can only be used once per tool.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tool = self.env["llm.tool.definition"].browse(vals.get("tool_id"))
            if tool:
                if not vals.get("version"):
                    vals["version"] = tool.next_version_number()
                expected_hash = tool._compute_schema_hash(tool.schema_json)
                provided_hash = vals.get("schema_hash")
                if provided_hash and provided_hash != expected_hash:
                    raise ValidationError(
                        _("Schema hash does not match the current tool schema."),
                    )
                vals.setdefault("schema_hash", expected_hash)
        return super().create(vals_list)

    @api.constrains("schema_hash")
    def _check_schema_hash(self):
        for record in self:
            expected = record.tool_id._compute_schema_hash(record.tool_id.schema_json)
            if record.schema_hash != expected:
                raise ValidationError(
                    _("Schema hash does not match the current tool schema."),
                )


class LLMToolBinding(models.Model):
    _name = "llm.tool.binding"
    _description = "LLM Tool Binding"

    name = fields.Char(default="Binding", required=True)
    tool_id = fields.Many2one(
        "llm.tool.definition",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="tool_id.company_id",
        store=True,
        readonly=True,
    )
    version_id = fields.Many2one(
        "llm.tool.version",
        string="Version",
        ondelete="restrict",
    )
    runner_id = fields.Many2one(
        "llm.tool.runner",
        string="Runner",
        required=True,
        ondelete="restrict",
    )
    executor_path = fields.Char(required=True)
    timeout = fields.Integer(default=60)
    max_retries = fields.Integer(default=0)
    retry_interval = fields.Integer(
        default=0, help="Base delay (in seconds) before retrying a failed execution"
    )
    retry_strategy = fields.Selection(
        [("fixed", "Fixed"), ("exponential", "Exponential")],
        default="fixed",
        help="Choose how retry delays are applied when executions fail",
    )
    rate_limit = fields.Integer(help="Maximum allowed executions per minute")
    sandbox_mode = fields.Boolean(default=False)
    dry_run = fields.Boolean(default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tool = self.env["llm.tool.definition"].browse(vals.get("tool_id"))
            if tool and not vals.get("version_id"):
                version = self.env["llm.tool.version"].create(
                    {
                        "tool_id": tool.id,
                        "version": tool.next_version_number(),
                        "schema_hash": tool._compute_schema_hash(tool.schema_json),
                        "change_log": _(
                            "Auto-created for binding %(name)s", {"name": tool.name}
                        ),
                    }
                )
                vals["version_id"] = version.id
        bindings = super().create(vals_list)
        bindings._check_version_alignment()
        return bindings

    @api.constrains("timeout", "max_retries", "retry_interval")
    def _check_positive_values(self):
        for record in self:
            if record.timeout is not None and record.timeout <= 0:
                raise ValidationError(_("Timeout must be a positive integer."))
            if record.max_retries is not None and record.max_retries < 0:
                raise ValidationError(_("Max retries cannot be negative."))
            if record.retry_interval is not None and record.retry_interval < 0:
                raise ValidationError(_("Retry interval cannot be negative."))

    @api.constrains("version_id")
    def _check_version_alignment(self):
        for record in self:
            if record.version_id and record.version_id.tool_id != record.tool_id:
                raise ValidationError(
                    _("The binding version must belong to the same tool definition."),
                )
            if record.tool_id:
                expected_hash = record.tool_id._compute_schema_hash(
                    record.tool_id.schema_json
                )
                if record.version_id and record.version_id.schema_hash != expected_hash:
                    raise ValidationError(
                        _(
                            "Version schema hash does not match the current tool definition schema."
                        ),
                    )

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMMCPInvocationRecord(models.Model):
    _name = "llm.mcp.invocation.record"
    _description = "LLM MCP Invocation Record"
    _inherit = ["mail.thread"]
    _order = "start_time desc, id desc"

    session_id = fields.Char(index=True, tracking=True)
    tool_version_id = fields.Many2one(
        "llm.tool.version",
        string="Tool Version",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    tool_id = fields.Many2one(
        related="tool_version_id.tool_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="tool_id.company_id",
        store=True,
        readonly=True,
    )
    params_redacted = fields.Json(
        help="Invocation parameters with sensitive fields redacted",
    )
    result_redacted = fields.Json(
        help="Execution result with sensitive fields redacted",
    )
    runner_id = fields.Many2one(
        "llm.mcp.command.runner",
        string="Command Runner",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
        tracking=True,
    )
    start_time = fields.Datetime(default=fields.Datetime.now, tracking=True)
    end_time = fields.Datetime(tracking=True)
    latency_ms = fields.Integer(compute="_compute_latency", store=True)
    result_json = fields.Json()
    exception_trace = fields.Text()
    consent_ledger_id = fields.Many2one(
        "llm.mcp.consent.ledger",
        string="Consent Ledger Entry",
        ondelete="set null",
        tracking=True,
    )
    timeout_flag = fields.Boolean(default=False, help="Set when execution timed out")
    parent_invocation_id = fields.Many2one(
        "llm.mcp.invocation.record",
        string="Parent Invocation",
        ondelete="cascade",
        help="Optional parent flow invocation this execution belongs to.",
    )
    child_invocation_ids = fields.One2many(
        "llm.mcp.invocation.record",
        "parent_invocation_id",
        string="Child Invocations",
    )
    audit_trail_ids = fields.One2many(
        "llm.mcp.audit.trail",
        "invocation_id",
        string="Audit Events",
    )

    @api.depends("start_time", "end_time")
    def _compute_latency(self):
        for record in self:
            if record.start_time and record.end_time:
                delta = record.end_time - record.start_time
                record.latency_ms = int(delta.total_seconds() * 1000)
            else:
                record.latency_ms = 0

    @api.constrains("end_time", "start_time")
    def _check_time_order(self):
        for record in self:
            if record.end_time and record.start_time and record.end_time < record.start_time:
                raise ValidationError(_("End time cannot be earlier than start time."))

    @api.model
    def _redact_payload(self, tool, payload):
        engine = self.env["llm.tool.redaction.engine"]
        return engine.redact_payload(tool, payload)

    @api.model
    def log_invocation(
        self,
        tool_version,
        runner,
        params=None,
        status="pending",
        start_time=None,
        end_time=None,
        result=None,
        exception_trace=None,
        consent_ledger=None,
        session_id=None,
        event_details=None,
        parent_invocation=None,
    ):
        params = params or {}
        start_time = start_time or fields.Datetime.now()
        end_time = end_time or start_time
        tool_version = tool_version.sudo()
        runner = runner.sudo()
        parent_invocation = parent_invocation or self.env.context.get(
            "parent_invocation"
        )
        if isinstance(parent_invocation, int):
            parent_invocation = self.browse(parent_invocation)

        redacted = self._redact_payload(tool_version.tool_id, params)
        redacted_result = self._redact_payload(tool_version.tool_id, result or {})

        record = self.create(
            {
                "session_id": session_id,
                "tool_version_id": tool_version.id,
                "runner_id": runner.id,
                "params_redacted": redacted,
                "result_redacted": redacted_result,
                "status": status,
                "start_time": start_time,
                "end_time": end_time,
                "result_json": redacted_result,
                "exception_trace": exception_trace,
                "consent_ledger_id": getattr(consent_ledger, "id", False),
                "parent_invocation_id": getattr(parent_invocation, "id", False),
            }
        )

        event_type = "start" if status == "pending" else status
        severity = "error" if status == "failed" else "info"
        record._log_event(
            event_type=event_type,
            details=self._redact_payload(tool_version.tool_id, event_details or params),
            severity=severity,
            system_flagged=status == "failed",
        )
        return record

    def _log_event(self, event_type, details=None, severity="info", system_flagged=False):
        self.ensure_one()
        redacted_details = self._redact_payload(self.tool_id, details)
        return self.env["llm.mcp.audit.trail"].create(
            {
                "invocation_id": self.id,
                "event_type": event_type,
                "details_json": redacted_details or {},
                "severity": severity,
                "system_flagged": system_flagged,
            }
        )


class LLMMCPAuditTrail(models.Model):
    _name = "llm.mcp.audit.trail"
    _description = "LLM MCP Audit Trail"
    _order = "created_at desc, id desc"

    invocation_id = fields.Many2one(
        "llm.mcp.invocation.record",
        string="Invocation",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="invocation_id.company_id",
        store=True,
        readonly=True,
    )
    event_type = fields.Selection(
        [
            ("start", "Start"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("retry", "Retry"),
            ("retry_exhausted", "Retry Exhausted"),
            ("consent", "Consent"),
            ("timeout", "Timeout"),
            ("warning", "Warning"),
        ],
        required=True,
        default="start",
    )
    details_json = fields.Json(default=dict)
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("error", "Error")],
        default="info",
        required=True,
    )
    created_at = fields.Datetime(default=fields.Datetime.now, required=True)
    system_flagged = fields.Boolean(
        default=False,
        help="Flagged by automated controls (e.g., circuit breaker, consent failure).",
    )

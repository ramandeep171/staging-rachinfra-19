from datetime import timedelta

from odoo import fields
from odoo.tests import SavepointCase


class TestInvocationAudit(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invocation_model = cls.env["llm.mcp.invocation.record"]
        cls.audit_model = cls.env["llm.mcp.audit.trail"]
        cls.consent_template_model = cls.env["llm.mcp.consent.template"]
        cls.consent_ledger_model = cls.env["llm.mcp.consent.ledger"]
        cls.tool_model = cls.env["llm.tool.definition"]
        cls.tool_version_model = cls.env["llm.tool.version"]
        cls.server_model = cls.env["llm.mcp.server"]
        cls.runner_model = cls.env["llm.mcp.command.runner"]

        cls.tool = cls.tool_model.create(
            {
                "name": "send_whatsapp_message",
                "action_type": "external_api",
                "description": "Send WhatsApp message",
                "schema_json": {"type": "object", "properties": {"message": {"type": "string"}}},
            }
        )
        cls.tool_version = cls.tool_version_model.create({"tool_id": cls.tool.id})

        cls.server = cls.server_model.create(
            {
                "name": "Local Agent Server",
                "transport_types": "local_agent",
                "host_config_json": {},
            }
        )
        cls.runner = cls.runner_model.create(
            {
                "name": "Local Runner",
                "server_id": cls.server.id,
                "type": "local_agent",
                "entrypoint": "local",
            }
        )

    def test_successful_invocation_records_and_audit(self):
        template = self.consent_template_model.create(
            {"name": "Tool Consent", "scope": "tool", "default_opt": "opt_out"}
        )
        ledger = self.consent_ledger_model.log_decision(
            self.tool, template, decision="granted", user=self.env.user
        )

        start_time = fields.Datetime.now()
        end_time = start_time + timedelta(seconds=1)

        record = self.invocation_model.log_invocation(
            self.tool_version,
            self.runner,
            params={"api_key": "secret", "message": "hello"},
            status="success",
            start_time=start_time,
            end_time=end_time,
            result={"ok": True},
            consent_ledger=ledger,
        )

        self.assertEqual(record.status, "success")
        self.assertEqual(record.params_redacted.get("api_key"), "**REDACTED**")
        self.assertEqual(record.params_redacted.get("message"), "hello")
        self.assertGreater(record.latency_ms, 0)
        self.assertEqual(record.consent_ledger_id, ledger)

        audit_events = self.audit_model.search([("invocation_id", "=", record.id)])
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events.event_type, "success")
        self.assertEqual(audit_events.severity, "info")

    def test_failed_invocation_logs_error_audit(self):
        start_time = fields.Datetime.now()
        end_time = start_time + timedelta(milliseconds=500)
        record = self.invocation_model.log_invocation(
            self.tool_version,
            self.runner,
            params={"token": "abc123"},
            status="failed",
            start_time=start_time,
            end_time=end_time,
            exception_trace="Traceback: boom",
        )

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.params_redacted.get("token"), "**REDACTED**")
        self.assertGreater(record.latency_ms, 0)

        audit_events = self.audit_model.search([("invocation_id", "=", record.id)])
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events.event_type, "failed")
        self.assertEqual(audit_events.severity, "error")
        self.assertTrue(audit_events.system_flagged)

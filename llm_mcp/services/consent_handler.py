from datetime import timedelta
import os

try:
    from odoo import api, fields, models
    from odoo.exceptions import UserError
except ImportError:

    class _ApiStub:
        def __getattr__(self, _name):
            def decorator(*_args, **_kwargs):
                def wrapper(method):
                    return method

                return wrapper

            return decorator

    class _FieldFactory:
        def __init__(self, _name):
            self._name = _name

        def __call__(self, *args, **kwargs):
            return None

        def __getattr__(self, _attr):
            def _inner(*_args, **_kwargs):
                return None

            return _inner

    class _FieldsStub:
        def __getattr__(self, _name):
            return _FieldFactory(_name)

    class _ModelsStub:
        class Model:
            pass

        class TransientModel:
            pass

        class AbstractModel:
            pass

    class UserError(Exception):
        pass

    api = _ApiStub()
    fields = _FieldsStub()
    models = _ModelsStub()


class ConsentHandlerService(models.AbstractModel):
    _name = "llm.mcp.consent.handler"
    _description = "LLM MCP Consent Handler"

    @api.model
    def _get_template(self, tool):
        return self.env["llm.mcp.consent.template"]._select_template_for_tool(tool)

    @api.model
    def request_consent(self, tool, user=None, decision=None, context_payload=None):
        user = (user or self.env.user).sudo()
        tool = tool.sudo()
        context_payload = context_payload or {}

        template = self._get_template(tool)
        if not template:
            return {"status": "granted", "scope": None, "message": None, "ledger_id": None}

        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()

        latest_entry = ledger_model.search(
            [
                ("tool_id", "=", tool.id),
                ("user_id", "=", user.id),
            ],
            order="timestamp desc",
            limit=1,
        )

        if decision == "granted":
            ledger = ledger_model.log_decision(
                tool,
                template,
                decision="granted",
                user=user,
                context_payload=context_payload,
            )
            return {
                "status": "granted",
                "scope": template.scope,
                "message": None,
                "ledger_id": ledger.id,
            }

        if latest_entry and latest_entry.decision == "denied":
            return {
                "status": "blocked",
                "scope": template.scope,
                "message": template.message_html or "Consent revoked",
                "ledger_id": latest_entry.id,
            }

        active_grant = ledger_model.search(
            [
                ("tool_id", "=", tool.id),
                ("template_id", "=", template.id),
                ("user_id", "=", user.id),
                ("decision", "=", "granted"),
                ("expired", "=", False),
            ],
            limit=1,
        )
        if active_grant:
            return {
                "status": "granted",
                "scope": template.scope,
                "message": None,
                "ledger_id": active_grant.id,
            }

        if template.default_opt == "opt_out":
            ledger = ledger_model.log_decision(
                tool,
                template,
                decision="granted",
                user=user,
                context_payload=context_payload,
            )
            return {
                "status": "granted",
                "scope": template.scope,
                "message": None,
                "ledger_id": ledger.id,
            }

        if decision == "denied":
            return {
                "status": "blocked",
                "scope": template.scope,
                "message": template.message_html or "Consent denied",
                "ledger_id": None,
            }

        return {
            "status": "required",
            "scope": template.scope,
            "message": template.message_html or "Consent required",
            "ledger_id": None,
        }

    @api.model
    def revoke_consent(self, user=None, ledger=None, tool=None):
        user = (user or self.env.user).sudo()
        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()

        ledger_to_revoke = ledger
        if not ledger_to_revoke and tool:
            ledger_to_revoke = ledger_model.search(
                [
                    ("tool_id", "=", tool.id),
                    ("user_id", "=", user.id),
                    ("decision", "=", "granted"),
                    ("expired", "=", False),
                ],
                limit=1,
            )

        if not ledger_to_revoke:
            return {"status": "revoked", "message": "No active consent found"}

        template = ledger_to_revoke.template_id
        if not template:
            raise UserError("Consent template missing for ledger entry")

        # Mark the prior consent as expired and add a denial entry to block execution.
        ledger_to_revoke.write(
            {
                "timestamp": fields.Datetime.now() - timedelta(days=max(template.ttl_days, 1)),
            }
        )

        denial = ledger_model.log_decision(
            tool=ledger_to_revoke.tool_id,
            template=template,
            decision="denied",
            user=user,
            context_payload={"reason": "revoked"},
        )

        return {
            "status": "revoked",
            "scope": template.scope,
            "message": "Consent revoked",
            "ledger_id": denial.id,
        }


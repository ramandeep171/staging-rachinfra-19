from odoo import _, api, models
from odoo.exceptions import UserError


class MCPPolicyEnforcer(models.AbstractModel):
    _name = "llm.mcp.policy.enforcer"
    _description = "MCP Consent Policy Enforcer"

    @api.model
    def enforce_consent_policy(self, user=None, tool=None, session_id=None):
        user = (user or self.env.user).sudo()
        tool = tool.sudo() if tool else tool
        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()
        template_model = self.env["llm.mcp.consent.template"].sudo()

        if not tool:
            raise UserError(_("Tool is required for consent enforcement."))

        # Validate tagging requirements before template selection.
        ledger_model._ensure_tool_requires_consent(tool)

        template = template_model._select_template_for_tool(tool)
        if not template:
            return {
                "status": "ALLOW",
                "ledger": False,
                "message": None,
                "enforced": False,
                "session_id": session_id,
            }

        latest_entry = ledger_model.search(
            [
                ("tool_id", "=", tool.id),
                ("user_id", "=", user.id),
            ],
            order="timestamp desc",
            limit=1,
        )

        if latest_entry and latest_entry.decision == "denied" and not latest_entry.expired:
            return {
                "status": "BLOCK",
                "ledger": latest_entry,
                "message": template.message_html
                or _("Consent has been revoked for tool %(tool)s", tool=tool.display_name),
                "enforced": True,
                "session_id": session_id,
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
                "status": "ALLOW",
                "ledger": active_grant,
                "message": None,
                "enforced": True,
                "session_id": session_id,
            }

        if latest_entry and latest_entry.decision == "granted" and latest_entry.expired:
            return {
                "status": "BLOCK",
                "ledger": latest_entry,
                "message": _(
                    "Consent expired for tool %(tool)s and must be re-approved.",
                    tool=tool.display_name,
                ),
                "enforced": True,
                "session_id": session_id,
            }

        if template.default_opt == "opt_out":
            ledger = ledger_model.log_decision(
                tool,
                template,
                decision="granted",
                user=user,
                context_payload={"session_id": session_id, "auto": True},
            )
            return {
                "status": "ALLOW",
                "ledger": ledger,
                "message": None,
                "enforced": True,
                "session_id": session_id,
            }

        return {
            "status": "REQUIRE_UI_APPROVAL",
            "ledger": False,
            "message": template.message_html
            or _("Consent required for tool %(tool)s.", tool=tool.display_name),
            "enforced": True,
            "session_id": session_id,
        }

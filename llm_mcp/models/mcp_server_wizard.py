import os

try:
    from odoo import _, fields, models
except ImportError:

    def _(message):
        return message

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

    fields = _FieldsStub()
    models = _ModelsStub()


class LLMMCPServerWizard(models.TransientModel):
    _name = "llm.mcp.server.wizard"
    _description = "MCP Server Creation Wizard"

    name = fields.Char(required=True, default="New MCP Server")
    transport_types = fields.Selection(
        [
            ("stdio", "Standard IO"),
            ("local_agent", "Local Agent"),
            ("python_subprocess", "Python Subprocess"),
            ("remote_api", "Remote API"),
            ("http", "HTTP"),
            ("websocket", "Websocket"),
        ],
        default="stdio",
        required=True,
    )
    command = fields.Char(help="Executable command for stdio transports.")
    args = fields.Char(help="Command arguments for stdio transports.")
    host_config_json = fields.Json(default=dict, help="Host or endpoint configuration")
    provider_whitelist_ids = fields.Many2many(
        "llm.provider",
        string="Allowed Providers",
    )
    audit_flags = fields.Selection(
        [
            ("none", "No Audit"),
            ("log", "Log Only"),
            ("enforce", "Enforce Consent/Scope"),
        ],
        default="log",
        required=True,
    )
    runner_line_ids = fields.One2many(
        "llm.mcp.server.wizard.runner",
        "wizard_id",
        string="Runners",
    )

    def action_create_server(self):
        self.ensure_one()
        server_vals = {
            "name": self.name,
            "transport_types": self.transport_types,
            "command": self.command,
            "args": self.args,
            "host_config_json": self.host_config_json or {},
            "provider_whitelist_ids": [(6, 0, self.provider_whitelist_ids.ids)],
            "audit_flags": self.audit_flags,
        }
        server = self.env["llm.mcp.server"].create(server_vals)

        for line in self.runner_line_ids:
            runner_vals = {
                "name": line.name,
                "server_id": server.id,
                "runner_type": line.runner_type,
                "entrypoint": line.entrypoint,
                "auth_headers": line.auth_headers or {},
                "retry_policy": line.retry_policy or {"retries": 0},
                "sandbox_mode": line.sandbox_mode,
                "enabled": line.enabled,
                "allowed_tool_ids": [(6, 0, line.allowed_tool_ids.ids)],
            }
            self.env["llm.mcp.command.runner"].create(runner_vals)

        return {
            "type": "ir.actions.act_window",
            "name": _("MCP Server"),
            "res_model": "llm.mcp.server",
            "res_id": server.id,
            "view_mode": "form",
            "target": "current",
        }


class LLMMCPServerWizardRunner(models.TransientModel):
    _name = "llm.mcp.server.wizard.runner"
    _description = "MCP Server Wizard Runner Line"

    wizard_id = fields.Many2one("llm.mcp.server.wizard", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    runner_type = fields.Selection(
        [
            ("local_agent", "Local Agent"),
            ("python_subprocess", "Python Subprocess"),
            ("remote_api", "Remote API"),
            ("http", "HTTP"),
            ("websocket", "Websocket"),
        ],
        default="remote_api",
        required=True,
    )
    entrypoint = fields.Char(help="Command path or endpoint URL")
    auth_headers = fields.Json(default=dict)
    retry_policy = fields.Json(default=lambda self: {"retries": 0})
    sandbox_mode = fields.Boolean(default=True)
    enabled = fields.Boolean(default=True)
    allowed_tool_ids = fields.Many2many("llm.tool", string="Allowed Tools")

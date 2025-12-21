from odoo import _, api, models
from odoo.exceptions import UserError


class MCPBindingResolver(models.AbstractModel):
    _name = "llm.mcp.binding.resolver"
    _description = "MCP Binding Resolver"

    @api.model
    def resolve(self, tool_key):
        """Resolve tool, version, binding, and command runner for execution."""
        tool = (
            self.env["llm.tool.definition"]
            .sudo()
            .search([("name", "=", tool_key)], limit=1)
        )
        if not tool or not tool.enabled:
            raise UserError(_("Tool %s is not available or disabled") % tool_key)

        binding = tool.binding_ids[:1]
        if not binding:
            raise UserError(_("No binding configured for tool %s") % tool.display_name)
        if not binding.runner_id:
            raise UserError(_("Binding %s is missing an execution runner") % binding.display_name)

        version = binding.version_id or tool.latest_version_id
        if not version:
            raise UserError(_("No version available for tool %s") % tool.display_name)

        runner_type_map = {
            "local": "local_agent",
            "python_subprocess": "python_subprocess",
            "remote_api": "remote_api",
            "http": "http",
            "websocket": "websocket",
        }
        resolved_type = runner_type_map.get(binding.runner_id.runner_type)
        if not resolved_type:
            raise UserError(
                _("Runner type %s is not supported for MCP dispatch")
                % binding.runner_id.runner_type
            )

        command_runner = (
            self.env["llm.mcp.command.runner"]
            .sudo()
            .search(
                [
                    ("type", "=", resolved_type),
                    ("enabled", "=", True),
                ],
                limit=1,
            )
        )
        if not command_runner:
            raise UserError(
                _("No command runner available for runner type %s")
                % (resolved_type or binding.runner_id.runner_type)
            )

        return {
            "tool": tool,
            "binding": binding,
            "runner": command_runner,
            "version": version,
        }

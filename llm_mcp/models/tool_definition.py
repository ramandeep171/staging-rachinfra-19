import os

try:
    from odoo import fields, models
except ImportError:

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


class LLMToolDefinition(models.Model):
    _inherit = "llm.tool.definition"

    mcp_consent_template_id = fields.Many2one(
        "llm.mcp.consent.template",
        string="MCP Consent Template",
        ondelete="restrict",
        help="Template used to enforce runtime consent when the tool is executed via MCP or agent flows.",
    )

    def _has_any_consent_template(self):
        res = super()._has_any_consent_template()
        if res:
            return res
        return bool(self.mcp_consent_template_id)

import sys
import types

if "odoo" not in sys.modules:
    odoo_stub = types.SimpleNamespace()
    api_stub = types.SimpleNamespace()

    def _decorator(*_args, **_kwargs):  # pragma: no cover - pytest stub
        def _wrap(func):
            return func

        return _wrap

    api_stub.model = api_stub.constrains = api_stub.depends = _decorator

    class _FieldFactory:
        def __init__(self, _name):
            self._name = _name

        def __call__(self, *args, **kwargs):
            return None

        def __getattr__(self, _attr):
            return lambda *a, **k: None

    class _Fields:
        def __getattr__(self, name):
            return _FieldFactory(name)

    class _Models:
        class Model:
            pass

        class TransientModel:
            pass

        class AbstractModel:
            pass

    class _Tests:
        class SavepointCase:
            pass

        class HttpCase:
            pass

        class TransactionCase:
            pass

    class _Exceptions:
        class UserError(Exception):
            pass

        class ValidationError(Exception):
            pass

        class AccessError(Exception):
            pass

    def _(message):
        return message

    odoo_stub._ = _
    odoo_stub.api = api_stub
    odoo_stub.fields = _Fields()
    odoo_stub.models = _Models()
    odoo_stub.tests = _Tests()
    odoo_stub.exceptions = _Exceptions()
    odoo_stub.__is_stub__ = True

    sys.modules["odoo"] = odoo_stub
    sys.modules["odoo.api"] = api_stub
    sys.modules["odoo.fields"] = odoo_stub.fields
    sys.modules["odoo.models"] = odoo_stub.models
    sys.modules["odoo.tests"] = _Tests()
    sys.modules["odoo.exceptions"] = _Exceptions()

from . import test_server_routing
from . import test_consent_enforcement
from . import test_invocation_audit
from . import test_api_consent
from . import test_execution_routing
from . import test_ui_server_wizard
from . import test_retry_logic
from . import test_policy_middleware
from . import test_api_registry
from . import test_tool_whatsapp
from . import test_tool_calendar
from . import test_flow_lead_followup
from . import test_redaction

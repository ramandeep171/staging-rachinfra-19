import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _name = "llm.provider"
    _inherit = ["mail.thread"]
    _description = "LLM Provider"

    name = fields.Char(required=True)
    backend_type = fields.Selection(
        selection=lambda self: self._selection_backend_type(),
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    api_key = fields.Char()
    api_base = fields.Char()
    model_ids = fields.One2many("llm.model", "provider_id", string="Models")
    model_variant_ids = fields.One2many(
        "llm.model.variant",
        "provider_id",
        string="Model Variants",
    )
    max_tokens = fields.Integer(help="Maximum tokens allowed per request for this provider")
    rate_limit = fields.Char(help="Rate limit guidance, e.g. requests per minute")
    default_model_id = fields.Many2one(
        "llm.model.variant",
        string="Default Model Variant",
        ondelete="set null",
    )

    _sql_constraints = [
        (
            "provider_name_unique",
            "unique(name, company_id)",
            "Provider name must be unique per company.",
        ),
    ]

    @api.constrains("name")
    def _check_unique_name(self):
        for record in self:
            if not record.name:
                continue

            existing = self.search(
                [
                    ("id", "!=", record.id),
                    ("company_id", "=", record.company_id.id),
                ]
            )
            existing_names_lower = {p.name.lower() for p in existing if p.name}
            if record.name.lower() in existing_names_lower:
                raise ValidationError(
                    _("The provider name must be unique (case-insensitive).")
                )

        return True

    @property
    def client(self):
        """Get client instance using dispatch pattern"""
        return self._dispatch("get_client")

    def _dispatch(self, method, *args, record=None, **kwargs):
        """Dispatch method call to appropriate service implementation on self or a given record."""
        if not self.backend_type:
            raise UserError(_("Provider service not configured"))

        service_method = f"{self.backend_type}_{method}"
        record = record if record else self
        record_name = record._name

        if not hasattr(record, service_method):
            raise NotImplementedError(
                _("Method '%s' not implemented for service '%s' on target '%s'")
                % (method, self.backend_type, record_name)
            )

        return getattr(record, service_method)(*args, **kwargs)

    @api.model
    def _selection_backend_type(self):
        """Get all available services from provider implementations"""
        services = []
        for provider in self._get_available_services():
            services.append(provider)
        return services

    @api.model
    def _get_available_services(self):
        """Hook method for registering provider services"""
        return [
            ("openai", "OpenAI"),
            ("ollama", "Ollama"),
            ("anthropic", "Anthropic"),
            ("custom", "Custom"),
        ]

    # -------------------------------------------------------------------------
    # OpenAI helpers and service implementation
    # -------------------------------------------------------------------------

    def _openai_api_base(self):
        """Return the OpenAI API base URL for this provider."""
        self.ensure_one()
        base = self.api_base or "https://api.openai.com/v1"
        return base.rstrip("/")

    def _openai_request(self, method, endpoint, payload=None, params=None, stream=False):
        """Execute an HTTP request against the OpenAI REST API."""
        self.ensure_one()
        if not self.api_key:
            raise UserError(
                _("An API key is required to communicate with OpenAI for provider %s.")
                % self.display_name
            )

        url = "%s/%s" % (self._openai_api_base(), endpoint.lstrip("/"))
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
        }

        request_kwargs = {
            "headers": headers,
            "timeout": 60,
            "stream": stream,
        }
        if payload is not None:
            request_kwargs["json"] = payload
        if params:
            request_kwargs["params"] = params

        try:
            response = requests.request(method, url, **request_kwargs)
        except requests.exceptions.RequestException as exc:
            _logger.exception("OpenAI request failed: %s", exc)
            raise UserError(_("Failed to reach OpenAI: %s") % exc) from exc

        if response.status_code >= 400:
            error_message = self._extract_openai_error(response)
            raise UserError(error_message)

        if stream:
            return response

        try:
            return response.json()
        except ValueError as exc:
            raise UserError(_("OpenAI returned an invalid JSON response.")) from exc

    @staticmethod
    def _extract_openai_error(response):
        """Return a readable error message from an HTTP error response."""
        status_message = _("OpenAI API call failed with status %s") % response.status_code
        try:
            payload = response.json()
        except ValueError:
            return status_message

        if not isinstance(payload, dict):
            return status_message

        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("code") or status_message
        return payload.get("message") or status_message

    def _normalize_openai_model(self, model_payload):
        """Normalize OpenAI model data to the structure expected by the wizard."""
        created_ts = model_payload.get("created")
        created_at = None
        if isinstance(created_ts, (int, float)):
            created_at = datetime.utcfromtimestamp(created_ts)

        permissions = model_payload.get("permission")
        if permissions is None:
            permissions = model_payload.get("permissions")

        details = {
            "id": model_payload.get("id"),
            "object": model_payload.get("object"),
            "type": model_payload.get("type"),
            "owned_by": model_payload.get("owned_by"),
            "root": model_payload.get("root"),
            "parent": model_payload.get("parent"),
            "created_at": created_at,
            "permission": permissions,
            "capabilities": self._openai_detect_capabilities(
                model_payload.get("id"), model_payload
            ),
        }

        description = model_payload.get("description")
        if description:
            details["description"] = description

        status = model_payload.get("status")
        if status:
            details["status"] = status

        return self.serialize_model_data(
            {key: value for key, value in details.items() if value not in (None, [], {})}
        )

    @staticmethod
    def _openai_detect_capabilities(model_name, payload=None):
        """Derive high-level capabilities for an OpenAI model."""
        payload = payload or {}
        name = (model_name or "").lower()
        model_type = (payload.get("type") or "").lower()

        capabilities = set()

        if "embedding" in name or model_type == "embedding":
            capabilities.add("embedding")

        if any(token in name for token in ["vision", "multimodal", "4o", "omni", "realtime"]):
            capabilities.add("multimodal")

        if any(token in name for token in ["audio", "tts", "speech"]):
            capabilities.add("audio")

        if "reasoning" in name or name.startswith("o1") or name.startswith("o3"):
            capabilities.add("reasoning")

        if "embedding" not in capabilities:
            capabilities.add("chat")

        return sorted(capabilities)

    def openai_models(self, model_id=None):
        """Fetch models from the OpenAI API."""
        self.ensure_one()
        endpoint = f"models/{model_id}" if model_id else "models"
        response = self._openai_request("GET", endpoint)

        if model_id:
            models_data = [response]
        else:
            models_data = response.get("data", [])

        payload = []
        for model_payload in models_data:
            name = model_payload.get("id")
            if not name:
                continue
            payload.append(
                {
                    "name": name,
                    "details": self._normalize_openai_model(model_payload),
                }
            )

        return payload

    @api.constrains("max_tokens")
    def _check_max_tokens(self):
        for record in self:
            if record.max_tokens is not None and record.max_tokens <= 0:
                raise ValidationError(
                    _("Max tokens must be a positive integer when specified."),
                )

    @api.constrains("default_model_id")
    def _check_default_model_provider(self):
        for record in self:
            if (
                record.default_model_id
                and record.default_model_id.provider_id != record
            ):
                raise ValidationError(
                    _(
                        "The default model variant must belong to the same provider."
                    )
                )

    def chat(self, messages, model=None, stream=False, **kwargs):
        """Send chat messages using this provider"""
        return self._dispatch("chat", messages, model=model, stream=stream, **kwargs)

    def embedding(self, texts, model=None):
        """Generate embeddings using this provider"""
        return self._dispatch("embedding", texts, model=model)

    def generate(self, input_data, model=None, stream=False, **kwargs):
        """Generate content using this provider

        Args:
            input_data: Input data for generation (could be text, prompt, or structured data)
            model: Optional specific model to use
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters

        Returns:
            tuple: (output_dict, urls_list) where:
                - output_dict: Dictionary containing provider-specific output data
                - urls_list: List of dictionaries with URL metadata
        """
        return self._dispatch(
            "generate", input_data, model=model, stream=stream, **kwargs
        )

    def list_models(self, model_id=None):
        """List available models from the provider"""
        return self._dispatch("models", model_id=model_id)

    def action_fetch_models(self):
        """Fetch models from provider and open import wizard"""
        self.ensure_one()

        # Create wizard first so it has an ID
        wizard = self.env["llm.fetch.models.wizard"].create({
            "provider_id": self.id,
        })

        # Get existing models for comparison
        existing_models = {
            model.name: model
            for model in self.env["llm.model"].search([("provider_id", "=", self.id)])
        }

        # Fetch models from provider
        model_to_fetch = self._context.get("default_model_to_fetch")
        if model_to_fetch:
            models_data = self.list_models(model_id=model_to_fetch)
        else:
            models_data = self.list_models()

        # Track models to prevent duplicates
        wizard_models = set()
        lines_to_create = []

        for model_data in models_data:
            details = model_data.get("details", {})
            name = model_data.get("name") or details.get("id")

            if not name:
                continue

            # Skip duplicates
            if name in wizard_models:
                continue
            wizard_models.add(name)

            # Determine model use and capabilities
            capabilities = details.get("capabilities", ["chat"])
            model_use = self._determine_model_use(name, capabilities)

            # Check against existing models
            existing = existing_models.get(name)
            status = "new"
            if existing:
                status = "modified" if existing.details != details else "existing"

            lines_to_create.append({
                "wizard_id": wizard.id,
                "name": name,
                "model_use": model_use,
                "status": status,
                "details": details,
                "existing_model_id": existing.id if existing else False,
                "selected": status in ["new", "modified"],
            })

        # Create all lines
        if lines_to_create:
            self.env["llm.fetch.models.line"].create(lines_to_create)

        # Return action to open the wizard
        return {
            "type": "ir.actions.act_window",
            "res_model": "llm.fetch.models.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Import Models"),
        }

    def _determine_model_use(self, name, capabilities):
        """
        Determine the primary model use based on capabilities.

        This method classifies models into Odoo's model_use categories based on their
        capabilities. The classification follows a priority order from most specialized
        to most general.

        EXTENSION POINT: Override this method in your provider class to add custom
        model types or modify classification logic.

        Args:
            name (str): Model name/ID from the provider
            capabilities (list): List of capability strings (usually from API response)

        Returns:
            str: One of the model_use values from _get_available_model_usages()
                 Default options: "chat", "embedding", "multimodal", "completion", etc.

        Priority Order:
            1. embedding - Specialized embedding models
            2. multimodal - Models with vision/image understanding
            3. chat - General conversational models (default)

        Standard Capability Names:
            - "chat": Text-based conversations
            - "embedding"/"text-embedding": Vector embeddings
            - "multimodal"/"vision": Image/vision understanding
            - "completion": Text completion
            - "function_calling": Tool/function support
            Provider-specific: "ocr", "image_generation", etc.

        Example Override:
            ```python
            class MyProvider(models.Model):
                _inherit = "llm.provider"

                def _determine_model_use(self, name, capabilities):
                    # Add custom model type
                    if "ocr" in capabilities:
                        return "ocr"
                    # Fall back to parent logic for standard types
                    return super()._determine_model_use(name, capabilities)
            ```

        See Also:
            - llm_mistral.models.mistral_provider for a working example
            - _<provider>_parse_model() for setting capabilities
        """
        # Priority 1: Embedding models (specialized, distinct use case)
        if (
            any(cap in capabilities for cap in ["embedding", "text-embedding"])
            or "embedding" in name.lower()
        ):
            return "embedding"

        # Priority 2: Multimodal models (advanced capability)
        elif any(cap in capabilities for cap in ["multimodal", "vision"]):
            return "multimodal"

        # Priority 3: Chat models (default for most LLMs)
        return "chat"

    def get_model(self, model=None, model_use="chat"):
        """Get a model to use for the given purpose

        Args:
            model: Optional specific model to use
            model_use: Type of model to get if no specific model provided

        Returns:
            llm.model record to use
        """
        if model:
            return model

        # Get models from provider
        models = self.model_ids.filtered(lambda m: m.model_use == model_use)

        default_models = models.filtered("default")
        if not default_models:
            default_models = models.sorted("id")

        if not default_models:
            raise ValueError(f"No {model_use} model found for provider {self.name}")

        return default_models[0]

    def custom_models(self, model_id=None):
        """Expose locally configured models for providers using the 'custom' backend."""
        self.ensure_one()
        domain = [("provider_id", "=", self.id)]
        if model_id:
            domain.append(("name", "=", model_id))

        models = self.env["llm.model"].sudo().search(domain, order="name")
        payload = []
        for model in models:
            details = dict(model.details or {})
            details.setdefault("capabilities", [model.model_use])
            payload.append({"name": model.name, "details": details})
        return payload

    @staticmethod
    def serialize_datetime(obj):
        """Helper function to serialize datetime objects to ISO format strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    @staticmethod
    def serialize_model_data(data: dict) -> dict:
        """
        Recursively process dictionary to serialize datetime objects
        and handle any other non-serializable types.

        Args:
            data (dict): Dictionary potentially containing datetime objects

        Returns:
            dict: Processed dictionary with datetime objects converted to ISO strings
        """
        return {
            key: LLMProvider.serialize_datetime(value)
            if isinstance(value, datetime)
            else LLMProvider.serialize_model_data(value)
            if isinstance(value, dict)
            else [
                LLMProvider.serialize_model_data(item)
                if isinstance(item, dict)
                else LLMProvider.serialize_datetime(item)
                for item in value
            ]
            if isinstance(value, list)
            else value
            for key, value in data.items()
        }

    def format_tools(self, tools):
        """Format tools for the specific provider"""
        return self._dispatch("format_tools", tools)

    def format_messages(self, messages, system_prompt=None):
        """Format messages for this provider

        Args:
            messages: List of messages to format for specific provider, could be mail.message record set or similar data format
            system_prompt: Optional system prompt to include at the beginning of the messages

        Returns:
            List of formatted messages in provider-specific format
        """
        return self._dispatch("format_messages", messages, system_prompt=system_prompt)

    def _prepare_chat_params_base(self, model, messages, stream, tools=None, **kwargs):
        """Base chat parameter preparation - common across providers."""
        params = {
            "model": model.name,
            "stream": stream,
        }

        # Handle prepend_messages (new approach)
        prepend_messages = kwargs.get("prepend_messages")
        if prepend_messages and isinstance(prepend_messages, list):
            formatted_messages = self.format_messages(messages)
            params["messages"] = prepend_messages + formatted_messages
        else:
            params["messages"] = self.format_messages(messages)

        # Add tools if provided
        if tools:
            formatted_tools = self.format_tools(tools)
            if formatted_tools:
                params["tools"] = formatted_tools
                # Let each provider handle tool-specific parameters
                params.update(self._get_provider_tool_params(tools, kwargs))

        return params

    def _get_provider_tool_params(self, tools, kwargs):
        """Hook for provider-specific tool parameters."""
        return {}

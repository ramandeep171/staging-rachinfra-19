from odoo.exceptions import ValidationError
from odoo.tests import SavepointCase


class TestProviderAndModelVariant(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider_model = cls.env["llm.provider"]
        cls.model_variant_model = cls.env["llm.model.variant"]

    def test_create_provider_and_variant(self):
        provider = self.provider_model.create(
            {
                "name": "OpenAI",
                "backend_type": "openai",
                "api_base": "https://api.openai.com/v1",
                "api_key": "test-key",
                "max_tokens": 4096,
            }
        )

        variant = self.model_variant_model.create(
            {
                "name": "gpt-4o-mini",
                "provider_id": provider.id,
                "capabilities": "chat,function_calling",
                "function_calling": True,
                "vision_enabled": False,
                "context_window": 128000,
            }
        )

        provider.default_model_id = variant.id

        self.assertTrue(provider.enabled)
        self.assertEqual(provider.default_model_id, variant)
        self.assertEqual(variant.provider_id, provider)
        self.assertIn("chat", variant.capabilities)

    def test_invalid_context_window_raises(self):
        provider = self.provider_model.create(
            {
                "name": "Ollama",
                "backend_type": "ollama",
                "api_base": "http://localhost:11434",
            }
        )

        with self.assertRaises(ValidationError):
            self.model_variant_model.create(
                {
                "name": "llama3",
                "provider_id": provider.id,
                "context_window": -1,
            }
        )

    def test_invalid_max_tokens_raises(self):
        with self.assertRaises(ValidationError):
            self.provider_model.create(
                {
                    "name": "Anthropic",
                    "backend_type": "anthropic",
                    "api_base": "https://api.anthropic.com", 
                    "max_tokens": 0,
                }
            )

    def test_default_model_must_match_provider(self):
        provider_one = self.provider_model.create(
            {
                "name": "Provider A",
                "backend_type": "custom",
                "api_base": "https://example.com", 
            }
        )
        provider_two = self.provider_model.create(
            {
                "name": "Provider B",
                "backend_type": "custom",
                "api_base": "https://example.org",
            }
        )

        variant = self.model_variant_model.create(
            {
                "name": "variant-a",
                "provider_id": provider_one.id,
                "context_window": 2048,
            }
        )

        with self.assertRaises(ValidationError):
            provider_two.default_model_id = variant.id

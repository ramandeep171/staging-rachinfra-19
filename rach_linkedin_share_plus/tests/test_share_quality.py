"""Scaffolding tests for share flows (slug, redirect, logging)."""

import pytest

odoo = pytest.importorskip("odoo", reason="Odoo test environment required for share flow scaffolds.")
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestShareQuality(common.TransactionCase):
    """Lightweight placeholders to validate quality hooks once Odoo env is available."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job_model = cls.env["hr.job"].with_context(tracking_disable=True)
        cls.share_log_model = cls.env["hr.job.share.log"].with_context(tracking_disable=True)
        cls.company = cls.env.company

    def test_slug_uniqueness_scope_placeholder(self):
        """Ensure slug uniqueness per company/website scope (placeholder)."""
        # Arrange: create two jobs with similar names to exercise collision handling.
        job_a = self.job_model.create({"name": "Site Engineer", "company_id": self.company.id, "website_published": True})
        job_b = self.job_model.create({"name": "Site Engineer", "company_id": self.company.id, "website_published": True})

        # Act: trigger slug generation for each job.
        job_a.ensure_share_slug()
        job_b.ensure_share_slug()

        # Assert: slugs should differ, representing scoped uniqueness.
        assert job_a.share_slug != job_b.share_slug

    def test_redirect_and_logging_placeholder(self):
        """Placeholder to assert redirect/link-building helpers keep short URL and logs aligned."""
        job = self.job_model.create({"name": "QA Lead", "company_id": self.company.id, "website_published": True})
        job.ensure_share_slug()

        short_url = job.short_url
        linkedin_url = job.share_url_linkedin
        whatsapp_url = job.share_url_whatsapp
        email_url = job.share_url_email

        assert job.share_slug
        assert short_url and job.share_slug in short_url
        assert linkedin_url and short_url in linkedin_url
        assert whatsapp_url and short_url in whatsapp_url
        assert email_url and short_url in email_url

        # Simulate a backend share log creation.
        log = self.share_log_model.sudo().with_company(job.company_id).create(
            {
                "job_id": job.id,
                "channel": "linkedin",
                "origin": "backend",
                "url_used": short_url,
            }
        )
        assert log.channel == "linkedin"
        assert log.job_id == job
        assert log.company_id == job.company_id

# -*- coding: utf-8 -*-
import logging

from werkzeug import exceptions
from werkzeug.utils import redirect

from odoo import http
from odoo.http import request
from odoo.addons.website_hr_recruitment.controllers.main import (
    WebsiteHrRecruitment as WebsiteHrRecruitmentBase,
)

from ..constants import WEBSITE_JOB_ROUTE_FLAG


_logger = logging.getLogger(__name__)


class JobShareController(http.Controller):
    @http.route(
        "/j/<string:share_slug>",
        type="http",
        auth="public",
        website=True,
        csrf=False,
        sitemap=True,
    )
    def job_short_link(self, share_slug, **kwargs):
        if not share_slug:
            raise exceptions.NotFound()
        job = self._find_job_by_slug(share_slug)
        if not job or not job.website_published:
            raise exceptions.NotFound()
        target_url = job.website_url or f"/jobs/detail/{job.id}"
        return redirect(target_url, code=301)

    @http.route(
        "/jobs/share/<string:channel>/<string:share_slug>",
        type="http",
        auth="public",
        website=True,
        csrf=False,
    )
    def share_job(self, channel, share_slug, **kwargs):
        if channel not in {"linkedin", "whatsapp", "email"}:
            raise exceptions.NotFound()
        job = self._find_job_by_slug(share_slug)
        if not job or not job.website_published:
            raise exceptions.NotFound()

        base_url = request.httprequest.host_url.rstrip("/")
        short_url = job._get_short_url(base_url=base_url)
        share_url = job._build_share_url(channel, short_url=short_url)

        try:
            job._log_share_action(
                channel,
                origin="website",
                short_url=short_url,
                user=request.env.user,
            )
        except Exception:  # noqa: BLE001 - logging must not block redirect
            _logger.warning(
                "Failed to log share action for job %s on channel %s", job.id, channel,
                exc_info=True,
            )
        return redirect(share_url)

    def _find_job_by_slug(self, share_slug):
        Job = request.env["hr.job"]
        domain = [("share_slug", "=", share_slug)]
        if Job._fields.get("company_id"):
            domain.append(("company_id", "in", request.env.companies.ids))
        website_field = Job._fields.get("website_id")
        if website_field and request.website:
            domain.append(("website_id", "in", [request.website.id, False]))
        env = Job.sudo().with_context(active_test=False)
        if request.website and request.website.company_id:
            env = env.with_company(request.website.company_id)
        return env.search(domain, limit=1)


class WebsiteHrRecruitment(WebsiteHrRecruitmentBase):
    """Override job detail/apply routes to bypass multi-company read blocks for website viewers."""

    def _prepare_job_for_website(self, job):
        job_sudo = job.with_company(job.company_id).sudo()
        website = request.website
        if website and job_sudo.website_id and job_sudo.website_id != website:
            raise exceptions.NotFound()
        if not job_sudo.website_published and not request.env.user.has_group(
            "hr_recruitment.group_hr_recruitment_user"
        ):
            raise exceptions.NotFound()
        return job_sudo

    @http.route(
        '''/jobs/<model("hr.job"):job>''',
        type="http",
        auth="public",
        website=True,
        sitemap=True,
        priority=10,
    )
    def job(self, job, **kwargs):
        job_sudo = self._prepare_job_for_website(job)
        return request.render(
            "website_hr_recruitment.detail",
            {"job": job_sudo, "main_object": job_sudo},
        )
    job.__dict__[WEBSITE_JOB_ROUTE_FLAG] = True

    @http.route(
        '''/jobs/apply/<model("hr.job"):job>''',
        type="http",
        auth="public",
        website=True,
        sitemap=True,
        priority=10,
    )
    def jobs_apply(self, job, **kwargs):
        job_sudo = self._prepare_job_for_website(job)
        return super().jobs_apply(job_sudo, **kwargs)
    jobs_apply.__dict__[WEBSITE_JOB_ROUTE_FLAG] = True

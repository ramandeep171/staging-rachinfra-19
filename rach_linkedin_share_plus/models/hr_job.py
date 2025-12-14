# -*- coding: utf-8 -*-
from urllib.parse import quote_plus

from werkzeug import urls

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrJob(models.Model):
    _inherit = "hr.job"

    share_slug = fields.Char(string="Share Slug", copy=False, index=True)
    short_url = fields.Char(string="Short URL", compute="_compute_short_url", readonly=True)
    share_url_linkedin = fields.Char(compute="_compute_share_urls", readonly=True)
    share_url_whatsapp = fields.Char(compute="_compute_share_urls", readonly=True)
    share_url_email = fields.Char(compute="_compute_share_urls", readonly=True)
    share_log_count = fields.Integer(string="Share Logs", compute="_compute_share_log_count")
    share_log_ids = fields.One2many("hr.job.share.log", "job_id", string="Share Logs")

    @api.depends("share_slug")
    def _compute_short_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", default="")
        for job in self:
            if job.share_slug:
                if base_url:
                    job.short_url = urls.url_join(base_url, f"/j/{job.share_slug}")
                else:
                    job.short_url = f"/j/{job.share_slug}"
            else:
                job.short_url = False

    @api.depends("short_url", "name")
    def _compute_share_urls(self):
        for job in self:
            short_url = job.short_url or ""
            if not job.share_slug:
                job.share_url_linkedin = False
                job.share_url_whatsapp = False
                job.share_url_email = False
                continue
            job.share_url_linkedin = job._build_share_url("linkedin", short_url=short_url)
            job.share_url_whatsapp = job._build_share_url("whatsapp", short_url=short_url)
            job.share_url_email = job._build_share_url("email", short_url=short_url)

    @api.depends("share_log_ids")
    def _compute_share_log_count(self):
        grouped_data = self.env["hr.job.share.log"].read_group(
            [("job_id", "in", self.ids)], ["job_id"], ["job_id"]
        )
        count_map = {data["job_id"][0]: data["job_id_count"] for data in grouped_data}
        for job in self:
            job.share_log_count = count_map.get(job.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        jobs = super().create(vals_list)
        for job, vals in zip(jobs, vals_list):
            if not vals.get("share_slug"):
                job.ensure_share_slug(force=True)
        return jobs

    def write(self, vals):
        name_changed = "name" in vals
        publish_changed = "website_published" in vals
        result = super().write(vals)
        if name_changed or publish_changed:
            self.ensure_share_slug(force=name_changed or publish_changed)
        elif any(not job.share_slug for job in self):
            self.ensure_share_slug(force=True)
        return result

    def ensure_share_slug(self, force=False):
        for job in self:
            if not job.share_slug or force:
                base_slug = job._generate_slug_base()
                unique_slug = job._find_unique_slug(base_slug)
                job.sudo().write({"share_slug": unique_slug})
        return True

    def _generate_slug_base(self):
        self.ensure_one()
        slugify = self.env["ir.http"]._slugify
        parts = [self.name or "job"]
        if getattr(self, "address_id", False) and self.address_id.city:
            parts.append(self.address_id.city)
        base = "-".join(filter(None, parts))
        cleaned = slugify(base)
        return cleaned or slugify(f"job-{self.id}")

    def _slug_uniqueness_domain(self, slug, include_self=False):
        domain = [("share_slug", "=", slug)]
        if not include_self:
            domain.append(("id", "!=", self.id))
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        website_field = self._fields.get("website_id")
        if website_field:
            website_id = self.website_id.id if self.website_id else False
            domain.append(("website_id", "=", website_id))
        return domain

    def _find_unique_slug(self, base_slug):
        self.ensure_one()
        slug = base_slug
        suffix = 1
        domain = self._slug_uniqueness_domain(slug)
        while self.sudo().with_context(active_test=False).search_count(domain):
            suffix += 1
            slug = f"{base_slug}-{suffix}"
            domain[0] = ("share_slug", "=", slug)
        return slug

    @api.constrains("share_slug")
    def _check_share_slug_unique(self):
        for job in self.filtered("share_slug"):
            domain = job._slug_uniqueness_domain(job.share_slug)
            if job.sudo().with_context(active_test=False).search_count(domain):
                raise ValidationError(
                    _("Share slug must be unique within the website/company scope.")
                )

    def _get_short_url(self, base_url=None):
        self.ensure_one()
        if not self.share_slug:
            self.ensure_share_slug(force=True)
        if not base_url:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", default="")
        if base_url:
            return urls.url_join(base_url, f"/j/{self.share_slug}")
        return f"/j/{self.share_slug}"

    def _build_share_url(self, channel, short_url=None):
        self.ensure_one()
        short = short_url or self._get_short_url()
        if channel == "linkedin":
            return f"https://www.linkedin.com/sharing/share-offsite/?url={quote_plus(short)}"
        if channel == "whatsapp":
            text = f"{self.name} - {short}" if self.name else short
            return f"https://api.whatsapp.com/send?text={quote_plus(text)}"
        if channel == "email":
            subject = quote_plus(self.name or _("Job Opportunity"))
            return f"mailto:?subject={subject}&body={quote_plus(short)}"
        return short

    def _log_share_action(self, channel, origin="backend", short_url=None, user=None):
        self.ensure_one()
        if channel not in {"linkedin", "whatsapp", "email"}:
            return False
        values = {
            "job_id": self.id,
            "channel": channel,
            "origin": origin,
            "url_used": short_url or self.short_url or self._get_short_url(),
        }
        if user and not user._is_public():
            values["user_id"] = user.id
        return (
            self.env["hr.job.share.log"]
            .sudo()
            .with_company(self.company_id)
            .create(values)
        )

    def action_open_share_logs(self):
        self.ensure_one()
        action = self.env.ref("rach_linkedin_share_plus.hr_job_share_log_action").read()[0]
        action["domain"] = [("job_id", "=", self.id)]
        action.setdefault("context", {})
        action["context"].update({"default_job_id": self.id})
        return action

    def _action_share_channel(self, channel):
        self.ensure_one()
        self._check_can_share()
        short_url = self._get_short_url()
        share_url = self._build_share_url(channel, short_url=short_url)
        self._log_share_action(
            channel,
            origin="backend",
            short_url=short_url,
            user=self.env.user,
        )
        return {"type": "ir.actions.act_url", "url": share_url, "target": "new"}

    def action_share_linkedin(self):
        return self._action_share_channel("linkedin")

    def action_share_whatsapp(self):
        return self._action_share_channel("whatsapp")

    def action_share_email(self):
        return self._action_share_channel("email")

    def _check_can_share(self):
        self.ensure_one()
        if not self.website_published:
            raise UserError(_("Publish the job before sharing."))
        if not self.share_slug:
            self.ensure_share_slug(force=True)
        return True

# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request

from ..constants import WEBSITE_JOB_ROUTE_FLAG


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _pre_dispatch(cls, rule, args):
        """Extend to loosen hr.job access for flagged website routes."""
        if cls._is_share_route(rule):
            cls._ensure_job_company_allowed(args)
        return super()._pre_dispatch(rule, args)

    @staticmethod
    def _is_share_route(rule):
        endpoint = rule.endpoint
        if getattr(endpoint, WEBSITE_JOB_ROUTE_FLAG, False):
            return True
        endpoint_func = getattr(endpoint, "func", None)
        return bool(endpoint_func and getattr(endpoint_func, WEBSITE_JOB_ROUTE_FLAG, False))

    @staticmethod
    def _ensure_job_company_allowed(args):
        job = args.get("job")
        if not job:
            return
        job = job.sudo()
        website = getattr(request, "website", None)
        company = job.company_id or (website and website.company_id)
        if not company:
            return
        allowed_ids = request.env.context.get("allowed_company_ids") or []
        if isinstance(allowed_ids, int):
            allowed_ids = [allowed_ids]
        else:
            allowed_ids = list(allowed_ids)
        context_updates = {}
        if company.id not in allowed_ids:
            allowed_ids.append(company.id)
            context_updates["allowed_company_ids"] = allowed_ids
        context_company_id = request.env.context.get("company_id")
        if context_company_id != company.id:
            context_updates["company_id"] = company.id
        if context_updates:
            request.update_context(**context_updates)

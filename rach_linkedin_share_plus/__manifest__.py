# -*- coding: utf-8 -*-
{
    "name": "LinkedIn Share Plus",
    "summary": "Share job openings on LinkedIn, WhatsApp, or Email with short URLs and activity logs.",
    "description": """Publish jobs with auto-generated short links and per-channel share logging. Backend and website
    share buttons route through logging endpoints, record channel, origin, and user/visitor, and then
    redirect to LinkedIn, WhatsApp, or Email share dialogs. Slugs are unique per company/website scope
    and resolve via /j/<slug> to the canonical job page, respecting publish visibility rules.""",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["hr", "hr_recruitment", "website_hr_recruitment"],
    "data": [
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "views/hr_job_share_log_views.xml",
        "views/hr_job_views.xml",
        "views/website_templates.xml",
    ],
    "assets": {},
    "installable": True,
    "application": False,
}

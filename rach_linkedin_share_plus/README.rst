LinkedIn Share Plus
===================

Purpose
-------
A lightweight add-on for Odoo 19E that lets recruiters share published jobs to LinkedIn, WhatsApp, and Email with short, clean URLs and per-channel activity logs. The module stays fully native to Odoo HR Recruitment + Website HR—no external APIs or dependencies.

Module flow at a glance
-----------------------
1. **Create & publish job** – recruiter adds a vacancy, publishes it on the website, and the module auto-generates a unique slug plus ``/j/<slug>`` short link scoped to company/website.
2. **Trigger share** – from the backend form buttons or from the website share buttons, the recruiter/visitor chooses LinkedIn, WhatsApp, or Email.
3. **Short URL redirect** – the module routes via ``/jobs/share/<channel>/<slug>`` so tracking happens before redirecting to each channel’s share dialog.
4. **Log share action** – ``hr.job.share.log`` captures job, channel, origin (backend vs website), user (if not public), timestamp, and short URL used.
5. **Review analytics** – recruiters use the “Share Logs” smart button or dedicated menu to review grouped stats per channel/origin/company.

Detailed usage flow
-------------------

Install & prerequisites
~~~~~~~~~~~~~~~~~~~~~~~
- Ensure ``hr``, ``hr_recruitment``, and ``website_hr_recruitment`` are installed before adding this module.
- Install **LinkedIn Share Plus** from Apps; no external keys or configuration are required.
- Multi-company/website deployments automatically scope slugs and logs to the active company/website.

Share from the backend (recruiter desk)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Open *Recruitment ▸ Jobs* and create or edit a job.
2. Publish the job on the website (sharing buttons stay hidden until ``website_published`` is true).
3. Go to the **Sharing** tab to see the generated slug plus short URL.
4. Use the header buttons: **Share LinkedIn**, **Share WhatsApp**, or **Share Email**.
5. Odoo opens the relevant channel in a new tab, pre-filled with the short link, and silently writes a backend-origin log entry.

Share from the website (public job page)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Browse to the website job detail page (``/jobs/detail/<id>``).
2. Use the rendered LinkedIn/WhatsApp/Email buttons (template override in ``views/website_templates.xml``).
3. The request hits ``/jobs/share/<channel>/<slug>``, registers a website-origin log, and redirects to the external share dialog.
4. Public visitors are logged without a user reference; signed-in portal users are linked to their ``res.users`` record automatically.

Track share logs & insights
~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Click the **Share Logs** stat button on the job form, or open the *Share Logs* smart action to filter by channel/origin/user.
- List/form views show ``shared_at``, ``channel``, ``origin`` (backend/website), ``user_id``, and short URL used.
- Use the search view filters to group by channel, origin, or user. Context defaults to the active company for clean multi-company reporting.
- Logs inherit the job’s company, so recruiters only see data allowed by standard record rules.

Slug lifecycle & redirects
~~~~~~~~~~~~~~~~~~~~~~~~~~
- Every published job gets a slug based on the job title (plus city if available). Slug uniqueness is enforced per company and website.
- Slug changes happen automatically when the job name or publish status changes.
- The ``/j/<slug>`` route resolves to the canonical job URL and returns a 404 if the job is unpublished or missing, ensuring marketing links never leak drafts.

Key capabilities
----------------
- Auto-generate shareable slugs per company/website scope and derive short redirect URLs like ``/j/<slug>``.
- Backend and website share buttons for LinkedIn, WhatsApp, and Email that log channel, origin, and user/visitor.
- Redirect controller that resolves short links to the canonical job page while respecting publish and visibility rules.
- Company-aware logging model with smart buttons and views to review share activity.

Quality hooks & coverage focus
------------------------------
- Slug uniqueness and collision handling inside the company/website scope.
- Redirect resolution for published jobs and graceful 404 for missing or unpublished entries.
- Logging integrity for backend and website origins, ensuring company isolation on sudoed writes.

How to test (targeted scenarios)
--------------------------------
- Install the module with HR Recruitment + Website HR enabled.
- Publish a job and confirm a slug is generated; verify ``/j/<slug>`` redirects to the job detail page.
- Use share buttons (backend + website) for each channel and confirm ``hr.job.share.log`` entries capture channel, origin, and user/visitor context.
- Toggle multi-company or multi-website and ensure slugs remain unique per scope and logs stay isolated.

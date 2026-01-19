from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class JrPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'jr_count' in counters:
            values['jr_count'] = request.env['jr.employee.jr']._portal_count()
        return values

    @http.route(['/my/job-responsibilities', '/my/job-responsibilities/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_job_responsibilities(self, page=1, sortby=None, **kw):
        Jr = request.env['jr.employee.jr']
        domain = Jr._portal_domain()

        sort_options = {
            'issue_date': {'label': 'Issue date', 'order': 'issue_date desc, id desc'},
            'name': {'label': 'Name', 'order': 'name desc'},
        }
        if sortby not in sort_options:
            sortby = 'issue_date'
        order = sort_options[sortby]['order']

        total = Jr.search_count(domain)
        pager = portal_pager(
            url="/my/job-responsibilities",
            total=total,
            page=page,
            step=20,
            url_args={'sortby': sortby},
        )
        jrs = Jr.search(domain, order=order, limit=20, offset=pager['offset'])

        values = self._prepare_portal_layout_values()
        values.update({
            'jrs': jrs,
            'page_name': 'job_responsibilities',
            'default_url': '/my/job-responsibilities',
            'pager': pager,
            'sortby': sortby,
            'sort_options': sort_options,
        })
        return request.render("hr_job_responsibility.portal_my_job_responsibilities", values)

    @http.route('/my/job-responsibilities/<int:jr_id>', type='http', auth='user', website=True)
    def portal_jr_detail(self, jr_id, **kw):
        Jr = request.env['jr.employee.jr'].sudo()
        jr = Jr.search([('id', '=', jr_id)] + Jr._portal_domain(), limit=1)
        if not jr:
            return request.not_found()
        values = self._prepare_portal_layout_values()
        values.update({
            'jr': jr,
            'page_name': 'job_responsibilities',
            'default_url': '/my/job-responsibilities',
        })
        return request.render("hr_job_responsibility.portal_jr_detail", values)

    @http.route('/my/job-responsibilities/<int:jr_id>/print', type='http', auth='user', website=True)
    def portal_jr_print(self, jr_id, **kw):
        Jr = request.env['jr.employee.jr'].sudo()
        jr = Jr.search([('id', '=', jr_id)] + Jr._portal_domain(), limit=1)
        if not jr:
            return request.not_found()
        report = (
            request.env['ir.actions.report']
            .sudo()
            ._get_report_from_name('hr_job_responsibility.report_employee_jr_document')
        )
        if not report:
            return request.not_found()
        pdf_content, _ = report._render_qweb_pdf(jr.id)
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', f'attachment; filename=\"{jr.name}.pdf\"'),
        ]
        return request.make_response(pdf_content, headers=pdfhttpheaders)

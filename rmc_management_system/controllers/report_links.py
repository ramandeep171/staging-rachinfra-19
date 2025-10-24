from odoo import http
from odoo.http import request
import json
import urllib.parse


class RmcReportLinks(http.Controller):
    def _redirect_to_report(self, kind, report_name, docid, **kw):
        ctx = dict(request.env.context or {})
        # Accept simple query params (e.g., ?window_days=7)
        if 'window_days' in kw:
            try:
                ctx['window_days'] = int(kw.get('window_days'))
            except Exception:
                pass
        if 'date_from' in kw and kw.get('date_from'):
            ctx['date_from'] = kw.get('date_from')
        query = 'context=' + urllib.parse.quote(json.dumps(ctx)) if ctx else ''
        url = '/report/{}/{}/{}{}'.format(
            kind,
            report_name,
            docid,
            ('?' + query) if query else ''
        )
        return request.redirect(url)

    @http.route(['/rmc/report/pdf/<string:report_name>/<int:docid>'], type='http', auth='public', website=True)
    def rmc_report_pdf(self, report_name, docid, **kw):
        return self._redirect_to_report('pdf', report_name, docid, **kw)

    @http.route(['/rmc/report/html/<string:report_name>/<int:docid>'], type='http', auth='public', website=True)
    def rmc_report_html(self, report_name, docid, **kw):
        return self._redirect_to_report('html', report_name, docid, **kw)

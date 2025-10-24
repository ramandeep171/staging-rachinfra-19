from odoo.addons.account.controllers.portal import PortalAccount as AccountPortal
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


class PortalAccountRMC(AccountPortal):
    """Extend customer invoice portal so RMC invoices render the custom template."""

    @http.route(['/my/invoices/<int:invoice_id>'], type='http', auth="public", website=True)
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        """Use the dedicated RMC invoice report for RMC products, keep default otherwise."""
        if report_type in ('html', 'pdf', 'text'):
            try:
                invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
            except (AccessError, MissingError):
                return request.redirect('/my')

            if report_type == 'pdf' and download and invoice_sudo.state == 'posted':
                docs_data = invoice_sudo._get_invoice_legal_documents_all(allow_fallback=True)
                if len(docs_data) != 1:
                    return super().portal_my_invoice_detail(
                        invoice_id,
                        access_token=access_token,
                        report_type=report_type,
                        download=download,
                        **kw,
                    )

            if getattr(invoice_sudo, 'is_rmc_product', False):
                has_generated_invoice = bool(invoice_sudo.invoice_pdf_report_id)
                request.update_context(proforma_invoice=not has_generated_invoice)
                return self._show_report(
                    model=invoice_sudo,
                    report_type=report_type,
                    report_ref='rmc_management_system.rmc_invoice_report',
                    download=download,
                )

        return super().portal_my_invoice_detail(
            invoice_id,
            access_token=access_token,
            report_type=report_type,
            download=download,
            **kw,
        )

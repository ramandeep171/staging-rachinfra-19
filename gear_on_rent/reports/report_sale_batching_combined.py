import logging

from odoo import models
from odoo.tools.pdf import merge_pdf
from odoo.tools.pdf import PdfFileReader, PdfFileWriter
import base64
import io

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """Append Batching Plant quotation after the standard sale order PDF.

        Runs when the default Quotation/Order report is rendered. Falls back
        silently if the batching report is missing or merging fails. Set
        context key `skip_batching_append=True` to bypass.
        """
        pdf_content, report_type = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if report_type != "pdf":
            return pdf_content, report_type

        try:
            report_sudo = self._get_report(report_ref)
        except Exception:
            return pdf_content, report_type

        # Only hook the standard quotation report.
        if report_sudo.report_name != "sale.report_saleorder":
            return pdf_content, report_type

        # Skip when explicitly asked or when nothing to render.
        if self.env.context.get("skip_batching_append") or not res_ids:
            return pdf_content, report_type

        orders = self.env["sale.order"].browse(res_ids).exists()
        if not orders:
            return pdf_content, report_type

        try:
            batching_action = self.env.ref("gear_on_rent.action_report_batching_plant_quote")
        except Exception:
            _logger.warning("Batching Plant report action not found; skipping merge.")
            return pdf_content, report_type

        try:
            batching_pdf, batching_type = super(IrActionsReport, self)._render_qweb_pdf(
                batching_action.id, res_ids=orders.ids, data=data
            )
        except Exception:
            _logger.exception("Failed to render Batching Plant quotation; skipping merge.")
            return pdf_content, report_type

        if batching_type != "pdf" or not batching_pdf:
            return pdf_content, report_type

        # Reorder so batching pages come before the default footer pages (quote builder terms).
        try:
            if len(orders) == 1:
                order = orders[0]
                footers = order.quotation_document_ids.filtered(lambda d: d.document_type != "header")
                footer_pages = 0
                for doc in footers:
                    try:
                        reader = PdfFileReader(io.BytesIO(base64.b64decode(doc.datas)), strict=False)
                        footer_pages += reader.getNumPages()
                    except Exception:
                        continue

                base_reader = PdfFileReader(io.BytesIO(pdf_content), strict=False)
                total_pages = base_reader.getNumPages()
                main_pages = max(0, total_pages - footer_pages)

                writer = PdfFileWriter()
                # Main quote (with headers/product docs), without footer pages.
                for i in range(main_pages):
                    writer.addPage(base_reader.getPage(i))
                # Batching plant pages.
                batching_reader = PdfFileReader(io.BytesIO(batching_pdf), strict=False)
                for i in range(batching_reader.getNumPages()):
                    writer.addPage(batching_reader.getPage(i))
                # Footer pages from original PDF, to keep filled fields.
                for i in range(main_pages, total_pages):
                    writer.addPage(base_reader.getPage(i))

                with io.BytesIO() as buf:
                    writer.write(buf)
                    return buf.getvalue(), "pdf"

            # Fallback: simple append for multi-order prints.
            merged = merge_pdf([pdf_content, batching_pdf])
            return merged, "pdf"
        except Exception:
            _logger.exception("Failed to merge sale + batching PDFs; returning base PDF.")
            return pdf_content, report_type

# Copyright (C) 2025 Tech Paras / Gear on Rent
# Apply Quote Builder header/footer PDFs to the custom batching plant quotation.

import io

from odoo import models
from odoo.tools import pdf


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        # Let existing overrides (including sale_pdf_quote_builder) run first.
        result = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)

        # Only adjust our batching plant report.
        report = self._get_report(report_ref)
        if report.report_name != "gear_on_rent.report_batching_plant_quote":
            return result

        orders = self.env["sale.order"].browse(res_ids)
        for order in orders:
            # Skip if no stream to augment.
            if order.id not in result or "stream" not in result[order.id]:
                continue

            initial_stream = result[order.id]["stream"]
            if not initial_stream:
                continue

            # Quote Builder selections
            if not hasattr(order, "quotation_document_ids"):
                continue
            quotation_documents = order.quotation_document_ids
            headers = quotation_documents.filtered(lambda doc: doc.document_type == "header")
            footers = quotation_documents - headers
            has_product_document = any(
                line.product_document_ids for line in getattr(order, "order_line", [])
            )

            if not headers and not has_product_document and not footers:
                continue

            form_fields_values_mapping = {}
            writer = pdf.PdfFileWriter()

            self_with_order_context = self.with_context(
                use_babel=True, lang=order._get_lang() or self.env.user.lang
            )

            if headers:
                for header in headers:
                    prefix = f"quotation_document_id_{header.id}__"
                    self_with_order_context._update_mapping_and_add_pages_to_writer(
                        writer, header, form_fields_values_mapping, prefix, order
                    )
            if has_product_document:
                for line in order.order_line:
                    for doc in line.product_document_ids:
                        prefix = f"sol_id_{line.id}_product_document_id_{doc.id}__"
                        self_with_order_context._update_mapping_and_add_pages_to_writer(
                            writer, doc, form_fields_values_mapping, prefix, order, line
                        )

            self._add_pages_to_writer(writer, initial_stream.getvalue())

            if footers:
                for footer in footers:
                    prefix = f"quotation_document_id_{footer.id}__"
                    self_with_order_context._update_mapping_and_add_pages_to_writer(
                        writer, footer, form_fields_values_mapping, prefix, order
                    )

            pdf.fill_form_fields_pdf(writer, form_fields=form_fields_values_mapping)
            with io.BytesIO() as _buffer:
                writer.write(_buffer)
                stream = io.BytesIO(_buffer.getvalue())

            result[order.id].update({"stream": stream})

        return result

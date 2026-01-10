from odoo import models, api
from odoo.tools.misc import formatLang as _format_lang
import base64

class ReportBatchingPlantQuote(models.AbstractModel):
    _name = 'report.gear_on_rent.report_batching_plant_quote'
    _description = 'Batching Plant Quotation Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['sale.order'].browse(docids)
        
        # Use the first document to generate data, as the template structure 
        # currently implies a single context for pdf_data.
        doc = docs[0] if docs else None
        
        pdf_data = {}
        chart_urls = {}
        dead_cost_context = {}
        
        if doc:
            pdf_helper = self.env["gear.batching.quotation.pdf"]
            pdf_data = pdf_helper.prepare_pdf_assets(doc)
            
            def _encode_chart(path):
                if not path:
                    return None
                if isinstance(path, str) and path.startswith("data:image"):
                    return path
                try:
                    with open(path, "rb") as handle:
                        encoded = base64.b64encode(handle.read()).decode("ascii")
                        return f"data:image/png;base64,{encoded}"
                except FileNotFoundError:
                    return None

            chart_urls = {
                key: _encode_chart(path) for key, path in pdf_data.get("charts", {}).items()
            }

            capex_breakdown = pdf_data.get("capex_breakdown") or {}
            final_rates = pdf_data.get("final_rates") or {}
            dead_cost_context = (
                pdf_data.get("dead_cost_context")
                or (data or {}).get("dead_cost")
                or {
                    "per_cum": pdf_data.get("dead_cost")
                    or final_rates.get("dead_cost")
                    or doc.gear_dead_cost_per_cum
                    or 0.0,
                    "total": capex_breakdown.get("total_amount")
                    or doc.gear_dead_cost_amount
                    or 0.0,
                }
            )
        else:
            dead_cost_context = (data or {}).get("dead_cost") or {}

        def formatLang(value, digits=None, currency_obj=None):
            """Expose Odoo number formatter to QWeb to avoid KeyError when missing in context."""
            return _format_lang(self.env, value, digits=digits, currency_obj=currency_obj)

        return {
            'doc_ids': docids,
            'doc_model': 'sale.order',
            'docs': docs,
            'pdf_data': pdf_data,
            'chart_urls': chart_urls,
            'dead_cost': dead_cost_context,
            'dead_cost_context': dead_cost_context,
            'formatLang': formatLang,
        }

from odoo import models, api
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
        
        if doc:
            pdf_helper = self.env["gear.batching.quotation.pdf"]
            pdf_data = pdf_helper.prepare_pdf_assets(doc)
            
            def _encode_chart(path):
                if not path: return None
                try:
                    with open(path, "rb") as handle:
                        encoded = base64.b64encode(handle.read()).decode("ascii")
                        return f"data:image/png;base64,{encoded}"
                except FileNotFoundError:
                    return None

            chart_urls = {
                key: _encode_chart(path) for key, path in pdf_data.get("charts", {}).items()
            }

        return {
            'doc_ids': docids,
            'doc_model': 'sale.order',
            'docs': docs,
            'pdf_data': pdf_data,
            'chart_urls': chart_urls,
        }

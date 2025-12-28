from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, endpoint):
        try:
            if request.httprequest.path.startswith("/odoo/mcp/"):
                db = request.httprequest.args.get("db") or request.httprequest.headers.get(
                    "X-Odoo-Database"
                )
                if db:
                    request.session.db = db
        except Exception:
            # never break core dispatch because of our helper
            pass

        return super()._dispatch(endpoint)

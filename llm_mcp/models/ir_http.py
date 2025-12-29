from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, endpoint):
        path = request.httprequest.path

        # 🔴 HARD BYPASS for MCP
        if path.startswith("/odoo/mcp/"):
            db = (
                request.httprequest.args.get("db")
                or request.httprequest.headers.get("X-Odoo-Database")
            )
            if db:
                request.session.db = db

            # ⛔ STOP login redirect completely
            request.session.uid = 1  # or MCP service user id
            request.uid = 1
            request.env = request.env(user=1)

        return super()._dispatch(endpoint)

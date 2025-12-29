from odoo import http
from odoo.http import Request


_ORIGINAL_GET_DB = Request._get_session_and_dbname


def _llm_mcp_get_session_and_dbname(self):
    """Allow MCP HTTP calls to pick a database via ?db=<name> when no session exists."""
    session, dbname = _ORIGINAL_GET_DB(self)
    if dbname:
        return session, dbname

    path = self.httprequest.path or ""
    if "/mcp/" not in path:
        return session, dbname

    db_param = (
        self.httprequest.args.get("db")
        or self.httprequest.headers.get("X-Odoo-Database")
        or ""
    ).strip()
    if not db_param:
        return session, dbname

    allowed = http.db_filter([db_param], host=self.httprequest.environ.get("HTTP_HOST"))
    if not allowed:
        return session, dbname

    db_name = allowed[0]
    session.db = db_name
    session.is_dirty = False
    return session, db_name


if not getattr(Request, "_llm_mcp_db_patch", False):
    Request._llm_mcp_db_patch = True
    Request._llm_mcp_original_get_session_and_dbname = _ORIGINAL_GET_DB
    Request._get_session_and_dbname = _llm_mcp_get_session_and_dbname

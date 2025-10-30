from collections import Counter
from datetime import timedelta

from werkzeug import urls

from odoo import fields, http
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request


class PortalCommissionAgent(CustomerPortal):
    def _commission_portal_redirect(self):
        """Return an http response if the current user cannot access the commission portal."""
        user = request.env.user
        if user._is_public():
            redirect_url = "/web/login?redirect=%s" % urls.url_quote(request.httprequest.full_path)
            return request.redirect(redirect_url)
        if not user.has_group("rmc_commission_agent.group_portal_commission_agent"):
            return request.redirect("/my")
        return None

    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        agent = self._get_portal_agent()
        values["commission_agent"] = agent
        values["commission_orders_count"] = len(agent.commission_sale_order_ids) if agent else 0
        if agent:
            values["commission_agent_channel_label"] = dict(agent._fields["agent_type"].selection).get(
                agent.agent_type, agent.agent_type
            )
            values["commission_agent_country_label"] = dict(agent._fields["country_tag"].selection).get(
                agent.country_tag, agent.country_tag
            )
            metrics = self._compute_dashboard_metrics(agent)
            currency = agent.partner_id.company_id.currency_id or request.env.company.currency_id
            values["commission_dashboard_metrics"] = metrics
            values["commission_agent_channel_options"] = agent._fields["agent_type"].selection
            values["commission_currency"] = currency
            values["commission_dashboard_metrics_display"] = self._prepare_metrics_display(metrics, currency)
            values["commission_vouchers"] = self._prepare_portal_vouchers(agent, currency)
            values["commission_leaderboard"] = self._prepare_leaderboard_entries(agent, currency)
            values["commission_agent_weights"] = agent.get_portal_performance_weights()
        else:
            values["commission_dashboard_metrics"] = self._empty_dashboard_metrics()
            values["commission_agent_channel_options"] = []
            values["commission_currency"] = request.env.company.currency_id
            values["commission_dashboard_metrics_display"] = self._prepare_metrics_display(
                values["commission_dashboard_metrics"], values["commission_currency"]
            )
            values["commission_vouchers"] = []
            values["commission_leaderboard"] = []
            values["commission_agent_weights"] = []
        return values

    def _get_portal_agent(self):
        partner = request.env.user.partner_id
        if not partner:
            return request.env["rmc.commission.agent"]
        commercial_partner = partner.commercial_partner_id or partner
        domain = [
            "|",
            ("partner_id", "child_of", commercial_partner.id),
            ("partner_id", "=", partner.id),
        ]
        return request.env["rmc.commission.agent"].sudo().search(domain, limit=1)

    def _empty_dashboard_metrics(self):
        return {
            "orders_count": 0,
            "commission_total": 0.0,
            "commission_paid_total": 0.0,
            "commission_pending_total": 0.0,
            "delivered_volume_total": 0.0,
            "delivered_volume_recent": 0.0,
            "recovery_rate_avg": 0.0,
            "stage_breakdown": [],
        }

    def _compute_dashboard_metrics(self, agent):
        metrics = self._empty_dashboard_metrics()
        orders = agent.commission_sale_order_ids.sudo()
        if not orders:
            return metrics

        commission_total = sum(orders.mapped("commission_amount"))
        commission_paid = sum(orders.filtered(lambda o: o.commission_stage == "paid").mapped("commission_amount"))
        delivered_volume_total = sum(orders.mapped("commission_delivered_volume"))

        today = fields.Date.context_today(agent)
        if isinstance(today, str):
            today = fields.Date.from_string(today)
        cutoff = today - timedelta(days=30)
        delivered_volume_recent = sum(
            order.commission_delivered_volume
            for order in orders
            if order.date_order and order.date_order.date() >= cutoff
        )

        recovery_rates = [rate for rate in orders.mapped("commission_recovery_rate") if rate]
        recovery_avg = sum(recovery_rates) / len(recovery_rates) if recovery_rates else 0.0

        stage_selection = dict(orders._fields["commission_stage"].selection)
        stage_counts = Counter(orders.mapped("commission_stage"))
        stage_breakdown = [
            {
                "code": code,
                "label": stage_selection.get(code, code),
                "count": count,
            }
            for code, count in stage_counts.items()
        ]
        stage_breakdown.sort(key=lambda item: item["label"])

        metrics.update(
            {
                "orders_count": len(orders),
                "commission_total": commission_total,
                "commission_paid_total": commission_paid,
                "commission_pending_total": max(commission_total - commission_paid, 0.0),
                "delivered_volume_total": delivered_volume_total,
                "delivered_volume_recent": delivered_volume_recent,
                "recovery_rate_avg": recovery_avg,
                "stage_breakdown": stage_breakdown,
            }
        )
        return metrics

    def _format_currency(self, amount, currency):
        if not currency:
            currency = request.env.company.currency_id
        elif isinstance(currency, int):
            currency = request.env["res.currency"].browse(currency)
        lang = request.env.lang or request.env.user.lang or "en_US"
        monetary = request.env["ir.qweb.field.monetary"].with_context(lang=lang)
        return monetary.value_to_html(
            amount or 0.0,
            {
                "currency": currency,
                "display_currency": currency,
            },
        )

    def _format_float(self, value, digits=2):
        lang = request.env.lang or request.env.user.lang or "en_US"
        float_formatter = request.env["ir.qweb.field.float"].with_context(lang=lang)
        options = {
            "digits": (16, digits),
            "precision": digits,
        }
        return float_formatter.value_to_html(value or 0.0, options)

    def _format_datetime(self, dt):
        if not dt:
            return ""
        user = request.env.user
        tz = user.tz or "UTC"
        lang = user.lang or request.env.lang or "en_US"
        formatter = request.env["ir.qweb.field.datetime"].with_context(lang=lang, tz=tz)
        return formatter.value_to_html(
            dt,
            {
                "timezone": tz,
                "tz": tz,
                "format": "medium",
            },
        )

    def _format_date(self, date_value):
        if not date_value:
            return ""
        lang = request.env.lang or request.env.user.lang or "en_US"
        formatter = request.env["ir.qweb.field.date"].with_context(lang=lang)
        return formatter.value_to_html(
            date_value,
            {},
        )

    def _prepare_metrics_display(self, metrics, currency):
        return {
            "commission_total": self._format_currency(metrics.get("commission_total", 0.0), currency),
            "commission_paid_total": self._format_currency(metrics.get("commission_paid_total", 0.0), currency),
            "commission_pending_total": self._format_currency(metrics.get("commission_pending_total", 0.0), currency),
            "delivered_volume_total": self._format_float(metrics.get("delivered_volume_total", 0.0), digits=1),
            "delivered_volume_recent": self._format_float(metrics.get("delivered_volume_recent", 0.0), digits=1),
            "recovery_rate_avg": self._format_float(metrics.get("recovery_rate_avg", 0.0), digits=1),
        }

    def _prepare_portal_vouchers(self, agent, currency, limit=5):
        Voucher = request.env["rmc.commission.voucher"].sudo()
        voucher_records = Voucher.search(
            [("commission_agent_id", "=", agent.id)],
            order="create_date desc",
            limit=limit,
        )
        state_selection = dict(Voucher._fields["state"].selection)
        stage_selection = dict(Voucher._fields["release_stage"].selection)
        entries = []
        for voucher in voucher_records:
            amount_currency = voucher.currency_id or currency
            entries.append(
                {
                    "name": voucher.name,
                    "order_name": voucher.sale_order_id.name or "",
                    "stage_label": stage_selection.get(voucher.release_stage, voucher.release_stage or ""),
                    "amount_display": self._format_currency(voucher.amount or 0.0, amount_currency),
                    "date_display": self._format_date(voucher.release_date) or "-",
                    "status_label": state_selection.get(voucher.state, voucher.state),
                    "status_code": voucher.state,
                    "download_url": "#",
                }
            )
        return entries

    def _prepare_leaderboard_entries(self, agent, currency, limit=5):
        Agent = request.env["rmc.commission.agent"].sudo()
        domain = []
        if agent:
            domain.append(("agent_type", "=", agent.agent_type))
        peers = Agent.search(domain) if domain else Agent.search([])
        leaderboard = []
        for candidate in peers:
            metrics = self._compute_dashboard_metrics(candidate)
            leaderboard.append(
                {
                    "agent_id": candidate.id,
                    "name": candidate.name,
                    "metrics": metrics,
                    "volume_display": self._format_float(metrics.get("delivered_volume_total", 0.0), digits=1),
                    "recovery_display": self._format_float(metrics.get("recovery_rate_avg", 0.0), digits=1),
                    "commission_display": self._format_currency(metrics.get("commission_total", 0.0), currency),
                    "stars_text": self._compute_star_rating(metrics),
                }
            )
        leaderboard.sort(key=lambda item: item["metrics"].get("commission_total", 0.0), reverse=True)
        for idx, entry in enumerate(leaderboard, start=1):
            entry["rank"] = idx
        return leaderboard[:limit]

    def _compute_star_rating(self, metrics):
        score = 3.0
        recovery = metrics.get("recovery_rate_avg", 0.0)
        if recovery >= 95:
            score += 1
        elif recovery <= 70:
            score -= 1
        pending = metrics.get("commission_pending_total", 0.0)
        total = metrics.get("commission_total", 0.0) or 1.0
        if pending < total * 0.25:
            score += 0.5
        score = max(1.0, min(5.0, score))
        filled = int(round(score))
        return "★" * filled + "☆" * (5 - filled)

    @http.route("/my/commission", type="http", auth="public", website=True)
    def portal_my_commission(self, **kwargs):
        redirect = self._commission_portal_redirect()
        if redirect:
            return redirect
        agent = self._get_portal_agent()
        if not agent:
            return request.render(
                "rmc_commission_agent.portal_agent_missing",
                {"page_name": "commission_agent"},
            )
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "agent": agent,
                "page_name": "commission_agent",
                "orders_by_channel": agent.get_portal_sale_orders(),
                "channel": agent.agent_type,
                "channel_label": values.get("commission_agent_channel_label"),
                "country_label": values.get("commission_agent_country_label"),
            }
        )
        return request.render("rmc_commission_agent.portal_agent_dashboard", values)

    @http.route(
        "/my/commission/orders",
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_commission_orders(self, page=1, **kw):
        redirect = self._commission_portal_redirect()
        if redirect:
            return redirect
        agent = self._get_portal_agent()
        if not agent:
            return request.redirect("/my")
        SaleOrder = request.env["sale.order"].sudo()
        domain = [("commission_agent_id", "=", agent.id)]
        order_count = SaleOrder.search_count(domain)
        pager = portal_pager(
            url="/my/commission/orders",
            total=order_count,
            page=page,
            step=20,
        )
        orders = SaleOrder.search(domain, order="date_order desc", limit=20, offset=pager["offset"])
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "agent": agent,
                "page_name": "commission_agent_orders",
                "orders": orders,
                "pager": pager,
            }
        )
        currency = values.get("commission_currency") or request.env.company.currency_id
        values["commission_order_commission_amounts"] = {
            order.id: self._format_currency(order.commission_amount or 0.0, currency) for order in orders
        }
        values["commission_order_total_amounts"] = {
            order.id: self._format_currency(order.amount_total or 0.0, currency) for order in orders
        }
        values["commission_order_dates"] = {
            order.id: self._format_datetime(order.date_order) or "-"
            for order in orders
        }
        return request.render("rmc_commission_agent.portal_agent_orders", values)

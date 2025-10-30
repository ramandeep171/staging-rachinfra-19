import uuid

from odoo import _, api, fields, models, SUPERUSER_ID

from .utils import AGENT_CHANNEL_SELECTION


class RmcCommissionAgent(models.Model):
    _name = "rmc.commission.agent"
    _description = "Commission Agent"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        tracking=True,
        help="Commercial partner linked to this agent. Portal access uses this contact.",
    )
    country_tag = fields.Selection(
        selection=[("ncr", "NCR"), ("haryana", "Haryana")],
        default="ncr",
        tracking=True,
        help="Regional tag for recommendation and reporting filters.",
    )
    agent_type = fields.Selection(
        selection=AGENT_CHANNEL_SELECTION,
        string="Agent Type",
        default="rmc_dropshipping",
        required=True,
        tracking=True,
        help=_("Sales channel for this agent — controls commission rules and portal view."),
    )
    commission_master_id = fields.Many2one(
        "rmc.commission.master",
        tracking=True,
        domain="['&', ('country_tag', '=', country_tag), '|', ('applicable_channel', '=', False), "
        "('applicable_channel', '=', agent_type)]",
    )
    commission_master_suggestion_id = fields.Many2one(
        "rmc.commission.master",
        compute="_compute_commission_master_suggestion_id",
        string="Suggested Commission Master",
        help="Best matching commission master based on country and channel.",
    )
    commission_sale_order_ids = fields.One2many(
        "sale.order", "commission_agent_id", string="Sales Orders"
    )
    portal_user_count = fields.Integer(
        compute="_compute_portal_user_count",
        string="Portal Users",
    )
    performance_volume_weight = fields.Integer(
        string="Order Confirmation Weight (%)",
        default=30,
        help="Commission percentage released once the order is confirmed.",
        tracking=True,
    )
    performance_recovery_weight = fields.Integer(
        string="Delivery Weight (%)",
        default=20,
        help="Commission percentage released when delivery is completed.",
        tracking=True,
    )
    performance_quality_weight = fields.Integer(
        string="Payment Clearance Weight (%)",
        default=40,
        help="Commission percentage tied to customer payment clearance.",
        tracking=True,
    )
    performance_feedback_weight = fields.Integer(
        string="Feedback Weight (%)",
        default=10,
        help="Commission percentage unlocked after customer feedback is received.",
        tracking=True,
    )

    _CONTEXT_SKIP_MASTER_AUTOSET = "rmc_commission_agent_skip_master_autoset"

    @api.model_create_multi
    def create(self, vals_list):
        agents = super().create(vals_list)
        auto_assign_agents = agents.filtered(lambda a: not a.commission_master_id)
        if auto_assign_agents:
            auto_assign_agents._auto_assign_commission_master()
        agents._ensure_portal_user()
        return agents

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in ("partner_id", "active")):
            self._ensure_portal_user()
        if (
            not self.env.context.get(self._CONTEXT_SKIP_MASTER_AUTOSET)
            and any(field in vals for field in ("agent_type", "country_tag", "commission_master_id"))
        ):
            self._auto_assign_commission_master()
        return res

    def _compute_access_url(self):
        super()._compute_access_url()
        for agent in self:
            agent.access_url = f"/my/commission/{agent.id}"

    def _compute_company_name(self):
        # ensure portal.mixin keeps display consistent with linked partner
        super()._compute_company_name()

    def _compute_access_url_name(self):
        super()._compute_access_url_name()

    @api.depends("agent_type", "country_tag")
    def _compute_commission_master_suggestion_id(self):
        for agent in self:
            agent.commission_master_suggestion_id = agent._get_suggested_master()

    def _get_suggested_master(self):
        """Return best matching commission master record."""
        self.ensure_one()
        domain = [
            ("country_tag", "=", self.country_tag),
            "|",
            ("applicable_channel", "=", False),
            ("applicable_channel", "=", self.agent_type),
        ]
        master = (
            self.env["rmc.commission.master"]
            .search(domain, order="applicable_channel desc, id asc", limit=1)
        )
        if not master:
            # fallback ignoring applicable_channel
            master = (
                self.env["rmc.commission.master"]
                .search([("country_tag", "=", self.country_tag)], limit=1)
            )
        return master

    @api.onchange("agent_type", "country_tag")
    def _onchange_channel_adjust_master(self):
        # make domain suggestion and optionally auto-set when no manual choice yet
        suggestion = self._get_suggested_master() if self.agent_type and self.country_tag else False
        if suggestion and (
            not self.commission_master_id
            or self.commission_master_id.country_tag != self.country_tag
            or self.commission_master_id.applicable_channel not in (False, self.agent_type)
        ):
            self.commission_master_id = suggestion

    @api.depends("partner_id")
    def _compute_portal_user_count(self):
        for agent in self:
            partner = agent.partner_id
            agent.portal_user_count = (
                self.env["res.users"]
                .sudo()
                .search_count([("partner_id", "child_of", partner.commercial_partner_id.id or False)])
                if partner
                else 0
            )

    def get_portal_sale_orders(self):
        """Portal helper for retrieving structured sale order data per channel."""
        self.ensure_one()
        orders = self.commission_sale_order_ids.sorted("date_order")
        if self.agent_type == "rmc_dropshipping":
            return [
                {
                    "order": order,
                    "delivered_volume": order.commission_delivered_volume,
                    "stage": order.commission_stage,
                    "amount": order.commission_amount,
                }
                for order in orders
            ]
        if self.agent_type == "rental":
            return [
                {
                    "order": order,
                    "rental_start": order.commission_rental_start,
                    "rental_end": order.commission_rental_end,
                    "equipment_reference": order.commission_equipment_reference,
                    "stage": order.commission_stage,
                }
                for order in orders
            ]
        if self.agent_type == "distribution":
            return [
                {
                    "order": order,
                    "volume": order.commission_delivered_volume,
                    "recovery_rate": order.commission_recovery_rate,
                }
                for order in orders
            ]
        if self.agent_type == "retention":
            return [
                {
                    "order": order,
                    "repeat_count": order.commission_repeat_order_count,
                    "bonus_status": order.commission_retention_bonus_status,
                }
                for order in orders
            ]
        # fallback generic payload
        return [{"order": order} for order in orders]

    def _ensure_portal_user(self):
        """Ensure every active agent has at least one portal user linked to its partner."""
        portal_group = self.env.ref("base.group_portal")
        commission_group = self.env.ref("rmc_commission_agent.group_portal_commission_agent")
        User = self.env["res.users"].with_user(SUPERUSER_ID).with_context(no_reset_password=True)
        for agent in self.filtered(lambda a: a.active and a.partner_id):
            partner = agent.partner_id.commercial_partner_id or agent.partner_id
            if not partner:
                continue
            linked_users = User.search([("partner_id", "=", partner.id)])
            portal_users = linked_users.filtered("share")
            if portal_users:
                portal_users.write(
                    {
                        "group_ids": [
                            (4, portal_group.id),
                            (4, commission_group.id),
                        ]
                    }
                )
                continue
            login = self._generate_portal_login(User, partner, agent)
            email = partner.email or login
            if not partner.email:
                partner.with_user(SUPERUSER_ID).write({"email": email})
            password = uuid.uuid4().hex
            User.create(
                {
                    "name": partner.name or agent.name,
                    "login": login,
                    "email": email,
                    "partner_id": partner.id,
                    "password": password,
                    "share": True,
                    "group_ids": [
                        (6, 0, [portal_group.id, commission_group.id]),
                    ],
                }
            )

    @staticmethod
    def _generate_portal_login(user_model, partner, agent):
        """Generate a unique email/login for the portal user."""
        base_email = partner.email or ""
        local, sep, domain = base_email.partition("@")
        if sep:
            candidate = base_email
            index = 1
            while user_model.search([("login", "=", candidate)], limit=1):
                candidate = f"{local}+agent{agent.id or partner.id}_{index}@{domain}"
                index += 1
            return candidate
        candidate = f"agent_{agent.id or partner.id}@portal.auto"
        index = 1
        while user_model.search([("login", "=", candidate)], limit=1):
            candidate = f"agent_{agent.id or partner.id}_{index}@portal.auto"
            index += 1
        return candidate

    def get_portal_performance_weights(self):
        """Return structured performance weight data for portal rendering."""
        self.ensure_one()
        return [
            {
                "code": "order_confirm",
                "label": _("Order Confirmation"),
                "value": self.performance_volume_weight or 0,
            },
            {
                "code": "delivery",
                "label": _("Delivery"),
                "value": self.performance_recovery_weight or 0,
            },
            {
                "code": "payment",
                "label": _("Payment Clearance"),
                "value": self.performance_quality_weight or 0,
            },
            {
                "code": "feedback",
                "label": _("Feedback"),
                "value": self.performance_feedback_weight or 0,
            },
        ]

    def _auto_assign_commission_master(self, force=False):
        """Assign the suggested commission master when appropriate."""
        ctx = {self._CONTEXT_SKIP_MASTER_AUTOSET: True}
        for agent in self:
            suggestion = agent._get_suggested_master()
            if not suggestion:
                continue
            if force or agent._should_replace_commission_master(suggestion):
                agent.with_context(ctx).write({"commission_master_id": suggestion.id})

    def _should_replace_commission_master(self, suggestion):
        """Return whether the agent's master should be replaced by the suggestion."""
        self.ensure_one()
        current_master = self.commission_master_id
        if not current_master:
            return True
        if current_master == suggestion:
            return False
        if current_master.country_tag != self.country_tag:
            return True
        if current_master.applicable_channel not in (False, self.agent_type):
            return True
        return False

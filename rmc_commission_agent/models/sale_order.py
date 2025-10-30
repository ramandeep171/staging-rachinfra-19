from odoo import _, api, fields, models

from .utils import AGENT_CHANNEL_SELECTION


class SaleOrder(models.Model):
    _inherit = "sale.order"

    commission_agent_id = fields.Many2one(
        "rmc.commission.agent",
        string="Commission Agent",
        domain="[('active', '=', True)]",
        tracking=True,
    )
    commission_agent_channel_info = fields.Char(
        compute="_compute_commission_agent_channel_info",
        string="Agent Channel",
    )
    commission_master_id = fields.Many2one(
        "rmc.commission.master",
        string="Commission Master",
        domain="['&', ('country_tag', '=', commission_agent_id.country_tag), '|', "
        "('applicable_channel', '=', False), ('applicable_channel', '=', commission_agent_id.agent_type)]",
    )
    commission_master_suggestion_id = fields.Many2one(
        related="commission_agent_id.commission_master_suggestion_id",
        comodel_name="rmc.commission.master",
        string="Suggested Commission Master",
        readonly=True,
    )
    commission_stage = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("paid", "Paid"),
        ],
        default="draft",
        tracking=True,
    )
    commission_delivered_volume = fields.Float(
        string="Delivered Volume",
        help="Delivered volume used for dropshipping or distribution KPIs.",
    )
    commission_amount = fields.Monetary(
        string="Commission Amount",
        currency_field="currency_id",
    )
    commission_rental_start = fields.Date(string="Rental Start")
    commission_rental_end = fields.Date(string="Rental End")
    commission_equipment_reference = fields.Char(string="Equipment Reference")
    commission_recovery_rate = fields.Float(
        string="Recovery Rate (%)",
        help="Distribution KPI describing payment recovery rate.",
    )
    commission_repeat_order_count = fields.Integer(string="Repeat Orders")
    commission_retention_bonus_status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("eligible", "Eligible"),
            ("awarded", "Awarded"),
        ],
        default="pending",
        string="Retention Bonus",
    )
    commission_voucher_ids = fields.One2many(
        "rmc.commission.voucher",
        "sale_order_id",
        string="Commission Vouchers",
        readonly=True,
    )

    @api.depends("commission_agent_id")
    def _compute_commission_agent_channel_info(self):
        for order in self:
            agent = order.commission_agent_id
            if agent:
                channel_dict = dict(AGENT_CHANNEL_SELECTION)
                channel_label = channel_dict.get(agent.agent_type, agent.agent_type)
                tag_dict = dict(agent._fields["country_tag"].selection)
                tag_label = tag_dict.get(agent.country_tag, agent.country_tag)
                order.commission_agent_channel_info = _("%(channel)s channel - %(tag)s") % {
                    "channel": channel_label,
                    "tag": tag_label,
                }
            else:
                order.commission_agent_channel_info = False

    @api.onchange("commission_agent_id")
    def _onchange_commission_agent_id(self):
        for order in self:
            agent = order.commission_agent_id
            if agent:
                suggestion = agent._get_suggested_master()
                if suggestion:
                    order.commission_master_id = suggestion
            else:
                order.commission_master_id = False

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._ensure_commission_voucher()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "commission_stage" in vals or "commission_amount" in vals:
            for order in self:
                order._ensure_commission_voucher()
        return res

    def _ensure_commission_voucher(self):
        """Create a draft voucher when the commission reaches 100%."""
        self.ensure_one()
        if (
            self.commission_stage == "paid"
            and self.commission_amount
            and self.commission_agent_id
            and not self.commission_voucher_ids.filtered(lambda v: v.release_stage == "full")
        ):
            self.env["rmc.commission.voucher"].create(
                {
                    "sale_order_id": self.id,
                    "amount": self.commission_amount,
                    "percentage": 100.0,
                    "release_stage": "full",
                    "state": "draft",
                }
            )

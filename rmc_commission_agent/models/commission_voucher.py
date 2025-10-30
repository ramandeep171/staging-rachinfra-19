from odoo import _, api, fields, models


class RmcCommissionVoucher(models.Model):
    _name = "rmc.commission.voucher"
    _description = "Commission Voucher"
    _order = "create_date desc"

    name = fields.Char(required=True, copy=False, default="/")
    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    commission_agent_id = fields.Many2one(
        "rmc.commission.agent",
        related="sale_order_id.commission_agent_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="sale_order_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="sale_order_id.currency_id",
        store=True,
        readonly=True,
    )
    amount = fields.Monetary(
        string="Voucher Amount",
        required=True,
    )
    percentage = fields.Float(
        string="Release Percentage",
        default=100.0,
        help="Percentage of the total commission represented by this voucher.",
    )
    release_stage = fields.Selection(
        selection=[
            ("full", "Full Settlement"),
            ("partial", "Partial Release"),
        ],
        string="Release Stage",
        default="full",
    )
    release_date = fields.Date(
        string="Release Date",
        default=fields.Date.context_today,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("hold", "On Hold"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ("voucher_name_unique", "unique(name, company_id)", "Voucher reference must be unique per company."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                sale_order = self.env["sale.order"].browse(vals.get("sale_order_id"))
                if sale_order and sale_order.exists():
                    existing = self.search_count([("sale_order_id", "=", sale_order.id)])
                    vals["name"] = f"COM/{sale_order.name}/{existing + 1}"
                else:
                    vals["name"] = self.env["ir.sequence"].next_by_name("rmc.commission.voucher") or _("New Voucher")
        vouchers = super().create(vals_list)
        for voucher in vouchers:
            if not voucher.release_date:
                voucher.release_date = fields.Date.context_today(voucher)
            if not voucher.amount:
                voucher.amount = voucher.sale_order_id.commission_amount
        return vouchers

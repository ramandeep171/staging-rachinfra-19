from odoo import api, fields, models, _


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    workorder_id = fields.Many2one("mrp.workorder", string="Work Order", ondelete="set null")
    monthly_order_id = fields.Many2one(
        "gear.rmc.monthly.order",
        string="Monthly Work Order",
        related="workorder_id.production_id.x_monthly_order_id",
        store=True,
        readonly=True,
    )
    gear_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Bill of Materials",
        domain="[('company_id', 'in', [company_id, False]), '|', ('product_id', '=', product_id), ('product_tmpl_id', '=', product_template)]",
        check_company=True,
        help="BOM reference used when scrapping from a manufacturing order.",
    )
    gear_recipe_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Recipe",
        related="workorder_id.gear_docket_recipe_id",
        store=False,
        readonly=True,
        help="Recipe selected on the work order, shown here for quick reference.",
    )
    gear_recipe_line_ids = fields.Many2many(
        comodel_name="mrp.bom.line",
        string="Recipe Components",
        related="workorder_id.gear_recipe_line_ids",
        store=False,
        readonly=True,
        help="Component lines of the selected recipe for visibility while logging scrap.",
    )
    gear_recipe_component_ids = fields.One2many(
        comodel_name="gear.scrap.recipe.line",
        inverse_name="scrap_id",
        string="Recipe Components",
        help="Editable recipe component snapshot for this scrap record.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        workorder_id = self.env.context.get("default_workorder_id")
        workorder = self.env["mrp.workorder"].browse(workorder_id) if workorder_id else False
        if workorder:
            production = workorder.production_id
            warehouse = False
            if production and production.picking_type_id:
                warehouse = production.picking_type_id.warehouse_id
            if not warehouse:
                warehouse = self.env["stock.warehouse"].search(
                    [("company_id", "in", [production.company_id.id if production else False, False])],
                    limit=1,
                )
            if production and production.product_id:
                res.setdefault("product_id", production.product_id.id)
            if production and production.company_id:
                res.setdefault("company_id", production.company_id.id)
            if production:
                res.setdefault("production_id", production.id)
                if production.bom_id:
                    res.setdefault("gear_bom_id", production.bom_id.id)
            # Prefill editable recipe snapshot from the work order recipe lines.
            if workorder.gear_recipe_line_ids:
                res.setdefault(
                    "gear_recipe_component_ids",
                    [
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "quantity": line.product_qty,
                                "product_uom_id": line.product_uom_id.id,
                            },
                        )
                        for line in workorder.gear_recipe_line_ids
                    ],
                )

            # Resolve scrap location safely for v17 (company-level location).
            scrap_location = getattr(self.env.company, "stock_scrap_location_id", False)
            if not scrap_location:
                scrap_location = self.env.ref("stock.stock_location_scrap", raise_if_not_found=False)
            if scrap_location:
                res.setdefault("scrap_location_id", scrap_location.id)

            if production and production.location_src_id:
                res.setdefault("location_id", production.location_src_id.id)
            elif warehouse:
                res.setdefault("location_id", getattr(warehouse, "lot_stock_id", False) and warehouse.lot_stock_id.id)
            if production and production.name:
                res.setdefault("origin", production.name)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        scraps = super().create(vals_list)
        for scrap, vals in zip(scraps, vals_list):
            workorder = scrap.workorder_id
            if workorder:
                total = sum(self.search([("workorder_id", "=", workorder.id)]).mapped("scrap_qty"))
                workorder.scrap_qty = total
                monthly = scrap.monthly_order_id
                if monthly:
                    monthly.message_post(
                        body=_("Scrap recorded on work order %s: %s units.")
                        % (workorder.display_name, scrap.scrap_qty),
                        subtype_xmlid="mail.mt_note",
                    )
        return scraps


class GearScrapRecipeLine(models.Model):
    _name = "gear.scrap.recipe.line"
    _description = "Scrap Recipe Component"

    scrap_id = fields.Many2one("stock.scrap", string="Scrap", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", string="Component", required=True)
    quantity = fields.Float(string="Quantity", digits=(16, 2), default=0.0)
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
        domain="[]",
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id and not line.product_uom_id:
                line.product_uom_id = line.product_id.uom_id

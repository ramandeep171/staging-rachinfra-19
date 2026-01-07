from odoo import api, fields, models


class GearRmcManualOperation(models.Model):
    """Manual operations entry that references an existing RMC docket."""

    _name = "gear.rmc.manual.operation"
    _description = "RMC Manual Operation"
    _rec_name = "docket_no"
    _order = "id desc"

    docket_id = fields.Many2one(
        comodel_name="gear.rmc.docket",
        string="Docket",
        required=True,
        domain="[('source', '=', 'manual')]",
        ondelete="restrict",
    )
    docket_no = fields.Char(string="Docket Number", related="docket_id.docket_no", store=True, readonly=True)
    workorder_id = fields.Many2one("mrp.workorder", string="Work Order", related="docket_id.workorder_id", store=True, readonly=True)
    workcenter_id = fields.Many2one("mrp.workcenter", string="Work Center", related="docket_id.workcenter_id", store=True, readonly=True)
    product_id = fields.Many2one("product.product", string="Assigned Product", related="docket_id.product_id", store=True, readonly=True)
    recipe_display_mode = fields.Selection(
        [("on_production", "On Production"), ("after_production", "After Production")],
        string="Recipe Mode",
        default="on_production",
    )
    quantity_produced = fields.Float(string="Quantity Produced (m³)", related="docket_id.quantity_produced", store=True, readonly=True)
    quantity_ordered = fields.Float(string="Quantity Ordered (m³)", related="docket_id.quantity_ordered", store=True, readonly=True)
    qty_m3 = fields.Float(string="Quantity (m³)", related="docket_id.qty_m3", store=True, readonly=True)
    manual_qty_total = fields.Float(string="Manual Quantity", digits=(16, 3), default=0.0)
    tm_number = fields.Char(string="TM Number", related="docket_id.tm_number", store=True, readonly=True)
    driver_name = fields.Char(string="Driver Name", related="docket_id.driver_name", store=True, readonly=True)
    operator_user_id = fields.Many2one("res.users", string="Operator User", related="docket_id.operator_user_id", store=True, readonly=True)
    recipe_id = fields.Many2one("mrp.bom", string="Recipe", related="docket_id.recipe_id", store=True, readonly=True)
    batching_time = fields.Datetime(string="Batching Time", related="docket_id.batching_time", store=True, readonly=True)
    customer_id = fields.Many2one("res.partner", string="Customer", related="docket_id.customer_id", store=True, readonly=True)
    date = fields.Date(string="Production Date", related="docket_id.date", store=True, readonly=True)
    docket_line_ids = fields.One2many(
        comodel_name="gear.rmc.docket.line",
        inverse_name="docket_id",
        string="Recipe Lines",
        compute="_compute_docket_relations",
        readonly=True,
    )
    docket_batch_ids = fields.One2many(
        comodel_name="gear.rmc.docket.batch",
        inverse_name="docket_id",
        string="Batches",
        compute="_compute_docket_relations",
        readonly=True,
    )
    manual_recipe_line_ids = fields.One2many(
        comodel_name="gear.rmc.manual.operation.line",
        inverse_name="manual_operation_id",
        string="After Production Recipe Lines",
        copy=False,
    )

    @api.onchange("recipe_display_mode", "product_id", "docket_id")
    def _onchange_recipe_display_mode(self):
        self._sync_manual_recipe_lines()

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ["recipe_display_mode", "product_id", "docket_id"]):
            self._sync_manual_recipe_lines()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_manual_recipe_lines()
        return records

    def _sync_manual_recipe_lines(self):
        for rec in self:
            after_mode = rec.recipe_display_mode == "after_production"
            rec.manual_qty_total = 1.0 if after_mode else (rec.manual_qty_total or 0.0)
            commands = [(5, 0, 0)]
            source_lines = rec.docket_line_ids or (rec.recipe_id and rec.recipe_id.bom_line_ids) or False
            if source_lines:
                for line in source_lines:
                    mat_name = getattr(line, "material_name", False) or getattr(line, "product_id", False) and line.product_id.display_name
                    mat_code = getattr(line, "material_code", False) or getattr(line, "product_id", False) and line.product_id.default_code
                    commands.append(
                        (
                            0,
                            0,
                            {
                                "material_name": mat_name,
                                "material_code": mat_code,
                                "design_qty": 1.0 if after_mode else getattr(line, "design_qty", 0.0),
                                "actual_qty": 1.0 if after_mode else getattr(line, "actual_qty", 0.0),
                                "manual_qty": 1.0 if after_mode else 0.0,
                            },
                        )
                    )
            elif rec.product_id:
                vals = {
                    "material_name": rec.product_id.display_name,
                    "material_code": rec.product_id.default_code,
                    "design_qty": 1.0 if after_mode else 0.0,
                    "actual_qty": 1.0 if after_mode else 0.0,
                    "manual_qty": 1.0 if after_mode else 0.0,
                }
                commands.append(
                    (
                        0,
                        0,
                        vals,
                    )
                )
            rec.manual_recipe_line_ids = commands

    @api.depends("docket_id", "docket_id.docket_line_ids", "docket_id.docket_batch_ids")
    def _compute_docket_relations(self):
        for rec in self:
            rec.docket_line_ids = rec.docket_id.docket_line_ids
            rec.docket_batch_ids = rec.docket_id.docket_batch_ids


class GearRmcManualOperationLine(models.Model):
    _name = "gear.rmc.manual.operation.line"
    _description = "Manual Operation Recipe Line"

    manual_operation_id = fields.Many2one("gear.rmc.manual.operation", string="Manual Operation", ondelete="cascade")
    material_name = fields.Char(string="Material Name")
    material_code = fields.Char(string="Material Code")
    design_qty = fields.Float(string="Design Qty (kg)", digits=(16, 3), default=0.0)
    actual_qty = fields.Float(string="Actual Qty (kg)", digits=(16, 3), default=0.0)
    manual_qty = fields.Float(string="Manual Qty", digits=(16, 3), default=0.0)
    variance = fields.Float(string="Variance (kg)", compute="_compute_variance", store=True, digits=(16, 3))
    variance_percentage = fields.Float(string="Variance %", compute="_compute_variance", store=True, digits=(16, 3))

    @api.depends("design_qty", "actual_qty", "manual_qty")
    def _compute_variance(self):
        for line in self:
            design = line.design_qty or 0.0
            actual = line.manual_qty if line.manual_qty not in (False, None) else (line.actual_qty or 0.0)
            variance = actual - design
            pct = (variance / design * 100.0) if design else 0.0
            line.variance = variance
            line.variance_percentage = pct

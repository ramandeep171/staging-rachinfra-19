import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gear_silent_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Silent Warehouse",
        domain="[('company_id', '=', company_id)]",
        help="Warehouse used for the without-inventory production flow.",
    )
    gear_cycle_runtime_threshold = fields.Float(
        string="Cycle Runtime Threshold (min)",
        default=60.0,
        help="Runtime minutes after which a reason must be provided on dockets/work orders.",
        config_parameter="gear_on_rent.cycle_runtime_threshold",
        company_dependent=True,
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        company = self.env.company
        param_model = self.env["ir.config_parameter"].sudo()
        company_key = f"gear_on_rent.silent_warehouse_id.{company.id}"
        param_value = param_model.get_param(company_key)
        if not param_value:
            param_value = param_model.get_param("gear_on_rent.silent_warehouse_id")
        silent_wh = False
        try:
            silent_wh = int(param_value) if param_value else False
        except (TypeError, ValueError):
            _logger.warning("Invalid silent warehouse parameter value: %s", param_value)
        res.update({"gear_silent_warehouse_id": silent_wh})
        return res

    def set_values(self):
        res = super().set_values()
        param_model = self.env["ir.config_parameter"].sudo()
        company_key = f"gear_on_rent.silent_warehouse_id.{self.env.company.id}"
        param_model.set_param(company_key, self.gear_silent_warehouse_id.id or False)
        return res

from odoo import api, fields, models


class AccountMoveExt(models.Model):
    _inherit = 'account.move'

    # Optional relation to maintenance.jobcard if that module is installed.
    # Use string reference to avoid import-time dependency. If the model is missing,
    # the field will be gracefully ignored at runtime for many operations, but
    # having the field declared prevents view parsing errors client-side.
    jobcard_id = fields.Many2one('maintenance.jobcard', string='Jobcard', ondelete='set null')


class AccountMove(models.Model):
    _inherit = 'account.move'

    docket_id = fields.Many2one('rmc.docket', string='RMC Docket', readonly=True)
    plant_check_id = fields.Many2one('rmc.plant_check', string='Plant Check', readonly=True)
    delivery_challan_number = fields.Char(string='Delivery Challan Number')
    delivery_date = fields.Date(string='Delivery Date')
    vehicle_number = fields.Char(string='Vehicle Number')
    transporter_name = fields.Char(string='Transporter Name')
    driver_name = fields.Char(string='Driver Name')
    driver_mobile = fields.Char(string='Driver Mobile')
    lr_number = fields.Char(string='LR Number')
    batch_number = fields.Char(string='Batch Number')
    batching_time = fields.Char(string='Batching Time')
    delivery_time = fields.Char(string='Delivery Time')
    slump_at_site = fields.Float(string='Slump at Site')
    receiver_mobile = fields.Char(string='Receiver Mobile')
    is_rmc_product = fields.Boolean(string='Is RMC Product', compute='_compute_is_rmc_product', store=True)
    # Pump info
    pump_required = fields.Boolean(string='Pump Required?')
    pump_provider_name = fields.Char(string='Pump Provider')
    pump_code = fields.Char(string='Pump Code')

    @api.depends(
        'invoice_line_ids.product_id',
        'invoice_line_ids.product_id.categ_id',
        'invoice_line_ids.product_id.product_tmpl_id.is_rmc_product',
        'invoice_line_ids.product_id.categ_id.is_rmc_category',
    )
    def _compute_is_rmc_product(self):
        for move in self:
            is_rmc = False
            for line in move.invoice_line_ids:
                product = line.product_id
                if not product:
                    continue
                tmpl = product.product_tmpl_id
                cat = product.categ_id
                # 1) Explicit category flag
                if cat and getattr(cat, 'is_rmc_category', False):
                    is_rmc = True
                    break
                # 2) Category name heuristic (RMC or Concrete)
                if cat and (('RMC' in (cat.name or '').upper()) or ('CONCRETE' in (cat.name or '').upper())):
                    is_rmc = True
                    break
                # 3) Product template flag as fallback
                if tmpl and getattr(tmpl, 'is_rmc_product', False):
                    is_rmc = True
                    break
            move.is_rmc_product = is_rmc

    def action_print_rmc_invoice(self):
        """Return the RMC invoice report action for selected invoices.
        Only meaningful when the move has at least one RMC product line.
        """
        self.ensure_one()
        action = self.env.ref('rmc_management_system.action_report_rmc_invoice')
        if action:
            return action.report_action(self)
        return False

    def action_print_pdf(self):
        """Use RMC invoice report by default for RMC invoices; fallback to standard."""
        self.ensure_one()
        if getattr(self, 'is_rmc_product', False):
            r = self.env.ref('rmc_management_system.action_report_rmc_invoice', raise_if_not_found=False)
            if r:
                return r.report_action(self.id)
        return super().action_print_pdf()


class AccountMoveSendOverride(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_default_pdf_report_id(self, move):
        # If it's an RMC invoice, use RMC report; else default behavior
        try:
            if move and getattr(move, 'is_rmc_product', False):
                r = self.env.ref('rmc_management_system.action_report_rmc_invoice', raise_if_not_found=False)
                if r:
                    return r
        except Exception:
            # Fallback to super in any unexpected case
            pass
        return super()._get_default_pdf_report_id(move)

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    subcontractor_id = fields.Many2one('res.partner', string="Subcontractor", domain="[('is_company', '=', True)]")
    plant_code = fields.Char(string="Plant Code", required=True, help="Unique per plant")

    @api.onchange('product_tmpl_id', 'product_id')
    def _onchange_product_tmpl_id(self):
        """Auto-populate BOM lines with standard RMC raw materials if product is RMC"""
        if self._is_rmc_product():
            self._auto_add_rmc_materials()

    def _is_rmc_product(self):
        """Check if the product is an RMC product"""
        # Check both product_tmpl_id and product_id
        if self.product_tmpl_id and self.product_tmpl_id.is_rmc_product:
            return True
        if self.product_id and self.product_id.product_tmpl_id.is_rmc_product:
            return True
        return False

    def _auto_add_rmc_materials(self):
        """Auto-populate BOM lines with predefined RMC raw materials"""
        standard_materials = [
            {'product_code': 'CEM', 'product_name': 'Cement', 'product_qty': 300.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
            {'product_code': 'SAND', 'product_name': 'Sand', 'product_qty': 600.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
            {'product_code': 'AGG10', 'product_name': '10mm Aggregate', 'product_qty': 400.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
            {'product_code': 'AGG20', 'product_name': '20mm Aggregate', 'product_qty': 800.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
            {'product_code': 'FLYASH', 'product_name': 'Fly Ash', 'product_qty': 50.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
            {'product_code': 'WATER', 'product_name': 'Water', 'product_qty': 150.0, 'product_uom_id': self.env.ref('uom.product_uom_litre').id},
            {'product_code': 'ADMIX', 'product_name': 'Admixture', 'product_qty': 2.0, 'product_uom_id': self.env.ref('uom.product_uom_kgm').id},
        ]

        existing_codes = set(self.bom_line_ids.mapped('product_code'))
        new_lines = []

        for material in standard_materials:
            if material['product_code'] not in existing_codes:
                # Find or create product
                product = self.env['product.product'].search([('default_code', '=', material['product_code'])], limit=1)
                if not product:
                    product = self.env['product.product'].create({
                        'name': material['product_name'],
                        'default_code': material['product_code'],
                        'type': 'consu',  # Use 'consu' for consumable/goods
                        'uom_id': material['product_uom_id'],
                        'uom_po_id': material['product_uom_id'],
                    })

                new_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_qty': material['product_qty'],
                    'product_uom_id': material['product_uom_id'],
                    'product_code': material['product_code'],
                }))

        if new_lines:
            self.bom_line_ids = new_lines

    def action_add_rmc_materials(self):
        """Manually add RMC materials - for testing/debugging"""
        if self.product_tmpl_id:
            if self.product_tmpl_id.is_rmc_product:
                self._auto_add_rmc_materials()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'RMC materials have been added to the BOM.',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Product Not Marked as RMC',
                        'message': f'The product "{self.product_tmpl_id.name}" is not marked as an RMC product. Please go to the product and check "Is RMC Product".',
                        'type': 'warning',
                    }
                }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Product Selected',
                    'message': 'Please select a product first.',
                    'type': 'warning',
                }
            }


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    product_code = fields.Char(string="Raw Material Code", help="Code for the raw material")
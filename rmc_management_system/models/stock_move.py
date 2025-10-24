from odoo import models, fields, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        res = super().button_confirm()
        for po in self:
            self.env['stock.move']._auto_shift_on_po(po)
        return res

class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def _get_default_parent_location(self, company):
        """Return a view location suitable as parent for new internal locations."""
        company = company or self.env.company
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        if warehouse and warehouse.view_location_id:
            return warehouse.view_location_id
        parent_location = self.env['stock.location'].search([
            ('usage', '=', 'view'),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        if parent_location:
            return parent_location
        raise ValueError(f"No parent view location found for company {company.display_name}.")

    @api.model
    def _create_move(self, from_loc, to_loc, product, qty):
        move_vals = {
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'location_id': from_loc.id,
            'location_dest_id': to_loc.id,
            'state': 'draft',
            'company_id': from_loc.company_id.id or to_loc.company_id.id or self.env.company.id,
        }
        # Add user friendly label for chatter / traceability using available description fields.
        move_vals['description_picking'] = product.display_name
        move = self.create(move_vals)
        move._action_confirm()
        move._action_assign()
        move._action_done()
        return move

    @api.model
    def _auto_shift_on_po(self, po):
        if po.order_line and po.partner_id:
            subcontractor = po.partner_id
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', po.company_id.id)], limit=1)
            subcontractor_loc = self.env['stock.location'].search([('name', '=', f'{subcontractor.name} Warehouse')], limit=1)
            if not subcontractor_loc:
                parent_location = self._get_default_parent_location(po.company_id)
                subcontractor_loc = self.env['stock.location'].create({
                    'name': f'{subcontractor.name} Warehouse',
                    'usage': 'internal',
                    'location_id': parent_location.id,
                    'company_id': po.company_id.id,
                })
            for line in po.order_line:
                product = line.product_id
                qty = line.product_qty
                self._create_move(warehouse.lot_stock_id if warehouse else self.env.ref('stock.stock_location_stock'), subcontractor_loc, product, qty)
                # Determine material_type from product category
                material_type = 'other'
                if product.categ_id:
                    categ_name = product.categ_id.name.lower()
                    if 'cement' in categ_name:
                        material_type = 'cement'
                    elif 'sand' in categ_name:
                        material_type = 'sand'
                    elif 'aggregate' in categ_name or 'gravel' in categ_name:
                        material_type = 'aggregate'
                self.env['rmc.material.balance']._update_balance(subcontractor, material_type, qty)

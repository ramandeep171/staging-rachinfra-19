# -*- coding: utf-8 -*-
##############################################################################
#
#    odoo, Open Source Management Solution
#    Copyright (C) 2018 BroadTech IT Solutions Pvt Ltd 
#    (<http://broadtech-innovations.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class BtAssetMove(models.Model):
    _name = "bt.asset.move"
    _description = "Asset Move"

    name = fields.Char(string='Name', default="New", copy=False)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    from_loc_id = fields.Many2one(
        'stock.location',
        string='From Location',
        required=True,
        check_company=True,
    )
    asset_id = fields.Many2one('bt.asset', string='Asset', required=True, copy=False, check_company=True)
    to_loc_id = fields.Many2one(
        'stock.location',
        string='To Location',
        required=True,
        check_company=True,
    )
    state = fields.Selection([
            ('draft', 'Draft'),
            ('done', 'Done')], string='State', tracking=True, default='draft', copy=False)
    
    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('bt.asset.move') or _('New')
            if vals.get('asset_id') and not vals.get('company_id'):
                asset = self.env['bt.asset'].browse(vals['asset_id'])
                vals['company_id'] = asset.company_id.id
            vals.setdefault('company_id', self.env.company.id)
        moves = super().create(vals_list)
        moves._check_move_constraints()
        return moves
    
    def write(self, vals):
        result = super().write(vals)
        self._check_move_constraints()
        return result
    
    def _check_move_constraints(self):
        for move in self:
            if move.from_loc_id and move.to_loc_id and move.from_loc_id == move.to_loc_id:
                raise ValidationError(_("From location and to location must be different."))
            if move.asset_id and move.asset_id.current_loc_id != move.from_loc_id:
                raise ValidationError(_("Current location and from location must be same while creating asset move."))
            if move.asset_id and move.asset_id.company_id and move.company_id and move.asset_id.company_id != move.company_id:
                raise ValidationError(_("Asset and move must belong to the same company."))
            if move.from_loc_id and move.from_loc_id.company_id and move.asset_id.company_id and move.from_loc_id.company_id != move.asset_id.company_id:
                raise ValidationError(_("From location company must match asset company."))
            if move.to_loc_id and move.to_loc_id.company_id and move.asset_id.company_id and move.to_loc_id.company_id != move.asset_id.company_id:
                raise ValidationError(_("To location company must match asset company."))
            for loc in (move.from_loc_id, move.to_loc_id):
                if loc and loc.usage != 'internal':
                    raise ValidationError(_("Move locations must be internal stock locations."))
    
    def action_move(self):
        for move in self:
            if move.state == 'done':
                continue
            if not move.asset_id:
                raise ValidationError(_("Please set an asset before validating the move."))
            move.asset_id.current_loc_id = move.to_loc_id
            move.state = 'done'
        return True
    
# vim:expandtab:smartindent:tabstop=2:softtabstop=2:shiftwidth=2:

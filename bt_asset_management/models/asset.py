# -*- coding: utf-8 -*-
##############################################################################
#
#    odoo, Open Source Management Solution
#    Copyright (C) 2018-BroadTech IT Solutions (<http://www.broadtech-innovations.com/>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
##############################################################################

import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BtAsset(models.Model):
    _name = "bt.asset"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Asset"
    _sql_constraints = [
        ('asset_code_unique', 'unique(asset_code)', 'Asset code must be unique.'),
    ]

    def _get_default_location(self):
        company = self.env.company
        warehouse = self.env['stock.warehouse'].with_company(company).search(
            [('company_id', '=', company.id)],
            order='id',
            limit=1,
        )
        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id
        location = self.env['stock.location'].with_company(company).search(
            [
                ('usage', '=', 'internal'),
                ('company_id', 'in', [company.id, False]),
            ],
            order='id',
            limit=1,
        )
        if not location:
            raise UserError(_("Please configure an internal stock location first."))
        return location

    name = fields.Char(string='Name', required=True)
    asset_type = fields.Selection(
        [
            ('main', 'Main'),
            ('component', 'Component'),
        ],
        string='Asset Type',
        default='component',
        required=True,
        tracking=True,
    )
    account_asset_id = fields.Many2one(
        'account.asset',
        string='Account Asset',
        copy=False,
        check_company=True,
    )
    parent_id = fields.Many2one(
        'bt.asset',
        string='Parent Asset',
        copy=False,
        check_company=True,
    )
    child_ids = fields.One2many(
        'bt.asset',
        'parent_id',
        string='Component Assets',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    purchase_date = fields.Date(string='Purchase Date', tracking=True)
    purchase_value = fields.Float(string='Purchase Value', tracking=True)
    asset_code = fields.Char(string='Asset Code', copy=False)
    component_type = fields.Selection(
        [
            ('pump', 'Pump'),
            ('membrane', 'Membrane'),
            ('panel', 'Panel'),
            ('flow_meter', 'Flow Meter'),
        ],
        string='Component Type',
        tracking=True,
    )
    capital_value = fields.Float(
        string='Capital Value',
        compute='_compute_costs',
        readonly=True,
        help='Analytical capital amount derived from the asset purchase value.',
    )
    maintenance_cost_total = fields.Float(
        string='Maintenance Cost (Analytical)',
        compute='_compute_costs',
        readonly=True,
        help='Sum of non-cancelled maintenance request costs linked to the asset equipment.',
    )
    lifecycle_cost_total = fields.Float(
        string='Total Lifecycle Cost',
        compute='_compute_costs',
        readonly=True,
        help='Analytical total cost = capital value + maintenance cost.',
    )
    custodian_id = fields.Many2one(
        'res.partner',
        string='Custodian',
        tracking=True,
    )
    qty_requested = fields.Integer(
        string='Quantity',
        default=1,
        copy=False,
        help='Quantity requested for asset creation. If greater than 1, individual assets are generated per unit.',
    )
    is_created = fields.Boolean('Created', copy=False)
    current_loc_id = fields.Many2one(
        'stock.location',
        string="Current Location",
        default=_get_default_location,
        required=True,
        tracking=True,
        check_company=True,
    )
    maintenance_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Maintenance Equipment',
        copy=False,
        check_company=True,
    )
    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Fleet Vehicle',
        copy=False,
        check_company=True,
    )
    model_name = fields.Char(string='Model Name')
    serial_no = fields.Char(string='Serial No', tracking=True)
    manufacturer = fields.Char(string='Manufacturer')
    warranty_start = fields.Date(string='Warranty Start')
    warranty_end = fields.Date(string='Warranty End')
    category_id = fields.Many2one('bt.asset.category', string='Category Id', check_company=True)
    note = fields.Text(string='Internal Notes')
    operational_status = fields.Selection(
        [
            ('active', 'Active'),
            ('idle', 'Idle'),
            ('breakdown', 'Breakdown'),
            ('disposed', 'Disposed'),
        ],
        string='Operational Status',
        default='active',
        tracking=True,
    )
    state = fields.Selection([
            ('active', 'Active'),
            ('scrapped', 'Scrapped')], string='State', tracking=True, default='active', copy=False)
    image_1920 = fields.Image(
        "Image",
        max_width=1024,
        max_height=1024,
        help="Image used as the main picture for the asset, limited to 1024x1024px.",
    )

    @api.depends('purchase_value', 'maintenance_equipment_id')
    def _compute_costs(self):
        equipment_cost_map = {}
        equipment_ids = list({asset.maintenance_equipment_id.id for asset in self if asset.maintenance_equipment_id})
        companies = self.mapped('company_id') or self.env.companies
        if equipment_ids and self.env.registry.get('maintenance.request'):
            request_model = self.env['maintenance.request']
            if 'cost' in request_model._fields:
                domain = [
                    ('equipment_id', 'in', equipment_ids),
                    ('state', 'not in', ['cancel', 'draft']),
                ]
                if 'company_id' in request_model._fields:
                    domain.append(('company_id', 'in', companies.ids))
                groups = request_model.read_group(
                    domain,
                    ['cost:sum'],
                    ['equipment_id'],
                )
                equipment_cost_map = {group['equipment_id'][0]: group['cost_sum'] for group in groups if group.get('equipment_id')}
        for asset in self:
            capital_value = asset.purchase_value or 0.0
            maintenance_total = equipment_cost_map.get(asset.maintenance_equipment_id.id, 0.0) if asset.maintenance_equipment_id else 0.0
            asset.capital_value = capital_value
            asset.maintenance_cost_total = maintenance_total
            asset.lifecycle_cost_total = capital_value + maintenance_total

    @api.constrains('qty_requested')
    def _check_qty_requested(self):
        for asset in self:
            if asset.qty_requested is not None and asset.qty_requested < 1:
                raise ValidationError(_("Quantity must be at least 1."))

    @api.constrains('maintenance_equipment_id', 'fleet_vehicle_id')
    def _check_operation_links(self):
        for asset in self:
            if asset.maintenance_equipment_id and asset.fleet_vehicle_id:
                raise ValidationError(
                    _("An asset can link to either Maintenance Equipment or Fleet Vehicle, not both."),
                )
            if asset.maintenance_equipment_id:
                existing = self.search([
                    ('maintenance_equipment_id', '=', asset.maintenance_equipment_id.id),
                    ('id', '!=', asset.id),
                    ('company_id', '=', asset.company_id.id),
                ], limit=1)
                if existing:
                    raise ValidationError(
                        _("Maintenance equipment is already linked to asset %s.") % existing.display_name,
                    )
            if asset.fleet_vehicle_id:
                existing = self.search([
                    ('fleet_vehicle_id', '=', asset.fleet_vehicle_id.id),
                    ('id', '!=', asset.id),
                    ('company_id', '=', asset.company_id.id),
                ], limit=1)
                if existing:
                    raise ValidationError(
                        _("Fleet vehicle is already linked to asset %s.") % existing.display_name,
                    )

    @api.constrains('asset_type', 'account_asset_id', 'parent_id')
    def _check_asset_hierarchy_constraints(self):
        for asset in self:
            if asset.asset_type == 'main':
                if asset.parent_id:
                    raise UserError(_("Main assets cannot have a parent asset."))
            if asset.asset_type == 'component':
                if asset.account_asset_id:
                    raise UserError(_("Component assets cannot be linked to an account asset."))
                if not asset.parent_id:
                    raise UserError(_("Component assets must have a parent asset."))
                if asset.parent_id and asset.parent_id.asset_type != 'main':
                    raise UserError(_("Component assets must have a main asset as parent."))

    @api.constrains('current_loc_id')
    def _check_current_location_usage(self):
        for asset in self:
            if asset.current_loc_id and asset.current_loc_id.usage != 'internal':
                raise ValidationError(_("Current location must be an internal stock location."))

    def _get_default_category(self, company_id=None):
        company = company_id or self.env.company.id
        category = self.env['bt.asset.category'].with_company(company).search(
            [('company_id', 'in', [company, False])],
            order='auto_asset_code desc, id',
            limit=1,
        )
        if not category:
            raise ValidationError(_("Configure an asset category before creating assets."))
        return category

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('asset_type') == 'component' and not vals.get('parent_id'):
                raise UserError(_("Component assets must have a parent asset."))
            if vals.get('asset_type') == 'component' and vals.get('parent_id') and not vals.get('category_id'):
                parent_asset = self.env['bt.asset'].browse(vals['parent_id'])
                if parent_asset:
                    vals['category_id'] = parent_asset.category_id.id
            qty = int(vals.get('qty_requested') or 1)
            if qty < 1:
                raise ValidationError(_("Quantity must be at least 1."))
            if vals.get('asset_code'):
                raise ValidationError(_("Asset code is system-generated and cannot be set manually."))
            if qty > 1 and (vals.get('maintenance_equipment_id') or vals.get('fleet_vehicle_id')):
                raise ValidationError(
                    _("Cannot split quantity when a maintenance equipment or fleet vehicle link is provided. Create one asset at a time."),
                )

            company_id = vals.get('company_id')
            if vals.get('current_loc_id'):
                company_id = self.env['stock.location'].browse(vals['current_loc_id']).company_id.id or company_id
            elif vals.get('asset_type') == 'component' and vals.get('parent_id'):
                parent = self.env['bt.asset'].browse(vals['parent_id'])
                if parent.current_loc_id:
                    vals['current_loc_id'] = parent.current_loc_id.id
                    company_id = parent.current_loc_id.company_id.id or company_id
            company_id = company_id or self.env.company.id

            if not vals.get('category_id'):
                if vals.get('parent_id'):
                    parent = self.env['bt.asset'].browse(vals['parent_id'])
                    if parent.category_id:
                        vals['category_id'] = parent.category_id.id
                if not vals.get('category_id'):
                    vals['category_id'] = self._get_default_category(company_id).id

            if vals.get('category_id'):
                company_id = self.env['bt.asset.category'].browse(vals['category_id']).company_id.id or company_id

            total_value = vals.get('purchase_value')
            per_unit_value = total_value / qty if total_value is not None else None

            base_vals = dict(
                vals,
                qty_requested=1,
                purchase_value=per_unit_value,
                company_id=company_id,
            )
            for i in range(qty):
                new_vals = dict(base_vals)
                new_vals.setdefault('is_created', True)
                generated_code = self._generate_asset_code(new_vals)
                if not generated_code:
                    raise ValidationError(_("Unable to generate asset code."))
                new_vals['asset_code'] = generated_code
                prepared_vals_list.append(new_vals)

        assets = super().create(prepared_vals_list)
        if self.env.context.get('from_account_asset'):
            for asset in assets.filtered(lambda a: a.account_asset_id):
                try:
                    asset._schedule_assign_equipment_activity()
                except Exception:
                    _logger.exception("Failed to schedule equipment assignment activity for asset %s", asset.id)
        for asset in assets:
            if asset.asset_code:
                body = _("Asset %s created with asset code %s") % (asset.name, asset.asset_code)
            else:
                body = _("Asset %s created") % asset.name
            asset.message_post(body=body)
        return assets

    def _get_asset_category(self, vals=None):
        vals = vals or {}
        category_id = vals.get('category_id') or self.category_id.id
        if not category_id and vals.get('parent_id'):
            parent = self.env['bt.asset'].browse(vals['parent_id'])
            category_id = parent.category_id.id
        if not category_id:
            raise ValidationError(_("Category is required to generate an asset code."))
        category = self.env['bt.asset.category'].browse(category_id)
        if not category:
            raise ValidationError(_("Invalid category provided for asset code generation."))
        return category

    def _generate_asset_code(self, vals=None):
        category = self._get_asset_category(vals or {})
        code = category._generate_asset_code()
        if not code:
            raise ValidationError(_("Unable to generate asset code for category %s.") % category.display_name)
        return code

    def write(self, vals):
        if 'asset_code' in vals:
            for asset in self:
                if asset.is_created and vals.get('asset_code') != asset.asset_code:
                    raise ValidationError(_("Asset code cannot be modified after creation."))
        if not self.env.context.get('allow_asset_split'):
            if 'maintenance_equipment_id' in vals:
                for asset in self:
                    if asset.maintenance_equipment_id and vals.get('maintenance_equipment_id') != asset.maintenance_equipment_id.id:
                        raise ValidationError(_("Maintenance equipment link cannot be changed once set."))
            if 'fleet_vehicle_id' in vals:
                for asset in self:
                    if asset.fleet_vehicle_id and vals.get('fleet_vehicle_id') != asset.fleet_vehicle_id.id:
                        raise ValidationError(_("Fleet vehicle link cannot be changed once set."))
        res = super().write(vals)
        if vals.get('maintenance_equipment_id'):
            self._complete_assign_equipment_activity()
        return res

    def _get_assign_activity_user(self):
        self.ensure_one()
        account_asset = self.account_asset_id
        responsible = False
        if account_asset:
            for field_name in ('responsible_user_id', 'user_id'):
                if field_name in account_asset._fields:
                    candidate = getattr(account_asset, field_name)
                    if candidate:
                        responsible = candidate
                        break
            if not responsible and account_asset.create_uid:
                responsible = account_asset.create_uid
        if not responsible:
            admin = self.env.ref('base.user_admin', raise_if_not_found=False)
            responsible = admin or self.env.user
        return responsible

    def _schedule_assign_equipment_activity(self):
        self.ensure_one()
        if self.maintenance_equipment_id:
            return False
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_type:
            return False
        existing = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'bt.asset'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', todo_type.id),
            ('summary', '=', _('Assign Equipment')),
        ], limit=1)
        if existing:
            return existing
        user = self._get_assign_activity_user()
        try:
            return self.env['mail.activity'].sudo().create({
                'res_model': 'bt.asset',
                'res_id': self.id,
                'activity_type_id': todo_type.id,
                'user_id': user.id if user else False,
                'summary': _('Assign Equipment'),
                'note': _('Please assign this asset to equipment to activate it.'),
            })
        except Exception:
            _logger.exception("Failed to create assign equipment activity for asset %s", self.id)
            return False

    def _complete_assign_equipment_activity(self):
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_type:
            return
        activities = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'bt.asset'),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', todo_type.id),
            ('summary', '=', _('Assign Equipment')),
        ])
        if activities:
            activities.action_feedback(feedback=_("Equipment assigned."))
        return True

    def action_split_quantity(self):
        for asset in self:
            if asset.qty_requested <= 1:
                raise ValidationError(_("Set quantity greater than 1 to split assets."))
        new_assets = self.env['bt.asset']
        for asset in self:
            qty = int(asset.qty_requested or 1)
            per_unit_value = (asset.purchase_value or 0.0) / qty if qty else 0.0
            base_vals = {
                'asset_type': asset.asset_type,
                'parent_id': asset.parent_id.id,
                'account_asset_id': asset.account_asset_id.id,
                'name': asset.name,
                'purchase_date': asset.purchase_date,
                'purchase_value': per_unit_value,
                'category_id': asset.category_id.id,
                'company_id': asset.company_id.id,
                'current_loc_id': asset.current_loc_id.id,
                'component_type': asset.component_type,
                'custodian_id': asset.custodian_id.id,
                'operational_status': asset.operational_status,
                'model_name': asset.model_name,
                'serial_no': asset.serial_no,
                'manufacturer': asset.manufacturer,
                'warranty_start': asset.warranty_start,
                'warranty_end': asset.warranty_end,
                'note': asset.note,
                'image_1920': asset.image_1920,
                'qty_requested': 1,
                'is_created': True,
            }
            # Create additional assets
            create_vals = [dict(base_vals) for i in range(qty - 1)]
            if create_vals:
                new_assets |= self.with_context(allow_asset_split=True).create(create_vals)
            # Update current asset to be one unit
            asset.with_context(allow_asset_split=True).write({
                'qty_requested': 1,
                'purchase_value': per_unit_value,
            })
        if new_assets:
            msg = _("%s asset(s) created from quantity split.") % len(new_assets)
            self.message_post(body=msg)
        return True
    
    def action_move_vals(self):
        for asset in self:
            scrap_location = asset.company_id.stock_scrap_location_id or self.env.company.stock_scrap_location_id
            if not scrap_location:
                scrap_location = self.env['stock.location'].search([
                    ('scrap_location', '=', True),
                    ('usage', '=', 'inventory'),
                    ('company_id', 'in', [asset.company_id.id, False]),
                ], limit=1)
            if not scrap_location:
                raise UserError(_("Please set a scrap location first"))
            if asset.state == 'scrapped':
                raise UserError(_("Asset %s is already scrapped.") % asset.display_name)
            move_vals = {
                'from_loc_id': asset.current_loc_id.id,
                'asset_id': asset.id,
                'to_loc_id': scrap_location.id,
            }
            asset_move = self.env['bt.asset.move'].create(move_vals)
            asset_move.action_move()
            asset.state = 'scrapped'
            asset.message_post(body=_("Asset scrapped to location %s") % scrap_location.display_name)
        return True

    def action_open_maintenance_equipment(self):
        self.ensure_one()
        equipment = self.maintenance_equipment_id
        if not equipment:
            raise UserError(_("No maintenance equipment linked to this asset."))
        try:
            equipment.check_access_rights('read')
            equipment.check_access_rule('read')
        except AccessError:
            raise UserError(_("You do not have access to the linked maintenance equipment."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Equipment'),
            'res_model': 'maintenance.equipment',
            'view_mode': 'form',
            'res_id': equipment.id,
            'target': 'current',
        }

    def action_open_fleet_vehicle(self):
        self.ensure_one()
        vehicle = self.fleet_vehicle_id
        if not vehicle:
            raise UserError(_("No fleet vehicle linked to this asset."))
        try:
            vehicle.check_access_rights('read')
            vehicle.check_access_rule('read')
        except AccessError:
            raise UserError(_("You do not have access to the linked fleet vehicle."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fleet Vehicle'),
            'res_model': 'fleet.vehicle',
            'view_mode': 'form',
            'res_id': vehicle.id,
            'target': 'current',
        }


class BtAssetCategory(models.Model):
    _name = "bt.asset.category"
    _description = "Asset Category"

    name = fields.Char(string='Name', required=True)
    categ_no = fields.Char(string='Category No')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    auto_asset_code = fields.Boolean(
        string='Auto Asset Code',
        help='Automatically generate asset codes for assets in this category when none is provided.',
    )
    code_prefix = fields.Char(string='Asset Code Prefix')
    code_padding = fields.Integer(string='Asset Code Padding', default=4)
    code_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Asset Code Sequence',
        readonly=True,
        copy=False,
    )

    @api.model
    def create(self, vals):
        category = super().create(vals)
        category._ensure_code_sequence()
        return category

    def write(self, vals):
        res = super().write(vals)
        if {'auto_asset_code', 'code_prefix', 'code_padding', 'name', 'company_id'} & set(vals.keys()):
            self._ensure_code_sequence()
        return res

    def _get_code_prefix_value(self):
        self.ensure_one()
        base = (self.code_prefix or self.name or '').strip()
        if not base:
            raise ValidationError(_('Category needs a code prefix or name to build asset codes.'))
        cleaned = []
        for ch in base:
            if ch.isalnum():
                cleaned.append(ch.upper())
            elif ch.isspace() or ch in ('-', '_', '/'):
                cleaned.append('_')
        prefix_value = ''.join(cleaned).strip('_')
        if not prefix_value:
            raise ValidationError(_('Category needs a code prefix or name to build asset codes.'))
        return prefix_value

    def _ensure_code_sequence(self):
        sequence_model = self.env['ir.sequence']
        for category in self:
            if category.code_padding is not None and category.code_padding < 1:
                raise ValidationError(_('Padding must be a positive integer.'))
            prefix_value = category._get_code_prefix_value()
            sequence_prefix = '%s/%%(range_year)s/' % prefix_value
            sequence_vals = {
                'name': _('%s Asset Code') % category.display_name,
                'code': 'bt.asset.category.%s' % category.id,
                'prefix': sequence_prefix,
                'padding': category.code_padding or 4,
                'company_id': category.company_id.id,
                'use_date_range': True,
            }
            if not category.code_sequence_id:
                category.code_sequence_id = sequence_model.create(sequence_vals)
            else:
                category.code_sequence_id.write(sequence_vals)

    def _generate_asset_code(self):
        self.ensure_one()
        self._ensure_code_sequence()
        if not self.code_sequence_id:
            return False
        seq_date = fields.Date.context_today(self)
        return self.code_sequence_id.with_context(ir_sequence_date=seq_date).next_by_id()
    
# vim:expandtab:smartindent:tabstop=2:softtabstop=2:shiftwidth=2:  

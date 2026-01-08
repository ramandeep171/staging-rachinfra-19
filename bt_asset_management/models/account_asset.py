# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.exceptions import ValidationError


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    def _get_default_bt_category(self):
        self.ensure_one()
        category = self.env['bt.asset.category'].with_company(self.company_id).search(
            [
                ('company_id', 'in', [self.company_id.id, False]),
            ],
            order='auto_asset_code desc, id',
            limit=1,
        )
        if not category:
            raise ValidationError(_("Configure an asset category before creating assets."))
        return category

    def _prepare_bt_asset_vals(self):
        self.ensure_one()
        bt_asset_model = self.env['bt.asset']
        location = bt_asset_model.with_company(self.company_id)._get_default_location()
        category = self._get_default_bt_category()
        acquisition_date = self.acquisition_date if 'acquisition_date' in self._fields else False
        original_value = self.original_value if 'original_value' in self._fields else False
        return {
            'asset_type': 'main',
            'account_asset_id': self.id,
            'name': self.name,
            'purchase_date': acquisition_date,
            'purchase_value': original_value,
            'category_id': category.id,
            'company_id': self.company_id.id,
            'current_loc_id': location.id,
            'operational_status': 'active',
        }

    def _ensure_bt_asset(self):
        bt_asset_model = self.env['bt.asset']
        existing = bt_asset_model.search([('account_asset_id', 'in', self.ids)])
        existing_map = {asset.account_asset_id.id: asset for asset in existing}
        to_create = []
        for asset in self:
            if asset.id in existing_map:
                continue
            to_create.append(asset._prepare_bt_asset_vals())
        if to_create:
            bt_asset_model.with_context(from_account_asset=True).create(to_create)

    @api.model_create_multi
    def create(self, vals_list):
        assets = super().create(vals_list)
        assets._ensure_bt_asset()
        return assets

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals and vals.get('state') in {'open', 'running', 'active'}:
            self._ensure_bt_asset()
        return res

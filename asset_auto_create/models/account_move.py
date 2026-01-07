# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_create_asset = fields.Boolean(
        string="Create Asset",
        default=False,
        help="If enabled, assets will be created automatically after the vendor bill is posted.",
    )
    x_asset_ids = fields.Many2many(
        comodel_name="account.asset",
        relation="account_move_asset_rel",
        column1="move_id",
        column2="asset_id",
        string="Linked Assets",
        help="Assets linked to this bill for idempotency and traceability.",
        domain="[('company_id', '=', company_id)]",
        copy=False,
    )
    x_asset_count = fields.Integer(
        string="Assets",
        compute="_compute_x_asset_count",
        readonly=True,
    )

    @api.depends("x_asset_ids", "asset_ids")
    def _compute_x_asset_count(self):
        for move in self:
            move.x_asset_count = len(move.x_asset_ids | move.asset_ids)

    def _auto_create_asset(self):
        """Gate the enterprise asset creation with an opt-in on vendor bills."""
        assets = self.env["account.asset"]

        vendor_moves_enabled = self.filtered(
            lambda move: move.is_purchase_document(include_receipts=True) and move.x_create_asset
        )
        vendor_moves_disabled = self.filtered(
            lambda move: move.is_purchase_document(include_receipts=True) and not move.x_create_asset
        )
        other_moves = self - vendor_moves_enabled - vendor_moves_disabled

        if other_moves:
            assets |= super(AccountMove, other_moves)._auto_create_asset()

        if vendor_moves_enabled:
            created_assets = super(AccountMove, vendor_moves_enabled)._auto_create_asset()
            if created_assets:
                assets |= created_assets
                move_ids_by_asset = {
                    asset.id: set(asset.original_move_line_ids.mapped("move_id").ids)
                    for asset in created_assets
                }
                for move in vendor_moves_enabled:
                    linked_assets = created_assets.filtered(
                        lambda asset: move.id in move_ids_by_asset[asset.id]
                    )
                    if linked_assets:
                        existing_links = move.x_asset_ids | move.asset_ids
                        move.x_asset_ids = [(6, 0, (existing_links | linked_assets).ids)]

        return assets

# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
 

    diesel_log_enabled = fields.Boolean(
        string="Enable Diesel Log",
        config_parameter='diesel_log.enabled'
    )

    diesel_product_id = fields.Many2one(
        'product.product',
        string='Diesel Product',
        config_parameter='diesel_log.diesel_product_id',
        domain="[('type', '=', 'product'), ('company_id', 'in', [company_id, False])]",
        help='Product used for diesel in diesel logs. If not set, a default product will be created.'
    )
    
    fuel_operation_type_id = fields.Many2one(
        'stock.picking.type',
        string='Fuel Issue Operation Type',
        config_parameter='diesel_log.fuel_operation_type_id',
        domain="[('code', '=', 'outgoing'), ('company_id', 'in', [company_id, False])]",
        help='Operation type used for fuel issue stock pickings. If not set, a default operation type will be created.'
    )
    shortage_activity_type_id = fields.Many2one(
        'mail.activity.type',
        string='Fuel Shortage Activity Type',
        config_parameter='diesel_log.shortage_activity_type_id',
        domain="['|', ('res_model', '=', False), ('res_model', '=', 'diesel.log')]",
        help='Activity type used when a finalized diesel log detects a fuel shortage.'
    )
    shortage_activity_user_id = fields.Many2one(
        'res.users',
        string='Fuel Shortage Responsible',
        config_parameter='diesel_log.shortage_activity_user_id',
        help='Default user assigned to shortage follow-up activities (optional).'
    )

    @api.model
    def _get_param_record(self, param_name, model_name):
        """Return a record for a company-aware config parameter."""
        company_id = self.env.company.id
        ICP = self.env['ir.config_parameter'].sudo()
        value = ICP.get_param(f'{param_name}.{company_id}', default=False)
        if not value:
            value = ICP.get_param(param_name, default=False)
        if not value:
            return self.env[model_name]
        try:
            record = self.env[model_name].browse(int(value))
        except (TypeError, ValueError):
            return self.env[model_name]
        return record if record.exists() else self.env[model_name]
    
    @api.model
    def _get_diesel_product_id(self):
        """Get the configured diesel product ID for current company"""
        company_id = self.env.company.id
        param_name = 'diesel_log.diesel_product_id'
        
        # Try to get company-specific parameter first
        product_id = self.env['ir.config_parameter'].sudo().get_param(
            f'{param_name}.{company_id}', default=False
        )
        
        # Fall back to global parameter
        if not product_id:
            product_id = self.env['ir.config_parameter'].sudo().get_param(param_name, default=False)
        
        if product_id:
            try:
                product_id = int(product_id)
                product = self.env['product.product'].browse(product_id)
                if product.exists() and (not product.company_id or product.company_id.id == company_id):
                    return product_id
            except (ValueError, TypeError):
                pass
        
        return False

    @api.model
    def _get_fuel_operation_type_id(self):
        """Get the configured fuel operation type ID for current company"""
        company_id = self.env.company.id
        param_name = 'diesel_log.fuel_operation_type_id'
        
        # Try to get company-specific parameter first
        operation_type_id = self.env['ir.config_parameter'].sudo().get_param(
            f'{param_name}.{company_id}', default=False
        )
        
        # Fall back to global parameter
        if not operation_type_id:
            operation_type_id = self.env['ir.config_parameter'].sudo().get_param(param_name, default=False)
        
        if operation_type_id:
            try:
                operation_type_id = int(operation_type_id)
                operation_type = self.env['stock.picking.type'].browse(operation_type_id)
                if operation_type.exists() and (not operation_type.company_id or operation_type.company_id.id == company_id):
                    return operation_type
            except (ValueError, TypeError):
                pass
        
        return False

    @api.model
    def _get_shortage_activity_type(self):
        return self._get_param_record('diesel_log.shortage_activity_type_id', 'mail.activity.type')

    @api.model
    def _get_shortage_activity_user(self):
        return self._get_param_record('diesel_log.shortage_activity_user_id', 'res.users')
    
    @api.model
    def get_values(self):
        """Override to get company-specific configuration values"""
        res = super(ResConfigSettings, self).get_values()
        company = self.env.company
        
        # Get diesel product ID
        diesel_product_id = self.env['ir.config_parameter'].sudo().get_param(
            f'diesel_log.diesel_product_id.{company.id}', 
            default=self.env['ir.config_parameter'].sudo().get_param('diesel_log.diesel_product_id', False)
        )
        if diesel_product_id:
            try:
                res['diesel_product_id'] = int(diesel_product_id)
            except (ValueError, TypeError):
                res['diesel_product_id'] = False
        
        # Get fuel operation type ID
        fuel_operation_type_id = self.env['ir.config_parameter'].sudo().get_param(
            f'diesel_log.fuel_operation_type_id.{company.id}',
            default=self.env['ir.config_parameter'].sudo().get_param('diesel_log.fuel_operation_type_id', False)
        )
        if fuel_operation_type_id:
            try:
                res['fuel_operation_type_id'] = int(fuel_operation_type_id)
            except (ValueError, TypeError):
                res['fuel_operation_type_id'] = False

        shortage_activity_type_id = self.env['ir.config_parameter'].sudo().get_param(
            f'diesel_log.shortage_activity_type_id.{company.id}',
            default=self.env['ir.config_parameter'].sudo().get_param('diesel_log.shortage_activity_type_id', False)
        )
        if shortage_activity_type_id:
            try:
                res['shortage_activity_type_id'] = int(shortage_activity_type_id)
            except (ValueError, TypeError):
                res['shortage_activity_type_id'] = False

        shortage_activity_user_id = self.env['ir.config_parameter'].sudo().get_param(
            f'diesel_log.shortage_activity_user_id.{company.id}',
            default=self.env['ir.config_parameter'].sudo().get_param('diesel_log.shortage_activity_user_id', False)
        )
        if shortage_activity_user_id:
            try:
                res['shortage_activity_user_id'] = int(shortage_activity_user_id)
            except (ValueError, TypeError):
                res['shortage_activity_user_id'] = False

        return res

    def set_values(self):
        """Override to set company-specific configuration values"""
        super(ResConfigSettings, self).set_values()
        company = self.env.company
        
        # Set diesel product ID (company-specific if multi-company)
        if hasattr(self, 'diesel_product_id'):
            param_name = 'diesel_log.diesel_product_id'
            if self.env['res.company'].search_count([]) > 1:
                param_name += f'.{company.id}'
            
            self.env['ir.config_parameter'].sudo().set_param(
                param_name, 
                self.diesel_product_id.id if self.diesel_product_id else False
            )
        
        # Set fuel operation type ID (company-specific if multi-company)
        if hasattr(self, 'fuel_operation_type_id'):
            param_name = 'diesel_log.fuel_operation_type_id'
            if self.env['res.company'].search_count([]) > 1:
                param_name += f'.{company.id}'
            
            self.env['ir.config_parameter'].sudo().set_param(
                param_name, 
                self.fuel_operation_type_id.id if self.fuel_operation_type_id else False
            )

        if hasattr(self, 'shortage_activity_type_id'):
            param_name = 'diesel_log.shortage_activity_type_id'
            if self.env['res.company'].search_count([]) > 1:
                param_name += f'.{company.id}'
            self.env['ir.config_parameter'].sudo().set_param(
                param_name,
                self.shortage_activity_type_id.id if self.shortage_activity_type_id else False
            )

        if hasattr(self, 'shortage_activity_user_id'):
            param_name = 'diesel_log.shortage_activity_user_id'
            if self.env['res.company'].search_count([]) > 1:
                param_name += f'.{company.id}'
            self.env['ir.config_parameter'].sudo().set_param(
                param_name,
                self.shortage_activity_user_id.id if self.shortage_activity_user_id else False
            )

from odoo import models, fields, api, _

class RmcQualityCheck(models.Model):
    _name = 'rmc.quality.check'
    _description = 'RMC Quality Check'
    _order = 'check_date desc'

    name = fields.Char(string='Quality Check Number', required=True, copy=False, readonly=True, default='New')
    check_date = fields.Datetime(string='Check Date', required=True, default=fields.Datetime.now)
    
    # References
    batch_id = fields.Many2one('rmc.batch', string='Batch')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    plant_check_id = fields.Many2one('rmc.plant_check', string='Plant Check')
    
    # Check Details
    check_type = fields.Selection([
        ('production', 'Production Check'),
        ('delivery', 'Delivery Check'),
        ('site', 'Site Check'),
    ], string='Check Type', required=True)
    
    check_location = fields.Char(string='Check Location')
    checker_name = fields.Char(string='Checker Name')
    
    # Quality Parameters
    slump_flow_actual = fields.Float(string='Slump/Flow Actual (mm)')
    slump_flow_target = fields.Float(string='Slump/Flow Target (mm)')
    temperature = fields.Float(string='Temperature (°C)')
    
    # Visual Inspection
    visual_inspection = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
    ], string='Visual Inspection')
    
    # Sample Collection
    sample_collected = fields.Boolean(string='Sample Collected')
    sample_id = fields.Char(string='Sample ID')
    
    # Test Results
    compression_strength_7day = fields.Float(string='7-Day Compression Strength (MPa)')
    compression_strength_28day = fields.Float(string='28-Day Compression Strength (MPa)')
    
    # Overall Result
    overall_result = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('pending', 'Pending'),
    ], string='Overall Result', default='pending')
    
    # Documentation
    quality_certificate = fields.Binary(string='Quality Certificate')
    test_photos = fields.Binary(string='Test Photos')
    
    notes = fields.Text(string='Notes')
    corrective_actions = fields.Text(string='Corrective Actions')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.quality.check') or 'New'
        return super(RmcQualityCheck, self).create(vals_list)
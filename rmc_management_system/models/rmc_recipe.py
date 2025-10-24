from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcRecipe(models.Model):
    _name = 'rmc.recipe'
    _description = 'RMC Recipe Management'
    _order = 'concrete_grade, name'

    name = fields.Char(string='Recipe Name', required=True)
    concrete_grade = fields.Selection([
        ('m7.5', 'M7.5'),
        ('m10', 'M10'),
        ('m15', 'M15'),
        ('m20', 'M20'),
        ('m25', 'M25'),
        ('m30', 'M30'),
        ('m35', 'M35'),
        ('m40', 'M40'),
    ], string='Concrete Grade', required=True)
    
    cement_type = fields.Selection([
        ('opc', 'OPC'),
        ('ppc', 'PPC'),
        ('psc', 'PSC'),
    ], string='Cement Type', default='opc')
    
    min_cement_content = fields.Float(string='Min Cement Content (Kg/Cum)', required=True)
    max_aggregate_size = fields.Float(string='Max Aggregate Size (mm)', required=True)
    max_water_ratio = fields.Float(string='Max Water Ratio', required=True)
    
    slump_flow_min = fields.Float(string='Slump/Flow Min (mm)')
    slump_flow_max = fields.Float(string='Slump/Flow Max (mm)')
    
    # Recipe Lines
    recipe_line_ids = fields.One2many('rmc.recipe.line', 'recipe_id', string='Recipe Lines')
    
    # Standards Reference
    chemical_admix_standard = fields.Char(string='Chemical Admix Standard', default='IS 9103')
    mineral_admix_standard = fields.Char(string='Mineral Admix Standard', default='IS 456')
    slump_standard = fields.Char(string='Slump Standard', default='IS 4926')
    
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    @api.constrains('min_cement_content', 'max_water_ratio')
    def _check_recipe_values(self):
        for record in self:
            if record.min_cement_content <= 0:
                raise ValidationError(_('Minimum cement content must be greater than zero.'))
            if record.max_water_ratio <= 0 or record.max_water_ratio > 1:
                raise ValidationError(_('Water ratio must be between 0 and 1.'))

class RmcRecipeLine(models.Model):
    _name = 'rmc.recipe.line'
    _description = 'RMC Recipe Line'

    recipe_id = fields.Many2one('rmc.recipe', string='Recipe', required=True, ondelete='cascade')
    material_name = fields.Char(string='Material Name', required=True)
    material_code = fields.Char(string='Material Code')
    design_qty = fields.Float(string='Design Qty (Kg)', required=True)
    tolerance_percentage = fields.Float(string='Tolerance %', default=2.0)
    
    @api.constrains('design_qty', 'tolerance_percentage')
    def _check_line_values(self):
        for record in self:
            if record.design_qty <= 0:
                raise ValidationError(_('Design quantity must be greater than zero.'))
            if record.tolerance_percentage < 0:
                raise ValidationError(_('Tolerance percentage cannot be negative.'))
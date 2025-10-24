from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcBatch(models.Model):
    _name = 'rmc.batch'
    _description = 'RMC Batch Production'
    _order = 'batch_date desc, batch_number desc'

    name = fields.Char(string='Batch Number', required=True, copy=False, readonly=True, default='New')
    batch_number = fields.Char(string='Batch Number', required=True)
    batch_date = fields.Datetime(string='Batch Date', required=True, default=fields.Datetime.now)
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket')
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor')
    plant_check_id = fields.Many2one('rmc.plant_check', string='Plant Check')
    docket_id = fields.Many2one('rmc.docket', string='Docket')
    
    recipe_id = fields.Many2one('rmc.recipe', string='Recipe', required=True)
    concrete_grade = fields.Selection(related='recipe_id.concrete_grade', string='Concrete Grade', store=True)
    
    quantity_ordered = fields.Float(string='Quantity Ordered (M3)', required=True)
    quantity_produced = fields.Float(string='Quantity Produced (M3)')
    cumulative_quantity = fields.Float(string='Cumulative Quantity (M3)')
    
    # Production Details
    pour_structure = fields.Selection([
        ('rcc', 'RCC'),
        ('pcc', 'PCC'),
        ('foundation', 'Foundation'),
        ('slab', 'Slab'),
        ('beam', 'Beam'),
        ('column', 'Column'),
    ], string='Pour Structure', default='rcc')
    
    batching_time = fields.Datetime(string='Batching Time')
    water_ratio_actual = fields.Float(string='Actual Water Ratio')
    slump_flow_actual = fields.Float(string='Actual Slump/Flow (mm)')
    
    # Material quantities
    ten_mm = fields.Float(string='10mm Aggregate (Kg)', compute='_compute_material_totals', store=True)
    twenty_mm = fields.Float(string='20mm Aggregate (Kg)', compute='_compute_material_totals', store=True)
    facs = fields.Float(string='Fine Aggregate (Kg)', compute='_compute_material_totals', store=True)
    water_batch = fields.Float(string='Water (L)', compute='_compute_material_totals', store=True)
    flyash = fields.Float(string='Fly Ash (Kg)', compute='_compute_material_totals', store=True)
    adm_plast = fields.Float(string='Admixture Plasticizer (Kg)', compute='_compute_material_totals', store=True)
    WATERR = fields.Float(string='Water Ratio', compute='_compute_material_totals', store=True)
    
    # Batch Lines
    batch_line_ids = fields.One2many('rmc.batch.line', 'batch_id', string='Batch Lines')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_production', 'In Production'),
        ('ready', 'Ready'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')
    
    notes = fields.Text(string='Notes')
    active = fields.Boolean(string='Active', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.batch') or 'New'
        return super(RmcBatch, self).create(vals_list)

    @api.onchange('recipe_id')
    def _onchange_recipe_id(self):
        if self.recipe_id:
            lines = []
            for recipe_line in self.recipe_id.recipe_line_ids:
                lines.append((0, 0, {
                    'material_name': recipe_line.material_name,
                    'material_code': recipe_line.material_code,
                    'design_qty': recipe_line.design_qty,
                    'tolerance_percentage': recipe_line.tolerance_percentage,
                }))
            self.batch_line_ids = lines

    @api.depends('batch_line_ids.actual_qty', 'batch_line_ids.material_name')
    def _compute_material_totals(self):
        for record in self:
            record.ten_mm = sum(line.actual_qty for line in record.batch_line_ids 
                               if '10mm' in (line.material_name or '').lower())
            record.twenty_mm = sum(line.actual_qty for line in record.batch_line_ids 
                                  if '20mm' in (line.material_name or '').lower())
            record.facs = sum(line.actual_qty for line in record.batch_line_ids 
                             if any(term in (line.material_name or '').lower() 
                                   for term in ['fine', 'sand', 'facs']))
            record.water_batch = sum(line.actual_qty for line in record.batch_line_ids 
                                    if 'water' in (line.material_name or '').lower())
            record.flyash = sum(line.actual_qty for line in record.batch_line_ids 
                               if 'fly' in (line.material_name or '').lower())
            record.adm_plast = sum(line.actual_qty for line in record.batch_line_ids 
                                  if any(term in (line.material_name or '').lower() 
                                        for term in ['admixture', 'plasticizer', 'adm']))
            record.WATERR = record.water_batch  # Water ratio is same as water quantity for now

class RmcBatchLine(models.Model):
    _name = 'rmc.batch.line'
    _description = 'RMC Batch Line'

    batch_id = fields.Many2one('rmc.batch', string='Batch', required=True, ondelete='cascade')
    material_name = fields.Char(string='Material Name', required=True)
    material_code = fields.Char(string='Material Code')
    design_qty = fields.Float(string='Design Qty (Kg)', required=True)
    actual_qty = fields.Float(string='Actual Qty (Kg)')
    tolerance_percentage = fields.Float(string='Tolerance %', default=2.0)
    
    variance = fields.Float(string='Variance (Kg)', compute='_compute_variance', store=True)
    variance_percentage = fields.Float(string='Variance %', compute='_compute_variance', store=True)
    
    @api.depends('design_qty', 'actual_qty')
    def _compute_variance(self):
        for record in self:
            if record.design_qty > 0:
                record.variance = record.actual_qty - record.design_qty
                record.variance_percentage = (record.variance / record.design_qty) * 100
            else:
                record.variance = 0
                record.variance_percentage = 0
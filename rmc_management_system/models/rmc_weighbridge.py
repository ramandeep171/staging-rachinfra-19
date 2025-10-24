from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcWeighbridge(models.Model):
    _name = 'rmc.weighbridge'
    _description = 'RMC Weighbridge Transaction'
    _order = 'transaction_date desc'

    name = fields.Char(string='Transaction Number', required=True, copy=False, readonly=True, default='New')
    transaction_date = fields.Datetime(string='Transaction Date', required=True, default=fields.Datetime.now)
    
    # References
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    batch_id = fields.Many2one('rmc.batch', string='Batch')
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor')
    
    # Vehicle Details
    vehicle_number = fields.Char(string='Vehicle Number', required=True)
    driver_name = fields.Char(string='Driver Name')
    driver_mobile = fields.Char(string='Driver Mobile')
    transporter = fields.Char(string='Transporter')
    
    # Weighbridge Details
    plant_empty_weight = fields.Float(string='Plant Empty Weight (Kg)')
    plant_loaded_weight = fields.Float(string='Plant Loaded Weight (Kg)')
    plant_net_weight = fields.Float(string='Plant Net Weight (Kg)')
    
    customer_empty_weight = fields.Float(string='Customer Empty Weight (Kg)')
    customer_loaded_weight = fields.Float(string='Customer Loaded Weight (Kg)')
    customer_net_weight = fields.Float(string='Customer Net Weight (Kg)')
    
    # Variance Analysis
    weight_variance = fields.Float(string='Weight Variance (Kg)')
    variance_percentage = fields.Float(string='Variance %')
    tolerance_percentage = fields.Float(string='Tolerance %', default=2.0)
    
    variance_action = fields.Selection([
        ('no_action', 'No Action'),
        ('credit_note', 'Credit Note Required'),
        ('debit_note', 'Debit Note Required'),
    ], string='Variance Action')
    
    # Documentation
    kanta_parchi = fields.Char(string='Kanta Parchi Number')
    delivery_challan = fields.Char(string='Delivery Challan Number')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('plant_weighed', 'Plant Weighed'),
        ('dispatched', 'Dispatched'),
        ('customer_weighed', 'Customer Weighed'),
        ('reconciled', 'Reconciled'),
    ], string='Status', default='draft')
    
    notes = fields.Text(string='Notes')

    @api.onchange('plant_loaded_weight', 'plant_empty_weight', 'customer_loaded_weight', 'customer_empty_weight')
    def _onchange_weights(self):
        """Calculate all values when weights change"""
        for record in self:
            # Calculate net weights
            record.plant_net_weight = float(record.plant_loaded_weight or 0) - float(record.plant_empty_weight or 0)
            record.customer_net_weight = float(record.customer_loaded_weight or 0) - float(record.customer_empty_weight or 0)

            # Calculate variance
            record.weight_variance = record.customer_net_weight - record.plant_net_weight

            # Calculate variance percentage
            if abs(record.plant_net_weight) > 0.001:
                record.variance_percentage = (abs(record.weight_variance) / abs(record.plant_net_weight)) * 100
            else:
                record.variance_percentage = 0.0

            # Determine variance action
            if abs(record.plant_net_weight) > 0.001:
                variance_percentage = (abs(record.weight_variance) / abs(record.plant_net_weight)) * 100

                if variance_percentage > record.tolerance_percentage:
                    if record.weight_variance < 0:  # Customer received less
                        record.variance_action = 'credit_note'
                    else:  # Customer received more
                        record.variance_action = 'debit_note'
                else:
                    record.variance_action = 'no_action'
            else:
                record.variance_action = 'no_action'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.weighbridge') or 'New'
        return super(RmcWeighbridge, self).create(vals_list)
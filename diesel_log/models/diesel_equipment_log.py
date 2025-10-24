from odoo import api, fields, models, _


class DieselEquipmentLog(models.Model):
    _name = 'diesel.equipment.log'
    _description = 'Diesel Equipment Log'
    _order = 'date desc'

    name = fields.Char(string='Reference', required=True, copy=False, default=lambda self: _('New'))
    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now)
    diesel_log_id = fields.Many2one('diesel.log', string='Diesel Log', ondelete='cascade', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=True)
    hours_worked = fields.Float(string='Hours Worked')
    fuel_used = fields.Float(string='Fuel Used (L)')
    output_qty = fields.Float(string='Output / Production')
    operator_id = fields.Many2one('res.partner', string='Operator')
    note = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', string='Status')

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('diesel.equipment.log') or _('New')
        return super().create(vals)

    def action_start(self):
        for rec in self:
            if rec.state == 'draft':
                rec.state = 'in_progress'

    def action_done(self):
        for rec in self:
            if rec.state in ('draft', 'in_progress'):
                rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            if rec.state != 'done':
                rec.state = 'cancel'

    def action_reset_draft(self):
        for rec in self:
            if rec.state in ('cancel',):
                rec.state = 'draft'
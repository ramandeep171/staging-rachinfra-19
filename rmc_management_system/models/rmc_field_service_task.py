from odoo import models, fields, api

class FieldServiceTask(models.Model):
    _name = 'rmc.field.service.task'
    _description = 'RMC Field Service Task'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket')
    site_check_weight = fields.Float(string='Site Weight Match (kg)')
    site_check_slump = fields.Float(string='Site Slump (mm)')
    loading_weight = fields.Float(string='Loading Batch Weight (kg)')
    loading_slump = fields.Float(string='Loading Slump (mm)')
    status = fields.Selection([('pending', 'Pending'), ('completed', 'Completed')], default='pending')
    active = fields.Boolean(string='Active', default=True)

    @api.model
    def _auto_update_qc(self):
        tasks = self.search([('status', '=', 'pending')])
        for task in tasks:
            if task.ticket_id.quality_check_id:
                task.status = 'completed'
                task.ticket_id.quality_check_id.write({
                    'slump': task.site_check_slump,
                    'temperature': 25.0,  # Default, adjust as needed
                })

    @api.model
    def create_for_ticket(self, ticket_id):
        """Create a field service task for the given ticket"""
        return self.create({
            'ticket_id': ticket_id,
            'status': 'pending',
            'site_check_slump': 0.0,
            'site_check_weight': 0.0,
            'loading_slump': 0.0,
            'loading_weight': 0.0,
        })
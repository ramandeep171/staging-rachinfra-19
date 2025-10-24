from odoo import models, fields, api, _
import math

class RmcSubcontractorAssignmentWizard(models.TransientModel):
    _name = 'rmc.subcontractor.assignment.wizard'
    _description = 'RMC Subcontractor Assignment Wizard'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True)
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor')
    suggested_subcontractor_id = fields.Many2one('rmc.subcontractor', string='Suggested Subcontractor', compute='_compute_suggested_subcontractor')

    @api.depends('ticket_id')
    def _compute_suggested_subcontractor(self):
        for wizard in self:
            if not wizard.ticket_id.sale_order_id.delivery_coordinates:
                wizard.suggested_subcontractor_id = False
                continue
            try:
                delivery_lat, delivery_lon = map(float, wizard.ticket_id.sale_order_id.delivery_coordinates.split(','))
            except ValueError:
                wizard.suggested_subcontractor_id = False
                continue
            subcontractors = self.env['rmc.subcontractor'].search([('active', '=', True)])
            min_distance = float('inf')
            suggested = False
            for sub in subcontractors:
                if sub.plant_coordinates:
                    try:
                        plant_lat, plant_lon = map(float, sub.plant_coordinates.split(','))
                        distance = self._haversine(delivery_lat, delivery_lon, plant_lat, plant_lon)
                        if distance < min_distance and distance <= sub.service_radius:
                            min_distance = distance
                            suggested = sub
                    except ValueError:
                        continue
            wizard.suggested_subcontractor_id = suggested

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def action_confirm(self):
        self.ensure_one()
        subcontractor = self.subcontractor_id or self.suggested_subcontractor_id
        if not subcontractor:
            return
        # Create purchase order
        po_lines = []
        for line in self.ticket_id.sale_order_id.order_line:
            po_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_uom_qty,
                'product_uom': line.product_uom.id,
                'price_unit': line.price_unit,
                'date_planned': fields.Datetime.now(),
            }))
        po = self.env['purchase.order'].create({
            'partner_id': subcontractor.partner_id.id,
            'order_line': po_lines,
        })
        # Assign to ticket
        self.ticket_id.assigned_subcontractor_id = subcontractor
        self.ticket_id.rmc_status = 'assigned'
        self.ticket_id.distance_to_site = self._haversine(
            float(self.ticket_id.sale_order_id.delivery_coordinates.split(',')[0]),
            float(self.ticket_id.sale_order_id.delivery_coordinates.split(',')[1]),
            float(subcontractor.plant_coordinates.split(',')[0]),
            float(subcontractor.plant_coordinates.split(',')[1])
        ) if subcontractor.plant_coordinates else 0
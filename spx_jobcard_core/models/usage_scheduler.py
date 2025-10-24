# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SpxChecklistTemplate(models.Model):
    _inherit = 'spx.checklist.template'

    def _current_usage_value(self):
        """Return current meter based on metric/vehicle/equipment."""
        self.ensure_one()
        if self.usage_metric == 'km' and self.vehicle_id:
            Odo = self.env['fleet.vehicle.odometer']
            rec = Odo.search([('vehicle_id','=',self.vehicle_id.id)], order='date desc,id desc', limit=1)
            return rec.value if rec else 0.0
        if self.usage_metric == 'hours' and self.equipment_id:
            # prefer standard field if present
            if 'meter_hours' in self.equipment_id._fields:
                return self.equipment_id.meter_hours or 0.0
        return 0.0

    @api.model
    def cron_usage_based_preventive(self):
        """Scan usage-based templates and spawn preventive Request + Checklist when due."""
        T = self.search([('trigger_type','=','usage'), ('active','=',True)])
        Req = self.env['maintenance.request']
        Chk = self.env['spx.checklist']

        for t in T:
            if not t.usage_interval:
                continue
            current = t._current_usage_value()
            if current and t.usage_next_due and current >= t.usage_next_due - 0.0001:
                # create Maintenance Request (Preventive)
                vals = {
                    'name': "%s due @ %.0f %s" % (t.name, t.usage_next_due, t.usage_metric or ''),
                    'equipment_id': t.equipment_id.id if t.equipment_id else False,
                    'priority': '1',
                    'maintenance_type': 'preventive',
                }
                req = Req.create(vals)
                # attach Checklist from template
                Chk.create_from_template(t, req)
                # bump next due (idempotent behaviour)
                t.usage_last_done = t.usage_next_due
                # compute_next_due will advance

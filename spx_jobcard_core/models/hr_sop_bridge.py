# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

SOP_MODEL_CANDIDATES = [
    'asset.sop.assignment',
    'asset.sop.ack',
    'sop.assignment',
    'asset.sop.protocol.ack',
]

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    spx_sop_model_name = fields.Char(string="SOP Model (Resolved)", compute='_compute_sop_flags', store=False)
    spx_has_sop_app = fields.Boolean(string="Has SOP App", compute='_compute_sop_flags', store=False)
    sop_ack_count = fields.Integer(string="SOP Acks", compute='_compute_sop_flags', store=False)

    def _resolve_sop_model_name(self):
        """Return first available SOP model name or False."""
        for name in SOP_MODEL_CANDIDATES:
            if name in self.env:
                return name
        return False

    def _compute_sop_flags(self):
        for emp in self:
            model_name = emp._resolve_sop_model_name()
            emp.spx_sop_model_name = model_name or ''
            emp.spx_has_sop_app = bool(model_name)
            count = 0
            if model_name:
                Ack = self.env[model_name].sudo()
                # generic domain: employee only (equipment/asset optional)
                dom = [('employee_id', '=', emp.id)]
                # if SOP model has 'state', count acknowledged/done first; otherwise all
                if 'state' in Ack._fields:
                    count = Ack.search_count(dom + [('state', 'in', ['ack', 'acknowledged', 'done'])])
                else:
                    count = Ack.search_count(dom)
            emp.sop_ack_count = count

    def action_view_sop_acks(self):
        """Open this employee's SOP ack/assignment records in a list view.
        If no SOP model is installed, return a close action.
        """
        self.ensure_one()
        model_name = self._resolve_sop_model_name()
        if not model_name:
            # No SOP app → show a notification to the user instead of closing silently
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No SOP app'),
                    'message': _('No SOP module installed. Install SOP app to view acknowledgements.'),
                    'sticky': False,
                    'type': 'warning',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('SOP Acks'),
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
            'target': 'current',
        }
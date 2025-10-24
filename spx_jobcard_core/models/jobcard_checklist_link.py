# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class MaintenanceJobCard(models.Model):
    _inherit = 'maintenance.jobcard'

    spx_checklist_ids = fields.One2many('spx.checklist', 'jobcard_id', string="Checklists")

    def action_done(self):
        # Before finishing, update any usage-based templates attached to this jobcard/request
        self._spx_update_usage_template_done()

        # Hard gate: if any attached checklist has required fail -> block
        for rec in self:
            chks = rec.spx_checklist_ids
            if chks and not all(c.passed for c in chks):
                raise ValidationError(_("Checklist not passed. Please resolve failed items before Done."))
        return super().action_done()

    def _spx_update_usage_template_done(self):
        for rec in self:
            # find any usage-based template checklists attached to this jobcard or related request
            chks_job = self.env['spx.checklist'].search([('jobcard_id', '=', rec.id)])
            chks_req = self.env['spx.checklist'].search([('request_id', '=', rec.request_id.id)]) if rec.request_id else self.env['spx.checklist']
            chks = chks_job | (chks_req if rec.request_id else self.env['spx.checklist'])
            # If rec.request_id is falsy, chks_req above was set to all records; avoid that
            if rec.request_id:
                chks = chks_job | chks_req
            else:
                chks = chks_job
            for chk in chks:
                t = chk.template_id
                if not t or t.trigger_type != 'usage':
                    continue
                # template should implement _current_usage_value()
                current = False
                if hasattr(t, '_current_usage_value'):
                    try:
                        current = t._current_usage_value()
                    except Exception:
                        current = False
                if current:
                    t.write({'usage_last_done': current})

    def action_open_apply_checklist_wizard_jobcard(self):
        """Open wizard to pick a template and apply it to this jobcard."""
        self.ensure_one()
        return {
            'name': _('Choose Checklist Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'spx.checklist.apply.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'jobcard_id': self.id},
        }


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    spx_checklist_ids = fields.One2many('spx.checklist', 'request_id', string="Checklists")

    # OPTIONAL: on create emergency when daily log fails (hook placeholder)
    # Your existing automation can call env['spx.checklist'].create_from_template(...)

    def action_open_apply_checklist_wizard(self):
        """Open wizard to pick a template and apply it to this request."""
        self.ensure_one()
        return {
            'name': _('Choose Checklist Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'spx.checklist.apply.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'request_id': self.id},
        }

    def action_open_apply_checklist_wizard_jobcard(self):
        """Open wizard to pick a template and apply it to this jobcard (helper on jobcard)."""
        self.ensure_one()
        return {
            'name': _('Choose Checklist Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'spx.checklist.apply.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'jobcard_id': self.id},
        }

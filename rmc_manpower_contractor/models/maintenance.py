# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcMaintenanceCheck(models.Model):
    _name = 'rmc.maintenance.check'
    _description = 'RMC Maintenance Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', required=True, ondelete='restrict', tracking=True)
    contractor_id = fields.Many2one(related='agreement_id.contractor_id', string='Contractor', store=True)
    date = fields.Date(string='Check Date', required=True, default=fields.Date.context_today, tracking=True)
    machine_id = fields.Char(string='Machine/Equipment ID')
    employee_id = fields.Many2one(
        'hr.employee',
        string='Responsible Employee',
        help='Employee/operator who performed or reported this check'
    )
    checklist_ok = fields.Float(string='Checklist Completion (%)', digits=(5, 2), required=True, default=100.0)
    defects_found = fields.Text(string='Defects Found')
    repaired = fields.Boolean(string='Repaired', default=False)
    cost = fields.Monetary(string='Repair Cost', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    state = fields.Selection([('draft', 'Draft'), ('pending_agreement', 'Pending Agreement'), ('validated', 'Validated')], default='draft', required=True, tracking=True)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.maintenance.check') or _('New')
        records = super(RmcMaintenanceCheck, self).create(vals_list)
        for record in records:
            record._check_agreement_signature()
            record._validate_agreement_employee()
            record._default_employee_from_agreement()
        return records

    def write(self, vals):
        res = super(RmcMaintenanceCheck, self).write(vals)
        if 'state' not in vals:
            self._check_agreement_signature()
        if 'employee_id' in vals:
            self._validate_agreement_employee()
        if 'employee_id' not in vals and 'agreement_id' in vals:
            self._default_employee_from_agreement()
        return res

    def _check_agreement_signature(self):
        for record in self:
            if not record.agreement_id.is_signed():
                record.state = 'pending_agreement'
                record.message_post(body=_('Maintenance check pending agreement signature.'))
                record.agreement_id.activity_schedule('mail.mail_activity_data_todo', summary=_('Sign agreement to validate maintenance'), note=_('Check %s waiting.') % record.name)

    @api.constrains('checklist_ok', 'cost')
    def _check_values(self):
        for record in self:
            if record.checklist_ok < 0 or record.checklist_ok > 100:
                raise ValidationError(_('Checklist completion must be between 0 and 100%.'))
            if record.cost < 0:
                raise ValidationError(_('Cost cannot be negative.'))
            if record.employee_id and record.agreement_id.driver_ids and record.employee_id not in record.agreement_id.driver_ids:
                raise ValidationError(
                    _('Employee %s is not assigned to agreement %s.') %
                    (record.employee_id.name, record.agreement_id.name)
                )

    def _validate_agreement_employee(self):
        for record in self.filtered(lambda r: r.employee_id):
            if record.agreement_id and record.agreement_id.driver_ids and record.employee_id not in record.agreement_id.driver_ids:
                raise ValidationError(
                    _('Employee %s is not assigned to agreement %s.') %
                    (record.employee_id.name, record.agreement_id.name)
                )

    def _default_employee_from_agreement(self):
        for record in self:
            if record.agreement_id and not record.employee_id and record.agreement_id.driver_ids:
                record.employee_id = record.agreement_id.driver_ids[:1]

    def action_validate(self):
        for record in self:
            if not record.agreement_id.is_signed():
                raise ValidationError(_('Cannot validate: Agreement not signed.'))
            record.state = 'validated'
            record.message_post(body=_('Maintenance check validated'))

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    _sql_constraints = [
        (
            'rmc_maintenance_cost_positive',
            'CHECK(cost >= 0)',
            'Cost must be non-negative.'
        ),
    ]

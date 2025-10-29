# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcAttendanceCompliance(models.Model):
    _name = 'rmc.attendance.compliance'
    _description = 'RMC Attendance Compliance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', required=True, ondelete='restrict', tracking=True)
    contractor_id = fields.Many2one(related='agreement_id.contractor_id', string='Contractor', store=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, tracking=True)
    headcount_expected = fields.Integer(string='Expected Headcount', compute='_compute_expected', store=True)
    headcount_present = fields.Integer(string='Present Headcount', required=True, default=0)
    documents_ok = fields.Boolean(string='Documents OK', default=True)
    supervisor_ok = fields.Boolean(string='Supervisor Sign-off', default=False)
    compliance_percentage = fields.Float(string='Compliance %', compute='_compute_compliance', store=True, digits=(5, 2))
    state = fields.Selection([('draft', 'Draft'), ('pending_agreement', 'Pending Agreement'), ('validated', 'Validated')], default='draft', required=True, tracking=True)
    employee_ids = fields.Many2many(
        'hr.employee',
        'rmc_attendance_employee_rel',
        'attendance_id',
        'employee_id',
        string='Present Employees',
        help='Employees who were present for this agreement on the selected date.'
    )
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.depends('agreement_id.manpower_matrix_ids')
    def _compute_expected(self):
        for record in self:
            record.headcount_expected = sum(record.agreement_id.manpower_matrix_ids.mapped('headcount'))

    @api.depends('headcount_present', 'headcount_expected', 'documents_ok', 'supervisor_ok')
    def _compute_compliance(self):
        for record in self:
            if record.headcount_expected > 0:
                attendance_pct = (record.headcount_present / record.headcount_expected) * 100
                doc_pct = 100 if record.documents_ok else 50
                super_pct = 100 if record.supervisor_ok else 70
                record.compliance_percentage = (attendance_pct * 0.6 + doc_pct * 0.2 + super_pct * 0.2)
            else:
                record.compliance_percentage = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.attendance.compliance') or _('New')
        records = super(RmcAttendanceCompliance, self).create(vals_list)
        for record in records:
            record._check_agreement_signature()
            record._sync_present_from_employees()
        return records

    def write(self, vals):
        res = super(RmcAttendanceCompliance, self).write(vals)
        if 'state' not in vals:
            self._check_agreement_signature()
        if 'employee_ids' in vals and not self.env.context.get('rmc_attendance_skip_sync'):
            self._sync_present_from_employees()
        if 'agreement_id' in vals and not self.env.context.get('rmc_attendance_skip_sync'):
            self._sync_present_from_employees()
        return res

    def _check_agreement_signature(self):
        for record in self:
            if not record.agreement_id.is_signed():
                record.state = 'pending_agreement'
                record.message_post(body=_('Attendance pending agreement signature.'))
                record.agreement_id.activity_schedule('mail.mail_activity_data_todo', summary=_('Sign agreement'), note=_('Attendance %s waiting.') % record.name)

    @api.constrains('headcount_present')
    def _check_headcount(self):
        for record in self:
            if record.headcount_present < 0:
                raise ValidationError(_('Headcount cannot be negative.'))
            if record.employee_ids and record.headcount_present != len(record.employee_ids):
                raise ValidationError(_('Headcount present must match the number of selected employees.'))

    @api.constrains('employee_ids', 'agreement_id')
    def _check_employee_assignment(self):
        for record in self:
            if record.agreement_id and record.agreement_id.driver_ids and record.employee_ids:
                extra = record.employee_ids - record.agreement_id.driver_ids
                if extra:
                    raise ValidationError(_(
                        'Employees %s are not assigned to agreement %s.'
                    ) % (', '.join(extra.mapped('name')), record.agreement_id.name))

    @api.onchange('employee_ids')
    def _onchange_employee_ids(self):
        for record in self:
            record.headcount_present = len(record.employee_ids)

    def _sync_present_from_employees(self):
        for record in self:
            if record.employee_ids:
                record.with_context(rmc_attendance_skip_sync=True).write({
                    'headcount_present': len(record.employee_ids)
                })

    def action_validate(self):
        for record in self:
            if not record.agreement_id.is_signed():
                raise ValidationError(_('Cannot validate: Agreement not signed.'))
            record.state = 'validated'
            record.message_post(body=_('Attendance validated'))

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    _sql_constraints = [
        (
            'rmc_attendance_headcount_positive',
            'CHECK(headcount_present >= 0)',
            'Present headcount must be non-negative.'
        ),
    ]

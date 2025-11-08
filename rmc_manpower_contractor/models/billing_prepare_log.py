# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class RmcBillingPrepareLog(models.Model):
    _name = 'rmc.billing.prepare.log'
    _description = 'RMC Monthly Billing Log'
    _order = 'create_date desc'

    name = fields.Char(string='Description', compute='_compute_name', store=True)
    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade'
    )
    contractor_id = fields.Many2one(
        related='agreement_id.contractor_id',
        store=True,
        string='Contractor'
    )
    wizard_id = fields.Many2one(
        'rmc.billing.prepare.wizard',
        string='Source Wizard',
        ondelete='set null'
    )
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        ondelete='set null'
    )
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    mgq_target = fields.Float(string='MGQ Target (m³)')
    mgq_achieved = fields.Float(string='MGQ Achieved (m³)')
    mgq_achievement_pct = fields.Float(string='MGQ Achievement %', digits=(5, 2))
    prime_output_qty = fields.Float(string='Prime Output (m³)')
    optimized_standby_qty = fields.Float(string='Optimized Standby (m³)')
    part_a_amount = fields.Monetary(string='Part-A Amount')
    part_b_amount = fields.Monetary(string='Part-B Amount')
    breakdown_deduction = fields.Monetary(string='Breakdown Deduction')
    bonus_penalty_pct = fields.Float(string='Bonus/Penalty %', digits=(5, 2))
    bonus_penalty_amount = fields.Monetary(string='Bonus/Penalty Amount')
    inventory_variance = fields.Monetary(string='Inventory Variance')
    subtotal = fields.Monetary(string='Subtotal')
    tds_amount = fields.Monetary(string='TDS Amount')
    total_amount = fields.Monetary(string='Net Payable')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    attach_attendance = fields.Boolean(string='Attendance Attached')
    attach_diesel = fields.Boolean(string='Diesel Attached')
    attach_maintenance = fields.Boolean(string='Maintenance Attached')
    attach_breakdown = fields.Boolean(string='Breakdown Attached')
    notes = fields.Text(string='Notes snapshot')
    state = fields.Selection([
        ('prepare', 'Prepare'),
        ('review', 'Review'),
        ('done', 'Done')
    ], string='Wizard State', default='done')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'rmc_billing_log_attachment_rel',
        'log_id',
        'attachment_id',
        string='Attachments'
    )
    attendance_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attendance Attachment',
        ondelete='set null'
    )
    diesel_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Diesel Attachment',
        ondelete='set null'
    )
    maintenance_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Maintenance Attachment',
        ondelete='set null'
    )
    breakdown_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Breakdown Attachment',
        ondelete='set null'
    )
    attendance_record_ids = fields.Many2many(
        'rmc.attendance.compliance',
        'rmc_billing_log_attendance_rel',
        'log_id',
        'attendance_id',
        string='Attendance Records'
    )
    diesel_record_ids = fields.Many2many(
        'rmc.diesel.log',
        'rmc_billing_log_diesel_rel',
        'log_id',
        'diesel_id',
        string='Diesel Records'
    )
    maintenance_record_ids = fields.Many2many(
        'rmc.maintenance.check',
        'rmc_billing_log_maintenance_rel',
        'log_id',
        'maintenance_id',
        string='Maintenance Records'
    )
    breakdown_record_ids = fields.Many2many(
        'rmc.breakdown.event',
        'rmc_billing_log_breakdown_rel',
        'log_id',
        'breakdown_id',
        string='Breakdown Records'
    )
    attendance_preview_html = fields.Html(string='Attendance Details', sanitize=False)
    diesel_preview_html = fields.Html(string='Diesel Details', sanitize=False)
    maintenance_preview_html = fields.Html(string='Maintenance Details', sanitize=False)
    breakdown_preview_html = fields.Html(string='Breakdown Details', sanitize=False)
    created_by = fields.Many2one(
        'res.users',
        string='Prepared By',
        default=lambda self: self.env.user,
        readonly=True
    )
    created_on = fields.Datetime(
        string='Prepared On',
        default=fields.Datetime.now,
        readonly=True
    )

    @api.depends('agreement_id', 'period_start', 'period_end')
    def _compute_name(self):
        for record in self:
            if record.agreement_id and record.period_start and record.period_end:
                record.name = _('%s (%s → %s)') % (
                    record.agreement_id.name,
                    record.period_start,
                    record.period_end,
                )
            elif record.agreement_id:
                record.name = record.agreement_id.name
            else:
                record.name = _('Billing Log')

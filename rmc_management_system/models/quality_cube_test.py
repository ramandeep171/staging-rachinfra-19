from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import uuid


class QualityCubeTest(models.Model):
    _name = 'quality.cube.test'
    _description = 'Concrete Cube Test'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: _('New'), copy=False, required=True)
    # Relaxed to allow Trial Mix-origin tests
    sale_order_id = fields.Many2one('sale.order', required=False, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='sale_order_id.partner_id', store=True, readonly=True)
    test_condition = fields.Selection([
        ('every_truck', 'Every Truck / Docket / Ticket'),
        ('workorder', 'Workorder Wise'),
        ('every_six', 'Every 6 Docket / Ticket')
    ], required=False, help='Trigger point that created this test (reference only)')
    cubes_per_test = fields.Integer(default=3)
    casting_date = fields.Date(required=True, default=fields.Date.context_today, help='Date when cube was casted')
    test_date = fields.Date(required=True, default=fields.Date.context_today, help='Auto-calculated: 7-day = casting+6, 28-day = casting+27')
    day_type = fields.Selection([
        ('7', '7 Days'),
        ('28', '28 Days')
    ], required=True, default='7')
    strength_result = fields.Float(digits=(6, 2), tracking=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed')
    ], default='pending', tracking=True)
    retest_of_id = fields.Many2one('quality.cube.test', string='Retest Of', index=True)
    retest_ids = fields.One2many('quality.cube.test', 'retest_of_id')

    design_strength = fields.Float(help='Target design strength (MPa) for mix', default=0.0)
    pass_fail = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail')
    ], compute='_compute_pass_fail', store=True)
    user_id = fields.Many2one('res.users', string='Assigned To')
    notes = fields.Text()
    docket_id = fields.Many2one('rmc.docket', string='Docket', help='If created from a docket trigger, linked docket for dedup and traceability')
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder', help='If created from a workorder trigger, linked workorder for traceability')
    # Trial Mix-centric metrics
    test_type = fields.Selection([('7d', '7 Days'), ('28d', '28 Days')], compute='_compute_test_type', store=True)
    required_strength = fields.Float(string='Required Strength (MPa)')
    sample_ids = fields.One2many('quality.cube.sample', 'test_id', string='Samples')
    average_strength = fields.Float(string='Average Strength (MPa)', compute='_compute_average_strength', store=True)

    # Context linkage
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    project_id = fields.Many2one('project.project', string='Project')

    # Ambient & fresh concrete properties
    ambient_temp = fields.Float(string='Ambient Temp (°C)')
    ambient_humidity = fields.Float(string='Ambient Humidity (%)')
    slump_0hr = fields.Float(string='Slump (0 hr)')
    slump_1hr = fields.Float(string='Slump (1 hr)')
    slump_2hr = fields.Float(string='Slump (2 hr)')
    slump_3hr = fields.Float(string='Slump (3 hr)')
    compaction_0hr = fields.Float(string='Compaction (0 hr)')
    compaction_1hr = fields.Float(string='Compaction (1 hr)')
    compaction_2hr = fields.Float(string='Compaction (2 hr)')
    compaction_3hr = fields.Float(string='Compaction (3 hr)')
    air_content_0hr = fields.Float(string='Air Content (0 hr)')
    air_content_1hr = fields.Float(string='Air Content (1 hr)')

    # Curing info
    curing_method = fields.Selection([
        ('water', 'Water Curing'),
        ('steam', 'Steam Curing'),
        ('air', 'Air Curing'),
        ('other', 'Other'),
    ], string='Curing Method')
    curing_notes = fields.Text(string='Curing Notes')

    # Attachments & approvals
    attachment_ids = fields.Many2many(
        'ir.attachment', 'quality_cube_test_ir_attachments_rel', 'test_id', 'attachment_id',
        string='Attachments'
    )
    approved_by_id = fields.Many2one('res.users', string='Approved By')
    approved_date = fields.Date(string='Approved Date')

    # Visibility helper: Show reference tab only if any reference exists
    has_origin_reference = fields.Boolean(string='Has Origin Reference', compute='_compute_has_origin_reference', store=False)

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Cube test reference must be unique')
    ]

    def _compute_has_origin_reference(self):
        for rec in self:
            rec.has_origin_reference = bool(rec.partner_id or rec.sale_order_id or rec.docket_id or rec.workorder_id)

    @api.depends('strength_result', 'design_strength', 'required_strength', 'average_strength')
    def _compute_pass_fail(self):
        for rec in self:
            # Determine the measured result and the target threshold
            result = rec.strength_result or rec.average_strength or 0.0
            threshold = rec.design_strength or rec.required_strength or 0.0
            if result and threshold:
                rec.pass_fail = 'pass' if result >= threshold else 'fail'
            else:
                rec.pass_fail = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.get('name')
            if not name or name in (_('New'), 'New'):
                # Try sequence first
                name = self.env['ir.sequence'].sudo().next_by_code('quality.cube.test') or self._generate_unique_name()
            # If name already exists (e.g., after a sequence reset), fallback to UUID-based unique name
            if name and self.search_count([('name', '=', name)]):
                name = self._generate_unique_name()
            vals['name'] = name
            # Normalize dates: compute test_date from casting_date and day_type if not provided or to enforce rule
            casting = vals.get('casting_date') or fields.Date.context_today(self)
            day_type = vals.get('day_type') or '7'
            # Always compute test_date
            vals['casting_date'] = casting
            vals['test_date'] = fields.Date.to_date(casting) + (timedelta(days=6) if day_type == '7' else timedelta(days=27))
        return super().create(vals_list)

    def write(self, vals):
        # Prevent manual override of test_date: recalc from casting_date/day_type
        res = super().write(vals)
        to_update = self
        # If client tried to set test_date manually, we still enforce rule after write
        for rec in to_update:
            casting = vals.get('casting_date') or rec.casting_date or fields.Date.context_today(self)
            day_type = vals.get('day_type') or rec.day_type or '7'
            calc = fields.Date.to_date(casting) + (timedelta(days=6) if day_type == '7' else timedelta(days=27))
            if rec.test_date != calc:
                super(QualityCubeTest, rec).write({'test_date': calc})
        return res

    def _generate_unique_name(self):
        return f"CBT/{fields.Date.today().strftime('%Y%m%d')}/{uuid.uuid4().hex[:6].upper()}"

    @api.depends('day_type')
    def _compute_test_type(self):
        for rec in self:
            rec.test_type = '7d' if rec.day_type == '7' else ('28d' if rec.day_type == '28' else False)

    @api.depends('sample_ids.compressive_strength')
    def _compute_average_strength(self):
        for rec in self:
            vals = [s.compressive_strength for s in rec.sample_ids if s.compressive_strength]
            rec.average_strength = sum(vals) / len(vals) if vals else 0.0

    # UX helper: prefill strength_result from average_strength while editing (do not override manual)
    @api.onchange('sample_ids')
    def _onchange_samples_prefill_strength_result(self):
        for rec in self:
            # Only prefill if user hasn't provided a manual strength_result
            if not rec.strength_result and rec.average_strength:
                rec.strength_result = rec.average_strength

    @api.onchange('average_strength')
    def _onchange_average_strength_prefill_strength_result(self):
        for rec in self:
            if not rec.strength_result and rec.average_strength:
                rec.strength_result = rec.average_strength

    def action_mark_completed(self):
        for rec in self:
            # If result not explicitly set, use average_strength as the final result
            if not rec.strength_result and rec.average_strength:
                rec.strength_result = rec.average_strength
            rec.status = 'completed'
            # For any trigger: if 7-day fails, schedule a 28-day retest
            if rec.pass_fail == 'fail' and rec.day_type == '7':
                rec._create_retest_28day()

    def _create_retest_28day(self):
        self.ensure_one()
        existing = self.retest_ids.filtered(lambda r: r.day_type == '28')
        if existing:
            return existing
        # If there's already a planned 28-day test for this sale order (not a retest), don't duplicate
        planned = self.search([
            ('sale_order_id', '=', self.sale_order_id.id),
            ('day_type', '=', '28'),
            ('retest_of_id', '=', False),
            ('status', '=', 'pending'),
        ], limit=1)
        if planned:
            return planned
        # For retest, set casting_date as original's casting_date and test_date auto-calculated
        return self.create({
            'sale_order_id': self.sale_order_id.id,
            'test_condition': self.test_condition,
            'cubes_per_test': self.cubes_per_test,
            'casting_date': self.casting_date,
            'day_type': '28',
            'retest_of_id': self.id,
            'design_strength': self.design_strength,
            'docket_id': self.docket_id.id,
            'workorder_id': self.workorder_id.id,
        })

    @api.model
    def cron_generate_automatic_tests(self):
        return True

    # UI actions and helpers
    def create_default_samples(self):
        """Create three default samples C-1..C-3 when none exist."""
        Sample = self.env['quality.cube.sample']
        for rec in self:
            if rec.sample_ids:
                continue
            for nm in ('C-1', 'C-2', 'C-3'):
                Sample.create({
                    'test_id': rec.id,
                    'name': nm,
                    'casting_date': rec.casting_date,
                })
        return True

    # Backward-compat alias used by crm_trial_mix
    def _create_default_samples(self):
        return self.create_default_samples()

    def action_daily_auto_run(self):
        """Placeholder hook to run any auto checks; returns True."""
        return True

    def _attach_placeholder(self, name, data, mimetype):
        Attachment = self.env['ir.attachment']
        for rec in self:
            Attachment.create({
                'name': name,
                'res_model': rec._name,
                'res_id': rec.id,
                'datas': data,
                'mimetype': mimetype,
            })

    def action_generate_pdf(self):
        """Generate and attach placeholder PDF report so the button works."""
        import base64
        content = base64.b64encode(b'%PDF-1.4\n% Cube Test Report (placeholder)\n')
        for rec in self:
            rec._attach_placeholder(f'{rec.name}_report.pdf', content, 'application/pdf')
        return True

    def action_generate_xlsx(self):
        """Generate and attach placeholder XLSX so the button works."""
        import base64
        content = base64.b64encode(b'PK\x03\x04 Cube Test Worksheet (placeholder)')
        for rec in self:
            rec._attach_placeholder(f'{rec.name}_worksheet.xlsx', content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        return True

    @api.constrains('sale_order_id')
    def _check_origin_presence(self):
        for rec in self:
            if not rec.sale_order_id and not getattr(rec, 'trial_mix_id', False):
                raise ValidationError(_('Either Sale Order or Trial Mix must be set for a cube test.'))

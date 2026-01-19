from odoo import api, fields, models
from odoo.exceptions import UserError


class JrEmployeeJr(models.Model):
    _name = 'jr.employee.jr'
    _description = 'Employee Job Responsibility'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _check_company_auto = True

    name = fields.Char(string='JR Reference', compute='_compute_name', store=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, tracking=True
    )
    job_id = fields.Many2one('hr.job', string='Job Position', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('issued', 'Issued'),
            ('acknowledged', 'Acknowledged'),
        ],
        default='draft',
        tracking=True,
    )
    issue_date = fields.Date(tracking=True)
    summary = fields.Text()
    line_ids = fields.One2many('jr.employee.jr.line', 'jr_id', string='Responsibilities')
    notes = fields.Text()
    template_id = fields.Many2one(
        'jr.job.template',
        string='Template',
        domain="[('job_id', '=', job_id), ('company_id', '=', company_id), ('active', '=', True)]",
        help="Select a template to auto-fill the responsibilities."
    )

    @api.depends('employee_id', 'job_id')
    def _compute_name(self):
        for record in self:
            employee = record.employee_id.name or 'Unnamed Employee'
            job = record.job_id.name or 'Undefined Job'
            record.name = f"JR - {employee} ({job})"

    def action_issue_to_employee(self):
        self._ensure_valid_state_transition(target_state='issued')
        template = self.env.ref(
            'hr_job_responsibility.mail_template_jr_issue',
            raise_if_not_found=False,
        )
        today = fields.Date.context_today(self)
        for jr in self:
            update_vals = {'state': 'issued', 'issue_date': today}
            jr.write(update_vals)
            jr.message_post(body='JR issued to employee for review.')
            jr._send_issue_email(template)
        return True

    def action_acknowledge(self):
        self._ensure_valid_state_transition(target_state='acknowledged')
        for jr in self:
            jr.write({'state': 'acknowledged'})
            jr.message_post(body='JR acknowledged.')
        return True

    def action_print_jr(self):
        self.ensure_one()
        return self.env.ref('hr_job_responsibility.action_report_employee_jr').report_action(self)

    def _send_issue_email(self, template):
        sandbox_enabled, redirect_email, allowed_domains = self._get_email_sandbox_rules()
        for jr in self:
            work_email = jr.employee_id.work_email
            if not template:
                jr.message_post(body='JR issue email template missing; email not sent.')
                continue
            if not work_email:
                jr.message_post(body='No work email on employee; JR issue email not sent.')
                continue

            recipient, reason = self._filter_recipient_for_sandbox(
                work_email, sandbox_enabled, redirect_email, allowed_domains
            )
            if not recipient:
                jr.message_post(body=f'JR issue email suppressed: {reason}')
                continue

            try:
                template.send_mail(
                    jr.id,
                    force_send=True,
                    email_values={'email_to': recipient},
                )
                if sandbox_enabled and recipient != work_email:
                    jr.message_post(
                        body=(
                            'JR issue email rerouted in sandbox mode '
                            f'(original: {work_email}, redirected to: {recipient}).'
                        )
                    )
            except Exception as exc:  # pragma: no cover - depends on mail subsystem
                jr.message_post(
                    body=f'JR issue email failed to send: {exc}'
                )

    def _filter_recipient_for_sandbox(
        self, email, sandbox_enabled, redirect_email, allowed_domains
    ):
        if not sandbox_enabled:
            return email, None
        domain = email.split('@')[-1].lower() if '@' in email else ''
        if domain in allowed_domains:
            return email, None
        if redirect_email:
            return redirect_email, 'recipient domain not allowed; redirected.'
        return False, 'sandbox mode blocks non-allowlisted recipient.'

    def _get_email_sandbox_rules(self):
        params = self.env['ir.config_parameter'].sudo()
        sandbox_enabled = params.get_param('jr.email_sandbox.enabled', 'False').lower() == 'true'
        allowed_domains_raw = params.get_param('jr.email_sandbox.allowed_domains', '')
        redirect_email = params.get_param('jr.email_sandbox.redirect_to', '')
        allowed_domains = [
            domain.strip().lower()
            for domain in allowed_domains_raw.split(',')
            if domain.strip()
        ]
        return sandbox_enabled, redirect_email, allowed_domains

    @api.model
    def create_from_template(self, employee, template):
        line_values = [
            (
                0,
                0,
                {
                    'sequence': line.sequence,
                    'description': line.description,
                    'kpi_hint': line.kpi_hint,
                    'emphasize': line.emphasize,
                },
            )
            for line in template.line_ids
        ]
        jr_vals = {
            'employee_id': employee.id,
            'job_id': template.job_id.id,
            'company_id': employee.company_id.id or template.company_id.id,
            'summary': template.summary,
            'line_ids': line_values,
        }
        jr = self.create(jr_vals)
        jr.message_post(
            body=f"JR auto-generated from Job Position: {template.job_id.display_name}."
        )
        return jr

    def _ensure_valid_state_transition(self, target_state):
        invalid_source = {
            'issued': ('issued', 'acknowledged'),
            'acknowledged': ('draft',),
        }
        for jr in self:
            blocked_states = invalid_source.get(target_state, tuple())
            if jr.state in blocked_states:
                raise UserError(
                    'This Job Responsibility cannot be transitioned from the current state.'
                )

    def _is_branding_enabled(self):
        """Return whether branding should be rendered on emails and reports."""
        value = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('sp_nextgen.branding_enabled', 'True')
            or 'True'
        )
        normalized = value.strip().lower()
        return normalized not in {'false', '0', 'no', 'off'}

    # ----------------------------
    # Template helpers
    # ----------------------------
    @api.onchange('template_id')
    def _onchange_template_id(self):
        """When a template is selected, preload summary and lines on the draft record."""
        if not self.template_id:
            return
        self.summary = self.template_id.summary
        self.line_ids = self._prepare_lines_from_template(self.template_id)

    @api.onchange('job_id', 'company_id')
    def _onchange_job_company_set_template(self):
        if self.job_id and self.company_id:
            template = self.env['jr.job.template'].search(
                [
                    ('job_id', '=', self.job_id.id),
                    ('company_id', '=', self.company_id.id),
                    ('active', '=', True),
                ],
                limit=1,
            )
            self.template_id = template

    def action_apply_template(self):
        for jr in self:
            if not jr.template_id:
                raise UserError('Please select a template to apply.')
            jr.write({
                'summary': jr.template_id.summary,
                'line_ids': jr._prepare_lines_from_template(jr.template_id),
            })
        return True

    def _prepare_lines_from_template(self, template):
        """Return commands to replace lines with the template content."""
        commands = [
            (0, 0, {
                'sequence': line.sequence,
                'description': line.description,
                'kpi_hint': line.kpi_hint,
                'emphasize': line.emphasize,
            })
            for line in template.line_ids
        ]
        return [(5, 0, 0)] + commands

    # ----------------------------
    # Portal helpers
    # ----------------------------
    @api.model
    def _portal_domain(self):
        """Domain limiting records to the current portal user and visible states."""
        return [
            ('employee_id.user_id', '=', self.env.user.id),
            ('state', 'in', ('issued', 'acknowledged')),
        ]

    @api.model
    def _portal_count(self):
        return self.sudo().search_count(self._portal_domain())

    def get_portal_url(self):
        self.ensure_one()
        return f"/my/job-responsibilities/{self.id}"


class JrEmployeeJrLine(models.Model):
    _name = 'jr.employee.jr.line'
    _description = 'Employee Job Responsibility Line'
    _order = 'sequence, id'

    jr_id = fields.Many2one(
        'jr.employee.jr', string='Job Responsibility', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=0)
    sequence_display = fields.Integer(
        string='Sr No.',
        compute='_compute_sequence_display',
        store=False,
    )
    description = fields.Text(required=True)
    kpi_hint = fields.Char(string='KPI Hint')
    emphasize = fields.Boolean(string='Emphasize/Bold')

    @api.depends('sequence', 'jr_id', 'emphasize')
    def _compute_sequence_display(self):
        jrs = self.mapped('jr_id')
        for jr in jrs:
            ordered = jr.line_ids.sorted(key=lambda l: (l.sequence, l.id))
            counter = 0
            for line in ordered:
                if line.emphasize:
                    line.sequence_display = 0
                    counter = 0
                else:
                    counter += 1
                    line.sequence_display = counter

        # For lines not linked to a JR yet (edge cases), keep simple numbering.
        for line in self.filtered(lambda l: not l.jr_id):
            if line.emphasize:
                line.sequence_display = 0
            else:
                line.sequence_display = (line.sequence or 0) if line.sequence else 0

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-increment sequence per JR when not provided.
        vals_list = [dict(vals) for vals in vals_list]
        missing = [vals for vals in vals_list if not vals.get('sequence')]
        jr_ids = {vals.get('jr_id') for vals in missing if vals.get('jr_id')}
        max_map = {}
        if jr_ids:
            groups = self.read_group(
                [('jr_id', 'in', list(jr_ids))],
                ['sequence:max'],
                ['jr_id'],
            )
            max_map = {g['jr_id'][0]: g['sequence_max'] for g in groups}

        for vals in vals_list:
            if vals.get('sequence'):
                continue
            jr_id = vals.get('jr_id')
            next_seq = (max_map.get(jr_id, 0) if jr_id else 0) + 1
            vals['sequence'] = next_seq
            if jr_id:
                max_map[jr_id] = next_seq

        return super().create(vals_list)

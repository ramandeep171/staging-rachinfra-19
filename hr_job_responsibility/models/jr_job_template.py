from odoo import api, fields, models
from odoo.exceptions import ValidationError


class JrJobTemplate(models.Model):
    _name = 'jr.job.template'
    _description = 'Job Responsibility Template'
    _order = 'job_id, company_id, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    job_id = fields.Many2one('hr.job', string='Job Position', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    summary = fields.Text()
    line_ids = fields.One2many('jr.job.template.line', 'template_id', string='Responsibilities')
    active = fields.Boolean(default=True)

    @api.constrains('job_id', 'company_id', 'active')
    def _check_unique_active_template(self):
        for template in self:
            if not template.active:
                continue
            domain = [
                ('id', '!=', template.id),
                ('job_id', '=', template.job_id.id),
                ('company_id', '=', template.company_id.id),
                ('active', '=', True),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    'There can only be one active JR template per job position and company.'
                )


class JrJobTemplateLine(models.Model):
    _name = 'jr.job.template.line'
    _description = 'Job Responsibility Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'jr.job.template', string='Template', required=True, ondelete='cascade'
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

    @api.depends('sequence', 'template_id', 'emphasize')
    def _compute_sequence_display(self):
        templates = self.mapped('template_id')
        for template in templates:
            ordered = template.line_ids.sorted(key=lambda l: (l.sequence, l.id))
            counter = 0
            for line in ordered:
                if line.emphasize:
                    line.sequence_display = 0
                    counter = 0
                else:
                    counter += 1
                    line.sequence_display = counter

        # For lines not linked to a template yet (edge cases), keep simple numbering.
        for line in self.filtered(lambda l: not l.template_id):
            if line.emphasize:
                line.sequence_display = 0
            else:
                line.sequence_display = (line.sequence or 0) if line.sequence else 0

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-increment sequence per template when not provided.
        vals_list = [dict(vals) for vals in vals_list]
        missing = [vals for vals in vals_list if not vals.get('sequence')]
        template_ids = {vals.get('template_id') for vals in missing if vals.get('template_id')}
        max_map = {}
        if template_ids:
            groups = self.read_group(
                [('template_id', 'in', list(template_ids))],
                ['sequence:max'],
                ['template_id'],
            )
            max_map = {g['template_id'][0]: g['sequence_max'] for g in groups}

        for vals in vals_list:
            if vals.get('sequence'):
                continue
            template_id = vals.get('template_id')
            next_seq = (max_map.get(template_id, 0) if template_id else 0) + 1
            vals['sequence'] = next_seq
            if template_id:
                max_map[template_id] = next_seq

        return super().create(vals_list)

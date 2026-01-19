from odoo import api, fields, models
from odoo.exceptions import UserError


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    jr_count = fields.Integer(string='Job Responsibilities', compute='_compute_jr_count')

    def _compute_jr_count(self):
        jr_data = self.env['jr.employee.jr'].read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['employee_id']
        )
        count_map = {data['employee_id'][0]: data['employee_id_count'] for data in jr_data}
        for employee in self:
            employee.jr_count = count_map.get(employee.id, 0)

    @api.model
    def create(self, vals):
        employees = super().create(vals)
        employees._generate_job_responsibilities_on_job_change()
        return employees

    def write(self, vals):
        previous_jobs = {employee.id: employee.job_id.id for employee in self}
        job_changed = 'job_id' in vals
        res = super().write(vals)
        if job_changed:
            to_generate = self.filtered(
                lambda emp: previous_jobs.get(emp.id) != emp.job_id.id
            )
            to_generate._generate_job_responsibilities_on_job_change()
        return res

    def _generate_job_responsibilities_on_job_change(self):
        template_model = self.env['jr.job.template']
        jr_model = self.env['jr.employee.jr']
        employees_with_jobs = self.filtered('job_id')
        if not employees_with_jobs:
            return

        job_company_pairs = {
            (employee.job_id.id, employee.company_id.id) for employee in employees_with_jobs
        }

        existing_jrs = jr_model.search_read(
            [
                ('employee_id', 'in', employees_with_jobs.ids),
                ('job_id', 'in', [pair[0] for pair in job_company_pairs]),
                ('company_id', 'in', [pair[1] for pair in job_company_pairs]),
            ],
            ['employee_id', 'job_id', 'company_id'],
        )
        existing_index = {
            (jr['employee_id'][0], jr['job_id'][0], jr['company_id'][0])
            for jr in existing_jrs
        }

        templates = template_model.search(
            [
                ('job_id', 'in', [pair[0] for pair in job_company_pairs]),
                ('company_id', 'in', [pair[1] for pair in job_company_pairs]),
                ('active', '=', True),
            ]
        )
        template_index = {
            (template.job_id.id, template.company_id.id): template for template in templates
        }

        for employee in employees_with_jobs:
            key = (employee.id, employee.job_id.id, employee.company_id.id)
            if key in existing_index:
                continue

            template = template_index.get((employee.job_id.id, employee.company_id.id))
            if template:
                jr_model.create_from_template(employee, template)

    def action_view_job_responsibilities(self):
        self.ensure_one()
        action = self.env.ref('hr_job_responsibility.action_jr_employee_jr').read()[0]
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {
            'default_employee_id': self.id,
            'default_job_id': self.job_id.id,
            'default_company_id': self.company_id.id,
        }
        return action

    def action_generate_job_responsibility(self):
        self.ensure_one()
        if not self.job_id:
            raise UserError('Please set a Job Position before generating a JR.')
        template = self.env['jr.job.template'].search(
            [
                ('job_id', '=', self.job_id.id),
                ('company_id', '=', self.company_id.id),
                ('active', '=', True),
            ],
            limit=1,
        )
        if not template:
            raise UserError('No active JR template found for this Job Position and Company.')
        self.env['jr.employee.jr'].create_from_template(self, template)
        return self.action_view_job_responsibilities()

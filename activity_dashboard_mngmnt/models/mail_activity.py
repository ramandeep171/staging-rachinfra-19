# -*- coding: utf-8 -*-
################################################################################
#
#    SmarterPeak (SP Nexgen Automind Pvt Ltd)
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Copyright (C) 2025-TODAY SmarterPeak (https://www.smarterpeak.com)
#    Author: SmarterPeak Solutions Team (support@smarterpeak.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models
from odoo.exceptions import AccessError


class MailActivity(models.Model):
    """Inherited mail.activity model mostly to add dashboard functionalities"""
    _inherit = "mail.activity"

    activity_tag_ids = fields.Many2many('activity.tag',
                                        string='Activity Tags',
                                        help='Select activity tags.')
    state = fields.Selection([
        ('planned', 'Planned'),
        ('today', 'Today'),
        ('done', 'Done'),
        ('overdue', 'Overdue')], string='State', help='State of the activity',
        compute='_compute_state', store=True)

    @api.model
    def _activity_dashboard_state_domains(self):
        """Centralized domains for dashboard state buckets."""
        today = fields.Date.context_today(self)
        return {
            'planned': [
                ('date_deadline', '>', today),
                ('active', '=', True),
            ],
            'planned_no_deadline': [
                ('date_deadline', '=', False),
                ('active', '=', True),
            ],
            'today': [
                ('date_deadline', '=', today),
                ('active', '=', True),
            ],
            'overdue': [
                ('date_deadline', '<', today),
                ('active', '=', True),
            ],
            'done': [('state', '=', 'done'), ('active', 'in', [True, False])],
        }

    def _activity_dashboard_limit(self):
        """Return per-bucket limit for dashboard lists."""
        limit_value = self.env['ir.config_parameter'].sudo().get_param(
            'activity_dashboard_mngmnt.bucket_limit', 50
        )
        try:
            return max(int(limit_value), 0)
        except (TypeError, ValueError):
            return 50

    @api.model
    def get_dashboard_buckets(self):
        """Return bucketed activity data for the dashboard."""
        domains = self._activity_dashboard_state_domains()
        limit = self._activity_dashboard_limit()
        fields_list = [
            'display_name',
            'activity_type_id',
            'user_id',
            'date_deadline',
            'res_model',
            'res_id',
            'state',
            'active',
        ]
        planned_domain = domains['planned']
        if domains.get('planned_no_deadline'):
            planned_domain = ['|'] + domains['planned_no_deadline'] + planned_domain
        return {
            'planned': self.search_read(
                planned_domain, fields_list, order='date_deadline asc, id desc',
                limit=limit
            ),
            'today': self.search_read(
                domains['today'], fields_list, order='date_deadline asc, id desc',
                limit=limit
            ),
            'overdue': self.search_read(
                domains['overdue'], fields_list, order='date_deadline asc, id desc',
                limit=limit
            ),
            'done': self.search_read(
                domains['done'], fields_list, order='date_deadline asc, id desc',
                limit=limit
            ),
            'activity_type_count': self.env['mail.activity.type'].search_count([]),
        }

    def _action_done(self, feedback=False, attachment_ids=None):
        """Rely on the Odoo 19 implementation to archive activities safely."""
        return super()._action_done(feedback=feedback,
                                    attachment_ids=attachment_ids)

    @api.model
    def get_activity(self, activity_id=None):
        """Return the origin record for an activity; tolerate missing/invalid ids."""
        empty_response = {'model': False, 'res_id': False}
        if activity_id is None:
            activity_id = self.ids[:1] and self.ids[0]
        try:
            activity_id = int(activity_id)
        except (TypeError, ValueError):
            return empty_response
        activity = self.env['mail.activity'].browse(activity_id).exists()
        if not activity:
            return empty_response
        try:
            activity.check_access_rights('read')
            activity.check_access_rule('read')
        except AccessError:
            return empty_response
        if not activity.res_model or not activity.res_id:
            return empty_response
        target = self.env[activity.res_model].browse(activity.res_id).exists()
        if not target:
            return empty_response
        try:
            target.check_access_rights('read')
            target.check_access_rule('read')
        except AccessError:
            return empty_response
        return {
            'model': activity.res_model,
            'res_id': activity.res_id
        }

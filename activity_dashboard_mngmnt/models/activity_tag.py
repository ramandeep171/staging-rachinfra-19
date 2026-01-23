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
from random import randint
from odoo import fields, models


class ActivityTag(models.Model):
    """Model to add tags to an activity"""
    _name = "activity.tag"
    _description = "Activity Tag"

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    name = fields.Char(string='Tag Name',
                       help='Name of the activity tag.',
                       required=True,
                       translate=True)
    color = fields.Integer(string='Color',
                           help='Field that gives color to the tag.',
                           default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists !"), ]

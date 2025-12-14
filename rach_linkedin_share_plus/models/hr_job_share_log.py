# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrJobShareLog(models.Model):
    _name = "hr.job.share.log"
    _description = "Job Share Log"
    _order = "shared_at desc, id desc"
    _check_company_auto = True

    job_id = fields.Many2one(
        "hr.job", string="Job", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="job_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    user_id = fields.Many2one("res.users", string="User", index=True)
    channel = fields.Selection(
        [
            ("linkedin", "LinkedIn"),
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
        ],
        required=True,
        index=True,
    )
    origin = fields.Selection(
        [("backend", "Backend"), ("website", "Website")],
        string="Origin",
        required=True,
        default="backend",
        index=True,
    )
    shared_at = fields.Datetime(
        string="Shared On", required=True, default=fields.Datetime.now, index=True
    )
    url_used = fields.Char(string="URL Used", help="Short URL used when sharing")

    @api.constrains("job_id", "company_id")
    def _check_company_consistency(self):
        for log in self:
            if log.job_id and log.company_id and log.job_id.company_id != log.company_id:
                raise ValidationError(
                    _("Job share log company must match the related job's company.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        assign_user = user and not user._is_public()
        for vals in vals_list:
            if assign_user and not vals.get("user_id"):
                vals.setdefault("user_id", user.id)
        return super().create(vals_list)

    def name_get(self):
        result = []
        for log in self:
            label = "%s (%s)" % (
                log.job_id.name or "",
                dict(self._fields["channel"].selection).get(log.channel, ""),
            )
            result.append((log.id, label))
        return result

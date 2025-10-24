from odoo import models, fields, api
from datetime import timedelta


class QualityCubeSample(models.Model):
    _name = 'quality.cube.sample'
    _description = 'Quality Cube Sample'

    test_id = fields.Many2one('quality.cube.test', string='Cube Test', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    size_mm = fields.Char(string='Size (mm)', default='150x150x150')
    casting_date = fields.Date()
    test_date = fields.Date(compute='_compute_test_date', store=True)
    load_kN = fields.Float(string='Load (kN)')
    area_mm2 = fields.Float(string='Area (mm²)', default=22500)
    compressive_strength = fields.Float(string='Strength (MPa)', compute='_compute_strength', store=True)
    mode_of_failure = fields.Char(string='Mode of Failure')
    remarks = fields.Text()

    @api.depends('casting_date', 'test_id.day_type')
    def _compute_test_date(self):
        for rec in self:
            if rec.casting_date and rec.test_id and rec.test_id.day_type:
                delta = 6 if rec.test_id.day_type == '7' else 27
                rec.test_date = fields.Date.to_date(rec.casting_date) + timedelta(days=delta)
            else:
                rec.test_date = False

    @api.depends('load_kN', 'area_mm2')
    def _compute_strength(self):
        for rec in self:
            try:
                rec.compressive_strength = (rec.load_kN or 0.0) * 1000.0 / (rec.area_mm2 or 1.0)
            except Exception:
                rec.compressive_strength = 0.0

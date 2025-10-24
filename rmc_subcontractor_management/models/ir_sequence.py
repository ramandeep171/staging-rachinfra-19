from datetime import datetime

from odoo import fields, models
from odoo.exceptions import UserError


class IrSequence(models.Model):
    _inherit = "ir.sequence"

    def _get_prefix_suffix(self, date=None, date_range=None):
        try:
            return super()._get_prefix_suffix(date=date, date_range=date_range)
        except UserError as error:
            def _interpolate(string, mapping):
                return (string % mapping) if string else ""

            def _interpolation_dict_with_context():
                now = range_date = effective_date = datetime.now(self.env.tz)
                ctx = self.env.context
                if date or ctx.get("ir_sequence_date"):
                    effective_date = fields.Datetime.from_string(date or ctx.get("ir_sequence_date"))
                if date_range or ctx.get("ir_sequence_date_range"):
                    range_date = fields.Datetime.from_string(date_range or ctx.get("ir_sequence_date_range"))

                sequences = {
                    "year": "%Y",
                    "month": "%m",
                    "day": "%d",
                    "y": "%y",
                    "doy": "%j",
                    "woy": "%W",
                    "weekday": "%w",
                    "h24": "%H",
                    "h12": "%I",
                    "min": "%M",
                    "sec": "%S",
                    "isoyear": "%G",
                    "isoy": "%g",
                    "isoweek": "%V",
                }
                result = {}
                for key, strftime_format in sequences.items():
                    result[key] = effective_date.strftime(strftime_format)
                    result[f"range_{key}"] = range_date.strftime(strftime_format)
                    result[f"current_{key}"] = now.strftime(strftime_format)

                # Surface selected context keys (used by custom prefixes) for interpolation.
                for ctx_key in ("subc_geo", "plant_code"):
                    if ctx_key in ctx and ctx[ctx_key] is not None:
                        result[ctx_key] = ctx[ctx_key]
                return result

            self.ensure_one()
            mapping = _interpolation_dict_with_context()
            try:
                return _interpolate(self.prefix, mapping), _interpolate(self.suffix, mapping)
            except (ValueError, TypeError, KeyError):
                raise error

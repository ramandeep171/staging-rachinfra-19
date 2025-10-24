from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    diesel_log_id = fields.Many2one(
        'diesel.log',
        string='Equipment Log',
        readonly=True,
        help='Auto-created equipment log linked to this attendance.'
    )

    # Related (no DB column) fields pulled from linked diesel log
    check_in_reading = fields.Float(
        string='Check In Reading',
        related='diesel_log_id.last_odometer',
        readonly=False,
        store=True,
        help='Starting (last) odometer reading from linked diesel log.'
    )
    check_out_reading = fields.Float(
        string='Check Out Reading',
        related='diesel_log_id.current_odometer',
        readonly=False,
        store=True,
        help='Ending (current) odometer reading from linked diesel log.'
    )
    check_in_gaje = fields.Float(
        string='Check In Gaje',
        related='diesel_log_id.last_gaje',
        readonly=False,
        store=True,
        help='Starting (last) gaje reading from linked diesel log.'
    )
    check_out_gaje = fields.Float(
        string='Check Out Gaje',
        related='diesel_log_id.current_gaje',
        readonly=False,
        store=True,
        help='Ending (current) gaje reading from linked diesel log.'
    )

    def _get_employee_vehicle(self):
        self.ensure_one()
        Vehicle = self.env['fleet.vehicle']
        partner_ids = []
        if self.employee_id.user_id and self.employee_id.user_id.partner_id:
            partner_ids.append(self.employee_id.user_id.partner_id.id)
        if getattr(self.employee_id, 'work_contact_id', False):
            partner_ids.append(self.employee_id.work_contact_id.id)
        domain = []
        if partner_ids:
            domain.append(('driver_id', 'in', list(set(partner_ids))))
        vehicles = Vehicle.search(domain, limit=1) if domain else Vehicle.browse()
        if not vehicles and 'employee_id' in Vehicle._fields:
            vehicles = Vehicle.search([('employee_id', '=', self.employee_id.id)], limit=1)
        if vehicles:
            return vehicles[0]
        _logger.debug('No vehicle matched for employee %s (partners %s)', self.employee_id.name, partner_ids)
        return False

    @staticmethod
    def _compute_shift_code(env, dt):
        if not dt:
            return 'a'
        hour = fields.Datetime.context_timestamp(env.user, dt).hour
        if 6 <= hour < 14:
            return 'a'
        if 14 <= hour < 22:
            return 'b'
        return 'c'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        DieselLog = self.env['diesel.log']
        for att in records:
            vehicle = att._get_employee_vehicle()
            if vehicle and not att.diesel_log_id and att.check_in:
                log_vals = {
                    'log_type': 'equipment',
                    'employee_id': att.employee_id.id,
                    'attendance_check_in': att.check_in,
                    'shift': self._compute_shift_code(self.env, att.check_in),
                    'vehicle_id': vehicle.id,
                    'name': 'New',
                    'date': att.check_in,
                }
                if att.check_out:
                    log_vals['attendance_check_out'] = att.check_out
                att.diesel_log_id = DieselLog.create(log_vals).id
                _logger.info('Created equipment diesel.log %s for attendance %s', att.diesel_log_id, att.id)
        return records

    def write(self, vals):
        res = super().write(vals)
        for att in self:
            if att.diesel_log_id:
                upd = {}
                if 'check_in' in vals:
                    if att.check_in:
                        upd.update({
                            'attendance_check_in': att.check_in,
                            'date': att.check_in,
                            'shift': self._compute_shift_code(self.env, att.check_in),
                        })
                    else:
                        upd.update({
                            'attendance_check_in': False,
                        })
                if 'check_out' in vals:
                    upd['attendance_check_out'] = att.check_out or False
                if upd:
                    att.diesel_log_id.write(upd)
                    _logger.info('Updated equipment diesel.log %s from attendance %s with %s', att.diesel_log_id.id, att.id, upd)
        return res

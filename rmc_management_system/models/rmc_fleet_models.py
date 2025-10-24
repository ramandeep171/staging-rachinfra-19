from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RmcSubcontractor(models.Model):
    _inherit = 'rmc.subcontractor'

    # keep existing fields; this file adds integrations (if not already present) via safety checks
    @api.model_create_multi
    def create(self, vals_list):
        # ensure partner exists; if not create a partner
        for vals in vals_list:
            if not vals.get('partner_id') and vals.get('name'):
                partner = self.env['res.partner'].create({'name': vals.get('name')})
                vals['partner_id'] = partner.id
        return super().create(vals_list)


class RmcSubcontractorPlant(models.Model):
    _inherit = 'rmc.subcontractor.plant'
    _description = 'RMC Subcontractor Plant (fleet extensions)'

    # Keep core fields in rmc_subcontractor.py; add extension fields only here if necessary


class RmcSubcontractorTransport(models.Model):
    _inherit = 'rmc.subcontractor.transport'
    _description = 'RMC Subcontractor Transport (fleet extensions)'

    @api.model_create_multi
    def create(self, vals_list):
        records = super(RmcSubcontractorTransport, self).create(vals_list)
        for rec in records:
            try:
                rec._sync_to_fleet()
            except Exception:
                pass
        return records

    def write(self, vals):
        res = super(RmcSubcontractorTransport, self).write(vals)
        for rec in self:
            try:
                rec._sync_to_fleet()
            except Exception:
                pass
        return res

    def _sync_to_fleet(self):
        if 'fleet.vehicle' not in self.env:
            return
        Fleet = self.env['fleet.vehicle']
        Partner = self.env['res.partner']
        for rec in self:
            partner = rec.subcontractor_id.partner_id
            if not partner:
                partner = Partner.create({'name': rec.subcontractor_id.name})
                rec.subcontractor_id.partner_id = partner
            if not rec.fleet_vehicle_id:
                vals = {
                    'name': rec.transport_code or rec.license_plate or 'Transport',
                    'license_plate': rec.license_plate,
                    'partner_id': partner.id,
                }
                vehicle = Fleet.create(vals)
                rec.fleet_vehicle_id = vehicle
            else:
                if partner and rec.fleet_vehicle_id.partner_id != partner:
                    rec.fleet_vehicle_id.partner_id = partner


class RmcSubcontractorPump(models.Model):
    _inherit = 'rmc.subcontractor.pump'
    _description = 'RMC Subcontractor Pump (fleet extensions)'

    # Keep core fields in rmc_subcontractor.py; add integration fields here if needed

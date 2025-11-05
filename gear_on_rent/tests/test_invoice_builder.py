from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import Form, SavepointCase
from odoo.tests.common import new_test_request


class TestGearOnRentMrp(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("gear_on_rent.group_gear_on_rent_manager")

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "email": "customer@example.com",
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "RMC Service",
                "type": "service",
                "list_price": 200.0,
            }
        )
        cls.product.gear_is_production = True

        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_qty": 1.0,
                "type": "phantom",
            }
        )

        cls.workcenter = cls.env["mrp.workcenter"].create(
            {
                "name": "Batching Plant 1",
                "code": "PLANT-1",
                "capacity": 1,
                "time_start": 0,
                "time_stop": 0,
                "x_ids_external_id": "PLANT-1",
            }
        )

        contract_start = fields.Date.to_date("2025-03-01")
        contract_end = fields.Date.to_date("2025-03-31")

        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "x_workcenter_id": cls.workcenter.id,
            }
        )

        cls.order_line = cls.env["sale.order.line"].create(
            {
                "order_id": cls.order.id,
                "product_id": cls.product.id,
                "product_uom_qty": 240.0,
                "price_unit": 200.0,
                "start_date": fields.Datetime.to_datetime("2025-03-01 00:00:00"),
                "return_date": fields.Datetime.to_datetime("2025-03-31 23:59:59"),
            }
        )

        cls.order.invalidate_recordset()
        cls.assertEqual(cls.order.x_billing_category, "rmc")
        cls.assertEqual(cls.order.x_monthly_mgq, 240.0)
        cls.assertEqual(cls.order.x_contract_start, contract_start)
        cls.assertEqual(cls.order.x_contract_end, contract_end)

        cls.order.action_confirm()
        cls.order.gear_generate_monthly_orders()
        cls.monthly_order = cls.env["gear.rmc.monthly.order"].search(
            [
                ("so_id", "=", cls.order.id),
                ("date_start", "<=", contract_start),
                ("date_end", ">=", contract_start),
            ],
            limit=1,
        )
        cls.monthly_order.action_schedule_orders()

    def _get_first_production(self):
        self.monthly_order.flush()
        production = self.monthly_order.production_ids.sorted(key=lambda p: p.date_start or datetime.min)[:1]
        self.assertTrue(production, "Expected a daily manufacturing order to exist")
        return production

    def _allocate_ngt(self, hours):
        start = fields.Datetime.to_datetime("2025-03-01 00:00:00")
        end = start + timedelta(hours=hours)
        ngt = self.env["gear.ngt.request"].create(
            {
                "so_id": self.order.id,
                "date_start": start,
                "date_end": end,
            }
        )
        ngt.action_submit()
        ngt.action_approve()
        return ngt

    def _allocate_loto(self, hours):
        start = fields.Datetime.to_datetime("2025-03-05 00:00:00")
        end = start + timedelta(hours=hours)
        loto = self.env["gear.loto.request"].create(
            {
                "so_id": self.order.id,
                "date_start": start,
                "date_end": end,
            }
        )
        loto.action_submit()
        loto.action_approve()
        return loto

    def test_ngt_relief_reduces_adjusted_target(self):
        ngt_hours = 12.0
        self._allocate_ngt(ngt_hours)
        daily_target = self.monthly_order.monthly_target_qty / len(self.monthly_order.production_ids)
        expected_relief_qty = daily_target * (ngt_hours / 24.0)
        expected_adjusted = self.monthly_order.monthly_target_qty - expected_relief_qty
        self.assertAlmostEqual(self.monthly_order.adjusted_target_qty, expected_adjusted, places=2)

    def test_loto_waveoff_applies_allowance(self):
        loto = self._allocate_loto(60.0)
        self.assertAlmostEqual(loto.hours_waveoff_applied, 48.0, places=2)
        self.assertAlmostEqual(loto.hours_chargeable, 12.0, places=2)
        self.assertAlmostEqual(self.monthly_order.waveoff_hours_applied, 48.0, places=2)
        self.assertAlmostEqual(self.monthly_order.waveoff_hours_chargeable, 12.0, places=2)

    def test_invoice_builder_uses_mrp_metrics(self):
        production = self._get_first_production()
        workorder = production.workorder_ids[:1]
        payload = {
            "produced_m3": 30.0,
            "timestamp": fields.Datetime.to_string(production.date_start or fields.Datetime.now()),
            "runtime_min": 45,
            "idle_min": 15,
            "alarms": ["LOW_WATER"],
        }
        workorder.gear_register_ids_payload(payload)

        wizard = Form(self.env["gear.prepare.invoice.mrp"])
        wizard.monthly_order_id = self.monthly_order
        wizard.invoice_date = fields.Date.to_date("2025-03-31")
        prepare = wizard.save()
        action = prepare.action_prepare_invoice()
        invoice = self.env["account.move"].browse(action["res_id"])

        self.assertAlmostEqual(invoice.gear_prime_output_qty, 30.0, places=2)
        payload = invoice._gear_get_month_end_payload()
        self.assertEqual(len(payload.get("dockets", [])), 1)
        self.assertGreater(payload.get("optimized_standby"), -0.01)
        self.assertIn("cooling_totals", payload)
        self.assertIn("normal_totals", payload)
        self.assertAlmostEqual(payload.get("normal_totals", {}).get("prime_output_qty", 0.0), 30.0, places=2)
        self.assertAlmostEqual(payload.get("cooling_totals", {}).get("target_qty", 0.0), 0.0, places=2)

    def test_invoice_builder_adds_ngt_line(self):
        production = self._get_first_production()
        workorder = production.workorder_ids[:1]
        payload = {
            "produced_m3": 40.0,
            "timestamp": fields.Datetime.to_string(production.date_start or fields.Datetime.now()),
            "runtime_min": 60,
            "idle_min": 0,
            "alarms": [],
        }
        workorder.gear_register_ids_payload(payload)

        self._allocate_ngt(12.0)
        self.monthly_order.invalidate_recordset()

        wizard = Form(self.env["gear.prepare.invoice.mrp"])
        wizard.monthly_order_id = self.monthly_order
        wizard.invoice_date = fields.Date.to_date("2025-03-31")
        prepare = wizard.save()
        action = prepare.action_prepare_invoice()
        invoice = self.env["account.move"].browse(action["res_id"])

        expected_qty = self.monthly_order.downtime_relief_qty
        self.assertGreater(expected_qty, 0.0)

        ngt_lines = invoice.invoice_line_ids.filtered(lambda l: "NGT Relief" in (l.name or ""))
        self.assertTrue(ngt_lines, "Expected an invoice line capturing NGT relief.")
        self.assertAlmostEqual(sum(ngt_lines.mapped("quantity")), expected_qty, places=2)
        self.assertTrue(all(abs(line.price_unit) < 1e-6 for line in ngt_lines))

        payload = invoice._gear_get_month_end_payload()
        self.assertAlmostEqual(
            payload.get("normal_totals", {}).get("ngt_m3", 0.0),
            expected_qty,
            places=2,
        )

    def test_ids_controller_creates_docket(self):
        production = self._get_first_production()
        timestamp = (production.date_start or fields.Datetime.now()) + timedelta(minutes=5)
        self.env["ir.config_parameter"].sudo().set_param("gear_on_rent.ids_token", "secret-token")

        payload = {
            "workcenter_external_id": self.workcenter.x_ids_external_id,
            "timestamp": fields.Datetime.to_string(timestamp),
            "produced_m3": 18.0,
            "runtime_min": 35,
            "idle_min": 10,
            "alarms": ["BATCH_DELAY"],
        }

        from odoo.addons.gear_on_rent.controllers.ids import GearIdsController

        with new_test_request(self.env, headers={"X-IDS-Token": "secret-token"}):
            response = GearIdsController().ids_workcenter_update(**payload)

        self.assertEqual(response.get("status"), "ok")
        workorder = production.workorder_ids[:1]
        self.assertAlmostEqual(workorder.gear_prime_output_qty, 18.0, places=2)
        self.assertTrue(workorder.gear_docket_ids)

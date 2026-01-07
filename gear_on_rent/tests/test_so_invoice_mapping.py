from pathlib import Path
import compileall

import pytest

try:  # pragma: no cover - skip when the Odoo framework is unavailable
    from odoo import fields
    from odoo.tests import SavepointCase
except ModuleNotFoundError:  # pragma: no cover
    pytest.skip(
        "The Odoo test framework is not available in this execution environment.",
        allow_module_level=True,
    )


class TestSoInvoiceMapping(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Plant Customer", "email": "plant@example.com"})

        cls.service_master = cls.env["gear.service.master"].create(
            {"name": "Dedicated Plant", "category": "dedicated", "inventory_mode": "without_inventory"}
        )
        cls.capacity_master = cls.env["gear.plant.capacity.master"].create(
            {"name": "120 CUM", "capacity_cum_hour": 120.0}
        )

        cls.base_rate = cls._make_rate_tier(prime=370.0, optimize=50.0, after=120.0)

    @classmethod
    def _make_rate_tier(cls, prime=0.0, optimize=0.0, after=0.0):
        return cls.env["gear.mgq.rate.master"].create(
            {
                "name": f"Tier {prime}/{optimize}/{after}",
                "service_id": cls.service_master.id,
                "capacity_id": cls.capacity_master.id,
                "mgq_min": 0.0,
                "mgq_max": False,
                "prime_rate": prime,
                "optimize_rate": optimize,
                "after_mgq_rate": after,
            }
        )

    def _create_quote(self, **kwargs):
        mgq = kwargs.get("mgq", 0.0)
        rate_tier = kwargs.get("rate_tier") or self.base_rate
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "x_billing_category": "plant",
                "gear_service_id": self.service_master.id,
                "gear_capacity_id": self.capacity_master.id,
                "gear_mgq_rate_id": rate_tier.id,
                "mgq_monthly": mgq,
                "x_monthly_mgq": mgq,
                "qty_mgq": kwargs.get("qty_mgq", mgq),
                "qty_below": kwargs.get("qty_below", 0.0),
                "qty_above": kwargs.get("qty_above", 0.0),
                "prime_rate": kwargs.get("prime_rate", rate_tier.prime_rate),
                "optimize_rate": kwargs.get("optimize_rate", rate_tier.optimize_rate),
                "excess_rate": kwargs.get("after_mgq_rate", rate_tier.after_mgq_rate),
                "gear_expected_production_qty": kwargs.get("production_qty", 0.0),
            }
        )

    def test_product_variant_integrity(self):
        template = self.env.ref("gear_on_rent.product_batching_service")
        attr = self.env.ref("gear_on_rent.product_attr_billing_mode")
        prime = self.env.ref("gear_on_rent.product_batching_service_prime")
        optimize = self.env.ref("gear_on_rent.product_batching_service_optimize")
        ngt = self.env.ref("gear_on_rent.product_batching_service_ngt")

        self.assertTrue(template.attribute_line_ids, "Plant / Mixing Service must have an attribute line")
        self.assertEqual(attr.name, "Billing Mode")
        self.assertSetEqual(
            set(template.attribute_line_ids.mapped("value_ids.id")),
            {
                self.env.ref("gear_on_rent.product_attr_billing_prime").id,
                self.env.ref("gear_on_rent.product_attr_billing_optimize").id,
                self.env.ref("gear_on_rent.product_attr_billing_ngt").id,
            },
        )
        self.assertTrue(prime.exists() and optimize.exists() and ngt.exists())

    def test_quotation_acceptance_creates_three_lines(self):
        quote = self._create_quote(
            mgq=3000,
            prime_rate=370,
            optimize_rate=50,
            after_mgq_rate=120,
            qty_below=2500,
            qty_above=4200,
        )

        so = quote.action_accept_and_create_so()
        self.assertEqual(len(so.order_line), 3, "Quotation acceptance must create three billing lines")

        products = so.order_line.mapped("product_id")
        self.assertSetEqual(
            set(products),
            {
                self.env.ref("gear_on_rent.product_batching_service_prime"),
                self.env.ref("gear_on_rent.product_batching_service_optimize"),
                self.env.ref("gear_on_rent.product_batching_service_ngt"),
            },
        )

        def _line_for(xmlid):
            return so.order_line.filtered(lambda l: l.product_id == self.env.ref(xmlid))

        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_prime").product_uom_qty, 3000)
        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_prime").price_unit, 370)
        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_optimize").product_uom_qty, 2500)
        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_optimize").price_unit, 50)
        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_ngt").product_uom_qty, 4200)
        self.assertAlmostEqual(_line_for("gear_on_rent.product_batching_service_ngt").price_unit, 120)

    def test_so_to_invoice_mapping(self):
        quote = self._create_quote(
            mgq=3000,
            prime_rate=370,
            optimize_rate=50,
            after_mgq_rate=120,
            qty_below=2500,
            qty_above=4200,
        )
        so = quote.action_accept_and_create_so()
        so.action_confirm()
        invoice = so._create_invoices()

        self.assertEqual(len(invoice.invoice_line_ids), 3)
        for line in invoice.invoice_line_ids:
            so_line = so.order_line.filtered(lambda l: l.product_id == line.product_id)
            self.assertTrue(so_line, "Invoice line must originate from an SO line")
            self.assertAlmostEqual(line.quantity, so_line.product_uom_qty)
            self.assertAlmostEqual(line.price_unit, so_line.price_unit)
            self.assertAlmostEqual(line.price_subtotal, so_line.product_uom_qty * so_line.price_unit)

    def test_zero_rate_handling_skips_lines(self):
        zero_rate_tier = self._make_rate_tier(prime=370.0, optimize=0.0, after=0.0)
        quote = self._create_quote(
            mgq=3000,
            prime_rate=370,
            optimize_rate=0,
            after_mgq_rate=0,
            qty_below=2500,
            qty_above=4200,
            rate_tier=zero_rate_tier,
        )
        so = quote.action_accept_and_create_so()
        self.assertEqual(len(so.order_line), 1)
        prime_line = so.order_line.filtered(lambda l: l.product_id == self.env.ref("gear_on_rent.product_batching_service_prime"))
        self.assertTrue(prime_line)
        self.assertAlmostEqual(prime_line.product_uom_qty, 3000)
        self.assertAlmostEqual(prime_line.price_unit, 370)

    def test_python_and_xml_are_loadable(self):
        module_root = Path(__file__).resolve().parents[1]
        assert compileall.compile_dir(str(module_root), quiet=1), "Python sources must compile"

        xml_files = list(module_root.rglob("*.xml"))
        self.assertTrue(xml_files, "Expected XML assets to exist for parsing")
        for xml_file in xml_files:
            try:
                xml_file.read_text()
                from xml.etree import ElementTree as ET

                ET.parse(xml_file)
            except Exception as exc:  # pragma: no cover - fail fast on malformed XML
                raise AssertionError(f"Failed to parse XML template {xml_file}: {exc}")

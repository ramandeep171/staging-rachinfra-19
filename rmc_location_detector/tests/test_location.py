import json
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGeoZone(TransactionCase):
    def setUp(self):
        super().setUp()
        config = self.env["res.config.settings"].create({"group_product_pricelist": True})
        config.execute()

        self.website = self.env["website"].get_current_website()
        currency = self.website.company_id.currency_id

        self.default_pricelist = self.website.pricelist_id
        self.city_pricelist = self.env["product.pricelist"].create(
            {
                "name": "City Pricelist",
                "currency_id": currency.id,
                "selectable": True,
                "website_id": self.website.id,
            }
        )
        self.zip_pricelist = self.env["product.pricelist"].create(
            {
                "name": "ZIP Pricelist",
                "currency_id": currency.id,
                "selectable": True,
                "website_id": self.website.id,
            }
        )
        self.website.write({"pricelist_ids": [(4, self.city_pricelist.id), (4, self.zip_pricelist.id)]})

        self.zone_zip = self.env["rmc.geo.zone"].create(
            {
                "name": "Bangalore ZIP Zone",
                "zip_prefix": "5600",
                "pricelist_id": self.zip_pricelist.id,
                "website_id": self.website.id,
            }
        )
        self.zone_city = self.env["rmc.geo.zone"].create(
            {
                "name": "Mumbai City Zone",
                "city": "Mumbai",
                "pricelist_id": self.city_pricelist.id,
                "website_id": self.website.id,
            }
        )

    def test_zip_prefix_priority(self):
        pricelist = self.env["rmc.geo.zone"].match(self.website, "Bengaluru", "560045")
        self.assertEqual(pricelist, self.zip_pricelist)

    def test_city_match_when_no_zip(self):
        pricelist = self.env["rmc.geo.zone"].match(self.website, "Mumbai", "")
        self.assertEqual(pricelist, self.city_pricelist)

    def test_default_pricelist_fallback(self):
        pricelist = self.env["rmc.geo.zone"].match(self.website, "Chennai", "600001")
        self.assertEqual(pricelist, self.default_pricelist)


@tagged("post_install", "-at_install")
class TestLocationController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = cls.env["res.config.settings"].create({"group_product_pricelist": True})
        config.execute()

        cls.website = cls.env["website"].get_current_website()
        currency = cls.website.company_id.currency_id

        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "Delhi Zone Pricelist",
                "currency_id": currency.id,
                "selectable": True,
                "website_id": cls.website.id,
            }
        )
        cls.website.write({"pricelist_ids": [(4, cls.pricelist.id)]})

        cls.env["rmc.geo.zone"].create(
            {
                "name": "Delhi Zone",
                "zip_prefix": "1100",
                "pricelist_id": cls.pricelist.id,
                "website_id": cls.website.id,
            }
        )

    def _json_from_response(self, response):
        if hasattr(response, "json"):
            try:
                return response.json()
            except Exception:
                pass
        text = getattr(response, "text", None)
        if text is None and hasattr(response, "content"):
            text = response.content.decode()
        if text is None:
            text = response.read().decode()
        return json.loads(text)

    def test_save_endpoint_switches_pricelist(self):
        payload = {"city": "Delhi", "zip": "110045", "method": "manual"}
        response = self.url_open(
            "/rmc/location/save",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = self._json_from_response(response)
        self.assertEqual(data.get("zip"), "110045")
        self.assertEqual(data.get("pricelist_id"), self.pricelist.id)
        self.assertTrue(data.get("repriced"))

    def test_checkout_sync_endpoint(self):
        payload = {"zip": "110099", "city": "Delhi"}
        response = self.url_open(
            "/rmc/location/checkout_sync",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = self._json_from_response(response)
        self.assertEqual(data.get("pricelist_id"), self.pricelist.id)

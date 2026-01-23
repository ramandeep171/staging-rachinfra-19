from odoo import fields
from odoo.tests.common import TransactionCase


class TestActivityDashboard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Dashboard Partner"})
        activity_type = self.env["mail.activity.type"].search([], limit=1)
        if not activity_type:
            activity_type = self.env["mail.activity.type"].create({
                "name": "Dashboard Test Type",
            })
        self.activity_type = activity_type

    def _create_activity(self, date_deadline):
        return self.env["mail.activity"].create({
            "activity_type_id": self.activity_type.id,
            "res_model_id": self.env["ir.model"]._get_id("res.partner"),
            "res_id": self.partner.id,
            "user_id": self.env.user.id,
            "date_deadline": date_deadline,
            "summary": "Dashboard test activity",
        })

    def test_bucket_classification(self):
        today = fields.Date.context_today(self.env.user)
        yesterday = fields.Date.subtract(today, days=1)
        tomorrow = fields.Date.add(today, days=1)

        overdue = self._create_activity(yesterday)
        today_activity = self._create_activity(today)
        planned = self._create_activity(tomorrow)

        buckets = self.env["mail.activity"].get_dashboard_buckets()

        planned_ids = {item["id"] for item in buckets["planned"]}
        today_ids = {item["id"] for item in buckets["today"]}
        overdue_ids = {item["id"] for item in buckets["overdue"]}

        self.assertIn(planned.id, planned_ids)
        self.assertIn(today_activity.id, today_ids)
        self.assertIn(overdue.id, overdue_ids)

    def test_get_activity_returns_origin(self):
        activity = self._create_activity(fields.Date.context_today(self.env.user))

        result = self.env["mail.activity"].get_activity(activity.id)

        self.assertEqual(result["model"], "res.partner")
        self.assertEqual(result["res_id"], self.partner.id)

    def test_get_activity_missing_target(self):
        activity = self._create_activity(fields.Date.context_today(self.env.user))
        self.partner.unlink()

        result = self.env["mail.activity"].get_activity(activity.id)

        self.assertFalse(result["model"])
        self.assertFalse(result["res_id"])

    def test_get_activity_without_argument(self):
        """Calling get_activity without id should not crash."""
        result = self.env["mail.activity"].get_activity()

        self.assertFalse(result["model"])
        self.assertFalse(result["res_id"])

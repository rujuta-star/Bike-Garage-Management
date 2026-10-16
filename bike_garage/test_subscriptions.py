import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import tenancy
from bike_garage.bike_garage.api import subscriptions
from bike_garage.bike_garage.doctype.bg_garage_subscription.bg_garage_subscription import (
	BGGarageSubscription,
)
from bike_garage.bike_garage.doctype.bg_subscription_plan.bg_subscription_plan import (
	BGSubscriptionPlan,
)


class FakeSubscription:
	def __init__(self, **values):
		self.__dict__.update(values)
		self._new = values.get("new", True)
		self._before = values.get("before")

	def is_new(self):
		return self._new

	def get_doc_before_save(self):
		return self._before


class TestSubscriptionFoundation(unittest.TestCase):
	def setUp(self):
		self.session = patch.object(frappe, "session", SimpleNamespace(user="garage.user@example.test"))
		self.session.start()
		self.addCleanup(self.session.stop)
		self.roles = patch.object(frappe, "get_roles", return_value=[])
		self.roles.start()
		self.addCleanup(self.roles.stop)
		self.throw = patch.object(frappe, "throw", side_effect=self._raise)
		self.throw.start()
		self.addCleanup(self.throw.stop)

	@staticmethod
	def _raise(message, exc=None):
		raise (exc or frappe.ValidationError)(message)

	def _subscription(self, **overrides):
		values = {
			"name": "SUBSCRIPTION-TEST-1",
			"status": "Pending",
			"garage": "GARAGE-A",
			"plan": "Basic",
			"start_date": "2026-01-01",
			"end_date": "2026-12-31",
			"billing_period": "Yearly",
			"agreed_amount": 1200,
			"currency": "INR",
			"payment_status": "Pending",
			"payment_reference": None,
			"active_garage": None,
			"new": True,
		}
		values.update(overrides)
		return FakeSubscription(**values)

	def test_garage_users_cannot_read_platform_subscription_data(self):
		with (
			patch.object(frappe, "get_all") as get_all,
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe.db, "exists") as exists,
		):
			with self.assertRaises(frappe.PermissionError):
				subscriptions.get_platform_subscription_data()
		get_all.assert_not_called()
		get_doc.assert_not_called()
		exists.assert_not_called()

	def test_all_subscription_mutations_require_platform_authorization(self):
		calls = (
			lambda: subscriptions.save_subscription_plan("Basic", "Monthly", 10, "INR"),
			lambda: subscriptions.create_garage_subscription(
				"GARAGE-A", "Basic", "2026-01-01", "2026-01-31"
			),
			lambda: subscriptions.update_garage_subscription("SUB-1", "Active"),
		)
		with (
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe.db, "exists") as exists,
			patch.object(frappe.db, "get_value") as get_value,
		):
			for call in calls:
				with self.subTest(call=call), self.assertRaises(frappe.PermissionError):
					call()
		get_doc.assert_not_called()
		exists.assert_not_called()
		get_value.assert_not_called()

	def test_plan_rejects_negative_and_non_finite_amounts(self):
		for amount in (-1, "NaN", "Infinity"):
			plan = SimpleNamespace(
				plan_name="Basic",
				status="Active",
				billing_period="Monthly",
				amount=amount,
				currency="INR",
			)
			with self.subTest(amount=amount), patch.object(frappe.db, "exists", return_value=True):
				with self.assertRaises(frappe.ValidationError):
					BGSubscriptionPlan.validate(plan)

	def test_plan_requires_an_existing_currency_and_allowlisted_period(self):
		plan = SimpleNamespace(
			plan_name="Basic", status="Active", billing_period="Weekly", amount=10, currency="INR"
		)
		with self.assertRaises(frappe.ValidationError):
			BGSubscriptionPlan.validate(plan)
		plan.billing_period = "Monthly"
		with patch.object(frappe.db, "exists", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				BGSubscriptionPlan.validate(plan)

	def test_subscription_rejects_invalid_dates_and_negative_amount(self):
		for values in (
			{"start_date": "2026-12-31", "end_date": "2026-01-01"},
			{"agreed_amount": -1},
			{"agreed_amount": "NaN"},
		):
			subscription = self._subscription(**values)
			with self.subTest(values=values):
				with (
					patch.object(frappe.db, "exists", return_value=True),
					patch.object(frappe.db, "get_value", return_value="Active"),
				):
					with self.assertRaises(frappe.ValidationError):
						BGGarageSubscription.validate(subscription)

	def test_new_subscription_must_start_pending_and_cannot_be_unassigned(self):
		for values in ({"status": "Active"}, {"garage": None}):
			subscription = self._subscription(**values)
			with self.subTest(values=values), patch.object(frappe.db, "exists", return_value=True):
				with self.assertRaises(frappe.ValidationError):
					BGGarageSubscription.validate(subscription)

	def test_cancelled_and_expired_subscriptions_cannot_be_reactivated(self):
		for old_status in ("Cancelled", "Expired"):
			subscription = self._subscription(
				status="Active",
				new=False,
				before=SimpleNamespace(status=old_status, garage="GARAGE-A"),
			)
			with self.subTest(old_status=old_status), patch.object(frappe.db, "exists", return_value=True):
				with self.assertRaises(frappe.ValidationError):
					BGGarageSubscription.validate(subscription)

	def test_active_subscription_is_unique_per_garage(self):
		subscription = self._subscription(
			status="Active",
			new=False,
			before=SimpleNamespace(status="Active", garage="GARAGE-A"),
		)
		with (
			patch.object(frappe.db, "exists", side_effect=[True, True, True]),
			patch.object(frappe.db, "get_value", side_effect=["Active", "Active"]),
		):
			with self.assertRaises(frappe.ValidationError):
				BGGarageSubscription.validate(subscription)

	def test_pending_subscription_can_be_activated_for_active_garage(self):
		subscription = self._subscription(
			status="Active",
			new=False,
			before=SimpleNamespace(status="Pending", garage="GARAGE-A"),
		)
		with (
			patch.object(frappe.db, "exists", side_effect=[True, True, False]),
			patch.object(frappe.db, "get_value", side_effect=["Active", "Active"]),
		):
			BGGarageSubscription.validate(subscription)
		self.assertEqual(subscription.active_garage, "GARAGE-A")

	def test_payment_reference_remains_unverified_and_is_not_revenue(self):
		subscription = self._subscription(payment_reference="BANK-REF-1")
		with (
			patch.object(frappe.db, "exists", side_effect=[True, True]),
			patch.object(frappe.db, "get_value", return_value="Active"),
		):
			BGGarageSubscription.validate(subscription)
		self.assertEqual(subscription.payment_status, "Unverified")
		self.assertIsNone(subscription.active_garage)

	def test_confirmed_payment_status_is_rejected_without_verification_integration(self):
		subscription = self._subscription(payment_status="Confirmed")
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value="Active"),
		):
			with self.assertRaises(frappe.ValidationError):
				BGGarageSubscription.validate(subscription)

	def test_platform_data_has_no_revenue_total_or_payment_fabrication(self):
		frappe.session.user = "platform.admin@example.test"
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(frappe, "get_all", side_effect=[[{"name": "Basic"}], []]),
		):
			result = subscriptions.get_platform_subscription_data()
		self.assertEqual(result["plans"], [{"name": "Basic"}])
		self.assertEqual(result["subscriptions"], [])
		self.assertNotIn("revenue", result)
		self.assertNotIn("collected", result)
		self.assertIn("no collected revenue is reported", result["payment_notice"])

	def test_platform_subscription_list_is_filtered_and_page_bounded(self):
		frappe.session.user = "platform.admin@example.test"
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(frappe, "get_all", side_effect=[[{"name": "Basic"}], [{"name": "SUB-1", "garage": "Garage A", "plan": "Basic"} ]]) as get_all,
			patch.object(frappe.db, "count", return_value=31) as count,
		):
			result = subscriptions.get_platform_subscription_data(status="Pending", start=20, page_length=200)
		self.assertEqual((result["subscription_total"], result["subscription_start"], result["subscription_page_length"]), (31, 20, 100))
		self.assertEqual(result["subscriptions"][0]["name"], "SUB-1")
		self.assertEqual(get_all.call_args_list[1].kwargs["filters"], {"status": "Pending"})
		self.assertEqual(get_all.call_args_list[1].kwargs["start"], 20)
		self.assertEqual(get_all.call_args_list[1].kwargs["page_length"], 100)
		count.assert_called_once_with("BG Garage Subscription", {"status": "Pending"})

	def test_platform_subscription_search_validation(self):
		frappe.session.user = "platform.admin@example.test"
		with patch.object(tenancy, "is_platform_super_admin", return_value=True), patch.object(frappe, "get_all") as get_all:
			for call in (
				lambda: subscriptions.get_platform_subscription_data(status="System Manager"),
				lambda: subscriptions.get_platform_subscription_data(start=-1),
				lambda: subscriptions.get_platform_subscription_data(query="x" * 101),
			):
				with self.subTest(call=call), self.assertRaises(frappe.ValidationError):
					call()
		get_all.assert_not_called()

	def test_explicit_platform_admin_can_create_a_plan(self):
		frappe.session.user = "platform.admin@example.test"
		plan = SimpleNamespace(
			name="Basic",
			status=None,
			is_new=lambda: True,
			insert=lambda ignore_permissions=False: None,
		)
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe.db, "get_value", return_value=None),
			patch.object(frappe, "get_doc", return_value=plan),
		):
			result = subscriptions.save_subscription_plan("Basic", "Monthly", 10, "INR")
		self.assertEqual(result, {"name": "Basic", "status": "Active"})

	def test_active_subscription_remains_valid_if_plan_is_later_retired(self):
		subscription = self._subscription(
			status="Active",
			new=False,
			before=SimpleNamespace(status="Active", garage="GARAGE-A"),
		)
		with (
			patch.object(frappe.db, "exists", side_effect=[True, True, False]),
			patch.object(frappe.db, "get_value", side_effect=["Inactive", "Active"]),
		):
			BGGarageSubscription.validate(subscription)
		self.assertEqual(subscription.active_garage, "GARAGE-A")


if __name__ == "__main__":
	unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import payments, tenancy
from bike_garage.bike_garage.api import dashboard


class TestDashboardGarageScope(unittest.TestCase):
	def setUp(self):
		self.session_patch = patch.object(
			frappe, "session", SimpleNamespace(user="garage.user@example.test")
		)
		self.session_patch.start()
		self.addCleanup(self.session_patch.stop)
		self.platform_patch = patch.object(tenancy, "is_platform_super_admin", return_value=False)
		self.is_platform_admin = self.platform_patch.start()
		self.addCleanup(self.platform_patch.stop)
		self.payment_access_patch = patch.object(payments, "can_read_payment_data", return_value=True)
		self.payment_access = self.payment_access_patch.start()
		self.addCleanup(self.payment_access_patch.stop)
		self.garage_patch = patch.object(tenancy, "get_current_garage", return_value="GARAGE-A")
		self.get_current_garage = self.garage_patch.start()
		self.addCleanup(self.garage_patch.stop)
		self.count_patch = patch.object(frappe.db, "count", return_value=3)
		self.count = self.count_patch.start()
		self.addCleanup(self.count_patch.stop)
		self.sql_patch = patch.object(frappe.db, "sql", side_effect=self.fake_sql)
		self.sql = self.sql_patch.start()
		self.addCleanup(self.sql_patch.stop)
		self.table_exists_patch = patch.object(frappe.db, "table_exists", return_value=True)
		self.table_exists_patch.start()
		self.addCleanup(self.table_exists_patch.stop)
		self.today_patch = patch.object(frappe.utils, "today", return_value="2026-10-13")
		self.today_patch.start()
		self.addCleanup(self.today_patch.stop)
		self.first_day_patch = patch.object(
			frappe.utils, "get_first_day", return_value="2026-10-01"
		)
		self.first_day_patch.start()
		self.addCleanup(self.first_day_patch.stop)

	@staticmethod
	def fake_sql(query, values=(), **kwargs):
		if "SELECT creation, amount, payment_mode" in query:
			return []
		if kwargs.get("as_dict"):
			return []
		return [(0,)]

	def call_all_methods(self):
		return (
			dashboard.get_dashboard_stats(),
			dashboard.get_monthly_revenue(),
			dashboard.get_profit_loss(),
		)

	def test_two_garages_use_only_the_session_resolved_scope(self):
		for garage in ("GARAGE-A", "GARAGE-B"):
			with self.subTest(garage=garage):
				self.get_current_garage.return_value = garage
				self.count.reset_mock()
				self.sql.reset_mock()
				self.call_all_methods()

				self.assertEqual(self.count.call_count, 3)
				for call in self.count.call_args_list:
					self.assertEqual(call.args[1]["garage"], garage)

				self.assertEqual(self.sql.call_count, 7)
				for call in self.sql.call_args_list:
					query, values = call.args
					self.assertIn("`garage` = %s", query)
					self.assertIn(garage, values)

	def test_missing_membership_denies_all_dashboard_methods_without_queries(self):
		self.get_current_garage.side_effect = frappe.PermissionError("No active garage")
		for method in (
			dashboard.get_dashboard_stats,
			dashboard.get_monthly_revenue,
			dashboard.get_profit_loss,
		):
			with self.subTest(method=method.__name__):
				with self.assertRaises(frappe.PermissionError):
					method()
		self.count.assert_not_called()
		self.sql.assert_not_called()

	def test_platform_role_lookup_failure_denies_all_methods_without_queries(self):
		self.is_platform_admin.side_effect = frappe.PermissionError("Role lookup failed")
		for method in (
			dashboard.get_dashboard_stats,
			dashboard.get_monthly_revenue,
			dashboard.get_profit_loss,
		):
			with self.subTest(method=method.__name__):
				self.count.reset_mock()
				self.sql.reset_mock()
				with self.assertRaises(frappe.PermissionError):
					method()
				self.is_platform_admin.assert_called_once_with()
				self.count.assert_not_called()
				self.sql.assert_not_called()
				self.is_platform_admin.reset_mock()

	def test_platform_admin_uses_explicit_global_path(self):
		self.is_platform_admin.return_value = True
		self.call_all_methods()
		self.get_current_garage.assert_not_called()

		for call in self.count.call_args_list:
			self.assertNotIn("garage", call.args[1])
		for call in self.sql.call_args_list:
			query, values = call.args
			self.assertIn("1=1", query)
			self.assertNotIn("GARAGE-A", values)
			self.assertNotIn("GARAGE-B", values)


if __name__ == "__main__":
	unittest.main()

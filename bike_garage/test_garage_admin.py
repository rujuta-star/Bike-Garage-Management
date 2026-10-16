import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import tenancy
from bike_garage.www import garage_admin


class TestGarageAdminPage(unittest.TestCase):
	def test_guest_is_denied_before_membership_or_garage_reads(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="Guest")),
			patch.object(tenancy, "get_current_garage") as resolve_garage,
			self.assertRaises(frappe.PermissionError),
		):
			garage_admin.get_context(SimpleNamespace())
		resolve_garage.assert_not_called()

	def test_platform_admin_cannot_enter_the_garage_admin_route(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="platform@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(tenancy, "get_current_garage") as resolve_garage,
			self.assertRaises(frappe.PermissionError),
		):
			garage_admin.get_context(SimpleNamespace())
		resolve_garage.assert_not_called()

	def test_owner_membership_is_denied_from_manager_dashboard(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="owner@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=False),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-A"),
			patch.object(frappe.db, "get_value", return_value="Owner"),
			self.assertRaises(frappe.PermissionError),
		):
			garage_admin.get_context(SimpleNamespace())

	def test_authorized_manager_route_redirects_to_main_garage_workspace(self):
		garage_doc = SimpleNamespace(status="Active", garage_name="Workshop A")
		flags = SimpleNamespace()
		with (
			patch.object(frappe, "session", SimpleNamespace(user="manager@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=False),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-A") as resolve_garage,
			patch.object(frappe.db, "get_value", return_value="Manager") as get_membership,
			patch.object(frappe, "get_doc", return_value=garage_doc) as get_doc,
			patch.object(frappe.local, "flags", flags, create=True),
			self.assertRaises(frappe.Redirect),
		):
			garage_admin.get_context(SimpleNamespace())

		resolve_garage.assert_called_once_with()
		get_membership.assert_called_once_with(
			"BG Garage Membership",
			{"user": "manager@example.test", "garage": "GARAGE-A", "status": "Active"},
			"membership_type",
		)
		get_doc.assert_called_once_with("BG Garage", "GARAGE-A")
		self.assertEqual(flags.redirect_location, "/garage")

	def test_manager_dashboard_exposes_only_supported_sections(self):
		template = (Path(__file__).parent / "www" / "garage_admin.html").read_text()
		self.assertIn('data-panel="customers"', template)
		self.assertIn('data-panel="vehicles"', template)
		self.assertIn('data-panel="jobs"', template)
		self.assertIn('data-panel="parts"', template)
		self.assertIn("get_dashboard_stats", template)
		self.assertIn("get_monthly_revenue", template)
		self.assertIn("get_job_card_part_report", template)
		self.assertIn("Garage membership changes and Frappe role assignments are not available", template)
		self.assertIn("No Manager-safe garage settings API is currently available", template)
		self.assertNotIn("Platform Super Admin</option>", template)


if __name__ == "__main__":
	unittest.main()

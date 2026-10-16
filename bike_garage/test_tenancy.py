import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import tenancy


class TestGarageMembershipResolver(unittest.TestCase):
	def setUp(self):
		self.user = "garage.user@example.test"
		self.session_patch = patch.object(frappe, "session", SimpleNamespace(user=self.user))
		self.session_patch.start()
		self.addCleanup(self.session_patch.stop)
		self.memberships = [
			{"user": self.user, "status": "Active", "garage": "GARAGE-001"}
		]
		self.garage_status = "Active"
		self.get_all_patch = patch.object(frappe, "get_all", side_effect=self.get_all)
		self.get_all_patch.start()
		self.addCleanup(self.get_all_patch.stop)
		self.garage_status_patch = patch.object(
			frappe.db, "get_value", side_effect=self.get_garage_status
		)
		self.garage_status_patch.start()
		self.addCleanup(self.garage_status_patch.stop)
		self.roles_patch = patch.object(frappe, "get_roles", return_value=[])
		self.roles_patch.start()
		self.addCleanup(self.roles_patch.stop)

	def get_all(self, doctype, **kwargs):
		self.assertEqual(doctype, "BG Garage Membership")
		self.assertEqual(kwargs["filters"], {"user": self.user, "status": "Active"})
		self.assertEqual(kwargs["fields"], ["garage"])
		self.assertEqual(kwargs["limit_page_length"], 2)
		filters = kwargs["filters"]
		matching_memberships = [
			membership
			for membership in self.memberships
			if all(membership.get(fieldname) == value for fieldname, value in filters.items())
		]
		return [{"garage": membership.get("garage")} for membership in matching_memberships]

	def get_garage_status(self, doctype, name, fieldname):
		self.assertEqual((doctype, name, fieldname), ("BG Garage", "GARAGE-001", "status"))
		return self.garage_status

	def test_active_membership_and_active_garage(self):
		self.assertEqual(tenancy.get_current_garage(), "GARAGE-001")

	def test_guest_user_is_denied(self):
		frappe.session.user = "Guest"
		with self.assertRaises(frappe.PermissionError):
			tenancy.get_current_garage()

	def test_missing_membership_is_denied(self):
		self.memberships = []
		with self.assertRaises(frappe.PermissionError):
			tenancy.get_current_garage()

	def test_pending_or_suspended_membership_is_not_resolved(self):
		for status in ("Pending", "Suspended"):
			with self.subTest(status=status):
				self.memberships = [
					{"user": self.user, "status": status, "garage": "GARAGE-001"}
				]
				with self.assertRaises(frappe.PermissionError):
					tenancy.get_current_garage()

	def test_inactive_garage_is_denied(self):
		self.garage_status = "Suspended"
		with self.assertRaises(frappe.PermissionError):
			tenancy.get_current_garage()

	def test_multiple_active_memberships_are_denied(self):
		self.memberships = [
			{"user": self.user, "status": "Active", "garage": "GARAGE-001"},
			{"user": self.user, "status": "Active", "garage": "GARAGE-002"},
		]
		with self.assertRaises(frappe.PermissionError):
			tenancy.get_current_garage()

	def test_client_supplied_garage_id_cannot_select_context(self):
		with self.assertRaises(TypeError):
			tenancy.get_current_garage("GARAGE-FORGED")

	def test_platform_super_admin_is_explicit_and_has_no_membership_bypass(self):
		with patch.object(frappe, "get_roles", return_value=[tenancy.PLATFORM_SUPER_ADMIN_ROLE]):
			self.assertTrue(tenancy.is_platform_super_admin(self.user))
			self.memberships = []
			with self.assertRaises(frappe.PermissionError):
				tenancy.get_current_garage()

	def test_role_lookup_failure_is_denied(self):
		with patch.object(frappe, "get_roles", side_effect=RuntimeError("role lookup failed")):
			with self.assertRaises(frappe.PermissionError):
				tenancy.get_current_garage()

	def test_membership_lookup_failure_is_denied(self):
		with patch.object(frappe, "get_all", side_effect=RuntimeError("membership lookup failed")):
			with self.assertRaises(frappe.PermissionError):
				tenancy.get_current_garage()

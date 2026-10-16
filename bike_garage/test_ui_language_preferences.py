import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage.bike_garage.api import preferences


class TestDashboardLanguagePreference(unittest.TestCase):
	def setUp(self):
		self.language_exists = patch.object(frappe.db, "exists", return_value=True)
		self.language_exists.start()
		self.addCleanup(self.language_exists.stop)

	def test_guest_preference_uses_frappe_preferred_language_cookie(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="Guest")),
			patch.object(frappe.local, "cookie_manager", create=True) as cookies,
		):
			result = preferences.set_dashboard_language("mr")

		self.assertEqual(result, {"language": "mr"})
		cookies.set_cookie.assert_called_once_with("preferred_language", "mr")

	def test_authenticated_preference_updates_only_the_session_user(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="garage.user@example.test")),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(preferences, "clear_document_cache") as clear_cache,
		):
			result = preferences.set_dashboard_language("hi")

		self.assertEqual(result, {"language": "hi"})
		set_value.assert_called_once_with(
			"User", "garage.user@example.test", "language", "hi", update_modified=False
		)
		clear_cache.assert_called_once_with("User", "garage.user@example.test")

	def test_unsupported_language_is_rejected(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="garage.user@example.test")),
			patch.object(frappe.db, "set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			preferences.set_dashboard_language("fr")

		set_value.assert_not_called()

	def test_supported_dashboard_language_does_not_require_global_language_enablement(self):
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "session", SimpleNamespace(user="garage.user@example.test")),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(preferences, "clear_document_cache") as clear_cache,
		):
			result = preferences.set_dashboard_language("mr")

		self.assertEqual(result, {"language": "mr"})
		set_value.assert_called_once_with(
			"User", "garage.user@example.test", "language", "mr", update_modified=False
		)
		clear_cache.assert_called_once_with("User", "garage.user@example.test")

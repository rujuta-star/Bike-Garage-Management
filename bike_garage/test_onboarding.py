import unittest
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.auth import LoginManager
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client

from bike_garage import tenancy
from bike_garage.bike_garage.api import onboarding
from bike_garage.install import ensure_platform_super_admin_role
from bike_garage.www import register
from bike_garage import website
from bike_garage.website import get_home_page


class FakeDocument(SimpleNamespace):
	def __init__(self, values):
		values = dict(values) if isinstance(values, dict) else {"doctype": values}
		self.doctype = values.get("doctype")
		self.name = values.get("name") or values.get("email") or values.get("garage_id") or "MEMBERSHIP-1"
		for key, value in values.items():
			setattr(self, key, value)
		self.saved = False
		self.inserted = False
		self.locked = False
		self.reset_email_requested = False
		self.registration_completed_on = values.get("registration_completed_on")
		self.owner_user = values.get("owner_user")

	def insert(self, **kwargs):
		self.inserted = True

	def save(self, **kwargs):
		self.saved = True

	def reload(self):
		return self

	def lock(self, **kwargs):
		self.locked = True

	def unlock(self):
		self.locked = False

	def validate_reset_password(self):
		self.reset_password_validated = True

	def _reset_password(self, send_email=False):
		self.reset_email_requested = send_email
		self.reset_link_generated = True
		return "/update-password?key=synthetic-test-key"

	def send_login_mail(self, subject, template, args, now=None, custom_template=None):
		self.login_mail = {
			"subject": subject,
			"template": template,
			"args": args,
			"now": now,
			"custom_template": custom_template,
		}


class TestGarageOnboarding(unittest.TestCase):
	def setUp(self):
		self.session_patch = patch.object(frappe, "session", SimpleNamespace(user="Guest"))
		self.session_patch.start()
		self.addCleanup(self.session_patch.stop)

	def test_public_landing_is_home_for_guests_and_website_users(self):
		self.assertEqual(get_home_page("Guest"), "index")
		with patch.object(frappe, "get_cached_value", return_value="Website User"):
			self.assertEqual(get_home_page("garage.user@example.test"), "index")
		with patch.object(frappe, "get_cached_value", return_value="System User"):
			self.assertIsNone(get_home_page("desk.user@example.test"))

	def test_root_path_resolver_is_public_for_get_and_head_and_preserves_other_routes(self):
		for method in ("GET", "HEAD"):
			with patch.object(
				frappe.local, "request", SimpleNamespace(path="/", method=method), create=True
			):
				self.assertEqual(website.resolve_website_path(""), "index")

		with (
			patch.object(frappe.local, "request", SimpleNamespace(path="/garage", method="GET"), create=True),
			patch("frappe.website.path_resolver.resolve_path", return_value="garage") as resolve_path,
		):
			self.assertEqual(website.resolve_website_path("garage"), "garage")
			resolve_path.assert_called_once_with("garage")

	def test_login_home_page_routes_explicit_platform_admin_before_user_type_fallback(self):
		with (
			patch.object(frappe.local, "request", SimpleNamespace(path="/api/method/login"), create=True),
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
		):
			self.assertEqual(get_home_page("admin@example.test"), "platform_admin")

	def test_dashboard_destination_requires_explicit_role_or_one_active_garage(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="platform@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
		):
			self.assertEqual(website.get_dashboard_route(), "/platform_admin")

		with (
			patch.object(frappe, "session", SimpleNamespace(user="owner@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=False),
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-A"),
			patch.object(frappe.db, "get_value", return_value="Owner"),
		):
			self.assertEqual(website.get_dashboard_route(), "/garage")

		with (
			patch.object(frappe, "session", SimpleNamespace(user="manager@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=False),
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-A"),
			patch.object(frappe.db, "get_value", return_value="Manager"),
		):
			self.assertEqual(website.get_dashboard_route(), "/garage")

		with (
			patch.object(frappe, "session", SimpleNamespace(user="pending@example.test")),
			patch.object(tenancy, "is_platform_super_admin", return_value=False),
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(tenancy, "get_current_garage", side_effect=frappe.PermissionError),
		):
			self.assertIsNone(website.get_dashboard_route())

	def test_frappe_logout_invalidates_session_and_guest_cannot_resolve_garage(self):
		with (
			patch.object(frappe.local, "request", SimpleNamespace(path="/api/method/logout"), create=True),
			patch.object(frappe, "session", SimpleNamespace(user="owner@example.test", sid="disposable-sid")),
		):
			manager = object.__new__(LoginManager)
			with (
				patch.object(LoginManager, "run_trigger"),
				patch.object(LoginManager, "login_as_guest") as login_as_guest,
				patch.object(LoginManager, "clear_cookies"),
				patch("frappe.auth.delete_session") as delete_session,
			):
				manager.logout()

		delete_session.assert_called_once_with(
			"disposable-sid", user="owner@example.test", reason="User Manually Logged Out"
		)
		login_as_guest.assert_called_once_with()
		with (
			patch.object(frappe, "session", SimpleNamespace(user="Guest")),
			self.assertRaises(frappe.PermissionError),
		):
			tenancy.get_current_garage()

	def test_login_home_page_uses_only_a_verified_active_garage(self):
		with (
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(frappe.local, "request", SimpleNamespace(path="/api/method/login"), create=True),
			patch.object(frappe, "get_all", return_value=[{"garage": "GARAGE-1", "membership_type": "Owner"}]),
			patch.object(frappe.db, "get_value", return_value="Active"),
		):
			self.assertEqual(get_home_page("owner@example.test"), "garage")

		with (
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(frappe.local, "request", SimpleNamespace(path="/api/method/login"), create=True),
			patch.object(frappe, "get_all", return_value=[{"garage": "GARAGE-1", "membership_type": "Manager"}]),
			patch.object(frappe.db, "get_value", side_effect=["Active", "Manager"]),
		):
			self.assertEqual(get_home_page("manager@example.test"), "garage")

		with (
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(frappe.local, "request", SimpleNamespace(path="/api/method/login"), create=True),
			patch.object(frappe, "get_all", return_value=[{"garage": "GARAGE-1", "membership_type": "Owner"}]),
			patch.object(frappe.db, "get_value", return_value="Pending"),
		):
			self.assertEqual(get_home_page("pending@example.test"), "index")

	def test_guest_request_creates_only_a_pending_application(self):
		created = []
		def make_doc(values, *args):
			doc = FakeDocument(values if isinstance(values, dict) else {"doctype": values, "name": args[0]})
			created.append(doc)
			return doc

		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(onboarding, "_registration_lock", return_value=nullcontext()),
			patch.object(frappe, "get_doc", side_effect=make_doc),
			patch.object(frappe, "generate_hash", return_value="a1b2c3"),
		):
			result = onboarding.submit_garage_registration(
				"  Garage A  ", " Owner A ", "OWNER@example.test ", " 123 456 ", city="Patur"
			)

		self.assertEqual(len(created), 1)
		garage = created[0]
		self.assertEqual((garage.status, garage.garage_name, garage.email), ("Pending", "Garage A", "owner@example.test"))
		self.assertEqual(result["message"], onboarding.REGISTRATION_ACKNOWLEDGEMENT)
		self.assertNotIn("password", result)
		self.assertNotIn("User", [doc.doctype for doc in created])
		self.assertNotIn("BG Garage Membership", [doc.doctype for doc in created])

	def test_duplicate_registration_is_generic_and_creates_no_records(self):
		with (
			patch.object(onboarding, "_registration_already_exists", return_value=True),
			patch.object(onboarding, "_registration_lock", return_value=nullcontext()),
			patch.object(frappe, "get_doc") as get_doc,
		):
			result = onboarding.submit_garage_registration(
				"Garage A", "Owner A", "owner@example.test", "123"
			)
		get_doc.assert_not_called()
		self.assertEqual(result["message"], onboarding.REGISTRATION_ACKNOWLEDGEMENT)

	def test_registration_lock_scopes_on_a_hash_of_the_email_and_releases(self):
		class Lock:
			acquired = False
			released = False
			def acquire(self, blocking=True):
				self.acquired = blocking
				return True
			def release(self):
				self.released = True

		lock = Lock()
		with patch.object(frappe.cache, "lock", return_value=lock) as make_lock:
			with onboarding._registration_lock("owner@example.test"):
				self.assertTrue(lock.acquired)
		self.assertTrue(lock.released)
		key = make_lock.call_args.args[0]
		self.assertNotIn("owner@example.test", key)
		self.assertIn(onboarding.hashlib.sha256(b"owner@example.test").hexdigest(), key)

	def test_registration_page_disables_caching_and_referrer_leakage(self):
		context = frappe._dict()
		headers = {}
		with (
			patch.object(register, "get_csrf_token", return_value="csrf-token"),
			patch.object(frappe.local, "response_headers", headers, create=True),
		):
			register.get_context(context)
		self.assertEqual(context["csrf_token"], "csrf-token")
		self.assertEqual(headers["Referrer-Policy"], "no-referrer")
		self.assertEqual(headers["Cache-Control"], "no-store")

	def test_registration_completion_activates_exactly_one_user_garage_and_owner_membership(self):
		from datetime import datetime

		now = datetime(2026, 10, 14, 12, 0, 0)
		token = "a" * 48
		garage = FakeDocument({
			"doctype": "BG Garage", "name": "G-APPROVED", "status": "Approved",
			"email": "owner@example.test", "owner_name": "Owner A", "garage_name": "Garage A",
			"application_token_hash": onboarding._registration_token_hash(token),
			"application_token_expires_on": now + timedelta(hours=1),
		})
		created = []
		def make_doc(values, *args, **kwargs):
			doc = FakeDocument(values)
			created.append(doc)
			return doc
		with (
			patch.object(frappe.db, "get_value", side_effect=lambda doctype, *args, **kwargs: "G-APPROVED" if doctype == "BG Garage" else None),
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_all", return_value=[]),
			patch.object(frappe, "get_doc", side_effect=[garage, make_doc({"doctype": "User", "email": "owner@example.test", "enabled": 1, "new_password": "SafePassword-42!"}), make_doc({"doctype": "BG Garage Membership", "garage": "G-APPROVED", "status": "Active", "membership_type": "Owner"})]),
			patch.object(onboarding, "now_datetime", return_value=now),
		):
			result = onboarding.complete_garage_registration(token, "SafePassword-42!", "SafePassword-42!")
		self.assertEqual(result["login_url"], "/login")
		self.assertEqual([doc.doctype for doc in created], ["User", "BG Garage Membership"])
		self.assertEqual(created[0].new_password, "SafePassword-42!")
		self.assertEqual((created[1].status, created[1].membership_type, created[1].garage), ("Active", "Owner", "G-APPROVED"))
		self.assertEqual(garage.status, "Active")
		self.assertFalse(garage.application_token_hash)
		self.assertEqual(garage.registration_completed_on, now)

	def test_registration_completion_rejects_pending_application_and_password_mismatch(self):
		token = "b" * 48
		for status in ("Pending", "Rejected"):
			garage = FakeDocument({
				"doctype": "BG Garage", "name": f"G-{status.upper()}", "status": status,
				"application_token_hash": onboarding._registration_token_hash(token),
				"application_token_expires_on": frappe.utils.now_datetime() + timedelta(hours=1),
			})
			with (
				patch.object(frappe.db, "get_value", return_value=garage.name),
				patch.object(frappe, "get_doc", return_value=garage),
				patch.object(frappe.db, "exists") as exists,
			):
				with self.assertRaises(frappe.ValidationError):
					onboarding.complete_garage_registration(token, "SafePassword-42!", "SafePassword-42!")
				exists.assert_not_called()
		with self.assertRaises(frappe.ValidationError):
			onboarding.complete_garage_registration(token, "SafePassword-42!", "different-password")

	def test_registration_completion_rejects_expired_approval_token(self):
		token = "d" * 48
		garage = FakeDocument({
			"doctype": "BG Garage", "name": "G-EXPIRED", "status": "Approved",
			"application_token_hash": onboarding._registration_token_hash(token),
			"application_token_expires_on": frappe.utils.add_to_date(
				frappe.utils.now_datetime(), hours=-1
			),
		})
		with (
			patch.object(frappe.db, "get_value", return_value=garage.name),
			patch.object(frappe, "get_doc", return_value=garage),
			patch.object(frappe.db, "exists") as exists,
		):
			with self.assertRaises(frappe.ValidationError):
				onboarding.complete_garage_registration(token, "SafePassword-42!", "SafePassword-42!")
			exists.assert_not_called()

	def test_approved_legacy_request_activates_only_its_matching_disabled_owner(self):
		from datetime import datetime

		now = datetime(2026, 10, 14, 12, 0, 0)
		token = "c" * 48
		garage = FakeDocument({
			"doctype": "BG Garage", "name": "G-LEGACY", "status": "Approved",
			"email": "legacy@example.test", "application_token_hash": onboarding._registration_token_hash(token),
			"application_token_expires_on": now + timedelta(hours=1),
		})
		user = FakeDocument({"doctype": "User", "name": "legacy@example.test", "enabled": 0, "user_type": "Website User"})
		membership = FakeDocument({"doctype": "BG Garage Membership", "name": "M-LEGACY", "user": user.name, "garage": garage.name, "status": "Pending", "membership_type": "Owner"})
		with (
			patch.object(frappe.db, "get_value", side_effect=[garage.name, user.name]),
			patch.object(frappe, "get_all", side_effect=[[{"name": membership.name, "user": user.name}], [frappe._dict(name=membership.name, garage=garage.name, status="Pending")]]),
			patch.object(frappe, "get_doc", side_effect=[garage, user, membership]),
			patch.object(onboarding, "now_datetime", return_value=now),
		):
			onboarding.complete_garage_registration(token, "SafePassword-42!", "SafePassword-42!")
		self.assertTrue(user.enabled)
		self.assertEqual(user.new_password, "SafePassword-42!")
		self.assertEqual(membership.status, "Active")
		self.assertEqual(garage.status, "Active")

	def test_invalid_email_is_rejected_before_account_creation(self):
		with patch.object(frappe, "get_doc") as get_doc:
			with self.assertRaises(frappe.ValidationError):
				onboarding.submit_garage_registration("Garage A", "Owner A", "bad email", "123")
		get_doc.assert_not_called()

	def test_missing_required_fields_are_rejected_before_account_creation(self):
		with patch.object(frappe, "get_doc") as get_doc:
			with self.assertRaises(frappe.ValidationError):
				onboarding.submit_garage_registration()
		get_doc.assert_not_called()

	def test_signed_in_user_cannot_use_public_registration(self):
		frappe.session.user = "garage.user@example.test"
		with patch.object(frappe, "get_doc") as get_doc:
			with self.assertRaises(frappe.PermissionError):
				onboarding.submit_garage_registration("Garage A", "Owner A", "owner@example.test", "123")
		get_doc.assert_not_called()


class TestPlatformAdministration(unittest.TestCase):
	def setUp(self):
		self.session_patch = patch.object(
			frappe, "session", SimpleNamespace(user="garage.user@example.test")
		)
		self.session_patch.start()
		self.addCleanup(self.session_patch.stop)
		self.admin_patch = patch.object(tenancy, "is_platform_super_admin", return_value=False)
		self.is_platform_admin = self.admin_patch.start()
		self.addCleanup(self.admin_patch.stop)

	def test_unauthorized_actions_and_platform_data_are_denied_before_queries(self):
		with (
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe, "get_all") as get_all,
			patch.object(frappe.db, "count") as count,
			patch.object(frappe.db, "get_value") as get_value,
		):
			calls = (
				lambda: onboarding.get_platform_dashboard(),
				lambda: onboarding.get_platform_garages(query="secret@example.test"),
				lambda: onboarding.get_platform_memberships(query="user@example.test"),
				lambda: onboarding.approve_garage_application("G-1"),
				lambda: onboarding.resend_garage_registration_link("G-1"),
				lambda: onboarding.reject_garage_application("G-1"),
				lambda: onboarding.set_garage_status("G-1", "Suspended"),
				lambda: onboarding.update_garage_membership("M-1", status="Active"),
				lambda: onboarding.add_garage_membership("user@example.test", "G-1", "Owner"),
			)
			for call in calls:
				with self.subTest(call=call):
					with self.assertRaises(frappe.PermissionError):
						call()
		get_doc.assert_not_called()
		get_all.assert_not_called()
		count.assert_not_called()
		get_value.assert_not_called()

	def test_approval_keeps_garage_pending_registration_and_queues_one_time_link(self):
		frappe.session.user = "platform.admin@example.test"
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Pending", "email": "owner@example.test"})
		with (
			patch.object(frappe, "get_doc", return_value=garage) as get_doc,
			patch.object(onboarding, "_queue_registration_email", return_value="queued_not_delivery_verified") as send,
			patch.object(onboarding.secrets, "token_urlsafe", return_value="x" * 48),
		):
			result = onboarding.approve_garage_application("G-1")
		self.assertEqual(garage.status, "Approved")
		self.assertEqual(result, {"status": "Approved", "registration_email_status": "queued_not_delivery_verified"})
		self.assertEqual(garage.application_token_hash, onboarding._registration_token_hash("x" * 48))
		self.assertEqual(garage.application_decision_by, frappe.session.user)
		self.assertIsNotNone(garage.application_decision_on)
		self.assertEqual(send.call_count, 1)
		get_doc.assert_called_once_with("BG Garage", "G-1", for_update=True)

	def test_approval_without_email_configuration_still_records_approved_state(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Pending", "email": "owner@example.test"})
		with (
			patch.object(frappe, "get_doc", return_value=garage),
			patch.object(onboarding, "_queue_registration_email", return_value="not_configured"),
		):
			result = onboarding.approve_garage_application("G-1")
		self.assertEqual(garage.status, "Approved")
		self.assertEqual(result["registration_email_status"], "not_configured")

	def test_authorized_dashboard_returns_real_counts_without_subscription_totals(self):
		self.is_platform_admin.return_value = True
		active_garages = [{"name": "G-1", "garage_name": "Garage One"}]
		with (
			patch.object(frappe.db, "count", side_effect=[2, 1, 0, 1, 0, 0, 0, 3, 1]) as count,
			patch.object(frappe, "get_all", return_value=active_garages) as get_all,
		):
			result = onboarding.get_platform_dashboard()
		self.assertEqual(result["counts"], {
			"garages": 2,
			"pending_garages": 1,
			"approved_garages": 0,
			"active_garages": 1,
			"suspended_garages": 0,
			"rejected_garages": 0,
			"closed_garages": 0,
			"memberships": 3,
			"pending_memberships": 1,
		})
		self.assertNotIn("subscription_revenue", result)
		self.assertEqual(result["active_garages"], active_garages)
		self.assertEqual(count.call_count, 9)
		get_all.assert_called_once_with("BG Garage", filters={"status": "Active"}, fields=["name", "garage_id", "garage_name"], order_by="garage_name asc", limit_page_length=0)

	def test_platform_lists_apply_search_filters_and_bounded_server_pagination(self):
		self.is_platform_admin.return_value = True
		garage_row = {"name": "G-1", "garage_name": "North Garage", "status": "Active"}
		member_row = {"name": "M-1", "user": "owner@example.test", "garage": "G-1", "status": "Active", "membership_type": "Owner"}
		with (
			patch.object(frappe, "get_all", side_effect=[[garage_row], [garage_row], [member_row], [member_row]]) as get_all,
			patch.object(frappe.db, "count") as count,
		):
			garages = onboarding.get_platform_garages("north", "Active", 20, 200)
			memberships = onboarding.get_platform_memberships("owner@example.test", "Active", "Owner", 0, 20)
		self.assertEqual((garages["total"], garages["page_length"], garages["rows"]), (1, 100, [garage_row]))
		self.assertEqual((memberships["total"], memberships["rows"]), (1, [member_row]))
		self.assertEqual(get_all.call_args_list[0].kwargs["start"], 20)
		self.assertEqual(get_all.call_args_list[0].kwargs["page_length"], 100)
		self.assertEqual(get_all.call_args_list[0].kwargs["filters"], {"status": "Active"})
		self.assertIn({"email": ["like", "%north%"]}, get_all.call_args_list[0].kwargs["or_filters"])
		self.assertEqual(get_all.call_args_list[2].kwargs["filters"], {"status": "Active", "membership_type": "Owner"})
		count.assert_not_called()

	def test_platform_list_rejects_invalid_status_paging_and_oversized_search(self):
		self.is_platform_admin.return_value = True
		for call in (
			lambda: onboarding.get_platform_garages(status="Administrator"),
			lambda: onboarding.get_platform_garages(start=-1),
			lambda: onboarding.get_platform_garages(page_length=0),
			lambda: onboarding.get_platform_memberships(membership_type="System Manager"),
			lambda: onboarding.get_platform_memberships(query="x" * 101),
		):
			with self.subTest(call=call), patch.object(frappe, "get_all") as get_all, self.assertRaises(frappe.ValidationError):
				call()
			get_all.assert_not_called()

	def test_rejection_uses_a_distinct_terminal_status(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Pending"})
		with (
			patch.object(frappe, "get_doc", return_value=garage),
			patch.object(frappe, "get_all", return_value=[]),
		):
			result = onboarding.reject_garage_application("G-1")
		self.assertEqual(garage.status, "Rejected")
		self.assertEqual(garage.application_decision_by, frappe.session.user)
		self.assertEqual(result["status"], "Rejected")

	def test_rejection_preserves_legacy_user_and_suspends_its_pending_membership(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-LEGACY", "email": "legacy@example.test", "status": "Pending"})
		user = FakeDocument({"doctype": "User", "name": "legacy@example.test", "enabled": 0, "user_type": "Website User"})
		membership = FakeDocument({"doctype": "BG Garage Membership", "name": "M-LEGACY", "user": user.name, "garage": garage.name, "status": "Pending", "membership_type": "Owner"})
		with (
			patch.object(frappe, "get_doc", side_effect=[garage, user, membership]),
			patch.object(frappe, "get_all", return_value=[{"name": membership.name, "user": user.name}]),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = onboarding.reject_garage_application(garage.name)
		self.assertEqual(result["status"], "Rejected")
		self.assertEqual(membership.status, "Suspended")
		self.assertTrue(membership.saved)
		self.assertFalse(user.enabled)
		delete_doc.assert_not_called()

	def test_rejection_keeps_legacy_user_that_has_another_garage_membership(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-LEGACY", "email": "legacy@example.test", "status": "Pending"})
		user = FakeDocument({"doctype": "User", "name": "legacy@example.test", "enabled": 0, "user_type": "Website User"})
		membership = FakeDocument({"doctype": "BG Garage Membership", "name": "M-LEGACY", "user": user.name, "garage": garage.name, "status": "Pending", "membership_type": "Owner"})
		with (
			patch.object(frappe, "get_doc", side_effect=[garage, user, membership]),
			patch.object(frappe, "get_all", side_effect=[[{"name": membership.name, "user": user.name}], [{"name": "M-OTHER"}]]),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = onboarding.reject_garage_application(garage.name)
		self.assertEqual(result["status"], "Rejected")
		self.assertEqual(membership.status, "Suspended")
		delete_doc.assert_not_called()

	def test_garage_and_membership_changes_use_allowlisted_values(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Active"})
		reactivated_garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Suspended"})
		membership = FakeDocument({"doctype": "BG Garage Membership", "name": "M-1", "user": "owner@example.test", "garage": "G-1", "status": "Pending", "membership_type": "Owner"})
		user = FakeDocument({"doctype": "User", "name": "owner@example.test", "enabled": 1})
		with (
			patch.object(
				frappe, "get_doc", side_effect=[garage, reactivated_garage, membership, user, membership]
			),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda doctype, *args, **kwargs: "Active" if doctype == "BG Garage" else None,
			),
		):
			onboarding.set_garage_status("G-1", "Suspended")
			onboarding.set_garage_status("G-1", "Active")
			onboarding.update_garage_membership("M-1", status="Active", membership_type="Manager")
		self.assertEqual(garage.status, "Suspended")
		self.assertEqual(reactivated_garage.status, "Active")
		self.assertEqual((membership.status, membership.membership_type), ("Active", "Manager"))
		with self.assertRaises(frappe.ValidationError):
			onboarding.update_garage_membership("M-1", membership_type="System Manager")

	def test_membership_activation_rejects_another_existing_active_membership(self):
		self.is_platform_admin.return_value = True
		membership = FakeDocument({
			"doctype": "BG Garage Membership", "name": "M-2", "user": "owner@example.test",
			"garage": "G-2", "status": "Pending", "membership_type": "Owner"
		})
		user = FakeDocument({"doctype": "User", "name": "owner@example.test", "enabled": 1})
		with (
			patch.object(frappe, "get_doc", side_effect=[membership, user, membership]),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=["Active", "M-1"],
			) as get_value,
		):
			with self.assertRaises(frappe.ValidationError):
				onboarding.update_garage_membership("M-2", status="Active")
		self.assertFalse(membership.saved)
		self.assertEqual(get_value.call_args.kwargs["for_update"], True)
		self.assertEqual(get_value.call_args.args[0], "BG Garage Membership")
		self.assertEqual(get_value.call_args.args[1], {
			"user": "owner@example.test", "status": "Active", "name": ["!=", "M-2"]
		})

	def test_activation_locks_user_row_before_locking_conflict_lookup(self):
		self.is_platform_admin.return_value = True
		membership = FakeDocument({
			"doctype": "BG Garage Membership", "name": "M-3", "user": "owner@example.test",
			"garage": "G-3", "status": "Pending", "membership_type": "Owner"
		})
		user = FakeDocument({"doctype": "User", "name": "owner@example.test", "enabled": 1})
		events = []

		def get_doc(doctype, name, **kwargs):
			events.append(("doc", doctype, kwargs.copy()))
			return membership if doctype == "BG Garage Membership" else user

		def get_value(doctype, *args, **kwargs):
			events.append(("value", doctype, kwargs.copy()))
			return "Active" if doctype == "BG Garage" else None

		with (
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe.db, "get_value", side_effect=get_value),
		):
			onboarding.update_garage_membership("M-3", status="Active")

		self.assertEqual(events[0], ("doc", "BG Garage Membership", {}))
		self.assertEqual(events[1], ("doc", "User", {"for_update": True}))
		self.assertEqual(events[2], ("doc", "BG Garage Membership", {"for_update": True}))
		self.assertEqual(events[3][0:2], ("value", "BG Garage"))
		self.assertEqual(events[4][0:2], ("value", "BG Garage Membership"))
		self.assertIs(events[4][2]["for_update"], True)
		self.assertTrue(membership.saved)

	def test_admin_can_resend_registration_only_for_approved_incomplete_application(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-4", "status": "Approved", "email": "owner@example.test"})
		with (
			patch.object(frappe, "get_doc", return_value=garage),
			patch.object(onboarding, "_queue_registration_email", return_value="not_configured"),
			patch.object(onboarding.secrets, "token_urlsafe", return_value="y" * 48),
		):
			result = onboarding.resend_garage_registration_link("G-4")
		self.assertEqual(result["registration_email_status"], "not_configured")
		self.assertEqual(garage.application_token_hash, onboarding._registration_token_hash("y" * 48))
		self.assertTrue(garage.saved)
		garage.status = "Pending"
		with patch.object(frappe, "get_doc", return_value=garage):
			with self.assertRaises(frappe.ValidationError):
				onboarding.resend_garage_registration_link("G-4")

	def test_authorized_admin_adds_only_a_pending_membership(self):
		self.is_platform_admin.return_value = True
		garage = FakeDocument({"doctype": "BG Garage", "name": "G-1", "status": "Active"})
		user = FakeDocument({"doctype": "User", "name": "staff@example.test", "enabled": 1})
		membership = FakeDocument({"doctype": "BG Garage Membership", "name": "M-2", "status": "Pending", "membership_type": "Technician"})
		with (
			patch.object(frappe, "get_doc", side_effect=[garage, user, membership]),
			patch.object(frappe, "get_all", return_value=[]),
		):
			result = onboarding.add_garage_membership("Staff@example.test", "G-1", "Technician")
		self.assertEqual(membership.status, "Pending")
		self.assertEqual(result["status"], "Pending")


class TestGarageRegistrationLifecycle(IntegrationTestCase):
	"""Exercise the request, admin decision, and one-time owner registration in Frappe."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=12).lower()
		self.email = f"onboarding-{self.token}@example.test"
		self.garage_name = None
		self.user_name = None

	def tearDown(self):
		frappe.set_user("Administrator")
		if self.garage_name:
			for row in frappe.get_all("BG Garage Membership", filters={"garage": self.garage_name}, fields=["name"]):
				frappe.delete_doc("BG Garage Membership", row.name, ignore_permissions=True, force=True)
		if self.user_name and frappe.db.exists("User", self.user_name):
			frappe.delete_doc("User", self.user_name, ignore_permissions=True, force=True)
		if self.garage_name and frappe.db.exists("BG Garage", self.garage_name):
			frappe.delete_doc("BG Garage", self.garage_name, ignore_permissions=True, force=True)
		super().tearDown()

	def test_pending_request_approval_and_registration_are_atomic_and_one_time(self):
		from contextlib import nullcontext

		frappe.set_user("Guest")
		with patch.object(onboarding, "_registration_lock", return_value=nullcontext()):
			ack = onboarding.submit_garage_registration(
				f"Lifecycle Garage {self.token}", "Lifecycle Owner", self.email, "9000000000", city="Pune"
			)
		self.assertIn("Pending review", ack["message"])
		self.garage_name = frappe.db.get_value("BG Garage", {"email": self.email}, "name")
		self.assertTrue(self.garage_name)
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Pending")
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(frappe.db.exists("BG Garage Membership", {"garage": self.garage_name}))

		frappe.set_user("Administrator")
		with patch.object(tenancy, "is_platform_super_admin", return_value=True):
			first_list = onboarding.get_platform_garages(query=self.email)
			refreshed_list = onboarding.get_platform_garages(query=self.email)
		self.assertEqual(first_list["total"], 1)
		self.assertEqual(refreshed_list["total"], 1)
		self.assertEqual(first_list["rows"][0]["name"], self.garage_name)
		self.assertEqual(refreshed_list["rows"][0]["status"], "Pending")

		with patch.object(onboarding, "_registration_lock", return_value=nullcontext()):
			frappe.set_user("Guest")
			onboarding.submit_garage_registration(
				f"Lifecycle Garage {self.token}", "Lifecycle Owner", self.email, "9000000000", city="Pune"
			)
		self.assertEqual(frappe.db.count("BG Garage", {"email": self.email}), 1)

		frappe.set_user("Administrator")
		registration_token = f"one-time-{self.token}-token-value"
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(onboarding, "_queue_registration_email", return_value="queued_not_delivery_verified") as queue_email,
			patch.object(onboarding.secrets, "token_urlsafe", return_value=registration_token),
		):
			approved = onboarding.approve_garage_application(self.garage_name)
		self.assertEqual(approved["status"], "Approved")
		self.assertEqual(queue_email.call_count, 1)
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(frappe.db.exists("BG Garage Membership", {"garage": self.garage_name}))

		frappe.set_user("Guest")
		with (
			patch("frappe.utils.global_search.sync_value_in_queue"),
			patch("frappe.request", None),
			patch("frappe.core.doctype.user.user.throttle_user_creation"),
		):
			complete = onboarding.complete_garage_registration(
				registration_token, "Lifecycle-Password-42!", "Lifecycle-Password-42!"
			)
		self.assertEqual(complete["login_url"], "/login")
		self.user_name = frappe.db.get_value("User", self.email, "name")
		self.assertTrue(self.user_name)
		self.assertEqual(frappe.db.get_value("User", self.user_name, "user_type"), "Website User")
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Active")
		self.assertEqual(frappe.db.count("BG Garage Membership", {"garage": self.garage_name, "user": self.user_name, "status": "Active", "membership_type": "Owner"}), 1)
		with (
			patch("frappe.request", None),
			patch("frappe.core.doctype.user.user.throttle_user_creation"),
			self.assertRaises(frappe.ValidationError),
		):
			onboarding.complete_garage_registration(
				registration_token, "Lifecycle-Password-42!", "Lifecycle-Password-42!"
			)

	def test_rejected_request_persists_and_cannot_complete_registration(self):
		from contextlib import nullcontext

		frappe.set_user("Guest")
		with patch.object(onboarding, "_registration_lock", return_value=nullcontext()):
			onboarding.submit_garage_registration(
				f"Rejected Lifecycle Garage {self.token}", "Lifecycle Owner", self.email, "9000000000"
			)
		self.garage_name = frappe.db.get_value("BG Garage", {"email": self.email}, "name")
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Pending")

		frappe.set_user("Administrator")
		with patch.object(tenancy, "is_platform_super_admin", return_value=True):
			result = onboarding.reject_garage_application(self.garage_name)
		self.assertEqual(result["status"], "Rejected")
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Rejected")
		self.assertFalse(frappe.db.get_value("BG Garage", self.garage_name, "application_token_hash"))

		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			onboarding.complete_garage_registration(
				f"rejected-{self.token}-registration-token", "Lifecycle-Password-42!", "Lifecycle-Password-42!"
			)
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Rejected")
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(frappe.db.exists("BG Garage Membership", {"garage": self.garage_name}))

	def test_expired_approved_token_is_rejected_without_activating_records(self):
		from contextlib import nullcontext

		frappe.set_user("Guest")
		with patch.object(onboarding, "_registration_lock", return_value=nullcontext()):
			onboarding.submit_garage_registration(
				f"Expired Lifecycle Garage {self.token}", "Lifecycle Owner", self.email, "9000000000"
			)
		self.garage_name = frappe.db.get_value("BG Garage", {"email": self.email}, "name")
		registration_token = f"expired-{self.token}-registration-token"

		frappe.set_user("Administrator")
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(onboarding, "_queue_registration_email", return_value="not_configured"),
			patch.object(onboarding.secrets, "token_urlsafe", return_value=registration_token),
		):
			approved = onboarding.approve_garage_application(self.garage_name)
		self.assertEqual(approved["status"], "Approved")
		self.assertEqual(approved["registration_email_status"], "not_configured")
		frappe.db.set_value(
			"BG Garage", self.garage_name, "application_token_expires_on", frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-1)
		)
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "registration_email_status"), "not_configured")

		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			onboarding.complete_garage_registration(
				registration_token, "Lifecycle-Password-42!", "Lifecycle-Password-42!"
			)
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Approved")
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(frappe.db.exists("BG Garage Membership", {"garage": self.garage_name}))

	def test_registration_route_is_no_store_and_does_not_refer_tokens(self):
		client = get_test_client()
		response = make_request(
			target=client.get,
			args=("/register?token=synthetic-registration-token",),
			kwargs={"headers": {"Host": frappe.local.site}},
			site=frappe.local.site,
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
		self.assertIn("no-store", response.headers.get("Cache-Control", ""))
		self.assertIn("Complete your owner registration", response.get_data(as_text=True))

	def test_registration_failure_rolls_back_user_before_membership_is_created(self):
		from contextlib import nullcontext
		from frappe.model.document import Document

		frappe.set_user("Guest")
		with patch.object(onboarding, "_registration_lock", return_value=nullcontext()):
			onboarding.submit_garage_registration(
				f"Failure Garage {self.token}", "Failure Owner", self.email, "9000000000"
			)
		self.garage_name = frappe.db.get_value("BG Garage", {"email": self.email}, "name")
		frappe.set_user("Administrator")
		registration_token = f"failure-{self.token}-one-time-token"
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(onboarding, "_queue_registration_email", return_value="queued_not_delivery_verified"),
			patch.object(onboarding.secrets, "token_urlsafe", return_value=registration_token),
		):
			onboarding.approve_garage_application(self.garage_name)

		savepoint = "bike_garage_registration_partial_failure"
		frappe.db.savepoint(savepoint)
		frappe.set_user("Guest")
		original_insert = Document.insert
		def fail_membership_insert(document, *args, **kwargs):
			if document.doctype == "BG Garage Membership":
				raise RuntimeError("synthetic membership insert failure")
			return original_insert(document, *args, **kwargs)
		try:
			with (
				patch.object(Document, "insert", fail_membership_insert),
				patch("frappe.utils.global_search.sync_value_in_queue"),
				patch("frappe.request", None),
				patch("frappe.core.doctype.user.user.throttle_user_creation"),
			):
				with self.assertRaises(RuntimeError):
					onboarding.complete_garage_registration(
						registration_token, "Lifecycle-Password-42!", "Lifecycle-Password-42!"
					)
		finally:
			frappe.db.rollback(save_point=savepoint)
		self.assertFalse(frappe.db.exists("User", self.email))
		self.assertFalse(frappe.db.exists("BG Garage Membership", {"garage": self.garage_name}))
		self.assertEqual(frappe.db.get_value("BG Garage", self.garage_name, "status"), "Approved")

	def test_builtin_administrator_is_not_an_implicit_platform_role(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="Administrator")),
			patch.object(frappe, "get_roles", return_value=[tenancy.PLATFORM_SUPER_ADMIN_ROLE]),
		):
			self.assertFalse(tenancy.is_platform_super_admin())

	def test_role_bootstrap_defines_role_without_assigning_it(self):
		role_doc = FakeDocument({"doctype": "Role", "role_name": tenancy.PLATFORM_SUPER_ADMIN_ROLE})
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_doc", return_value=role_doc) as get_doc,
		):
			ensure_platform_super_admin_role()
		get_doc.assert_called_once()
		self.assertEqual(role_doc.role_name, tenancy.PLATFORM_SUPER_ADMIN_ROLE)
		self.assertNotIn("user", role_doc.__dict__)
		self.assertTrue(role_doc.inserted)

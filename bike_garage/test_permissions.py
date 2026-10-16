import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import permissions, tenancy


class FakeGarageDocument:
	def __init__(self, doctype="BG Customer", garage=None, name=None, is_new=False, **values):
		self.doctype = doctype
		self.garage = garage
		self.name = name
		self._is_new = is_new
		self.__dict__.update(values)

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def is_new(self):
		return self._is_new


class TestGaragePermissions(unittest.TestCase):
	def setUp(self):
		self.user = "garage.user@example.test"
		self.garage = "GARAGE-001"
		self.session_patch = patch.object(frappe, "session", SimpleNamespace(user=self.user))
		self.session_patch.start()
		self.addCleanup(self.session_patch.stop)
		self.garage_patch = patch.object(tenancy, "get_current_garage", return_value=self.garage)
		self.get_current_garage = self.garage_patch.start()
		self.addCleanup(self.garage_patch.stop)
		self.roles_patch = patch.object(frappe, "get_roles", return_value=[])
		self.roles_patch.start()
		self.addCleanup(self.roles_patch.stop)
		self.has_column_patch = patch.object(frappe.db, "has_column", return_value=True)
		self.has_column = self.has_column_patch.start()
		self.addCleanup(self.has_column_patch.stop)
		self.meta_patch = patch.object(
			frappe,
			"get_meta",
			return_value=SimpleNamespace(
				get_field=lambda fieldname: SimpleNamespace(fieldtype="Link", options="BG Garage")
				if fieldname == "garage"
				else None
			),
		)
		self.meta_patch.start()
		self.addCleanup(self.meta_patch.stop)
		self.throw_patch = patch.object(frappe, "throw", side_effect=self.raise_permission_error)
		self.throw_patch.start()
		self.addCleanup(self.throw_patch.stop)

	@staticmethod
	def raise_permission_error(message, exc=None):
		raise (exc or frappe.ValidationError)(message)

	def test_legacy_garage_settings_are_not_readable_by_all_users(self):
		schema_path = (
			Path(__file__).parent
			/ "bike_garage"
			/ "doctype"
			/ "bg_garage_settings"
			/ "bg_garage_settings.json"
		)
		with schema_path.open(encoding="utf-8") as schema_file:
			permissions = json.load(schema_file)["permissions"]
		self.assertFalse(any(row.get("role") == "All" and row.get("read") for row in permissions))
		self.assertEqual(
			[
				(row.get("read"), row.get("write"))
				for row in permissions
				if row.get("role") == "System Manager"
			],
			[(1, 1)],
		)

	def test_permission_query_condition_scopes_to_active_garage(self):
		with patch.object(frappe.db, "escape", return_value=f"'{self.garage}'") as escape:
			condition = permissions.get_permission_query_conditions(
				self.user, doctype="BG Customer"
			)
		self.assertEqual(condition, "`tabBG Customer`.`garage` = 'GARAGE-001'")
		escape.assert_called_once_with(self.garage, percent=False)

	def test_missing_membership_returns_no_rows_and_denies_document_access(self):
		self.get_current_garage.side_effect = frappe.PermissionError("No active membership")
		self.assertEqual(
			permissions.get_permission_query_conditions(self.user, doctype="BG Customer"),
			"1=0",
		)
		self.assertFalse(permissions.has_permission(FakeGarageDocument(garage=self.garage), "read", self.user))

	def test_unmigrated_ownership_column_fails_closed(self):
		self.has_column.return_value = False
		self.assertEqual(
			permissions.get_permission_query_conditions(self.user, doctype="BG Customer"),
			"1=0",
		)
		self.assertFalse(
			permissions.has_permission(FakeGarageDocument(garage=self.garage), "read", self.user)
		)
		with self.assertRaises(frappe.PermissionError):
			permissions.assign_garage_on_insert(FakeGarageDocument(is_new=True))

	def test_missing_ownership_metadata_fails_closed(self):
		with patch.object(frappe, "get_meta", return_value=SimpleNamespace(get_field=lambda fieldname: None)):
			self.assertEqual(
				permissions.get_permission_query_conditions(self.user, doctype="BG Customer"),
				"1=0",
			)
			self.assertFalse(
				permissions.has_permission(FakeGarageDocument(garage=self.garage), "read", self.user)
			)

	def test_cross_garage_and_unassigned_documents_are_denied(self):
		self.assertFalse(
			permissions.has_permission(FakeGarageDocument(garage="GARAGE-002"), "read", self.user)
		)
		self.assertFalse(permissions.has_permission(FakeGarageDocument(), "read", self.user))
		self.assertTrue(
			permissions.has_permission(FakeGarageDocument(garage=self.garage), "read", self.user)
		)

	def test_new_record_is_assigned_from_session_membership(self):
		doc = FakeGarageDocument(garage=None, is_new=True)
		permissions.assign_garage_on_insert(doc)
		self.assertEqual(doc.garage, self.garage)

	def test_forged_garage_is_rejected_on_create(self):
		doc = FakeGarageDocument(garage="GARAGE-002", is_new=True)
		self.assertFalse(permissions.has_permission(doc, "create", self.user))
		with self.assertRaises(frappe.PermissionError):
			permissions.assign_garage_on_insert(doc)

	def test_ordinary_user_cannot_change_ownership(self):
		doc = FakeGarageDocument(garage="GARAGE-002", name="CUSTOMER-1")
		with patch.object(frappe.db, "get_value", return_value=self.garage):
			with self.assertRaises(frappe.PermissionError):
				permissions.validate_garage_ownership(doc)

	def test_ordinary_user_cannot_edit_unassigned_legacy_record(self):
		doc = FakeGarageDocument(garage=None, name="CUSTOMER-LEGACY")
		with patch.object(frappe.db, "get_value", return_value=None):
			with self.assertRaises(frappe.PermissionError):
				permissions.validate_garage_ownership(doc)

	def test_system_manager_does_not_bypass_garage_scope(self):
		with patch.object(frappe, "get_roles", return_value=["System Manager"]):
			self.assertFalse(
				permissions.has_permission(FakeGarageDocument(garage="GARAGE-002"), "read", self.user)
			)

	def test_explicit_platform_super_admin_has_separate_cross_garage_path(self):
		with patch.object(
			frappe,
			"get_roles",
			return_value=[tenancy.PLATFORM_SUPER_ADMIN_ROLE],
		):
			self.assertTrue(
				permissions.has_permission(
					FakeGarageDocument(garage="GARAGE-002"), "read", self.user
				)
			)
			self.assertEqual(
				permissions.get_permission_query_conditions(self.user, doctype="BG Customer"),
				"",
			)

	def test_administrator_retains_frappe_root_access(self):
		frappe.session.user = "Administrator"
		self.assertTrue(
			permissions.has_permission(FakeGarageDocument(garage=None), "read", "Administrator")
		)
		self.assertEqual(
			permissions.get_permission_query_conditions("Administrator", doctype="BG Customer"),
			"",
		)

	def test_membership_lookup_failure_fails_closed(self):
		self.get_current_garage.side_effect = RuntimeError("membership lookup failed")
		self.assertFalse(permissions.has_permission(FakeGarageDocument(garage=self.garage), "read", self.user))
		self.assertEqual(
			permissions.get_permission_query_conditions(self.user, doctype="BG Customer"),
			"1=0",
		)

	def test_delete_authorization_is_scoped_to_the_active_garage(self):
		self.assertTrue(
			permissions.has_permission(
				FakeGarageDocument(garage=self.garage), "delete", self.user
			)
		)
		self.assertFalse(
			permissions.has_permission(
				FakeGarageDocument(garage="GARAGE-002"), "delete", self.user
			)
		)

	def test_effective_platform_permissions_use_explicit_docperms(self):
		from frappe import permissions as frappe_permissions

		doctype = "BG Customer"
		schema_path = (
			Path(__file__).parent
			/ "bike_garage"
			/ "doctype"
			/ "bg_customer"
			/ "bg_customer.json"
		)
		with schema_path.open(encoding="utf-8") as schema_file:
			schema = json.load(schema_file)
		for doctype_name in (
			"bg_bike", "bg_customer", "bg_expense", "bg_job_card", "bg_sale", "bg_spare_part"
		):
			path = schema_path.parent.parent / doctype_name / f"{doctype_name}.json"
			with path.open(encoding="utf-8") as file:
				configured_schema = json.load(file)
			rows = [
				row for row in configured_schema["permissions"]
				if row.get("role") == tenancy.PLATFORM_SUPER_ADMIN_ROLE
			]
			self.assertEqual(len(rows), 1, doctype_name)
			for permission in ("read", "write", "create", "delete"):
				self.assertEqual(rows[0].get(permission), 1, (doctype_name, permission))
			if doctype_name == "bg_customer":
				platform_rows = rows

		meta = SimpleNamespace(
			name=doctype,
			permissions=[frappe._dict(row) for row in schema["permissions"]],
			is_submittable=0,
			allow_import=0,
			get_field=lambda fieldname: SimpleNamespace(fieldtype="Link", options="BG Garage")
			if fieldname == "garage"
			else None,
		)
		self.user = "platform.admin@example.test"
		frappe.session.user = self.user
		frappe.local.role_permissions.pop((doctype, self.user, False), None)
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(frappe, "get_roles", return_value=[tenancy.PLATFORM_SUPER_ADMIN_ROLE]),
			patch.object(
				frappe,
				"get_hooks",
				side_effect=lambda hook, *args, **kwargs: (
					{"BG Customer": ["bike_garage.permissions.has_permission"]}
					if hook == "has_permission"
					else {}
				),
			),
			patch.object(frappe_permissions, "get_rights", return_value=["read", "write", "create", "delete"]),
			patch.object(frappe_permissions, "has_user_permission", return_value=True),
		):
			self.assertTrue(
				frappe_permissions.has_permission(
					doctype,
					"delete",
					doc=FakeGarageDocument(doctype, garage="GARAGE-002"),
					user=self.user,
				)
			)

	def test_cross_garage_parent_link_is_rejected(self):
		doc = FakeGarageDocument(
			"BG Bike", garage=self.garage, customer="CUSTOMER-2", is_new=True
		)
		for linked_garage in ("GARAGE-002", None):
			with self.subTest(linked_garage=linked_garage):
				with patch.object(frappe.db, "get_value", return_value=linked_garage):
					with self.assertRaises(frappe.PermissionError):
						permissions.validate_garage_ownership(doc)

	def test_child_part_references_and_attachments_are_validated(self):
		for parent_doctype, child_doctype, table_field, parent_name in (
			("BG Job Card", "BG Job Card Part", "parts", "JOB-1"),
			("BG Sale", "BG Sale Item", "items", "SALE-1"),
		):
			with self.subTest(parent_doctype=parent_doctype):
				row = FakeGarageDocument(
					child_doctype,
					name="ROW-1",
					parent=parent_name,
					parenttype=parent_doctype,
					parentfield=table_field,
					part="PART-2",
				)
				doc = FakeGarageDocument(
					parent_doctype,
					garage=self.garage,
					name=parent_name,
					is_new=True,
					customer="CUSTOMER-1",
					**{table_field: [row]},
				)
				def linked_garage(doctype, name, field):
					return {"CUSTOMER-1": self.garage, "PART-2": "GARAGE-002"}.get(name)

				with patch.object(frappe.db, "get_value", side_effect=linked_garage):
					with self.assertRaises(frappe.PermissionError):
						permissions.validate_garage_ownership(doc)

				row.parentfield = "wrong_table"
				with patch.object(frappe.db, "get_value", return_value=self.garage):
					with self.assertRaises(frappe.PermissionError):
						permissions.validate_garage_ownership(doc)

	def test_job_card_bike_must_belong_to_selected_customer(self):
		doc = FakeGarageDocument(
			"BG Job Card", garage=self.garage, name="JOB-1", is_new=True,
			customer="CUSTOMER-1", bike="BIKE-1", parts=[]
		)
		def linked_value(doctype, name, field):
			return {
				("BG Customer", "CUSTOMER-1", "garage"): self.garage,
				("BG Bike", "BIKE-1", "garage"): self.garage,
				("BG Bike", "BIKE-1", "customer"): "CUSTOMER-2",
			}.get((doctype, name, field))
		with patch.object(frappe.db, "get_value", side_effect=linked_value):
			with self.assertRaises(frappe.PermissionError):
				permissions.validate_garage_ownership(doc)

	def test_sale_job_card_must_belong_to_selected_customer(self):
		doc = FakeGarageDocument(
			"BG Sale", garage=self.garage, name="SALE-1", is_new=True,
			customer="CUSTOMER-1", job_card="JOB-1", items=[]
		)
		def linked_value(doctype, name, field):
			return {
				("BG Customer", "CUSTOMER-1", "garage"): self.garage,
				("BG Job Card", "JOB-1", "garage"): self.garage,
				("BG Job Card", "JOB-1", "customer"): "CUSTOMER-2",
			}.get((doctype, name, field))
		with patch.object(frappe.db, "get_value", side_effect=linked_value):
			with self.assertRaises(frappe.PermissionError):
				permissions.validate_garage_ownership(doc)


class TestInvoiceGarageReadPermission(unittest.TestCase):
	def test_bg_sale_invoice_read_is_limited_to_active_garage(self):
		user = "garage.user@example.test"
		with (
			patch.object(permissions, "_active_session_user", return_value=user),
			patch.object(permissions, "_ownership_field_available", return_value=True),
			patch.object(permissions, "_has_platform_access", return_value=False),
			patch.object(permissions, "_has_payment_read_membership", return_value=True),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-001"),
		):
			self.assertTrue(
				permissions.has_permission(
					FakeGarageDocument(doctype="BG Sale", garage="GARAGE-001"), "read", user
				)
			)
			self.assertFalse(
				permissions.has_permission(
					FakeGarageDocument(doctype="BG Sale", garage="GARAGE-002"), "read", user
				)
			)

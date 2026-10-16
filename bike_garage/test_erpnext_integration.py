"""Unit-level checks for non-posting ERPNext mapping validation."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import erpnext_integration


class FakeDoc:
	def __init__(self, doctype, **values):
		self.doctype = doctype
		self.name = values.pop("name", "BG-TEST")
		self._before = values.pop("before", None)
		self.__dict__.update(values)

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def get_doc_before_save(self):
		return self._before


class TestERPNextMappingValidation(unittest.TestCase):
	def setUp(self):
		self.meta_patch = patch.object(erpnext_integration, "_field_ready", return_value=True)
		self.meta_patch.start()
		self.addCleanup(self.meta_patch.stop)
		self.throw_patch = patch.object(frappe, "throw", side_effect=ValueError)
		self.throw_patch.start()
		self.addCleanup(self.throw_patch.stop)

	def test_mapping_fields_require_explicit_platform_authorization(self):
		doc = FakeDoc("BG Customer", erpnext_customer="ERP-CUSTOMER-1", garage="GARAGE-A")
		with patch.object(erpnext_integration, "_is_mapping_admin", return_value=False):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_unauthorized_garage_configuration_is_rejected_before_document_lookup(self):
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=False),
			patch.object(frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(ValueError):
				erpnext_integration.configure_garage_erpnext_mapping(
					"GARAGE-A", "COMPANY-A", "WAREHOUSE-A"
				)

		get_doc.assert_not_called()

	def test_garage_company_and_warehouse_must_be_configured_together(self):
		doc = FakeDoc("BG Garage", erpnext_company="COMPANY-A", erpnext_warehouse=None)
		with patch.object(erpnext_integration, "_is_mapping_admin", return_value=True):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_warehouse_cannot_be_assigned_to_another_garage(self):
		doc = FakeDoc(
			"BG Garage", name="GARAGE-A", erpnext_company="COMPANY-A", erpnext_warehouse="WH-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(
				db,
				"get_value",
				return_value={"company": "COMPANY-A", "is_group": 0, "disabled": 0},
			),
			patch.object(frappe, "get_all", return_value=[{"name": "GARAGE-A"}, {"name": "GARAGE-B"}]),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_missing_garage_configuration_fails_before_transaction_mapping(self):
		doc = FakeDoc(
			"BG Sale", garage="GARAGE-A", customer="CUSTOMER-A", erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "exists", side_effect=[True]),
			patch.object(db, "get_value", return_value=None),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_transaction_customer_must_belong_to_the_same_garage(self):
		doc = FakeDoc(
			"BG Sale", garage="GARAGE-A", customer="CUSTOMER-B", erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(
				db,
				"get_value",
				side_effect=[
					{"erpnext_company": "COMPANY-A", "erpnext_warehouse": "WAREHOUSE-A"},
					{"company": "COMPANY-A", "is_group": 0, "disabled": 0},
					{"garage": "GARAGE-B", "erpnext_customer": "ERP-CUSTOMER-B"},
				],
			),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_one_erpnext_invoice_cannot_be_mapped_to_two_bg_sales(self):
		doc = FakeDoc(
			"BG Sale", name="BG-SALE-1", garage="GARAGE-A", customer="CUSTOMER-A",
			erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(
				frappe,
				"get_meta",
				return_value=SimpleNamespace(
					fields=[SimpleNamespace(fieldtype="Link", options="BG Garage", fieldname="garage")]
				),
			),
			patch.object(db, "has_column", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(
				db,
				"get_value",
				side_effect=[
					{"erpnext_company": "COMPANY-A", "erpnext_warehouse": "WAREHOUSE-A"},
					{"company": "COMPANY-A", "is_group": 0, "disabled": 0},
					{"garage": "GARAGE-A", "erpnext_customer": "ERP-CUSTOMER-A"},
					0,
					{"company": "COMPANY-A", "customer": "ERP-CUSTOMER-A", "garage": "GARAGE-A"},
				],
			),
			patch.object(frappe, "get_all", return_value=[{"name": "BG-SALE-OTHER"}]),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_erpnext_invoice_with_another_garage_owner_is_rejected(self):
		doc = FakeDoc(
			"BG Sale", name="BG-SALE-1", garage="GARAGE-A", customer="CUSTOMER-A",
			erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(
				frappe,
				"get_meta",
				return_value=SimpleNamespace(
					fields=[SimpleNamespace(fieldtype="Link", options="BG Garage", fieldname="garage")]
				),
			),
			patch.object(db, "has_column", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(
				db,
				"get_value",
				side_effect=[
					{"erpnext_company": "COMPANY-A", "erpnext_warehouse": "WAREHOUSE-A"},
					{"company": "COMPANY-A", "is_group": 0, "disabled": 0},
					{"garage": "GARAGE-A", "erpnext_customer": "ERP-CUSTOMER-A"},
					0,
					{"company": "COMPANY-A", "customer": "ERP-CUSTOMER-A", "garage": "GARAGE-B"},
				],
			),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_transaction_mapping_requires_a_migrated_erpnext_garage_link(self):
		doc = FakeDoc(
			"BG Sale", garage="GARAGE-A", customer="CUSTOMER-A", erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(frappe, "get_meta", return_value=SimpleNamespace(fields=[])),
			patch.object(db, "has_column", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(
				db,
				"get_value",
				side_effect=[
					{"erpnext_company": "COMPANY-A", "erpnext_warehouse": "WAREHOUSE-A"},
					{"company": "COMPANY-A", "is_group": 0, "disabled": 0},
					{"garage": "GARAGE-A", "erpnext_customer": "ERP-CUSTOMER-A"},
					0,
				],
			),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_unassigned_transaction_cannot_receive_an_erpnext_reference(self):
		doc = FakeDoc(
			"BG Sale", garage=None, customer="CUSTOMER-A", erpnext_sales_invoice="SI-1"
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "exists", return_value=False),
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

	def test_existing_item_mapping_is_validated_without_creating_or_posting(self):
		doc = FakeDoc(
			"BG Spare Part",
			name="PART-A",
			garage="GARAGE-A",
			erpnext_item="ITEM-A",
			before=SimpleNamespace(get=lambda fieldname: "ITEM-A" if fieldname == "erpnext_item" else None),
		)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "exists", return_value=True),
			patch.object(db, "get_value", return_value={"disabled": 0, "is_stock_item": 1}),
			patch.object(db, "set_value") as set_value,
			patch.object(frappe, "new_doc") as new_doc,
		):
			erpnext_integration.validate_mapping_reference(doc)

		set_value.assert_not_called()
		new_doc.assert_not_called()

	def test_mapping_validation_error_performs_no_database_mutation(self):
		doc = FakeDoc("BG Garage", erpnext_company="COMPANY-A", erpnext_warehouse=None)
		db = frappe.db
		with (
			patch.object(erpnext_integration, "_is_mapping_admin", return_value=True),
			patch.object(db, "set_value") as set_value,
			patch.object(frappe, "new_doc") as new_doc,
		):
			with self.assertRaises(ValueError):
				erpnext_integration.validate_mapping_reference(doc)

		set_value.assert_not_called()
		new_doc.assert_not_called()


if __name__ == "__main__":
	unittest.main()

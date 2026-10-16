"""Fail-closed validation for explicit, non-posting ERPNext references.

This module intentionally does not create ERPNext masters, stock documents, or
accounting documents. Existing BG quantities continue to be managed only by
``stock.py`` until an approved inventory/accounting workflow replaces that
behavior end to end.
"""

import frappe
from frappe import _

from bike_garage import tenancy


MAPPING_FIELDS = {
	"BG Garage": ("erpnext_company", "erpnext_warehouse"),
	"BG Customer": ("erpnext_customer",),
	"BG Spare Part": ("erpnext_item",),
	"BG Job Card": ("erpnext_maintenance_visit",),
	"BG Sale": ("erpnext_sales_invoice",),
}

SOURCE_TARGETS = {
	"BG Customer": {"erpnext_customer": "Customer"},
	"BG Spare Part": {"erpnext_item": "Item"},
	"BG Job Card": {"erpnext_maintenance_visit": "Maintenance Visit"},
	"BG Sale": {"erpnext_sales_invoice": "Sales Invoice"},
}

EXPECTED_LINKS = {
	("BG Garage", "erpnext_company"): "Company",
	("BG Garage", "erpnext_warehouse"): "Warehouse",
	("BG Customer", "garage"): "BG Garage",
	("BG Customer", "erpnext_customer"): "Customer",
	("BG Spare Part", "erpnext_item"): "Item",
	("BG Job Card", "erpnext_maintenance_visit"): "Maintenance Visit",
	("BG Sale", "erpnext_sales_invoice"): "Sales Invoice",
}


def _raise(message):
	frappe.throw(_(message), frappe.PermissionError)


def _is_mapping_admin():
	user = getattr(frappe.session, "user", None)
	if user == "Administrator":
		# Preserve Frappe's built-in root-user configuration path deliberately.
		return True
	if not user or user == "Guest":
		return False
	return tenancy.is_platform_super_admin(user)


def _require_mapping_admin():
	if not _is_mapping_admin():
		_raise("Only an explicitly authorized Platform Super Admin may configure ERPNext mappings.")


def _field_ready(doctype, fieldname):
	"""Require both DocType metadata and a migrated database column."""
	try:
		field = frappe.get_meta(doctype).get_field(fieldname)
		return bool(
			field
			and field.fieldtype == "Link"
			and field.options == EXPECTED_LINKS.get((doctype, fieldname))
			and frappe.db.has_column(doctype, fieldname)
		)
	except Exception:
		return False


def _value(doc, fieldname):
	return doc.get(fieldname) if hasattr(doc, "get") else getattr(doc, fieldname, None)


def _previous_value(doc, fieldname):
	previous = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	if not previous:
		return None
	return _value(previous, fieldname)


def _validate_garage_configuration(doc, garage_name=None):
	"""Validate existing Company/Warehouse references; a Warehouse belongs to one garage."""
	company = _value(doc, "erpnext_company")
	warehouse = _value(doc, "erpnext_warehouse")
	if not company and not warehouse:
		return
	if not company or not warehouse:
		_raise("Configure both an ERPNext Company and its garage Warehouse.")
	if not frappe.db.exists("Company", company):
		_raise("The configured ERPNext Company does not exist.")

	warehouse_doc = frappe.db.get_value(
		"Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True
	)
	if (
		not warehouse_doc
		or warehouse_doc.get("company") != company
		or warehouse_doc.get("is_group")
		or warehouse_doc.get("disabled")
	):
		_raise("The configured Warehouse must be an enabled, non-group Warehouse for this Company.")

	garage_name = garage_name or getattr(doc, "name", None)
	try:
		mapped_garages = frappe.get_all(
			"BG Garage",
			filters={"erpnext_warehouse": warehouse},
			fields=["name"],
			limit_page_length=0,
		)
	except Exception:
		_raise("Unable to verify that the ERPNext Warehouse belongs to only one garage.")
	if any(row.get("name") != garage_name for row in mapped_garages):
		_raise("An ERPNext Warehouse may be assigned to only one garage.")


def _get_garage_configuration(garage):
	if not garage:
		_raise("An assigned garage is required for ERPNext mapping.")
	if not frappe.db.exists("BG Garage", garage):
		_raise("The assigned garage does not exist.")
	if not _field_ready("BG Garage", "erpnext_company") or not _field_ready(
		"BG Garage", "erpnext_warehouse"
	):
		_raise("ERPNext garage configuration fields are unavailable; migrate the site first.")
	configuration = frappe.db.get_value(
		"BG Garage", garage, ["erpnext_company", "erpnext_warehouse"], as_dict=True
	)
	if not configuration or not configuration.get("erpnext_company") or not configuration.get(
		"erpnext_warehouse"
	):
		_raise("ERPNext Company and Warehouse are not configured for this garage.")
	_validate_garage_configuration(configuration, garage)
	return configuration


def _validate_customer_mapping(source_doc):
	customer_name = _value(source_doc, "customer")
	if not customer_name:
		_raise("A Bike Garage Customer is required for this ERPNext transaction mapping.")
	if not _field_ready("BG Customer", "garage") or not _field_ready(
		"BG Customer", "erpnext_customer"
	):
		_raise("Customer ownership or ERPNext mapping fields are unavailable.")
	customer = frappe.db.get_value(
		"BG Customer", customer_name, ["garage", "erpnext_customer"], as_dict=True
	)
	if not customer or customer.get("garage") != _value(source_doc, "garage"):
		_raise("The customer must belong to the same garage as the transaction.")
	if not customer.get("erpnext_customer"):
		_raise("Map the garage customer to an ERPNext Customer before mapping this transaction.")
	if not frappe.db.exists("Customer", customer.get("erpnext_customer")):
		_raise("The mapped ERPNext Customer does not exist.")
	disabled = frappe.db.get_value("Customer", customer.get("erpnext_customer"), "disabled")
	if disabled is None or disabled:
		_raise("The mapped ERPNext Customer is disabled.")
	return customer.get("erpnext_customer")


def _ensure_transaction_target_is_unmapped(source_doc, fieldname, target_name):
	"""Keep each ERPNext service visit or invoice attached to at most one BG record."""
	try:
		matches = frappe.get_all(
			source_doc.doctype,
			filters={fieldname: target_name},
			fields=["name"],
			limit_page_length=0,
		)
	except Exception:
		_raise("Unable to verify whether this ERPNext transaction is already mapped.")

	for match in matches:
		if match.get("name") != getattr(source_doc, "name", None):
			_raise("This ERPNext transaction is already mapped to another Bike Garage record.")


def _erpnext_garage_field(doctype):
	"""Require an installed, migrated ERPNext transaction ownership Link."""
	try:
		meta = frappe.get_meta(doctype)
		fields = [
			field
			for field in meta.fields
			if field.fieldtype == "Link"
			and field.options == "BG Garage"
			and frappe.db.has_column(doctype, field.fieldname)
		]
	except Exception:
		_raise("Unable to verify garage ownership on the ERPNext transaction.")

	if len(fields) != 1:
		_raise(
			"ERPNext transaction mapping is unavailable until its DocType has exactly one migrated BG Garage ownership Link."
		)
	return fields[0].fieldname


def _validate_transaction_target(source_doc, target_doctype, target_name):
	configuration = _get_garage_configuration(_value(source_doc, "garage"))
	erp_customer = _validate_customer_mapping(source_doc)
	garage_field = _erpnext_garage_field(target_doctype)
	target = frappe.db.get_value(
		target_doctype,
		target_name,
		["company", "customer", garage_field],
		as_dict=True,
	)
	if (
		not target
		or target.get("company") != configuration.get("erpnext_company")
		or target.get("customer") != erp_customer
		or target.get(garage_field) != _value(source_doc, "garage")
	):
		_raise("The ERPNext transaction must belong to this garage and use its configured Company and mapped Customer.")
	fieldname = {
		"Maintenance Visit": "erpnext_maintenance_visit",
		"Sales Invoice": "erpnext_sales_invoice",
	}[target_doctype]
	_ensure_transaction_target_is_unmapped(source_doc, fieldname, target_name)


def validate_mapping_reference(doc, method=None):
	"""Protect mapping references and verify they match existing ERPNext records."""
	fields = MAPPING_FIELDS.get(getattr(doc, "doctype", None))
	if not fields:
		return

	try:
		for fieldname in fields:
			current = _value(doc, fieldname)
			previous = _previous_value(doc, fieldname)
			if not _field_ready(doc.doctype, fieldname):
				if current or previous:
					_raise("ERPNext mapping fields are unavailable; migrate the site first.")
				continue
			if current != previous and not _is_mapping_admin():
				_raise("Only an explicitly authorized Platform Super Admin may change ERPNext mappings.")

		if doc.doctype == "BG Garage":
			_validate_garage_configuration(doc)
			return

		for fieldname, target_doctype in SOURCE_TARGETS.get(doc.doctype, {}).items():
			target_name = _value(doc, fieldname)
			if not target_name:
				continue
			if not frappe.db.exists(target_doctype, target_name):
				_raise("The selected ERPNext mapping target does not exist.")
			if doc.doctype == "BG Customer":
				customer = frappe.db.get_value("Customer", target_name, "disabled")
				if customer is None or customer:
					_raise("The mapped ERPNext Customer must be enabled.")
			elif doc.doctype == "BG Spare Part":
				item = frappe.db.get_value("Item", target_name, ["disabled", "is_stock_item"], as_dict=True)
				if not item or item.get("disabled") or not item.get("is_stock_item"):
					_raise("A spare part must map to an enabled ERPNext stock Item.")
			elif doc.doctype in {"BG Job Card", "BG Sale"}:
				_validate_transaction_target(doc, target_doctype, target_name)
	except frappe.PermissionError:
		raise
	except Exception:
		_raise("Unable to validate ERPNext mapping. No ERPNext records were changed.")


@frappe.whitelist(methods=["POST"])
def configure_garage_erpnext_mapping(garage, company=None, warehouse=None):
	"""Set references to existing ERPNext records; never create them."""
	_require_mapping_admin()
	if not garage:
		_raise("A garage is required.")
	if not _field_ready("BG Garage", "erpnext_company") or not _field_ready(
		"BG Garage", "erpnext_warehouse"
	):
		_raise("ERPNext garage configuration fields are unavailable; migrate the site first.")

	try:
		doc = frappe.get_doc("BG Garage", garage)
		doc.erpnext_company = company or None
		doc.erpnext_warehouse = warehouse or None
		_validate_garage_configuration(doc)
		doc.save(ignore_permissions=True)
		return {
			"garage": doc.name,
			"company": doc.get("erpnext_company"),
			"warehouse": doc.get("erpnext_warehouse"),
		}
	except frappe.PermissionError:
		raise
	except Exception:
		_raise("Unable to save the ERPNext Company and Warehouse mapping.")

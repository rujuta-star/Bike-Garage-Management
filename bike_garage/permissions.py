"""Garage ownership permission checks for tenant-owned parent DocTypes."""

import frappe
from frappe import _

from bike_garage import tenancy


TENANT_DOCTYPES = frozenset(
	{
		"BG Customer",
		"BG Bike",
		"BG Job Card",
		"BG Spare Part",
		"BG Sale",
		"BG Sale Payment",
		"BG Expense",
		"BG Stock Movement",
	}
)
PAYMENT_SENSITIVE_READ_DOCTYPES = frozenset({"BG Sale", "BG Job Card", "BG Expense"})


# Parent links and child-table links that must remain inside the transaction's garage.
LINK_FIELDS = {
	"BG Bike": {"customer": ("BG Customer", True)},
	"BG Job Card": {
		"customer": ("BG Customer", True),
		"bike": ("BG Bike", False),
	},
	"BG Sale": {
		"customer": ("BG Customer", True),
		"job_card": ("BG Job Card", False),
	},
	"BG Sale Payment": {"sale": ("BG Sale", True)},
	"BG Stock Movement": {
		"part": ("BG Spare Part", True),
		"against_receipt": ("BG Stock Movement", False),
	},
}
CHILD_PART_TABLES = {
	"BG Job Card": ("parts", "BG Job Card Part"),
	"BG Sale": ("items", "BG Sale Item"),
}


def _active_session_user(user=None):
	session_user = getattr(frappe.session, "user", None)
	user = user or session_user
	if not session_user or user != session_user or user == "Guest":
		return None
	return user


def _has_platform_access(user):
	"""Only the explicitly assigned platform role bypasses garage row scoping.

	Frappe's built-in Administrator remains its root user. System Manager alone
	does not receive cross-garage access through this app.
	"""
	return user == "Administrator" or tenancy.is_platform_super_admin(user)


def _ownership_field_available(doctype):
	"""Require both current DocType metadata and its migrated database column."""
	try:
		field = frappe.get_meta(doctype).get_field("garage")
		return bool(
			field
			and field.fieldtype == "Link"
			and field.options == "BG Garage"
			and frappe.db.has_column(doctype, "garage")
		)
	except Exception:
		return False


def _validate_linked_record_garage(parent_garage, linked_doctype, linked_name):
	"""Reject absent, unassigned, or cross-garage references without trusting Link UI filters."""
	if not linked_name:
		frappe.throw(
			_("A required linked record is missing."),
			frappe.PermissionError,
		)

	linked_garage = frappe.db.get_value(linked_doctype, linked_name, "garage")
	if not parent_garage or not linked_garage or linked_garage != parent_garage:
		frappe.throw(
			_("Linked records must belong to the same garage."),
			frappe.PermissionError,
		)


def _validate_linked_garage_references(doc):
	"""Validate tenant-owned links and part rows against this parent's garage."""
	parent_garage = doc.get("garage")
	for fieldname, (linked_doctype, required) in LINK_FIELDS.get(doc.doctype, {}).items():
		linked_name = doc.get(fieldname)
		if linked_name or required:
			_validate_linked_record_garage(parent_garage, linked_doctype, linked_name)

	# Same-garage membership is necessary but not sufficient for these semantic links.
	if doc.doctype == "BG Job Card" and doc.get("bike") and doc.get("customer"):
		bike_customer = frappe.db.get_value("BG Bike", doc.get("bike"), "customer")
		if bike_customer != doc.get("customer"):
			frappe.throw(
				_("The selected bike must belong to the selected customer."),
				frappe.PermissionError,
			)
	if doc.doctype == "BG Sale" and doc.get("job_card") and doc.get("customer"):
		job_card_customer = frappe.db.get_value("BG Job Card", doc.get("job_card"), "customer")
		if job_card_customer != doc.get("customer"):
			frappe.throw(
				_("The selected Job Card must belong to the selected customer."),
				frappe.PermissionError,
			)

	child_table = CHILD_PART_TABLES.get(doc.doctype)
	if not child_table:
		return

	fieldname, child_doctype = child_table
	for row in doc.get(fieldname) or []:
		# Frappe sets parent and parenttype immediately before validation. Verify the
		# relationship instead of assuming a submitted child row belongs here.
		if (
			row.doctype != child_doctype
			or row.get("parent") != doc.name
			or row.get("parenttype") != doc.doctype
			or row.get("parentfield") != fieldname
		):
			frappe.throw(
				_("Child rows must remain attached to their parent document."),
				frappe.PermissionError,
			)
		_validate_linked_record_garage(
			parent_garage,
			"BG Spare Part",
			row.get("part"),
		)


def get_permission_query_conditions(user=None, doctype=None):
	"""Return a garage predicate for permission-aware list queries."""
	if doctype not in TENANT_DOCTYPES:
		return "1=0"

	user = _active_session_user(user)
	if not user:
		return "1=0"

	try:
		if _has_platform_access(user):
			return ""
		if doctype in PAYMENT_SENSITIVE_READ_DOCTYPES and not _has_payment_read_membership(user):
			return "1=0"
		if doctype == "BG Sale Payment" and not _has_payment_read_membership(user):
			return "1=0"
		if doctype == "BG Stock Movement" and not _has_inventory_membership(user):
			return "1=0"
		if not _ownership_field_available(doctype):
			return "1=0"

		garage = tenancy.get_current_garage()
		escaped_garage = frappe.db.escape(garage, percent=False)
		# db.escape() returns a complete SQL literal, including its quotes.
		return f"`tab{doctype}`.`garage` = {escaped_garage}"
	except Exception:
		# No active membership, role lookup failure, or database failure means no rows.
		return "1=0"


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Deny direct access unless the document belongs to the active garage."""
	doctype = getattr(doc, "doctype", None)
	if doctype not in TENANT_DOCTYPES:
		return True

	user = _active_session_user(user)
	if not user:
		return False

	try:
		if user == "Administrator":
			return True
		if doctype == "BG Sale" and ptype == "delete" and user != "Administrator":
			return False
		if doctype == "BG Sale" and ptype in {"create", "write", "delete", "submit", "cancel"}:
			# Website sales remain read-only until a payment ledger and auditable
			# cancellation path exist; hiding the dashboard action alone is insufficient.
			if frappe.get_cached_value("User", user, "user_type") == "Website User":
				return False
		if doctype == "BG Sale Payment" and ptype not in (None, "read", "select"):
			# Platform administrators may inspect payment history, but this read
			# exception must not become a generic permission to mutate ledger rows.
			return False
		if _has_platform_access(user):
			return True
		if doctype == "BG Expense" and not _has_payment_read_membership(user):
			return False
		if doctype == "BG Stock Movement" and not _has_inventory_membership(user):
			return False
		if (
			doctype in PAYMENT_SENSITIVE_READ_DOCTYPES
			and ptype in (None, "read", "select")
			and not _has_payment_read_membership(user)
		):
			return False
		if doctype == "BG Sale Payment":
			if ptype not in (None, "read", "select") or not _has_payment_read_membership(user):
				return False
		if not _ownership_field_available(doctype):
			return False
		garage = tenancy.get_current_garage()
		doc_garage = doc.get("garage")
		if ptype == "create":
			# The before_insert event assigns the resolved garage. Reject forged values
			# during Frappe's create permission check, which runs before that event.
			return not doc_garage or doc_garage == garage

		return bool(doc_garage) and doc_garage == garage
	except Exception:
		return False


def _has_payment_read_membership(user):
	try:
		garage = tenancy.get_current_garage()
		return frappe.db.get_value(
			"BG Garage Membership",
			{"user": user, "garage": garage, "status": "Active"},
			"membership_type",
		) in {"Owner", "Manager", "Accountant"}
	except Exception:
		return False


def _has_inventory_membership(user):
	try:
		from bike_garage.bike_garage.api.inventory import INVENTORY_MEMBERSHIP_TYPES

		garage = tenancy.get_current_garage()
		return frappe.db.get_value(
			"BG Garage Membership",
			{"user": user, "garage": garage, "status": "Active"},
			"membership_type",
		) in INVENTORY_MEMBERSHIP_TYPES
	except Exception:
		return False


def assign_garage_on_insert(doc, method=None):
	"""Assign ordinary users' new records to their session-resolved garage."""
	user = _active_session_user()
	if user == "Administrator":
		# Preserve Frappe's built-in root-user workflow, including reviewed legacy work.
		return
	if not user:
		frappe.throw(_("An authenticated garage user is required."), frappe.PermissionError)

	try:
		if not _ownership_field_available(doc.doctype):
			frappe.throw(_("Garage ownership fields are not available; migrate the site before creating records."), frappe.PermissionError)
		if tenancy.is_platform_super_admin(user):
			if not doc.get("garage"):
				frappe.throw(
					_("Platform Super Admin must explicitly select a garage."),
					frappe.PermissionError,
				)
			return

		garage = tenancy.get_current_garage()
		if doc.get("garage") and doc.get("garage") != garage:
			frappe.throw(_("The selected garage does not match your active membership."), frappe.PermissionError)
		doc.garage = garage
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.throw(_("Unable to assign the active garage."), frappe.PermissionError)


def validate_garage_ownership(doc, method=None):
	"""Prevent ordinary users from editing or transferring garage ownership."""
	user = _active_session_user()
	if user == "Administrator":
		return
	if not user:
		frappe.throw(_("An authenticated garage user is required."), frappe.PermissionError)

	try:
		if not _ownership_field_available(doc.doctype):
			frappe.throw(_("Garage ownership fields are not available; migrate the site before editing records."), frappe.PermissionError)
		is_platform_admin = tenancy.is_platform_super_admin(user)

		if not is_platform_admin:
			garage = tenancy.get_current_garage()
			if doc.is_new():
				if doc.get("garage") != garage:
					frappe.throw(_("New records must belong to your active garage."), frappe.PermissionError)
			else:
				stored_garage = frappe.db.get_value(doc.doctype, doc.name, "garage")
				if not stored_garage or stored_garage != garage or doc.get("garage") != stored_garage:
					frappe.throw(_("You cannot access or change this record's garage ownership."), frappe.PermissionError)

		_validate_linked_garage_references(doc)
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.throw(_("Unable to verify garage ownership."), frappe.PermissionError)

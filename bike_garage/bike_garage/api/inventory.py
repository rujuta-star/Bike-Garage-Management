"""Garage-scoped quantity receiving and stock movement history."""

import hashlib
import json
import uuid
from decimal import Decimal

import frappe
from frappe import _

from bike_garage import tenancy
from bike_garage.numeric import validate_number


INVENTORY_MEMBERSHIP_TYPES = {"Owner", "Manager", "Inventory Manager"}
MOVEMENT_TYPES = {
	"Purchase Receipt",
	"Positive Adjustment",
	"Negative Adjustment",
	"Supplier Return",
}


def require_inventory_role(garage=None):
	"""Require a current garage membership with inventory authority."""
	if frappe.session.user == "Administrator":
		return garage
	active_garage = tenancy.get_current_garage()
	if garage and garage != active_garage:
		frappe.throw(_("The selected garage does not match your active membership."), frappe.PermissionError)
	membership_type = frappe.db.get_value(
		"BG Garage Membership",
		{"user": frappe.session.user, "garage": active_garage, "status": "Active"},
		"membership_type",
	)
	if membership_type not in INVENTORY_MEMBERSHIP_TYPES:
		frappe.throw(_("Your garage membership does not allow inventory operations."), frappe.PermissionError)
	return active_garage


def _clean_text(value, label, *, required=False, maximum=140):
	if value is None:
		value = ""
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)
	value = value.strip()
	if required and not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > maximum:
		frappe.throw(_("{0} must be at most {1} characters.").format(label, maximum), frappe.ValidationError)
	return value or None


def _submission_uuid(value):
	try:
		return str(uuid.UUID(str(value)))
	except (ValueError, TypeError, AttributeError):
		frappe.throw(_("Refresh the form and try again."), frappe.ValidationError)


def _canonical_number(value):
	if value in (None, ""):
		return None
	return str(Decimal(str(value)).normalize())


def _request_fingerprint(
	*, part, movement_type, qty, unit_cost, supplier, reference, against_receipt, reason,
	source_doctype=None, source_document=None, source_event=None,
):
	payload = {
		"part": part,
		"movement_type": movement_type,
		"qty": _canonical_number(qty),
		"unit_cost": _canonical_number(unit_cost),
		"supplier": supplier,
		"reference": reference,
		"against_receipt": against_receipt,
		"reason": reason,
		"source_doctype": source_doctype,
		"source_document": source_document,
		"source_event": source_event,
	}
	serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _return_existing_submission(key, garage, fingerprint):
	rows = frappe.get_all(
		"BG Stock Movement",
		filters={"submission_key": key},
		fields=["name", "garage", "docstatus", "request_fingerprint", "stock_after"],
		limit=1,
	)
	if not rows:
		return None
	row = rows[0]
	if row.garage != garage:
		frappe.throw(_("This submission could not be verified."), frappe.PermissionError)
	if row.docstatus != 1 or row.request_fingerprint != fingerprint:
		frappe.throw(_("This submission key was already used for a different or incomplete request."), frappe.ValidationError)
	return {"name": row.name, "duplicate": True, "stock_qty": row.stock_after}


@frappe.whitelist(methods=["GET"])
def get_stock_movement_options():
	garage = require_inventory_role()
	parts = frappe.get_list(
		"BG Spare Part",
		filters={"garage": garage},
		fields=["name", "part_name", "stock_qty", "unit"],
		order_by="part_name asc",
		limit_page_length=500,
	)
	receipts = frappe.get_list(
		"BG Stock Movement",
		filters={"garage": garage, "movement_type": "Purchase Receipt", "docstatus": 1},
		fields=["name", "part", "qty", "supplier", "reference", "creation"],
		order_by="creation desc",
		limit_page_length=500,
	)
	prior_returns = frappe.get_all(
		"BG Stock Movement",
		filters={"garage": garage, "movement_type": "Supplier Return", "against_receipt": ["is", "set"]},
		fields=["against_receipt"],
	)
	returned_receipts = {row.against_receipt for row in prior_returns}
	receipts = [row for row in receipts if row.name not in returned_receipts]
	return {"parts": parts, "receipts": receipts, "movement_types": sorted(MOVEMENT_TYPES)}


@frappe.whitelist(methods=["GET"])
def get_stock_movement_history(limit=100):
	garage = require_inventory_role()
	try:
		limit = max(1, min(int(limit), 200))
	except (TypeError, ValueError, OverflowError):
		limit = 100
	return frappe.get_list(
		"BG Stock Movement",
		filters={"garage": garage},
		fields=[
			"name", "movement_type", "part", "qty", "unit_cost", "supplier", "reference",
			"against_receipt", "reason", "docstatus", "stock_before", "stock_after",
			"source_doctype", "source_document", "source_event", "reversal_reason",
			"reversal_stock_before", "reversal_stock_after", "creation",
		],
		order_by="creation desc",
		limit_page_length=limit,
	)


@frappe.whitelist(methods=["POST"])
def create_stock_movement(
	part,
	movement_type,
	qty,
	reason,
	submission_key,
	unit_cost=None,
	supplier=None,
	reference=None,
	against_receipt=None,
):
	"""Create and submit a scoped stock movement; retries return the same document."""
	garage = require_inventory_role()
	if not isinstance(movement_type, str) or movement_type not in MOVEMENT_TYPES:
		frappe.throw(_("Choose a valid movement type."), frappe.ValidationError)
	validate_number(qty, _("Quantity"), minimum=0, minimum_exclusive=True)
	reason = _clean_text(reason, _("Reason"), required=True, maximum=2000)
	supplier = _clean_text(supplier, _("Supplier"))
	reference = _clean_text(reference, _("Purchase or return reference"))
	key = _submission_uuid(submission_key)
	if movement_type == "Purchase Receipt":
		validate_number(unit_cost, _("Unit cost"), minimum=0)
	elif unit_cost not in (None, ""):
		frappe.throw(_("Unit cost can only be entered for a purchase receipt."), frappe.ValidationError)

	fingerprint = _request_fingerprint(
		part=part,
		movement_type=movement_type,
		qty=qty,
		unit_cost=unit_cost if movement_type == "Purchase Receipt" else None,
		supplier=supplier,
		reference=reference,
		against_receipt=against_receipt,
		reason=reason,
	)
	existing = _return_existing_submission(key, garage, fingerprint)
	if existing:
		return existing

	if movement_type == "Supplier Return" and (not supplier or not reference or not against_receipt):
		frappe.throw(_("Supplier, return reference, and original receipt are required."), frappe.ValidationError)
	if movement_type == "Supplier Return" and frappe.get_all(
		"BG Stock Movement", filters={"garage": garage, "against_receipt": against_receipt, "movement_type": movement_type},
		fields=["name"], limit=1,
	):
		frappe.throw(_("A supplier return has already been recorded for this receipt."), frappe.ValidationError)

	parts = frappe.get_list(
		"BG Spare Part", filters={"name": part, "garage": garage}, fields=["name"], limit_page_length=1
	)
	if not parts:
		frappe.throw(_("Spare part was not found."), frappe.DoesNotExistError)

	doc = frappe.get_doc({
		"doctype": "BG Stock Movement",
		"movement_type": movement_type,
		"part": part,
		"qty": qty,
		"unit_cost": unit_cost if movement_type == "Purchase Receipt" else None,
		"supplier": supplier,
		"reference": reference,
		"against_receipt": against_receipt,
		"reason": reason,
		"garage": garage,
		"submission_key": key,
		"request_fingerprint": fingerprint,
	})
	savepoint = f"bg_stock_movement_{uuid.uuid4().hex}"
	frappe.db.savepoint(savepoint)
	try:
		doc.insert(ignore_permissions=True)
		doc.flags.ignore_permissions = True
		doc.submit()
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point=savepoint)
		winner = _return_existing_submission(key, garage, fingerprint)
		if winner:
			return winner
		frappe.throw(_("This stock movement conflicts with an existing submission or receipt return."), frappe.ValidationError)
	except BaseException:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {"name": doc.name, "duplicate": False, "stock_qty": doc.stock_after}


@frappe.whitelist(methods=["POST"])
def cancel_stock_movement(name, reason):
	"""Reverse a submitted movement without allowing a negative stock balance."""
	garage = require_inventory_role()
	reason = _clean_text(reason, _("Reversal reason"), required=True, maximum=2000)
	rows = frappe.get_list(
		"BG Stock Movement", filters={"name": name, "garage": garage}, fields=["name"], limit_page_length=1
	)
	if not rows:
		frappe.throw(_("Stock movement was not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("BG Stock Movement", rows[0].name, for_update=True)
	if doc.source_document:
		frappe.throw(
			_("This movement is reversed through its source document lifecycle."),
			frappe.ValidationError,
		)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted stock movement can be reversed."), frappe.ValidationError)
	doc.flags.ignore_permissions = True
	savepoint = f"bg_stock_cancel_{uuid.uuid4().hex}"
	frappe.db.savepoint(savepoint)
	try:
		doc.db_set("reversal_reason", reason, update_modified=False)
		doc.cancel()
	except BaseException:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {"name": doc.name, "docstatus": doc.docstatus}

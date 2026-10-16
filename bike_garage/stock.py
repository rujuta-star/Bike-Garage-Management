"""Inventory (stock) auto-management for Bike Garage.

Job Card and Sale changes apply their quantity deltas to the custom
`BG Spare Part.stock_qty` balance. The movement workflow adds auditable stock
receipts, adjustments, and supplier returns to this same balance. All stock
changes lock the affected part and validate garage ownership and nonnegative
results. Existing Sale deletion still restores stock while deleting its history;
Website User deletion is denied, and the New Sale UI stays disabled until an
auditable sale lifecycle and payment ledger are implemented.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

import frappe
from bike_garage.numeric import validate_number


_stock_qty_update_authorized = ContextVar("bike_garage_stock_qty_update_authorized", default=None)
_historical_import_active = ContextVar("bike_garage_historical_import_active", default=False)
_source_stock_audit = ContextVar("bike_garage_source_stock_audit", default=None)
_HISTORICAL_IMPORT_CAPABILITY = object()


@contextmanager
def _stock_qty_update_scope(part_name):
	token = _stock_qty_update_authorized.set(part_name)
	try:
		yield
	finally:
		_stock_qty_update_authorized.reset(token)


def _is_stock_qty_update_authorized(part_name):
	return _stock_qty_update_authorized.get() == part_name


@contextmanager
def _historical_import_scope(capability):
	"""Temporarily suppress automatic stock deltas for the trusted legacy importer."""
	if capability is not _HISTORICAL_IMPORT_CAPABILITY:
		frappe.throw("Historical import authorization is required.", frappe.PermissionError)
	token = _historical_import_active.set(True)
	try:
		yield
	finally:
		_historical_import_active.reset(token)


def _is_historical_import_active():
	return _historical_import_active.get()


@contextmanager
def _source_stock_audit_scope(source, part, before, after):
	token = _source_stock_audit.set({**source, "part": part, "before": before, "after": after})
	try:
		yield
	finally:
		_source_stock_audit.reset(token)


def _source_stock_audit_context(doc):
	audit = _source_stock_audit.get()
	if (
		audit
		and doc.get("source_doctype") == audit.get("source_doctype")
		and doc.get("source_document") == audit.get("source_document")
		and doc.get("source_event") == audit.get("source_event")
		and doc.get("part") == audit.get("part")
		and doc.get("garage") == audit.get("garage")
		and doc.get("stock_before") in (None, "", audit.get("before"))
		and doc.get("stock_after") in (None, "", audit.get("after"))
	):
		return audit
	return None


def _is_source_stock_audit_authorized(doc):
	return _source_stock_audit_context(doc) is not None


def _consumed_map(doc, table_field):
	"""Return {part_name: total_qty} for a child table on the given document."""
	totals = {}
	if not doc:
		return totals
	for row in (doc.get(table_field) or []):
		part = row.get("part") if isinstance(row, dict) else row.part
		qty = row.get("qty") if isinstance(row, dict) else row.qty
		if part:
			validate_number(qty, "Consumed part quantity", minimum=0, minimum_exclusive=True)
			totals[part] = totals.get(part, 0) + qty
			validate_number(totals[part], "Total consumed part quantity", minimum=0, minimum_exclusive=True)
	return totals


def _transaction_garage(doc, expected_doctype):
	"""Resolve ownership from the persisted transaction, not the caller's value."""
	if (
		getattr(doc, "doctype", None) != expected_doctype
		or not getattr(doc, "name", None)
		or not doc.get("garage")
	):
		frappe.throw("Stock changes require a saved transaction with garage ownership.", frappe.PermissionError)

	try:
		field = frappe.get_meta(expected_doctype).get_field("garage")
		available = (
			field
			and field.fieldtype == "Link"
			and field.options == "BG Garage"
			and frappe.db.has_column(expected_doctype, "garage")
		)
		stored_garage = frappe.db.get_value(expected_doctype, doc.name, "garage")
		garage_exists = stored_garage and frappe.db.exists("BG Garage", stored_garage)
	except Exception:
		frappe.throw("Unable to verify transaction garage ownership for stock changes.", frappe.PermissionError)

	if not available or not garage_exists or stored_garage != doc.get("garage"):
		frappe.throw("The saved transaction garage is missing or does not match.", frappe.PermissionError)
	return stored_garage


def _apply_stock_changes(changes, *, garage, source_audit=None):
	"""Lock, validate, then apply all stock changes in a stable order."""
	stock_docs = {}
	new_quantities = {}
	old_quantities = {}

	for part in sorted(changes):
		change = changes[part]
		validate_number(change, "Stock quantity change")
		if not change:
			continue
		stock_doc = frappe.get_doc("BG Spare Part", part, for_update=True)
		if garage and stock_doc.get("garage") != garage:
			frappe.throw(
				"Every stock part must belong to the transaction's garage.",
				frappe.PermissionError,
			)
		validate_number(stock_doc.stock_qty, "Current stock quantity", allow_empty=True, minimum=0)
		new_qty = (stock_doc.stock_qty or 0) + change
		validate_number(new_qty, "Resulting stock quantity")
		if change < 0 and new_qty < 0:
			frappe.throw(
				f"Insufficient stock for {stock_doc.part_name}: "
				f"{stock_doc.stock_qty or 0} available, {-change} required."
			)
		stock_docs[part] = stock_doc
		old_quantities[part] = stock_doc.stock_qty or 0
		new_quantities[part] = new_qty

	if not stock_docs:
		return
	if not garage:
		frappe.throw("Stock changes require a verified transaction garage.", frappe.PermissionError)

	# Keep stock writes atomic even when a caller catches a later save exception.
	# This savepoint is inside, and never commits or rolls back, the caller's transaction.
	savepoint = f"bg_stock_{uuid4().hex}"
	frappe.db.savepoint(savepoint)
	try:
		for part, stock_doc in stock_docs.items():
			stock_doc.stock_qty = new_quantities[part]
			with _stock_qty_update_scope(stock_doc.name):
				stock_doc.save(ignore_permissions=True)
		if source_audit:
			_record_source_stock_movements(
				source_audit, changes, old_quantities, new_quantities
			)
		frappe.db.release_savepoint(savepoint)
	except BaseException:
		try:
			frappe.db.rollback(save_point=savepoint)
		except BaseException:
			# Preserve the operation's original exception. The outer Frappe transaction
			# can still roll back if this savepoint rollback itself fails.
			frappe.logger("bike_garage.stock").exception(
				"Stock savepoint rollback failed: %s", savepoint
			)
		raise


def _consumed_map_for_document(doc, table_field, respect_job_card_status=False):
	if respect_job_card_status and doc and doc.status == "Cancelled":
		return {}
	return _consumed_map(doc, table_field)


def _source_event(doc, before, *, deleting=False):
	if deleting:
		return "Deleted"
	if doc.doctype == "BG Job Card" and before:
		if before.status != "Cancelled" and doc.status == "Cancelled":
			return "Cancelled"
		if before.status == "Cancelled" and doc.status != "Cancelled":
			return "Reactivated"
	return "Updated"


def _apply_delta(doc, table_field, *, expected_doctype, respect_job_card_status=False):
	"""Apply only the changed consumption since the previous save."""
	garage = _transaction_garage(doc, expected_doctype)
	new = _consumed_map_for_document(doc, table_field, respect_job_card_status)
	old = _consumed_map_for_document(
		doc.get_doc_before_save(), table_field, respect_job_card_status
	)
	changes = {part: old.get(part, 0) - new.get(part, 0) for part in set(new) | set(old)}
	_apply_stock_changes(
		changes,
		garage=garage,
		source_audit={
			"source_doctype": expected_doctype,
			"source_document": doc.name,
			"source_event": _source_event(doc, doc.get_doc_before_save()),
			"garage": garage,
		},
	)


def _restore(doc, table_field, *, expected_doctype, respect_job_card_status=False):
	"""Restore the stock currently consumed by a document being deleted."""
	garage = _transaction_garage(doc, expected_doctype)
	consumed = _consumed_map_for_document(doc, table_field, respect_job_card_status)
	_apply_stock_changes(
		consumed,
		garage=garage,
		source_audit={
			"source_doctype": expected_doctype,
			"source_document": doc.name,
			"source_event": _source_event(doc, doc.get_doc_before_save(), deleting=True),
			"garage": garage,
		},
	)


def _record_source_stock_movements(source, changes, before_values, after_values):
	from bike_garage.bike_garage.api.inventory import _request_fingerprint

	for part in sorted(changes):
		delta = changes[part]
		if not delta:
			continue
		if source["source_doctype"] == "BG Sale":
			movement_type = "Sale Consumption" if delta < 0 else "Sale Restoration"
		else:
			movement_type = "Job Card Consumption" if delta < 0 else "Job Card Restoration"
		quantity = abs(delta)
		reason = f"{source['source_event']} from {source['source_doctype']} {source['source_document']}"
		values = {
			"part": part,
			"movement_type": movement_type,
			"qty": quantity,
			"unit_cost": None,
			"supplier": None,
			"reference": None,
			"against_receipt": None,
			"reason": reason,
			"source_doctype": source["source_doctype"],
			"source_document": source["source_document"],
			"source_event": source["source_event"],
		}
		values["submission_key"] = str(uuid4())
		values["request_fingerprint"] = _request_fingerprint(
			part=part,
			movement_type=movement_type,
			qty=quantity,
			unit_cost=None,
			supplier=None,
			reference=None,
			against_receipt=None,
			reason=reason,
			source_doctype=source["source_doctype"],
			source_document=source["source_document"],
			source_event=source["source_event"],
		)
		movement = frappe.get_doc({
			"doctype": "BG Stock Movement",
			**values,
			"garage": source["garage"],
		})
		with _source_stock_audit_scope(
			{**source, "garage": source["garage"]},
			part,
			before_values[part],
			after_values[part],
		):
			movement.insert(ignore_permissions=True)
			movement.flags.ignore_permissions = True
			movement.submit()


# --- Document event handlers (wired in hooks.py) -----------------------------

def update_stock_from_job_card(doc, method=None):
	if _is_historical_import_active():
		return
	_apply_delta(doc, "parts", expected_doctype="BG Job Card", respect_job_card_status=True)


def restore_stock_from_job_card(doc, method=None):
	_restore(doc, "parts", expected_doctype="BG Job Card", respect_job_card_status=True)


def update_stock_from_sale(doc, method=None):
	if _is_historical_import_active():
		return
	_apply_delta(doc, "items", expected_doctype="BG Sale")


def restore_stock_from_sale(doc, method=None):
	_restore(doc, "items", expected_doctype="BG Sale")


def _validate_supplier_return(doc):
	if doc.movement_type != "Supplier Return":
		return
	receipt = frappe.get_doc("BG Stock Movement", doc.against_receipt, for_update=True)
	if (
		not receipt
		or receipt.movement_type != "Purchase Receipt"
		or receipt.docstatus != 1
		or receipt.part != doc.part
		or receipt.garage != doc.garage
	):
		frappe.throw("Supplier returns must reference a submitted receipt for this part and garage.", frappe.ValidationError)
	if receipt.supplier and receipt.supplier != doc.supplier:
		frappe.throw("Supplier return must use the supplier recorded on the original receipt.", frappe.ValidationError)

	if doc.qty != receipt.qty:
		frappe.throw("Supplier returns must reverse the full original receipt quantity.", frappe.ValidationError)


def apply_stock_movement(doc, method=None):
	"""Apply one submitted, garage-owned movement to the existing on-hand balance."""
	from bike_garage.bike_garage.api.inventory import require_inventory_role

	if doc.docstatus != 1 or not doc.name:
		frappe.throw("Only a saved submitted stock movement can change inventory.", frappe.PermissionError)
	garage = _transaction_garage(doc, "BG Stock Movement")
	_validate_supplier_return(doc)
	part = frappe.get_doc("BG Spare Part", doc.part, for_update=True)
	if part.garage != garage:
		frappe.throw("The stock part must belong to the movement garage.", frappe.PermissionError)
	audit = _source_stock_audit_context(doc)
	if audit:
		if part.stock_qty != audit["after"]:
			frappe.throw("Source stock changed before its audit movement was recorded.", frappe.ValidationError)
		doc.db_set({"stock_before": audit["before"], "stock_after": audit["after"]}, update_modified=False)
		return
	require_inventory_role(doc.garage)
	change = doc.stock_delta()
	before = part.stock_qty or 0
	_apply_stock_changes({doc.part: change}, garage=garage)
	after = before + change
	doc.db_set({"stock_before": before, "stock_after": after}, update_modified=False)


def reverse_stock_movement(doc, method=None):
	"""Reverse the exact submitted effect on cancellation, refusing negative stock."""
	from bike_garage.bike_garage.api.inventory import require_inventory_role

	if doc.source_document:
		frappe.throw("Source-linked stock movements follow their Sale or Job Card lifecycle.", frappe.PermissionError)
	require_inventory_role(doc.garage)
	if not isinstance(doc.reversal_reason, str) or not doc.reversal_reason.strip():
		frappe.throw("A reversal reason is required.", frappe.ValidationError)
	garage = _transaction_garage(doc, "BG Stock Movement")
	if doc.movement_type == "Purchase Receipt":
		active_returns = frappe.db.count(
			"BG Stock Movement",
			{"against_receipt": doc.name, "movement_type": "Supplier Return", "docstatus": 1},
		)
		if active_returns:
			frappe.throw("Cancel related supplier returns before reversing this receipt.", frappe.ValidationError)
	part = frappe.get_doc("BG Spare Part", doc.part, for_update=True)
	if part.garage != garage:
		frappe.throw("The stock part must belong to the movement garage.", frappe.PermissionError)
	change = -doc.stock_delta()
	before = part.stock_qty or 0
	_apply_stock_changes({doc.part: change}, garage=garage)
	doc.db_set({"reversal_stock_before": before, "reversal_stock_after": before + change}, update_modified=False)

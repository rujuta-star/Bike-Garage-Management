"""Garage-scoped operational receipt ledger for BG Sales.

This records operator-attested receipts only. It does not post accounting entries,
and refund/reversal workflows remain unavailable until policy is approved.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
import hashlib
import json
import uuid

import frappe
from frappe import _
from frappe.utils import flt

from bike_garage import tenancy
from bike_garage.numeric import validate_number


PAYMENT_MEMBERSHIP_TYPES = {"Owner", "Manager", "Accountant"}
PAYMENT_MODES = {"Cash", "UPI", "Card", "NEFT", "Cheque"}
_authorized_payment_context = ContextVar("bike_garage_authorized_sale_payment", default=None)


def require_payment_role(garage=None):
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
	if membership_type not in PAYMENT_MEMBERSHIP_TYPES:
		frappe.throw(_("Your garage membership does not allow payment operations."), frappe.PermissionError)
	return active_garage


def can_read_payment_data(garage=None):
	"""Check the existing payment-read policy without accepting caller scope."""
	user = frappe.session.user
	if user == "Administrator":
		return True
	try:
		if tenancy.is_platform_super_admin(user):
			return True
		active_garage = tenancy.get_current_garage()
		if garage is not None and garage != active_garage:
			return False
		membership_type = frappe.db.get_value(
			"BG Garage Membership",
			{"user": user, "garage": active_garage, "status": "Active"},
			"membership_type",
		)
		return membership_type in PAYMENT_MEMBERSHIP_TYPES
	except Exception:
		return False


def require_payment_read_access(garage=None):
	if not can_read_payment_data(garage):
		frappe.throw(_("Your garage membership does not allow access to payment data."), frappe.PermissionError)
	return garage


def _clean_reference(value):
	if value is None:
		return None
	if not isinstance(value, str):
		frappe.throw(_("Payment reference must be text."), frappe.ValidationError)
	value = value.strip()
	if len(value) > 140:
		frappe.throw(_("Payment reference must be at most 140 characters."), frappe.ValidationError)
	return value or None


def _submission_uuid(value):
	try:
		return str(uuid.UUID(str(value)))
	except (ValueError, TypeError, AttributeError):
		frappe.throw(_("Refresh the payment form and try again."), frappe.ValidationError)


def _money_precision():
	return int(frappe.get_precision("BG Sale", "grand_total") or 2)


def _money(value, label, *, positive=False):
	validate_number(value, label, minimum=0, minimum_exclusive=positive)
	precision = _money_precision()
	# Use Frappe's configured currency precision and rounding policy consistently
	# with Currency fields in this app.
	rounded = Decimal(str(flt(value, precision=precision)))
	validate_number(rounded, label, minimum=0)
	if positive and rounded <= 0:
		frappe.throw(_("{0} must remain positive at the configured currency precision.").format(label), frappe.ValidationError)
	return rounded


def _canonical_amount(value):
	return format(value.normalize(), "f")


def _fingerprint(*, sale, amount, payment_mode, reference):
	payload = {
		"sale": sale,
		"amount": _canonical_amount(amount),
		"payment_mode": payment_mode,
		"reference": reference,
	}
	serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _payment_record_context():
	return _authorized_payment_context.get()


def _payment_record_context_matches(doc):
	context = _payment_record_context()
	return bool(context) and all(
		doc.get(field) == value
		for field, value in context.items()
	)


@contextmanager
def _payment_record_scope(values):
	token = _authorized_payment_context.set(values.copy())
	try:
		yield
	finally:
		_authorized_payment_context.reset(token)


def _scoped_sale(name, garage, *, for_update=False):
	rows = frappe.get_list(
		"BG Sale",
		filters={"name": name, **({"garage": garage} if garage else {})},
		fields=["name"],
		limit_page_length=1,
	)
	if not rows:
		frappe.throw(_("Sale was not found."), frappe.DoesNotExistError)
	sale = frappe.get_doc("BG Sale", rows[0].name, for_update=for_update)
	if sale.garage != garage:
		frappe.throw(_("Sale was not found."), frappe.DoesNotExistError)
	return sale


def _recorded_total(sale_name, *, lock_rows=False):
	if not frappe.db.table_exists("BG Sale Payment"):
		return Decimal(0)
	query = "SELECT amount FROM `tabBG Sale Payment` WHERE sale = %s"
	if lock_rows and getattr(frappe.db, "db_type", None) != "sqlite":
		# A locking read sees the newest committed receipt even under MariaDB's
		# default repeatable-read isolation after waiting on the Sale row lock.
		query += " FOR UPDATE"
	rows = frappe.db.sql(query, sale_name)
	total = sum((Decimal(str(row[0] or 0)) for row in rows), Decimal(0))
	return _money(total, _("Recorded paid amount"))


def _sale_summary(sale):
	if sale.payment_ledger_status != "Tracked":
		return {
			"payment_ledger_status": "Unverified",
			"payment_status": sale.payment_status,
			"amount_paid": None,
			"outstanding": None,
			"payments": [],
		}
	precision = _money_precision()
	paid = _recorded_total(sale.name)
	total = _money(sale.grand_total or 0, _("Sale total"))
	outstanding = max(total - paid, Decimal(0))
	payments = frappe.get_list(
		"BG Sale Payment",
		filters={"sale": sale.name, "garage": sale.garage},
		fields=["name", "amount", "payment_mode", "reference", "creation", "owner"],
		order_by="creation asc",
		limit_page_length=0,
	)
	return {
		"payment_ledger_status": "Tracked",
		"payment_status": _status_for(paid, total),
		"amount_paid": flt(paid, precision=precision),
		"outstanding": flt(outstanding, precision=precision),
		"payments": payments,
	}


def collection_rows(start, end, garage):
	"""Return minimal payment rows for an authorized aggregate dashboard report."""
	if not frappe.db.table_exists("BG Sale Payment"):
		return []
	scope_sql = "1=1" if garage is None else "`garage` = %s"
	values = (start, end) if garage is None else (start, end, garage)
	return frappe.db.sql(
		f"""SELECT creation, amount, payment_mode FROM `tabBG Sale Payment`
		WHERE creation >= %s AND creation < %s AND {scope_sql}
		ORDER BY creation""",
		values,
	)


def monthly_collection_totals(year, garage):
	if not frappe.db.table_exists("BG Sale Payment"):
		return []
	scope_sql = "1=1" if garage is None else "`garage` = %s"
	values = (f"{year}-01-01 00:00:00", f"{year + 1}-01-01 00:00:00")
	if garage is not None:
		values += (garage,)
	if getattr(frappe.db, "db_type", None) == "sqlite":
		month_expr = "CAST(strftime('%m', creation) AS INTEGER)"
		year_expr = "CAST(strftime('%Y', creation) AS INTEGER)"
	else:
		month_expr = "MONTH(creation)"
		year_expr = "YEAR(creation)"
	return frappe.db.sql(
		f"""SELECT {month_expr} AS month, {year_expr} AS year, SUM(amount) AS total
		FROM `tabBG Sale Payment`
		WHERE creation >= %s AND creation < %s AND {scope_sql}
		GROUP BY {month_expr}, {year_expr}
		ORDER BY month""",
		values,
		as_dict=True,
	)


@frappe.whitelist(methods=["GET"])
def get_daily_collections(date):
	"""Return garage-scoped daily totals by recorded method, without payment references."""
	from bike_garage.bike_garage.api.dashboard import _get_dashboard_garage

	try:
		day = frappe.utils.getdate(date)
	except Exception:
		frappe.throw(_("Enter a valid report date."), frappe.ValidationError)
	start = f"{day} 00:00:00"
	end_day = frappe.utils.add_days(day, 1)
	end = f"{end_day} 00:00:00"
	garage = _get_dashboard_garage()
	require_payment_read_access(garage)
	rows = collection_rows(start, end, garage)
	by_mode = {mode: Decimal(0) for mode in sorted(PAYMENT_MODES)}
	for _, amount, mode in rows:
		if mode in by_mode:
			by_mode[mode] += Decimal(str(amount or 0))
	precision = _money_precision()
	return {
		"total": flt(sum(by_mode.values(), Decimal(0)), precision=precision),
		"by_mode": {mode: flt(value, precision=precision) for mode, value in by_mode.items()},
	}


def _status_for(paid, total):
	if paid <= 0:
		return "Pending"
	if paid >= total:
		return "Paid"
	return "Partially Paid"


def _update_sale_summary(sale, paid, total):
	precision = _money_precision()
	amount_paid = flt(paid, precision=precision)
	payment_status = _status_for(paid, total)
	frappe.db.set_value(
		"BG Sale",
		sale.name,
		{"amount_paid": amount_paid, "payment_status": payment_status},
		update_modified=False,
	)
	sale.amount_paid = amount_paid
	sale.payment_status = payment_status


def _existing_submission(key, garage, fingerprint):
	query = """SELECT name, garage, sale, amount, request_fingerprint
		FROM `tabBG Sale Payment` WHERE submission_key = %s"""
	if getattr(frappe.db, "db_type", None) != "sqlite":
		query += " FOR UPDATE"
	rows = frappe.db.sql(query, key)
	if not rows:
		return None
	name, row_garage, _row_sale, _amount, row_fingerprint = rows[0]
	if row_garage != garage:
		frappe.throw(_("This payment request could not be verified."), frappe.PermissionError)
	if row_fingerprint != fingerprint:
		frappe.throw(_("This retry key was already used for a different payment."), frappe.ValidationError)
	return {"name": name, "duplicate": True}


@frappe.whitelist(methods=["POST"])
def record_sale_payment(sale, amount, payment_mode, submission_key, reference=None):
	"""Record one receipt against a tracked Sale; retries are idempotent."""
	garage = require_payment_role()
	if not isinstance(payment_mode, str) or payment_mode not in PAYMENT_MODES:
		frappe.throw(_("Choose a valid payment method."), frappe.ValidationError)
	reference = _clean_reference(reference)
	key = _submission_uuid(submission_key)
	amount = _money(amount, _("Payment amount"), positive=True)
	fingerprint = _fingerprint(sale=sale, amount=amount, payment_mode=payment_mode, reference=reference)
	locked_sale = _scoped_sale(sale, garage, for_update=True)
	garage = locked_sale.garage
	require_payment_role(garage)
	if locked_sale.payment_ledger_status != "Tracked":
		frappe.throw(_("This legacy Sale has unverified payment history and must be reconciled before recording a payment."), frappe.ValidationError)
	existing = _existing_submission(key, garage, fingerprint)
	if existing:
		return {**existing, **_sale_summary(locked_sale)}
	total = _money(locked_sale.grand_total or 0, _("Sale total"))
	paid = _recorded_total(locked_sale.name, lock_rows=True)
	if amount > total - paid:
		frappe.throw(_("Payment exceeds the verified outstanding balance."), frappe.ValidationError)
	values = {
		"sale": locked_sale.name,
		"garage": garage,
		"amount": flt(amount, precision=_money_precision()),
		"payment_mode": payment_mode,
		"reference": reference,
		"submission_key": key,
		"request_fingerprint": fingerprint,
	}
	savepoint = f"bg_sale_payment_{uuid.uuid4().hex}"
	frappe.db.savepoint(savepoint)
	try:
		payment = frappe.get_doc({"doctype": "BG Sale Payment", **values})
		with _payment_record_scope(values):
			payment.insert(ignore_permissions=True)
		new_paid = paid + amount
		_update_sale_summary(locked_sale, new_paid, total)
		frappe.db.release_savepoint(savepoint)
		return {"name": payment.name, "duplicate": False, **_sale_summary(locked_sale)}
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point=savepoint)
		winner = _existing_submission(key, garage, fingerprint)
		if winner:
			return {**winner, **_sale_summary(locked_sale)}
		frappe.throw(_("This payment conflicts with an existing request."), frappe.ValidationError)
	except BaseException:
		frappe.db.rollback(save_point=savepoint)
		raise


@frappe.whitelist(methods=["GET"])
def get_sale_payment_history(sale):
	"""Return only the active garage's verified ledger, or an unverified legacy marker."""
	if frappe.session.user == "Administrator" or tenancy.is_platform_super_admin():
		locked_sale = frappe.get_doc("BG Sale", sale)
		require_payment_read_access(locked_sale.garage)
	else:
		garage = require_payment_role()
		locked_sale = _scoped_sale(sale, garage)
		require_payment_role(locked_sale.garage)
	return _sale_summary(locked_sale)


def ensure_sale_total_covers_recorded_payments(sale):
	"""Reject edits that would make recorded receipts exceed the sale total."""
	if not getattr(sale, "name", None) or not frappe.db.table_exists("BG Sale Payment"):
		return
	_lock_sale_row(sale.name)
	paid = _recorded_total(sale.name)
	total = _money(sale.grand_total or 0, _("Sale total"))
	if paid > total:
		frappe.throw(_("The Sale total cannot be reduced below its recorded payments."), frappe.ValidationError)


def prevent_sale_with_payments_from_deletion(doc, method=None):
	"""Keep a Sale with payment history; refunds/reversals need an approved policy."""
	if not frappe.db.table_exists("BG Sale Payment"):
		return
	_lock_sale_row(doc.name)
	if _recorded_total(doc.name, lock_rows=True) > 0:
		frappe.throw(
			_("This Sale has recorded payments and cannot be deleted. Refund/reversal policy must be implemented first."),
			frappe.ValidationError,
		)


def _lock_sale_row(sale_name):
	if getattr(frappe.db, "db_type", None) != "sqlite":
		frappe.db.sql("SELECT name FROM `tabBG Sale` WHERE name = %s FOR UPDATE", sale_name)

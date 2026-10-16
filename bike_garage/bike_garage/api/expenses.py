"""Website expense operations scoped to the active garage membership."""

import uuid
from datetime import date as calendar_date

import frappe
from frappe import _

from bike_garage import payments, tenancy
from bike_garage.numeric import validate_number


EXPENSE_TYPES = {
	"Rent", "Electricity", "Salary", "Tools & Equipment",
	"Maintenance", "Transport", "Miscellaneous",
}
PAYMENT_MODES = {"Cash", "UPI", "Card", "NEFT"}
DETAIL_FIELDS = [
	"name", "expense_type", "description", "date", "amount",
	"payment_mode", "paid_to", "notes",
]


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


def _get_for_garage(name, garage):
	if not isinstance(name, str) or not name.strip():
		frappe.throw(_("Expense was not found."), frappe.DoesNotExistError)
	rows = frappe.get_list(
		"BG Expense",
		filters={"garage": garage, "name": name.strip()},
		fields=DETAIL_FIELDS,
		limit_page_length=1,
	)
	if not rows:
		frappe.throw(_("Expense was not found."), frappe.DoesNotExistError)
	return rows[0]


@frappe.whitelist(methods=["GET"])
def get_expense(name):
	"""Return a single expense without revealing cross-garage record existence."""
	garage = tenancy.get_current_garage()
	payments.require_payment_read_access(garage)
	return _get_for_garage(name, garage)


@frappe.whitelist(methods=["POST"])
def create_expense(expense_type, description, date, amount, payment_mode="Cash", paid_to=None, notes=None, submission_key=None):
	"""Create an expense for the session garage; retries are idempotent by UUID."""
	garage = tenancy.get_current_garage()
	payments.require_payment_role(garage)
	if not isinstance(expense_type, str) or expense_type not in EXPENSE_TYPES:
		frappe.throw(_("Choose a valid expense type."), frappe.ValidationError)
	if not isinstance(payment_mode, str) or payment_mode not in PAYMENT_MODES:
		frappe.throw(_("Choose a valid payment mode."), frappe.ValidationError)
	description = _clean_text(description, _("Description"), required=True)
	paid_to = _clean_text(paid_to, _("Paid To"))
	notes = _clean_text(notes, _("Notes"), maximum=2000)
	if not isinstance(date, str) or not date.strip():
		frappe.throw(_("Enter a valid expense date."), frappe.ValidationError)
	try:
		date = calendar_date.fromisoformat(date.strip()).isoformat()
	except (TypeError, ValueError, OverflowError):
		frappe.throw(_("Enter a valid expense date."), frappe.ValidationError)
	validate_number(amount, _("Expense amount"), minimum=0)
	try:
		key = str(uuid.UUID(str(submission_key)))
	except (ValueError, TypeError, AttributeError):
		frappe.throw(_("Refresh the form and try again."), frappe.ValidationError)

	existing = frappe.get_list(
		"BG Expense", filters={"submission_key": key}, fields=["name", "garage"], limit_page_length=1
	)
	if existing:
		if existing[0].garage != garage:
			frappe.throw(_("This submission could not be verified."), frappe.PermissionError)
		return {"name": existing[0].name, "duplicate": True}

	doc = frappe.get_doc({
		"doctype": "BG Expense",
		"expense_type": expense_type,
		"description": description,
		"date": date,
		"amount": amount,
		"payment_mode": payment_mode,
		"paid_to": paid_to,
		"notes": notes,
		"submission_key": key,
		"garage": garage,
	})
	try:
		doc.insert()
	except frappe.DuplicateEntryError:
		# A unique DB index serializes simultaneous retries with the same key.
		winner = frappe.get_list(
			"BG Expense", filters={"submission_key": key}, fields=["name", "garage"], limit_page_length=1
		)
		if winner and winner[0].garage == garage:
			return {"name": winner[0].name, "duplicate": True}
		frappe.throw(_("This submission could not be verified."), frappe.PermissionError)
	return {"name": doc.name, "duplicate": False}

"""Shared validation for finite quantities and monetary values."""

from decimal import Decimal, InvalidOperation

import frappe
from frappe import _


def validate_number(
	value,
	label,
	*,
	allow_empty=False,
	minimum=None,
	minimum_exclusive=False,
	maximum=None,
):
	"""Reject malformed, non-finite, or out-of-range numeric input.

	The input value is not changed or rounded, preserving the DocField's own
	precision and currency behavior.
	"""
	if value is None or value == "":
		if allow_empty:
			return
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if isinstance(value, bool):
		frappe.throw(_("{0} must be a finite number.").format(label), frappe.ValidationError)
	try:
		number = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError):
		frappe.throw(_("{0} must be a finite number.").format(label), frappe.ValidationError)
	if not number.is_finite():
		frappe.throw(_("{0} must be a finite number.").format(label), frappe.ValidationError)
	if minimum is not None and (number <= Decimal(str(minimum)) if minimum_exclusive else number < Decimal(str(minimum))):
		operator = _("greater than") if minimum_exclusive else _("at least")
		frappe.throw(_("{0} must be {1} {2}.").format(label, operator, minimum), frappe.ValidationError)
	if maximum is not None and number > Decimal(str(maximum)):
		frappe.throw(_("{0} cannot exceed {1}.").format(label, maximum), frappe.ValidationError)

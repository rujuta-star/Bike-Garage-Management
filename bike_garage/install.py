"""Idempotent app setup for the platform role and workflow submission indexes."""

import frappe

from bike_garage.tenancy import PLATFORM_SUPER_ADMIN_ROLE


def ensure_platform_super_admin_role():
	if frappe.db.exists("Role", PLATFORM_SUPER_ADMIN_ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": PLATFORM_SUPER_ADMIN_ROLE,
			"desk_access": 0,
			"is_custom": 1,
			"disabled": 0,
		}
	).insert(ignore_permissions=True)


def after_install():
	ensure_platform_super_admin_role()
	ensure_expense_submission_index()
	ensure_stock_movement_submission_index()


def after_migrate():
	ensure_platform_super_admin_role()
	ensure_expense_submission_index()
	ensure_stock_movement_submission_index()


def ensure_expense_submission_index():
	"""Keep idempotency enforced by the database on every supported backend."""
	if frappe.db.table_exists("BG Expense") and frappe.db.has_column("BG Expense", "submission_key"):
		frappe.db.add_unique("BG Expense", ["submission_key"], "unique_bg_expense_submission_key")


def ensure_stock_movement_submission_index():
	"""Enforce movement retry idempotency after the additive DocType schema exists."""
	if frappe.db.table_exists("BG Stock Movement") and frappe.db.has_column("BG Stock Movement", "submission_key"):
		frappe.db.add_unique("BG Stock Movement", ["submission_key"], "unique_bg_stock_movement_submission_key")
		frappe.db.add_unique("BG Stock Movement", ["against_receipt"], "unique_bg_stock_movement_receipt_return")

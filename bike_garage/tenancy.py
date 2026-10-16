"""Server-side garage membership resolution.

This module deliberately does not accept a garage name from request data. A future
Platform Super Admin workflow must be implemented separately from tenant context.
"""

import frappe
from frappe import _


PLATFORM_SUPER_ADMIN_ROLE = "Platform Super Admin"


def is_platform_super_admin(user=None):
	"""Identify the explicit future platform role; this grants no tenant bypass."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	# Frappe reports every role for its built-in Administrator account. That
	# implicit root behavior must not count as explicit Platform Super Admin
	# authorization; Administrator's separate app policies remain unchanged.
	if user == "Administrator":
		return False

	try:
		return PLATFORM_SUPER_ADMIN_ROLE in frappe.get_roles(user)
	except Exception:
		frappe.throw(_("Unable to verify platform administrator role."), frappe.PermissionError)


def get_current_garage():
	"""Return the sole active garage assigned to the authenticated session user."""
	user = getattr(frappe.session, "user", None)
	if not user or user == "Guest":
		frappe.throw(_("An authenticated garage membership is required."), frappe.PermissionError)

	try:
		# The platform role is deliberately recognized separately but receives no
		# bypass here; platform-wide operations need their own explicit API/context.
		is_platform_super_admin(user)

		memberships = frappe.get_all(
			"BG Garage Membership",
			filters={"user": user, "status": "Active"},
			fields=["garage"],
			limit_page_length=2,
		)
		if len(memberships) != 1:
			frappe.throw(_("Exactly one active garage membership is required."), frappe.PermissionError)

		garage_name = memberships[0].get("garage")
		if not garage_name:
			frappe.throw(_("The active garage membership is incomplete."), frappe.PermissionError)

		garage_status = frappe.db.get_value("BG Garage", garage_name, "status")
		if garage_status != "Active":
			frappe.throw(_("The assigned garage is not active."), frappe.PermissionError)

		return garage_name
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.throw(_("Unable to verify the current garage membership."), frappe.PermissionError)

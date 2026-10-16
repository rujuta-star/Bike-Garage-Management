import frappe
from frappe import _
from frappe.sessions import get_csrf_token

from bike_garage import payments, tenancy


def get_context(context):
	"""Render the garage manager workspace only for an active Manager member."""
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.throw(_("Please login to access this page."), frappe.PermissionError)
	if tenancy.is_platform_super_admin():
		frappe.throw(_("Platform administrators must use the platform dashboard."), frappe.PermissionError)

	garage = tenancy.get_current_garage()
	membership_type = frappe.db.get_value(
		"BG Garage Membership",
		{"user": frappe.session.user, "garage": garage, "status": "Active"},
		"membership_type",
	)
	if membership_type != "Manager":
		frappe.throw(_("An active Garage Manager membership is required."), frappe.PermissionError)

	garage_doc = frappe.get_doc("BG Garage", garage)
	if garage_doc.status != "Active":
		frappe.throw(_("The assigned garage is not active."), frappe.PermissionError)

	frappe.redirect("/garage")

	context.user = frappe.session.user
	context.garage_name = garage_doc.garage_name
	context.can_view_financials = payments.can_read_payment_data(garage)
	context.csrf_token = get_csrf_token()

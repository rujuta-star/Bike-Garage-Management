import frappe
from frappe.sessions import get_csrf_token
from bike_garage.website import _dashboard_destination


def get_context(context):
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	context.title = "Bike Garage Management"
	context.dashboard_route = _dashboard_destination(frappe.session.user)

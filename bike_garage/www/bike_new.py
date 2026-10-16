import frappe
from frappe.sessions import get_csrf_token

from bike_garage import tenancy
from bike_garage.bike_garage.api.bikes import get_bike_form_options


def get_context(context):
	context.no_cache = 1
	tenancy.get_current_garage()
	context.csrf_token = get_csrf_token()
	context.customers = get_bike_form_options()
	context.title = "Add Bike"
	return context

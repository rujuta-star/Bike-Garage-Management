import frappe

from bike_garage import tenancy
from bike_garage.bike_garage.api.bikes import _get_bike


def get_context(context):
	context.no_cache = 1
	context.bike = _get_bike(frappe.form_dict.get("name"), tenancy.get_current_garage())
	context.title = "Bike " + context.bike.name
	return context

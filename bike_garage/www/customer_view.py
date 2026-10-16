import frappe

from bike_garage import tenancy
from bike_garage.bike_garage.api.customers import _get_customer


def get_context(context):
	context.no_cache = 1
	context.customer = _get_customer(frappe.form_dict.get("name"), tenancy.get_current_garage())
	context.title = "Customer " + context.customer.name
	return context

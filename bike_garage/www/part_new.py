import frappe
from frappe.sessions import get_csrf_token

from bike_garage import tenancy


def get_context(context):
	context.no_cache = 1
	tenancy.get_current_garage()
	context.csrf_token = get_csrf_token()
	context.title = "Add Spare Part"
	return context

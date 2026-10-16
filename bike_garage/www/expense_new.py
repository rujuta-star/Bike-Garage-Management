import frappe
from frappe.sessions import get_csrf_token

from bike_garage import payments, tenancy


def get_context(context):
	context.no_cache = 1
	garage = tenancy.get_current_garage()
	payments.require_payment_role(garage)
	context.csrf_token = get_csrf_token()
	context.today = frappe.utils.today()
	context.title = "Record Expense"
	return context

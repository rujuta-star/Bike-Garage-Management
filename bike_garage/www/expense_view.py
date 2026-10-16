import frappe

from bike_garage import payments, tenancy
from bike_garage.bike_garage.api.expenses import _get_for_garage


def get_context(context):
	context.no_cache = 1
	garage = tenancy.get_current_garage()
	payments.require_payment_read_access(garage)
	context.expense = _get_for_garage(frappe.form_dict.get("name"), garage)
	context.title = "Expense " + context.expense.name
	return context

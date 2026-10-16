import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import today
from uuid import uuid4

from bike_garage.bike_garage.api.inventory import require_inventory_role


def get_context(context):
	context.no_cache = 1
	context.garage = require_inventory_role()
	context.csrf_token = get_csrf_token()
	context.submission_key = str(uuid4())
	context.title = "Receive or Adjust Stock"
	context.today = today()
	return context

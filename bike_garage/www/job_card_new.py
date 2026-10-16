import frappe
from frappe.sessions import get_csrf_token

from bike_garage import tenancy
from bike_garage.bike_garage.api.garage_job_cards import get_job_card_form_options


def get_context(context):
	context.no_cache = 1
	# Require an active approved membership before rendering any tenant choices.
	tenancy.get_current_garage()
	context.csrf_token = get_csrf_token()
	context.options = get_job_card_form_options()
	context.title = "Create Job Card"
	return context

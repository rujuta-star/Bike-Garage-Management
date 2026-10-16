from frappe.sessions import get_csrf_token

from bike_garage.bike_garage.api.garage_job_cards import get_job_cards


def get_context(context):
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	context.job_cards = get_job_cards()
	context.title = "Job Cards"
	return context

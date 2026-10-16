import frappe
from frappe.sessions import get_csrf_token

from bike_garage.bike_garage.api.garage_job_cards import _get_job_card_for_current_garage


def get_context(context):
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	context.job = _get_job_card_for_current_garage(frappe.form_dict.get("name"))
	context.title = "Job Card " + context.job.name
	return context

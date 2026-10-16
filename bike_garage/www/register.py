import frappe
from frappe.sessions import get_csrf_token


def get_context(context):
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	frappe.local.response_headers["Referrer-Policy"] = "no-referrer"
	frappe.local.response_headers["Cache-Control"] = "no-store"

import frappe
from frappe.sessions import get_csrf_token

from bike_garage.bike_garage.api.onboarding import _require_platform_super_admin


def get_context(context):
	context.no_cache = 1
	_require_platform_super_admin()
	context.csrf_token = get_csrf_token()
	context.user = frappe.session.user

"""Website routing that exposes the public landing page to garage visitors."""

import frappe
from bike_garage import tenancy


def get_home_page(user):
	if user == "Guest":
		return "index"

	request = getattr(frappe.local, "request", None)
	if request and getattr(request, "path", "") == "/api/method/login":
		try:
			if tenancy.is_platform_super_admin(user):
				return "platform_admin"
		except Exception:
			# A role lookup failure must never grant a privileged landing route.
			return "index"

	if frappe.get_cached_value("User", user, "user_type") != "Website User":
		# Keep Frappe's standard home-page handling for System Users.
		return

	# The public root remains the landing page even for signed-in users. For
	# Frappe's successful login response, send only a verified active member to
	# the protected dashboard; pending/unlinked accounts return to the landing.
	if request and getattr(request, "path", "") == "/api/method/login":
		try:
			memberships = frappe.get_all(
				"BG Garage Membership",
				filters={"user": user, "status": "Active"},
				fields=["garage"],
				limit_page_length=2,
			)
			if len(memberships) == 1 and memberships[0].get("garage"):
				if frappe.db.get_value("BG Garage", memberships[0]["garage"], "status") == "Active":
					return "garage"
		except Exception:
			# A lookup failure must never grant dashboard access or fail login.
			pass

	return "index"


def resolve_website_path(path):
	"""Resolve root requests to the public landing page for every user.

	Frappe resolves `/` through its configurable home-page selection. Resolve
	that one path directly, while leaving every other route to Frappe's normal
	website resolver.
	"""
	request = getattr(frappe.local, "request", None)
	if (
		request
		and (path or "").strip("/") in {"", "index"}
		and getattr(request, "method", "GET") in {"GET", "HEAD"}
	):
		frappe.local.path = "index"
		return "index"

	from frappe.website.path_resolver import resolve_path

	return resolve_path(path)


def _dashboard_destination(user):
	"""Resolve a dashboard only after checking the user's server-side authority."""
	if not user or user == "Guest":
		return None

	if tenancy.is_platform_super_admin(user):
		return "/platform_admin"

	if frappe.get_cached_value("User", user, "user_type") != "Website User":
		return None

	try:
		garage = tenancy.get_current_garage()
	except Exception:
		# Missing, ambiguous, inactive, or unverifiable membership grants no route.
		return None
	# All verified garage members use the same operational workspace. Managers
	# previously received the separate overview route, which now redirects here.
	return "/garage"


@frappe.whitelist()
def get_dashboard_route():
	"""Return the current user's authorized website dashboard, if any."""
	return _dashboard_destination(getattr(frappe.session, "user", None))

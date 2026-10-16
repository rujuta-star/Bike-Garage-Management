"""Session-bound presentation preferences for the Bike Garage website UI."""

import frappe
from frappe import _
from frappe.model.document import clear_document_cache


SUPPORTED_LANGUAGES = {"en", "hi", "mr"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_dashboard_language(language=None):
	"""Persist a language supported by the dashboard's shipped translation catalogs."""
	if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
		frappe.throw(_("Choose English, Hindi, or Marathi."), frappe.ValidationError)

	user = frappe.session.user
	if user == "Guest":
		# Frappe's request language resolver reads this cookie for guest requests.
		frappe.local.cookie_manager.set_cookie("preferred_language", language)
	else:
		# The endpoint can update only the authenticated session user's preference.
		frappe.db.set_value("User", user, "language", language, update_modified=False)
		clear_document_cache("User", user)

	frappe.local.lang = language
	return {"language": language}

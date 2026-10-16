"""Website customer operations limited to the active garage."""

from datetime import date as calendar_date

import frappe
from frappe import _

from bike_garage import tenancy


GENDERS = {"Male", "Female", "Other"}
CUSTOMER_FIELDS = ["name", "customer_name", "phone", "email", "address", "gender", "date_of_birth", "notes"]


def _text(value, label, *, required=False, maximum=140):
	if value is None:
		value = ""
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)
	value = value.strip()
	if required and not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > maximum:
		frappe.throw(_("{0} must be at most {1} characters.").format(label, maximum), frappe.ValidationError)
	return value or None


def _get_customer(name, garage):
	if not isinstance(name, str) or not name.strip():
		frappe.throw(_("Customer was not found."), frappe.DoesNotExistError)
	rows = frappe.get_list(
		"BG Customer", filters={"garage": garage, "name": name.strip()}, fields=CUSTOMER_FIELDS, limit_page_length=1
	)
	if not rows:
		frappe.throw(_("Customer was not found."), frappe.DoesNotExistError)
	return rows[0]


@frappe.whitelist(methods=["GET"])
def get_customer(name):
	return _get_customer(name, tenancy.get_current_garage())


@frappe.whitelist(methods=["POST"])
def create_customer(customer_name, phone, email=None, address=None, gender=None, date_of_birth=None, notes=None):
	garage = tenancy.get_current_garage()
	customer_name = _text(customer_name, _("Customer Name"), required=True)
	phone = _text(phone, _("Phone Number"), required=True, maximum=40)
	email = _text(email, _("Email"), maximum=140)
	address = _text(address, _("Address"), maximum=2000)
	notes = _text(notes, _("Notes"), maximum=2000)
	if gender and (not isinstance(gender, str) or gender not in GENDERS):
		frappe.throw(_("Choose a valid gender option."), frappe.ValidationError)
	if date_of_birth:
		if not isinstance(date_of_birth, str):
			frappe.throw(_("Enter a valid date of birth."), frappe.ValidationError)
		try:
			date_of_birth = calendar_date.fromisoformat(date_of_birth.strip()).isoformat()
		except (TypeError, ValueError, OverflowError):
			frappe.throw(_("Enter a valid date of birth."), frappe.ValidationError)
	else:
		date_of_birth = None

	doc = frappe.get_doc({
		"doctype": "BG Customer", "customer_name": customer_name, "phone": phone,
		"email": email, "address": address, "gender": gender or None,
		"date_of_birth": date_of_birth, "notes": notes, "garage": garage,
	})
	doc.insert()
	return {"name": doc.name}

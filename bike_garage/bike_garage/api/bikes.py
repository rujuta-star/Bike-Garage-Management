"""Website bike operations with server-validated garage customer links."""

from datetime import date as calendar_date

import frappe
from frappe import _

from bike_garage import tenancy


BRANDS = {"Hero", "Honda", "Bajaj", "TVS", "Suzuki", "Royal Enfield", "Yamaha", "KTM", "Other"}
BIKE_FIELDS = [
	"name", "customer", "registration_no", "bike_brand", "bike_model", "year", "color",
	"engine_no", "chassis_no", "km_reading", "last_service_date", "notes",
]


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


def _integer(value, label):
	if value in (None, ""):
		return None
	if isinstance(value, bool):
		frappe.throw(_("{0} must be a whole number.").format(label), frappe.ValidationError)
	try:
		number = int(value)
	except (TypeError, ValueError, OverflowError):
		frappe.throw(_("{0} must be a whole number.").format(label), frappe.ValidationError)
	if str(number) != str(value).strip() or number < 0:
		frappe.throw(_("{0} must be a nonnegative whole number.").format(label), frappe.ValidationError)
	return number


def _get_bike(name, garage):
	if not isinstance(name, str) or not name.strip():
		frappe.throw(_("Bike was not found."), frappe.DoesNotExistError)
	rows = frappe.get_list(
		"BG Bike", filters={"garage": garage, "name": name.strip()}, fields=BIKE_FIELDS, limit_page_length=1
	)
	if not rows:
		frappe.throw(_("Bike was not found."), frappe.DoesNotExistError)
	return rows[0]


@frappe.whitelist(methods=["GET"])
def get_bike_form_options():
	garage = tenancy.get_current_garage()
	return frappe.get_list(
		"BG Customer", filters={"garage": garage}, fields=["name", "customer_name"],
		order_by="customer_name asc", limit_page_length=500,
	)


@frappe.whitelist(methods=["GET"])
def get_bike(name):
	return _get_bike(name, tenancy.get_current_garage())


@frappe.whitelist(methods=["POST"])
def create_bike(customer, registration_no, bike_model, bike_brand=None, year=None, color=None,
		engine_no=None, chassis_no=None, km_reading=None, last_service_date=None, notes=None):
	garage = tenancy.get_current_garage()
	if not isinstance(customer, str) or not customer.strip():
		frappe.throw(_("Choose a customer."), frappe.ValidationError)
	registration_no = _text(registration_no, _("Registration Number"), required=True)
	bike_model = _text(bike_model, _("Bike Model"), required=True)
	color = _text(color, _("Color"))
	engine_no = _text(engine_no, _("Engine Number"))
	chassis_no = _text(chassis_no, _("Chassis Number"))
	notes = _text(notes, _("Notes"), maximum=2000)
	if bike_brand and (not isinstance(bike_brand, str) or bike_brand not in BRANDS):
		frappe.throw(_("Choose a valid bike brand."), frappe.ValidationError)
	year = _integer(year, _("Year"))
	km_reading = _integer(km_reading, _("Current KM Reading"))
	if last_service_date:
		if not isinstance(last_service_date, str):
			frappe.throw(_("Enter a valid service date."), frappe.ValidationError)
		try:
			last_service_date = calendar_date.fromisoformat(last_service_date.strip()).isoformat()
		except (TypeError, ValueError, OverflowError):
			frappe.throw(_("Enter a valid service date."), frappe.ValidationError)
	else:
		last_service_date = None

	doc = frappe.get_doc({
		"doctype": "BG Bike", "customer": customer.strip(), "registration_no": registration_no,
		"bike_model": bike_model, "bike_brand": bike_brand or None, "year": year, "color": color,
		"engine_no": engine_no, "chassis_no": chassis_no, "km_reading": km_reading,
		"last_service_date": last_service_date, "notes": notes, "garage": garage,
	})
	doc.insert()
	return {"name": doc.name}

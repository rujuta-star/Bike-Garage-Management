"""Website spare-part catalog creation; stock is never accepted from clients."""

import frappe
from frappe import _

from bike_garage import tenancy
from bike_garage.numeric import validate_number


CATEGORIES = {
	"Lubricant", "Brakes", "Filter", "Ignition", "Drive", "Electrical",
	"Body", "Suspension", "Controls", "Other",
}
GST_RATES = {"0", "5", "12", "18", "28"}
UNITS = {"Pcs", "Litre", "Set", "Pair", "Kg", "Metre"}


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


@frappe.whitelist(methods=["POST"])
def create_spare_part(part_name, selling_price, category=None, brand=None, purchase_price=None,
		gst_rate="18", min_stock_qty="5", unit="Pcs", description=None):
	"""Add a catalog item at zero stock; receipts use a separate future workflow."""
	garage = tenancy.get_current_garage()
	part_name = _text(part_name, _("Part Name"), required=True)
	brand = _text(brand, _("Brand"))
	description = _text(description, _("Description"), maximum=2000)
	if category and (not isinstance(category, str) or category not in CATEGORIES):
		frappe.throw(_("Choose a valid part category."), frappe.ValidationError)
	if not isinstance(gst_rate, str) or gst_rate not in GST_RATES:
		frappe.throw(_("Choose a valid GST rate."), frappe.ValidationError)
	if not isinstance(unit, str) or unit not in UNITS:
		frappe.throw(_("Choose a valid unit."), frappe.ValidationError)
	validate_number(purchase_price, _("Purchase Price"), allow_empty=True, minimum=0)
	validate_number(selling_price, _("Selling Price"), minimum=0)
	validate_number(min_stock_qty, _("Minimum Stock Quantity"), allow_empty=True, minimum=0)

	doc = frappe.get_doc({
		"doctype": "BG Spare Part", "part_name": part_name, "category": category or None,
		"brand": brand, "purchase_price": purchase_price or 0, "selling_price": selling_price,
		"gst_rate": gst_rate, "stock_qty": 0, "min_stock_qty": min_stock_qty or 0,
		"unit": unit, "description": description, "garage": garage,
	})
	doc.insert()
	return {"name": doc.name, "stock_qty": 0}

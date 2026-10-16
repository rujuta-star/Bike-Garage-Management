from decimal import Decimal, InvalidOperation

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from bike_garage.numeric import validate_number
from bike_garage.stock import _is_historical_import_active, _is_stock_qty_update_authorized


class BGSparePart(Document):
    def validate(self):
        validate_number(self.purchase_price, "Purchase price", allow_empty=True, minimum=0)
        validate_number(self.selling_price, "Selling price", minimum=0)
        validate_number(self.min_stock_qty, "Minimum stock quantity", allow_empty=True, minimum=0)
        validate_number(self.stock_qty, "Stock quantity", allow_empty=True, minimum=0)
        if self.gst_rate not in (None, ""):
            try:
                gst_rate = Decimal(str(self.gst_rate))
            except (InvalidOperation, TypeError, ValueError):
                frappe.throw("Select a supported GST rate.", frappe.ValidationError)
            if not gst_rate.is_finite() or gst_rate not in {
                Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")
            }:
                frappe.throw("Select a supported GST rate.", frappe.ValidationError)

        if self.is_new():
            if flt(self.stock_qty) and not _is_historical_import_active():
                frappe.throw("Set initial stock through a stock adjustment.")
            return

        previous = self.get_doc_before_save()
        if previous is None:
            frappe.throw("Unable to verify stock quantity. Reload the spare part and try again.")

        if flt(self.stock_qty) != flt(previous.stock_qty) and not _is_stock_qty_update_authorized(self.name):
            frappe.throw("Stock quantity can only be changed through the stock service.")

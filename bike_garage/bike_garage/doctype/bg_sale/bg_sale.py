import frappe
from frappe.model.document import Document
from frappe.utils import flt
from bike_garage import payments
from bike_garage.numeric import validate_number

class BGSale(Document):
    def validate(self):
        validate_number(self.labour_charges, "Labour charges", allow_empty=True, minimum=0)
        if self.is_new():
            if getattr(frappe.flags, "in_import", False):
                # Preserve legacy snapshots without treating their historical status
                # or payment mode as evidence in the new ledger.
                self.payment_ledger_status = "Unverified"
                self.amount_paid = None
            else:
                # Creating an operational sale is never evidence that payment was received.
                self.payment_status = "Pending"
                self.payment_mode = None
                self.payment_ledger_status = "Tracked"
                self.amount_paid = 0
                for item in self.items:
                    part = frappe.get_list(
                        "BG Spare Part",
                        filters={"name": item.part, "garage": self.garage},
                        fields=["selling_price", "gst_rate"],
                        limit_page_length=1,
                    )
                    if not part:
                        frappe.throw(
                            "Every sale item must be an available part from this garage.",
                            frappe.PermissionError,
                        )
                    item.rate = part[0].selling_price
                    item.gst_rate = part[0].gst_rate
        else:
            previous = self.get_doc_before_save()
            if previous and (
                self.payment_status != previous.payment_status
                or self.payment_mode != previous.payment_mode
                or self.payment_ledger_status != previous.payment_ledger_status
                or self.amount_paid != previous.amount_paid
            ):
                frappe.throw(
                    "Sale payment fields can only be changed by the authorized payment ledger.",
                    frappe.PermissionError,
                )

    def before_save(self):
        self.calculate_totals()
        if not self.is_new():
            payments.ensure_sale_total_covers_recorded_payments(self)

    def calculate_totals(self):
        subtotal = 0
        gst_total = 0
        for item in self.items:
            validate_number(item.qty, "Item quantity", minimum=0, minimum_exclusive=True)
            validate_number(item.rate, "Item rate", allow_empty=True, minimum=0)
            validate_number(item.gst_rate, "GST rate", allow_empty=True, minimum=0, maximum=100)
            amount = (item.qty or 0) * (item.rate or 0)
            validate_number(amount, "Item amount", minimum=0)
            item.amount = amount
            subtotal += item.amount
            validate_number(subtotal, "Sale subtotal", minimum=0)
            # Select fields arrive as strings in Frappe documents.
            gst_amount = item.amount * (flt(item.gst_rate or 0) / 100)
            validate_number(gst_amount, "GST amount", minimum=0)
            gst_total += gst_amount
            validate_number(gst_total, "Total GST amount", minimum=0)
        self.subtotal = subtotal
        self.gst_amount = gst_total
        grand_total = subtotal + gst_total + (self.labour_charges or 0)
        validate_number(grand_total, "Sale total", minimum=0)
        self.grand_total = grand_total

import frappe
from frappe.model.document import Document
from bike_garage.numeric import validate_number

class BGSaleItem(Document):
    def validate(self):
        validate_number(self.qty, "Item quantity", minimum=0, minimum_exclusive=True)
        validate_number(self.rate, "Item rate", allow_empty=True, minimum=0)
        validate_number(self.gst_rate, "GST rate", allow_empty=True, minimum=0, maximum=100)
        validate_number(self.amount, "Item amount", allow_empty=True, minimum=0)

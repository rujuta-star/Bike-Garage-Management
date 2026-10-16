import frappe
from frappe.model.document import Document
from bike_garage.numeric import validate_number

class BGJobCardPart(Document):
    def validate(self):
        validate_number(self.qty, "Part quantity", minimum=0, minimum_exclusive=True)
        validate_number(self.rate, "Part rate", allow_empty=True, minimum=0)
        validate_number(self.amount, "Part amount", allow_empty=True, minimum=0)

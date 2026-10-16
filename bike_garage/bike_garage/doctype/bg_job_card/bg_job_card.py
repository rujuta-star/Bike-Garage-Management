import frappe
from frappe.model.document import Document
from bike_garage.numeric import validate_number

class BGJobCard(Document):
    def validate(self):
        validate_number(self.labour_charges, "Labour charges", allow_empty=True, minimum=0)
        validate_number(self.amount_paid, "Amount paid", allow_empty=True, minimum=0)

    def before_save(self):
        self.calculate_totals()
        self.set_payment_status()

    def calculate_totals(self):
        parts_total = 0
        for part in self.parts:
            validate_number(part.qty, "Part quantity", minimum=0, minimum_exclusive=True)
            validate_number(part.rate, "Part rate", allow_empty=True, minimum=0)
            amount = (part.qty or 0) * (part.rate or 0)
            validate_number(amount, "Part amount", minimum=0)
            part.amount = amount
            parts_total += part.amount
            validate_number(parts_total, "Parts total", minimum=0)
        self.parts_total = parts_total
        grand_total = parts_total + (self.labour_charges or 0)
        validate_number(grand_total, "Job Card total", minimum=0)
        self.grand_total = grand_total

    def set_payment_status(self):
        paid = self.amount_paid or 0
        if self.grand_total and paid >= self.grand_total:
            self.payment_status = "Paid"
        elif paid > 0:
            self.payment_status = "Partially Paid"
        else:
            self.payment_status = "Unpaid"

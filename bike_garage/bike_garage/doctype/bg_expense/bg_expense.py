import frappe
from frappe.model.document import Document
from bike_garage.numeric import validate_number
class BGExpense(Document):
    def validate(self):
        validate_number(self.amount, "Expense amount", minimum=0)

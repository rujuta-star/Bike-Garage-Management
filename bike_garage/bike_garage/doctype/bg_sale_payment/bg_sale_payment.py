import frappe
from frappe import _
from frappe.model.document import Document

from bike_garage import payments


class BGSalePayment(Document):
	def validate(self):
		if not payments._payment_record_context_matches(self):
			frappe.throw(
				_("Sale payment records must be created through the authorized payment operation."),
				frappe.PermissionError,
			)
		if not self.is_new():
			frappe.throw(_("Sale payment records are append-only."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Sale payment records cannot be deleted."), frappe.PermissionError)

import frappe
from frappe import _
from frappe.model.document import Document
from bike_garage.numeric import validate_number


class BGSubscriptionPlan(Document):
	def validate(self):
		self.plan_name = (self.plan_name or "").strip()
		if not self.plan_name or len(self.plan_name) > 140:
			frappe.throw(_("Plan name is required and must be 140 characters or fewer."), frappe.ValidationError)
		if not isinstance(self.status, str) or self.status not in {"Active", "Inactive"}:
			frappe.throw(_("Unsupported subscription plan status."), frappe.ValidationError)
		if not isinstance(self.billing_period, str) or self.billing_period not in {"Monthly", "Quarterly", "Yearly"}:
			frappe.throw(_("Unsupported billing period."), frappe.ValidationError)
		validate_number(self.amount, _("Plan amount"), minimum=0)
		if not self.currency or not frappe.db.exists("Currency", self.currency):
			frappe.throw(_("Select an existing currency."), frappe.ValidationError)

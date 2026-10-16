import frappe
from frappe import _
from frappe.model.document import Document

from bike_garage import stock
from bike_garage.numeric import validate_number
from bike_garage.bike_garage.api.inventory import _request_fingerprint, _submission_uuid, require_inventory_role


MOVEMENT_TYPES = {
	"Purchase Receipt",
	"Positive Adjustment",
	"Negative Adjustment",
	"Supplier Return",
	"Sale Consumption",
	"Sale Restoration",
	"Job Card Consumption",
	"Job Card Restoration",
}
SOURCE_DOCTYPES = {
	"Sale Consumption": "BG Sale",
	"Sale Restoration": "BG Sale",
	"Job Card Consumption": "BG Job Card",
	"Job Card Restoration": "BG Job Card",
}


class BGStockMovement(Document):
	def validate(self):
		audit = stock._source_stock_audit_context(self)
		if not audit:
			require_inventory_role(self.garage)
		if self.movement_type not in MOVEMENT_TYPES:
			frappe.throw(_("Choose a valid stock movement type."), frappe.ValidationError)
		validate_number(self.qty, _("Quantity"), minimum=0, minimum_exclusive=True)
		if self.movement_type in SOURCE_DOCTYPES:
			if not audit or self.source_doctype != SOURCE_DOCTYPES[self.movement_type]:
				frappe.throw(_("Source-linked stock movements can only be created by their source workflow."), frappe.PermissionError)
			if not self.source_document or not self.source_event:
				frappe.throw(_("Source document and event are required."), frappe.ValidationError)
			if self.source_event not in {"Updated", "Cancelled", "Reactivated", "Deleted"}:
				frappe.throw(_("Invalid source event."), frappe.ValidationError)
			if any((self.unit_cost, self.supplier, self.reference, self.against_receipt)):
				frappe.throw(_("Source-linked movements cannot contain receipt fields."), frappe.ValidationError)
			if frappe.db.get_value(self.source_doctype, self.source_document, "garage") != self.garage:
				frappe.throw(_("The source document must belong to this garage."), frappe.PermissionError)
			if self.stock_delta() != audit["after"] - audit["before"]:
				frappe.throw(_("The recorded source delta does not match the stock change."), frappe.ValidationError)
		elif self.source_doctype or self.source_document or self.source_event:
			frappe.throw(_("Source references are reserved for audited Sale and Job Card changes."), frappe.PermissionError)
		elif self.movement_type == "Purchase Receipt":
			validate_number(self.unit_cost, _("Unit cost"), minimum=0)
			if self.against_receipt:
				frappe.throw(_("A purchase receipt cannot reference another receipt."), frappe.ValidationError)
		elif self.unit_cost not in (None, ""):
			frappe.throw(_("Unit cost is recorded only on purchase receipts."), frappe.ValidationError)

		if self.movement_type == "Supplier Return":
			if not self.against_receipt:
				frappe.throw(_("Choose the original purchase receipt for this return."), frappe.ValidationError)
			if not self.supplier or not self.reference:
				frappe.throw(_("Supplier and return reference are required."), frappe.ValidationError)
		elif self.against_receipt:
			frappe.throw(_("Only a supplier return can reference an original receipt."), frappe.ValidationError)

		if not isinstance(self.reason, str) or not self.reason.strip():
			frappe.throw(_("A reason is required for every stock movement."), frappe.ValidationError)
		if len(self.reason.strip()) > 2000:
			frappe.throw(_("Reason must be at most 2000 characters."), frappe.ValidationError)
		for fieldname, maximum in (("supplier", 140), ("reference", 140)):
			value = self.get(fieldname)
			if value and (not isinstance(value, str) or len(value.strip()) > maximum):
				frappe.throw(_("{0} must be at most {1} characters.").format(fieldname.title(), maximum), frappe.ValidationError)

		if self.docstatus == 1:
			if _submission_uuid(self.submission_key) != self.submission_key:
				frappe.throw(_("A valid submission key is required."), frappe.ValidationError)
			expected = _request_fingerprint(
				part=self.part,
				movement_type=self.movement_type,
				qty=self.qty,
				unit_cost=self.unit_cost if self.movement_type == "Purchase Receipt" else None,
				supplier=(self.supplier or "").strip() or None,
				reference=(self.reference or "").strip() or None,
				against_receipt=self.against_receipt,
				reason=self.reason.strip(),
				source_doctype=self.source_doctype or None,
				source_document=self.source_document or None,
				source_event=self.source_event or None,
			)
			if self.request_fingerprint != expected:
				frappe.throw(_("Stock movements must be submitted through the authorized inventory operation."), frappe.PermissionError)

	def stock_delta(self):
		return -self.qty if self.movement_type in {
			"Negative Adjustment", "Supplier Return", "Sale Consumption", "Job Card Consumption"
		} else self.qty

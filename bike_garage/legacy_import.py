"""Reviewed, non-destructive importer for the supplied legacy Bike Garage snapshot.

This module never executes SQL. It accepts only a pinned dump made of INSERTs
for the expected tables, maps every tenant-owned parent to the staging demo
garage, and imports through normal Frappe documents and validators. Historical
stock is treated as an end-of-snapshot balance; automatic historical
consumption deltas are suppressed only inside the private import scope.

The dry-run mode materializes documents inside a database savepoint and always
rolls it back. No file attachment payloads are present in the supplied dump.
"""

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
from pathlib import Path
import re
from uuid import uuid4

import frappe

from bike_garage import stock


STAGING_SITE = "bike-garage-staging.local"
TARGET_GARAGE = "BG-DEMO-LEGACY-2026"
SOURCE_PATH = Path("/mnt/c/Users/rujut/Downloads/bike-garage-data.sql")
SOURCE_SHA256 = "470464d241103e266f5f4f329fba48b4180f8087f8c2fc88556dd20e8405483d"

EXPECTED_SOURCE_COUNTS = {
	"tabBG Bike": 55,
	"tabBG Customer": 40,
	"tabBG Expense": 45,
	"tabBG Job Card": 100,
	"tabBG Job Card Part": 199,
	"tabBG Sale": 120,
	"tabBG Sale Item": 240,
	"tabBG Spare Part": 30,
	"tabFile": 55,
	"tabSeries": 1,
	"tabSingles": 19,
}

PARENT_TABLES = {
	"tabBG Customer": ("BG Customer", (
		"customer_name", "phone", "email", "address", "gender", "date_of_birth", "notes",
	)),
	"tabBG Bike": ("BG Bike", (
		"customer", "registration_no", "bike_brand", "bike_model", "year", "color",
		"engine_no", "chassis_no", "km_reading", "last_service_date", "notes",
	)),
	"tabBG Spare Part": ("BG Spare Part", (
		"part_name", "category", "brand", "purchase_price", "selling_price", "gst_rate",
		"stock_qty", "min_stock_qty", "unit", "description",
	)),
	"tabBG Job Card": ("BG Job Card", (
		"customer", "phone", "bike", "registration_no", "mechanic", "status", "date",
		"estimated_delivery", "km_reading", "problem_description", "parts_total",
		"labour_charges", "grand_total", "payment_status", "payment_mode", "amount_paid", "notes",
	)),
	"tabBG Sale": ("BG Sale", (
		"customer", "phone", "date", "job_card", "payment_mode", "payment_status", "subtotal",
		"gst_amount", "labour_charges", "grand_total", "notes",
	)),
	"tabBG Expense": ("BG Expense", (
		"expense_type", "description", "date", "amount", "payment_mode", "paid_to", "notes",
	)),
}

CHILD_TABLES = {
	"tabBG Job Card Part": ("BG Job Card", "parts", "part", "qty", "rate", "amount"),
	"tabBG Sale Item": ("BG Sale", "items", "part", "qty", "rate", "gst_rate", "amount"),
}

NUMERIC_FIELDS = {
	"BG Bike": {"year", "km_reading"},
	"BG Spare Part": {"purchase_price", "selling_price", "stock_qty", "min_stock_qty"},
	"BG Job Card": {"km_reading", "parts_total", "labour_charges", "grand_total", "amount_paid"},
	"BG Job Card Part": {"qty", "rate", "amount"},
	"BG Sale": {"subtotal", "gst_amount", "labour_charges", "grand_total"},
	"BG Sale Item": {"qty", "rate", "amount"},
	"BG Expense": {"amount"},
}
INTEGER_FIELDS = {("BG Bike", "year")}

IGNORED_TABLES = frozenset({"tabFile", "tabSeries", "tabSingles"})
ALLOWED_DELETE_TABLES = frozenset({
	"tabBG Bike", "tabBG Customer", "tabBG Expense", "tabBG Job Card",
	"tabBG Job Card Part", "tabBG Sale", "tabBG Sale Item", "tabBG Spare Part",
	"tabFile", "tabSingles",
})


class LegacyImportError(Exception):
	"""Safe, non-sensitive diagnostic for a rejected legacy snapshot."""


def _decode_sql_value(source, index):
	length = len(source)
	if index >= length:
		raise LegacyImportError("Unexpected end of SQL value list.")

	if source[index] == "'":
		index += 1
		value = []
		while index < length:
			char = source[index]
			if char == "\\":
				index += 1
				if index >= length:
					raise LegacyImportError("Invalid SQL string escape.")
				escaped = source[index]
				value.append({"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}.get(escaped, escaped))
				index += 1
				continue
			if char == "'":
				if index + 1 < length and source[index + 1] == "'":
					value.append("'")
					index += 2
					continue
				return "".join(value), index + 1
			value.append(char)
			index += 1
		raise LegacyImportError("Unterminated SQL string value.")

	start = index
	while index < length and source[index] not in ",)":
		index += 1
	token = source[start:index].strip()
	if not token:
		raise LegacyImportError("Empty SQL value.")
	return (None if token.upper() == "NULL" else token), index


def _parse_values(source, expected_columns, *, allow_trailing_upsert=False):
	rows = []
	index = 0
	length = len(source)
	while index < length:
		while index < length and (source[index].isspace() or source[index] == ","):
			index += 1
		if index >= length or source[index] == ";":
			break
		if source[index] != "(":
			raise LegacyImportError("Unsupported SQL value syntax.")
		index += 1
		values = []
		while True:
			while index < length and source[index].isspace():
				index += 1
			value, index = _decode_sql_value(source, index)
			values.append(value)
			while index < length and source[index].isspace():
				index += 1
			if index >= length:
				raise LegacyImportError("Unterminated SQL row.")
			if source[index] == ",":
				index += 1
				continue
			if source[index] == ")":
				index += 1
				break
			raise LegacyImportError("Unsupported SQL row delimiter.")
		if len(values) != expected_columns:
			raise LegacyImportError("SQL column and value counts do not match.")
		rows.append(values)
		while index < length and source[index].isspace():
			index += 1
		if index < length and source[index] not in ",;":
			if allow_trailing_upsert and source[index:].lstrip().upper().startswith("ON DUPLICATE KEY UPDATE "):
				break
			raise LegacyImportError(f"Unsupported SQL statement suffix at offset {index} (character code {ord(source[index])}).")
	return rows


def _read_snapshot(path=SOURCE_PATH):
	path = Path(path)
	try:
		data = path.read_bytes()
	except OSError as exc:
		raise LegacyImportError("The approved legacy SQL dump could not be read.") from exc
	if sha256(data).hexdigest() != SOURCE_SHA256:
		raise LegacyImportError("The legacy dump hash does not match the reviewed source.")

	counts = {}
	rows = {table: [] for table in PARENT_TABLES}
	for table in CHILD_TABLES:
		rows[table] = []
	ignored_counts = {table: 0 for table in IGNORED_TABLES}
	delete_count = 0

	for line in data.decode("utf-8").splitlines():
		statement = line.strip()
		if not statement or statement.startswith(("--", "/*", "*/")):
			continue
		insert = re.match(r"INSERT\s+INTO\s+`([^`]+)`\s*\((.*?)\)\s*VALUES\s*(.*);\s*$", statement, re.I)
		if insert:
			table, column_sql, values_sql = insert.groups()
			if table not in rows and table not in IGNORED_TABLES:
				raise LegacyImportError("The dump contains an unexpected INSERT table.")
			columns = re.findall(r"`([^`]+)`", column_sql)
			if not columns or len(columns) != len(set(columns)):
				raise LegacyImportError("The dump contains invalid INSERT columns.")
			parsed = _parse_values(values_sql, len(columns), allow_trailing_upsert=table in IGNORED_TABLES)
			counts[table] = counts.get(table, 0) + len(parsed)
			if table in IGNORED_TABLES:
				ignored_counts[table] += len(parsed)
			else:
				rows[table].extend(dict(zip(columns, values)) for values in parsed)
			continue

		delete = re.match(r"DELETE\s+FROM\s+`([^`]+)`(?:\s|;|$)", statement, re.I)
		if delete:
			if delete.group(1) not in ALLOWED_DELETE_TABLES:
				raise LegacyImportError("The dump contains an unexpected destructive statement.")
			delete_count += 1
			continue
		if re.match(r"^(SET\s|START\s+TRANSACTION\s*;|COMMIT\s*;)", statement, re.I):
			continue
		raise LegacyImportError("The dump contains an unsupported statement; nothing was imported.")

	if counts != EXPECTED_SOURCE_COUNTS:
		raise LegacyImportError("The source row counts differ from the reviewed snapshot.")
	return rows, {
		"source_sha256": SOURCE_SHA256,
		"source_counts": dict(counts),
		"excluded_file_metadata_rows": ignored_counts["tabFile"],
		"excluded_settings_and_series_rows": ignored_counts["tabSingles"] + ignored_counts["tabSeries"],
		"ignored_delete_statements": delete_count,
	}


def _require_rows(rows, table):
	return rows[table]


def _unique_by_name(rows, table):
	result = {}
	for row in _require_rows(rows, table):
		name = row.get("name")
		if not name or name in result:
			raise LegacyImportError("The snapshot has a missing or duplicate record identifier.")
		result[name] = row
	return result


def _same_customer(source_name, customer_map):
	return bool(source_name and source_name in customer_map)


def _validate_relationships(rows):
	customers = _unique_by_name(rows, "tabBG Customer")
	bikes = _unique_by_name(rows, "tabBG Bike")
	parts = _unique_by_name(rows, "tabBG Spare Part")
	jobs = _unique_by_name(rows, "tabBG Job Card")
	sales = _unique_by_name(rows, "tabBG Sale")
	expenses = _unique_by_name(rows, "tabBG Expense")

	for bike in bikes.values():
		if not _same_customer(bike.get("customer"), customers):
			raise LegacyImportError("A bike references a missing customer.")
	for job in jobs.values():
		if not _same_customer(job.get("customer"), customers):
			raise LegacyImportError("A Job Card references a missing customer.")
		if job.get("bike"):
			bike = bikes.get(job["bike"])
			if not bike or bike.get("customer") != job.get("customer"):
				raise LegacyImportError("A Job Card bike does not match its customer.")
	for sale in sales.values():
		if not _same_customer(sale.get("customer"), customers):
			raise LegacyImportError("A Sale references a missing customer.")
		if sale.get("job_card"):
			job = jobs.get(sale["job_card"])
			if not job or job.get("customer") != sale.get("customer"):
				raise LegacyImportError("A Sale Job Card does not match its customer.")
	for table, expected_parent, expected_field, required_values in (
		("tabBG Job Card Part", "BG Job Card", "parts", jobs),
		("tabBG Sale Item", "BG Sale", "items", sales),
	):
		for row in rows[table]:
			parent = row.get("parent")
			if row.get("parenttype") != expected_parent or row.get("parentfield") != expected_field or parent not in required_values:
				raise LegacyImportError("A child part row has an invalid parent relationship.")
			if row.get("part") not in parts:
				raise LegacyImportError("A transaction part row references a missing spare part.")
	if not expenses:
		raise LegacyImportError("The legacy expense table is missing.")
	return {
		"BG Customer": len(customers),
		"BG Bike": len(bikes),
		"BG Spare Part": len(parts),
		"BG Job Card": len(jobs),
		"BG Job Card Part": len(rows["tabBG Job Card Part"]),
		"BG Sale": len(sales),
		"BG Sale Item": len(rows["tabBG Sale Item"]),
		"BG Expense": len(expenses),
	}


def _check_numeric_snapshot(rows):
	checks = (
		("tabBG Spare Part", "stock_qty", Decimal("0"), False, False),
		("tabBG Spare Part", "min_stock_qty", Decimal("0"), False, True),
		("tabBG Spare Part", "purchase_price", Decimal("0"), False, True),
		("tabBG Spare Part", "selling_price", Decimal("0"), False, False),
		("tabBG Job Card Part", "qty", Decimal("0"), True, False),
		("tabBG Job Card Part", "rate", Decimal("0"), False, True),
		("tabBG Job Card Part", "amount", Decimal("0"), False, True),
		("tabBG Sale Item", "qty", Decimal("0"), True, False),
		("tabBG Sale Item", "rate", Decimal("0"), False, True),
		("tabBG Sale Item", "amount", Decimal("0"), False, True),
		("tabBG Expense", "amount", Decimal("0"), False, False),
		("tabBG Job Card", "labour_charges", Decimal("0"), False, True),
		("tabBG Job Card", "amount_paid", Decimal("0"), False, True),
		("tabBG Sale", "labour_charges", Decimal("0"), False, True),
	)
	for table, field, minimum, exclusive, allow_empty in checks:
		for row in rows[table]:
			if row.get(field) in (None, "") and allow_empty:
				continue
			try:
				value = Decimal(str(row.get(field)))
			except (InvalidOperation, TypeError, ValueError) as exc:
				raise LegacyImportError("The snapshot contains an invalid numeric value.") from exc
			if not value.is_finite() or (value <= minimum if exclusive else value < minimum):
				raise LegacyImportError("The snapshot contains a non-finite or out-of-range numeric value.")
	for row in rows["tabBG Sale Item"]:
		if row.get("gst_rate") in (None, ""):
			continue
		try:
			rate = Decimal(str(row.get("gst_rate")))
		except (InvalidOperation, TypeError, ValueError) as exc:
			raise LegacyImportError("The snapshot contains an invalid tax rate.") from exc
		if not rate.is_finite() or rate < 0 or rate > 100:
			raise LegacyImportError("The snapshot contains an out-of-range tax rate.")


def _require_staging_target():
	if getattr(frappe.local, "site", None) != STAGING_SITE:
		raise LegacyImportError("Legacy import is restricted to bike-garage-staging.local.")
	garage = frappe.db.get_value("BG Garage", TARGET_GARAGE, ["name", "status"], as_dict=True)
	if not garage or garage.status != "Pending":
		raise LegacyImportError("The expected Pending demo garage is unavailable.")


def _validate_schema():
	for table, (doctype, fields) in PARENT_TABLES.items():
		meta = frappe.get_meta(doctype)
		available = {field.fieldname for field in meta.fields}
		missing = set(fields) - available
		garage_field = meta.get_field("garage")
		if (
			missing
			or not garage_field
			or garage_field.fieldtype != "Link"
			or garage_field.options != "BG Garage"
			or not frappe.db.has_column(doctype, "garage")
		):
			raise LegacyImportError("The current DocType schema cannot accept the reviewed snapshot.")
	for table, (parent_doctype, fieldname, *child_fields) in CHILD_TABLES.items():
		meta = frappe.get_meta(parent_doctype)
		table_field = meta.get_field(fieldname)
		if not table_field or table_field.fieldtype != "Table":
			raise LegacyImportError("The current child-table schema does not match the reviewed snapshot.")
		child_fields_available = {field.fieldname for field in frappe.get_meta(table_field.options).fields}
		if set(child_fields) - child_fields_available:
			raise LegacyImportError("The current child-table fields do not match the reviewed snapshot.")


def _check_collisions(rows, counts):
	all_present = True
	for source_table, (doctype, _fields) in PARENT_TABLES.items():
		names = [row["name"] for row in rows[source_table]]
		present = set(frappe.get_all(doctype, filters={"name": ["in", names]}, pluck="name"))
		if not present:
			all_present = False
			continue
		if len(present) != len(names):
			raise LegacyImportError("Some source identifiers already exist; import stopped without overwriting records.")
		for name in present:
			garage = frappe.db.get_value(doctype, name, "garage")
			if garage != TARGET_GARAGE:
				raise LegacyImportError("A source identifier is already owned outside the demo garage.")

	for doctype, expected in counts.items():
		if doctype in {"BG Job Card Part", "BG Sale Item"}:
			continue
		existing_count = frappe.db.count(doctype, {"garage": TARGET_GARAGE})
		if existing_count and existing_count != expected:
			raise LegacyImportError("The demo garage already contains a partial or different dataset; nothing was changed.")
	for table, (parent_doctype, fieldname, *_fields) in CHILD_TABLES.items():
		child_doctype = frappe.get_meta(parent_doctype).get_field(fieldname).options
		parents = [row["name"] for row in rows["tabBG Job Card"]] if parent_doctype == "BG Job Card" else [row["name"] for row in rows["tabBG Sale"]]
		child_count = frappe.db.count(child_doctype, {"parenttype": parent_doctype, "parent": ["in", parents]})
		if child_count and (not all_present or child_count != counts[child_doctype]):
			raise LegacyImportError("Existing child rows conflict with the complete source set; nothing was changed.")
	if all_present and all(
		frappe.db.count(dt, {"garage": TARGET_GARAGE}) == count
		for dt, count in counts.items()
		if dt not in {"BG Job Card Part", "BG Sale Item"}
	):
		for table, (parent_doctype, fieldname, *_fields) in CHILD_TABLES.items():
			child_doctype = frappe.get_meta(parent_doctype).get_field(fieldname).options
			parents = [row["name"] for row in rows["tabBG Job Card"] if parent_doctype == "BG Job Card"]
			if parent_doctype == "BG Sale":
				parents = [row["name"] for row in rows["tabBG Sale"]]
			if frappe.db.count(child_doctype, {"parenttype": parent_doctype, "parent": ["in", parents]}) != counts[child_doctype]:
				raise LegacyImportError("Existing demo records do not match the complete source set; nothing was changed.")
		return "already_present"
	if any(frappe.db.count(dt, {"garage": TARGET_GARAGE}) for dt in counts if dt not in {"BG Job Card Part", "BG Sale Item"}):
		raise LegacyImportError("The demo garage is not empty; import stopped without overwriting records.")
	return "ready"


def _document_values(doctype, row, fields):
	values = {}
	for field in fields:
		if field not in row:
			continue
		value = row.get(field)
		if field not in NUMERIC_FIELDS.get(doctype, set()) or value in (None, ""):
			values[field] = value
			continue
		try:
			number = Decimal(str(value))
		except (InvalidOperation, TypeError, ValueError) as exc:
			raise LegacyImportError("The snapshot contains an invalid numeric value.") from exc
		if not number.is_finite():
			raise LegacyImportError("The snapshot contains a non-finite numeric value.")
		if (doctype, field) in INTEGER_FIELDS:
			if number != number.to_integral_value():
				raise LegacyImportError("The snapshot contains a fractional value for an integer field.")
			values[field] = int(number)
		else:
			converted = float(number)
			if not math.isfinite(converted):
				raise LegacyImportError("The snapshot contains a numeric value outside the supported range.")
			values[field] = converted
	return values


def _child_values(child_doctype, row, fields):
	return _document_values(child_doctype, row, fields)


def _insert_parent(doctype, name, values, *, table_field=None, children=None):
	data = {"doctype": doctype, "garage": TARGET_GARAGE, **values}
	if table_field:
		data[table_field] = children or []
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True, set_name=name)
	return doc


def _create_snapshot(rows, expected_counts):
	_validate_schema()
	mode = _check_collisions(rows, expected_counts)
	if mode == "already_present":
		return {"state": "already_present", "created": {}}

	children_by_parent = {table: {} for table in CHILD_TABLES}
	for table, (parent_type, fieldname, *child_fields) in CHILD_TABLES.items():
		child_doctype = frappe.get_meta(parent_type).get_field(fieldname).options
		for row in rows[table]:
			children_by_parent[table].setdefault(row["parent"], []).append(
				_child_values(child_doctype, row, child_fields)
			)

	created = {}
	for table in ("tabBG Customer", "tabBG Bike", "tabBG Spare Part", "tabBG Job Card", "tabBG Sale", "tabBG Expense"):
		doctype, fields = PARENT_TABLES[table]
		for row in rows[table]:
			if table == "tabBG Job Card":
				doc = _insert_parent(
					doctype, row["name"], _document_values(doctype, row, fields),
					table_field="parts", children=children_by_parent["tabBG Job Card Part"].get(row["name"], []),
				)
			elif table == "tabBG Sale":
				doc = _insert_parent(
					doctype, row["name"], _document_values(doctype, row, fields),
					table_field="items", children=children_by_parent["tabBG Sale Item"].get(row["name"], []),
				)
			else:
				doc = _insert_parent(doctype, row["name"], _document_values(doctype, row, fields))
			created[doctype] = created.get(doctype, 0) + 1
			if table in {"tabBG Job Card", "tabBG Sale"}:
				calculated_fields = (
					("parts_total", "grand_total") if table == "tabBG Job Card"
					else ("subtotal", "gst_amount", "grand_total")
				)
				for fieldname in calculated_fields:
					try:
						old_value = Decimal(str(row.get(fieldname) or 0))
						new_value = Decimal(str(doc.get(fieldname) or 0))
					except (InvalidOperation, TypeError, ValueError) as exc:
						raise LegacyImportError("A transaction total could not be verified.") from exc
					if abs(old_value - new_value) > Decimal("0.01"):
						raise LegacyImportError("Current total calculation differs from a legacy transaction total; import stopped.")
				if table == "tabBG Job Card" and doc.get("payment_status") != row.get("payment_status"):
					raise LegacyImportError("Current Job Card payment status differs from the legacy snapshot.")

	for table, (doctype, fields) in PARENT_TABLES.items():
		for row in rows[table]:
			if frappe.db.get_value(doctype, row["name"], "garage") != TARGET_GARAGE:
				raise LegacyImportError("A created record failed garage ownership verification.")

	for source_table, expected_stock in (
		(row["name"], row.get("stock_qty")) for row in rows["tabBG Spare Part"]
	):
		actual = frappe.db.get_value("BG Spare Part", source_table, "stock_qty")
		try:
			matches = Decimal(str(actual)) == Decimal(str(expected_stock))
		except (InvalidOperation, TypeError, ValueError):
			matches = False
		if not matches:
			raise LegacyImportError("A spare-part stock snapshot changed during import validation.")

	for doctype, expected in expected_counts.items():
		if doctype not in {"BG Job Card Part", "BG Sale Item"} and frappe.db.count(doctype, {"garage": TARGET_GARAGE}) != expected:
			raise LegacyImportError("Imported record counts did not match the reviewed snapshot.")
	for table, (parent_doctype, _fieldname, *_fields) in CHILD_TABLES.items():
		child_doctype = frappe.get_meta(parent_doctype).get_field(_fieldname).options
		parents = [r["name"] for r in rows["tabBG Job Card"]] if parent_doctype == "BG Job Card" else [r["name"] for r in rows["tabBG Sale"]]
		if frappe.db.count(child_doctype, {"parenttype": parent_doctype, "parent": ["in", parents]}) != expected_counts[child_doctype]:
			raise LegacyImportError("Imported child row counts did not match the reviewed snapshot.")
		created[child_doctype] = expected_counts[child_doctype]
	return {"state": "materialized", "created": created}


def preview_legacy_import():
	"""Return a privacy-safe dry-run plan. No records are written."""
	_require_staging_target()
	rows, source = _read_snapshot()
	counts = _validate_relationships(rows)
	_check_numeric_snapshot(rows)
	_validate_schema()
	state = _check_collisions(rows, counts)
	return {
		"target_garage": TARGET_GARAGE,
		"state": state,
		"source": source,
		"business_record_counts": counts,
		"stock_policy": "preserve source stock_qty snapshot; do not apply historical part deltas",
		"writes_performed": False,
	}


def run_legacy_import(*, dry_run=True, confirmed_garage=None, confirmed_source_sha256=None):
	"""Materialize and verify the import; by default roll it back in full.

	A permanent run requires both explicit confirmations. This function is not a
	whitelisted endpoint. The caller is responsible for the staging backup.
	"""
	_require_staging_target()
	if not dry_run and (confirmed_garage != TARGET_GARAGE or confirmed_source_sha256 != SOURCE_SHA256):
		raise LegacyImportError("Permanent import requires explicit garage and source-hash confirmation.")
	rows, source = _read_snapshot()
	counts = _validate_relationships(rows)
	_check_numeric_snapshot(rows)
	_validate_schema()
	state = _check_collisions(rows, counts)
	if state == "already_present":
		return {"state": state, "target_garage": TARGET_GARAGE, "source": source, "writes_performed": False}

	savepoint = f"bg_legacy_import_{uuid4().hex}"
	frappe.db.savepoint(savepoint)
	old_import = getattr(frappe.flags, "in_import", False)
	old_mute = getattr(frappe.flags, "mute_emails", False)
	frappe.flags.in_import = True
	frappe.flags.mute_emails = True
	try:
		with stock._historical_import_scope(stock._HISTORICAL_IMPORT_CAPABILITY):
			result = _create_snapshot(rows, counts)
		if dry_run:
			frappe.db.rollback(save_point=savepoint)
			result["state"] = "dry_run_rolled_back"
		else:
			frappe.db.release_savepoint(savepoint)
			result["state"] = "imported"
		return {
			**result,
			"target_garage": TARGET_GARAGE,
			"source": source,
			"writes_performed": not dry_run,
			"stock_policy": "source stock_qty snapshot preserved; no historical consumption was replayed",
			"excluded_file_metadata_rows": source["excluded_file_metadata_rows"],
			"unsupported_vehicle_photo_fields_omitted": 55,
		}
	except BaseException:
		try:
			frappe.db.rollback(save_point=savepoint)
		except BaseException as rollback_error:
			frappe.logger("bike_garage.legacy_import").critical(
				"Legacy-import savepoint rollback failed; database state is uncertain (%s).",
				savepoint,
				exc_info=True,
			)
			raise LegacyImportError("Import failed and savepoint rollback could not be confirmed; staging database state is uncertain.") from rollback_error
		raise
	finally:
		frappe.flags.in_import = old_import
		frappe.flags.mute_emails = old_mute


def verify_legacy_import_dry_run():
	"""Run a real document-validation dry run and verify its savepoint rollback."""
	_require_staging_target()
	rows, _source = _read_snapshot()
	parent_before = {
		doctype: frappe.db.count(doctype, {"garage": TARGET_GARAGE})
		for doctype, _fields in PARENT_TABLES.values()
	}
	child_before = {}
	for parent_doctype, fieldname, *_fields in CHILD_TABLES.values():
		child_doctype = frappe.get_meta(parent_doctype).get_field(fieldname).options
		parent_rows = rows["tabBG Job Card"] if parent_doctype == "BG Job Card" else rows["tabBG Sale"]
		child_before[child_doctype] = frappe.db.count(
			child_doctype,
			{"parenttype": parent_doctype, "parent": ["in", [row["name"] for row in parent_rows]]},
		)
	result = run_legacy_import(dry_run=True)
	parent_after = {
		doctype: frappe.db.count(doctype, {"garage": TARGET_GARAGE})
		for doctype, _fields in PARENT_TABLES.values()
	}
	child_after = {}
	for parent_doctype, fieldname, *_fields in CHILD_TABLES.values():
		child_doctype = frappe.get_meta(parent_doctype).get_field(fieldname).options
		parent_rows = rows["tabBG Job Card"] if parent_doctype == "BG Job Card" else rows["tabBG Sale"]
		child_after[child_doctype] = frappe.db.count(
			child_doctype,
			{"parenttype": parent_doctype, "parent": ["in", [row["name"] for row in parent_rows]]},
		)
	if parent_before != parent_after or child_before != child_after:
		raise LegacyImportError("The staging dry-run rollback did not restore the original demo record counts.")
	return {
		**result,
		"dry_run_rollback_verified": True,
		"parent_counts_unchanged": True,
		"child_counts_unchanged": True,
	}

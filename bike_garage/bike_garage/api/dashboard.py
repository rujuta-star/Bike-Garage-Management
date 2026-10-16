"""Garage-scoped dashboard data for the Bike Garage UI."""

import frappe

from bike_garage import payments, tenancy


def _get_dashboard_garage():
	"""Return None only for the explicitly authorized platform-wide path."""
	if tenancy.is_platform_super_admin():
		return None
	return tenancy.get_current_garage()


def _sql_garage_scope(garage):
	"""Return a fixed SQL fragment and bound values for the authorized scope."""
	if garage is None:
		return "1=1", ()
	return "`garage` = %s", (garage,)


@frappe.whitelist()
def get_dashboard_stats():
	garage = _get_dashboard_garage()
	active_job_filters = {
		"status": ["in", ["Pending", "In Progress", "Waiting for Parts"]]
	}
	customer_filters = {}
	part_filters = {}
	if garage is not None:
		active_job_filters["garage"] = garage
		customer_filters["garage"] = garage
		part_filters["garage"] = garage

	active_jobs = frappe.db.count("BG Job Card", active_job_filters)
	total_customers = frappe.db.count("BG Customer", customer_filters)
	total_parts = frappe.db.count("BG Spare Part", part_filters)

	today = frappe.utils.today()
	scope_sql, scope_values = _sql_garage_scope(garage)
	financial_access = payments.can_read_payment_data(garage)
	if financial_access:
		tomorrow = frappe.utils.add_days(today, 1)
		collections = payments.collection_rows(f"{today} 00:00:00", f"{tomorrow} 00:00:00", garage)
		today_revenue = sum((row[1] or 0 for row in collections), 0)
		outstanding = frappe.db.sql(
			f"""
			SELECT IFNULL(SUM(grand_total - IFNULL(amount_paid, 0)), 0)
			FROM `tabBG Job Card`
			WHERE payment_status IN ('Unpaid', 'Partially Paid') AND {scope_sql}
			""",
			scope_values,
		)[0][0] or 0
	else:
		# Keep operational dashboard counts available while withholding financial fields.
		today_revenue = None
		outstanding = None

	low_stock = frappe.db.sql(
		f"""
		SELECT part_name, stock_qty, min_stock_qty FROM `tabBG Spare Part`
		WHERE stock_qty <= min_stock_qty AND {scope_sql}
		ORDER BY stock_qty ASC LIMIT 5
		""",
		scope_values,
		as_dict=True,
	)

	recent_jobs = frappe.db.sql(
		f"""
		SELECT name, customer, registration_no, mechanic, status, date
		FROM `tabBG Job Card`
		WHERE {scope_sql}
		ORDER BY modified DESC LIMIT 6
		""",
		scope_values,
		as_dict=True,
	)

	return {
		"active_jobs": active_jobs,
		"today_revenue": today_revenue,
		"outstanding": outstanding,
		"financial_access": financial_access,
		"total_parts": total_parts,
		"total_customers": total_customers,
		"low_stock": low_stock,
		"recent_jobs": recent_jobs,
	}


@frappe.whitelist()
def get_monthly_revenue():
	garage = _get_dashboard_garage()
	payments.require_payment_read_access(garage)
	year = int(frappe.utils.today()[:4])
	return payments.monthly_collection_totals(year, garage)


@frappe.whitelist()
def get_profit_loss():
	garage = _get_dashboard_garage()
	payments.require_payment_read_access(garage)
	scope_sql, scope_values = _sql_garage_scope(garage)
	today = frappe.utils.today()
	month_start = frappe.utils.get_first_day(today)

	tomorrow = frappe.utils.add_days(today, 1)
	collections = payments.collection_rows(
		f"{month_start} 00:00:00", f"{tomorrow} 00:00:00", garage
	)
	revenue = sum((row[1] or 0 for row in collections), 0)

	expenses = frappe.db.sql(
		f"""
		SELECT IFNULL(SUM(amount), 0) FROM `tabBG Expense`
		WHERE date BETWEEN %s AND %s AND {scope_sql}
		""",
		(month_start, today, *scope_values),
	)[0][0] or 0

	return {
		"revenue": revenue,
		"expenses": expenses,
		"profit": revenue - expenses,
	}

import copy
import unittest

from bike_garage import legacy_import


class TestLegacySnapshotParsing(unittest.TestCase):
	def test_reviewed_dump_is_pinned_and_relationships_are_complete(self):
		rows, summary = legacy_import._read_snapshot()
		counts = legacy_import._validate_relationships(rows)
		legacy_import._check_numeric_snapshot(rows)

		self.assertEqual(summary["source_sha256"], legacy_import.SOURCE_SHA256)
		self.assertEqual(counts["BG Customer"], 40)
		self.assertEqual(counts["BG Bike"], 55)
		self.assertEqual(counts["BG Job Card"], 100)
		self.assertEqual(counts["BG Job Card Part"], 199)
		self.assertEqual(counts["BG Sale"], 120)
		self.assertEqual(counts["BG Sale Item"], 240)
		self.assertEqual(summary["ignored_delete_statements"], 10)
		self.assertEqual(summary["excluded_file_metadata_rows"], 55)
		self.assertEqual(summary["excluded_settings_and_series_rows"], 20)
		self.assertNotIn("vehicle_photo", legacy_import.PARENT_TABLES["tabBG Bike"][1])

	def test_job_card_bike_must_match_its_customer(self):
		rows, _summary = legacy_import._read_snapshot()
		rows = copy.deepcopy(rows)
		rows["tabBG Job Card"][0]["customer"] = "missing-customer"
		with self.assertRaises(legacy_import.LegacyImportError):
			legacy_import._validate_relationships(rows)

	def test_non_finite_historical_quantity_is_rejected(self):
		rows, _summary = legacy_import._read_snapshot()
		rows = copy.deepcopy(rows)
		rows["tabBG Sale Item"][0]["qty"] = "Infinity"
		with self.assertRaises(legacy_import.LegacyImportError):
			legacy_import._check_numeric_snapshot(rows)

	def test_sql_parser_handles_quotes_commas_and_null_without_running_sql(self):
		rows = legacy_import._parse_values("('Patil, D''Souza','line\\nnext',NULL,12.50);", 4)
		self.assertEqual(rows, [["Patil, D'Souza", "line\nnext", None, "12.50"]])

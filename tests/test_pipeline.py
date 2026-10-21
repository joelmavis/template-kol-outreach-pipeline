import copy
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pipeline", ROOT / "scripts/pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
EXAMPLE = ROOT / "example/sample-creator-campaign"


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = pipeline.load_config()
        self.creators = read_rows(EXAMPLE / "creators.csv")

    def rated(self, rating):
        row = dict(self.creators[0])
        row["creator_id"] = "C-TEST"
        row["profile_url"] = "https://example.com/creators/test"
        for key in pipeline.DIMENSIONS:
            row[key] = str(rating)
        row["verification_status"] = "Verified"
        return row

    def temp_example(self):
        holder = tempfile.TemporaryDirectory()
        target = Path(holder.name) / "campaign"
        shutil.copytree(EXAMPLE, target)
        return holder, target

    def temp_public_copy(self):
        holder = tempfile.TemporaryDirectory()
        target = Path(holder.name) / "release"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        return holder, target

    def write_rows(self, path, rows):
        with path.open(encoding="utf-8", newline="") as stream:
            fields = next(csv.reader(stream))
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_01_tier_boundaries_and_endpoints(self):
        for rating, tier in [(5, "A"), (4.25, "A"), (4.249, "B"), (3.5, "B"),
                             (3.499, "C"), (2.5, "C"), (2.499, "D"), (0, "D")]:
            with self.subTest(rating=rating):
                row = pipeline.score_creators([self.rated(rating)], self.config)[0]
                self.assertEqual(row["tier"], tier)
                self.assertAlmostEqual(float(row["score"]), rating * 20, places=2)

    def test_02_original_weighting_is_preserved(self):
        self.assertEqual(self.config["dimensions"], {
            "audience_fit": 30, "content_relevance": 25, "engagement_quality": 20,
            "audience_size_band": 5, "brand_safety": 15, "collaboration_readiness": 5,
        })

    def test_03_incomplete_evidence_remains_unscored(self):
        row = self.rated(5)
        row["verification_status"] = "Needs verification"
        row["engagement_quality"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("", "Unscored", ""))

    def test_04_invalid_rating_fails(self):
        for value in ("NaN", "Infinity", "-1", "6", "unknown"):
            row = self.rated(4)
            row["audience_fit"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                pipeline.score_creators([row], self.config)

    def test_05_duplicate_id_and_profile_fail(self):
        first, second = self.rated(4), self.rated(3)
        second["creator_id"] = first["creator_id"].lower()
        second["profile_url"] += "-2"
        with self.assertRaises(ValueError):
            pipeline.score_creators([first, second], self.config)
        second["creator_id"] = "C-TEST-2"
        second["profile_url"] = first["profile_url"]
        with self.assertRaises(ValueError):
            pipeline.score_creators([first, second], self.config)

    def test_06_html_escapes_user_content(self):
        row = self.rated(5)
        row["name"] = "<script>alert(1)</script>"
        scored = pipeline.score_creators([row], self.config)
        data = {"creators": scored, "outreach": [], "events": [], "offers": [], "partnerships": [], "performance": []}
        html = pipeline.outreach_dashboard(data, ROOT / "workspace")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_07_build_outputs_exactly_three_dashboards(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        rendered = pipeline.build(source, output, example=True)
        self.assertEqual(set(rendered), {"persona-dashboard.html", "outreach-dashboard.html", "performance-dashboard.html"})
        self.assertEqual({p.name for p in output.glob("*.html")}, set(rendered))

    def test_08_drafts_do_not_create_outreach_or_events(self):
        _, data = pipeline.load_workspace(EXAMPLE)
        self.assertTrue((EXAMPLE / "drafts/C-EX-001.md").exists())
        self.assertFalse(any(row["creator_id"] == "C-EX-001" and row["event_type"] == "Sent" for row in data["events"]))
        self.assertEqual(next(row for row in data["outreach"] if row["creator_id"] == "C-EX-001")["current_status"], "Drafted")

    def test_09_duplicate_event_id_fails(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "activity-log.csv")
        rows.append(dict(rows[0]))
        self.write_rows(source / "activity-log.csv", rows)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_10_multiple_offers_are_preserved(self):
        _, data = pipeline.load_workspace(EXAMPLE)
        offers = [row for row in data["offers"] if row["creator_id"] == "C-EX-002"]
        self.assertEqual(len(offers), 3)
        self.assertEqual(len({row["offer_id"] for row in offers}), 3)
        self.assertEqual(len({(row["collaboration_type"], row["payment_terms"]) for row in offers}), 3)

    def test_11_confirmed_is_not_published(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "partnerships.csv")
        rows[0]["status"] = "Confirmed"
        rows[0]["confirmed_at"] = "2026-08-15T10:00:00Z"
        rows[0]["published_at"] = ""
        self.write_rows(source / "partnerships.csv", rows)
        pipeline.load_workspace(source)

    def test_12_performance_requires_published_deliverable(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        partnerships = read_rows(source / "partnerships.csv")
        partnerships[1]["status"] = "Confirmed"
        partnerships[1]["published_at"] = ""
        self.write_rows(source / "partnerships.csv", partnerships)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_13_cumulative_metrics_cannot_decrease(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["clicks"] = "1"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_14_dashboard_matches_csv_relationships(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        pipeline.build(source, output, example=True)
        outreach = (output / "outreach-dashboard.html").read_text(encoding="utf-8")
        performance = (output / "performance-dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Workflow Weekly", outreach)
        self.assertIn("OFF-EX-001", outreach)
        self.assertIn("Quiet Metrics Studio", performance)
        self.assertIn("D30", performance)
        self.assertNotIn("Workflow Weekly", performance)

    def test_15_example_marking_and_paths_are_visible(self):
        html = pipeline.persona_dashboard(EXAMPLE, example=True)
        self.assertIn("Example · Illustrative data and fictional creators", html)
        self.assertIn("example/sample-creator-campaign/persona.md", html)

    def test_16_cli_runs_from_another_directory(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/build_dashboards.py"),
            "--source", str(source), "--output", str(output), "--example",
        ], cwd=holder.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output / "performance-dashboard.html").exists())

    def test_17_performance_creator_must_match_partnership(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["creator_id"] = "C-EX-001"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "creator_id does not match"):
            pipeline.load_workspace(source)

    def test_18_offer_must_belong_to_same_creator(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "partnerships.csv")
        rows[1]["offer_id"] = "OFF-EX-001"
        self.write_rows(source / "partnerships.csv", rows)
        with self.assertRaisesRegex(ValueError, "another creator or collaboration"):
            pipeline.load_workspace(source)

    def test_19_offer_must_belong_to_same_collaboration(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        offers = read_rows(source / "offers.csv")
        offers[-1]["collaboration_id"] = "COL-EX-OTHER"
        self.write_rows(source / "offers.csv", offers)
        with self.assertRaisesRegex(ValueError, "another creator or collaboration"):
            pipeline.load_workspace(source)

    def test_20_measurement_before_publication_fails(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["measured_at"] = "2026-08-13T12:00:00Z"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "before published_at"):
            pipeline.load_workspace(source)

    def test_21_performance_publication_date_must_match_partnership(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["published_at"] = "2026-08-15T13:00:00Z"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "does not match partnership D0"):
            pipeline.load_workspace(source)

    def test_22_measurement_window_uses_utc_calendar_date(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["measured_at"] = "2026-08-22T00:10:00+00:00"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "D7 must be measured on 2026-08-21 UTC"):
            pipeline.load_workspace(source)

    def test_23_confirmation_must_precede_publication(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "partnerships.csv")
        rows[1]["confirmed_at"] = "2026-08-15T13:00:00Z"
        self.write_rows(source / "partnerships.csv", rows)
        with self.assertRaisesRegex(ValueError, "confirmed_at must not be after"):
            pipeline.load_workspace(source)

    def test_24_verified_without_evidence_url_is_unscored(self):
        row = self.rated(5)
        row["evidence_url"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("", "Unscored", ""))
        self.assertEqual(result["verification_status"], "Needs verification")
        self.assertIn("Evidence URL", result["missing_evidence"])

    def test_25_verified_without_checked_at_is_unscored(self):
        row = self.rated(5)
        row["checked_at"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("", "Unscored", ""))
        self.assertEqual(result["verification_status"], "Needs verification")
        self.assertIn("Evidence checked date", result["missing_evidence"])

    def test_26_unverified_contact_or_metric_source_blocks_scoring(self):
        row = self.rated(5)
        row["business_email_source"] = ""
        row["metric_source"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual(result["tier"], "Unscored")
        self.assertIn("Public business email source", result["missing_evidence"])
        self.assertIn("Follower metric source", result["missing_evidence"])

    def test_27_performance_dashboard_shows_spend_and_costs(self):
        _, data = pipeline.load_workspace(EXAMPLE)
        html = pipeline.performance_dashboard(data, example=True)
        self.assertIn("USD 1,800", html)
        self.assertIn("USD 5.98", html)
        self.assertIn("USD 9.09", html)
        self.assertIn("Insights / Next Actions", html)
        self.assertIn("Insufficient data for a cross-creator recommendation", html)

    def test_28_cost_metrics_are_na_for_missing_or_zero_inputs(self):
        base = {
            "spend": "", "downloads": "10", "installs": "5", "currency": "USD",
            "attribution_source": "Verified analytics", "metric_definition": "Cumulative",
            "verification_status": "Verified",
        }
        self.assertEqual(pipeline.cost_value(base, "downloads", tracking_verified=True), "N/A")
        zero = dict(base, spend="100", downloads="0", installs="0")
        self.assertEqual(pipeline.cost_value(zero, "downloads", tracking_verified=True), "N/A")
        self.assertEqual(pipeline.cost_value(zero, "installs", tracking_verified=True), "N/A")
        self.assertEqual(pipeline.cost_value(dict(zero, downloads="10"), "downloads", tracking_verified=False), "N/A")

    def test_29_like_for_like_comparison_rejects_different_attribution(self):
        _, data = pipeline.load_workspace(EXAMPLE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", attribution_source="Different source")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, example=True)
        self.assertIn("Insufficient data for a like-for-like comparison", html)

    def test_30_like_for_like_comparison_accepts_matching_scope(self):
        _, data = pipeline.load_workspace(EXAMPLE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, example=True)
        self.assertNotIn("Insufficient data for a like-for-like comparison", html)
        self.assertIn("Frame by Frame Lab", html)

    def test_31_temporal_normalization_handles_offsets_and_date_only_values(self):
        utc = pipeline.parse_temporal("2026-08-14T13:00:00Z", "utc", allow_blank=False)
        offset = pipeline.parse_temporal("2026-08-14T21:00:00+08:00", "offset", allow_blank=False)
        date_only = pipeline.parse_temporal("2026-08-14", "date", allow_blank=False)
        self.assertEqual(utc, offset)
        self.assertEqual(date_only.isoformat(), "2026-08-14T00:00:00+00:00")

    def test_32_performance_utm_campaign_must_match_partnership(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["utm_url"] = rows[0]["utm_url"].replace("utm_campaign=focus-week", "utm_campaign=wrong-campaign")
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "utm_campaign wrong-campaign does not match partnership campaign focus-week"):
            pipeline.load_workspace(source)

    def test_33_performance_utm_creator_must_match_partnership(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["utm_url"] = rows[0]["utm_url"].replace("utm_content=C-EX-003", "utm_content=C-EX-001")
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "utm_content does not match creator_id"):
            pipeline.load_workspace(source)

    def test_34_cumulative_spend_cannot_decrease_without_reason(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["spend"] = "900"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "cumulative spend decreases"):
            pipeline.load_workspace(source)

    def test_35_documented_spend_adjustment_is_allowed_and_used(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["spend"] = "900"
        rows[1]["notes"] = "[Spend adjustment: partial refund confirmed]"
        rows[2]["spend"] = "900"
        self.write_rows(source / "performance.csv", rows)
        _, data = pipeline.load_workspace(source)
        html = pipeline.performance_dashboard(data, example=True)
        self.assertIn("USD 900", html)

    def test_36_spend_requires_cumulative_definition(self):
        holder, source = self.temp_example()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["metric_definition"] = "Single-period spend"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "spend requires a cumulative metric_definition"):
            pipeline.load_workspace(source)

    def test_37_public_release_scan_blocks_simulated_sensitive_text(self):
        holder, target = self.temp_public_copy()
        self.addCleanup(holder.cleanup)
        with (target / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("\nDO NOT SHARE: simulated commercial terms\n")
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Potential confidential text", result.stderr)

    def test_38_public_release_reports_non_git_copy_as_skipped(self):
        holder, target = self.temp_public_copy()
        self.addCleanup(holder.cleanup)
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Git status: Skipped — Not a Git Repository", result.stdout)
        self.assertNotIn("(clean)", result.stdout)

    def test_39_public_release_blocks_unredacted_commercial_terms(self):
        holder, target = self.temp_public_copy()
        self.addCleanup(holder.cleanup)
        with (target / "release-notes.md").open("w", encoding="utf-8") as stream:
            stream.write("Creator fee: $900\n")
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Potential unredacted commercial terms", result.stderr)


if __name__ == "__main__":
    unittest.main()

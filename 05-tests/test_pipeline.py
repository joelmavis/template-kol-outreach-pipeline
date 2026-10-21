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
spec = importlib.util.spec_from_file_location("pipeline", ROOT / "04-tools/pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
FIXTURE = ROOT / "05-tests/fixtures/sample-creator-campaign"


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = pipeline.load_config()
        with (FIXTURE / "creators.csv").open(encoding="utf-8", newline="") as stream:
            self.creator_fields = next(csv.reader(stream))
        self.creators = read_rows(FIXTURE / "creators.csv")

    def rated(self, rating):
        row = dict(self.creators[0])
        row["creator_id"] = "C-TEST"
        row["profile_url"] = "https://example.com/creators/test"
        for key in pipeline.DIMENSIONS:
            row[key] = str(rating)
        row["verification_status"] = "Verified"
        return row

    def temp_fixture(self):
        holder = tempfile.TemporaryDirectory()
        target = Path(holder.name) / "campaign"
        shutil.copytree(FIXTURE, target)
        return holder, target

    def temp_public_copy(self):
        holder = tempfile.TemporaryDirectory()
        target = Path(holder.name) / "release"
        target.mkdir()
        workspace = target / "01-workspace"
        workspace.mkdir()
        (workspace / "drafts").mkdir()
        (workspace / "collaborations").mkdir()
        (workspace / "drafts/.gitkeep").touch()
        (workspace / "collaborations/.gitkeep").touch()
        for filename in pipeline.FILES.values():
            source = ROOT / "01-workspace" / filename
            with source.open(encoding="utf-8", newline="") as stream:
                fields = next(csv.reader(stream))
            with (workspace / filename).open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerow(fields)
        shutil.copytree(ROOT / "05-tests/fixtures", target / "05-tests/fixtures")
        (target / "README.md").write_text("# Public release fixture\n", encoding="utf-8")
        _, data = pipeline.load_workspace(workspace)
        (target / "creator-database-dashboard.html").write_text(pipeline.creator_database_dashboard(data, workspace), encoding="utf-8")
        (target / "outreach-dashboard.html").write_text(pipeline.outreach_dashboard(data, workspace), encoding="utf-8")
        (target / "performance-dashboard.html").write_text(pipeline.performance_dashboard(data), encoding="utf-8")
        return holder, target

    def temp_user_workspace(self):
        holder = tempfile.TemporaryDirectory()
        target = Path(holder.name) / "workspace"
        shutil.copytree(ROOT / "01-workspace", target)
        self.populate_user_workspace(target)
        return holder, target

    def populate_user_workspace(self, target):
        base = dict(self.creators[0])
        creators = []
        for number in range(1, 11):
            row = dict(base)
            creator_id = f"C-UAT-{number:03d}"
            row.update(
                creator_id=creator_id,
                name=f"Fixture Creator {number}",
                handle=f"fixture-{number}",
                profile_url=f"https://example.com/creators/{number}",
                representative_content_url=f"https://example.com/content/{number}",
                public_business_email=f"creator{number}@example.com",
                business_email_source=f"https://example.com/contact/{number}",
                dm_url=f"https://example.com/dm/{number}",
                contact_page_url=f"https://example.com/contact/{number}",
                evidence_url=f"https://example.com/evidence/{number}",
                rank=str(number),
            )
            creators.append(row)
        self.write_rows(target / "creators.csv", creators)

    def minimal_creator(self, number, *, status="Pending Verification"):
        row = {field: "" for field in self.creator_fields}
        row.update(
            creator_id=f"C-BATCH-{number:03d}",
            name=f"Batch Channel {number}",
            platform="YouTube",
            profile_url=f"https://example.com/youtube/channel-{number}",
            evidence_url=f"https://example.com/youtube/channel-{number}",
            verification_status=status,
            do_not_contact="false",
        )
        return row

    def write_rows(self, path, rows):
        with path.open(encoding="utf-8", newline="") as stream:
            fields = next(csv.reader(stream))
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def progress_rows(self, source, record_type):
        return [row for row in read_rows(source / "outreach-progress.csv") if row["record_type"] == record_type]

    def write_progress_rows(self, source, record_type, rows):
        path = source / "outreach-progress.csv"
        retained = [row for row in read_rows(path) if row["record_type"] != record_type]
        self.write_rows(path, retained + rows)

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
        row["verification_status"] = "Partial"
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
        html = pipeline.outreach_dashboard(data, ROOT / "01-workspace")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_07_build_outputs_exactly_three_dashboards(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        rendered = pipeline.build(source, output, fixture=True)
        self.assertEqual(set(rendered), {"creator-database-dashboard.html", "outreach-dashboard.html", "performance-dashboard.html"})
        self.assertEqual({p.name for p in output.glob("*.html")}, set(rendered))

    def test_08_drafts_do_not_create_outreach_or_events(self):
        _, data = pipeline.load_workspace(FIXTURE)
        self.assertTrue((FIXTURE / "drafts/C-EX-001.md").exists())
        self.assertFalse(any(row["creator_id"] == "C-EX-001" and row["event_type"] == "Sent" for row in data["events"]))
        self.assertEqual(next(row for row in data["outreach"] if row["creator_id"] == "C-EX-001")["current_status"], "Drafted")

    def test_09_duplicate_event_id_fails(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = self.progress_rows(source, "activity")
        rows.append(dict(rows[0]))
        self.write_progress_rows(source, "activity", rows)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_10_multiple_offers_are_preserved(self):
        _, data = pipeline.load_workspace(FIXTURE)
        offers = [row for row in data["offers"] if row["creator_id"] == "C-EX-002"]
        self.assertEqual(len(offers), 3)
        self.assertEqual(len({row["offer_id"] for row in offers}), 3)
        self.assertEqual(len({(row["collaboration_type"], row["payment_terms"]) for row in offers}), 3)

    def test_11_confirmed_is_not_published(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = self.progress_rows(source, "partnership")
        rows[0]["status"] = "Confirmed"
        rows[0]["confirmed_at"] = "2026-08-15T10:00:00Z"
        rows[0]["published_at"] = ""
        self.write_progress_rows(source, "partnership", rows)
        pipeline.load_workspace(source)

    def test_12_performance_requires_published_deliverable(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        partnerships = self.progress_rows(source, "partnership")
        partnerships[1]["status"] = "Confirmed"
        partnerships[1]["published_at"] = ""
        self.write_progress_rows(source, "partnership", partnerships)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_13_cumulative_metrics_cannot_decrease(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["clicks"] = "1"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaises(ValueError):
            pipeline.load_workspace(source)

    def test_14_dashboard_matches_csv_relationships(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        pipeline.build(source, output, fixture=True)
        outreach = (output / "outreach-dashboard.html").read_text(encoding="utf-8")
        performance = (output / "performance-dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Workflow Weekly", outreach)
        self.assertIn("OFF-EX-001", outreach)
        self.assertIn("Quiet Metrics Studio", performance)
        self.assertIn("D30", performance)
        self.assertNotIn("Workflow Weekly", performance)

    def test_15_fixture_marking_and_paths_are_visible(self):
        _, data = pipeline.load_workspace(FIXTURE)
        html = pipeline.creator_database_dashboard(data, FIXTURE, fixture=True)
        self.assertIn("Test fixture · Illustrative data and fictional creators", html)
        self.assertIn("05-tests/fixtures/sample-creator-campaign/creators.csv", html)

    def test_16_cli_runs_from_another_directory(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name) / "out"
        result = subprocess.run([
            sys.executable, str(ROOT / "04-tools/build_dashboards.py"),
            "--source", str(source), "--output", str(output), "--fixture",
        ], cwd=holder.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output / "performance-dashboard.html").exists())

    def test_17_performance_creator_must_match_partnership(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["creator_id"] = "C-EX-001"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "creator_id does not match"):
            pipeline.load_workspace(source)

    def test_18_offer_must_belong_to_same_creator(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = self.progress_rows(source, "partnership")
        rows[1]["offer_id"] = "OFF-EX-001"
        self.write_progress_rows(source, "partnership", rows)
        with self.assertRaisesRegex(ValueError, "another creator or collaboration"):
            pipeline.load_workspace(source)

    def test_19_offer_must_belong_to_same_collaboration(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        offers = self.progress_rows(source, "offer")
        offers[-1]["collaboration_id"] = "COL-EX-OTHER"
        self.write_progress_rows(source, "offer", offers)
        with self.assertRaisesRegex(ValueError, "another creator or collaboration"):
            pipeline.load_workspace(source)

    def test_20_measurement_before_publication_fails(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["measured_at"] = "2026-08-13T12:00:00Z"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "before published_at"):
            pipeline.load_workspace(source)

    def test_21_performance_publication_date_must_match_partnership(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["published_at"] = "2026-08-15T13:00:00Z"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "does not match partnership D0"):
            pipeline.load_workspace(source)

    def test_22_measurement_window_uses_utc_calendar_date(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["measured_at"] = "2026-08-22T00:10:00+00:00"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "D7 must be measured on 2026-08-21 UTC"):
            pipeline.load_workspace(source)

    def test_23_confirmation_must_precede_publication(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = self.progress_rows(source, "partnership")
        rows[1]["confirmed_at"] = "2026-08-15T13:00:00Z"
        self.write_progress_rows(source, "partnership", rows)
        with self.assertRaisesRegex(ValueError, "confirmed_at must not be after"):
            pipeline.load_workspace(source)

    def test_24_verified_without_evidence_url_is_unscored(self):
        row = self.rated(5)
        row["evidence_url"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("", "Unscored", ""))
        self.assertEqual(result["verification_status"], "Pending Verification")
        self.assertIn("Evidence URL", result["missing_evidence"])

    def test_25_verified_without_checked_at_is_unscored(self):
        row = self.rated(5)
        row["checked_at"] = ""
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("", "Unscored", ""))
        self.assertEqual(result["verification_status"], "Pending Verification")
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
        _, data = pipeline.load_workspace(FIXTURE)
        html = pipeline.performance_dashboard(data, fixture=True)
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
        _, data = pipeline.load_workspace(FIXTURE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", attribution_source="Different source")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertIn("Insufficient data for a like-for-like comparison", html)

    def test_30_like_for_like_comparison_accepts_matching_scope(self):
        _, data = pipeline.load_workspace(FIXTURE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertNotIn("Insufficient data for a like-for-like comparison", html)
        self.assertIn("Frame by Frame Lab", html)

    def test_31_temporal_normalization_handles_offsets_and_date_only_values(self):
        utc = pipeline.parse_temporal("2026-08-14T13:00:00Z", "utc", allow_blank=False)
        offset = pipeline.parse_temporal("2026-08-14T21:00:00+08:00", "offset", allow_blank=False)
        date_only = pipeline.parse_temporal("2026-08-14", "date", allow_blank=False)
        self.assertEqual(utc, offset)
        self.assertEqual(date_only.isoformat(), "2026-08-14T00:00:00+00:00")

    def test_32_performance_utm_campaign_must_match_partnership(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["utm_url"] = rows[0]["utm_url"].replace("utm_campaign=focus-week", "utm_campaign=wrong-campaign")
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "utm_campaign wrong-campaign does not match partnership campaign focus-week"):
            pipeline.load_workspace(source)

    def test_33_performance_utm_creator_must_match_partnership(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[0]["utm_url"] = rows[0]["utm_url"].replace("utm_content=C-EX-003", "utm_content=C-EX-001")
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "utm_content does not match creator_id"):
            pipeline.load_workspace(source)

    def test_34_cumulative_spend_cannot_decrease_without_reason(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["spend"] = "900"
        self.write_rows(source / "performance.csv", rows)
        with self.assertRaisesRegex(ValueError, "cumulative spend decreases"):
            pipeline.load_workspace(source)

    def test_35_documented_spend_adjustment_is_allowed_and_used(self):
        holder, source = self.temp_fixture()
        self.addCleanup(holder.cleanup)
        rows = read_rows(source / "performance.csv")
        rows[1]["spend"] = "900"
        rows[1]["notes"] = "[Spend adjustment: partial refund confirmed]"
        rows[2]["spend"] = "900"
        self.write_rows(source / "performance.csv", rows)
        _, data = pipeline.load_workspace(source)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertIn("USD 900", html)

    def test_36_spend_requires_cumulative_definition(self):
        holder, source = self.temp_fixture()
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
            sys.executable, str(ROOT / "04-tools/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Potential confidential text", result.stderr)

    def test_38_public_release_reports_non_git_copy_as_skipped(self):
        holder, target = self.temp_public_copy()
        self.addCleanup(holder.cleanup)
        result = subprocess.run([
            sys.executable, str(ROOT / "04-tools/check_public_release.py"), "--root", str(target),
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
            sys.executable, str(ROOT / "04-tools/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Potential unredacted commercial terms", result.stderr)

    def test_40_workspace_and_fixture_expose_exactly_three_tables(self):
        expected = {"creators.csv", "outreach-progress.csv", "performance.csv"}
        self.assertEqual({path.name for path in (ROOT / "01-workspace").glob("*.csv")}, expected)
        self.assertEqual({path.name for path in FIXTURE.glob("*.csv")}, expected)
        record_types = {row["record_type"] for row in read_rows(FIXTURE / "outreach-progress.csv")}
        self.assertEqual(record_types, {"outreach", "activity", "offer", "partnership"})

    def test_41_top_level_workflow_directories_are_ordered(self):
        expected = {"01-workspace", "03-config", "04-tools", "05-tests"}
        self.assertTrue(all((ROOT / name).is_dir() for name in expected))
        self.assertFalse(any((ROOT / name).exists() for name in {"workspace", "example", "scripts", "tests", "01-kol-profile-and-scoring"}))

    def test_42_ten_creator_database_rows_pass_user_workspace_mode(self):
        holder, source = self.temp_user_workspace()
        self.addCleanup(holder.cleanup)
        _, data = pipeline.load_workspace(source)
        self.assertEqual(len(data["creators"]), 10)
        output = Path(holder.name) / "dashboards"
        pipeline.build(source, output)
        self.assertEqual(
            {path.name for path in output.glob("*.html")},
            {"creator-database-dashboard.html", "outreach-dashboard.html", "performance-dashboard.html"},
        )
        result = subprocess.run([
            sys.executable, str(ROOT / "04-tools/validate_workspace.py"), "--source", str(source),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("10 creators", result.stdout)

    def test_43_release_mode_blocks_user_data_without_deleting_it(self):
        holder, target = self.temp_public_copy()
        self.addCleanup(holder.cleanup)
        workspace = target / "01-workspace"
        self.populate_user_workspace(workspace)
        result = subprocess.run([
            sys.executable, str(ROOT / "04-tools/check_public_release.py"), "--root", str(target),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Public workspace must be blank", result.stderr)
        self.assertEqual(len(read_rows(workspace / "creators.csv")), 10)

    def test_44_creator_database_dashboard_shows_actual_database_metrics(self):
        _, data = pipeline.load_workspace(FIXTURE)
        html = pipeline.creator_database_dashboard(data, FIXTURE, fixture=True)
        self.assertIn("Creator database", html)
        self.assertIn('aria-label="A B C D creator score tier distribution"', html)
        self.assertIn('aria-label="Creator subscriber count band distribution"', html)
        self.assertIn("Data completeness", html)
        self.assertIn("Recommended next actions", html)
        self.assertIn("Quiet Metrics Studio", html)

    def test_45_outreach_charts_use_creator_and_progress_rows(self):
        _, data = pipeline.load_workspace(FIXTURE)
        html = pipeline.outreach_dashboard(data, FIXTURE, fixture=True)
        self.assertIn('aria-label="Creator outreach status distribution"', html)
        self.assertIn("<b>Pending</b><small>3 · 60% of total</small>", html)
        self.assertIn("<b>Negotiating</b><small>1 · 20% of total</small>", html)
        self.assertIn('aria-label="A B C D creator tier distribution"', html)
        self.assertIn("Tier A", html)
        self.assertIn("Unscored creators: 1", html)
        self.assertNotIn("<th>ID</th>", html)
        self.assertLess(html.index("Workflow Weekly"), html.index("Internal creator ID: C-EX-002"))
        self.assertLess(html.index("Integrated workflow segment"), html.index("Internal offer ID: OFF-EX-001"))

    def test_46_performance_kpis_and_trend_use_latest_snapshot_only(self):
        _, data = pipeline.load_workspace(FIXTURE)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertIn("Total recorded spend", html)
        self.assertIn("USD 1,800", html)
        self.assertNotIn("USD 5,400", html)
        self.assertIn("Total downloads", html)
        self.assertIn(">301<", html)
        self.assertIn("Total installs", html)
        self.assertIn(">198<", html)
        self.assertIn(">65.8%<", html)
        self.assertIn('aria-label="Quiet Metrics Studio cumulative performance by measurement window"', html)
        self.assertIn("D7 181 · D14 236 · D30 301", html)
        self.assertLess(html.index("Quiet Metrics Studio"), html.index("Internal creator ID: C-EX-003"))
        self.assertLess(html.index("Dedicated video"), html.index("Internal deliverable ID: DEL-EX-003"))

    def test_47_empty_workspace_uses_chart_empty_states(self):
        _, data = pipeline.load_workspace(ROOT / "01-workspace")
        database = pipeline.creator_database_dashboard(data, ROOT / "01-workspace")
        outreach = pipeline.outreach_dashboard(data, ROOT / "01-workspace")
        performance = pipeline.performance_dashboard(data)
        self.assertNotIn("<svg", database)
        self.assertIn("No creator records yet", database)
        self.assertNotIn("<svg", outreach)
        self.assertIn("No eligible records yet, so no distribution is shown", outreach)
        self.assertIn("No evidence-ready creators have a score yet", outreach)
        self.assertNotIn("<svg", performance)
        self.assertIn("no trend chart is shown", performance)
        self.assertIn("Insufficient data for a like-for-like creator chart", performance)

    def test_48_comparison_chart_requires_like_for_like_records(self):
        _, data = pipeline.load_workspace(FIXTURE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertIn('aria-label="D14 creator download to install conversion comparison"', html)
        self.assertIn("CPD USD 7.63 · CPI USD 11.39", html)

    def test_49_total_conversion_requires_matching_latest_scopes(self):
        _, data = pipeline.load_workspace(FIXTURE)
        data = copy.deepcopy(data)
        partnership = dict(data["partnerships"][1])
        partnership.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001", offer_id="")
        data["partnerships"].append(partnership)
        record = dict(data["performance"][1])
        record.update(collaboration_id="COL-EX-ALT", deliverable_id="DEL-EX-ALT", creator_id="C-EX-001")
        data["performance"].append(record)
        html = pipeline.performance_dashboard(data, fixture=True)
        self.assertIn('Download → install</div><div class="metric">N/A</div>', html)

    def test_50_product_brief_discovery_can_save_twenty_creators_in_batches(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        source = Path(holder.name) / "workspace"
        shutil.copytree(ROOT / "01-workspace", source)
        fields, existing = pipeline.read_csv(source / "creators.csv")
        first = [self.minimal_creator(index) for index in range(1, 9)]
        merged = pipeline.merge_creator_batch(existing, first, fields)
        pipeline.write_csv(source / "creators.csv", fields, pipeline.score_creators(merged, self.config))
        second = [self.minimal_creator(index) for index in range(9, 21)]
        current = read_rows(source / "creators.csv")
        merged = pipeline.merge_creator_batch(current, second, fields)
        pipeline.write_csv(source / "creators.csv", fields, pipeline.score_creators(merged, self.config))
        _, data = pipeline.load_workspace(source)
        self.assertEqual(len(data["creators"]), 20)
        self.assertEqual(data["creators"][0]["name"], "Batch Channel 1")
        html = pipeline.creator_database_dashboard(data, source)
        self.assertIn("<div class=\"metric\">20</div>", html)

    def test_51_five_channel_links_can_enter_as_partial_records(self):
        rows = []
        for index in range(1, 6):
            row = self.minimal_creator(index, status="Partial")
            row["checked_at"] = "2026-10-21"
            rows.append(row)
        scored = pipeline.score_creators(rows, self.config)
        self.assertEqual(len(scored), 5)
        self.assertTrue(all(row["verification_status"] == "Partial" for row in scored))
        self.assertTrue(all(row["tier"] == "Unscored" for row in scored))

    def test_52_missing_supplementary_data_does_not_block_database_row(self):
        row = self.minimal_creator(1)
        row.update(follower_count="", public_business_email="", metric_summary="", country_region="")
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual(result["verification_status"], "Pending Verification")
        self.assertEqual(result["tier"], "Unscored")
        self.assertEqual(result["follower_count"], "")

    def test_53_interrupted_discovery_resume_preserves_and_enriches_existing_rows(self):
        fields = self.creator_fields
        original = self.minimal_creator(1)
        original["content_category"] = "Workflow education"
        duplicate = self.minimal_creator(99, status="Partial")
        duplicate["profile_url"] = original["profile_url"] + "/"
        duplicate["evidence_url"] = original["evidence_url"]
        duplicate["checked_at"] = "2026-10-21"
        duplicate["language"] = "English"
        merged = pipeline.merge_creator_batch([original], [duplicate, self.minimal_creator(2)], fields)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["creator_id"], original["creator_id"])
        self.assertEqual(merged[0]["content_category"], "Workflow education")
        self.assertEqual(merged[0]["language"], "English")

    def test_54_partial_record_can_score_when_six_dimension_evidence_is_complete(self):
        row = self.rated(4)
        row["verification_status"] = "Partial"
        result = pipeline.score_creators([row], self.config)[0]
        self.assertEqual(result["verification_status"], "Partial")
        self.assertEqual((result["score"], result["tier"], result["rank"]), ("80.00", "B", "1"))

    def test_55_outreach_collaboration_and_performance_regression_after_database_change(self):
        _, data = pipeline.load_workspace(FIXTURE)
        self.assertTrue(data["events"])
        self.assertTrue(data["offers"])
        self.assertTrue(data["partnerships"])
        self.assertTrue(data["performance"])
        self.assertIn("Workflow Weekly", pipeline.outreach_dashboard(data, FIXTURE, fixture=True))
        self.assertIn("Quiet Metrics Studio", pipeline.performance_dashboard(data, fixture=True))

    def test_56_v22_has_no_independent_persona_artifacts(self):
        self.assertFalse((ROOT / "01-workspace/persona.md").exists())
        self.assertFalse((FIXTURE / "persona.md").exists())
        self.assertFalse((ROOT / "persona-dashboard.html").exists())
        self.assertFalse((FIXTURE / "persona-dashboard.html").exists())
        self.assertTrue((ROOT / "creator-database-dashboard.html").exists())


if __name__ == "__main__":
    unittest.main()

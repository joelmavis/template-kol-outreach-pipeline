import csv
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "04-tools"
sys.path.insert(0, str(TOOLS))

import check_public_release
from import_creator_batch import map_rows
from local_table import read_local_table
from pipeline import (
    FILES,
    build,
    creator_database_dashboard,
    load_workspace,
    merge_creator_batch,
    outreach_dashboard,
    performance_dashboard,
    read_csv,
    validate_creators,
    write_csv,
)

WORKSPACE = ROOT / "01-workspace"
FIXTURE = ROOT / "05-tests/fixtures/sample-creator-campaign"


def copy_workspace(source):
    temp = tempfile.TemporaryDirectory()
    destination = Path(temp.name) / "workspace"
    shutil.copytree(source, destination)
    return temp, destination


def append_row(path, row):
    fields, rows = read_csv(path)
    rows.append({field: row.get(field, "") for field in fields})
    write_csv(path, fields, rows)


class PipelineV3Tests(unittest.TestCase):
    def test_01_blank_workspace_is_valid(self):
        _, data = load_workspace(WORKSPACE)
        self.assertEqual(len(data["creators"]), 0)
        self.assertEqual(len(data["partnerships"]), 0)

    def test_02_fixture_is_valid(self):
        _, data = load_workspace(FIXTURE)
        self.assertEqual(len(data["creators"]), 5)
        self.assertEqual(len(data["events"]), 7)
        self.assertEqual(len(data["partnerships"]), 2)

    def test_03_partial_creator_needs_only_id_and_name(self):
        row = {"creator_id": "C-PARTIAL", "name": "Unfinished Channel", "verification_status": "Pending Verification"}
        validate_creators([row])

    def test_04_duplicate_channel_url_is_rejected(self):
        rows = [
            {"creator_id": "C-1", "name": "One", "profile_url": "https://example.com/channel/a", "verification_status": "Partial"},
            {"creator_id": "C-2", "name": "Two", "profile_url": "https://example.com/channel/a/", "verification_status": "Partial"},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate YouTube channel URL"):
            validate_creators(rows)

    def test_05_external_verification_is_not_required_for_use(self):
        validate_creators([{"creator_id": "C-1", "name": "One", "verification_status": "Verified"}])
        validate_creators([{"creator_id": "C-2", "name": "Two", "verification_status": ""}])

    def test_06_missing_email_source_does_not_block_import(self):
        validate_creators([{
            "creator_id": "C-1", "name": "One", "verification_status": "",
            "public_business_email": "test@example.com",
        }])

    def test_07_additional_source_data_must_be_json_object(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            validate_creators([{
                "creator_id": "C-1", "name": "One", "verification_status": "Partial",
                "additional_data_json": "{broken",
            }])

    def test_08_batch_fills_blank_values(self):
        fields = ["creator_id", "name", "profile_url", "language"]
        existing = [{"creator_id": "C-1", "name": "One", "profile_url": "https://example.com/one", "language": ""}]
        batch = [{"creator_id": "C-1", "name": "One", "profile_url": "https://example.com/one", "language": "English"}]
        merged = merge_creator_batch(existing, batch, fields)
        self.assertEqual(merged[0]["language"], "English")

    def test_09_batch_does_not_overwrite_prior_value(self):
        fields = ["creator_id", "name", "profile_url", "language"]
        existing = [{"creator_id": "C-1", "name": "One", "profile_url": "https://example.com/one", "language": "English"}]
        batch = [{"creator_id": "C-1", "name": "One renamed", "profile_url": "https://example.com/one", "language": "French"}]
        merged = merge_creator_batch(existing, batch, fields)
        self.assertEqual(merged[0]["name"], "One")
        self.assertEqual(merged[0]["language"], "English")

    def test_10_batch_deduplicates_by_channel_url(self):
        fields = ["creator_id", "name", "profile_url", "language"]
        existing = [{"creator_id": "C-1", "name": "One", "profile_url": "https://example.com/one", "language": ""}]
        batch = [{"creator_id": "C-NEW", "name": "One", "profile_url": "https://example.com/one/", "language": "English"}]
        merged = merge_creator_batch(existing, batch, fields)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["creator_id"], "C-1")

    def test_11_legacy_offer_rows_are_rejected(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        append_row(workspace / "outreach-progress.csv", {
            "record_type": "offer", "record_id": "OFF-1", "creator_id": "C-EX-001",
        })
        with self.assertRaisesRegex(ValueError, "invalid record_type"):
            load_workspace(workspace)

    def test_12_selected_is_a_valid_current_state(self):
        _, data = load_workspace(FIXTURE)
        row = next(item for item in data["outreach"] if item["creator_id"] == "C-EX-001")
        self.assertEqual(row["status"], "Selected / To Contact")
        self.assertFalse(row["first_contact_at"])

    def test_13_duplicate_current_state_is_rejected(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        append_row(workspace / "outreach-progress.csv", {
            "record_type": "outreach", "record_id": "OUT-DUP", "creator_id": "C-EX-001",
            "status": "Contacted", "opt_out": "false",
        })
        with self.assertRaisesRegex(ValueError, "one current-state row"):
            load_workspace(workspace)

    def test_14_unknown_creator_relation_is_rejected(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        append_row(workspace / "outreach-progress.csv", {
            "record_type": "activity", "record_id": "EV-UNKNOWN", "creator_id": "C-UNKNOWN",
            "event_at": "2026-08-10", "event_type": "Sent",
        })
        with self.assertRaisesRegex(ValueError, "unknown creator_id"):
            load_workspace(workspace)

    def test_15_negotiation_requires_collaboration_folder(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "outreach-progress.csv")
        target = next(row for row in rows if row["record_id"] == "PAR-COL-EX-002-DEL-EX-002")
        target["collaboration_folder"] = ""
        write_csv(workspace / "outreach-progress.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "requires collaboration_folder"):
            load_workspace(workspace)

    def test_16_negotiation_requires_three_working_files(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        (workspace / "collaborations/C-EX-002/pricing.md").unlink()
        with self.assertRaisesRegex(ValueError, "missing .*pricing.md"):
            load_workspace(workspace)

    def test_17_published_requires_confirmation_and_publication_dates(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "outreach-progress.csv")
        target = next(row for row in rows if row["record_id"] == "PAR-COL-EX-003-DEL-EX-003")
        target["confirmed_at"] = ""
        write_csv(workspace / "outreach-progress.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "needs confirmation"):
            load_workspace(workspace)

    def test_18_performance_requires_published_deliverable(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "performance.csv")
        rows[0]["collaboration_id"] = "COL-NOPE"
        write_csv(workspace / "performance.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "not a published deliverable"):
            load_workspace(workspace)

    def test_19_utm_is_optional(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "outreach-progress.csv")
        for row in rows:
            if row["record_type"] == "partnership":
                row["utm_url"] = ""
        write_csv(workspace / "outreach-progress.csv", fields, rows)
        fields, rows = read_csv(workspace / "performance.csv")
        for row in rows:
            row["utm_url"] = ""
        write_csv(workspace / "performance.csv", fields, rows)
        load_workspace(workspace)

    def test_20_cumulative_outcomes_cannot_decrease(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "performance.csv")
        rows[1]["downloads"] = "100"
        write_csv(workspace / "performance.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "cumulative downloads decreases"):
            load_workspace(workspace)

    def test_21_spend_decrease_needs_reason(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "performance.csv")
        rows[1]["spend"] = "900"
        write_csv(workspace / "performance.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "Spend adjustment"):
            load_workspace(workspace)

    def test_22_documented_spend_adjustment_is_allowed(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "performance.csv")
        rows[1]["spend"] = "900"
        rows[1]["notes"] += " [Spend adjustment: documented refund]"
        rows[2]["spend"] = "900"
        write_csv(workspace / "performance.csv", fields, rows)
        load_workspace(workspace)

    def test_23_build_outputs_exactly_three_dashboards(self):
        with tempfile.TemporaryDirectory() as temp:
            rendered = build(FIXTURE, temp, fixture=True)
            self.assertEqual(set(rendered), {
                "creator-database-dashboard.html", "outreach-dashboard.html", "performance-dashboard.html",
            })

    def test_24_dashboards_use_names_first(self):
        _, data = load_workspace(FIXTURE)
        html = creator_database_dashboard(data, FIXTURE, fixture=True)
        self.assertIn("Frame by Frame Lab", html)
        self.assertIn("Internal creator ID", html)
        self.assertIn("C-EX-001", html)

    def test_25_creator_dashboard_has_no_legacy_ranking_ui(self):
        _, data = load_workspace(FIXTURE)
        html = creator_database_dashboard(data, FIXTURE, fixture=True).casefold()
        for phrase in ("score tiers", "rank / priority", "a/b/c/d"):
            self.assertNotIn(phrase, html)

    def test_26_outreach_dashboard_separates_selection_from_contact(self):
        _, data = load_workspace(FIXTURE)
        html = outreach_dashboard(data, FIXTURE, fixture=True)
        self.assertIn("Selected / To Contact", html)
        self.assertIn("Selected does not mean contacted", html)

    def test_27_performance_dashboard_works_without_utm(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "performance.csv")
        for row in rows:
            row["utm_url"] = ""
        write_csv(workspace / "performance.csv", fields, rows)
        _, data = load_workspace(workspace)
        html = performance_dashboard(data, workspace, fixture=True)
        self.assertIn("D30", html)
        self.assertIn("UTM links can be recorded", html)

    def test_28_empty_workspace_has_actionable_empty_states(self):
        _, data = load_workspace(WORKSPACE)
        creator_html = creator_database_dashboard(data, WORKSPACE)
        outreach_html = outreach_dashboard(data, WORKSPACE)
        self.assertIn("Describe what you need or attach a local CSV/XLSX file", creator_html)
        self.assertIn("URLs are reference fields, not an input mode", creator_html)
        self.assertIn("Ask the Agent to filter", outreach_html)

    def test_29_actual_style_chinese_headers_map_without_legacy_priority(self):
        fields, _ = read_csv(WORKSPACE / "creators.csv")
        rows = map_rows(
            ["Creator", "内容垂类", "订阅数", "视频链接", "profile_url", "Tier", "总分"],
            [{"Creator": "Fictional Local Channel", "内容垂类": "Productivity", "订阅数": "12000",
              "视频链接": "https://example.com/video", "profile_url": "https://example.com/channel",
              "Tier": "A", "总分": "99"}],
            fields,
            "local-list.csv",
        )
        self.assertEqual(rows[0]["name"], "Fictional Local Channel")
        self.assertEqual(rows[0]["follower_count"], "12000")
        self.assertIn('"Tier":"A"', rows[0]["additional_data_json"])
        self.assertNotIn("score", fields)
        self.assertNotIn("tier", fields)

    def test_30_mapping_preserves_source_trace(self):
        fields, _ = read_csv(WORKSPACE / "creators.csv")
        rows = map_rows(["Creator"], [{"Creator": "One"}], fields, "source.csv")
        self.assertEqual(rows[0]["source_file"], "source.csv")
        self.assertEqual(rows[0]["source_row"], "2")
        self.assertTrue(rows[0]["creator_id"].startswith("C-IMP-"))

    def test_31_csv_reader_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.csv"
            path.write_text("\ufeffCreator,profile_url\nOne,https://example.com/one\n", encoding="utf-8")
            headers, rows = read_local_table(path)
            self.assertEqual(headers[0], "Creator")
            self.assertEqual(rows[0]["profile_url"], "https://example.com/one")

    def test_32_xlsx_reader_reads_first_sheet(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.xlsx"
            with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Creators" sheetId="1" r:id="rId1"/></sheets></workbook>')
                archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                archive.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Creator</t></is></c><c r="B1" t="inlineStr"><is><t>profile_url</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>One</t></is></c><c r="B2" t="inlineStr"><is><t>https://example.com/one</t></is></c></row></sheetData></worksheet>')
            headers, rows = read_local_table(path)
            self.assertEqual(headers, ["Creator", "profile_url"])
            self.assertEqual(rows[0]["Creator"], "One")

    def test_33_import_cli_preserves_original_source_copy(self):
        temp, workspace = copy_workspace(WORKSPACE)
        self.addCleanup(temp.cleanup)
        source = Path(temp.name) / "creators.csv"
        source.write_text("Creator,profile_url\nOne,https://example.com/one\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(TOOLS / "import_creator_batch.py"), str(source), "--source", str(workspace)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list((workspace / "imports").glob("creators-*.csv"))), 1)
        _, rows = read_csv(workspace / "creators.csv")
        self.assertEqual(rows[0]["name"], "One")

    def test_34_public_release_reports_non_git_copy_as_skipped(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "release"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        self.assertEqual(check_public_release.git_status(root), "Skipped — Not a Git Repository")

    def test_35_public_release_blocks_sensitive_text(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "release"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        (root / "private-note.md").write_text("internal only", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "confidential text"):
            check_public_release.check_public_text_files(root)

    def test_36_release_mode_blocks_business_rows_without_deleting(self):
        temp, workspace = copy_workspace(WORKSPACE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "creators.csv")
        rows.append({field: "" for field in fields} | {
            "creator_id": "C-PRIVATE", "name": "Private Creator", "verification_status": "Pending Verification",
        })
        write_csv(workspace / "creators.csv", fields, rows)
        root = Path(temp.name)
        workspace.rename(root / "01-workspace")
        with self.assertRaisesRegex(ValueError, "must be blank"):
            check_public_release.check_blank_workspace(root)
        _, preserved = read_csv(root / "01-workspace/creators.csv")
        self.assertEqual(preserved[0]["name"], "Private Creator")

    def test_37_workspace_has_exactly_three_csv_tables(self):
        self.assertEqual({path.name for path in WORKSPACE.glob("*.csv")}, set(FILES.values()))
        self.assertEqual({path.name for path in FIXTURE.glob("*.csv")}, set(FILES.values()))

    def test_38_folder_order_and_templates_are_present(self):
        for folder in ("01-workspace", "03-templates", "04-tools", "05-tests"):
            self.assertTrue((ROOT / folder).is_dir())
        for filename in ("negotiation-summary.md", "pricing.md", "contract-draft.md"):
            self.assertTrue((ROOT / "03-templates/collaboration" / filename).is_file())

    def test_39_public_creator_schema_excludes_legacy_decision_fields(self):
        fields, _ = read_csv(WORKSPACE / "creators.csv")
        removed = {"score", "tier", "rank", "audience_fit", "content_relevance", "engagement_quality", "audience_size_band", "brand_safety", "collaboration_readiness"}
        self.assertFalse(removed.intersection(fields))

    def test_40_root_pages_are_blank_workspace_builds(self):
        _, data = load_workspace(WORKSPACE)
        expected = {
            "creator-database-dashboard.html": creator_database_dashboard(data, WORKSPACE),
            "outreach-dashboard.html": outreach_dashboard(data, WORKSPACE),
            "performance-dashboard.html": performance_dashboard(data, WORKSPACE),
        }
        for filename, content in expected.items():
            self.assertEqual((ROOT / filename).read_text(encoding="utf-8"), content)

    def test_41_local_performance_csv_can_be_imported_without_utm(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, _ = read_csv(workspace / "performance.csv")
        write_csv(workspace / "performance.csv", fields, [])
        source = Path(temp.name) / "results.csv"
        source.write_text(
            "Creator,window,measurement date,downloads,installs,cost,currency,data source,metric definition\n"
            "Quiet Metrics Studio,D7,2026-08-21T13:10:00Z,181,123,1800,USD,User analytics,Cumulative since publication\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(TOOLS / "import_performance_data.py"), str(source), "--source", str(workspace)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        _, data = load_workspace(workspace)
        self.assertEqual(len(data["performance"]), 1)
        self.assertEqual(data["performance"][0]["utm_url"], "")

    def test_42_outreach_csv_is_name_first_and_keeps_ids_at_the_end(self):
        fields, _ = read_csv(WORKSPACE / "outreach-progress.csv")
        self.assertEqual(fields[:5], [
            "record_type", "creator_name", "status", "channels", "contact_information",
        ])
        self.assertEqual(fields[-4:], [
            "record_id", "creator_id", "collaboration_id", "deliverable_id",
        ])

    def test_43_creator_name_must_match_creator_id_when_present(self):
        temp, workspace = copy_workspace(FIXTURE)
        self.addCleanup(temp.cleanup)
        fields, rows = read_csv(workspace / "outreach-progress.csv")
        rows[0]["creator_name"] = "Wrong Channel"
        write_csv(workspace / "outreach-progress.csv", fields, rows)
        with self.assertRaisesRegex(ValueError, "does not match creator_id"):
            load_workspace(workspace)

    def test_44_recommendations_use_creator_specific_state(self):
        _, data = load_workspace(FIXTURE)
        html = creator_database_dashboard(data, FIXTURE, fixture=True)
        self.assertIn("Frame by Frame Lab: prepare the first personalised outreach via Email", html)
        self.assertIn("Workflow Weekly: negotiation is active", html)
        self.assertIn("Quiet Metrics Studio: published", html)
        self.assertNotIn("complete the most useful missing fields", html)

    def test_45_fifty_to_ten_to_three_and_partial_performance_flow(self):
        temp, workspace = copy_workspace(WORKSPACE)
        self.addCleanup(temp.cleanup)
        creator_fields, _ = read_csv(workspace / "creators.csv")
        creators = []
        for index in range(1, 51):
            row = {field: "" for field in creator_fields}
            row.update({
                "creator_id": f"C-{index:03d}",
                "name": f"Local Creator {index:02d}",
                "platform": "YouTube",
                "profile_url": f"https://example.com/channel/{index}",
                "content_category": "Productivity" if index % 2 else "Technology",
                "follower_count": str(index * 1000),
                "language": "English" if index % 3 else "",
                "country_region": "United States" if index % 4 else "",
                "public_business_email": f"creator{index}@example.com" if index % 5 else "",
                "source_file": "local-50.csv",
                "source_row": str(index + 1),
                "additional_data_json": "{}",
                "do_not_contact": "false",
            })
            creators.append(row)
        write_csv(workspace / "creators.csv", creator_fields, creators)

        progress_fields, _ = read_csv(workspace / "outreach-progress.csv")
        progress = []
        for index in range(1, 11):
            row = {field: "" for field in progress_fields}
            status = "Selected / To Contact"
            if index == 1:
                status = "Contacted"
            elif index == 2:
                status = "Replied"
            elif index == 3:
                status = "Negotiating"
            row.update({
                "record_type": "outreach",
                "creator_name": f"Local Creator {index:02d}",
                "status": status,
                "channels": "Email",
                "contact_information": f"creator{index}@example.com",
                "first_contact_at": "2026-10-01" if index <= 3 else "",
                "last_contact_at": "2026-10-02" if index <= 3 else "",
                "next_action_at": "2026-10-08" if index == 1 else "",
                "next_action": "Review reply details" if index == 2 else "Confirm open terms" if index == 3 else "",
                "owner": "Campaign lead",
                "opt_out": "false",
                "source": "User workspace",
                "record_id": f"OUT-{index:03d}",
                "creator_id": f"C-{index:03d}",
            })
            progress.append(row)
        partnership = {field: "" for field in progress_fields}
        partnership.update({
            "record_type": "partnership",
            "creator_name": "Local Creator 01",
            "status": "Published",
            "collaboration_type": "Integrated video",
            "confirmed_at": "2026-09-29",
            "published_at": "2026-10-01",
            "content_type": "YouTube video",
            "content_title": "Local workflow test",
            "owner": "Campaign lead",
            "opt_out": "false",
            "source": "User workspace",
            "record_id": "PAR-001",
            "creator_id": "C-001",
            "collaboration_id": "COL-001",
            "deliverable_id": "DEL-001",
        })
        progress.append(partnership)
        write_csv(workspace / "outreach-progress.csv", progress_fields, progress)

        performance_fields, _ = read_csv(workspace / "performance.csv")
        d7 = {field: "" for field in performance_fields}
        d7.update({
            "creator_id": "C-001", "collaboration_id": "COL-001", "deliverable_id": "DEL-001",
            "published_at": "2026-10-01", "window": "D7", "views": "1000",
            "verification_status": "User provided", "notes": "Views only at D7",
        })
        write_csv(workspace / "performance.csv", performance_fields, [d7])
        output = Path(temp.name) / "output"
        first = build(workspace, output)
        self.assertIn(">50<", first["creator-database-dashboard.html"])
        self.assertIn(">10<", first["outreach-dashboard.html"])
        self.assertIn("D7", first["performance-dashboard.html"])
        self.assertIn(">1000<", first["performance-dashboard.html"])
        self.assertIn(">N/A<", first["performance-dashboard.html"])

        d14 = {field: "" for field in performance_fields}
        d14.update({
            "creator_id": "C-001", "collaboration_id": "COL-001", "deliverable_id": "DEL-001",
            "published_at": "2026-10-01", "window": "D14", "views": "1500",
            "downloads": "100", "installs": "60", "verification_status": "User provided",
            "notes": "Views, downloads and installs at D14",
        })
        write_csv(workspace / "performance.csv", performance_fields, [d7, d14])
        second = build(workspace, output)
        self.assertIn("D14", second["performance-dashboard.html"])
        self.assertIn("D7 1,000 · D14 1,500", second["performance-dashboard.html"])
        self.assertIn('<div class="label">Total downloads</div><div class="metric">100</div>', second["performance-dashboard.html"])
        self.assertIn('<div class="label">Total installs</div><div class="metric">60</div>', second["performance-dashboard.html"])
        self.assertIn('<div class="label">Total recorded spend</div><div class="metric">N/A</div>', second["performance-dashboard.html"])
        self.assertIn(">100<", second["performance-dashboard.html"])
        self.assertIn(">60<", second["performance-dashboard.html"])


if __name__ == "__main__":
    unittest.main()

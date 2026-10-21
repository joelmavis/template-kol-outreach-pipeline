#!/usr/bin/env python3
"""Fail when the public template appears to contain working creator data or stale dashboards."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

from pipeline import FILES, ROOT, creator_database_dashboard, load_workspace, outreach_dashboard, performance_dashboard, read_csv

FORBIDDEN_MARKERS = ("youtube.com/" + "channel/", "@" + "gmail.com")
PUBLIC_PATHS = ("01-workspace", "creator-database-dashboard.html", "outreach-dashboard.html", "performance-dashboard.html")
PUBLIC_TEXT_EXTENSIONS = {".md", ".csv", ".html", ".json"}
SENSITIVE_LABEL_RE = re.compile(r"\b(?:confidential|internal only|do not share)\b", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(
    r"\b(?:api[_ -]?key|access[_ -]?token|password|private[_ -]?key)\b\s*[:=]\s*(?!\*{3}\b)\S+",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
COMMERCIAL_VALUE_RE = re.compile(
    r"\b(?:creator\s+)?(?:fee|rate|price|budget|payment(?:\s+amount)?)\b\s*[:=]\s*"
    r"(?!\*{3}(?:\s|$))(?:[$€£]\s*)?\d[\d,]*(?:\.\d+)?",
    re.IGNORECASE,
)


def fail(message):
    raise ValueError(message)


def check_blank_workspace(root):
    workspace = root / "01-workspace"
    expected_tables = set(FILES.values())
    actual_tables = {path.name for path in workspace.glob("*.csv")}
    if actual_tables != expected_tables:
        fail(f"Public workspace must contain exactly these three tables: {', '.join(sorted(expected_tables))}")
    for filename in FILES.values():
        _, rows = read_csv(workspace / filename)
        if rows:
            fail(f"Public workspace must be blank: 01-workspace/{filename} has {len(rows)} row(s)")
    if (workspace / "persona.md").exists() or (root / "persona-dashboard.html").exists():
        fail("Legacy Persona files must not be included in the v3.0 public template")
    if any(workspace.glob("drafts/*.md")) or any(workspace.glob("collaborations/**/*.md")):
        fail("Public workspace contains drafts or collaboration material")
    if any(path.is_file() and path.name != ".gitkeep" for path in (workspace / "imports").glob("**/*")):
        fail("Public workspace contains imported source files")
    creator_fields, _ = read_csv(workspace / FILES["creators"])
    removed = {"score", "tier", "rank", "audience_fit", "content_relevance", "engagement_quality", "audience_size_band", "brand_safety", "collaboration_readiness"}
    if removed.intersection(creator_fields):
        fail("Legacy scoring fields must not be included in the v3.0 creator table")
    if (root / "03-config/scoring-config.json").exists():
        fail("Legacy scoring configuration must not be included in the v3.0 template")


def check_root_dashboards(root):
    _, data = load_workspace(root / "01-workspace")
    expected = {
        "creator-database-dashboard.html": creator_database_dashboard(data, root / "01-workspace"),
        "outreach-dashboard.html": outreach_dashboard(data, root / "01-workspace"),
        "performance-dashboard.html": performance_dashboard(data, root / "01-workspace"),
    }
    for filename, content in expected.items():
        if (root / filename).read_text(encoding="utf-8") != content:
            fail(f"{filename} is stale or was not generated from the blank public workspace")


def check_fixture_domains(root):
    fixture = root / "05-tests/fixtures/sample-creator-campaign"
    expected_tables = set(FILES.values())
    actual_tables = {path.name for path in fixture.glob("*.csv")}
    if actual_tables != expected_tables:
        fail(f"Fixture must contain exactly these three tables: {', '.join(sorted(expected_tables))}")
    for csv_path in fixture.glob("*.csv"):
        _, rows = read_csv(csv_path)
        for row in rows:
            for field, value in row.items():
                value = value.strip()
                if not value:
                    continue
                if field.endswith("_url") or field in {"profile_url", "evidence_url", "metric_source", "business_email_source", "dm_url", "contact_page_url", "content_url", "utm_url"}:
                    host = urlparse(value).hostname
                    if host and host != "example.com" and not host.endswith(".example.com"):
                        fail(f"Fixture uses a non-reserved URL in {csv_path.name}:{field}")
                if "email" in field and "@" in value and not value.lower().endswith("@example.com"):
                    fail(f"Fixture uses a non-reserved email in {csv_path.name}:{field}")


def check_public_text_files(root):
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in PUBLIC_TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in text.lower():
                fail(f"Potential private business data found in {path.relative_to(root)}: {marker}")
        if SENSITIVE_LABEL_RE.search(text):
            fail(f"Potential confidential text found in {path.relative_to(root)}")
        if SECRET_VALUE_RE.search(text):
            fail(f"Potential credential found in {path.relative_to(root)}")
        relative = path.relative_to(root)
        in_fixture = relative.parts[:2] == ("05-tests", "fixtures")
        if not in_fixture and COMMERCIAL_VALUE_RE.search(text):
            fail(f"Potential unredacted commercial terms found in {relative}")
        for match in EMAIL_RE.finditer(text):
            domain = match.group(1).lower()
            if domain != "example.com" and not domain.endswith(".example.com"):
                fail(f"Potential private email found in {relative}")


def git_status(root):
    if not (root / ".git").exists():
        return "Skipped — Not a Git Repository"
    result = subprocess.run(
        ["git", "status", "--short", "--", *PUBLIC_PATHS], cwd=root, capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"Skipped — Git status unavailable ({result.stderr.strip() or 'unknown error'})"
    return result.stdout.rstrip() or "clean"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository or release-copy root to inspect")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        check_blank_workspace(root)
        check_root_dashboards(root)
        check_fixture_domains(root)
        check_public_text_files(root)
    except (OSError, ValueError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 1
    print("OK public-release data boundary: blank workspace and imports, blank-derived root dashboards, isolated reserved-domain fixtures, public text scan")
    print("Git status:", git_status(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

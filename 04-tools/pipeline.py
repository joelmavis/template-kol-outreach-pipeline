#!/usr/bin/env python3
"""Validate a local-first creator workflow and render three static dashboards."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from html import escape
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "creators": "creators.csv",
    "progress": "outreach-progress.csv",
    "performance": "performance.csv",
}
CREATOR_VERIFICATION_STATES = {"Verified", "Partial", "Pending Verification"}
PROGRESS_TYPES = {"outreach", "activity", "partnership"}
OUTREACH_STATES = {
    "Selected / To Contact", "Contacted", "Replied", "Negotiating", "Confirmed",
    "Published", "Completed", "Paused", "Opted out", "Closed Lost",
}
PARTNERSHIP_STATES = {"Negotiating", "Confirmed", "Published", "Completed", "Closed Lost"}
WINDOW_ORDER = {"D7": 7, "D14": 14, "D30": 30}
COUNT_FIELDS = ("views", "clicks", "downloads", "installs", "activated_users")
SPEND_ADJUSTMENT_RE = re.compile(r"\[Spend adjustment:\s*[^\]]+\]", re.IGNORECASE)


def number(value, label, *, allow_blank=False):
    raw = str(value or "").strip()
    if allow_blank and raw.casefold() in {"", "n/a", "unknown", "pending"}:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected a finite number")
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError(f"{label}: expected a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{label}: expected a finite number")
    return result


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or duplicate CSV headers")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"{path}: malformed row width")
        return reader.fieldnames, rows


def write_csv(path, fields, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def unique_id(rows, field, label):
    seen = set()
    for row in rows:
        value = row.get(field, "").strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value) or value.casefold() in seen:
            raise ValueError(f"Invalid or duplicate {label}: {value or '<blank>'}")
        seen.add(value.casefold())


def parse_temporal(value, label, *, allow_blank=True):
    raw = str(value or "").strip()
    if not raw and allow_blank:
        return None
    if not raw:
        raise ValueError(f"{label}: required ISO date or datetime")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return datetime.combine(date.fromisoformat(raw), time.min, tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"{label}: invalid ISO date or datetime") from None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label}: invalid ISO date or datetime") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized_profile_url(value):
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.netloc.lower()}{path}".casefold()


def validate_url(value, label, *, allow_blank=True):
    raw = str(value or "").strip()
    if not raw and allow_blank:
        return
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label}: expected an HTTP(S) URL")


def merge_creator_batch(existing_rows, batch_rows, fields):
    """Merge a batch by creator ID or channel URL without overwriting collected values."""
    merged = [{field: row.get(field, "") for field in fields} for row in existing_rows]
    by_id = {row["creator_id"].strip().casefold(): row for row in merged if row.get("creator_id", "").strip()}
    by_url = {normalized_profile_url(row.get("profile_url")): row for row in merged if normalized_profile_url(row.get("profile_url"))}
    for incoming_raw in batch_rows:
        incoming = {field: str(incoming_raw.get(field, "") or "").strip() for field in fields}
        creator_id = incoming.get("creator_id", "")
        name = incoming.get("name", "")
        if not creator_id or not name:
            raise ValueError("Creator batch rows require creator_id and name")
        profile_key = normalized_profile_url(incoming.get("profile_url"))
        id_match = by_id.get(creator_id.casefold())
        url_match = by_url.get(profile_key) if profile_key else None
        if id_match is not None and url_match is not None and id_match is not url_match:
            raise ValueError(f"{creator_id}: creator_id and channel URL match different existing rows")
        target = id_match or url_match
        if target is None:
            target = {field: "" for field in fields}
            target.update(incoming)
            merged.append(target)
        else:
            for field, value in incoming.items():
                current = str(target.get(field, "") or "").strip()
                if value and value.casefold() not in {"unknown", "n/a", "not available"} and current.casefold() in {"", "unknown", "n/a", "not available"}:
                    target[field] = value
        by_id[target["creator_id"].strip().casefold()] = target
        normalized = normalized_profile_url(target.get("profile_url"))
        if normalized:
            by_url[normalized] = target
    return merged


def split_progress(rows):
    if rows:
        unique_id(rows, "record_id", "outreach-progress record_id")
    result = {"outreach": [], "events": [], "partnerships": []}
    for row in rows:
        record_type = row.get("record_type", "").strip().lower()
        if record_type not in PROGRESS_TYPES:
            raise ValueError(f"outreach-progress: invalid record_type {record_type or '<blank>'}")
        if record_type == "outreach":
            result["outreach"].append(row)
        elif record_type == "activity":
            event = dict(row)
            event["event_id"] = row["record_id"]
            result["events"].append(event)
        else:
            result["partnerships"].append(row)
    return result


def validate_creators(rows):
    if rows:
        unique_id(rows, "creator_id", "creator_id")
    seen_urls = set()
    for row in rows:
        creator_id = row["creator_id"]
        if not row.get("name", "").strip():
            raise ValueError(f"{creator_id}: channel name is required")
        profile = row.get("profile_url", "").strip()
        if profile:
            validate_url(profile, f"{creator_id} profile_url")
            normalized = normalized_profile_url(profile)
            if normalized in seen_urls:
                raise ValueError(f"Duplicate YouTube channel URL for {creator_id}")
            seen_urls.add(normalized)
        status = row.get("verification_status", "").strip()
        status = {"Pending": "Pending Verification", "Needs verification": "Pending Verification"}.get(status, status)
        if status and status not in CREATOR_VERIFICATION_STATES:
            raise ValueError(f"{creator_id}: invalid verification_status {status}")
        row["verification_status"] = status
        parse_temporal(row.get("checked_at"), f"{creator_id} checked_at")
        if row.get("follower_count", "").strip() and row.get("follower_count", "").strip().casefold() != "unknown":
            count = number(row["follower_count"], f"{creator_id} follower_count")
            if count < 0:
                raise ValueError(f"{creator_id}: follower_count cannot be negative")
        extra = row.get("additional_data_json", "").strip()
        if extra:
            try:
                value = json.loads(extra)
            except json.JSONDecodeError:
                raise ValueError(f"{creator_id}: additional_data_json must be valid JSON") from None
            if not isinstance(value, dict):
                raise ValueError(f"{creator_id}: additional_data_json must be a JSON object")


def validate_relations(data, source):
    creators = data["creators"]
    creator_ids = {row["creator_id"] for row in creators}
    creator_by_id = {row["creator_id"]: row for row in creators}
    for name in ("outreach", "events", "partnerships", "performance"):
        for row in data[name]:
            if row.get("creator_id") not in creator_ids:
                raise ValueError(f"{name}: unknown creator_id {row.get('creator_id')}")
            expected_name = creator_by_id[row["creator_id"]].get("name", "").strip()
            stored_name = row.get("creator_name", "").strip()
            if stored_name and stored_name.casefold() != expected_name.casefold():
                raise ValueError(
                    f"{name}: creator_name {stored_name} does not match creator_id {row['creator_id']}"
                )
            row["creator_name"] = expected_name

    current_seen = set()
    for row in data["outreach"]:
        cid = row["creator_id"]
        if cid in current_seen:
            raise ValueError(f"outreach: creator {cid} must have one current-state row")
        current_seen.add(cid)
        if row.get("status") not in OUTREACH_STATES:
            raise ValueError(f"outreach: invalid status {row.get('status')}")
        if row.get("opt_out", "").lower() == "true" and row["status"] != "Opted out":
            raise ValueError(f"outreach: {cid} opt_out requires Opted out status")
        parse_temporal(row.get("first_contact_at"), f"{cid} first_contact_at")
        parse_temporal(row.get("last_contact_at"), f"{cid} last_contact_at")
        parse_temporal(row.get("next_action_at"), f"{cid} next_action_at")

    for row in data["events"]:
        parse_temporal(row.get("event_at"), f"{row['record_id']} event_at", allow_blank=False)

    partnership_keys = set()
    partnership_by_key = {}
    published = set()
    for row in data["partnerships"]:
        key = (row.get("collaboration_id", ""), row.get("deliverable_id", ""))
        if not all(key) or key in partnership_keys:
            raise ValueError(f"partnerships: duplicate or incomplete collaboration/deliverable key {key}")
        partnership_keys.add(key)
        partnership_by_key[key] = row
        status = row.get("status")
        if status not in PARTNERSHIP_STATES:
            raise ValueError(f"partnerships: invalid status {status}")
        folder = row.get("collaboration_folder", "").strip()
        if status == "Negotiating" and not folder:
            raise ValueError(f"partnerships: {key} Negotiating requires collaboration_folder")
        if folder:
            if Path(folder).is_absolute() or ".." in Path(folder).parts:
                raise ValueError(f"partnerships: {key} collaboration_folder must stay inside the workspace")
            collaboration_dir = source / folder
            for filename in ("negotiation-summary.md", "pricing.md", "contract-draft.md"):
                if status == "Negotiating" and not (collaboration_dir / filename).is_file():
                    raise ValueError(f"partnerships: {key} missing {folder}/{filename}")
        if status in {"Published", "Completed"}:
            if not row.get("confirmed_at") or not row.get("published_at"):
                raise ValueError(f"partnerships: {key} needs confirmation and publication dates")
            confirmed = parse_temporal(row["confirmed_at"], f"partnerships {key} confirmed_at", allow_blank=False)
            published_at = parse_temporal(row["published_at"], f"partnerships {key} published_at", allow_blank=False)
            if confirmed > published_at:
                raise ValueError(f"partnerships: {key} confirmed_at must not be after published_at")
            published.add(key)
        elif row.get("published_at"):
            raise ValueError(f"partnerships: unpublished state {status} cannot have published_at")
        validate_url(row.get("utm_url"), f"partnerships {key} utm_url")

    snapshots = defaultdict(list)
    for row in data["performance"]:
        key = (row.get("collaboration_id", ""), row.get("deliverable_id", ""))
        if key not in published:
            raise ValueError(f"performance: {key} is not a published deliverable")
        partnership = partnership_by_key[key]
        if row.get("creator_id") != partnership.get("creator_id"):
            raise ValueError(f"performance: {key} creator_id does not match partnership")
        window = row.get("window")
        if window not in WINDOW_ORDER:
            raise ValueError(f"performance: invalid window {window}")
        if row.get("published_at"):
            recorded_d0 = parse_temporal(row["published_at"], f"performance {key} published_at", allow_blank=False)
            partnership_d0 = parse_temporal(partnership["published_at"], f"partnerships {key} published_at", allow_blank=False)
            if recorded_d0 != partnership_d0:
                raise ValueError(f"performance: {key} published_at does not match partnership D0")
        status = row.get("verification_status", "").strip() or "Pending Verification"
        if status not in {"Verified", "User provided", "Pending Verification", "Illustrative"}:
            raise ValueError(f"performance: {key} invalid verification_status {status}")
        parse_temporal(row.get("measured_at"), f"performance {key} measured_at")
        validate_url(row.get("utm_url"), f"performance {key} utm_url")
        for field in COUNT_FIELDS + ("spend",):
            value = number(row.get(field), f"performance {key} {field}", allow_blank=True)
            if value is not None and value < 0:
                raise ValueError(f"performance {key} {field}: cannot be negative")
        snapshots[key].append(row)

    for key, rows in snapshots.items():
        if len(rows) != len({row["window"] for row in rows}):
            raise ValueError(f"performance: duplicate window for {key}")
        ordered = sorted(rows, key=lambda row: WINDOW_ORDER[row["window"]])
        for field in COUNT_FIELDS:
            previous = None
            for row in ordered:
                value = number(row.get(field), f"performance {key} {field}", allow_blank=True)
                if value is not None and previous is not None and value < previous:
                    raise ValueError(f"performance: cumulative {field} decreases for {key}")
                if value is not None:
                    previous = value
        previous_spend = None
        for row in ordered:
            spend = number(row.get("spend"), f"performance {key} spend", allow_blank=True)
            if spend is not None and previous_spend is not None and spend < previous_spend:
                if not SPEND_ADJUSTMENT_RE.search(row.get("notes", "")):
                    raise ValueError(f"performance: cumulative spend decreases for {key}; add [Spend adjustment: reason] to notes")
            if spend is not None:
                previous_spend = spend

    for draft in source.glob("drafts/*.md"):
        creator = creator_by_id.get(draft.stem)
        if not creator:
            raise ValueError(f"drafts: {draft.name} has no matching creator")
        if creator.get("do_not_contact", "").lower() == "true":
            raise ValueError(f"drafts: {draft.name} belongs to a do-not-contact creator")


def load_workspace(source, **_ignored):
    source = Path(source)
    fields, data = {}, {}
    for key, filename in FILES.items():
        fields[key], data[key] = read_csv(source / filename)
    progress = data.pop("progress")
    data.update(split_progress(progress))
    validate_creators(data["creators"])
    validate_relations(data, source)
    return fields, data


def fmt(value, empty="Not recorded"):
    return escape(str(value).strip()) if str(value).strip() else empty


def badge(text, tone="neutral"):
    return f'<span class="badge {tone}">{escape(str(text))}</span>'


def table(headers, rows, empty):
    if not rows:
        return f'<div class="empty">{escape(empty)}</div>'
    head = "".join(f"<th>{escape(label)}</th>" for label in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


CHART_COLORS = ("#256b52", "#315f77", "#a86e19", "#9b4a4a", "#718f78", "#77638f")


def compact_number(value):
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return f"{value:,.0f}"


def donut_chart(items, *, aria_label, center_value, center_label):
    prepared = [(str(label), float(value), color) for label, value, color in items if float(value) > 0]
    total = sum(value for _, value, _ in prepared)
    if total <= 0:
        return '<div class="empty">No eligible records yet, so no distribution is shown.</div>'
    radius, circumference, offset = 72, 2 * math.pi * 72, 0.0
    segments, legends = [], []
    for label, value, color in prepared:
        length = circumference * value / total
        segments.append(f'<circle cx="110" cy="110" r="{radius}" fill="none" stroke="{color}" stroke-width="24" stroke-dasharray="{length:.3f} {circumference-length:.3f}" stroke-dashoffset="{-offset:.3f}" />')
        offset += length
        legends.append(f'<div class="legend-item"><span class="swatch" style="background:{color}"></span><span><b>{escape(label)}</b><small>{value:,.0f} · {value/total*100:.0f}%</small></span></div>')
    return f'<div class="chart-layout"><div class="donut-wrap"><svg class="donut" viewBox="0 0 220 220" role="img" aria-label="{escape(aria_label)}"><circle cx="110" cy="110" r="{radius}" fill="none" stroke="#ebe5dc" stroke-width="24"/><g transform="rotate(-90 110 110)">{"".join(segments)}</g><text x="110" y="105" text-anchor="middle" class="chart-center-value">{escape(str(center_value))}</text><text x="110" y="126" text-anchor="middle" class="chart-center-label">{escape(center_label)}</text></svg></div><div class="legend">{"".join(legends)}</div></div>'


def horizontal_bars(items, *, aria_label, empty_message, suffix="", scale_max=None):
    prepared = [(str(label), float(value), detail, color) for label, value, detail, color in items]
    if not prepared or not any(value > 0 for _, value, _, _ in prepared):
        return f'<div class="empty">{escape(empty_message)}</div>'
    maximum = float(scale_max) if scale_max is not None else max(value for _, value, _, _ in prepared) or 1
    rows = []
    for label, value, detail, color in prepared:
        width = min(100, value / maximum * 100) if value > 0 else 0
        shown = f"{value:,.1f}" if suffix == "%" else f"{value:,.0f}"
        rows.append(f'<div class="bar-row"><div class="bar-heading"><b>{escape(label)}</b><span>{shown}{escape(suffix)}</span></div><div class="bar-track" role="img" aria-label="{escape(label)}: {shown}{escape(suffix)}"><i style="width:{width:.2f}%;background:{color}"></i></div><small>{escape(detail)}</small></div>')
    return f'<div class="bar-chart" aria-label="{escape(aria_label)}">{"".join(rows)}</div>'


def line_chart(labels, series, *, aria_label):
    numeric = [value for _, values, _ in series for value in values if value is not None]
    if not numeric:
        return '<div class="empty">No eligible D7, D14 or D30 measurements yet, so no trend is shown.</div>'
    width, height, left, right, top, bottom = 680, 280, 58, 22, 22, 48
    plot_w, plot_h, maximum = width-left-right, height-top-bottom, max(numeric) or 1
    xs = [left + plot_w * index / max(1, len(labels)-1) for index in range(len(labels))]
    grid = []
    for index in range(5):
        fraction = index / 4
        y = top + plot_h * fraction
        grid.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" class="grid-line"/><text x="{left-9}" y="{y+4:.2f}" text-anchor="end" class="axis-label">{escape(compact_number(maximum*(1-fraction)))}</text>')
    paths, legends = [], []
    for name, values, color in series:
        points, exact = [], []
        for label, x, value in zip(labels, xs, values):
            if value is None:
                continue
            y = top + plot_h - float(value)/maximum*plot_h
            points.append(f"{x:.2f},{y:.2f}")
            paths.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"><title>{escape(name)} · {escape(label)}: {float(value):,.0f}</title></circle>')
            exact.append(f"{label} {float(value):,.0f}")
        if len(points) > 1:
            paths.insert(0, f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
        legends.append(f'<div class="series-key"><span class="swatch" style="background:{color}"></span><span><b>{escape(name)}</b><small>{escape(" · ".join(exact))}</small></span></div>')
    x_axis = "".join(f'<text x="{x:.2f}" y="{height-17}" text-anchor="middle" class="axis-label">{escape(label)}</text>' for label, x in zip(labels, xs))
    return f'<div class="line-chart"><svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria_label)}">{"".join(grid)}{"".join(paths)}{x_axis}</svg><div class="series-legend">{"".join(legends)}</div></div>'


def page(title, eyebrow, intro, body, *, fixture=False):
    note = '<div class="sample">Test fixture · Illustrative data and fictional creators</div>' if fixture else ""
    footer = "Test fixture · Illustrative data and fictional creators" if fixture else "Creator Outreach Pipeline · Generated from local workspace files"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · Creator Outreach Pipeline</title><style>
:root{{--ink:#18211f;--muted:#66716d;--paper:#f6f3ed;--card:#fffdfa;--line:#ded8ce;--green:#256b52;--sage:#dfeae2;--gold:#a86e19;--rose:#9b4a4a;--blue:#315f77}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}main{{max-width:1180px;margin:auto;padding:48px 28px 72px}}header{{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:26px}}.eyebrow{{color:var(--green);font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}h1{{font:700 clamp(34px,6vw,64px)/1.02 Georgia,serif;max-width:800px;margin:10px 0 14px}}h2{{font:700 27px/1.15 Georgia,serif;margin:0 0 14px}}h3{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px}}p{{max-width:820px}}.intro{{font-size:18px;color:#3e4845}}.sample{{display:inline-block;margin-top:15px;padding:6px 10px;border:1px solid #c9bba4;border-radius:999px;color:#745b37;font-size:12px}}.record-id{{display:block;color:var(--muted);font-size:11px;font-weight:500;margin-top:3px}}.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;margin:18px 0 28px}}.card{{grid-column:span 4;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 8px 24px #332a1c0a}}.wide{{grid-column:span 12}}.half{{grid-column:span 6}}.quarter{{grid-column:span 3}}.metric{{font:700 34px/1 Georgia,serif;margin:7px 0}}.label,.muted{{color:var(--muted)}}.badge{{display:inline-block;border-radius:999px;padding:4px 9px;background:#e9ecea;font-size:12px;white-space:nowrap}}.good{{background:var(--sage);color:#174a38}}.warn{{background:#f4e8cf;color:#765018}}.risk{{background:#f3dddd;color:#7c3333}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}}table{{border-collapse:collapse;width:100%;min-width:720px}}th,td{{padding:12px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#eee9e0;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}tr:last-child td{{border-bottom:0}}.empty{{border:1px dashed #b8b1a6;border-radius:14px;padding:26px;color:var(--muted);background:#fbf9f5}}.path{{font-family:ui-monospace,SFMono-Regular,monospace;background:#ece8df;border-radius:7px;padding:2px 6px}}footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}.chart-layout{{display:grid;grid-template-columns:minmax(210px,.7fr) minmax(260px,1.3fr);gap:24px;align-items:center}}.donut-wrap{{max-width:260px;margin:auto;width:100%}}.donut{{display:block;width:100%;height:auto}}.chart-center-value{{font:700 28px Georgia,serif;fill:var(--ink)}}.chart-center-label{{font-size:11px;fill:var(--muted);text-transform:uppercase;letter-spacing:.08em}}.legend{{display:grid;gap:10px}}.legend-item,.series-key{{display:flex;gap:10px;align-items:flex-start}}.legend-item small,.series-key small,.bar-row small{{display:block;color:var(--muted);margin-top:2px}}.swatch{{width:11px;height:11px;border-radius:3px;flex:0 0 auto;margin-top:5px}}.bar-chart{{display:grid;gap:15px;margin-top:12px}}.bar-heading{{display:flex;justify-content:space-between;gap:16px}}.bar-track{{height:10px;background:#ebe5dc;border-radius:99px;overflow:hidden;margin:6px 0 4px}}.bar-track i{{display:block;height:100%;border-radius:99px}}.line-chart svg{{display:block;width:100%;height:auto}}.grid-line{{stroke:#ded8ce;stroke-width:1}}.axis-label{{fill:var(--muted);font-size:12px}}.series-legend{{display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:12px}}.chart-note{{color:var(--muted);font-size:13px;margin-top:12px}}.chart-stack{{display:grid;gap:16px}}.chart-panel{{border-top:1px solid var(--line);padding-top:18px}}.chart-panel:first-child{{border-top:0;padding-top:0}}@media(max-width:900px){{.half{{grid-column:span 12}}.quarter{{grid-column:span 6}}}}@media(max-width:760px){{main{{padding:30px 16px 50px}}.card,.half,.quarter{{grid-column:span 12}}.chart-layout{{grid-template-columns:1fr}}.donut-wrap{{max-width:220px}}.series-legend{{display:grid}}}}</style></head><body><main><header><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1><p class="intro">{escape(intro)}</p>{note}</header>{body}<footer>{escape(footer)}</footer></main></body></html>'''


def audience_count(value):
    try:
        result = number(value, "audience count", allow_blank=True)
    except ValueError:
        return None
    return result if result is not None and result >= 0 else None


def source_path_label(source):
    source = Path(source).resolve()
    try:
        return source.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return source.as_posix()


def creator_name(creators, creator_id):
    return creators.get(creator_id, {}).get("name", "").strip() or "Unknown channel"


def creator_display(creators, creator_id):
    return f"<b>{fmt(creator_name(creators, creator_id))}</b><span class='record-id'>Internal creator ID: {fmt(creator_id)}</span>"


def content_display(partnership):
    label = partnership.get("content_title", "").strip() or partnership.get("content_type", "").strip() or "Published content"
    url = partnership.get("content_url", "").strip()
    return f"<b>{fmt(label)}</b>" + (f"<br><span class='muted'>{fmt(url)}</span>" if url else "") + f"<span class='record-id'>Internal deliverable ID: {fmt(partnership.get('deliverable_id'))}</span>"


CREATOR_COMPLETENESS_FIELDS = (
    ("profile_url", "channel URL"),
    ("handle", "channel handle"),
    ("country_region", "country / region"),
    ("language", "language"),
    ("content_category", "content category"),
    ("follower_count", "subscriber count"),
)


def creator_contact(row):
    return (
        row.get("public_business_email", "").strip()
        or row.get("dm_url", "").strip()
        or row.get("contact_page_url", "").strip()
    )


def creator_missing_fields(row):
    missing = [label for field, label in CREATOR_COMPLETENESS_FIELDS if not row.get(field, "").strip()]
    if not creator_contact(row):
        missing.append("public contact route")
    return missing


def creator_completeness(row):
    total = len(CREATOR_COMPLETENESS_FIELDS) + 1
    return round((total - len(creator_missing_fields(row))) / total * 100)


def creator_recommendation(row, outreach_row, latest_event, partnership):
    """Return one evidence-based next action, or nothing when the files do not support one."""
    name = row.get("name", "").strip() or "Unknown channel"
    status = outreach_row.get("status", "").strip() if outreach_row else ""
    relationship_contact = outreach_row.get("contact_information", "").strip() if outreach_row else ""
    contact = creator_contact(row) or relationship_contact
    if row.get("do_not_contact", "").strip().lower() == "true" or status == "Opted out":
        return f"{name}: do not contact; the current record is marked as opted out."
    if status == "Negotiating" or (partnership and partnership.get("status") == "Negotiating"):
        action = outreach_row.get("next_action", "").strip() if outreach_row else ""
        if not action:
            action = partnership.get("next_action", "").strip()
        if action:
            return f"{name}: negotiation is active — {action.rstrip('.')}."
        return None
    if status == "Selected / To Contact":
        if contact:
            route = outreach_row.get("channels", "").strip() or (
                "email" if row.get("public_business_email", "").strip() else "the recorded public contact route"
            )
            return f"{name}: prepare the first personalised outreach via {route}; no contact event is recorded yet."
        return f"{name}: add a public business email, DM link or contact page before preparing first outreach."
    if status == "Contacted":
        last_contact = outreach_row.get("last_contact_at", "").strip() or (
            latest_event.get("event_at", "").strip() if latest_event else ""
        )
        follow_up = outreach_row.get("next_action_at", "").strip()
        if follow_up:
            context = f" after the last recorded contact on {last_contact}" if last_contact else ""
            return f"{name}: follow up on {follow_up}{context}."
        if last_contact:
            return f"{name}: contacted on {last_contact}; set a follow-up date if no reply has arrived."
        return f"{name}: contact is recorded, but the latest contact date and follow-up date are missing."
    if status == "Replied":
        action = outreach_row.get("next_action", "").strip()
        if action:
            return f"{name}: replied — {action.rstrip('.')}."
        return f"{name}: a reply is recorded; capture the open question and next agreed action."
    if status in {"Confirmed", "Published", "Completed"}:
        action = outreach_row.get("next_action", "").strip()
        if action:
            return f"{name}: {status.lower()} — {action.rstrip('.')}."
        if status == "Published":
            return f"{name}: content is published; add the next available D7, D14 or D30 result."
        return None
    missing = creator_missing_fields(row)
    if missing:
        return f"{name}: missing {', '.join(missing[:3])}" + (" and other fields." if len(missing) > 3 else ".")
    return None


def creator_database_dashboard(data, source, *, fixture=False):
    creators = list(data["creators"])
    outreach = {row["creator_id"]: row for row in data["outreach"]}
    latest_events = {}
    for event in sorted(data["events"], key=lambda item: item.get("event_at", "")):
        latest_events[event["creator_id"]] = event
    partnerships = {}
    for partnership in data["partnerships"]:
        partnerships[partnership["creator_id"]] = partnership
    contactable = sum(bool(creator_contact(row)) and row.get("do_not_contact", "").lower() != "true" for row in creators)
    completeness_values = [creator_completeness(row) for row in creators]
    average_completeness = round(sum(completeness_values) / len(completeness_values)) if completeness_values else 0
    selected = sum(row.get("status") in {"Selected / To Contact", "Contacted", "Replied", "Negotiating", "Confirmed", "Published", "Completed"} for row in outreach.values())
    kpis = "".join([
        f'<section class="card quarter"><div class="label">Creators</div><div class="metric">{len(creators)}</div><div class="muted">Saved local records</div></section>',
        f'<section class="card quarter"><div class="label">Average completeness</div><div class="metric">{average_completeness}%</div><div class="muted">Fields present, not truth verification</div></section>',
        f'<section class="card quarter"><div class="label">Contactable</div><div class="metric">{contactable}</div><div class="muted">Public route recorded</div></section>',
        f'<section class="card quarter"><div class="label">Selected</div><div class="metric">{selected}</div><div class="muted">Moved to outreach</div></section>',
    ])
    bands = Counter()
    for row in creators:
        count = audience_count(row.get("follower_count"))
        bands["Unknown" if count is None else "Under 10K" if count < 10000 else "10K–49K" if count < 50000 else "50K–99K" if count < 100000 else "100K–499K" if count < 500000 else "500K+"] += 1
    band_order = ("Under 10K", "10K–49K", "50K–99K", "100K–499K", "500K+", "Unknown")
    band_chart = horizontal_bars([(label, bands[label], f"{bands[label]} creator records", CHART_COLORS[index]) for index, label in enumerate(band_order)], aria_label="Subscriber distribution", empty_message="No creator records yet, so no subscriber distribution is shown.")
    categories = Counter(row.get("content_category", "").strip() or "Unknown" for row in creators)
    category_chart = donut_chart([(label, value, CHART_COLORS[index % len(CHART_COLORS)]) for index, (label, value) in enumerate(categories.most_common(6))], aria_label="Content category distribution", center_value=len(creators), center_label="Creators")
    rows, recommendations = [], []
    for row in sorted(creators, key=lambda item: (item.get("name", "").casefold(), item["creator_id"])):
        contact = creator_contact(row)
        state = outreach.get(row["creator_id"], {}).get("status", "Not selected")
        subscriber = audience_count(row.get("follower_count"))
        missing_fields = creator_missing_fields(row)
        completeness = creator_completeness(row)
        rows.append([
            f"<b>{fmt(row.get('name'), 'Unknown channel')}</b><br><span class='muted'>{fmt(row.get('profile_url'), 'URL not recorded')}</span><span class='record-id'>Internal creator ID: {fmt(row['creator_id'])}</span>",
            f"{subscriber:,.0f}" if subscriber is not None else "Unknown",
            fmt(row.get("content_category"), "Unknown"),
            f"{fmt(row.get('language'), 'Unknown')}<br><span class='muted'>{fmt(row.get('country_region'), 'Unknown')}</span>",
            f"<b>{completeness}%</b><br><span class='muted'>{escape(', '.join(missing_fields[:3]) if missing_fields else 'No tracked field gaps')}</span>",
            fmt(contact), fmt(state), fmt(row.get("source_file") or row.get("evidence_url")), fmt(row.get("missing_evidence"), "No additional notes"),
        ])
        recommendation = creator_recommendation(
            row,
            outreach.get(row["creator_id"]),
            latest_events.get(row["creator_id"]),
            partnerships.get(row["creator_id"]),
        )
        if recommendation and len(recommendations) < 8:
            recommendations.append(recommendation)
    specs = [
        ("Channel URL", lambda r: bool(r.get("profile_url", "").strip())),
        ("Subscriber count", lambda r: audience_count(r.get("follower_count")) is not None),
        ("Language / country", lambda r: bool(r.get("language", "").strip() or r.get("country_region", "").strip())),
        ("Content category", lambda r: bool(r.get("content_category", "").strip())),
        ("Representative content", lambda r: bool(r.get("representative_content_url", "").strip())),
        ("Public contact route", lambda r: bool(r.get("public_business_email", "").strip() or r.get("dm_url", "").strip() or r.get("contact_page_url", "").strip())),
        ("Source trace", lambda r: bool(r.get("source_file", "").strip() or r.get("evidence_url", "").strip())),
    ]
    completeness = [[escape(label), str(sum(predicate(r) for r in creators)), str(len(creators)-sum(predicate(r) for r in creators)), f"{(sum(predicate(r) for r in creators)/len(creators)*100 if creators else 0):.0f}%"] for label, predicate in specs]
    next_actions = "".join(f"<li>{escape(item)}</li>" for item in recommendations) or "<li>No evidence-based next action is available yet. Add a creator record or relationship update when one becomes available.</li>"
    body = f'''<div class="grid">{kpis}</div><section class="grid"><div class="card half"><h2>Subscriber bands</h2><p class="muted">Recorded subscriber counts only; Unknown stays separate.</p>{band_chart}</div><div class="card half"><h2>Content categories</h2><p class="muted">Categories preserved from the source file or user instructions.</p>{category_chart}</div></section><section class="grid"><div class="card wide"><h2>Creator database and filter results</h2>{table(['Channel','Subscribers','Category','Language / country','Data completeness','Public contact','Filter / outreach state','Source','Missing information'], rows, 'No creators yet. Upload a local CSV or XLSX table and tell the Agent what you need.')}</div></section><section class="grid"><div class="card half"><h2>Data completeness</h2><p class="muted">Coverage means a field has a value. It does not certify that the value was externally verified.</p>{table(['Field group','Complete','Missing','Coverage'], completeness, 'No creator records yet.') if creators else '<div class="empty">No creator records yet. Completeness appears after the first import.</div>'}</div><div class="card half"><h2>Recommended next actions</h2><ul>{next_actions}</ul><p class="chart-note">Suggestions use each creator’s recorded fields, current relationship state and latest communication only.</p></div></section><p class="muted">Source of truth: <span class="path">{source_path_label(source)}/creators.csv</span>. Missing fields do not block display or import. Internal IDs remain in the data layer; the interface leads with channel names.</p>'''
    return page("Creator database", "Import, filter, continue", "A local creator database built from files you provide, with partial records preserved for later completion.", body, fixture=fixture)


def outreach_dashboard(data, source, *, fixture=False):
    creators = {row["creator_id"]: row for row in data["creators"]}
    outreach = {row["creator_id"]: row for row in data["outreach"]}
    counts = Counter(row.get("status", "") for row in outreach.values())
    contacted = sum(counts[key] for key in ("Contacted", "Replied", "Negotiating", "Confirmed", "Published", "Completed"))
    selected_total = sum(counts.values())
    stats = [
        ("Selected", selected_total), ("To contact", counts["Selected / To Contact"]),
        ("Contacted", contacted), ("Replied", sum(counts[key] for key in ("Replied", "Negotiating", "Confirmed", "Published", "Completed"))),
        ("Negotiating", counts["Negotiating"]), ("Won", sum(counts[key] for key in ("Confirmed", "Published", "Completed"))),
    ]
    metrics = "".join(f'<section class="card"><div class="label">{label}</div><div class="metric">{value}</div></section>' for label, value in stats)
    status_order = ("Selected / To Contact", "Contacted", "Replied", "Negotiating", "Confirmed", "Published", "Completed", "Paused", "Opted out", "Closed Lost")
    donut = donut_chart([(label, counts[label], CHART_COLORS[index % len(CHART_COLORS)]) for index, label in enumerate(status_order)], aria_label="Outreach status distribution", center_value=selected_total, center_label="Selected")
    interest = Counter((row.get("intent", "").strip() or "Not recorded") for row in outreach.values())
    interest_chart = horizontal_bars([(label, value, f"{value} creator records", CHART_COLORS[index % len(CHART_COLORS)]) for index, (label, value) in enumerate(interest.most_common())], aria_label="Interest distribution", empty_message="No selected creators yet, so no interest distribution is shown.")
    current_rows = []
    for cid, row in sorted(outreach.items(), key=lambda item: (creator_name(creators, item[0]).casefold(), item[0])):
        current_rows.append([creator_display(creators, cid), badge(row.get("status"), "good" if row.get("status") in {"Confirmed", "Published", "Completed"} else "warn"), fmt(row.get("channels")), fmt(row.get("contact_information")), fmt(row.get("last_contact_at")), fmt(row.get("intent")), fmt(row.get("next_action")), fmt(row.get("next_action_at"))])
    event_rows = [[fmt(row.get("event_at")), creator_display(creators, row["creator_id"]), fmt(row.get("event_type")), fmt(row.get("channel")), fmt(row.get("summary")), fmt(row.get("source"))] for row in sorted(data["events"], key=lambda item: item.get("event_at", ""), reverse=True)[:10]]
    partnership_rows = []
    for row in sorted(data["partnerships"], key=lambda item: (creator_name(creators, item["creator_id"]).casefold(), item.get("collaboration_id", ""))):
        partnership_rows.append([creator_display(creators, row["creator_id"]), fmt(row.get("collaboration_type"), "Collaboration"), badge(row.get("status"), "good" if row.get("status") in {"Confirmed", "Published", "Completed"} else "warn"), fmt(row.get("collaboration_folder")), fmt(row.get("next_action"))])
    body = f'''<div class="grid">{metrics}</div><section class="grid"><div class="card half"><h2>Outreach status</h2><p class="muted">Selected does not mean contacted; each creator appears once at the latest confirmed state.</p>{donut}</div><div class="card half"><h2>Interest signal</h2><p class="muted">Interest is recorded only from real correspondence or the user's report.</p>{interest_chart}</div></section><section class="grid"><div class="card wide"><h2>Selected creators and next steps</h2>{table(['Creator','Status','Channel','Contact information','Latest contact','Interest','Next action','Next follow-up'], current_rows, 'No creators selected. Ask the Agent to filter the Creator Database and move the chosen channels here as Selected / To Contact.')}</div></section><section class="grid"><div class="card wide"><h2>Recent communication</h2>{table(['When','Creator','Event','Channel','What happened','Source'], event_rows, 'No real contact events recorded. Drafts do not create activity.')}</div></section><section class="grid"><div class="card wide"><h2>Collaborations</h2>{table(['Creator','Format','Status','Working folder','Next action'], partnership_rows, 'No collaboration records yet. Negotiation detail belongs in the creator collaboration folder, not extra tables.')}</div></section><p class="muted">Source files: <span class="path">{source_path_label(source)}/creators.csv</span> and <span class="path">{source_path_label(source)}/outreach-progress.csv</span>. No status advances without user-provided or inspectable evidence.</p>'''
    return page("Outreach workspace", "Select, personalise, follow up", "A clear view of chosen creators, real communication, collaboration status and the next action.", body, fixture=fixture)


def ratio(a, b):
    x, y = number(a, "ratio numerator", allow_blank=True), number(b, "ratio denominator", allow_blank=True)
    return "N/A" if x is None or y in {None, 0} else f"{x/y*100:.1f}%"


def cost_value(record, denominator):
    spend = number(record.get("spend"), "spend", allow_blank=True)
    outcome = number(record.get(denominator), denominator, allow_blank=True)
    comparable = all([record.get("currency", "").strip(), record.get("attribution_source", "").strip(), record.get("metric_definition", "").strip(), record.get("verification_status") in {"Verified", "User provided", "Illustrative"}])
    if not comparable or spend is None or outcome in {None, 0}:
        return "N/A"
    return f"{record['currency']} {spend/outcome:,.2f}"


def spend_value(record):
    spend = number(record.get("spend"), "spend", allow_blank=True)
    currency = record.get("currency", "").strip()
    return "N/A" if spend is None or not currency else f"{escape(currency)} {spend:,.0f}"


def performance_dashboard(data, source=None, *, fixture=False):
    source = source or ROOT / "01-workspace"
    creators = {row["creator_id"]: row for row in data["creators"]}
    partnerships = {(row["collaboration_id"], row["deliverable_id"]): row for row in data["partnerships"] if row.get("status") in {"Published", "Completed"}}
    grouped = defaultdict(dict)
    for row in data["performance"]:
        grouped[(row["collaboration_id"], row["deliverable_id"])][row["window"]] = row
    latest_records, rows, trend_panels, insights = [], [], [], []
    comparison_groups = defaultdict(list)
    for key, partnership in partnerships.items():
        windows = grouped.get(key, {})
        latest = windows.get("D30") or windows.get("D14") or windows.get("D7")
        if not latest:
            continue
        creator = creators[partnership["creator_id"]]
        latest_records.append((creator, partnership, latest))
        labels = [window for window in ("D7", "D14", "D30") if window in windows]
        series = [
            (label, values, color)
            for metric, label, color in (
                ("views", "Views", CHART_COLORS[0]),
                ("downloads", "Downloads", CHART_COLORS[1]),
                ("installs", "Installs", CHART_COLORS[2]),
            )
            if any(
                value is not None
                for value in [number(windows[window].get(metric), metric, allow_blank=True) for window in labels]
            )
            for values in [[number(windows[window].get(metric), metric, allow_blank=True) for window in labels]]
        ]
        trend_panels.append(f'<div class="chart-panel"><h3>{fmt(creator["name"])} · {fmt(partnership.get("content_title") or partnership.get("content_type"), "Published content")}</h3>{line_chart(labels, series, aria_label=f"{creator["name"]} cumulative performance")}</div>')
        if latest.get("verification_status") == "Pending Verification":
            insights.append(f"{creator['name']}: confirm the measurement source and window before using cost or conversion results.")
        elif not latest.get("downloads", "").strip() and latest.get("views", "").strip():
            insights.append(f"{creator['name']}: {latest['window']} currently includes views only; add downloads or installs when available. Cost and conversion remain N/A.")
        elif latest.get("downloads", "").strip() == "0":
            insights.append(f"{creator['name']}: downloads are recorded as zero at {latest['window']}; review the path before scaling.")
        else:
            insights.append(f"{creator['name']}: compare {latest['window']} with another deliverable using the same definition before scaling.")
        for window in labels:
            record = windows[window]
            rows.append([creator_display(creators, partnership["creator_id"]), content_display(partnership), badge(window, "good"), fmt(record.get("views"), "N/A"), fmt(record.get("clicks"), "N/A"), fmt(record.get("downloads"), "N/A"), fmt(record.get("installs"), "N/A"), fmt(record.get("activated_users"), "N/A"), spend_value(record), cost_value(record, "downloads"), cost_value(record, "installs"), ratio(record.get("downloads"), record.get("clicks")), ratio(record.get("installs"), record.get("downloads")), fmt(record.get("verification_status"), "N/A")])
            scope = (window, record.get("attribution_source", "").strip(), record.get("metric_definition", "").strip(), record.get("currency", "").strip())
            if all(scope) and record.get("verification_status") in {"Verified", "User provided", "Illustrative"}:
                comparison_groups[scope].append((creator, partnership, record))
    comparison_panels, comparison_rows = [], []
    for (window, attribution, definition, currency), items in sorted(comparison_groups.items(), key=lambda item: (WINDOW_ORDER[item[0][0]], item[0][1:])):
        if len(items) < 2:
            continue
        chart_items = []
        for creator, partnership, record in items:
            downloads = number(record.get("downloads"), "downloads", allow_blank=True)
            installs = number(record.get("installs"), "installs", allow_blank=True)
            conversion = installs/downloads*100 if downloads not in {None, 0} and installs is not None else 0
            cpd, cpi = cost_value(record, "downloads"), cost_value(record, "installs")
            chart_items.append((creator["name"], conversion, f"CPD {cpd} · CPI {cpi}", CHART_COLORS[len(chart_items) % len(CHART_COLORS)]))
            comparison_rows.append([badge(window, "good"), creator_display(creators, partnership["creator_id"]), content_display(partnership), fmt(record.get("downloads"), "N/A"), fmt(record.get("installs"), "N/A"), cpd, cpi, fmt(attribution), fmt(definition)])
        comparison_panels.append(f'<div class="chart-panel"><h3>{escape(window)} · {escape(currency)}</h3>{horizontal_bars(chart_items, aria_label=f"{window} creator conversion comparison", empty_message="No comparable outcomes.", suffix="%", scale_max=100)}<p class="chart-note">Like-for-like only: {escape(attribution)} · {escape(definition)}.</p></div>')
    outcome_scopes, currencies = set(), set()
    spend_values, downloads_values, installs_values = [], [], []
    trusted_outcomes = bool(latest_records)
    for _, _, record in latest_records:
        spend = number(record.get("spend"), "spend", allow_blank=True)
        downloads = number(record.get("downloads"), "downloads", allow_blank=True)
        installs = number(record.get("installs"), "installs", allow_blank=True)
        currency = record.get("currency", "").strip()
        outcome_scope = (record.get("window", ""),)
        if not all(outcome_scope) or record.get("verification_status") not in {"Verified", "User provided", "Illustrative"}:
            trusted_outcomes = False
        else:
            outcome_scopes.add(outcome_scope)
        if spend is not None and currency:
            spend_values.append(spend)
            currencies.add(currency)
        if downloads is not None:
            downloads_values.append(downloads)
        if installs is not None:
            installs_values.append(installs)
    like_for_like = trusted_outcomes and len(outcome_scopes) == 1
    spend_ready = like_for_like and len(spend_values) == len(latest_records) and len(currencies) == 1
    downloads_ready = like_for_like and len(downloads_values) == len(latest_records)
    installs_ready = like_for_like and len(installs_values) == len(latest_records)
    conversion_ready = downloads_ready and installs_ready
    total_spend = f"{next(iter(currencies))} {sum(spend_values):,.0f}" if spend_ready else "N/A"
    total_downloads = f"{sum(downloads_values):,.0f}" if downloads_ready else "N/A"
    total_installs = f"{sum(installs_values):,.0f}" if installs_ready else "N/A"
    total_conversion = ratio(sum(installs_values), sum(downloads_values)) if conversion_ready else "N/A"
    kpis = "".join([f'<section class="card quarter"><div class="label">Total recorded spend</div><div class="metric">{escape(total_spend)}</div></section>', f'<section class="card quarter"><div class="label">Total downloads</div><div class="metric">{escape(total_downloads)}</div></section>', f'<section class="card quarter"><div class="label">Total installs</div><div class="metric">{escape(total_installs)}</div></section>', f'<section class="card quarter"><div class="label">Download → install</div><div class="metric">{escape(total_conversion)}</div></section>'])
    insight_items = "".join(f"<li>{escape(item)}</li>" for item in insights) or "<li>Add local performance data after a deliverable is published.</li>"
    body = f'''<div class="grid">{kpis}</div><section class="grid"><div class="card wide"><h2>Cumulative outcome trends</h2><p class="muted">D7, D14 and D30 are separate cumulative snapshots and are never added together.</p><div class="chart-stack">{"".join(trend_panels) or '<div class="empty">No eligible D7, D14 or D30 measurements yet.</div>'}</div></div></section><section class="grid"><div class="card wide"><h2>Creator efficiency comparison</h2><div class="chart-stack">{"".join(comparison_panels) or '<div class="empty">Two or more deliverables need the same window, metric definition, attribution source and currency.</div>'}</div></div></section><section class="grid"><div class="card wide"><h2>Cumulative performance windows</h2>{table(['Creator','Published content','Window','Views','Clicks','Downloads','Installs','Activated','Spend','CPD','CPI','Click → download','Download → install','Evidence'], rows, 'No performance records yet. Import local results after publication; UTM is optional.')}</div></section><section class="grid"><div class="card wide"><h2>Comparable results</h2>{table(['Window','Creator','Published content','Downloads','Installs','CPD','CPI','Attribution','Metric definition'], comparison_rows, 'Insufficient like-for-like data for comparison.')}</div></section><section class="grid"><div class="card half"><h2>Insights / Next Actions</h2><ul>{insight_items}</ul></div><div class="card half"><h2>How to read this</h2><p>Cost and conversion metrics appear only when the observation window, source, definition and currency are clear. UTM links can be recorded as a reference, but are not required for local results.</p></div></section><p class="muted">Source files: <span class="path">{source_path_label(source)}/outreach-progress.csv</span> and <span class="path">{source_path_label(source)}/performance.csv</span>.</p>'''
    return page("Partnership performance", "Published evidence only", "Local post-publication evidence, conversion efficiency and the limits that matter before the next decision.", body, fixture=fixture)


def build(source, output, *, fixture=False):
    source, output = Path(source), Path(output)
    _, data = load_workspace(source)
    output.mkdir(parents=True, exist_ok=True)
    rendered = {
        "creator-database-dashboard.html": creator_database_dashboard(data, source, fixture=fixture),
        "outreach-dashboard.html": outreach_dashboard(data, source, fixture=fixture),
        "performance-dashboard.html": performance_dashboard(data, source, fixture=fixture),
    }
    for filename, content in rendered.items():
        (output / filename).write_text(content, encoding="utf-8")
    return rendered

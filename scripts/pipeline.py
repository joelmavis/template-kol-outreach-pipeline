#!/usr/bin/env python3
"""Validate the outreach workspace, score evidence-ready creators, and render three static dashboards."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "01-kol-profile-and-scoring/scoring-config.json"
DIMENSIONS = (
    "audience_fit", "content_relevance", "engagement_quality",
    "audience_size_band", "brand_safety", "collaboration_readiness",
)
FILES = {
    "creators": "creators.csv",
    "outreach": "outreach.csv",
    "events": "activity-log.csv",
    "offers": "offers.csv",
    "partnerships": "partnerships.csv",
    "performance": "performance.csv",
}
OUTREACH_STATES = {
    "Discovered", "Scored", "Drafted", "Planned", "Sent", "Replied",
    "Negotiating", "Confirmed", "Published", "Completed", "Paused",
    "Opted out", "Closed Lost",
}
PARTNERSHIP_STATES = {"Negotiating", "Confirmed", "Published", "Completed", "Closed Lost"}
WINDOW_ORDER = {"D7": 7, "D14": 14, "D30": 30}
COUNT_FIELDS = ("views", "clicks", "downloads", "installs", "activated_users")
SPEND_ADJUSTMENT_RE = re.compile(r"\[Spend adjustment:\s*[^\]]+\]", re.IGNORECASE)


def number(value, label, *, allow_blank=False):
    if allow_blank and (value is None or str(value).strip() in {"", "N/A"}):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: expected a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{label}: expected a finite number")
    return result


def validate_config(config):
    scale = number(config.get("scale_max"), "scale_max")
    if scale <= 0:
        raise ValueError("scale_max must be positive")
    dimensions = config.get("dimensions")
    if tuple(dimensions or ()) != DIMENSIONS:
        raise ValueError("Scoring dimensions or order changed unexpectedly")
    weights = [number(value, key) for key, value in dimensions.items()]
    if any(value < 0 for value in weights) or sum(weights) <= 0:
        raise ValueError("Weights must be nonnegative with a positive total")
    tiers = config.get("tiers", [])
    if [item.get("tier") for item in tiers] != list("ABCD"):
        raise ValueError("Tiers must be A, B, C, D in that order")
    previous = 101.0
    for item in tiers:
        threshold = number(item.get("min_score"), "min_score")
        if not 0 <= threshold < previous:
            raise ValueError("Tier thresholds must strictly descend within 0..100")
        previous = threshold
    if number(tiers[-1]["min_score"], "min_score") != 0:
        raise ValueError("Tier D must start at zero")
    return config


def load_config():
    return validate_config(json.loads(CONFIG.read_text(encoding="utf-8")))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or duplicate CSV headers")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"{path}: malformed row width")
        return reader.fieldnames, rows


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
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
    """Normalize ISO dates and datetimes to UTC; date-only values mean 00:00 UTC."""
    raw_value = str(value or "").strip()
    if not raw_value and allow_blank:
        return None
    if not raw_value:
        raise ValueError(f"{label}: required ISO date or datetime")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_value):
        try:
            return datetime.combine(date.fromisoformat(raw_value), time.min, tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"{label}: invalid ISO date or datetime") from None
    raw = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{label}: invalid ISO date or datetime") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def valid_date(value, label, *, allow_blank=True):
    return parse_temporal(value, label, allow_blank=allow_blank)


def utm_value(url, parameter, label, *, required=False):
    """Return one normalized UTM value and reject missing or ambiguous attribution."""
    raw_url = str(url or "").strip()
    if not raw_url:
        if required:
            raise ValueError(f"{label}: {parameter} is required")
        return ""
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label}: expected an HTTP(S) UTM URL")
    values = [value.strip() for value in parse_qs(parsed.query, keep_blank_values=True).get(parameter, []) if value.strip()]
    if required and len(values) != 1:
        raise ValueError(f"{label}: exactly one non-empty {parameter} is required")
    if len(set(values)) > 1:
        raise ValueError(f"{label}: conflicting {parameter} values")
    return values[0] if values else ""


def add_missing(row, message):
    existing = [item.strip() for item in row.get("missing_evidence", "").split(";") if item.strip()]
    if message not in existing:
        existing.append(message)
    row["missing_evidence"] = "; ".join(existing)


def score_creators(rows, config):
    unique_id(rows, "creator_id", "creator_id")
    identities = set()
    scored = []
    total_weight = sum(float(value) for value in config["dimensions"].values())
    scale = float(config["scale_max"])
    for original in rows:
        row = dict(original)
        identity_value = row.get("profile_url", "").strip() or row.get("handle", "").strip()
        identity = (row.get("platform", "").strip().casefold(), identity_value.casefold())
        if not all(identity) or identity in identities:
            raise ValueError(f"Duplicate or incomplete platform/profile identity for {row['creator_id']}")
        identities.add(identity)
        checked_at = valid_date(row.get("checked_at", ""), f"{row['creator_id']} checked_at")
        status = row.get("verification_status", "").strip()
        ratings = [row.get(key, "").strip() for key in DIMENSIONS]
        evidence_url = row.get("evidence_url", "").strip()
        evidence_ready = bool(re.match(r"^https?://", evidence_url)) and checked_at is not None
        if row.get("public_business_email", "").strip() and not row.get("business_email_source", "").strip():
            evidence_ready = False
            add_missing(row, "Public business email source")
        if row.get("follower_count", "").strip() and not row.get("metric_source", "").strip():
            evidence_ready = False
            add_missing(row, "Follower metric source")
        if not evidence_url:
            add_missing(row, "Evidence URL")
        if checked_at is None:
            add_missing(row, "Evidence checked date")
        if status != "Verified" or not all(ratings) or not evidence_ready:
            if status == "Verified" and not evidence_ready:
                row["verification_status"] = "Needs verification"
            row.update(score="", tier="Unscored", rank="")
            scored.append(row)
            continue
        weighted = 0.0
        for key, weight in config["dimensions"].items():
            rating = number(row[key], f"{row['creator_id']} {key}")
            if not 0 <= rating <= scale:
                raise ValueError(f"{row['creator_id']} {key}: rating outside 0..{scale:g}")
            weighted += (float(weight) / total_weight) * (rating / scale)
        score = min(100.0, weighted * 100)
        tier = next(item["tier"] for item in config["tiers"] if score >= float(item["min_score"]))
        row.update(score=f"{score:.2f}", tier=tier, rank="")
        scored.append(row)
    ranked = sorted((row for row in scored if row["score"]), key=lambda r: (-float(r["score"]), r["creator_id"]))
    for index, row in enumerate(ranked, 1):
        row["rank"] = str(index)
    return scored


def validate_relations(data, source):
    creators = data["creators"]
    creator_ids = {row["creator_id"] for row in creators}
    creator_by_id = {row["creator_id"]: row for row in creators}
    for name in ("outreach", "events", "offers", "partnerships", "performance"):
        for row in data[name]:
            if row.get("creator_id") not in creator_ids:
                raise ValueError(f"{name}: unknown creator_id {row.get('creator_id')}")

    unique_id(data["events"], "event_id", "event_id") if data["events"] else None
    unique_id(data["offers"], "offer_id", "offer_id") if data["offers"] else None
    outreach_seen = set()
    for row in data["outreach"]:
        cid = row["creator_id"]
        if cid in outreach_seen:
            raise ValueError(f"outreach: creator {cid} must have one current-state row")
        outreach_seen.add(cid)
        if row["current_status"] not in OUTREACH_STATES:
            raise ValueError(f"outreach: invalid status {row['current_status']}")
        if row.get("opt_out", "").lower() == "true" and row["current_status"] != "Opted out":
            raise ValueError(f"outreach: {cid} opt_out requires Opted out status")
        valid_date(row.get("first_contact_at", ""), f"{cid} first_contact_at")
        valid_date(row.get("last_contact_at", ""), f"{cid} last_contact_at")

    event_ids = set()
    for row in data["events"]:
        if row["event_id"] in event_ids:
            raise ValueError(f"events: duplicate event_id {row['event_id']}")
        event_ids.add(row["event_id"])
        valid_date(row.get("event_at", ""), f"{row['event_id']} event_at", allow_blank=False)

    offer_by_id = {row["offer_id"]: row for row in data["offers"]}
    offer_ids = set(offer_by_id)
    selected_by_collaboration = Counter(row["collaboration_id"] for row in data["offers"] if row.get("selected", "").lower() == "true")
    if any(count > 1 for count in selected_by_collaboration.values()):
        raise ValueError("offers: only one offer may be selected per collaboration")
    partnership_keys = set()
    partnership_by_key = {}
    published = set()
    for row in data["partnerships"]:
        key = (row["collaboration_id"], row["deliverable_id"])
        if not all(key) or key in partnership_keys:
            raise ValueError(f"partnerships: duplicate or incomplete collaboration/deliverable key {key}")
        partnership_keys.add(key)
        partnership_by_key[key] = row
        status = row["status"]
        if status not in PARTNERSHIP_STATES:
            raise ValueError(f"partnerships: invalid status {status}")
        if row.get("offer_id"):
            if row["offer_id"] not in offer_ids:
                raise ValueError(f"partnerships: unknown offer_id {row['offer_id']}")
            offer = offer_by_id[row["offer_id"]]
            if offer["creator_id"] != row["creator_id"] or offer["collaboration_id"] != row["collaboration_id"]:
                raise ValueError(f"partnerships: offer {row['offer_id']} belongs to another creator or collaboration")
        if status in {"Published", "Completed"}:
            if not row.get("confirmed_at") or not row.get("published_at"):
                raise ValueError(f"partnerships: {key} needs confirmation and publication dates")
            confirmed_at = parse_temporal(row["confirmed_at"], f"partnerships {key} confirmed_at", allow_blank=False)
            published_at = parse_temporal(row["published_at"], f"partnerships {key} published_at", allow_blank=False)
            if confirmed_at > published_at:
                raise ValueError(f"partnerships: {key} confirmed_at must not be after published_at")
            tracking_verified = row.get("tracking_verified", "").strip().lower() == "true"
            utm_value(row.get("utm_url"), "utm_campaign", f"partnerships {key} utm_url", required=tracking_verified)
            utm_creator = utm_value(row.get("utm_url"), "utm_content", f"partnerships {key} utm_url")
            if utm_creator and utm_creator != row["creator_id"]:
                raise ValueError(f"partnerships: {key} utm_content does not match creator_id")
            published.add(key)
        elif row.get("published_at"):
            raise ValueError(f"partnerships: unpublished state {status} cannot have published_at")

    snapshots = defaultdict(list)
    for row in data["performance"]:
        key = (row["collaboration_id"], row["deliverable_id"])
        if key not in published:
            raise ValueError(f"performance: {key} is not a published deliverable")
        partnership = partnership_by_key[key]
        if row["creator_id"] != partnership["creator_id"]:
            raise ValueError(f"performance: {key} creator_id does not match partnership")
        tracking_verified = partnership.get("tracking_verified", "").strip().lower() == "true"
        partnership_campaign = utm_value(
            partnership.get("utm_url"), "utm_campaign", f"partnerships {key} utm_url", required=tracking_verified
        )
        performance_campaign = utm_value(
            row.get("utm_url"), "utm_campaign", f"performance {key} utm_url", required=tracking_verified
        )
        if performance_campaign != partnership_campaign:
            raise ValueError(
                f"performance: {key} utm_campaign {performance_campaign or '<blank>'} "
                f"does not match partnership campaign {partnership_campaign or '<blank>'}"
            )
        performance_creator = utm_value(row.get("utm_url"), "utm_content", f"performance {key} utm_url")
        if performance_creator and performance_creator != partnership["creator_id"]:
            raise ValueError(f"performance: {key} utm_content does not match creator_id")
        window = row.get("window")
        if window not in WINDOW_ORDER:
            raise ValueError(f"performance: invalid window {window}")
        partnership_published = parse_temporal(partnership["published_at"], f"partnerships {key} published_at", allow_blank=False)
        performance_published = parse_temporal(row.get("published_at"), f"performance {key} published_at", allow_blank=False)
        if performance_published != partnership_published:
            raise ValueError(f"performance: {key} published_at does not match partnership D0")
        measured_at = parse_temporal(row.get("measured_at"), f"performance {key} measured_at", allow_blank=False)
        if measured_at < partnership_published:
            raise ValueError(f"performance: {key} measured_at cannot be before published_at")
        expected_date = partnership_published.date() + timedelta(days=WINDOW_ORDER[window])
        if measured_at.date() != expected_date:
            raise ValueError(f"performance: {key} {window} must be measured on {expected_date.isoformat()} UTC")
        snapshots[key].append(row)
        for field in COUNT_FIELDS + ("spend",):
            value = number(row.get(field, ""), f"performance {key} {field}", allow_blank=True)
            if value is not None and value < 0:
                raise ValueError(f"performance {key} {field}: cannot be negative")
        if row.get("spend", "").strip() and "cumulative" not in row.get("metric_definition", "").casefold():
            raise ValueError(f"performance: {key} spend requires a cumulative metric_definition")
    for key, rows in snapshots.items():
        windows = [row["window"] for row in rows]
        if len(windows) != len(set(windows)):
            raise ValueError(f"performance: duplicate window for {key}")
        ordered = sorted(rows, key=lambda row: WINDOW_ORDER[row["window"]])
        for field in COUNT_FIELDS:
            previous = None
            for row in ordered:
                value = number(row.get(field, ""), f"performance {key} {field}", allow_blank=True)
                if value is not None and previous is not None and value < previous:
                    raise ValueError(f"performance: cumulative {field} decreases for {key}")
                if value is not None:
                    previous = value
        previous_spend = None
        for row in ordered:
            spend = number(row.get("spend", ""), f"performance {key} spend", allow_blank=True)
            if spend is not None and previous_spend is not None and spend < previous_spend:
                if not SPEND_ADJUSTMENT_RE.search(row.get("notes", "")):
                    raise ValueError(
                        f"performance: cumulative spend decreases for {key}; "
                        "add [Spend adjustment: reason] to notes for a documented refund or correction"
                    )
            if spend is not None:
                previous_spend = spend

    for draft in source.glob("drafts/*.md"):
        creator = creator_by_id.get(draft.stem)
        if not creator:
            raise ValueError(f"drafts: {draft.name} has no matching creator")
        if creator.get("tier") in {"D", "Unscored", ""} or creator.get("do_not_contact", "").lower() == "true":
            raise ValueError(f"drafts: {draft.name} is not eligible for outreach drafting")


def load_workspace(source, *, write_scores=False):
    source = Path(source)
    fields = {}
    data = {}
    for key, filename in FILES.items():
        fields[key], data[key] = read_csv(source / filename)
    data["creators"] = score_creators(data["creators"], load_config())
    validate_relations(data, source)
    if write_scores:
        write_csv(source / FILES["creators"], fields["creators"], data["creators"])
    return fields, data


def parse_persona(path):
    text = path.read_text(encoding="utf-8")
    values = {}
    for line in text.splitlines():
        match = re.match(r"^- ([^:]+):\s*(.*)$", line)
        if match:
            values[match.group(1).strip()] = match.group(2).strip()
    return text, values


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


def page(title, eyebrow, intro, body, *, example=False):
    note = '<div class="sample">Example · Illustrative data and fictional creators</div>' if example else ""
    footer = "Example · Illustrative data and fictional creators" if example else "Creator Outreach Pipeline · Generated from local workspace files"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · Creator Outreach Pipeline</title><style>
:root{{--ink:#18211f;--muted:#66716d;--paper:#f6f3ed;--card:#fffdfa;--line:#ded8ce;--green:#256b52;--sage:#dfeae2;--gold:#a86e19;--rose:#9b4a4a;--blue:#315f77}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}main{{max-width:1180px;margin:auto;padding:48px 28px 72px}}header{{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:26px}}.eyebrow{{color:var(--green);font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}h1{{font:700 clamp(34px,6vw,64px)/1.02 Georgia,serif;max-width:800px;margin:10px 0 14px}}h2{{font:700 27px/1.15 Georgia,serif;margin:0 0 14px}}h3{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px}}p{{max-width:820px}}.intro{{font-size:18px;color:#3e4845}}.sample{{display:inline-block;margin-top:15px;padding:6px 10px;border:1px solid #c9bba4;border-radius:999px;color:#745b37;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;margin:18px 0 28px}}.card{{grid-column:span 4;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 8px 24px #332a1c0a}}.wide{{grid-column:span 12}}.half{{grid-column:span 6}}.metric{{font:700 34px/1 Georgia,serif;margin:7px 0}}.label,.muted{{color:var(--muted)}}.badge{{display:inline-block;border-radius:999px;padding:4px 9px;background:#e9ecea;font-size:12px;white-space:nowrap}}.good{{background:var(--sage);color:#174a38}}.warn{{background:#f4e8cf;color:#765018}}.risk{{background:#f3dddd;color:#7c3333}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}}table{{border-collapse:collapse;width:100%;min-width:720px}}th,td{{padding:12px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#eee9e0;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}tr:last-child td{{border-bottom:0}}.empty{{border:1px dashed #b8b1a6;border-radius:14px;padding:26px;color:var(--muted);background:#fbf9f5}}.path{{font-family:ui-monospace,SFMono-Regular,monospace;background:#ece8df;border-radius:7px;padding:2px 6px}}.bar{{height:8px;background:#ebe5dc;border-radius:99px;overflow:hidden;margin-top:8px}}.bar i{{display:block;height:100%;background:var(--green)}}footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
@media(max-width:760px){{main{{padding:30px 16px 50px}}.card,.half{{grid-column:span 12}}}}
</style></head><body><main><header><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1><p class="intro">{escape(intro)}</p>{note}</header>{body}<footer>{escape(footer)}</footer></main></body></html>'''


def persona_dashboard(source, *, example=False):
    _, values = parse_persona(Path(source) / "persona.md")
    source_label = "example/sample-creator-campaign" if example else "workspace"
    status = values.get("Status", "Needs confirmation")
    tone = "good" if status == "Confirmed" else "warn"
    items = [
        ("Product / industry", values.get("Product / industry", "")),
        ("Target audience / market", values.get("Target audience / market", "")),
        ("Priority platforms", values.get("Priority platforms", "")),
        ("Content types", values.get("Content types", "")),
        ("Partnership goal", values.get("Partnership goal", "")),
        ("Exclusions / brand-safety rules", values.get("Exclusions / brand-safety rules", "")),
    ]
    cards = "".join(f'<section class="card half"><h3>{escape(label)}</h3><p>{fmt(value)}</p></section>' for label, value in items)
    body = f'''<div class="grid"><section class="card"><div class="label">Confirmation</div><div class="metric">{badge(status, tone)}</div><div class="muted">Version {fmt(values.get('Version',''))}</div></section>
<section class="card"><div class="label">Confirmed at</div><div class="metric" style="font-size:20px">{fmt(values.get('Confirmed at',''))}</div></section>
<section class="card"><div class="label">Source of truth</div><p><span class="path">{source_label}/persona.md</span></p></section>{cards}</div>
<section class="grid"><div class="card half"><h2>Preferences</h2><p><b>Languages / regions:</b> {fmt(values.get('Preferred languages / regions',''))}</p><p><b>Audience size:</b> {fmt(values.get('Audience size preference',''))}</p><p><b>Formats:</b> {fmt(values.get('Preferred collaboration formats',''))}</p><p><b>Budget:</b> {fmt(values.get('Budget guidance',''))}</p></div><div class="card half"><h2>Evidence and open items</h2><p><b>Sources:</b> {fmt(values.get('Sources',''))}</p><p><b>Assumptions:</b> {fmt(values.get('Assumptions',''))}</p><p><b>Open questions:</b> {fmt(values.get('Open questions',''))}</p></div></section>
<p class="muted">Confirm this persona before broad discovery. If it changes, update the version and rescore candidates from evidence. File path: <span class="path">{source_label}/persona.md</span>.</p>'''
    return page("Creator persona", "Plan and confirm", "The shared definition of who fits, why they fit, and what must be excluded before discovery begins.", body, example=example)


def outreach_dashboard(data, source, *, example=False):
    source_label = "example/sample-creator-campaign" if example else "workspace"
    creators = {row["creator_id"]: row for row in data["creators"]}
    outreach = {row["creator_id"]: row for row in data["outreach"]}
    scored = [row for row in creators.values() if row.get("score")]
    counts = Counter(row.get("current_status", "") for row in outreach.values())
    stats = [
        ("Discovered", len(creators)), ("Scored", len(scored)),
        ("Drafted", counts["Drafted"] + counts["Planned"]),
        ("Contacted", sum(counts[key] for key in ("Sent", "Replied", "Negotiating", "Confirmed", "Published", "Completed"))),
        ("Replied", sum(counts[key] for key in ("Replied", "Negotiating", "Confirmed", "Published", "Completed"))),
        ("Negotiating", counts["Negotiating"]),
    ]
    metrics = "".join(f'<section class="card"><div class="label">{label}</div><div class="metric">{value}</div></section>' for label, value in stats)
    ordered = sorted(creators.values(), key=lambda row: (int(row["rank"]) if row.get("rank") else 9999, row["creator_id"]))
    candidate_rows = []
    for row in ordered:
        state = outreach.get(row["creator_id"], {})
        score = f"{fmt(row.get('score',''), '—')} / {fmt(row.get('tier','Unscored'))}"
        verification = badge(row.get("verification_status") or "Unknown", "good" if row.get("verification_status") == "Verified" else "warn")
        candidate_rows.append([
            fmt(row["creator_id"]), f"<b>{fmt(row['name'])}</b><br><span class='muted'>{fmt(row['platform'])}</span>",
            score, verification, fmt(state.get("current_status", "Not contacted")),
            fmt(state.get("next_action", row.get("missing_evidence", ""))),
        ])
    event_rows = []
    for row in sorted(data["events"], key=lambda item: item.get("event_at", ""), reverse=True)[:8]:
        event_rows.append([fmt(row["event_at"]), fmt(row["creator_id"]), fmt(row["event_type"]), fmt(row["summary"]), fmt(row["source"])])
    offer_rows = []
    for row in sorted(data["offers"], key=lambda item: item.get("updated_at", ""), reverse=True):
        amount = row.get("negotiated_amount") or row.get("original_amount")
        offer_rows.append([fmt(row["offer_id"]), fmt(row["creator_id"]), fmt(row["collaboration_type"]), f"{fmt(row['currency'], '')} {fmt(amount, 'Not recorded')}", fmt(row["payment_terms"]), badge(row["status"], "warn" if row["status"] == "Under review" else "good")])
    body = f'''<div class="grid">{metrics}</div><section class="grid"><div class="card wide"><h2>Candidate priority and current state</h2>{table(['ID','Creator','Score / tier','Evidence','Current state','Next action or gap'], candidate_rows, 'No creators yet. Confirm the persona, then ask the Agent to discover a specific number with verifiable evidence.')}</div></section>
<section class="grid"><div class="card wide"><h2>Latest recorded activity</h2>{table(['When','Creator','Event','What happened','Source'], event_rows, 'No actual contact events recorded. Drafts do not create activity.')}</div></section>
<section class="grid"><div class="card wide"><h2>Offer versions</h2>{table(['Offer','Creator','Scope','Amount','Payment terms','Status'], offer_rows, 'No offers recorded. Keep each scope and payment option as a separate row.')}</div></section>
<p class="muted">Source files: <span class="path">{source_label}/creators.csv</span>, <span class="path">{source_label}/outreach.csv</span>, <span class="path">{source_label}/activity-log.csv</span> and <span class="path">{source_label}/offers.csv</span>. A draft or score never means a message was sent.</p>'''
    return page("Outreach workspace", "Discover, review, follow up", "A decision-ready view of evidence, priority, real contact history, negotiations and next actions.", body, example=example)


def ratio(a, b):
    x, y = number(a, "ratio numerator", allow_blank=True), number(b, "ratio denominator", allow_blank=True)
    if x is None or y in {None, 0}:
        return "—"
    return f"{x / y * 100:.1f}%"


def cost_value(record, denominator, *, tracking_verified):
    spend = number(record.get("spend", ""), "spend", allow_blank=True)
    outcome = number(record.get(denominator, ""), denominator, allow_blank=True)
    comparable_scope = all([
        tracking_verified,
        record.get("currency", "").strip(),
        record.get("attribution_source", "").strip(),
        record.get("metric_definition", "").strip(),
        record.get("verification_status", "") in {"Verified", "Illustrative"},
    ])
    if not comparable_scope or spend is None or outcome in {None, 0}:
        return "N/A"
    return f"{record['currency']} {spend / outcome:,.2f}"


def spend_value(record):
    spend = number(record.get("spend", ""), "spend", allow_blank=True)
    currency = record.get("currency", "").strip()
    if spend is None or not currency:
        return "N/A"
    return f"{escape(currency)} {spend:,.0f}" if spend.is_integer() else f"{escape(currency)} {spend:,.2f}"


def performance_dashboard(data, *, example=False):
    source_label = "example/sample-creator-campaign" if example else "workspace"
    creators = {row["creator_id"]: row for row in data["creators"]}
    partnerships = {(row["collaboration_id"], row["deliverable_id"]): row for row in data["partnerships"] if row["status"] in {"Published", "Completed"}}
    grouped = defaultdict(dict)
    for row in data["performance"]:
        grouped[(row["collaboration_id"], row["deliverable_id"])][row["window"]] = row
    published_cards = []
    rows = []
    insights = []
    comparison_groups = defaultdict(list)
    for key, partnership in partnerships.items():
        creator = creators[partnership["creator_id"]]
        windows = grouped.get(key, {})
        latest = windows.get("D30") or windows.get("D14") or windows.get("D7")
        if not latest:
            continue
        tracking_verified = partnership.get("tracking_verified", "").lower() == "true"
        latest_cpd = cost_value(latest, "downloads", tracking_verified=tracking_verified)
        latest_cpi = cost_value(latest, "installs", tracking_verified=tracking_verified)
        spend_label = spend_value(latest)
        published_cards.append(f'''<section class="card half"><h2>{fmt(creator['name'])}</h2><p>{badge(partnership['status'], 'good')} · {fmt(partnership['content_type'])}</p><p><b>D0:</b> {fmt(partnership['published_at'])}<br><b>Latest window:</b> {fmt(latest['window'])}<br><b>Attribution:</b> {fmt(latest['attribution_source'])}<br><b>Spend:</b> {spend_label}<br><b>Cost / download:</b> {latest_cpd}<br><b>Cost / install:</b> {latest_cpi}</p><p class="muted">{fmt(latest['notes'])}</p></section>''')
        if not tracking_verified or latest.get("verification_status") not in {"Verified", "Illustrative"}:
            insights.append(f"{creator['name']}: verify attribution before using cost or conversion results.")
        elif latest.get("downloads", "").strip() in {"", "0"} or latest.get("installs", "").strip() in {"", "0"}:
            insights.append(f"{creator['name']}: outcomes are missing or zero at {latest['window']}; review the landing and install path before scaling.")
        else:
            insights.append(f"{creator['name']}: {latest['window']} has attributable downloads and installs; compare the same window and definition with another deliverable before deciding whether to scale.")
        for window in ("D7", "D14", "D30"):
            record = windows.get(window)
            if not record:
                continue
            cpd = cost_value(record, "downloads", tracking_verified=tracking_verified)
            cpi = cost_value(record, "installs", tracking_verified=tracking_verified)
            spend = spend_value(record)
            rows.append([
                fmt(creator["name"]), fmt(partnership["deliverable_id"]), badge(window, "good"),
                fmt(record["views"], "—"), fmt(record["clicks"], "—"), fmt(record["downloads"], "—"),
                fmt(record["installs"], "—"), fmt(record["activated_users"], "—"),
                spend, cpd, cpi,
                ratio(record["downloads"], record["clicks"]), ratio(record["installs"], record["downloads"]),
                ratio(record["activated_users"], record["installs"]), fmt(record["verification_status"]),
            ])
            comparison_key = (
                window, record.get("attribution_source", "").strip(),
                record.get("metric_definition", "").strip(), record.get("currency", "").strip(),
            )
            if tracking_verified and all(comparison_key) and record.get("verification_status") in {"Verified", "Illustrative"}:
                comparison_groups[comparison_key].append((creator, partnership, record, cpd, cpi))
    comparison_rows = []
    for (window, attribution, definition, _currency), items in sorted(comparison_groups.items()):
        if len({partnership["deliverable_id"] for _, partnership, _, _, _ in items}) < 2:
            continue
        for creator, partnership, record, cpd, cpi in items:
            comparison_rows.append([
                badge(window, "good"), fmt(creator["name"]), fmt(partnership["deliverable_id"]),
                fmt(record["downloads"], "—"), fmt(record["installs"], "—"), cpd, cpi,
                fmt(attribution), fmt(definition),
            ])
    content = "".join(published_cards) or '<div class="card wide empty">No published deliverable has a performance record yet. Confirming a collaboration is not publication, and missing metrics are not zero.</div>'
    insight_items = "".join(f"<li>{escape(item)}</li>" for item in insights)
    if len(partnerships) < 2:
        insight_items += "<li>Insufficient data for a cross-creator recommendation; only one published deliverable is available.</li>"
    if not insight_items:
        insight_items = "<li>Insufficient data. Add a published deliverable and a verified measurement window.</li>"
    body = f'''<div class="grid">{content}</div><section class="grid"><div class="card wide"><h2>Cumulative performance windows</h2>{table(['Creator','Deliverable','Window','Views','Clicks','Downloads','Installs','Activated','Spend','Cost / download','Cost / install','Click → download','Download → install','Install → activate','Evidence'], rows, 'No eligible D7, D14 or D30 measurements. Add evidence only after publication.')}</div></section>
<section class="grid"><div class="card wide"><h2>Comparable results</h2>{table(['Window','Creator','Deliverable','Downloads','Installs','Cost / download','Cost / install','Attribution','Metric definition'], comparison_rows, 'Insufficient data for a like-for-like comparison. Two or more deliverables must share the same window, attribution source, metric definition and currency.')}</div></section>
<section class="grid"><div class="card half"><h2>Insights / Next Actions</h2><ul>{insight_items}</ul></div><div class="card half"><h2>How to read this</h2><p>D7, D14 and D30 are cumulative snapshots from each deliverable’s publication date. Do not add them together. Spend is the cumulative amount recorded for one deliverable and is repeated across windows for context, never summed. Cost metrics are N/A when spend, outcome, attribution scope or tracking verification is missing.</p></div><div class="card wide"><h2>Decision limits</h2><p>Compare formats and creators only when the observation window, attribution source, metric definition and currency match. Small samples and incomplete attribution support hypotheses, not guaranteed growth claims.</p></div></section>
<p class="muted">Source files: <span class="path">{source_label}/partnerships.csv</span> and <span class="path">{source_label}/performance.csv</span>. The stored UTM URL is evidence of link design, not by itself evidence that tracking worked.</p>'''
    return page("Partnership performance", "Published evidence only", "Cumulative post-publication evidence, conversion efficiency and the limits that matter before the next decision.", body, example=example)


def build(source, output, *, example=False):
    source, output = Path(source), Path(output)
    _, data = load_workspace(source, write_scores=True)
    output.mkdir(parents=True, exist_ok=True)
    rendered = {
        "persona-dashboard.html": persona_dashboard(source, example=example),
        "outreach-dashboard.html": outreach_dashboard(data, source, example=example),
        "performance-dashboard.html": performance_dashboard(data, example=example),
    }
    for filename, content in rendered.items():
        (output / filename).write_text(content, encoding="utf-8")
    return rendered

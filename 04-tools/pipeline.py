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
CONFIG = ROOT / "03-config/scoring-config.json"
DIMENSIONS = (
    "audience_fit", "content_relevance", "engagement_quality",
    "audience_size_band", "brand_safety", "collaboration_readiness",
)
CREATOR_VERIFICATION_STATES = {"Verified", "Partial", "Pending Verification"}
SYSTEM_MISSING_EVIDENCE = {
    "Evidence URL", "Evidence checked date", "Public business email source", "Follower metric source",
}
FILES = {
    "creators": "creators.csv",
    "progress": "outreach-progress.csv",
    "performance": "performance.csv",
}
PROGRESS_TYPES = {"outreach", "activity", "offer", "partnership"}
PROGRESS_FIELDS = {
    "outreach": (
        "creator_id", "current_status", "first_contact_at", "dm_used", "channels",
        "last_contact_at", "intent", "owner", "next_action", "next_action_at", "opt_out", "source",
    ),
    "activity": ("event_id", "creator_id", "event_at", "event_type", "channel", "summary", "source", "recorded_at"),
    "offer": (
        "offer_id", "creator_id", "collaboration_id", "offer_version", "collaboration_type",
        "content_length", "video_count", "currency", "original_amount", "negotiated_amount",
        "payment_terms", "deposit_percent", "rights", "deliverables", "timing", "updated_at",
        "selected", "status", "evidence_source",
    ),
    "partnership": (
        "collaboration_id", "creator_id", "deliverable_id", "offer_id", "status", "confirmed_at",
        "published_at", "completed_at", "content_type", "content_url", "utm_url", "tracking_verified",
        "owner", "evidence_source",
    ),
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
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def merge_creator_batch(existing_rows, batch_rows, fields):
    """Merge one discovery batch without erasing previously collected creator evidence."""
    merged = [{field: row.get(field, "") for field in fields} for row in existing_rows]
    by_id = {row.get("creator_id", "").strip().casefold(): row for row in merged if row.get("creator_id", "").strip()}
    by_url = {normalized_profile_url(row.get("profile_url", "")): row for row in merged if normalized_profile_url(row.get("profile_url", ""))}
    for incoming_raw in batch_rows:
        incoming = {field: incoming_raw.get(field, "") for field in fields}
        creator_id = incoming.get("creator_id", "").strip()
        profile_key = normalized_profile_url(incoming.get("profile_url", ""))
        if not creator_id:
            raise ValueError("Creator batch row requires creator_id")
        if not profile_key:
            raise ValueError(f"{creator_id}: creator batch row requires a valid HTTP(S) YouTube channel URL")
        id_match = by_id.get(creator_id.casefold())
        url_match = by_url.get(profile_key)
        if id_match is not None and url_match is not None and id_match is not url_match:
            raise ValueError(f"{creator_id}: creator_id and channel URL match different existing rows")
        target = id_match or url_match
        if target is None:
            target = {field: "" for field in fields}
            target.update(incoming)
            merged.append(target)
        else:
            for field, value in incoming.items():
                value = str(value or "").strip()
                if field == "creator_id" and url_match is target:
                    continue
                if value and value.casefold() not in {"unknown", "n/a", "not available"}:
                    target[field] = value
        by_id[target["creator_id"].strip().casefold()] = target
        by_url[normalized_profile_url(target.get("profile_url", ""))] = target
    return merged


def split_progress(rows):
    """Expose one consolidated progress table through the existing validated workflow model."""
    unique_id(rows, "record_id", "outreach-progress record_id") if rows else None
    result = {"outreach": [], "events": [], "offers": [], "partnerships": []}
    destinations = {"outreach": "outreach", "activity": "events", "offer": "offers", "partnership": "partnerships"}
    for row in rows:
        record_type = row.get("record_type", "").strip().lower()
        if record_type not in PROGRESS_TYPES:
            raise ValueError(f"outreach-progress: invalid record_type {record_type or '<blank>'}")
        projected = {field: row.get(field, "") for field in PROGRESS_FIELDS[record_type]}
        if record_type == "outreach":
            projected["current_status"] = row.get("status", "")
        elif record_type == "activity":
            projected["event_id"] = row["record_id"]
        elif record_type == "offer":
            projected["offer_id"] = row.get("offer_id", "") or row["record_id"]
        result[destinations[record_type]].append(projected)
    return result


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


def normalized_profile_url(value):
    """Normalize a public channel URL enough to detect repeat rows across discovery batches."""
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}".casefold()


def score_creators(rows, config):
    unique_id(rows, "creator_id", "creator_id")
    identities = set()
    scored = []
    total_weight = sum(float(value) for value in config["dimensions"].values())
    scale = float(config["scale_max"])
    for original in rows:
        row = dict(original)
        identity = normalized_profile_url(row.get("profile_url", ""))
        if not identity:
            raise ValueError(f"{row['creator_id']}: a valid HTTP(S) YouTube channel URL is required")
        if identity in identities:
            raise ValueError(f"Duplicate YouTube channel URL for {row['creator_id']}")
        identities.add(identity)
        checked_at = valid_date(row.get("checked_at", ""), f"{row['creator_id']} checked_at")
        status = row.get("verification_status", "").strip()
        status = {"Needs verification": "Pending Verification", "Pending": "Pending Verification", "": "Pending Verification"}.get(status, status)
        if status not in CREATOR_VERIFICATION_STATES:
            raise ValueError(f"{row['creator_id']}: invalid verification_status {status}")
        row["verification_status"] = status
        existing_missing = [
            item.strip() for item in row.get("missing_evidence", "").split(";")
            if item.strip() and item.strip() not in SYSTEM_MISSING_EVIDENCE and not item.strip().startswith("Scoring ratings:")
        ]
        row["missing_evidence"] = "; ".join(existing_missing)
        ratings = [row.get(key, "").strip() for key in DIMENSIONS]
        evidence_url = row.get("evidence_url", "").strip()
        basic_evidence_ready = bool(re.match(r"^https?://", evidence_url)) and checked_at is not None
        evidence_ready = basic_evidence_ready
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
        missing_ratings = [DIMENSION_LABELS.get(key, key.replace("_", " ")) for key, value in zip(DIMENSIONS, ratings) if not value]
        if missing_ratings:
            add_missing(row, "Scoring ratings: " + ", ".join(missing_ratings))
        if status == "Verified" and (not all(ratings) or not evidence_ready):
            row["verification_status"] = "Partial" if evidence_url and checked_at is not None else "Pending Verification"
            status = row["verification_status"]
        elif status == "Partial" and not basic_evidence_ready:
            row["verification_status"] = "Pending Verification"
            status = row["verification_status"]
        if status == "Pending Verification" or not all(ratings) or not evidence_ready:
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
    progress_rows = data.pop("progress")
    data.update(split_progress(progress_rows))
    data["creators"] = score_creators(data["creators"], load_config())
    validate_relations(data, source)
    if write_scores:
        write_csv(source / FILES["creators"], fields["creators"], data["creators"])
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
DIMENSION_LABELS = {
    "audience_fit": "Audience fit",
    "content_relevance": "Content relevance",
    "engagement_quality": "Engagement quality",
    "audience_size_band": "Audience size",
    "brand_safety": "Brand safety",
    "collaboration_readiness": "Collaboration readiness",
}


def compact_number(value):
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return f"{value:,.0f}"


def donut_chart(items, *, aria_label, center_value, center_label, value_suffix=""):
    """Render a labelled, dependency-free SVG donut from non-negative source values."""
    prepared = [(str(label), float(value), color) for (label, value, color) in items if float(value) > 0]
    total = sum(value for _, value, _ in prepared)
    if total <= 0:
        return '<div class="empty">No eligible records yet, so no distribution is shown.</div>'
    radius = 72
    circumference = 2 * math.pi * radius
    offset = 0.0
    segments = []
    legends = []
    for label, value, color in prepared:
        length = circumference * value / total
        segments.append(
            f'<circle cx="110" cy="110" r="{radius}" fill="none" stroke="{color}" stroke-width="24" '
            f'stroke-dasharray="{length:.3f} {circumference - length:.3f}" stroke-dashoffset="{-offset:.3f}" />'
        )
        offset += length
        share = value / total * 100
        display_value = f"{value:,.0f}{value_suffix} weight" if value_suffix else f"{value:,.0f} · {share:.0f}% of total"
        legends.append(
            f'<div class="legend-item"><span class="swatch" style="background:{color}"></span>'
            f'<span><b>{escape(label)}</b><small>{escape(display_value)}</small></span></div>'
        )
    return f'''<div class="chart-layout"><div class="donut-wrap"><svg class="donut" viewBox="0 0 220 220" role="img" aria-label="{escape(aria_label)}">
<circle cx="110" cy="110" r="{radius}" fill="none" stroke="#ebe5dc" stroke-width="24" />
<g transform="rotate(-90 110 110)">{''.join(segments)}</g>
<text x="110" y="105" text-anchor="middle" class="chart-center-value">{escape(str(center_value))}</text>
<text x="110" y="126" text-anchor="middle" class="chart-center-label">{escape(center_label)}</text></svg></div>
<div class="legend">{''.join(legends)}</div></div>'''


def horizontal_bars(items, *, aria_label, empty_message, suffix="", scale_max=None):
    """Render accessible CSS bars while keeping exact values visible as text."""
    prepared = [(str(label), float(value), detail, color) for label, value, detail, color in items]
    if not prepared or not any(value > 0 for _, value, _, _ in prepared):
        return f'<div class="empty">{escape(empty_message)}</div>'
    maximum = float(scale_max) if scale_max is not None else (max(value for _, value, _, _ in prepared) or 1)
    rows = []
    for label, value, detail, color in prepared:
        width = min(100, value / maximum * 100) if value > 0 else 0
        value_text = f"{value:,.1f}" if suffix == "%" else f"{value:,.0f}"
        rows.append(f'''<div class="bar-row"><div class="bar-heading"><b>{escape(label)}</b><span>{value_text}{escape(suffix)}</span></div>
<div class="bar-track" role="img" aria-label="{escape(label)}: {value_text}{escape(suffix)}"><i style="width:{width:.2f}%;background:{color}"></i></div>
<small>{escape(detail)}</small></div>''')
    return f'<div class="bar-chart" aria-label="{escape(aria_label)}">{"".join(rows)}</div>'


def line_chart(labels, series, *, aria_label):
    """Render a compact SVG line chart from recorded cumulative values only."""
    numeric = [value for _, values, _ in series for value in values if value is not None]
    if not numeric:
        return '<div class="empty">No eligible D7, D14 or D30 measurements yet, so no trend is shown.</div>'
    width, height = 680, 280
    left, right, top, bottom = 58, 22, 22, 48
    plot_w, plot_h = width - left - right, height - top - bottom
    maximum = max(numeric) or 1
    x_positions = [left + (plot_w * index / max(1, len(labels) - 1)) for index in range(len(labels))]
    grid = []
    for index in range(5):
        fraction = index / 4
        y = top + plot_h * fraction
        value = maximum * (1 - fraction)
        grid.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" class="grid-line" />'
            f'<text x="{left-9}" y="{y+4:.2f}" text-anchor="end" class="axis-label">{escape(compact_number(value))}</text>'
        )
    x_axis = "".join(
        f'<text x="{x:.2f}" y="{height-17}" text-anchor="middle" class="axis-label">{escape(label)}</text>'
        for label, x in zip(labels, x_positions)
    )
    paths, legends = [], []
    for name, values, color in series:
        points = []
        dots = []
        exact = []
        for label, x, value in zip(labels, x_positions, values):
            if value is None:
                continue
            y = top + plot_h - (float(value) / maximum * plot_h)
            points.append(f"{x:.2f},{y:.2f}")
            dots.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"><title>{escape(name)} · {escape(label)}: {float(value):,.0f}</title></circle>')
            exact.append(f"{label} {float(value):,.0f}")
        if len(points) > 1:
            paths.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />')
        paths.extend(dots)
        legends.append(
            f'<div class="series-key"><span class="swatch" style="background:{color}"></span>'
            f'<span><b>{escape(name)}</b><small>{escape(" · ".join(exact))}</small></span></div>'
        )
    return f'''<div class="line-chart"><svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria_label)}">
{"".join(grid)}{"".join(paths)}{x_axis}</svg><div class="series-legend">{"".join(legends)}</div></div>'''


def page(title, eyebrow, intro, body, *, example=False):
    note = '<div class="sample">Example · Illustrative data and fictional creators</div>' if example else ""
    footer = "Example · Illustrative data and fictional creators" if example else "Creator Outreach Pipeline · Generated from local workspace files"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · Creator Outreach Pipeline</title><style>
:root{{--ink:#18211f;--muted:#66716d;--paper:#f6f3ed;--card:#fffdfa;--line:#ded8ce;--green:#256b52;--sage:#dfeae2;--gold:#a86e19;--rose:#9b4a4a;--blue:#315f77}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}main{{max-width:1180px;margin:auto;padding:48px 28px 72px}}header{{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:26px}}.eyebrow{{color:var(--green);font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}h1{{font:700 clamp(34px,6vw,64px)/1.02 Georgia,serif;max-width:800px;margin:10px 0 14px}}h2{{font:700 27px/1.15 Georgia,serif;margin:0 0 14px}}h3{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px}}p{{max-width:820px}}.intro{{font-size:18px;color:#3e4845}}.sample{{display:inline-block;margin-top:15px;padding:6px 10px;border:1px solid #c9bba4;border-radius:999px;color:#745b37;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;margin:18px 0 28px}}.card{{grid-column:span 4;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 8px 24px #332a1c0a}}.wide{{grid-column:span 12}}.half{{grid-column:span 6}}.metric{{font:700 34px/1 Georgia,serif;margin:7px 0}}.label,.muted{{color:var(--muted)}}.badge{{display:inline-block;border-radius:999px;padding:4px 9px;background:#e9ecea;font-size:12px;white-space:nowrap}}.good{{background:var(--sage);color:#174a38}}.warn{{background:#f4e8cf;color:#765018}}.risk{{background:#f3dddd;color:#7c3333}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}}table{{border-collapse:collapse;width:100%;min-width:720px}}th,td{{padding:12px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#eee9e0;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}tr:last-child td{{border-bottom:0}}.empty{{border:1px dashed #b8b1a6;border-radius:14px;padding:26px;color:var(--muted);background:#fbf9f5}}.path{{font-family:ui-monospace,SFMono-Regular,monospace;background:#ece8df;border-radius:7px;padding:2px 6px}}.bar{{height:8px;background:#ebe5dc;border-radius:99px;overflow:hidden;margin-top:8px}}.bar i{{display:block;height:100%;background:var(--green)}}footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
.chart-layout{{display:grid;grid-template-columns:minmax(210px,.7fr) minmax(260px,1.3fr);gap:24px;align-items:center}}.donut-wrap{{max-width:260px;margin:auto;width:100%}}.donut{{display:block;width:100%;height:auto}}.chart-center-value{{font:700 28px Georgia,serif;fill:var(--ink)}}.chart-center-label{{font-size:11px;fill:var(--muted);text-transform:uppercase;letter-spacing:.08em}}.legend{{display:grid;gap:10px}}.legend-item,.series-key{{display:flex;gap:10px;align-items:flex-start}}.legend-item small,.series-key small,.bar-row small{{display:block;color:var(--muted);margin-top:2px}}.swatch{{width:11px;height:11px;border-radius:3px;flex:0 0 auto;margin-top:5px}}.bar-chart{{display:grid;gap:15px;margin-top:12px}}.bar-heading{{display:flex;justify-content:space-between;gap:16px}}.bar-track{{height:10px;background:#ebe5dc;border-radius:99px;overflow:hidden;margin:6px 0 4px}}.bar-track i{{display:block;height:100%;border-radius:99px}}.line-chart svg{{display:block;width:100%;height:auto;overflow:visible}}.grid-line{{stroke:#ded8ce;stroke-width:1}}.axis-label{{fill:var(--muted);font-size:12px}}.series-legend{{display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:12px}}.chart-note{{color:var(--muted);font-size:13px;margin-top:12px}}.chart-stack{{display:grid;gap:16px}}.chart-panel{{border-top:1px solid var(--line);padding-top:18px}}.chart-panel:first-child{{border-top:0;padding-top:0}}footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
.quarter{{grid-column:span 3}}@media(max-width:900px){{.quarter{{grid-column:span 6}}}}@media(max-width:760px){{main{{padding:30px 16px 50px}}.card,.half,.quarter{{grid-column:span 12}}.chart-layout{{grid-template-columns:1fr}}.donut-wrap{{max-width:220px}}.series-legend{{display:grid}}}}
</style></head><body><main><header><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1><p class="intro">{escape(intro)}</p>{note}</header>{body}<footer>{escape(footer)}</footer></main></body></html>'''


def audience_count(value):
    """Return a public subscriber count when it is numeric; Unknown and blanks stay unknown."""
    raw = str(value or "").strip().replace(",", "")
    if not raw or raw.casefold() in {"unknown", "n/a", "not available"}:
        return None
    try:
        result = float(raw)
    except ValueError:
        return None
    return result if math.isfinite(result) and result >= 0 else None


def creator_database_dashboard(data, source, *, example=False):
    source_label = "02-examples/sample-creator-campaign" if example else "01-workspace"
    creators = list(data["creators"])
    config = load_config()
    verified = sum(row.get("verification_status") == "Verified" for row in creators)
    contactable = sum(
        bool(row.get("public_business_email", "").strip() or row.get("dm_url", "").strip() or row.get("contact_page_url", "").strip())
        and row.get("do_not_contact", "").strip().lower() != "true"
        for row in creators
    )
    needs_completion = sum(
        row.get("verification_status") != "Verified" or not row.get("score", "").strip() or bool(row.get("missing_evidence", "").strip())
        for row in creators
    )
    kpis = "".join([
        f'<section class="card quarter"><div class="label">Creators</div><div class="metric">{len(creators)}</div><div class="muted">Saved channel records</div></section>',
        f'<section class="card quarter"><div class="label">Verified</div><div class="metric">{verified}</div><div class="muted">Evidence-ready records</div></section>',
        f'<section class="card quarter"><div class="label">Contactable</div><div class="metric">{contactable}</div><div class="muted">Public route recorded</div></section>',
        f'<section class="card quarter"><div class="label">Needs completion</div><div class="metric">{needs_completion}</div><div class="muted">Safe to continue later</div></section>',
    ])

    tier_counts = Counter(row.get("tier", "") for row in creators)
    tier_items = [
        (f"Tier {tier}", tier_counts[tier], CHART_COLORS[index])
        for index, tier in enumerate("ABCD") if tier_counts[tier]
    ]
    tier_chart = donut_chart(
        tier_items,
        aria_label="A B C D creator score tier distribution",
        center_value=sum(tier_counts[tier] for tier in "ABCD"),
        center_label="Scored creators",
    )
    unscored = sum(row.get("tier") in {"", "Unscored"} for row in creators)

    subscriber_bands = Counter()
    for row in creators:
        count = audience_count(row.get("follower_count", ""))
        if count is None:
            subscriber_bands["Unknown"] += 1
        elif count < 10_000:
            subscriber_bands["Under 10K"] += 1
        elif count < 50_000:
            subscriber_bands["10K–49K"] += 1
        elif count < 100_000:
            subscriber_bands["50K–99K"] += 1
        elif count < 500_000:
            subscriber_bands["100K–499K"] += 1
        else:
            subscriber_bands["500K+"] += 1
    band_order = ("Under 10K", "10K–49K", "50K–99K", "100K–499K", "500K+", "Unknown")
    band_items = [
        (label, subscriber_bands[label], f"{subscriber_bands[label]} creator records", CHART_COLORS[index % len(CHART_COLORS)])
        for index, label in enumerate(band_order)
    ]
    subscriber_chart = horizontal_bars(
        band_items,
        aria_label="Creator subscriber count band distribution",
        empty_message="No creator records yet, so no subscriber distribution is shown.",
    )

    priorities = {item["tier"]: item["priority"] for item in config["tiers"]}
    ordered = sorted(creators, key=lambda row: (int(row["rank"]) if row.get("rank") else 9999, row["creator_id"]))
    ranking_rows = []
    recommendations = []
    for row in ordered:
        contact = row.get("public_business_email") or row.get("dm_url") or row.get("contact_page_url")
        score = f"{fmt(row.get('score', ''), '—')} / {fmt(row.get('tier', 'Unscored'))}"
        priority = priorities.get(row.get("tier", ""), "Research")
        status = row.get("verification_status") or "Pending Verification"
        tone = "good" if status == "Verified" else "warn"
        missing = row.get("missing_evidence", "").strip() or "No recorded evidence gaps"
        subscriber = audience_count(row.get("follower_count", ""))
        subscriber_label = f"{subscriber:,.0f}" if subscriber is not None else "Unknown"
        average_views = audience_count(row.get("average_views", ""))
        signal_lines = [
            f"Avg views: {average_views:,.0f}" if average_views is not None else "Avg views: Unknown",
            f"Frequency: {fmt(row.get('upload_frequency', ''), 'Unknown')}",
            f"Engagement: {fmt(row.get('engagement_indicators', ''), 'Unknown')}",
        ]
        evidence = (
            f"{fmt(row.get('evidence_url', ''), 'Not recorded')}<br>"
            f"<span class='muted'>Checked: {fmt(row.get('checked_at', ''), 'Not recorded')}</span>"
        )
        ranking_rows.append([
            f"<b>{fmt(row.get('name', ''), 'Unknown channel')}</b><br><span class='muted'>{fmt(row.get('profile_url', ''))}</span>",
            subscriber_label,
            f"{fmt(row.get('language', ''), 'Unknown')}<br><span class='muted'>{fmt(row.get('country_region', ''), 'Unknown')}</span>",
            fmt(row.get("content_category", ""), "Unknown"),
            "<br>".join(signal_lines), badge(status, tone), evidence, score, f"{fmt(row.get('rank', ''), '—')} / {escape(priority)}",
            fmt(contact, "Not recorded"), fmt(missing),
        ])
        if len(recommendations) < 6:
            if status != "Verified" or not row.get("score"):
                verification_gap = missing if missing != "No recorded evidence gaps" else f"verification status is {status}"
                recommendations.append(f"{row.get('name') or row['creator_id']}: continue verification — {verification_gap}.")
            elif row.get("tier") in {"A", "B"} and contact:
                recommendations.append(f"{row.get('name') or row['creator_id']}: review the evidence and consider personalised outreach.")
            elif not contact:
                recommendations.append(f"{row.get('name') or row['creator_id']}: look for a public business contact route before outreach.")

    completeness_specs = [
        ("Subscriber count", lambda row: audience_count(row.get("follower_count", "")) is not None),
        ("Language and country", lambda row: bool(row.get("language", "").strip() and row.get("country_region", "").strip())),
        ("Content category", lambda row: bool(row.get("content_category", "").strip())),
        ("Average views", lambda row: audience_count(row.get("average_views", "")) is not None),
        ("Upload frequency", lambda row: bool(row.get("upload_frequency", "").strip())),
        ("Engagement indicators", lambda row: bool(row.get("engagement_indicators", "").strip())),
        ("Recent relevant video", lambda row: bool(row.get("representative_content_url", "").strip())),
        ("Public business email", lambda row: bool(row.get("public_business_email", "").strip())),
        ("Other contact method", lambda row: bool(row.get("dm_url", "").strip() or row.get("contact_page_url", "").strip())),
        ("Fit and product relevance", lambda row: bool(row.get("fit_rationale", "").strip() and row.get("potential_collaboration", "").strip())),
        ("Evidence-backed score", lambda row: bool(row.get("score", "").strip())),
    ]
    completeness_rows = []
    for label, predicate in completeness_specs:
        complete = sum(bool(predicate(row)) for row in creators)
        missing = len(creators) - complete
        rate = complete / len(creators) * 100 if creators else 0
        completeness_rows.append([escape(label), str(complete), str(missing), f"{rate:.0f}%"])
    completeness_content = table(
        ['Field group', 'Complete', 'Missing', 'Coverage'], completeness_rows, 'No creator records yet.'
    ) if creators else '<div class="empty">No creator records yet. Completeness appears after the first saved batch.</div>'
    recommendation_list = "".join(f"<li>{escape(item)}</li>" for item in recommendations)
    if not recommendation_list:
        recommendation_list = "<li>Add channel URLs or import a creator list to begin. Partial records can be saved and completed in later batches.</li>"

    body = f'''<div class="grid">{kpis}</div>
<section class="grid"><div class="card half"><h2>Score tiers</h2><p class="muted">Only evidence-supported six-dimension scores appear in A–D.</p>{tier_chart}<p class="chart-note">Unscored creators: {unscored}. Missing rating evidence is never treated as zero.</p></div><div class="card half"><h2>Subscriber bands</h2><p class="muted">Public subscriber counts grouped for quick database coverage review.</p>{subscriber_chart}</div></section>
<section class="grid"><div class="card wide"><h2>Creator ranking</h2>{table(['Channel','Subscribers','Language / country','Category','Public signals','Verification','Source / checked','Score / tier','Rank / priority','Public contact','Missing or unresolved'], ranking_rows, 'No creators yet. Provide a product brief, a YouTube channel URL, a list or a CSV; the Agent can save the first usable batch immediately.')}</div></section>
<section class="grid"><div class="card half"><h2>Data completeness</h2>{completeness_content}</div><div class="card half"><h2>Recommended next actions</h2><ul>{recommendation_list}</ul><p class="chart-note">Discovery may continue in batches. Rebuild this page after each saved batch to update the counts and priorities.</p></div></section>
<p class="muted">Source of truth: <span class="path">{source_label}/creators.csv</span>. Public information can be incomplete; blank or Unknown means not yet available, while 0 means a verified zero.</p>'''
    return page("Creator database", "Discover, verify, continue", "A durable YouTube creator database that can start with channel links, save partial progress and become more complete over time.", body, example=example)


def outreach_dashboard(data, source, *, example=False):
    source_label = "02-examples/sample-creator-campaign" if example else "01-workspace"
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
    stage_counts = Counter()
    for creator_id in creators:
        state = outreach.get(creator_id, {}).get("current_status", "").strip()
        if state in {"Sent"}:
            stage_counts["Contacted"] += 1
        elif state == "Replied":
            stage_counts["Replied"] += 1
        elif state == "Negotiating":
            stage_counts["Negotiating"] += 1
        elif state in {"Confirmed", "Published", "Completed"}:
            stage_counts["Won"] += 1
        elif state in {"Opted out", "Closed Lost"}:
            stage_counts["Closed"] += 1
        else:
            stage_counts["Pending"] += 1
    stage_order = ("Pending", "Contacted", "Replied", "Negotiating", "Won", "Closed")
    stage_items = [
        (label, stage_counts[label], CHART_COLORS[index])
        for index, label in enumerate(stage_order)
        if stage_counts[label]
    ]
    stage_chart = donut_chart(
        stage_items,
        aria_label="Creator outreach status distribution",
        center_value=len(creators),
        center_label="Creators",
    )
    tier_counts = Counter(row.get("tier", "") for row in creators.values())
    tier_colors = {"A": "#256b52", "B": "#315f77", "C": "#a86e19", "D": "#9b4a4a"}
    tier_items = [
        (f"Tier {tier}", tier_counts[tier], f"{tier_counts[tier]} scored creators", tier_colors[tier])
        for tier in "ABCD"
    ]
    tier_chart = horizontal_bars(
        tier_items,
        aria_label="A B C D creator tier distribution",
        empty_message="No evidence-ready creators have a score yet, so no tier distribution is shown.",
    )
    unscored_count = sum(1 for row in creators.values() if row.get("tier") in {"", "Unscored"})
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
    body = f'''<div class="grid">{metrics}</div><section class="grid"><div class="card half"><h2>Outreach status</h2><p class="muted">Each creator appears once at their current furthest recorded stage.</p>{stage_chart}</div><div class="card half"><h2>Score tiers</h2><p class="muted">Evidence-ready creators grouped by the configured A–D thresholds.</p>{tier_chart}<p class="chart-note">Unscored creators: {unscored_count}. They are excluded from the A–D bars until the required evidence is complete.</p></div></section>
<section class="grid"><div class="card wide"><h2>Candidate priority and current state</h2>{table(['ID','Creator','Score / tier','Evidence','Current state','Next action or gap'], candidate_rows, 'No creators yet. Provide a product brief, channel links or a creator file, then save the first discovery batch.')}</div></section>
<section class="grid"><div class="card wide"><h2>Latest recorded activity</h2>{table(['When','Creator','Event','What happened','Source'], event_rows, 'No actual contact events recorded. Drafts do not create activity.')}</div></section>
<section class="grid"><div class="card wide"><h2>Offer versions</h2>{table(['Offer','Creator','Scope','Amount','Payment terms','Status'], offer_rows, 'No offers recorded. Keep each scope and payment option as a separate row.')}</div></section>
<p class="muted">Source files: <span class="path">{source_label}/creators.csv</span> and <span class="path">{source_label}/outreach-progress.csv</span>. The consolidated progress table keeps outreach state, activity history, offers and partnerships as separate record types. A draft or score never means a message was sent.</p>'''
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
    source_label = "02-examples/sample-creator-campaign" if example else "01-workspace"
    creators = {row["creator_id"]: row for row in data["creators"]}
    partnerships = {(row["collaboration_id"], row["deliverable_id"]): row for row in data["partnerships"] if row["status"] in {"Published", "Completed"}}
    grouped = defaultdict(dict)
    for row in data["performance"]:
        grouped[(row["collaboration_id"], row["deliverable_id"])][row["window"]] = row
    published_cards = []
    rows = []
    insights = []
    comparison_groups = defaultdict(list)
    latest_records = []
    trend_panels = []
    for key, partnership in partnerships.items():
        creator = creators[partnership["creator_id"]]
        windows = grouped.get(key, {})
        latest = windows.get("D30") or windows.get("D14") or windows.get("D7")
        if not latest:
            continue
        tracking_verified = partnership.get("tracking_verified", "").lower() == "true"
        latest_records.append((creator, partnership, latest, tracking_verified))
        latest_cpd = cost_value(latest, "downloads", tracking_verified=tracking_verified)
        latest_cpi = cost_value(latest, "installs", tracking_verified=tracking_verified)
        spend_label = spend_value(latest)
        published_cards.append(f'''<section class="card half"><h2>{fmt(creator['name'])}</h2><p>{badge(partnership['status'], 'good')} · {fmt(partnership['content_type'])}</p><p><b>D0:</b> {fmt(partnership['published_at'])}<br><b>Latest window:</b> {fmt(latest['window'])}<br><b>Attribution:</b> {fmt(latest['attribution_source'])}<br><b>Spend:</b> {spend_label}<br><b>Cost / download:</b> {latest_cpd}<br><b>Cost / install:</b> {latest_cpi}</p><p class="muted">{fmt(latest['notes'])}</p></section>''')
        labels = [window for window in ("D7", "D14", "D30") if window in windows]
        if labels:
            trend_series = []
            for metric, label, color in (
                ("downloads", "Downloads", CHART_COLORS[0]),
                ("installs", "Installs", CHART_COLORS[1]),
                ("activated_users", "Activated users", CHART_COLORS[2]),
            ):
                values = [number(windows[window].get(metric, ""), metric, allow_blank=True) for window in labels]
                trend_series.append((label, values, color))
            chart = line_chart(labels, trend_series, aria_label=f"{creator['name']} cumulative performance by measurement window")
            trend_panels.append(
                f'<div class="chart-panel"><h3>{fmt(creator["name"])} · {fmt(partnership["deliverable_id"])}</h3>{chart}</div>'
            )
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
    comparison_panels = []
    ordered_groups = sorted(comparison_groups.items(), key=lambda item: (WINDOW_ORDER[item[0][0]], item[0][1:]))
    for (window, attribution, definition, currency), items in ordered_groups:
        if len({partnership["deliverable_id"] for _, partnership, _, _, _ in items}) < 2:
            continue
        chart_items = []
        for creator, partnership, record, cpd, cpi in items:
            comparison_rows.append([
                badge(window, "good"), fmt(creator["name"]), fmt(partnership["deliverable_id"]),
                fmt(record["downloads"], "—"), fmt(record["installs"], "—"), cpd, cpi,
                fmt(attribution), fmt(definition),
            ])
            downloads = number(record.get("downloads", ""), "downloads", allow_blank=True)
            installs = number(record.get("installs", ""), "installs", allow_blank=True)
            conversion = installs / downloads * 100 if downloads not in {None, 0} and installs is not None else 0
            if downloads in {None, 0} or installs is None:
                detail = f"Conversion unavailable · CPD {cpd} · CPI {cpi}"
            else:
                detail = f"CPD {cpd} · CPI {cpi} · {installs:,.0f} installs from {downloads:,.0f} downloads"
            chart_items.append((creator["name"], conversion, detail, CHART_COLORS[len(chart_items) % len(CHART_COLORS)]))
        chart = horizontal_bars(
            chart_items,
            aria_label=f"{window} creator download to install conversion comparison",
            empty_message="Conversion cannot be compared because recorded downloads are missing or zero.",
            suffix="%",
            scale_max=100,
        )
        comparison_panels.append(
            f'<div class="chart-panel"><h3>{escape(window)} · {escape(currency)}</h3>{chart}'
            f'<p class="chart-note">Like-for-like only: {escape(attribution)} · {escape(definition)}. Longer bars mean a higher download-to-install conversion; use the exact CPD and CPI labels to compare cost efficiency.</p></div>'
        )

    spend_values = []
    currencies = set()
    download_values = []
    install_values = []
    total_scopes = set()
    totals_are_comparable = bool(latest_records)
    for _, _, record, tracking_verified in latest_records:
        spend = number(record.get("spend", ""), "spend", allow_blank=True)
        downloads = number(record.get("downloads", ""), "downloads", allow_blank=True)
        installs = number(record.get("installs", ""), "installs", allow_blank=True)
        currency = record.get("currency", "").strip()
        if spend is None or not currency:
            totals_are_comparable = False
        else:
            spend_values.append(spend)
            currencies.add(currency)
        if downloads is None or installs is None:
            totals_are_comparable = False
        else:
            download_values.append(downloads)
            install_values.append(installs)
        if not tracking_verified or record.get("verification_status") not in {"Verified", "Illustrative"}:
            totals_are_comparable = False
        scope = (
            record.get("window", "").strip(), record.get("attribution_source", "").strip(),
            record.get("metric_definition", "").strip(), currency,
        )
        if not all(scope):
            totals_are_comparable = False
        else:
            total_scopes.add(scope)
    if len(total_scopes) != 1:
        totals_are_comparable = False
    one_currency = len(currencies) == 1 and len(spend_values) == len(latest_records)
    total_spend_label = f"{next(iter(currencies))} {sum(spend_values):,.0f}" if one_currency else "N/A"
    total_downloads_label = f"{sum(download_values):,.0f}" if len(download_values) == len(latest_records) and latest_records else "N/A"
    total_installs_label = f"{sum(install_values):,.0f}" if len(install_values) == len(latest_records) and latest_records else "N/A"
    total_conversion = ratio(sum(install_values), sum(download_values)) if totals_are_comparable else "N/A"
    kpis = "".join([
        f'<section class="card quarter"><div class="label">Total recorded spend</div><div class="metric">{escape(total_spend_label)}</div><div class="muted">Latest snapshot per deliverable</div></section>',
        f'<section class="card quarter"><div class="label">Total downloads</div><div class="metric">{escape(total_downloads_label)}</div><div class="muted">Latest snapshot per deliverable</div></section>',
        f'<section class="card quarter"><div class="label">Total installs</div><div class="metric">{escape(total_installs_label)}</div><div class="muted">Latest snapshot per deliverable</div></section>',
        f'<section class="card quarter"><div class="label">Download → install</div><div class="metric">{escape(total_conversion)}</div><div class="muted">Verified like-for-like totals only</div></section>',
    ])
    content = "".join(published_cards) or '<div class="card wide empty">No published deliverable has a performance record yet. Confirming a collaboration is not publication, and missing metrics are not zero.</div>'
    trend_content = "".join(trend_panels) or '<div class="empty">No eligible D7, D14 or D30 measurements yet, so no trend chart is shown.</div>'
    comparison_content = "".join(comparison_panels) or '<div class="empty">Insufficient data for a like-for-like creator chart. Two or more deliverables must share the same window, attribution source, metric definition and currency.</div>'
    insight_items = "".join(f"<li>{escape(item)}</li>" for item in insights)
    if len(partnerships) < 2:
        insight_items += "<li>Insufficient data for a cross-creator recommendation; only one published deliverable is available.</li>"
    if not insight_items:
        insight_items = "<li>Insufficient data. Add a published deliverable and a verified measurement window.</li>"
    body = f'''<div class="grid">{kpis}</div><section class="grid"><div class="card wide"><h2>Cumulative outcome trends</h2><p class="muted">Each line uses recorded cumulative snapshots for one published deliverable. D7, D14 and D30 are not added together.</p><div class="chart-stack">{trend_content}</div></div></section>
<div class="grid">{content}</div><section class="grid"><div class="card wide"><h2>Creator efficiency comparison</h2><p class="muted">Shown only when two or more deliverables can be compared on the same measurement basis.</p><div class="chart-stack">{comparison_content}</div></div></section>
<section class="grid"><div class="card wide"><h2>Cumulative performance windows</h2>{table(['Creator','Deliverable','Window','Views','Clicks','Downloads','Installs','Activated','Spend','Cost / download','Cost / install','Click → download','Download → install','Install → activate','Evidence'], rows, 'No eligible D7, D14 or D30 measurements. Add evidence only after publication.')}</div></section>
<section class="grid"><div class="card wide"><h2>Comparable results</h2>{table(['Window','Creator','Deliverable','Downloads','Installs','Cost / download','Cost / install','Attribution','Metric definition'], comparison_rows, 'Insufficient data for a like-for-like comparison. Two or more deliverables must share the same window, attribution source, metric definition and currency.')}</div></section>
<section class="grid"><div class="card half"><h2>Insights / Next Actions</h2><ul>{insight_items}</ul></div><div class="card half"><h2>How to read this</h2><p>D7, D14 and D30 are cumulative snapshots from each deliverable’s publication date. Do not add them together. Spend is the cumulative amount recorded for one deliverable and is repeated across windows for context, never summed. Cost metrics are N/A when spend, outcome, attribution scope or tracking verification is missing.</p></div><div class="card wide"><h2>Decision limits</h2><p>Compare formats and creators only when the observation window, attribution source, metric definition and currency match. Small samples and incomplete attribution support hypotheses, not guaranteed growth claims.</p></div></section>
<p class="muted">Source files: <span class="path">{source_label}/outreach-progress.csv</span> and <span class="path">{source_label}/performance.csv</span>. Partnership records live in the consolidated progress table. The stored UTM URL is evidence of link design, not by itself evidence that tracking worked.</p>'''
    return page("Partnership performance", "Published evidence only", "Cumulative post-publication evidence, conversion efficiency and the limits that matter before the next decision.", body, example=example)


def build(source, output, *, example=False):
    source, output = Path(source), Path(output)
    _, data = load_workspace(source, write_scores=True)
    output.mkdir(parents=True, exist_ok=True)
    rendered = {
        "creator-database-dashboard.html": creator_database_dashboard(data, source, example=example),
        "outreach-dashboard.html": outreach_dashboard(data, source, example=example),
        "performance-dashboard.html": performance_dashboard(data, example=example),
    }
    for filename, content in rendered.items():
        (output / filename).write_text(content, encoding="utf-8")
    return rendered

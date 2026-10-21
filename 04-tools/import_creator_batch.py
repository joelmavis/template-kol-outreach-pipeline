#!/usr/bin/env python3
"""Map a local creator CSV/XLSX into creators.csv and preserve its source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from local_table import read_local_table
from pipeline import FILES, ROOT, merge_creator_batch, read_csv, validate_creators, write_csv


ALIASES = {
    "creator_id": ("creator id", "creator_id", "达人id", "达人编号"),
    "name": ("creator", "creator name", "channel name", "name", "达人名称", "频道名称"),
    "handle": ("handle", "channel handle", "频道handle", "频道账号"),
    "profile_url": ("profile_url", "profile url", "youtube channel url", "channel url", "频道链接", "达人链接"),
    "country_region": ("country", "region", "country region", "国家", "地区"),
    "language": ("language", "语言"),
    "content_category": ("content category", "category", "内容垂类", "内容类别"),
    "representative_content_title": ("representative content", "video title", "匹配视频", "代表视频"),
    "representative_content_url": ("video url", "content url", "视频链接", "代表视频链接"),
    "follower_count": ("subscriber count", "subscribers", "followers", "订阅数", "粉丝数"),
    "average_views": ("average views", "avg views", "匹配视频播放", "平均播放量"),
    "upload_frequency": ("upload frequency", "更新频率", "发布频率"),
    "engagement_indicators": ("engagement", "engagement indicators", "互动口径", "互动指标"),
    "metric_summary": ("metric summary", "数据摘要"),
    "public_business_email": ("public business email", "business email", "公开商务邮箱", "商务邮箱"),
    "business_email_source": ("contact source", "email source", "联系方式来源", "邮箱来源"),
    "dm_url": ("dm url", "dm", "私信链接"),
    "contact_page_url": ("contact page", "contact url", "联系页面"),
    "evidence_url": ("source url", "source link", "evidence url", "来源搜索链接", "来源链接"),
    "checked_at": ("last checked date", "checked at", "抓取时间", "核查日期"),
    "verification_status": ("verification status", "核实状态", "验证状态"),
    "missing_evidence": ("missing information", "missing evidence", "待补全", "缺失信息"),
    "do_not_contact": ("do not contact", "do_not_contact", "不联系"),
}


def normalized_header(value):
    return re.sub(r"[\s_\-/]+", " ", str(value or "").strip().casefold())


ALIAS_LOOKUP = {
    normalized_header(alias): field
    for field, aliases in ALIASES.items()
    for alias in aliases
}


def generated_id(row, row_number):
    identity = row.get("profile_url") or row.get("name") or f"row-{row_number}"
    digest = hashlib.sha1(identity.strip().casefold().encode("utf-8")).hexdigest()[:10].upper()
    return f"C-IMP-{digest}"


def normalise_status(value):
    value = str(value or "").strip()
    lookup = {
        "verified": "Verified", "已核实": "Verified", "已验证": "Verified",
        "partial": "Partial", "部分核实": "Partial", "部分验证": "Partial",
        "pending": "Pending Verification", "pending verification": "Pending Verification",
        "待核实": "Pending Verification", "待验证": "Pending Verification", "": "Pending Verification",
    }
    return lookup.get(value.casefold(), "Pending Verification")


def map_rows(headers, source_rows, fields, source_name):
    mapped_headers = {header: ALIAS_LOOKUP.get(normalized_header(header)) for header in headers}
    output = []
    for row_number, source in enumerate(source_rows, 2):
        row = {field: "" for field in fields}
        extra = {}
        for header, value in source.items():
            value = str(value or "").strip()
            if not value:
                continue
            field = mapped_headers.get(header)
            if field and field in row and not row[field]:
                row[field] = value
            else:
                extra[header] = value
        row["creator_id"] = row.get("creator_id") or generated_id(row, row_number)
        row["platform"] = row.get("platform") or "YouTube"
        row["verification_status"] = normalise_status(row.get("verification_status"))
        row["do_not_contact"] = row.get("do_not_contact") or "false"
        row["source_file"] = source_name
        row["source_row"] = str(row_number)
        row["additional_data_json"] = json.dumps(extra, ensure_ascii=False, separators=(",", ":")) if extra else "{}"
        if not row.get("name"):
            row["name"] = row.get("handle") or f"Unnamed creator from row {row_number}"
            existing = row.get("missing_evidence", "")
            row["missing_evidence"] = "; ".join(filter(None, (existing, "Channel name needs confirmation")))
        output.append(row)
    return output


def preserve_source(batch, source):
    imports = source / "imports"
    imports.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(batch.read_bytes()).hexdigest()[:12]
    destination = imports / f"{batch.stem}-{digest}{batch.suffix.lower()}"
    if not destination.exists():
        shutil.copy2(batch, destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Local CSV or XLSX creator table")
    parser.add_argument("--source", type=Path, default=ROOT / "01-workspace")
    parser.add_argument("--dry-run", action="store_true", help="validate mapping without changing the workspace")
    args = parser.parse_args(argv)
    creator_path = args.source / FILES["creators"]
    fields, existing = read_csv(creator_path)
    headers, source_rows = read_local_table(args.batch)
    mapped = map_rows(headers, source_rows, fields, args.batch.name)
    merged = merge_creator_batch(existing, mapped, fields)
    validate_creators(merged)
    verified = sum(row.get("verification_status") == "Verified" for row in merged)
    incomplete = sum(row.get("verification_status") != "Verified" or row.get("missing_evidence", "").strip() for row in merged)
    if not args.dry_run:
        preserve_source(args.batch, args.source)
        write_csv(creator_path, fields, merged)
    mode = "Checked" if args.dry_run else "Saved"
    print(f"{mode} {len(mapped)} source row(s); database has {len(merged)} unique creator(s), {verified} verified, {incomplete} needing completion")


if __name__ == "__main__":
    main()

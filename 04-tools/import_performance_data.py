#!/usr/bin/env python3
"""Map a local CSV/XLSX result table into performance.csv for published work."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil

from local_table import read_local_table
from pipeline import FILES, ROOT, load_workspace, read_csv, write_csv


ALIASES = {
    "creator_id": ("creator id", "creator_id", "达人id"),
    "creator_name": ("creator", "creator name", "channel name", "达人名称", "频道名称"),
    "collaboration_id": ("collaboration id", "合作id", "合作编号"),
    "deliverable_id": ("deliverable id", "内容id", "交付物id"),
    "published_at": ("published at", "publish date", "发布日期", "上线日期"),
    "window": ("window", "measurement window", "统计周期", "窗口"),
    "measured_at": ("measured at", "measurement date", "统计日期", "核查日期"),
    "utm_url": ("utm url", "utm", "跟踪链接"),
    "views": ("views", "播放量"), "clicks": ("clicks", "点击量"),
    "downloads": ("downloads", "下载量"), "installs": ("installs", "安装量"),
    "activated_users": ("activated users", "activations", "激活用户", "激活量"),
    "spend": ("spend", "cost", "费用", "合作成本"), "currency": ("currency", "币种"),
    "attribution_source": ("attribution source", "data source", "归因来源", "数据来源"),
    "metric_definition": ("metric definition", "口径", "指标口径"),
    "verification_status": ("verification status", "核实状态", "验证状态"),
    "notes": ("notes", "备注"),
}


def norm(value):
    return re.sub(r"[\s_\-/]+", " ", str(value or "").strip().casefold())


LOOKUP = {norm(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def preserve_source(batch, source):
    imports = source / "imports"
    imports.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(batch.read_bytes()).hexdigest()[:12]
    destination = imports / f"{batch.stem}-{digest}{batch.suffix.lower()}"
    if not destination.exists():
        shutil.copy2(batch, destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Local CSV or XLSX performance table")
    parser.add_argument("--source", type=Path, default=ROOT / "01-workspace")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    fields, existing = read_csv(args.source / FILES["performance"])
    _, data = load_workspace(args.source)
    creator_by_name = {}
    for row in data["creators"]:
        creator_by_name.setdefault(row["name"].strip().casefold(), []).append(row["creator_id"])
    partnerships = [row for row in data["partnerships"] if row.get("status") in {"Published", "Completed"}]
    headers, source_rows = read_local_table(args.batch)
    header_map = {header: LOOKUP.get(norm(header)) for header in headers}
    mapped = []
    for row_number, source_row in enumerate(source_rows, 2):
        row = {field: "" for field in fields}
        creator_name = ""
        for header, value in source_row.items():
            field = header_map.get(header)
            if field == "creator_name":
                creator_name = value.strip()
            elif field in row and not row[field]:
                row[field] = value.strip()
        if not row["creator_id"] and creator_name:
            matches = creator_by_name.get(creator_name.casefold(), [])
            if len(matches) == 1:
                row["creator_id"] = matches[0]
        candidates = [item for item in partnerships if not row["creator_id"] or item["creator_id"] == row["creator_id"]]
        if row["collaboration_id"]:
            candidates = [item for item in candidates if item["collaboration_id"] == row["collaboration_id"]]
        if row["deliverable_id"]:
            candidates = [item for item in candidates if item["deliverable_id"] == row["deliverable_id"]]
        if len(candidates) != 1:
            raise ValueError(f"row {row_number}: identify exactly one published collaboration using creator name/ID and optional collaboration/deliverable ID")
        partnership = candidates[0]
        row["creator_id"] = partnership["creator_id"]
        row["collaboration_id"] = partnership["collaboration_id"]
        row["deliverable_id"] = partnership["deliverable_id"]
        row["published_at"] = row["published_at"] or partnership["published_at"]
        row["verification_status"] = row["verification_status"] or "User provided"
        row["notes"] = row["notes"] or f"Imported from {args.batch.name} row {row_number}"
        if row["window"].upper() in {"D7", "D14", "D30"}:
            row["window"] = row["window"].upper()
        mapped.append(row)
    by_key = {(row["creator_id"], row["collaboration_id"], row["deliverable_id"], row["window"]): row for row in existing}
    for incoming in mapped:
        key = (incoming["creator_id"], incoming["collaboration_id"], incoming["deliverable_id"], incoming["window"])
        target = by_key.get(key)
        if target is None:
            existing.append(incoming)
            by_key[key] = incoming
        else:
            for field, value in incoming.items():
                if value and not target.get(field, "").strip():
                    target[field] = value
    if not args.dry_run:
        preserve_source(args.batch, args.source)
        write_csv(args.source / FILES["performance"], fields, existing)
        load_workspace(args.source)
    print(f"{'Checked' if args.dry_run else 'Saved'} {len(mapped)} performance row(s); workspace now has {len(existing)} row(s)")


if __name__ == "__main__":
    main()

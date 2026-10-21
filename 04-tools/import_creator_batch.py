#!/usr/bin/env python3
"""Safely merge one creator-discovery CSV batch into an existing workspace."""
import argparse
from pathlib import Path

from pipeline import FILES, ROOT, load_config, merge_creator_batch, read_csv, score_creators, write_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="CSV containing one discovery or enrichment batch")
    parser.add_argument("--source", type=Path, default=ROOT / "01-workspace")
    args = parser.parse_args(argv)
    creator_path = args.source / FILES["creators"]
    fields, existing = read_csv(creator_path)
    batch_fields, batch = read_csv(args.batch)
    unknown_fields = sorted(set(batch_fields) - set(fields))
    if unknown_fields:
        parser.error("Batch contains unsupported fields: " + ", ".join(unknown_fields))
    merged = merge_creator_batch(existing, batch, fields)
    scored = score_creators(merged, load_config())
    write_csv(creator_path, fields, scored)
    print(f"Saved {len(batch)} batch row(s); creator database now has {len(scored)} unique channel(s)")


if __name__ == "__main__":
    main()

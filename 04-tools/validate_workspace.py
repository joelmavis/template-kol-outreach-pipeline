#!/usr/bin/env python3
"""Validate the blank workspace and the complete fictional campaign."""
import argparse
from pathlib import Path
from pipeline import ROOT, load_workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append")
    args = parser.parse_args(argv)
    sources = args.source or [ROOT / "01-workspace", ROOT / "02-examples/sample-creator-campaign"]
    for source in sources:
        _, data = load_workspace(source)
        print(f"OK {source}: {len(data['creators'])} creators, {len(data['events'])} events, {len(data['offers'])} offers, {len(data['performance'])} performance rows")


if __name__ == "__main__":
    main()

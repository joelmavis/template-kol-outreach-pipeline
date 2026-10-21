#!/usr/bin/env python3
"""Build the three static Creator Outreach Pipeline dashboards."""
import argparse
from pathlib import Path
from pipeline import ROOT, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "01-workspace")
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--fixture", action="store_true", help="mark maintainer-only fixture output")
    args = parser.parse_args(argv)
    rendered = build(args.source, args.output, fixture=args.fixture)
    print("Built " + ", ".join(rendered))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate working data without applying public-template release rules."""
import argparse
from pathlib import Path
import subprocess
from pipeline import ROOT, load_workspace


def public_remote_warning(root):
    """Warn about publication risk without making daily validation fail."""
    if not (root / ".git").exists():
        return
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True
    )
    remote = result.stdout.strip()
    if result.returncode == 0 and ("github.com" in remote or "gitlab.com" in remote):
        print(
            "WARNING: This working directory is connected to a hosted Git remote. "
            "Daily validation does not make real business data safe to publish. "
            "Run 04-tools/check_public_release.py only when preparing a clean template release."
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append")
    args = parser.parse_args(argv)
    sources = args.source or [ROOT / "01-workspace", ROOT / "02-examples/sample-creator-campaign"]
    for source in sources:
        _, data = load_workspace(source)
        print(f"OK {source}: {len(data['creators'])} creators, {len(data['events'])} events, {len(data['offers'])} offers, {len(data['performance'])} performance rows")
    if not args.source:
        public_remote_warning(ROOT)


if __name__ == "__main__":
    main()

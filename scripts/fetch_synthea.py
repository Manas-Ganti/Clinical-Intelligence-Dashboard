"""Fetch the Synthea sample patient population into data/synthea/.

Synthea is a synthetic-but-realistic patient generator from MITRE; its published
sample export is the project's real-data source (see OPEN_SOURCE_DATASETS.md).
The data is not vendored into git — it is ~9 MB zipped, ~470k rows — so this
script pulls it on demand and the ingestion layer falls back to the small
hand-authored fixtures in ingestion/sample_data/ when it is absent.

Usage:  python scripts/fetch_synthea.py
"""
from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

# The historical synthea.mitre.org/downloads host fails TLS as of 2026-07;
# the GitHub mirror is the maintained one.
SYNTHEA_URL = (
    "https://raw.githubusercontent.com/synthetichealth/synthea-sample-data/"
    "main/downloads/synthea_sample_data_csv_apr2020.zip"
)

DEST = Path(__file__).parent.parent / "data" / "synthea"

# Files the ingestion layer actually reads; the export ships ~16.
REQUIRED = ("patients.csv", "encounters.csv", "observations.csv", "imaging_studies.csv")


def main() -> int:
    if all((DEST / "csv" / name).exists() for name in REQUIRED):
        print(f"Synthea data already present in {DEST}/csv — nothing to do.")
        return 0

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Synthea sample data ({SYNTHEA_URL.rsplit('/', 1)[-1]})...")
    with urllib.request.urlopen(SYNTHEA_URL) as resp:  # noqa: S310 - pinned https URL
        payload = resp.read()

    print(f"Extracting {len(payload) / 1e6:.1f} MB to {DEST}...")
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extractall(DEST)

    missing = [n for n in REQUIRED if not (DEST / "csv" / n).exists()]
    if missing:
        print(f"ERROR: expected files missing from archive: {missing}", file=sys.stderr)
        return 1

    for name in REQUIRED:
        path = DEST / "csv" / name
        rows = sum(1 for _ in path.open(encoding="utf-8")) - 1  # minus header
        print(f"  {name:<22} {rows:>7,} rows")
    print("Done. Restart the API to seed from Synthea.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

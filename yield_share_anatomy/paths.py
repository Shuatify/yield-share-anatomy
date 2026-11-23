"""Default paths for the pinned, fully checked-in historical research snapshot.

All paths are relative to the repository root; run commands from there.
Fresh downloads and calculations are written under ignored outputs/ and
never overwrite the checked-in inputs or published baseline evidence.
"""
from pathlib import Path

SNAPSHOT_DATE = "2026-11-20"
SNAPSHOT_DIR = Path("data/snapshots") / SNAPSHOT_DATE
RAW_PURPOSE_FILE = Path("data/raw/purpose") / f"ytsl_{SNAPSHOT_DATE}.csv"
CASH_EVENTS = Path("data/events/ytsl_cash_distributions.csv")
NOTIONAL_EVENTS = Path("data/events/ytsl_notional_events.csv")
REFERENCE_DIR = Path("data/reference")
OUTPUT_DIR = Path("outputs")
BASELINE_DIR = Path("research/baselines") / SNAPSHOT_DATE

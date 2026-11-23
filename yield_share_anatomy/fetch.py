#!/usr/bin/env python3
"""Yield Share Anatomy: inspect YTSL, TSLA and USD/CAD historical inputs.

Examples:
  python -m yield_share_anatomy.fetch --out /mnt/data/yield_share_live
  python -m yield_share_anatomy.fetch --fixture-dir tests/fixtures --out /mnt/data/yield_share_demo
  python -m yield_share_anatomy.fetch --purpose-file data/raw/purpose/ytsl_2026-11-20.csv --out outputs/fetch

Fixture data is SYNTHETIC and never suitable for published investment analysis.
This collects and validates source inputs; it does NOT compute ETF total returns.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path

from .paths import OUTPUT_DIR
import sys

import pandas as pd
import requests

PURPOSE_URL = "https://www.purposeinvest.com/api/nav?fundId=YTSL&seriesId=ETF"
BOC_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA"
START = "2022-12-19"


class DataProblem(ValueError):
    """Malformed or incomplete input."""


def parse_purpose(body: str, min_rows: int = 100) -> pd.DataFrame:
    df = pd.read_csv(StringIO(body))
    required = {"date", "nav", "price", "volume"}
    if not required.issubset(df):
        raise DataProblem(f"Purpose missing columns: {sorted(required - set(df))}")
    df = df[["date", "nav", "price", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise DataProblem("Purpose contains invalid dates")
    for col in ("nav", "price", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    if len(df) < min_rows or (df["nav"] > 0).sum() < min_rows:
        raise DataProblem(f"Purpose has insufficient positive NAV observations: {len(df)}")
    return df


def parse_yahoo(payload: dict, min_rows: int = 100) -> pd.DataFrame:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise DataProblem(f"Yahoo error: {chart['error']}")
    result = chart.get("result") or []
    if not result:
        raise DataProblem("Yahoo contains no result")
    r = result[0]
    bars = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((r.get("indicators") or {}).get("adjclose") or [{}])[0]
    times = r.get("timestamp") or []
    n = len(times)
    if not n or len(bars.get("close") or []) != n:
        raise DataProblem("Yahoo timestamp/close length mismatch")
    tz = (r.get("meta") or {}).get("exchangeTimezoneName") or "America/New_York"
    dates = pd.to_datetime(times, unit="s", utc=True).tz_convert(tz).date
    adj_vals = adj.get("adjclose") or [None] * n
    if len(adj_vals) != n:
        raise DataProblem("Yahoo adjusted-close length mismatch")
    vols = bars.get("volume") or [None] * n
    if len(vols) != n:
        raise DataProblem("Yahoo volume length mismatch")
    df = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "close_usd": pd.to_numeric(bars["close"], errors="coerce"),
        "adj_close_usd": pd.to_numeric(adj_vals, errors="coerce"),
        "volume": pd.to_numeric(vols, errors="coerce"),
    }).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    if len(df) < min_rows or (df["close_usd"] > 0).sum() < min_rows:
        raise DataProblem(f"Yahoo has insufficient positive close observations: {len(df)}")
    return df


def parse_boc(payload: dict, min_rows: int = 100) -> pd.DataFrame:
    rows = []
    for obs in payload.get("observations", []):
        v = (obs.get("FXUSDCAD") or {}).get("v")
        if v is not None:
            rows.append({"date": obs.get("d"), "usd_cad": v})
    if not rows:
        raise DataProblem("BoC contains no USD/CAD observations")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["usd_cad"] = pd.to_numeric(df["usd_cad"], errors="coerce")
    if df["date"].isna().any():
        raise DataProblem("BoC contains invalid dates")
    df = df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    if len(df) < min_rows or (df["usd_cad"] > 0).sum() < min_rows:
        raise DataProblem(f"BoC has insufficient positive FX observations: {len(df)}")
    return df


def fetch_live(session: requests.Session, *, purpose_file: Path | None = None,
               cached_purpose_csv: Path | None = None,
               refresh_purpose: bool = False) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict[str, str]]:
    """Fetch independently. A rate-limited source must not block other datasets.

    Downloading manually using Purpose's official Download NAVs button and passing
    --purpose-file is the preferred fallback for 429. No evasion/repeated requests.
    """
    session.headers.update({"User-Agent": "YieldShareAnatomyResearch/0.2 (historical research)"})
    datasets: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    sources: dict[str, str] = {}

    try:
        if purpose_file is not None:
            datasets["ytsl"] = parse_purpose(purpose_file.read_text(encoding="utf-8-sig"))
            sources["ytsl"] = f"user-provided file: {purpose_file}"
        elif cached_purpose_csv is not None and cached_purpose_csv.is_file() and not refresh_purpose:
            datasets["ytsl"] = parse_purpose(cached_purpose_csv.read_text(encoding="utf-8-sig"))
            sources["ytsl"] = f"cached file: {cached_purpose_csv} (use --refresh-purpose to update)"
        else:
            response = session.get(PURPOSE_URL, timeout=25)
            response.raise_for_status()
            datasets["ytsl"] = parse_purpose(response.text)
            sources["ytsl"] = PURPOSE_URL
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code == 429:
            errors["ytsl"] = ("Purpose returned HTTP 429 (rate limited). Download CSV once with "
                               "the site's Download NAVs button, save as ytsl.csv, "
                               "and run --purpose-file ytsl.csv. No automatic rapid retries.")
        else:
            errors["ytsl"] = f"{type(exc).__name__}: {exc}"

    try:
        start_unix = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
        now_unix = int(datetime.now(tz=timezone.utc).timestamp()) + 86400
        response = session.get(YAHOO_URL, params={"period1": start_unix,
                                                  "period2": now_unix,
                                                  "interval": "1d",
                                                  "events": "history"}, timeout=25)
        response.raise_for_status()
        datasets["tsla"] = parse_yahoo(response.json())
        sources["tsla"] = YAHOO_URL
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        errors["tsla"] = f"{type(exc).__name__}: {exc}"

    try:
        response = session.get(BOC_URL, params={"start_date": START}, timeout=25)
        response.raise_for_status()
        datasets["fx"] = parse_boc(response.json())
        sources["fx"] = BOC_URL
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        errors["fx"] = f"{type(exc).__name__}: {exc}"

    return datasets, errors, sources


def load_fixtures(folder: Path) -> dict[str, pd.DataFrame]:
    return {
        "ytsl": parse_purpose((folder / "purpose.csv").read_text(), min_rows=3),
        "tsla": parse_yahoo(json.loads((folder / "yahoo.json").read_text()), min_rows=3),
        "fx": parse_boc(json.loads((folder / "boc.json").read_text()), min_rows=3),
    }


def quality_metrics(datasets: dict[str, pd.DataFrame]) -> dict:
    metrics = {}
    for name, df in datasets.items():
        cols = {"ytsl": ["nav", "price"], "tsla": ["close_usd", "adj_close_usd"], "fx": ["usd_cad"]}[name]
        metrics[name] = {
            "rows": len(df), "start": df.date.min().date().isoformat(), "end": df.date.max().date().isoformat(),
            "duplicate_dates": int(df.date.duplicated().sum()),
            "null_values": {col: int(df[col].isna().sum()) for col in cols},
            "nonpositive_values": {col: int((df[col] <= 0).sum()) for col in cols},
        }
    return metrics


def build_alignment(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Keep YTSL trading days as the base; US/CAD trading calendars differ.
    ytsl, tsla, fx = datasets["ytsl"], datasets["tsla"], datasets["fx"]
    combined = ytsl[["date", "nav", "price"]].merge(
        tsla[["date", "close_usd", "adj_close_usd"]], on="date", how="left", validate="one_to_one")
    fx_lookup = fx[["date", "usd_cad"]].rename(columns={"date": "fx_observation_date"})
    combined = pd.merge_asof(combined.sort_values("date"), fx_lookup.sort_values("fx_observation_date"),
                             left_on="date", right_on="fx_observation_date", direction="backward",
                             tolerance=pd.Timedelta(days=5))
    combined["fx_age_days"] = (combined["date"] - combined["fx_observation_date"]).dt.days
    combined["tsla_cad_reference"] = combined["close_usd"] * combined["usd_cad"]
    return combined


def save(datasets: dict[str, pd.DataFrame], dest: Path, fixture: bool,
         errors: dict[str, str] | None = None,
         sources: dict[str, str] | None = None) -> dict:
    """Save every available dataset even when some providers are unavailable."""
    errors = errors or {}
    dest.mkdir(parents=True, exist_ok=True)
    filenames = {"ytsl": "ytsl_purpose_daily.csv", "tsla": "tsla_yahoo_daily.csv",
                 "fx": "usdcad_boc_daily.csv"}
    for name, df in datasets.items():
        df.to_csv(dest / filenames[name], index=False)

    metrics = quality_metrics(datasets) if datasets else {}
    if set(datasets) == {"ytsl", "tsla", "fx"}:
        aligned = build_alignment(datasets)
        aligned.to_csv(dest / "aligned_daily_preview.csv", index=False)
        metrics["alignment"] = {
            "rows": len(aligned),
            "tsla_missing_on_ytsl_days": int(aligned["close_usd"].isna().sum()),
            "fx_missing": int(aligned["usd_cad"].isna().sum()),
            "fx_carried_forward_days": int((aligned["fx_age_days"] > 0).sum())}
    elif (dest / "aligned_daily_preview.csv").exists():
        # Never leave stale combined data that look like a result of this failed run.
        (dest / "aligned_daily_preview.csv").unlink()

    state = "ok" if len(datasets) == 3 and not errors else ("partial" if datasets else "failed")
    result = {"status": state,
              "data_type": "SYNTHETIC_TEST_FIXTURE" if fixture else "LIVE_SOURCE_DATA",
              "available": sorted(datasets), "missing": sorted(set(filenames) - set(datasets)),
              "errors": errors,
              "sources": sources or {"ytsl": PURPOSE_URL, "tsla": YAHOO_URL, "fx": BOC_URL},
              "quality": metrics,
              "warning": "Not total returns; cash/non-cash distributions not integrated."}
    (dest / "fetch_status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture-dir", type=Path, help="Read synthetic fixtures (not for actual investment analysis)")
    ap.add_argument("--purpose-file", type=Path,
                    help="Use an official Purpose CSV downloaded in browser; skip Purpose HTTP request")
    ap.add_argument("--refresh-purpose", action="store_true",
                    help="Force one Purpose HTTP request even if its previous CSV is cached")
    ap.add_argument("--out", type=Path, default=OUTPUT_DIR / "fetch")
    args = ap.parse_args(argv)
    if args.fixture_dir and (args.purpose_file or args.refresh_purpose):
        ap.error("--fixture-dir cannot be combined with --purpose-file or --refresh-purpose")
    try:
        if args.fixture_dir:
            data = load_fixtures(args.fixture_dir)
            errors: dict[str, str] = {}
            sources = {"ytsl": "SYNTHETIC", "tsla": "SYNTHETIC", "fx": "SYNTHETIC"}
        else:
            data, errors, sources = fetch_live(
                requests.Session(), purpose_file=args.purpose_file,
                cached_purpose_csv=args.out / "ytsl_purpose_daily.csv",
                refresh_purpose=args.refresh_purpose)
        result = save(data, args.out, fixture=bool(args.fixture_dir), errors=errors, sources=sources)
        print(json.dumps(result, indent=2))
        return {"ok": 0, "partial": 2, "failed": 1}[result["status"]]
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        failure = {"status": "failed", "data_type": "SYNTHETIC_TEST_FIXTURE" if args.fixture_dir else "LIVE_SOURCE_DATA",
                   "error_type": type(exc).__name__, "message": str(exc)}
        (args.out / "fetch_status.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

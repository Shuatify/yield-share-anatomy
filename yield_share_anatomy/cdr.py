"""Collect Tesla CDR historical prices; provisional until independently audited.

The CDR traded on Cboe through 2025-02-13 and on TSX from 2025-02-05.
Never overwrite the pinned 2026-11-20 TSLA/YTSL/FX snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

START = date(2022, 12, 21)
END = date(2026, 11, 20)
TSX_START = date(2025, 2, 5)
CBOE_END = date(2025, 2, 13)
TZ = ZoneInfo("America/Toronto")
COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"]


class CDRDataError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_chart(symbol: str, start: date, end: date) -> tuple[dict, str]:
    """Save Yahoo chart JSON unchanged as a primary raw evidence source."""
    period1 = int(datetime.combine(start - timedelta(days=2), datetime.min.time(), timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=2), datetime.min.time(), timezone.utc).timestamp())
    params = {"period1": period1, "period2": period2, "interval": "1d", "events": "div,splits"}
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            response = requests.get(url, params=params,
                headers={"User-Agent": "Mozilla/5.0 (compatible; YieldShareAnatomy/1.0)"},
                timeout=30)
            response.raise_for_status()
            payload = response.json()
            chart = payload.get("chart") or {}
            if chart.get("error") or not chart.get("result"):
                raise CDRDataError(f"Yahoo empty/error response: {chart.get('error')}")
            return payload, response.url
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{host}: {exc}")
            time.sleep(1)
    raise CDRDataError("Yahoo download failed: " + " | ".join(errors))


def parse_chart(raw: dict, symbol: str, start: date = START,
                end: date = END) -> pd.DataFrame:
    chart = raw.get("chart") or {}
    results = chart.get("result") or []
    if len(results) != 1:
        raise CDRDataError(f"{symbol}: expected one result")
    result = results[0]
    if result.get("meta", {}).get("currency") != "CAD":
        raise CDRDataError(f"{symbol}: currency is not CAD")
    quotes = result.get("indicators", {}).get("quote") or []
    if len(quotes) != 1:
        raise CDRDataError(f"{symbol}: missing quote array")
    data = quotes[0]
    adjusted = result.get("indicators", {}).get("adjclose") or []
    adj = adjusted[0].get("adjclose", []) if adjusted else []
    rows = []
    for i, ts in enumerate(result.get("timestamp") or []):
        day = datetime.fromtimestamp(ts, TZ).date()
        if not start <= day <= end:
            continue
        rows.append({
            "date": day.isoformat(),
            "open": data.get("open", [])[i],
            "high": data.get("high", [])[i],
            "low": data.get("low", [])[i],
            "close": data.get("close", [])[i],
            "adj_close": adj[i] if i < len(adj) else None,
            "volume": data.get("volume", [])[i],
            "ticker": symbol,
        })
    frame = pd.DataFrame(rows, columns=COLUMNS)
    if frame["date"].duplicated().any():
        raise CDRDataError(f"{symbol}: duplicate dates")
    # A retired venue may have valid Yahoo metadata but zero historical candles.
    # Preserve source evidence and continue to collect the other venue.
    return frame.sort_values("date").reset_index(drop=True)


def valid_quote(row) -> bool:
    prices = [row.get(k) for k in ("open", "high", "low", "close")]
    if any(pd.isna(x) or not math.isfinite(float(x)) or float(x) <= 0 for x in prices):
        return False
    op, hi, lo, cl = map(float, prices)
    return lo <= min(op, cl) and hi >= max(op, cl) and lo <= hi


def stitch(cboe: pd.DataFrame, tsx: pd.DataFrame,
           overlap_tolerance: float = 0.015) -> tuple[pd.DataFrame, list[dict]]:
    """Use real Cboe sessions through Feb 13 and TSX afterwards."""
    issues = []
    left, right = cboe.set_index("date"), tsx.set_index("date")
    overlap_checked = 0
    for day in sorted(set(left.index) & set(right.index)):
        if TSX_START.isoformat() <= day <= CBOE_END.isoformat():
            a, b = left.loc[day], right.loc[day]
            if not valid_quote(a) or not valid_quote(b):
                issues.append({"code": "invalid_overlap_quote", "date": day})
                continue
            overlap_checked += 1
            gap = abs(float(a["close"]) / float(b["close"]) - 1)
            if gap > overlap_tolerance:
                issues.append({"code": "venue_overlap_disagreement", "date": day,
                               "ne_close": float(a["close"]), "to_close": float(b["close"]),
                               "relative_gap": round(gap, 6)})
    if not overlap_checked:
        issues.append({"code": "no_verified_dual_listing_overlap",
                       "period": "2025-02-05..2025-02-13"})
    legacy = cboe.loc[cboe["date"] <= CBOE_END.isoformat()]
    if legacy.empty:
        # Yahoo TSLA.TO returns prices before the TSX listing began.
        # Treat them as *unverified historical vendor backfill*, not TSX trades.
        legacy = tsx.loc[tsx["date"] <= CBOE_END.isoformat()]
        issues.append({
            "code": "historical_vendor_backfill_requires_exchange_validation",
            "ticker": "TSLA.TO", "expected_venue": "Cboe Canada",
            "rows": int(len(legacy)),
            "first": legacy.iloc[0]["date"] if len(legacy) else None,
            "last": legacy.iloc[-1]["date"] if len(legacy) else None
        })
    rows = pd.concat([
        legacy, tsx.loc[tsx["date"] > CBOE_END.isoformat()]
    ], ignore_index=True).sort_values("date").reset_index(drop=True)
    if rows.empty or rows["date"].duplicated().any():
        raise CDRDataError("Empty or duplicated stitched series")
    for _, row in rows.iterrows():
        if not valid_quote(row):
            issues.append({"code": "invalid_ohlc", "date": row["date"], "ticker": row["ticker"]})
        if pd.isna(row["volume"]) or float(row["volume"]) <= 0:
            issues.append({"code": "zero_or_missing_volume", "date": row["date"],
                           "ticker": row["ticker"]})
    daily = pd.to_numeric(rows["close"], errors="coerce").pct_change(fill_method=None)
    for index in daily.index[daily.abs() > 0.40]:
        issues.append({"code": "extreme_close_move", "date": rows.loc[index, "date"],
                       "return": round(float(daily.loc[index]), 6)})
    if rows["date"].iloc[0] > START.isoformat() or rows["date"].iloc[-1] < END.isoformat():
        issues.append({"code": "missing_required_endpoint",
                       "first": rows["date"].iloc[0], "last": rows["date"].iloc[-1]})
    return rows, issues


def audit_external(stitched: pd.DataFrame, source: pd.DataFrame,
                   label: str, tolerance: float = 0.025) -> dict:
    """Cross-check issuer/venue date,close_cad observations; do not overwrite Yahoo."""
    if not {"date", "close_cad"}.issubset(source.columns):
        raise CDRDataError(f"{label}: need date,close_cad")
    shared = stitched[["date", "close"]].merge(
        source[["date", "close_cad"]], on="date", how="inner")
    if shared.empty:
        return {"source": label, "matches": 0, "outliers": [],
                "warning": "no shared dates"}
    for col in ("close", "close_cad"):
        shared[col] = pd.to_numeric(shared[col], errors="raise")
    gaps = (shared["close"] / shared["close_cad"] - 1).abs()
    outliers = [
        {"date": row["date"], "yahoo_close": float(row["close"]),
         "external_close": float(row["close_cad"]),
         "relative_gap": round(float(gap), 6)}
        for (_, row), gap in zip(shared.iterrows(), gaps)
        if pd.isna(gap) or gap > tolerance
    ]
    return {"source": label, "matches": int(len(shared)), "outliers": outliers}


def run(out: Path, start: date = START, end: date = END,
        ne_json: Path | None = None, to_json: Path | None = None,
        exchange_csv: Path | None = None, cibc_csv: Path | None = None,
        calendar_csv: Path | None = None,
        secondary_csv: Path | None = None) -> dict:
    if start >= end or start > CBOE_END or end <= TSX_START:
        raise CDRDataError("Date range must span Cboe and TSX venue periods")
    out.mkdir(parents=True, exist_ok=True)
    sources = {}
    frames = {}
    for symbol, file in (("TSLA.NE", ne_json), ("TSLA.TO", to_json)):
        if file:
            payload = json.loads(file.read_text(encoding="utf-8"))
            url = "local saved Yahoo chart JSON"
        else:
            payload, url = fetch_chart(symbol, start, end)
        path = out / f"yahoo_{symbol.replace('.', '_')}_raw.json"
        path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        frame = parse_chart(payload, symbol, start, end)
        frame.to_csv(out / f"yahoo_{symbol.replace('.', '_')}_candidate.csv", index=False)
        frames[symbol] = frame
        sources[symbol] = {
            "request_url": url, "raw_sha256": sha256(path),
            "rows": len(frame),
            "first": frame.iloc[0]["date"] if len(frame) else None,
            "last": frame.iloc[-1]["date"] if len(frame) else None,
            "event_types": sorted((payload["chart"]["result"][0].get("events") or {}).keys())
        }
    merged, issues = stitch(frames["TSLA.NE"], frames["TSLA.TO"])
    for symbol, frame in frames.items():
        if frame.empty:
            issues.append({"code": "no_yahoo_history_for_symbol", "ticker": symbol})
    merged = merged.loc[merged["date"].between(start.isoformat(), end.isoformat())]
    merged.to_csv(out / "tsla_cdr_preliminary_daily.csv", index=False)
    close = pd.to_numeric(merged["close"], errors="coerce")
    adj = pd.to_numeric(merged["adj_close"], errors="coerce")
    adjusted_different = int(((close - adj).abs() > 0.000001).sum())
    if adjusted_different:
        issues.append({"code": "adjusted_vs_unadjusted_close_difference",
                       "rows": adjusted_different})

    external = []
    for label, path in (("exchange", exchange_csv), ("cibc", cibc_csv),
                        ("secondary", secondary_csv)):
        if path:
            external.append(audit_external(
                merged, pd.read_csv(path, dtype={"date": "string"}), label))
        else:
            external.append({"source": label, "matches": 0,
                             "note": "no independent file supplied"})
    if calendar_csv:
        calendar = pd.read_csv(calendar_csv)
        if "date" not in calendar:
            raise CDRDataError("Reference calendar missing date")
        expected = set(calendar["date"].astype(str).loc[
            lambda s: s.between(start.isoformat(), end.isoformat())])
        missing = sorted(expected - set(merged["date"]))
    else:
        missing = []
    for ext in external:
        for item in ext.get("outliers", []):
            issues.append({"code": ext["source"] + "_close_disagreement", **item})
    report = {
        "status": "needs_review", "start": str(start), "end": str(end),
        "primary": "Yahoo NE Cboe where available; otherwise pre-TSX-listing Yahoo TO vendor backfill; Yahoo TO from 2025-02-14",
        "rows": len(merged), "first": merged.iloc[0]["date"],
        "last": merged.iloc[-1]["date"], "sources": sources,
        "reference_calendar_missing_dates": missing,
        "crosschecks": external, "issues": issues,
        "limitations": [
            "No verified CIBC daily historical OHLCV file",
            "No fabricated prices or gap interpolation",
            "Provisional quotes, not yet total return data",
            "All corporate actions require independent review"
        ]
    }
    (out / "quality_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("outputs/cdr_collection"))
    p.add_argument("--ne-json", type=Path)
    p.add_argument("--to-json", type=Path)
    p.add_argument("--exchange-csv", type=Path)
    p.add_argument("--cibc-csv", type=Path)
    p.add_argument("--calendar-csv", type=Path)
    p.add_argument("--secondary-csv", type=Path)
    a = p.parse_args()
    report = run(a.out, ne_json=a.ne_json, to_json=a.to_json,
                 exchange_csv=a.exchange_csv, cibc_csv=a.cibc_csv,
                 calendar_csv=a.calendar_csv, secondary_csv=a.secondary_csv)
    print(json.dumps({
        "status": report["status"], "rows": report["rows"],
        "issues": len(report["issues"]),
        "reference_missing": len(report["reference_calendar_missing_dates"]),
        "output": str(a.out)
    }, indent=2))


if __name__ == "__main__":
    main()

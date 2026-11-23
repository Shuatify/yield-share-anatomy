#!/usr/bin/env python3
"""Phase 1 robustness check using the already-produced monthly_regimes.csv.

Offline only; never downloads data. Report is provisional until issuer cash
entitlements and pricing assumptions are independently verified.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

REQUIRED = {
    "month", "tsla_monthly_pct", "ytsl_nav_drip_monthly_pct",
    "ytsl_market_drip_monthly_pct", "gap_pp"
}
THRESHOLDS = (3.0, 5.0, 8.0, 10.0)


def load_months(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")
        rows = []
        seen = set()
        for index, raw in enumerate(reader, start=2):
            month = raw["month"].strip()
            if not month or month in seen:
                raise ValueError(f"Missing/duplicate month on CSV line {index}: {month!r}")
            seen.add(month)
            row = {"month": month}
            for key in ("tsla_monthly_pct", "ytsl_nav_drip_monthly_pct", "ytsl_market_drip_monthly_pct", "gap_pp"):
                try:
                    val = float(raw[key])
                except (TypeError, ValueError) as e:
                    raise ValueError(f"Invalid {key} on line {index}") from e
                if not math.isfinite(val):
                    raise ValueError(f"Non-finite {key} on line {index}")
                row[key] = val
            if not math.isclose(row["ytsl_nav_drip_monthly_pct"] - row["tsla_monthly_pct"], row["gap_pp"], abs_tol=1e-7):
                raise ValueError(f"Gap inconsistent for {month}")
            row["market_gap_pp"] = row["ytsl_market_drip_monthly_pct"] - row["tsla_monthly_pct"]
            rows.append(row)
    if not rows:
        raise ValueError("No monthly observations")
    return rows


def get_regime(tsla_pct: float, threshold_pct: float) -> str:
    if tsla_pct > threshold_pct:
        return "Up"
    if tsla_pct < -threshold_pct:
        return "Down"
    return "Sideways"


def describe_group(rows: list[dict], threshold_pct: float, name: str) -> dict:
    selected = [r for r in rows if get_regime(r["tsla_monthly_pct"], threshold_pct) == name]
    if not selected:
        return {"regime": name, "months": 0, "nav_gap_mean_pp": None, "nav_gap_median_pp": None,
                "nav_win_rate_pct": None, "market_gap_mean_pp": None, "market_win_rate_pct": None,
                "leave_one_out_nav_mean_range_pp": None}
    nav_gaps = [r["gap_pp"] for r in selected]
    market_gaps = [r["market_gap_pp"] for r in selected]
    leave_one_out = None
    if len(nav_gaps) >= 2:
        submeans = [(sum(nav_gaps) - x) / (len(nav_gaps) - 1) for x in nav_gaps]
        leave_one_out = [round(min(submeans), 4), round(max(submeans), 4)]
    return {"regime": name, "months": len(selected),
            "nav_gap_mean_pp": round(statistics.mean(nav_gaps), 4),
            "nav_gap_median_pp": round(statistics.median(nav_gaps), 4),
            "nav_win_rate_pct": round(100 * sum(g > 0 for g in nav_gaps) / len(nav_gaps), 2),
            "market_gap_mean_pp": round(statistics.mean(market_gaps), 4),
            "market_win_rate_pct": round(100 * sum(g > 0 for g in market_gaps) / len(market_gaps), 2),
            "leave_one_out_nav_mean_range_pp": leave_one_out}


def analyze(rows: list[dict], thresholds: tuple[float, ...] = THRESHOLDS) -> dict:
    all_gaps = [r["gap_pp"] for r in rows]
    sensitivity = [{"threshold_pct": t, "regimes": [describe_group(rows, t, name) for name in ("Up", "Sideways", "Down")]} for t in thresholds]
    rank = sorted(rows, key=lambda r: r["gap_pp"])
    return {
        "status": "ok",
        "research_status": "PROVISIONAL: distribution source audit not complete; historical association is not causal attribution",
        "month_count": len(rows), "first_month": min(r["month"] for r in rows), "last_month": max(r["month"] for r in rows),
        "overall_monthly_nav_win_count": sum(g > 0 for g in all_gaps),
        "overall_monthly_nav_win_rate_pct": round(100 * sum(g > 0 for g in all_gaps) / len(all_gaps), 2),
        "overall_mean_monthly_gap_pp": round(statistics.mean(all_gaps), 4),
        "overall_median_monthly_gap_pp": round(statistics.median(all_gaps), 4),
        "threshold_sensitivity": sensitivity,
        "largest_ytsl_underperformances": [{"month": r["month"], "gap_pp": round(r["gap_pp"], 4), "tsla_pct": round(r["tsla_monthly_pct"], 4)} for r in rank[:5]],
        "largest_ytsl_outperformances": [{"month": r["month"], "gap_pp": round(r["gap_pp"], 4), "tsla_pct": round(r["tsla_monthly_pct"], 4)} for r in reversed(rank[-5:])],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monthly", type=Path, default=Path("yield_share_phase1_results/monthly_regimes.csv"))
    parser.add_argument("--out", type=Path, default=Path("yield_share_phase1_robustness"))
    args = parser.parse_args()
    try:
        result = analyze(load_months(args.monthly))
    except (OSError, ValueError) as e:
        parser.exit(1, f"Robustness analysis failed: {e}\n")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "robustness_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (args.out / "regime_sensitivity.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["threshold_pct", "regime", "months", "nav_gap_mean_pp", "nav_gap_median_pp", "nav_win_rate_pct", "market_gap_mean_pp", "market_win_rate_pct", "leave_one_out_nav_mean_range_pp"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for scenario in result["threshold_sensitivity"]:
            for group in scenario["regimes"]:
                row = dict(group)
                row["threshold_pct"] = scenario["threshold_pct"]
                if row["leave_one_out_nav_mean_range_pp"] is not None:
                    row["leave_one_out_nav_mean_range_pp"] = json.dumps(row["leave_one_out_nav_mean_range_pp"])
                w.writerow(row)
    print(f"Analyzed {result['month_count']} months ({result['first_month']} to {result['last_month']})")
    print(f"YTSL NAV wins: {result['overall_monthly_nav_win_count']}/{result['month_count']} months")
    for scenario in result["threshold_sensitivity"]:
        print(f"Threshold ±{scenario['threshold_pct']:g}%:")
        for group in scenario["regimes"]:
            if group["months"]:
                print(f"  {group['regime']:8} n={group['months']:2}  NAV gap={group['nav_gap_mean_pp']:+.2f} pp/month  win={group['nav_win_rate_pct']:5.1f}%  market gap={group['market_gap_mean_pp']:+.2f} pp/month")
            else:
                print(f"  {group['regime']:8} no observations")
    print(f"Saved {args.out / 'robustness_summary.json'} and {args.out / 'regime_sensitivity.csv'}")


if __name__ == "__main__":
    main()

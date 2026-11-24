#!/usr/bin/env python3
"""Exact accounting identity for YTSL NAV DRIP vs unhedged TSLA CAD wealth.

All components are arithmetic identities for the same observed paired returns.
The nonlinear term is NOT an independently identified options/financing/FX
cost; the quadratic approximation is NOT a structural volatility-drag estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from .benchmark import build_tsla_fx_reference
from .exposure import END, START, paired_daily
from .nav import compute_nav_index, load_nav
from .paths import CASH_EVENTS, OUTPUT_DIR, SNAPSHOT_DIR
from .returns import read_cash_events


class CompoundingError(ValueError):
    pass


def _finite_positive_factor(series: pd.Series, name: str) -> None:
    values = pd.to_numeric(series, errors="coerce")
    if (values.isna().any() or
            not values.map(math.isfinite).all() or
            values.le(-1).any()):
        raise CompoundingError(f"{name}: every simple return must be finite and > -100%")


def decompose(pairs: pd.DataFrame) -> pd.DataFrame:
    """For each common-close return interval, log gap = arithmetic + nonlinear.

    Exact identity: log(1+y)-log(1+x) = (y-x) +
        { [log(1+y)-y] - [log(1+x)-x] }.
    Taylor: nonlinear = -0.5*(y*y - x*x) + higher-order remainder.

    Values are *decimal* returns until exported, not terminal return pp.
    """
    required = {
        "date", "previous_date", "tsla_cad_return", "ytsl_nav_return",
        "nav_drip_index", "tsla_cad_reference",
    }
    if not required.issubset(pairs):
        raise CompoundingError(f"Missing paired interval columns: {sorted(required - set(pairs))}")
    if pairs.empty or not pairs["date"].is_monotonic_increasing or pairs["date"].duplicated().any():
        raise CompoundingError("Paired intervals must be nonempty, sorted, and unique")
    out = pairs.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["previous_date"] = pd.to_datetime(out["previous_date"], errors="coerce")
    if out[["date", "previous_date"]].isna().any().any():
        raise CompoundingError("Invalid paired dates")
    if not out["date"].gt(out["previous_date"]).all():
        raise CompoundingError("Return interval end must follow start")
    if (out["previous_date"].iloc[1:].reset_index(drop=True) !=
            out["date"].iloc[:-1].reset_index(drop=True)).any():
        raise CompoundingError("Paired return intervals must be contiguous")
    for col in ("tsla_cad_return", "ytsl_nav_return"):
        _finite_positive_factor(out[col], col)
        out[col] = pd.to_numeric(out[col])
    for col in ("nav_drip_index", "tsla_cad_reference"):
        val = pd.to_numeric(out[col], errors="coerce")
        if val.isna().any() or val.le(0).any() or not val.map(math.isfinite).all():
            raise CompoundingError(f"{col}: invalid wealth/reference level")

    x, y = out["tsla_cad_return"], out["ytsl_nav_return"]
    out["log_ytsl"] = y.map(math.log1p)
    out["log_tsla"] = x.map(math.log1p)
    out["arithmetic_spread"] = y - x
    out["relative_log_spread"] = out["log_ytsl"] - out["log_tsla"]
    out["nonlinear_correction"] = out["relative_log_spread"] - out["arithmetic_spread"]
    out["quadratic_component"] = -0.5 * (y * y - x * x)
    out["higher_order_remainder"] = (
        out["nonlinear_correction"] - out["quadratic_component"]
    )
    out["year"] = out["date"].dt.year
    out["tsla_direction"] = x.map(lambda r: "Up" if r > 0 else ("Down" if r < 0 else "Flat"))
    out["cumulative_nav_wealth"] = out["log_ytsl"].cumsum().map(math.exp)
    out["cumulative_tsla_wealth"] = out["log_tsla"].cumsum().map(math.exp)
    out["cumulative_relative_log_spread"] = out["relative_log_spread"].cumsum()
    out["cumulative_arithmetic_spread"] = out["arithmetic_spread"].cumsum()
    out["cumulative_nonlinear_correction"] = out["nonlinear_correction"].cumsum()
    out["cumulative_relative_wealth_ratio"] = out["cumulative_relative_log_spread"].map(math.exp)
    out["cumulative_return_gap_pp"] = 100 * (
        out["cumulative_nav_wealth"] - out["cumulative_tsla_wealth"])
    return out


def _sum_column(frame: pd.DataFrame, col: str) -> float:
    return math.fsum(float(v) for v in frame[col])


def components(frame: pd.DataFrame) -> dict:
    """Use 100x decimal scaling, NOT terminal percentage points."""
    n = len(frame)
    arithmetic = _sum_column(frame, "arithmetic_spread")
    nonlinear = _sum_column(frame, "nonlinear_correction")
    quadratic = _sum_column(frame, "quadratic_component")
    higher_order = _sum_column(frame, "higher_order_remainder")
    relative_log = _sum_column(frame, "relative_log_spread")
    return {
        "intervals": n,
        "arithmetic_spread_sum_100x": 100 * arithmetic,
        "nonlinear_correction_100x": 100 * nonlinear,
        "quadratic_approx_100x": 100 * quadratic,
        "higher_order_remainder_100x": 100 * higher_order,
        "relative_log_wealth_100x": 100 * relative_log,
        "identity_residual_100x": 100 * (relative_log - arithmetic - nonlinear),
        "quadratic_identity_residual_100x": 100 * (nonlinear - quadratic - higher_order),
    }


def _grouped(frame: pd.DataFrame, by: str) -> list[dict]:
    out = []
    for name, subset in frame.groupby(by, sort=True):
        out.append({by: int(name) if by == "year" else str(name),
                    **components(subset)})
    return out


def _extreme_intervals(frame: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = [
        "date", "previous_date", "tsla_cad_return", "ytsl_nav_return",
        "arithmetic_spread", "nonlinear_correction",
        "relative_log_spread",
    ]
    worst = frame.nsmallest(n, "relative_log_spread")[cols].copy()
    worst["direction"] = "worst_for_ytsl"
    best = frame.nlargest(n, "relative_log_spread")[cols].copy()
    best["direction"] = "best_for_ytsl"
    return pd.concat([worst, best], ignore_index=True)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def study(pairs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Construct full accounting, exact terminal-wealth bridge and group checks."""
    intervals = decompose(pairs)
    sums = components(intervals)
    annual = _grouped(intervals, "year")
    directions = _grouped(intervals, "tsla_direction")
    nav = math.exp(_sum_column(intervals, "log_ytsl"))
    tsla = math.exp(_sum_column(intervals, "log_tsla"))
    log_ratio = math.log(nav / tsla)
    direct_from_levels = (
        float(pairs["nav_drip_index"].iloc[-1]) /
        (float(pairs["nav_drip_index"].iloc[0]) /
         (1 + float(pairs["ytsl_nav_return"].iloc[0]))),
        float(pairs["tsla_cad_reference"].iloc[-1]) /
        (float(pairs["tsla_cad_reference"].iloc[0]) /
         (1 + float(pairs["tsla_cad_return"].iloc[0]))),
    )
    tol = 1e-10
    if abs(nav - direct_from_levels[0]) > tol or abs(tsla - direct_from_levels[1]) > tol:
        raise CompoundingError("Terminal wealth fails independent NAV/TSLA level check")
    if abs(log_ratio - sums["relative_log_wealth_100x"] / 100) > tol:
        raise CompoundingError("Log wealth fails exact arithmetic/nonlinear bridge")
    if abs(sums["identity_residual_100x"]) > tol:
        raise CompoundingError("Arithmetic and nonlinear terms fail identity")
    for group in (annual, directions):
        if abs(math.fsum(x["relative_log_wealth_100x"] for x in group) -
               sums["relative_log_wealth_100x"]) > tol:
            raise CompoundingError("Grouped log contributions do not sum to full window")

    return intervals, {
        "status": "pass",
        "start": pairs["previous_date"].iloc[0].strftime("%Y-%m-%d"),
        "end": pairs["date"].iloc[-1].strftime("%Y-%m-%d"),
        "shared_closes": len(pairs) + 1,
        "paired_intervals": len(pairs),
        "wealth": {
            "ytsl_nav_multiple": nav,
            "tsla_cad_multiple": tsla,
            "ytsl_nav_total_return_pct": 100 * (nav - 1),
            "tsla_cad_total_return_pct": 100 * (tsla - 1),
            "terminal_return_gap_pp_of_initial_capital": 100 * (nav - tsla),
            "relative_wealth_ratio_ytsl_over_tsla": nav / tsla,
            "relative_wealth_shortfall_pct_of_tsla_terminal": 100 * (nav / tsla - 1),
        },
        "components_100x_decimal": sums,
        "accounting_fraction_of_negative_log_gap": {
            "arithmetic_spread": (
                sums["arithmetic_spread_sum_100x"] /
                sums["relative_log_wealth_100x"] if sums["relative_log_wealth_100x"] else None),
            "nonlinear_correction": (
                sums["nonlinear_correction_100x"] /
                sums["relative_log_wealth_100x"] if sums["relative_log_wealth_100x"] else None),
        },
        "by_year": annual,
        "by_tsla_direction": directions,
        "extremes": {
            "worst_log_interval": intervals.nsmallest(1, "relative_log_spread")["date"].iloc[0].strftime("%Y-%m-%d"),
            "best_log_interval": intervals.nlargest(1, "relative_log_spread")["date"].iloc[0].strftime("%Y-%m-%d"),
        },
        "identity": (
            "sum(log1p(y)-log1p(x)) = sum(y-x) + "
            "sum([log1p(y)-y] - [log1p(x)-x])"
        ),
        "measurement": (
            "components_100x_decimal are 100 times sums of decimal-return terms. "
            "They are algebraic log-point-scale components, NOT shares of initial "
            "capital or independently identified economic drag."
        ),
        "limitations": (
            "NAV-based descriptive identity only. Return gap compounds; assigning "
            "nonlinear correction to covered calls, leverage, fee, borrowing, FX "
            "hedging or a counterfactual strategy is not identified."
        ),
    }


def run(snapshot_dir: Path = SNAPSHOT_DIR, cash_file: Path = CASH_EVENTS,
        out_dir: Path = OUTPUT_DIR / "compounding", *,
        start: pd.Timestamp = START, end: pd.Timestamp = END) -> dict:
    source_files = {
        "purpose_nav": snapshot_dir / "ytsl_purpose_daily.csv",
        "tsla_usd": snapshot_dir / "tsla_yahoo_daily.csv",
        "usd_cad": snapshot_dir / "usdcad_boc_daily.csv",
        "cash_events": cash_file,
    }
    source_status = json.loads((snapshot_dir / "fetch_status.json").read_text(encoding="utf-8"))
    if source_status.get("status") != "ok" or source_status.get("data_type") != "LIVE_SOURCE_DATA":
        raise CompoundingError("Only validated LIVE_SOURCE_DATA snapshots may be analyzed")
    nav = compute_nav_index(load_nav(source_files["purpose_nav"]), read_cash_events(cash_file))
    reference = build_tsla_fx_reference(
        pd.read_csv(source_files["tsla_usd"]), pd.read_csv(source_files["usd_cad"]))
    pairs = paired_daily(nav, reference, start=start, end=end)
    intervals, report = study(pairs)
    report["input_sha256"] = {k: _hash(p) for k, p in source_files.items()}
    report["snapshot_data_type"] = source_status["data_type"]
    out_dir.mkdir(parents=True, exist_ok=True)
    intervals.to_csv(out_dir / "compounding_daily.csv", index=False)
    pd.DataFrame(report["by_year"]).to_csv(out_dir / "annual_log_components.csv", index=False)
    _extreme_intervals(intervals).to_csv(out_dir / "extreme_intervals.csv", index=False)
    (out_dir / "compounding_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    ap.add_argument("--events", type=Path, default=CASH_EVENTS)
    ap.add_argument("--out", type=Path, default=OUTPUT_DIR / "compounding")
    args = ap.parse_args()
    try:
        result = run(args.snapshot_dir, args.events, args.out)
    except (ValueError, OSError, KeyError) as err:
        ap.exit(1, f"Compounding study failed: {err}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

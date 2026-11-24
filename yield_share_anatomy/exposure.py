#!/usr/bin/env python3
"""Descriptive effective exposure of YTSL NAV DRIP to TSLA/CAD returns.

OLS with an intercept on aligned common-close-to-common-close intervals.
This is an observed sensitivity, NOT disclosed fund leverage or a causal
decomposition of covered calls, FX hedging, options or financing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

import pandas as pd

from .benchmark import build_tsla_fx_reference
from .monthly_validation import independent_monthly
from .nav import compute_nav_index, load_nav
from .paths import CASH_EVENTS, OUTPUT_DIR, SNAPSHOT_DIR
from .returns import read_cash_events

START = pd.Timestamp("2022-12-21")
END = pd.Timestamp("2026-11-20")
DEFAULT_BLOCK = 10
DEFAULT_REPLICATES = 800
DEFAULT_SEED = 20261120


class ExposureError(ValueError):
    pass


def paired_daily(nav_index: pd.DataFrame, tsla_reference: pd.DataFrame, *,
                 start: pd.Timestamp = START,
                 end: pd.Timestamp = END) -> pd.DataFrame:
    """Select *same-date* observations first; compute interval returns second.

    Both native wealth paths are independently computed on their own calendars
    before matching closes. An intervening nonshared session is accumulated
    inside the common-close interval, not silently lost or shifted.
    """
    if not {"date", "nav_drip_index"}.issubset(nav_index):
        raise ExposureError("Missing NAV index/date fields")
    if not {"date", "tsla_cad_reference"}.issubset(tsla_reference):
        raise ExposureError("Missing TSLA CAD reference/date fields")
    if pd.Timestamp(start) >= pd.Timestamp(end):
        raise ExposureError("Start must precede end")

    nav = nav_index[["date", "nav_drip_index"]].copy()
    tsla = tsla_reference[["date", "tsla_cad_reference"]].copy()
    for name, frame, field in (
        ("NAV", nav, "nav_drip_index"),
        ("TSLA", tsla, "tsla_cad_reference"),
    ):
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
        if frame["date"].isna().any() or frame["date"].duplicated().any():
            raise ExposureError(f"{name} has invalid or duplicate dates")
        values = frame[field].dropna()
        if values.empty or values.le(0).any() or not values.map(math.isfinite).all():
            raise ExposureError(f"{name} has nonpositive or nonfinite values")
    joined = nav.merge(tsla.dropna(subset=["tsla_cad_reference"]), on="date",
                       validate="one_to_one")
    joined = joined.loc[
        joined["date"].between(pd.Timestamp(start), pd.Timestamp(end))
    ].sort_values("date").reset_index(drop=True)
    if (joined.empty or joined["date"].iloc[0] != pd.Timestamp(start) or
            joined["date"].iloc[-1] != pd.Timestamp(end)):
        raise ExposureError("Exact requested start/end must be shared NAV/TSLA dates")
    if len(joined) < 4:
        raise ExposureError("Need at least four common-date NAV/TSLA observations")
    joined["previous_date"] = joined["date"].shift(1)
    joined["gap_calendar_days"] = (joined["date"] - joined["previous_date"]).dt.days
    joined["tsla_cad_return"] = joined["tsla_cad_reference"].pct_change(fill_method=None)
    joined["ytsl_nav_return"] = joined["nav_drip_index"].pct_change(fill_method=None)
    out = joined.iloc[1:].copy().reset_index(drop=True)
    if out[["tsla_cad_return", "ytsl_nav_return"]].isna().any().any():
        raise ExposureError("Missing paired interval returns")
    out["nav_minus_tsla_pp"] = 100 * (
        out["ytsl_nav_return"] - out["tsla_cad_return"])
    out["tsla_direction"] = out["tsla_cad_return"].map(
        lambda r: "Up" if r > 0 else ("Down" if r < 0 else "Flat"))
    return out


def fit_beta(pairs: pd.DataFrame, *, min_n: int = 3) -> dict:
    """Unweighted OLS y = alpha + beta*x; both x,y are decimal returns."""
    if not {"tsla_cad_return", "ytsl_nav_return"}.issubset(pairs):
        raise ExposureError("Missing paired return columns")
    if len(pairs) < min_n:
        raise ExposureError(f"At least {min_n} paired intervals required")
    x = [float(v) for v in pairs["tsla_cad_return"]]
    y = [float(v) for v in pairs["ytsl_nav_return"]]
    if not all(map(math.isfinite, x + y)):
        raise ExposureError("Nonfinite returns are not allowed")
    xbar = statistics.fmean(x)
    ybar = statistics.fmean(y)
    sxx = sum((v - xbar)**2 for v in x)
    syy = sum((v - ybar)**2 for v in y)
    sxy = sum((a - xbar) * (b - ybar) for a, b in zip(x, y))
    if sxx <= 1e-25:
        raise ExposureError("Cannot estimate beta with constant TSLA returns")
    beta = sxy / sxx
    alpha = ybar - beta * xbar
    return {
        "n": len(x),
        "beta": beta,
        "alpha_interval_pp": alpha * 100,
        "r_squared": (sxy*sxy/(sxx*syy)) if syy > 1e-25 else None,
        "mean_tsla_interval_pct": xbar * 100,
        "mean_nav_interval_pct": ybar * 100,
        "mean_relative_interval_pp": (ybar - xbar) * 100,
    }


def conditional_fits(pairs: pd.DataFrame, *,
                     threshold_pct: float = 0.0,
                     min_n: int = 3) -> dict:
    """Split by *TSLA/CAD* sign, optionally ignoring abs returns <= cutoff."""
    if threshold_pct < 0:
        raise ExposureError("Direction threshold must be nonnegative")
    limit = threshold_pct/100
    up = pairs.loc[pairs["tsla_cad_return"] > limit]
    down = pairs.loc[pairs["tsla_cad_return"] < -limit]
    if min(len(up), len(down)) < min_n:
        raise ExposureError(f"Need >= {min_n} Up and Down intervals")
    u, d = fit_beta(up, min_n=min_n), fit_beta(down, min_n=min_n)
    return {
        "threshold_pct": threshold_pct,
        "up": u,
        "down": d,
        "down_minus_up_beta": d["beta"] - u["beta"],
        "excluded_near_zero": len(pairs) - len(up) - len(down),
    }


def _percentile(data: list[float], pct: float) -> float:
    if not data or not 0 <= pct <= 1:
        raise ExposureError("Invalid percentile")
    seq = sorted(data)
    pos = (len(seq) - 1) * pct
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return seq[lo] + (pos - lo) * (seq[hi] - seq[lo])


def block_bootstrap(pairs: pd.DataFrame, *,
                    block: int = DEFAULT_BLOCK,
                    replicates: int = DEFAULT_REPLICATES,
                    seed: int = DEFAULT_SEED) -> dict:
    """Moving-block bootstrap of paired return intervals.

    Resample contiguous *joint* (TSLA,CAD NAV) return pairs, preserving
    some serial dependence. Confidence intervals are descriptive and
    not evidence for causality or a calibrated forecasting strategy.
    """
    n = len(pairs)
    if n < 12 or block < 1 or block > n//2 or replicates < 20:
        raise ExposureError("Need n>=12, 1<=block<=n/2, replicates>=20")
    values = [
        (float(x),float(y))
        for x,y in zip(pairs["tsla_cad_return"],pairs["ytsl_nav_return"])
    ]
    rng = random.Random(seed)
    outcomes = {"full": [], "up": [], "down": [], "down_minus_up": []}
    for _ in range(replicates):
        sampled = []
        while len(sampled) < n:
            pos = rng.randrange(n - block + 1)
            sampled.extend(values[pos:pos + block])
        sampled = sampled[:n]
        frame = pd.DataFrame(sampled, columns=[
            "tsla_cad_return", "ytsl_nav_return"])
        split = conditional_fits(frame, min_n=3)
        all_fit = fit_beta(frame)
        outcomes["full"].append(all_fit["beta"])
        outcomes["up"].append(split["up"]["beta"])
        outcomes["down"].append(split["down"]["beta"])
        outcomes["down_minus_up"].append(split["down_minus_up_beta"])
    limits = {key: [_percentile(values, 0.025), _percentile(values, 0.975)]
              for key, values in outcomes.items()}
    return {
        "method": "overlapping_moving_block_bootstrap",
        "block_size_joint_intervals": block,
        "replicates": replicates,
        "seed": seed,
        "beta_ci_95": limits,
        "delta_includes_zero": limits["down_minus_up"][0] <= 0 <= limits["down_minus_up"][1],
        "warning": "Serial-dependence-aware heuristic CI, not proof of structural leverage or significance under all market models.",
    }


def rolling_beta(pairs: pd.DataFrame, *,
                 windows: tuple[int, ...] = (63, 126)) -> pd.DataFrame:
    """One trailing OLS estimate per requested fully observed window."""
    if not windows or any(w < 3 for w in windows):
        raise ExposureError("Rolling windows must be >=3 observations")
    rows = []
    for w in windows:
        for i in range(w - 1, len(pairs)):
            subset = pairs.iloc[i - w + 1:i + 1]
            fit = fit_beta(subset)
            rows.append({
                "date": pairs["date"].iloc[i],
                "window_intervals": w,
                "start_date": subset["previous_date"].iloc[0],
                "beta": fit["beta"],
                "r_squared": fit["r_squared"],
                "alpha_interval_pp": fit["alpha_interval_pp"],
            })
    return pd.DataFrame(rows).sort_values(
        ["window_intervals", "date"]).reset_index(drop=True)


def _safe_fit(pairs: pd.DataFrame, min_n: int) -> dict:
    if len(pairs) < min_n:
        return {"status": "insufficient_sample", "n": len(pairs)}
    return {"status": "estimated", **fit_beta(pairs, min_n=min_n)}


def annual_fits(pairs: pd.DataFrame) -> list[dict]:
    annual = []
    for year, group in pairs.groupby(pairs["date"].dt.year):
        row = {"year": int(year), **_safe_fit(group, 30)}
        if row["status"] == "estimated":
            try:
                row["directional"] = conditional_fits(group, min_n=25)
            except ExposureError:
                row["directional"] = {"status": "insufficient_sign_subsets"}
        annual.append(row)
    return annual


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(snapshot_dir: Path = SNAPSHOT_DIR, events_file: Path = CASH_EVENTS,
        out_dir: Path = OUTPUT_DIR / "effective_beta", *,
        start: pd.Timestamp = START, end: pd.Timestamp = END,
        block: int = DEFAULT_BLOCK, replicates: int = DEFAULT_REPLICATES,
        seed: int = DEFAULT_SEED) -> dict:
    inputs = {
        "nav": snapshot_dir / "ytsl_purpose_daily.csv",
        "tsla": snapshot_dir / "tsla_yahoo_daily.csv",
        "fx": snapshot_dir / "usdcad_boc_daily.csv",
        "cash_events": events_file,
    }
    status_path = snapshot_dir / "fetch_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("status") != "ok" or status.get("data_type") != "LIVE_SOURCE_DATA":
        raise ExposureError("Expected complete LIVE_SOURCE_DATA historical snapshot")
    cash = read_cash_events(events_file)
    nav_index = compute_nav_index(load_nav(inputs["nav"]), cash)
    tsla_fx = build_tsla_fx_reference(
        pd.read_csv(inputs["tsla"]), pd.read_csv(inputs["fx"]))
    paired = paired_daily(nav_index, tsla_fx, start=start, end=end)
    full = fit_beta(paired)
    direction = conditional_fits(paired)
    above_1pct = conditional_fits(paired, threshold_pct=1.0)
    ci = block_bootstrap(paired, block=block, replicates=replicates, seed=seed)
    rolling = rolling_beta(paired)
    annual = annual_fits(paired)
    monthly = independent_monthly(nav_index, tsla_fx)
    monthly_pairs = monthly.rename(columns={
        "tsla_cad_monthly_pct": "tsla_cad_return",
        "nav_monthly_pct": "ytsl_nav_return",
    }).copy()
    monthly_pairs["tsla_cad_return"] /= 100
    monthly_pairs["ytsl_nav_return"] /= 100
    monthly_all = fit_beta(monthly_pairs)
    monthly_down = _safe_fit(monthly_pairs.loc[
        monthly_pairs["tsla_cad_return"] < -.05], 8)
    monthly_up = _safe_fit(monthly_pairs.loc[
        monthly_pairs["tsla_cad_return"] > .05], 8)
    rolling_stats = {}
    for w in sorted(rolling["window_intervals"].unique()):
        subset = rolling.loc[rolling["window_intervals"] == w]
        rolling_stats[str(w)] = {
            "observations": len(subset),
            "min_beta": float(subset["beta"].min()),
            "max_beta": float(subset["beta"].max()),
            "latest_beta": float(subset["beta"].iloc[-1]),
            "latest_date": subset["date"].iloc[-1].strftime("%Y-%m-%d"),
        }
    report = {
        "status": "ok",
        "research_status": "descriptive_effective_exposure;cash_events_provisional",
        "start": pd.Timestamp(start).strftime("%Y-%m-%d"),
        "end": pd.Timestamp(end).strftime("%Y-%m-%d"),
        "common_closing_dates": len(paired) + 1,
        "paired_intervals": len(paired),
        "calendar_gap_max_days": int(paired["gap_calendar_days"].max()),
        "full_daily": full,
        "daily_directional": direction,
        "directional_abs_gt_1pct": above_1pct,
        "block_bootstrap": ci,
        "annual": annual,
        "rolling": rolling_stats,
        "monthly_46": {
            "observations": len(monthly_pairs),
            "full": monthly_all,
            "tsla_up_gt_5pct": monthly_up,
            "tsla_down_lt_minus_5pct": monthly_down,
        },
        "inputs_sha256": {k: _hash(p) for k, p in inputs.items()},
        "methodology": {
            "paired": "Both NAV DRIP and TSLA CAD wealth computed on native calendars first; return calculated between consecutive exact common closes",
            "ols": "Daily YTSL NAV DRIP decimal return = alpha + beta*TSLA CAD decimal return; intercept fitted in each subset",
            "directional": "Condition on contemporaneous TSLA CAD sign, not a predictive trading signal",
            "bootstrap": "Resample contiguous blocks of paired observations with replacement; deterministic seed",
            "rolling": "Trailing 63 and 126 common-close return intervals",
            "monthly": "Reuses independently validated NAV/TSLA CAD native month ends; current pinned sample 46 full months",
            "limits": "Sensitivity not nominal leverage. Fund leverage/options/fees/FX hedge are not individually identifiable from these two series.",
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    paired.to_csv(out_dir / "paired_daily_returns.csv", index=False)
    rolling.to_csv(out_dir / "rolling_beta.csv", index=False)
    pd.DataFrame(annual).to_csv(out_dir / "annual_beta.csv", index=False)
    (out_dir / "effective_beta_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    p.add_argument("--events", type=Path, default=CASH_EVENTS)
    p.add_argument("--out", type=Path, default=OUTPUT_DIR / "effective_beta")
    p.add_argument("--block", type=int, default=DEFAULT_BLOCK)
    p.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    try:
        summary = run(args.snapshot_dir, args.events, args.out,
                      block=args.block, replicates=args.replicates, seed=args.seed)
    except (ValueError, OSError, KeyError) as exc:
        p.exit(1, f"Exposure study failed: {exc}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

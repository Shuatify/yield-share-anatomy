#!/usr/bin/env python3
"""Frictionless daily-reset TSLA CAD leverage as a counterfactual baseline.

We do NOT claim this models YTSL leverage, financing, covered calls, currency
hedging, option premium or trading operations. Leverage is reset on every
valid native US TSLA trading session, including those absent from YTSL NAV.
The fund and the model are compared only at matching observed closes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from .benchmark import build_tsla_fx_reference
from .exposure import END, START, conditional_fits, fit_beta, paired_daily
from .nav import compute_nav_index, load_nav
from .paths import CASH_EVENTS, OUTPUT_DIR, SNAPSHOT_DIR
from .returns import read_cash_events

DEFAULT_LEVERAGES = (1.0, 1.1, 1.2)
MAX_CALENDAR_GAP_DAYS = 7
VALIDATION_TOLERANCE = 1e-9


class CounterfactualError(ValueError):
    pass


def leverage_index(tsla_fx: pd.DataFrame, leverage: float, *,
                   start: pd.Timestamp = START, end: pd.Timestamp = END
                   ) -> pd.DataFrame:
    """Build wealth with daily factor 1 + L * (TSLA_CAD[t]/TSLA_CAD[t-1] - 1).

    No financing/fees/interest, dividends other than Yahoo adjustments,
    currency hedge, slippage, margin constraints or trade execution. The
    index is initialized to 1 at the *start close*, then reset every TSLA
    daily close, not only on days shared with the Canadian ETF.
    """
    if not math.isfinite(leverage) or leverage <= 0:
        raise CounterfactualError("Leverage must be positive and finite")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start >= end:
        raise CounterfactualError("Start must be strictly earlier than end")
    required = {"date", "tsla_cad_reference"}
    if not required.issubset(tsla_fx):
        raise CounterfactualError(f"Missing TSLA FX columns: {sorted(required-set(tsla_fx))}")
    df = tsla_fx[["date", "tsla_cad_reference"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["tsla_cad_reference"] = pd.to_numeric(df["tsla_cad_reference"], errors="coerce")
    if df["date"].isna().any() or df["date"].duplicated().any():
        raise CounterfactualError("Invalid or duplicate TSLA trading dates")
    df = df.loc[df["date"].between(start, end)].sort_values("date").reset_index(drop=True)
    if len(df) < 2 or df["date"].iloc[0] != start or df["date"].iloc[-1] != end:
        raise CounterfactualError("Exact model start and end must exist on TSLA's native calendar")
    prices = df["tsla_cad_reference"]
    if prices.isna().any() or prices.le(0).any() or not prices.map(math.isfinite).all():
        raise CounterfactualError("Missing, nonpositive, or nonfinite TSLA CAD observations")
    if df["date"].diff().dt.days.iloc[1:].gt(MAX_CALENDAR_GAP_DAYS).any():
        raise CounterfactualError("Excessive gap in TSLA daily reference data")
    df["tsla_cad_return"] = prices.pct_change(fill_method=None)
    df["leverage"] = float(leverage)
    factors = 1 + leverage * df["tsla_cad_return"]
    if factors.iloc[1:].isna().any() or not factors.iloc[1:].map(math.isfinite).all():
        raise CounterfactualError("Invalid model daily return")
    if factors.iloc[1:].le(0).any():
        raise CounterfactualError("Model wipes out on a day: 1 + leverage*return <= 0")
    factors.iloc[0] = 1.0
    df["model_factor"] = factors
    df["wealth_multiple"] = factors.cumprod()
    return df


def _drawdown_at_shared_closes(wealth: pd.Series) -> float:
    if wealth.empty or wealth.isna().any() or wealth.le(0).any():
        raise CounterfactualError("Invalid shared-close wealth path")
    peak = wealth.cummax()
    return 100 * float((wealth / peak - 1).min())


def _grouped_calendar_year(pairs: pd.DataFrame, model_returns: pd.Series) -> list[dict]:
    work = pairs[["date", "tsla_cad_return", "ytsl_nav_return"]].copy()
    work["model_return"] = model_returns.to_numpy()
    work["year"] = work["date"].dt.year
    result = []
    for year, g in work.groupby("year", sort=True):
        result.append({
            "year": int(year), "intervals": len(g),
            "tsla_cad_return_pct": 100 * (math.prod(1 + float(r) for r in g["tsla_cad_return"]) - 1),
            "ytsl_nav_drip_return_pct": 100 * (math.prod(1 + float(r) for r in g["ytsl_nav_return"]) - 1),
            "model_return_pct": 100 * (math.prod(1 + float(r) for r in g["model_return"]) - 1),
        })
    return result


def study(nav_index: pd.DataFrame, tsla_fx: pd.DataFrame, *,
          start: pd.Timestamp = START, end: pd.Timestamp = END,
          leverages: tuple[float, ...] = DEFAULT_LEVERAGES
          ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Compare model paths and fund NAV on precisely the same endpoints."""
    if not leverages or any(not math.isfinite(l) or l <= 0 for l in leverages):
        raise CounterfactualError("A nonempty list of positive finite leverages is required")
    if len(set(leverages)) != len(leverages):
        raise CounterfactualError("Duplicate scenario leverages are not allowed")
    if 1.0 not in leverages:
        raise CounterfactualError("Include 1.0x as an unleveraged identity control")
    paired = paired_daily(nav_index, tsla_fx, start=start, end=end)
    # The first row in paired starts on START and ends on the second common
    # close. Reconstruct the complete list to align scenario wealth levels.
    shared_dates = pd.DatetimeIndex([pd.Timestamp(start), *paired["date"].tolist()])
    nav_levels = nav_index.set_index("date")["nav_drip_index"].loc[shared_dates].astype(float)
    nav_multiple = nav_levels / float(nav_levels.iloc[0])
    nav_total = 100 * (float(nav_multiple.iloc[-1]) - 1)
    baseline = paired["tsla_cad_return"].astype(float)
    tsla_end = math.prod(1 + float(r) for r in baseline)
    real_conditional = conditional_fits(paired)
    scenarios: list[dict] = []
    native_rows: list[pd.DataFrame] = []
    shared_records = pd.DataFrame({
        "date": shared_dates,
        "ytsl_nav_wealth_multiple": nav_multiple.to_numpy(),
    })
    for leverage in leverages:
        native = leverage_index(tsla_fx, leverage, start=start, end=end)
        native_rows.append(native)
        wealth = native.set_index("date")["wealth_multiple"].loc[shared_dates].astype(float)
        values = wealth.to_numpy()
        shared_records[f"wealth_{leverage:g}x"] = values
        common_returns = wealth.pct_change(fill_method=None).iloc[1:].reset_index(drop=True)
        # OLS up/down slopes of the model *against the same TSLA CAD*
        # interval returns that were used for NAV effective-beta research.
        model_pairs = paired[["tsla_cad_return"]].copy()
        model_pairs["ytsl_nav_return"] = common_returns.to_numpy()
        fitted = fit_beta(model_pairs)
        direction = conditional_fits(model_pairs)
        model_end = float(wealth.iloc[-1])
        if leverage == 1.0 and abs(model_end - tsla_end) > VALIDATION_TOLERANCE:
            raise CounterfactualError("1.0x daily model fails unleveraged TSLA CAD identity control")
        if abs(model_end - math.prod(1 + float(r) for r in common_returns)) > VALIDATION_TOLERANCE:
            raise CounterfactualError("Model wealth fails common-close return product")
        scenarios.append({
            "leverage": leverage,
            "native_us_trading_closes": len(native),
            "shared_closes": len(shared_dates),
            "wealth_multiple": model_end,
            "total_return_pct": 100 * (model_end - 1),
            "nav_minus_model_pp_initial_capital": 100 * (float(nav_multiple.iloc[-1]) - model_end),
            "model_minus_1x_pp_initial_capital": 100 * (model_end - tsla_end),
            "max_drawdown_shared_closes_pct": _drawdown_at_shared_closes(wealth),
            "effective_beta_vs_tsla_cad": fitted,
            "conditional_beta_vs_tsla_cad": direction,
            "by_calendar_year": _grouped_calendar_year(paired, common_returns),
        })
    # The full native daily path includes TSLA US closes on dates absent
    # from Purpose NAV. Never replace daily rebalancing with a shortcut
    # applying leverage to multi-day common-close returns.
    first = next(v for v in scenarios if v["leverage"] == 1.0)
    if abs(first["total_return_pct"] - 100*(tsla_end-1)) > VALIDATION_TOLERANCE:
        raise CounterfactualError("Unleveraged return does not match TSLA CAD")
    report = {
        "status": "pass",
        "study_type": "zero_carry_daily_reset_counterfactual_not_YTSL_strategy_replica",
        "start": pd.Timestamp(start).strftime("%Y-%m-%d"),
        "end": pd.Timestamp(end).strftime("%Y-%m-%d"),
        "native_tsla_trading_closes": len(native_rows[0]),
        "shared_nav_tsla_closes": len(shared_dates),
        "shared_return_intervals": len(paired),
        "actual_ytsl_nav": {
            "wealth_multiple": float(nav_multiple.iloc[-1]),
            "total_return_pct": nav_total,
            "max_drawdown_shared_closes_pct": _drawdown_at_shared_closes(nav_multiple),
            "up_beta": real_conditional["up"]["beta"],
            "down_beta": real_conditional["down"]["beta"],
            "down_minus_up_beta": real_conditional["down_minus_up_beta"],
        },
        "scenarios": scenarios,
        "assumptions": {
            "reference": "TSLA Yahoo USD adjusted close multiplied by BoC historical USD/CAD reference",
            "reset_frequency": "Every native US TSLA daily session close, including dates without YTSL NAV",
            "daily_simple_return": "model = leverage * simple TSLA CAD reference return",
            "wealth_factor": "1 + leverage * daily simple reference return",
            "financing_cost": 0,
            "transaction_cost": 0,
            "currency_hedge": "none",
            "margin_liquidations": "ignored unless factor <= 0, then model fails",
            "ETF_replication_claim": False,
            "limitations": "Fund financing, options income/cost, dynamic leverage, hedging, fees, funding availability and executable closes are not modeled. Residual is not attributable to covered calls.",
        },
    }
    return pd.concat(native_rows, ignore_index=True), shared_records, report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(snapshot_dir: Path = SNAPSHOT_DIR, cash_file: Path = CASH_EVENTS,
        out_dir: Path = OUTPUT_DIR / "leverage_counterfactual",
        *, start: pd.Timestamp = START, end: pd.Timestamp = END
        ) -> dict:
    sources = {
        "purpose_nav": snapshot_dir / "ytsl_purpose_daily.csv",
        "tsla_usd": snapshot_dir / "tsla_yahoo_daily.csv",
        "usd_cad": snapshot_dir / "usdcad_boc_daily.csv",
        "cash_events": cash_file,
    }
    status = json.loads((snapshot_dir / "fetch_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "ok" or status.get("data_type") != "LIVE_SOURCE_DATA":
        raise CounterfactualError("Pinned source must be LIVE_SOURCE_DATA")
    nav = compute_nav_index(load_nav(sources["purpose_nav"]), read_cash_events(cash_file))
    reference = build_tsla_fx_reference(
        pd.read_csv(sources["tsla_usd"]), pd.read_csv(sources["usd_cad"]))
    native, shared, report = study(nav, reference, start=start, end=end)
    report["input_sha256"] = {k: _sha256(path) for k,path in sources.items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    native.to_csv(out_dir / "daily_model_on_tsla_sessions.csv", index=False)
    shared.to_csv(out_dir / "common_close_wealth.csv", index=False)
    (out_dir / "leverage_counterfactual_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--events", type=Path, default=CASH_EVENTS)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR / "leverage_counterfactual")
    args = parser.parse_args()
    try:
        report = run(args.snapshot_dir, args.events, args.out)
    except (ValueError, OSError, KeyError, OverflowError) as err:
        parser.exit(1, f"Counterfactual failed: {err}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

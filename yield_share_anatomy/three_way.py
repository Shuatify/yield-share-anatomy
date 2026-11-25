"""Compare TSLA unhedged CAD, TSLA CDR CAD, and YTSL NAV DRIP.

Read ONLY immutable research inputs. Align native wealth paths at shared
closes; a Canadian-only trading day must not cause a cash event to move.
No inference about causal option/hedging costs is made here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from .benchmark import build_tsla_fx_reference
from .nav import compute_nav_index, load_nav
from .paths import CASH_EVENTS, OUTPUT_DIR, SNAPSHOT_DIR
from .returns import read_cash_events

START = pd.Timestamp("2022-12-21")
END = pd.Timestamp("2026-11-20")
CDR_FILE = Path("data/snapshots/2026-11-20-cdr-yahoo/tsla_cdr_yahoo_daily.csv")
CDR_MANIFEST = CDR_FILE.with_name("source_manifest.json")

WEALTH = {
    "TSLA CAD (unhedged)": "tsla_cad_wealth",
    "TSLA CDR (CAD hedged)": "tsla_cdr_wealth",
    "YTSL NAV DRIP": "ytsl_nav_drip_wealth",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cdr(path: Path) -> pd.DataFrame:
    cdr = pd.read_csv(path)
    needed = {"date", "close", "adj_close"}
    if not needed.issubset(cdr.columns):
        raise ValueError(f"CDR missing columns: {needed - set(cdr.columns)}")
    cdr["date"] = pd.to_datetime(cdr["date"], errors="raise")
    if cdr["date"].duplicated().any() or cdr["date"].isna().any():
        raise ValueError("CDR has duplicate or invalid dates")
    for col in ("close", "adj_close"):
        cdr[col] = pd.to_numeric(cdr[col], errors="raise")
        if not cdr[col].map(math.isfinite).all() or (cdr[col] <= 0).any():
            raise ValueError(f"Invalid CDR {col} prices")
    # Adjusted prices should not differ when no CDR dividends/splits occurred.
    # Refuse to treat Close as total return if historical actions emerge.
    if ((cdr["close"] / cdr["adj_close"] - 1).abs() > 0.00001).any():
        raise ValueError("CDR Close != Adj Close; review distributions and corporate actions")
    return cdr[["date", "close"]].sort_values("date").reset_index(drop=True)


def align_three_way(
    ytsl_index: pd.DataFrame,
    tsla_fx: pd.DataFrame,
    cdr: pd.DataFrame,
    start: pd.Timestamp = START,
    end: pd.Timestamp = END,
) -> pd.DataFrame:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start >= end:
        raise ValueError("Start must precede end")
    required = (
        (ytsl_index, {"date", "nav_drip_index"}, "YTSL NAV"),
        (tsla_fx, {"date", "tsla_cad_reference"}, "TSLA CAD"),
        (cdr, {"date", "close"}, "CDR"),
    )
    for frame, cols, label in required:
        if not cols.issubset(frame.columns) or frame["date"].duplicated().any():
            raise ValueError(f"{label}: missing columns or duplicated dates")
    # NAV DRIP index is computed on the full issuer NAV calendar FIRST, not
    # recalculated from prices after inner-joining to US trading sessions.
    common = (
        ytsl_index[["date", "nav_drip_index"]]
        .merge(tsla_fx[["date", "tsla_cad_reference"]],
               on="date", how="inner", validate="one_to_one")
        .merge(cdr[["date", "close"]], on="date", how="inner",
               validate="one_to_one")
        .loc[lambda f: f["date"].between(start, end)]
        .sort_values("date")
        .reset_index(drop=True)
    )
    if len(common) < 2:
        raise ValueError("Insufficient shared closes")
    if common["date"].iloc[0] != start or common["date"].iloc[-1] != end:
        raise ValueError("Missing exact common start or end date")
    for raw, wealth in (
        ("tsla_cad_reference", WEALTH["TSLA CAD (unhedged)"]),
        ("close", WEALTH["TSLA CDR (CAD hedged)"]),
        ("nav_drip_index", WEALTH["YTSL NAV DRIP"]),
    ):
        raw_values = pd.to_numeric(common[raw], errors="raise")
        if raw_values.isna().any() or (raw_values <= 0).any() or not raw_values.map(math.isfinite).all():
            raise ValueError(f"Missing/non-positive {raw} on shared dates")
        common[wealth] = 100.0 * raw_values / float(raw_values.iloc[0])
    common = common.rename(columns={"close": "tsla_cdr_close_cad"})
    result_columns = ["date", "tsla_cad_reference", "tsla_cdr_close_cad",
                      "nav_drip_index", *WEALTH.values()]
    return common[result_columns]


def period_table(daily: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Previous period's final common close is each next period's anchor.

    The initial partial period starts at the very first common close.
    Native wealth indices are never reconstituted from monthly data.
    """
    if frequency not in ("year", "month"):
        raise ValueError("Only year and month supported")
    dates = pd.to_datetime(daily["date"])
    keys = dates.dt.year if frequency == "year" else dates.dt.to_period("M").astype(str)
    last_indices = daily.groupby(keys, sort=True).tail(1).index.tolist()
    result = []
    prev = 0
    for group_end in last_indices:
        first_row, last_row = daily.loc[prev], daily.loc[group_end]
        label = str(dates.iloc[group_end].year) if frequency == "year" else dates.iloc[group_end].strftime("%Y-%m")
        row = {
            "period": label,
            "period_start_anchor": dates.iloc[prev].date().isoformat(),
            "period_end_close": dates.iloc[group_end].date().isoformat(),
            "intervals": int(group_end - prev),
            "partial_from_study_start": bool(prev == 0),
            "partial_to_study_end": bool(group_end == len(daily) - 1),
        }
        for col in WEALTH.values():
            row[f"{col}_return_pct"] = 100.0 * (last_row[col] / first_row[col] - 1.0)
        result.append(row)
        prev = group_end
    return pd.DataFrame(result)


def compound_table_matches_terminal(annual: pd.DataFrame, daily: pd.DataFrame, tolerance: float = 1e-9) -> None:
    for col in WEALTH.values():
        annual_return = (1 + annual[f"{col}_return_pct"] / 100.0).prod()
        terminal_return = float(daily[col].iloc[-1] / daily[col].iloc[0])
        if not math.isclose(annual_return, terminal_return, abs_tol=tolerance, rel_tol=tolerance):
            raise ValueError(f"Period compounding disagrees with end-to-end {col}")


def compute(cdr_file: Path, nav_file: Path, cash_file: Path,
            tsla_file: Path, fx_file: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    ytsl = compute_nav_index(load_nav(nav_file), read_cash_events(cash_file))
    tsla_fx = build_tsla_fx_reference(pd.read_csv(tsla_file), pd.read_csv(fx_file))
    cdr = load_cdr(cdr_file)
    daily = align_three_way(ytsl, tsla_fx, cdr)
    annual = period_table(daily, "year")
    monthly = period_table(daily, "month")
    compound_table_matches_terminal(annual, daily)
    compound_table_matches_terminal(monthly, daily)
    totals = {
        label: 100.0 * (float(daily[col].iloc[-1]) / 100.0 - 1.0)
        for label, col in WEALTH.items()
    }
    summary = {
        "status": "reviewed_vendor_data_not_independent_venue_verified",
        "start": daily.date.iloc[0].date().isoformat(),
        "end": daily.date.iloc[-1].date().isoformat(),
        "shared_closes": int(len(daily)),
        "shared_intervals": int(len(daily) - 1),
        "rebased_wealth": 100,
        "total_return_pct": totals,
        "gap_pp": {
            "YTSL_minus_TSLA_unhedged": totals["YTSL NAV DRIP"] - totals["TSLA CAD (unhedged)"],
            "YTSL_minus_TSLA_CDR": totals["YTSL NAV DRIP"] - totals["TSLA CDR (CAD hedged)"],
            "TSLA_CDR_minus_TSLA_unhedged": totals["TSLA CDR (CAD hedged)"] - totals["TSLA CAD (unhedged)"],
        },
        "return_convention": {
            "TSLA CAD (unhedged)": "TSLA Yahoo USD adjusted close * BoC USD/CAD (last known <=5 calendar days), no currency hedge",
            "TSLA CDR (CAD hedged)": "Yahoo TSLA.TO close (same as adj close), dividend/corporate-action history N/A on CIBC page, no additional cash flows assumed",
            "YTSL NAV DRIP": "Purpose NAV and cash entitlements, exact ex-date NAV reinvestment on native NAV calendar BEFORE joining common dates",
            "calendar": "All 3 rebased at exact first common close; no YTSL NAV date dropped before DRIP construction",
            "annual_and_monthly": "Returns anchored to prior period's last shared close; first/last periods may be partial",
        },
        "input_sha256": {
            name: sha256(path) for name, path in (
                ("cdr", cdr_file), ("ytsl_nav", nav_file),
                ("ytsl_cash_events", cash_file), ("tsla_usd", tsla_file), ("boc_usdcad", fx_file))
        },
        "limits": [
            "CDR quotes are reviewed vendor data, including 539 pre-TSX Yahoo historical backfill sessions",
            "Currency hedging mechanics differ between CDR and YTSL; observed gaps are not causal attributions",
            "CDR traded market close vs YTSL issuer NAV is a different valuation basis",
            "No investor tax, execution costs or investor contribution cash flows modeled",
        ],
    }
    return daily, annual, monthly, summary


def run(cdr_file: Path, nav_file: Path, cash_file: Path,
        tsla_file: Path, fx_file: Path, output_dir: Path) -> dict:
    daily, annual, monthly, summary = compute(cdr_file, nav_file, cash_file, tsla_file, fx_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_dir / "three_way_daily.csv", index=False, float_format="%.12f")
    annual.to_csv(output_dir / "three_way_annual.csv", index=False, float_format="%.12f")
    monthly.to_csv(output_dir / "three_way_monthly.csv", index=False, float_format="%.12f")
    (output_dir / "three_way_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cdr", type=Path, default=CDR_FILE)
    p.add_argument("--nav", type=Path, default=SNAPSHOT_DIR / "ytsl_purpose_daily.csv")
    p.add_argument("--cash-events", type=Path, default=CASH_EVENTS)
    p.add_argument("--tsla", type=Path, default=SNAPSHOT_DIR / "tsla_yahoo_daily.csv")
    p.add_argument("--fx", type=Path, default=SNAPSHOT_DIR / "usdcad_boc_daily.csv")
    p.add_argument("--out", type=Path, default=OUTPUT_DIR / "three_way")
    a = p.parse_args()
    summary = run(a.cdr, a.nav, a.cash_events, a.tsla, a.fx, a.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

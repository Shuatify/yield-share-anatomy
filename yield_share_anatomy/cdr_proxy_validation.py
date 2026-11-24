"""Diagnostic audit of candidate CDR closes versus TSLA USD and BoC FX.

This is NOT an estimate of the CIBC published CDR Ratio nor total return.
The reference snapshots and CDR candidate files remain read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def audit(cdr: pd.DataFrame, tsla: pd.DataFrame, fx: pd.DataFrame, *,
          gap_threshold_pp: float = 2.0,
          ratio_change_threshold_pp: float = 3.0) -> tuple[dict, pd.DataFrame]:
    for label, frame, needed in (
        ("cdr", cdr, {"date", "close"}),
        ("tsla", tsla, {"date", "adj_close_usd"}),
        ("fx", fx, {"date", "usd_cad"}),
    ):
        if not needed.issubset(frame.columns):
            raise ValueError(f"{label}: missing {needed - set(frame.columns)}")
        if frame["date"].duplicated().any():
            raise ValueError(f"{label}: duplicate dates")
    c = cdr[["date", "close"]].copy()
    u = tsla[["date", "adj_close_usd"]].copy()
    f = fx[["date", "usd_cad"]].copy()
    for frame in (c, u, f):
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        frame.sort_values("date", inplace=True)
    f.rename(columns={"date": "fx_date"}, inplace=True)
    joined = c.merge(u, on="date", how="inner", validate="one_to_one")
    joined = pd.merge_asof(joined, f, left_on="date", right_on="fx_date",
                           direction="backward", tolerance=pd.Timedelta(days=5))
    if len(joined) < 3 or joined["usd_cad"].isna().any():
        raise ValueError("insufficient common dates or stale FX")
    for name in ("close", "adj_close_usd", "usd_cad"):
        values = pd.to_numeric(joined[name], errors="raise")
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"invalid {name}")
    joined["cdr_return"] = joined["close"].pct_change()
    joined["tsla_usd_return"] = joined["adj_close_usd"].pct_change()
    joined["return_gap_pp"] = 100 * (joined["cdr_return"] - joined["tsla_usd_return"])
    joined["implied_ratio_proxy"] = joined["close"] / (joined["adj_close_usd"] * joined["usd_cad"])
    joined["implied_ratio_delta_pp"] = 100 * joined["implied_ratio_proxy"].pct_change()
    joined["interval_days"] = joined["date"].diff().dt.days
    issues = []
    for _, row in joined.loc[joined["return_gap_pp"].abs() >= gap_threshold_pp].iterrows():
        issues.append({"date": row["date"].date().isoformat(),
                       "code": "cdr_vs_underlying_return_gap",
                       "gap_pp": round(float(row["return_gap_pp"]), 4)})
    for _, row in joined.loc[joined["implied_ratio_delta_pp"].abs() >= ratio_change_threshold_pp].iterrows():
        issues.append({"date": row["date"].date().isoformat(),
                       "code": "large_implied_ratio_proxy_change",
                       "delta_pp": round(float(row["implied_ratio_delta_pp"]), 4)})
    valid = joined.dropna(subset=["cdr_return", "tsla_usd_return"])
    yearly = []
    for year, part in valid.groupby(valid["date"].dt.year):
        yearly.append({"year": int(year), "intervals": int(len(part)),
                       "correlation": round(float(part["cdr_return"].corr(part["tsla_usd_return"])), 6)
                       if len(part) >= 3 else None,
                       "mean_abs_gap_pp": round(float(part["return_gap_pp"].abs().mean()), 4),
                       "max_abs_gap_pp": round(float(part["return_gap_pp"].abs().max()), 4)})
    report = {
        "status": "diagnostic_only_not_external_verification",
        "common_dates": int(len(joined)),
        "first": joined["date"].iloc[0].date().isoformat(),
        "last": joined["date"].iloc[-1].date().isoformat(),
        "cdr_dates_without_us_stock": int(len(c) - len(joined)),
        "whole_window_correlation": round(float(valid["cdr_return"].corr(valid["tsla_usd_return"])), 6),
        "mean_absolute_return_gap_pp": round(float(valid["return_gap_pp"].abs().mean()), 5),
        "implied_ratio_proxy_start": round(float(joined["implied_ratio_proxy"].iloc[0]), 8),
        "implied_ratio_proxy_end": round(float(joined["implied_ratio_proxy"].iloc[-1]), 8),
        "flagged_intervals": issues, "by_year": yearly,
        "limits": [
            "Implied ratio is a traded-price proxy, NOT the issuer CDR ratio",
            "BoC FX reference need not coincide with market close",
            "Shared-close intervals may span holidays",
            "No causal attribution or investable return comparison"
        ]
    }
    return report, joined


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cdr", type=Path, default=Path("outputs/cdr_collection/tsla_cdr_preliminary_daily.csv"))
    p.add_argument("--tsla", type=Path, default=Path("data/snapshots/2026-11-20/tsla_yahoo_daily.csv"))
    p.add_argument("--fx", type=Path, default=Path("data/snapshots/2026-11-20/usdcad_boc_daily.csv"))
    p.add_argument("--out", type=Path, default=Path("outputs/cdr_collection"))
    a = p.parse_args()
    report, detail = audit(pd.read_csv(a.cdr), pd.read_csv(a.tsla), pd.read_csv(a.fx))
    report["input_sha256"] = {label: hashlib.sha256(path.read_bytes()).hexdigest()
                              for label, path in (("cdr", a.cdr), ("tsla", a.tsla), ("fx", a.fx))}
    a.out.mkdir(parents=True, exist_ok=True)
    detail.to_csv(a.out / "cdr_underlying_diagnostic_intervals.csv", index=False)
    (a.out / "cdr_underlying_diagnostic_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("flagged_intervals", "by_year", "limits")}, indent=2))


if __name__ == "__main__":
    main()

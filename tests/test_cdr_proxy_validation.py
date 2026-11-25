import pandas as pd
import pytest
from yield_share_anatomy.cdr_proxy_validation import audit


def test_diagnostic_identity_and_holiday_interval():
    cdr = pd.DataFrame({
        "date": ["2025-02-12", "2025-02-13", "2025-02-18"],
        "close": [10., 11., 12.]
    })
    tsla = pd.DataFrame({
        "date": ["2025-02-12", "2025-02-13", "2025-02-14", "2025-02-18"],
        "adj_close_usd": [100., 110., 115., 120.]
    })
    fx = pd.DataFrame({
        "date": ["2025-02-12", "2025-02-13", "2025-02-14", "2025-02-18"],
        "usd_cad": [1., 1., 1., 1.]
    })
    report, rows = audit(cdr, tsla, fx)
    assert report["common_dates"] == 3
    assert rows["implied_ratio_proxy"].round(8).tolist() == [0.1, 0.1, 0.1]
    assert rows["interval_days"].iloc[2] == 5
    assert not report["flagged_intervals"]


def test_missing_shared_market_dates_rejected():
    with pytest.raises(ValueError, match="insufficient common dates"):
        audit(pd.DataFrame({"date": ["2025-02-12"], "close": [10]}),
              pd.DataFrame({"date": ["2025-02-12"], "adj_close_usd": [100]}),
              pd.DataFrame({"date": ["2025-02-12"], "usd_cad": [1]}))

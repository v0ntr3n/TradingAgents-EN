"""
Shared document indicator processing functions
- add_financial_metrics: Append daily underlying metrics (market cap/valuation/transactions) to document
"""
from typing import Dict


def add_financial_metrics(doc: Dict, daily_metrics: Dict) -> None:
    """
    Write financial and trading indicators to doc (modify in place).
    - Market value: total_mv/circ_mv (converted from 10,000 yuan to 100 million yuan)
    - Valuation: pe/pb/pe_ttm/pb_mrq/ps/ps_ttm (filter NaN/None)
    - Transaction: turnover_rate/volume_ratio (filter NaN/None)
    - Equity: total_share/float_share (10,000 shares, filter NaN/None)
    - Dividends:dv_ratio/dv_ttm -> dividend_yield/dividend_yield_ttm (Filter NaN/None)
    """
    # Market value (10,000 yuan -> billion)
    if "total_mv" in daily_metrics and daily_metrics["total_mv"] is not None:
        doc["total_mv"] = daily_metrics["total_mv"] / 10000
    if "circ_mv" in daily_metrics and daily_metrics["circ_mv"] is not None:
        doc["circ_mv"] = daily_metrics["circ_mv"] / 10000

    # Valuation indicators (🔥 New ps and ps_ttm)
    for field in ["pe", "pb", "pe_ttm", "pb_mrq", "ps", "ps_ttm"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    # trading indicators
    for field in ["turnover_rate", "volume_ratio"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    # 🔥 Equity data (10,000 shares)
    for field in ["total_share", "float_share"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    for source_field, target_field in {"dv_ratio": "dividend_yield", "dv_ttm": "dividend_yield_ttm"}.items():
        if source_field in daily_metrics and daily_metrics[source_field] is not None:
            try:
                value = float(daily_metrics[source_field])
                if not (value != value):  # filter NaN
                    doc[target_field] = value
            except (ValueError, TypeError):
                pass


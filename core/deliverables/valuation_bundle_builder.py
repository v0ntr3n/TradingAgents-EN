"""Valuation calculation bundle automatic assembly (A10-D2)

Assemble the bundles required for generate_valuation_spec from the local sync database, with data all coming from existing helpers:

- Current price: core.tools.external.local_data.get_latest_stock_price(market_quotes → basic_info fallback)
- Stock name:core.tools.external.local_data.get_stock_basic_info
- Financial history (annual revenue/net profit attributable to parent company):
  core.skill_runtime.standard_financial_apis.get_historical_financial_annual_series
   (records The unit is yuan, converted here to 100 million yuan)
- Total share capital (100 million shares):
  1) stock_basic_info.total_share / total_shares (Field contract unit: 10,000 shares)
  2) The bottom line: the latest annual report balance_sheet.total_share (the measured unit of the synchronization link is the share, and the magnitude judgment is made)

The iron law of data traceability: when any required data is not synchronized, a ValuationDataError is thrown and the missing item is clearly stated.
Estimated fill is prohibited.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.skill_runtime.standard_financial_apis import (
    get_historical_financial_annual_series,
    get_stock_financial_periods,
)
from core.tools.external.local_data import get_latest_stock_price, get_stock_basic_info

logger = logging.getLogger(__name__)

# Number of historical periods of annual reports (at least 2 periods are required to render the growth formula)
_MIN_HISTORY = 2
_MAX_HISTORY = 3


class ValuationDataError(Exception):
    """The necessary data for valuation calculation is not synchronized (blocking generation, data synchronization is required first)"""


def _normalize_symbol(symbol: str) -> str:
    s = str(symbol or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) != 6:
        raise ValuationDataError(f"The stock code is illegal:{symbol!r} (Requires 6-digit code)")
    return digits.zfill(6)


def _shares_to_yi(raw: float, source: str) -> Tuple[float, Optional[str]]:
    """Convert the original equity value into 100 million shares and return (100 million shares, Explanation of magnitude judgment or None)"""
    if raw >= 1e8:
        # Unit is share
        return raw / 1e8, None
    # The unit is 10,000 shares (field contract caliber)
    return raw / 1e4, f"Source of equity {source} numerical value {raw} Converted based on 10,000 shares"


def _resolve_share_count_yi(symbol: str, basic_info: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Analysis of total share capital (100 million shares): basic_info 10,000 shares contract → Latest annual report balance_sheet full details"""
    notes: List[str] = []
    raw = basic_info.get("total_share") or basic_info.get("total_shares")
    if isinstance(raw, (int, float)) and raw > 0:
        yi, note = _shares_to_yi(float(raw), "stock_basic_info.total_share")
        if note:
            notes.append(note)
        return yi, notes

    # The bottom line: the latest annual report balance_sheet.total_share (the measured unit of the synchronization link is shares)
    try:
        periods = get_stock_financial_periods(symbol, limit=8)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ValuationBundle] Failed to query financial period (equity fund is not available): %s", exc)
        periods = []
    annual = [p for p in periods if str(p.get("report_period") or "").endswith("1231")]
    if annual:
        latest = annual[0]
        bs = latest.get("balance_sheet") or {}
        raw_bs = bs.get("total_share") or bs.get("total_shares")
        if isinstance(raw_bs, (int, float)) and raw_bs > 0:
            yi, note = _shares_to_yi(
                float(raw_bs), f"annual report{latest.get('report_period')} balance_sheet.total_share"
            )
            if note:
                notes.append(note)
            notes.append(f"Total share capital is taken from the latest annual report {latest.get('report_period')}, May be later than current share capital changes")
            return yi, notes

    raise ValuationDataError(
        "The total share capital data is not synchronized (stock_basic_info and annual report balance_sheet have no total_share),"
        "Please synchronize the basic information data of the stock first and try again."
    )


def _build_financial_history(symbol: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Construct the financial history of the annual report (ascending order, billion yuan), discard when the data is insufficient ValuationDataError"""
    notes: List[str] = []
    try:
        result = get_historical_financial_annual_series(symbol, years=_MAX_HISTORY)
    except Exception as exc:  # noqa: BLE001
        raise ValuationDataError(f"Failed to obtain annual report financial data:{exc}") from exc

    records = result.get("records") or []
    history: List[Dict[str, Any]] = []
    for rec in records:  # records Sort by year in descending order, reverse to ascending order (old → new)
        revenue, net_profit = rec.get("revenue"), rec.get("net_profit")
        if not isinstance(revenue, (int, float)) or revenue <= 0:
            continue
        if not isinstance(net_profit, (int, float)) or net_profit <= 0:
            continue
        history.append(
            {
                "period": str(rec.get("year") or rec.get("report_period") or ""),
                "revenue": round(float(revenue) / 1e8, 4),  # Yuan → billion
                "net_profit": round(float(net_profit) / 1e8, 4),
            }
        )
    history.reverse()

    if len(history) < _MIN_HISTORY:
        raise ValuationDataError(
            f"Insufficient annual report data (valid annual report {len(history)} period, at least {_MIN_HISTORY} period),"
            "Please synchronize the financial data of the stock first and try again."
        )
    notes.append(
        f"Financial history to the most recent {len(history)} Annual report (latest {history[-1]['period']}) , Unit conversion: Yuan → billion"
    )
    return history, notes


def build_valuation_bundle(
    symbol: str,
    context_notes: str = "",
    forecast_years: int = 2,
) -> Dict[str, Any]:
    """Assembly valuation calculation bundle (all data comes from the local synchronization library, if missing, an error will be reported)

    Returns:
        bundle dict：ticker / stock_name / analysis_date / current_price /
        share_count (100 million shares)/financial_history (ascending order, 100 million yuan)/
        investment_plan (context_notes, Injected as a comprehensive research conclusion)/
        data_notes (Data caliber description for results disclosure)

    Raises:
        ValuationDataError: Required data is not synced
    """
    from datetime import datetime

    sym = _normalize_symbol(symbol)
    notes: List[str] = []

    basic_info = get_stock_basic_info(sym) or {}
    stock_name = str(basic_info.get("name") or basic_info.get("stock_name") or "").strip()
    if not stock_name:
        raise ValuationDataError(f"No stock found {sym} Basic information, please perform data synchronization first")

    current_price = get_latest_stock_price(sym)
    if not current_price or current_price <= 0:
        raise ValuationDataError(
            f"stocks {sym} ({stock_name}) The latest market data is not synchronized and the current price cannot be determined. Please synchronize the market data first."
        )

    share_count_yi, share_notes = _resolve_share_count_yi(sym, basic_info)
    notes.extend(share_notes)

    history, history_notes = _build_financial_history(sym)
    notes.extend(history_notes)

    forecast_years = max(1, min(int(forecast_years or 2), 3))
    context = ""
    if str(context_notes or "").strip():
        context = (
            f"Users hope to have a better understanding of the future based on the following research conclusions {forecast_years} Annual profit deduction and valuation calculation:\n"
            f"{str(context_notes).strip()}"
        )
    else:
        context = f"Users hope for the future {forecast_years} Profit deductions and valuation calculations are conducted every year, and assumptions are made by you based on historical financial data."

    bundle: Dict[str, Any] = {
        "ticker": sym,
        "stock_name": stock_name,
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "current_price": float(current_price),
        "share_count": round(share_count_yi, 4),
        "financial_history": history,
        "investment_plan": context,
        "data_notes": notes,
    }
    logger.info(
        "[ValuationBundle] %s (%s) Assembly completed: price=%s, shares=%.2f 100 million shares, history=%s",
        stock_name, sym, current_price, share_count_yi,
        [h["period"] for h in history],
    )
    return bundle

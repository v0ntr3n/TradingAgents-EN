"""Event study method tool.

Perform statistical analysis on the abnormal returns of specified stocks before and after the event date.
Calculate abnormal returns using the Mean-Adjusted Return Model.
"""

import datetime
import json
import logging
from statistics import mean, stdev
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_daily_quotes
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric != numeric:
                return None
            return numeric
        except (TypeError, ValueError):
            return None
    try:
        numeric = float(str(value).strip())
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _parse_date(date_str: str) -> str:
    """Normalized dates are in YYYY-MM-DD format."""
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


def _to_dash_date(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, keeping the existing format unchanged."""
    if "-" in date_str:
        return date_str
    cleaned = "".join(ch for ch in date_str if ch.isdigit())[:8]
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return date_str


@tool
@register_tool(
    tool_id="get_event_study",
    name="事件研究法",
    description=(
        "Perform statistical analysis on the abnormal returns of specified stocks before and after the event date."
        "Calculate abnormal returns using the Mean-Adjusted Return Model(AR)and cumulative abnormal returns(CAR), "
        "and calculate the t statistic to test significance."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=["event", "event_study", "quantitative"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["事件驱动分析", "公告效应研究", "市场反应量化评估"],
    when_to_use=(
        "When it is necessary to quantitatively analyze an event (such as financial report release, major announcements, regulatory penalties, executive changes, etc.)"
        "Used when affecting stock prices. Suitable for event-driven strategy research."
    ),
    when_not_to_use=(
        "Not suitable for obtaining historical stock quotes itself (please use get_stock_daily_quotes);"
        "Not suitable for fundamental factor analysis. If you only need the rise and fall before and after the event, you can directly query the market price."
    ),
    returns=(
        "Returns a JSON string, including symbol, event_date, method,"
        "estimation (Estimated period statistics), event_window (daily AR/CAR details),"
        "summary (Total CAR, t-statistic, significance judgment), data_quality (data quality description)."
    ),
    example="get_event_study(symbol='600519', event_date='20251201', window_before=30, window_after=30, estimation_window=120)",
    related_tools=[
        "get_stock_daily_quotes",
        "get_income_analysis",
        "get_stock_news",
    ],
)
def get_event_study(
    symbol: Annotated[str, "A Stock stock code, 6 digits, such as 600519"],
    event_date: Annotated[str, "Event date in the format YYYYMMDD or YYYY-MM-DD"],
    window_before: Annotated[int, "The number of days forward in the event window (before the event), default 30"] = 30,
    window_after: Annotated[int, "The number of days back the event window (after the event), default 30"] = 30,
    estimation_window: Annotated[int, "Number of days in the estimation window, default 120"] = 120,
) -> str:
    """Event study analysis tool.

    Calculated using the Mean-Adjusted Return Model:
    - Estimation period: used to estimate normal income
    - Event Window: Calculating Abnormal Returns(AR)and cumulative abnormal returns(CAR)
    - Significance test: t statistic

    Args:
        symbol: A stock ticker code
        event_date: event date
        window_before: Event window number of days forward
        window_after: Event window number of days backward
        estimation_window: Estimated window number of days

    Returns:
        JSON Event research results in string format
    """
    try:
        symbol = str(symbol).strip().zfill(6)
        event = _parse_date(event_date)

        event_dt = datetime.datetime.strptime(event, "%Y-%m-%d")

        # Calculate date range
        estimation_start = event_dt - datetime.timedelta(days=estimation_window + window_before + 10)
        event_end = event_dt + datetime.timedelta(days=window_after + 10)

        start_str = estimation_start.strftime("%Y%m%d")
        end_str = event_end.strftime("%Y%m%d")

        # Get daily data
        quotes = get_stock_daily_quotes(symbol, start_str, end_str, period="daily", limit=5000)

        if not quotes:
            return json.dumps(
                {"status": "error", "message": f"未获取到 {symbol} 的日线数据"},
                ensure_ascii=False,
                default=str,
            )

        # Calculate daily return
        daily_returns: List[Dict[str, Any]] = []
        for q in quotes:
            trade_date = q.get("trade_date", "")
            trade_date_str = _to_dash_date(str(trade_date)) if trade_date else ""

            close = _to_float(q.get("close"))
            pre_close = _to_float(q.get("pre_close"))

            if close is not None and pre_close is not None and pre_close > 0:
                daily_return = (close - pre_close) / pre_close
            else:
                continue

            daily_returns.append({
                "date": trade_date_str,
                "return": daily_return,
            })

        if len(daily_returns) < estimation_window // 2:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"日线数据不足，仅获取到 {len(daily_returns)} 条有效交易记录，"
                    f"The estimation period needs to be at least {estimation_window // 2} Article",
                },
                ensure_ascii=False,
                default=str,
            )

        # Sort by date
        daily_returns.sort(key=lambda x: x["date"])

        # Convert date to datetime for comparison
        def _date_key(d: str) -> datetime.datetime:
            try:
                return datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return datetime.datetime.min

        event_dt_compare = _date_key(event)

        # Separate estimation periods and event windows
        estimation_returns: List[float] = []
        event_window_returns: List[Dict[str, Any]] = []

        for item in daily_returns:
            item_date = _date_key(item["date"])
            days_diff = (item_date - event_dt_compare).days

            # Estimated period:[event_date - estimation_window - window_before, event_date - window_before)
            est_start = -estimation_window - window_before
            est_end = -window_before

            if est_start <= days_diff < est_end:
                estimation_returns.append(item["return"])

            # Event window:[event_date - window_before, event_date + window_after]
            if -window_before <= days_diff <= window_after:
                event_window_returns.append({
                    "date": item["date"],
                    "days_from_event": days_diff,
                    "actual_return": item["return"],
                })

        if len(estimation_returns) < 10:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"估计期内有效收益数据不足，仅 {len(estimation_returns)} 条（需至少 10 条）",
                },
                ensure_ascii=False,
                default=str,
            )

        # mean adjusted return model
        mean_return = mean(estimation_returns)
        std_return = stdev(estimation_returns) if len(estimation_returns) > 1 else 0.0

        # Compute the AR sum within the event window CAR
        ar_values: List[float] = []
        car = 0.0
        event_results: List[Dict[str, Any]] = []

        for item in event_window_returns:
            ar = item["actual_return"] - mean_return
            ar_values.append(ar)
            car += ar

            event_results.append({
                "date": item["date"],
                "days_from_event": item["days_from_event"],
                "actual_return": round(item["actual_return"], 6),
                "expected_return": round(mean_return, 6),
                "ar": round(ar, 6),
                "car": round(car, 6),
            })

        # t Statistical test:H0: CAR = 0
        n = len(ar_values)
        if n > 1 and std_return > 0:
            # Approximate using the standard deviation of the estimation period
            t_stat = car / (std_return * (n ** 0.5)) if n > 0 else 0.0
        else:
            t_stat = 0.0

        # Critical value approximation (two-tailed test, 5% significance level)
        significant = abs(t_stat) > 1.96

        summary = {
            "car_total": round(car, 6),
            "t_stat": round(t_stat, 4),
            "significant": significant,
            "interpretation": (
                "Events generate statistically significant abnormal returns"
                if significant
                else "事件未产生显著异常收益"
            ),
        }

        payload = {
            "symbol": symbol,
            "event_date": event,
            "method": "mean_adjusted_return",
            "estimation": {
                "window_days": len(estimation_returns),
                "mean_return": round(mean_return, 6),
                "std": round(std_return, 6),
            },
            "event_window": event_results,
            "summary": summary,
            "data_quality": {
                "total_quotes_fetched": len(quotes),
                "valid_return_days": len(daily_returns),
                "estimation_days_used": len(estimation_returns),
                "event_window_days_used": len(event_results),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Event study analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_event_study"]

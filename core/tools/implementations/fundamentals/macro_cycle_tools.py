"""Economic cycle positioning, monetary environment analysis and industry rotation signal tools."""

import datetime
import json
import logging
from statistics import median
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _get_db():
    """Get a synchronous MongoDB connection."""
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
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
        text = str(value).strip()
        if not text:
            return None
        numeric = float(text)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _fetch_zh_us_rate() -> dict:
    """Get the latest data comparing U.S. and Chinese yields with AKShare."""
    try:
        import akshare as ak

        df = ak.bond_zh_us_rate()
        df["日期"] = pd.to_datetime(df["日期"])
        latest = df.sort_values("日期").iloc[-1]
        result: dict = {
            "date": str(latest["日期"].date()),
            "china": {},
            "us": {},
            "spread_cn": {},
            "history": [],
        }
        cn_cols = {
            "中国国债收益率2年": "2年",
            "中国国债收益率5年": "5年",
            "中国国债收益率10年": "10年",
            "中国国债收益率30年": "30年",
        }
        us_cols = {
            "美国国债收益率2年": "2年",
            "美国国债收益率5年": "5年",
            "美国国债收益率10年": "10年",
            "美国国债收益率30年": "30年",
        }
        for raw, name in cn_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["china"][name] = round(float(v), 4)
        for raw, name in us_cols.items():
            v = latest.get(raw)
            if v is not None and v == v:
                result["us"][name] = round(float(v), 4)
        spread = latest.get("中国国债收益率10年-2年")
        if spread is not None and spread == spread:
            result["spread_cn"]["10Y-2Y"] = round(float(spread), 4)

        # Take the past 3 months of historical records for trend calculations
        three_months_ago = latest["日期"] - pd.DateOffset(months=3)
        hist = df[df["日期"] >= three_months_ago].sort_values("日期")
        hist_records = []
        for _, row in hist.iterrows():
            rec = {"date": str(row["日期"].date())}
            for raw, name in cn_cols.items():
                v = row.get(raw)
                if v is not None and v == v:
                    rec[f"china_{name}"] = round(float(v), 4)
            for raw, name in us_cols.items():
                v = row.get(raw)
                if v is not None and v == v:
                    rec[f"us_{name}"] = round(float(v), 4)
            hist_records.append(rec)
        result["history"] = hist_records

        return result
    except Exception as e:
        logger.warning("AKShare Failed to obtain Sino-US yield: %s", e)
        return {"status": "error", "message": str(e)}


def _fetch_csi300_daily(days: int = 90) -> dict:
    """Get CSI 300-day data through AKShare."""
    try:
        import akshare as ak

        df = ak.stock_zh_index_daily("sh000300")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        # Get the last N days
        cutoff = df["date"].max() - pd.Timedelta(days=days)
        df = df[df["date"] >= cutoff].copy()
        if df.empty:
            return {"status": "no_data", "message": "沪深300数据为空"}
        records = []
        for _, row in df.iterrows():
            records.append({
                "date": str(row["date"].date()),
                "close": round(float(row["close"]), 2),
            })
        return {
            "status": "ok",
            "latest_date": str(df["date"].max().date()),
            "latest_close": round(float(df["close"].iloc[-1]), 2),
            "records": records,
        }
    except Exception as e:
        logger.warning("AKShare Failed to obtain CSI 300: %s", e)
        return {"status": "error", "message": str(e)}


def _compute_merrill_lynch_clock(
    market_return_3m: float,
    yield_change_3m: float,
) -> dict:
    """Mapping the four quadrants of the Merrill Lynch Clock based on market returns and yield changes.

    Args:
        market_return_3m: CSI 300 return rate in the past 3 months (%)
        yield_change_3m: Changes in China s 10Y yield in the past three months (percentage points)

    Returns:
        Dictionary containing quadrants, recommended assets, signal descriptions
    """
    growth_direction = (
        "high"
        if market_return_3m > 5.0
        else ("low" if market_return_3m < -5.0 else "neutral")
    )
    inflation_direction = (
        "rising"
        if yield_change_3m > 0.2
        else ("falling" if yield_change_3m < -0.2 else "stable")
    )

    # Merrill Lynch Clock Map
    if growth_direction == "high" and inflation_direction == "rising":
        quadrant = "过热"
        recommended_asset = "商品"
        signal_desc = "Economic growth is strong and inflation is rising, making it suitable for allocating commodities and cyclical assets."
    elif growth_direction == "low" and inflation_direction == "rising":
        quadrant = "滞涨"
        recommended_asset = "现金"
        signal_desc = "Economic growth is slowing but inflation is high. Cash is king and defense is the priority."
    elif growth_direction == "low" and inflation_direction == "falling":
        quadrant = "衰退"
        recommended_asset = "债券"
        signal_desc = "The economy contracts, inflation falls, and bonds perform best during periods of falling interest rates."
    elif growth_direction == "high" and inflation_direction == "falling":
        quadrant = "复苏"
        recommended_asset = "股票"
        signal_desc = "The economy resumes growth, inflation is moderate, and equity assets benefit from improved corporate profits."
    else:
        # neutral zone
        quadrant = "过渡/模糊"
        recommended_asset = "均衡配置"
        signal_desc = "The signal is unclear. It is recommended to have a balanced allocation of stocks and bonds."

    return {
        "quadrant": quadrant,
        "recommended_asset_class": recommended_asset,
        "signal_description": signal_desc,
    }


@tool
@register_tool(
    tool_id="get_economic_cycle_position",
    name="经济周期定位",
    description=(
        "Based on the Merrill Lynch clock framework, through the Shanghai and Shenzhen 300 return rate in the past three months (as a growth proxy indicator) and"
        "Changes in China s 10-year government bond yield in the past three months (as a proxy indicator of inflation),"
        "Automatically locate the quadrant of the current economic cycle (recovery/overheating/stagflation/recession),"
        "And give the corresponding recommended asset allocation direction."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "economic_cycle", "asset_allocation"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["经济周期位置判断", "美林时钟分析", "宏观资产配置参考"],
    when_to_use=(
        "When users ask what cycle stage the current economy is in and which quadrant the Merrill Lynch clock points to,"
        "Should be used when allocating stocks/bonds/commodities/cash. Real-time macro data support is required."
    ),
    when_not_to_use=(
        "Not suitable for inquiries about investment advice on specific industries or individual stocks;"
        "Not suitable as a substitute for detailed macro research reports;"
        "Use get_yield_curve_analysis when you only need Treasury yield data."
    ),
    returns=(
        "Returns a JSON string, including cycle_position (cycle phase positioning),"
        "gdp_proxy (Shanghai and Shenzhen 300 yields in the past three months), inflation_proxy (changes in government bond yields),"
        "quadrant (Merrill Lynch Clock Quadrant), recommended_asset_class (recommended asset class),"
        "data_quality (Data quality description) and other fields."
    ),
    example="get_economic_cycle_position()",
    related_tools=["get_yield_curve_analysis", "get_monetary_environment", "get_macro_dashboard"],
)
def get_economic_cycle_position() -> str:
    """Get Business Cycle Positioning (Merrill Lynch Clock) analysis.

    Obtain real-time CSI 300 Index yield and treasury bond yield data through AKShare,
    Use the simplified Merrill Lynch Clock Framework to determine the current cycle position and recommended asset allocation.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            cycle_position: dict Cycle positioning——
                — quadrant: Merrill Lynch Clock Quadrant
                — recommended_asset_class: Recommended asset classes
                — signal_description: Signal description
            gdp_proxy: dict Growth proxy indicator (CSI 300 return rate in the past 3 months)——
                — label: Indicator label
                — value_pct: Yield (%)
                — direction: direction: "high growth" | "low growth" | "Neutral"
                — threshold_note: Threshold description
            inflation_proxy: dict Inflation proxy indicator (10Y Treasury bond yield changes in the past three months)——
                — label: Indicator label
                — value_change: Yield changes
                — direction: direction: "rise" | "fall" | "Smooth"
                — threshold_note: Threshold description
            current_data: dict current data——
                — csi300_latest_close: CSI 300 latest closing price
                — csi300_latest_date: CSI 300 latest date
                — china_10y_yield: China 10-year yield
                — china_10y_3m_ago: 3 China s 10-year yield months ago
                — us_10y_yield: US 10-year yield
                — cn_us_spread_10y: China-U.S. 10-year interest rate spread
            data_quality: dict Data quality——
                — has_csi300_data: Is there CSI 300 data?
                — has_yield_history: Is there a rate of return history?
                — yield_history_days: Historical data days
                — note: Description text
            message: Error message (only status="error" exist)
    """
    try:
        # 1. Obtain Sino-US yield data (including recent 3-month history)
        rate_data = _fetch_zh_us_rate()
        if "status" in rate_data and rate_data["status"] == "error":
            return json.dumps({
                "status": "error",
                "message": f"收益率数据获取失败: {rate_data.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        # 2. Get Shanghai and Shenzhen 300-day line data
        csi300 = _fetch_csi300_daily(days=120)  # Take more and make sure you have 3 months of data
        if csi300.get("status") != "ok":
            return json.dumps({
                "status": "error",
                "message": f"沪深300数据获取失败: {csi300.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        # 3. Calculate the CSI 300 return rate in the past 3 months
        records = csi300.get("records", [])
        if len(records) < 2:
            return json.dumps({
                "status": "error",
                "message": "Insufficient data on the CSI 300 makes it impossible to calculate the rate of return",
            }, ensure_ascii=False, indent=2, default=str)

        latest_close = records[-1]["close"]
        # Find the closing price approximately 90 days ago
        target_date = datetime.datetime.strptime(records[-1]["date"], "%Y-%m-%d") - datetime.timedelta(days=90)
        three_month_ago = None
        for rec in records:
            rec_date = datetime.datetime.strptime(rec["date"], "%Y-%m-%d")
            if rec_date >= target_date:
                three_month_ago = rec["close"]
                break
        if three_month_ago is None:
            three_month_ago = records[0]["close"]

        market_return_3m = round((latest_close - three_month_ago) / three_month_ago * 100, 2)

        # 4. Calculate the changes in China's 10Y yield in the past three months
        history = rate_data.get("history", [])
        china_10y_now = rate_data.get("china", {}).get("10年")
        if china_10y_now is None:
            return json.dumps({
                "status": "error",
                "message": "Missing data on China s 10-year government bond yield",
            }, ensure_ascii=False, indent=2, default=str)

        # Find the 10Y return rate approximately 90 days ago
        china_10y_3m_ago = None
        if history:
            target_dt = datetime.datetime.strptime(rate_data["date"], "%Y-%m-%d") - datetime.timedelta(days=90)
            for hrec in history:
                hrec_date = datetime.datetime.strptime(hrec["date"], "%Y-%m-%d")
                if hrec_date >= target_dt:
                    china_10y_3m_ago = hrec.get("china_10年")
                    break
            if china_10y_3m_ago is None and len(history) > 0:
                china_10y_3m_ago = history[0].get("china_10年")

        if china_10y_3m_ago is not None:
            yield_change_3m = round(china_10y_now - china_10y_3m_ago, 4)
        else:
            yield_change_3m = 0.0

        # 5. Merrill Lynch Clock Positioning
        clock = _compute_merrill_lynch_clock(market_return_3m, yield_change_3m)

        # 6. Build results
        today = datetime.date.today()
        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": (
                "The CSI 300 yield rate comes from akshare.stock_zh_index_daily('sh000300'), "
                "Treasury bond yields come from akshare.bond_zh_us_rate()"
            ),
            "cycle_position": {
                "quadrant": clock["quadrant"],
                "recommended_asset_class": clock["recommended_asset_class"],
                "signal_description": clock["signal_description"],
            },
            "gdp_proxy": {
                "label": "Growth proxy indicator - CSI 300 return rate in the past three months",
                "value_pct": market_return_3m,
                "direction": "高增长" if market_return_3m > 5 else ("低增长" if market_return_3m < -5 else "中性"),
                "threshold_note": ">5%For high growth,<-5%for low growth",
            },
            "inflation_proxy": {
                "label": "Inflation proxy indicator - China s 10Y government bond yield changes in the past three months",
                "value_change": yield_change_3m,
                "direction": "上升" if yield_change_3m > 0.2 else ("下降" if yield_change_3m < -0.2 else "平稳"),
                "threshold_note": ">0.2%As inflation rises,<-0.2%for inflation to fall",
            },
            "current_data": {
                "csi300_latest_close": csi300["latest_close"],
                "csi300_latest_date": csi300["latest_date"],
                "china_10y_yield": china_10y_now,
                "china_10y_3m_ago": china_10y_3m_ago,
                "us_10y_yield": rate_data.get("us", {}).get("10年"),
                "cn_us_spread_10y": (
                    round(china_10y_now - rate_data["us"]["10年"], 4)
                    if rate_data.get("us", {}).get("10年") is not None
                    else None
                ),
            },
            "data_quality": {
                "has_csi300_data": len(records) > 1,
                "has_yield_history": len(history) > 1,
                "yield_history_days": len(history),
                "note": (
                    "This tool uses a simplified Merrill Lynch clock model, using the CSI 300 yield rate as a proxy for the direction of economic growth,"
                    "10Y Changes in Treasury yields proxy for the direction of inflation. The actual cycle judgment needs to be combined with formal macro indicators such as CPI, GDP, and PMI."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("经济周期定位失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


@tool
@register_tool(
    tool_id="get_monetary_environment",
    name="货币环境分析",
    description=(
        "Real-time analysis of the current currency/interest rate environment, based on China and US 10-year Treasury bond yield data,"
        "Including assessment of yield levels (low/medium/high), trend direction in the past 1 month and 3 months,"
        "Comparison of interest rate differentials between China and the United States, and judgment of monetary policy stance (easing/neutral/tightening)."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "monetary_policy", "interest_rate"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["货币环境评估", "利率走势分析", "中美利差查询"],
    when_to_use=(
        "When a user asks whether the current monetary policy is loose or tight, what level the interest rate is,"
        "Used when looking at trends in Sino-US interest rate spreads and Treasury bond yields."
    ),
    when_not_to_use=(
        "Not suitable for querying specific LPR/MLF operating interest rates (official data from the central bank is required);"
        "Not suitable for querying monetary policy tools such as deposit reserve ratio;"
        "It is not suitable for querying historical long-term series of return data."
    ),
    returns=(
        "Returns a JSON string containing interest_rate_environment (interest rate level/trend assessment),"
        "china_10y_yield (China 10Y yield and changes), us_10y_yield (US 10Y yield and changes),"
        "spread_trend (Sino-US interest rate spread trend), monetary_stance (monetary policy stance judgment),"
        "available_data_sources (Data source description) and other fields."
    ),
    example="get_monetary_environment()",
    related_tools=["get_yield_curve_analysis", "get_economic_cycle_position", "get_macro_dashboard"],
)
def get_monetary_environment() -> str:
    """Get an analysis of the currency environment.

    Obtain Sino-US bond yield data through AKShare and analyze interest rate levels, trends,
    Spreads and policy stances.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            interest_rate_environment: dict interest rate environment——
                — china_10y_level: interest rate level: "low position" | "Neutral" | "high position" | "unknown"
                — china_10y_level_detail: Level details
                — trend_1m: dict Trends in the past month——
                    — change_bps: Change (basis points)
                    — direction: direction: "rise" | "fall" | "Smooth" | "unknown"
                — trend_3m: dict Trend in the past three months (the structure is the same as trend_1m)
            china_10y_yield: dict China 10-year yield——
                — current: current value
                — 1m_ago: 1 months ago
                — 3m_ago: 3 months ago
            us_10y_yield: dict US 10-year yield——
                — current: current value
            spread_trend: dict Interest rate spread trend between China and the United States——
                — cn_us_10y_spread: China-U.S. 10-year interest rate spread
                — note: Description text
            monetary_stance: dict monetary policy stance——
                — stance: stance: "Loose" | "Neutral" | "austerity" | "unknown"
                — description: Position description
                — basis: Judgment basis
            available_data_sources: dict Available data sources——
                — current_data: Current data source
                — not_included: list[str] List of data sources not included
            data_quality: dict Data quality——
                — has_full_history: Is there a complete history?
                — has_china_10y: Is there any China 10Y data?
                — has_us_10y: Is there US 10Y data?
                — history_points: historical data points
            message: Error message (only status="error" exist)
    """
    try:
        rate_data = _fetch_zh_us_rate()
        if "status" in rate_data and rate_data["status"] == "error":
            return json.dumps({
                "status": "error",
                "message": f"收益率数据获取失败: {rate_data.get('message')}",
            }, ensure_ascii=False, indent=2, default=str)

        today = datetime.date.today()
        china_10y = rate_data.get("china", {}).get("10年")
        us_10y = rate_data.get("us", {}).get("10年")
        history = rate_data.get("history", [])

        # Judgment of interest rate levels (China 10Y historical reference:<2.5%Lower, 2.5%-3.5% neutral,>3.5%higher)
        if china_10y is not None:
            if china_10y < 2.5:
                rate_level = "低位"
                rate_level_note = "China s 10Y government bond yield is below 2.5%, at a historically low range"
            elif china_10y > 3.5:
                rate_level = "高位"
                rate_level_note = "The yield on China s 10Y government bonds is higher than 3.5%, which is at a historically high range"
            else:
                rate_level = "中性"
                rate_level_note = "China s 10Y government bond yield is between 2.5% and 3.5%, which is in the neutral range"
        else:
            rate_level = "未知"
            rate_level_note = "Missing data on China s 10Y government bond yield"

        # Trend calculation (last month and last 3 months)
        trend_1m = None
        trend_3m = None
        china_10y_1m_ago = None
        china_10y_3m_ago = None

        if history and china_10y is not None:
            current_date = datetime.datetime.strptime(rate_data["date"], "%Y-%m-%d")
            target_1m = current_date - datetime.timedelta(days=30)
            target_3m = current_date - datetime.timedelta(days=90)

            for hrec in history:
                hrec_date = datetime.datetime.strptime(hrec["date"], "%Y-%m-%d")
                if china_10y_1m_ago is None and hrec_date >= target_1m:
                    china_10y_1m_ago = hrec.get("china_10年")
                if china_10y_3m_ago is None and hrec_date >= target_3m:
                    china_10y_3m_ago = hrec.get("china_10年")

            if china_10y_1m_ago is None and len(history) > 0:
                china_10y_1m_ago = history[0].get("china_10年")
            if china_10y_3m_ago is None and len(history) > 0:
                china_10y_3m_ago = history[0].get("china_10年")

        if china_10y is not None and china_10y_1m_ago is not None:
            trend_1m = round(china_10y - china_10y_1m_ago, 4)
        if china_10y is not None and china_10y_3m_ago is not None:
            trend_3m = round(china_10y - china_10y_3m_ago, 4)

        def trend_label(chg):
            if chg is None:
                return "未知"
            if chg > 0.1:
                return "上升"
            if chg < -0.1:
                return "下降"
            return "平稳"

        # Interest rate spread between China and the United States
        cn_us_spread = None
        if china_10y is not None and us_10y is not None:
            cn_us_spread = round(china_10y - us_10y, 4)

        # Comprehensive judgment on monetary policy stance
        if china_10y is not None:
            if china_10y < 2.0 or (trend_3m is not None and trend_3m < -0.3):
                monetary_stance = "宽松"
                stance_desc = "Interest rates are at low levels and continue to decline, and monetary policy is loose"
            elif china_10y > 3.5 or (trend_3m is not None and trend_3m > 0.3):
                monetary_stance = "紧缩"
                stance_desc = "Interest rates are at a high level and continue to rise, and monetary policy is tightening"
            else:
                monetary_stance = "中性"
                stance_desc = "Interest rates are at a medium level, with little fluctuation, and monetary policy is neutral."
        else:
            monetary_stance = "未知"
            stance_desc = "数据不足无法判断"

        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": "akshare.bond_zh_us_rate()",
            "interest_rate_environment": {
                "china_10y_level": rate_level,
                "china_10y_level_detail": rate_level_note,
                "trend_1m": {
                    "change_bps": round(trend_1m * 100, 2) if trend_1m is not None else None,
                    "direction": trend_label(trend_1m),
                },
                "trend_3m": {
                    "change_bps": round(trend_3m * 100, 2) if trend_3m is not None else None,
                    "direction": trend_label(trend_3m),
                },
            },
            "china_10y_yield": {
                "current": china_10y,
                "1m_ago": china_10y_1m_ago,
                "3m_ago": china_10y_3m_ago,
            },
            "us_10y_yield": {
                "current": us_10y,
            },
            "spread_trend": {
                "cn_us_10y_spread": cn_us_spread,
                "note": (
                    "A positive value indicates that China s yield is higher than that of the United States, and a negative value indicates that China s yield is lower than that of the United States."
                    if cn_us_spread is not None else "数据不足"
                ),
            },
            "monetary_stance": {
                "stance": monetary_stance,
                "description": stance_desc,
                "basis": (
                    "Judgment based on the absolute level of 10Y Treasury bond yields and the trend in the past three months,"
                    "The actual monetary policy stance needs to be comprehensively evaluated based on the central bank s open market operations, LPR, MLF interest rates, etc."
                ),
            },
            "available_data_sources": {
                "current_data": "akshare.bond_zh_us_rate()",
                "not_included": [
                    "LPR (Loan market quoted interest rate) - need to be obtained from the central bank s official website or Oriental Wealth",
                    "MLF (Medium-term lending facility) interest rate - need to be obtained from the central bank s official website",
                    "Deposit reserve ratio - need to be obtained from the central bank s official website",
                    "SHIBOR - Available via akshare",
                ],
            },
            "data_quality": {
                "has_full_history": len(history) > 1,
                "has_china_10y": china_10y is not None,
                "has_us_10y": us_10y is not None,
                "history_points": len(history),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("货币环境分析失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


def _get_industry_sector_snapshot() -> dict:
    """Get a snapshot of valuations by industry from stock_basic_info."""
    db = _get_db()
    col = db["stock_basic_info"]

    all_stocks = list(col.find({}, {
        "_id": 0,
        "symbol": 1,
        "name": 1,
        "industry": 1,
        "pe_ttm": 1,
        "pb": 1,
        "pb_mrq": 1,
        "total_mv": 1,
    }))

    # Group by industry
    industry_groups: Dict[str, Dict[str, Any]] = {}
    all_pe: List[float] = []
    all_pb: List[float] = []

    for stock in all_stocks:
        if not stock.get("symbol"):
            continue
        industry = (stock.get("industry") or "未知").strip()

        pe = _safe_float(stock.get("pe_ttm"))
        if pe is not None and 0 < pe < 1000:
            all_pe.append(pe)

        pb_raw = _safe_float(stock.get("pb") or stock.get("pb_mrq"))
        if pb_raw is not None and 0 < pb_raw < 100:
            all_pb.append(pb_raw)

        if industry not in industry_groups:
            industry_groups[industry] = {"count": 0, "pe_list": [], "pb_list": [], "total_mv": 0.0}
        industry_groups[industry]["count"] += 1
        if pe is not None and 0 < pe < 1000:
            industry_groups[industry]["pe_list"].append(pe)
        if pb_raw is not None and 0 < pb_raw < 100:
            industry_groups[industry]["pb_list"].append(pb_raw)
        mv = _safe_float(stock.get("total_mv"))
        if mv is not None:
            industry_groups[industry]["total_mv"] += mv

    # Market-wide median
    market_pe_median = round(median(all_pe), 2) if all_pe else None
    market_pb_median = round(median(all_pb), 2) if all_pb else None

    # Calculate the relative strength of each industry
    sector_results = []
    for industry, data in industry_groups.items():
        pe_med = round(median(data["pe_list"]), 2) if data["pe_list"] else None
        pb_med = round(median(data["pb_list"]), 2) if data["pb_list"] else None

        # Relative strength: The lower the PE is than the market median, the better"value", The higher the"grow"
        relative_strength = 0.0
        if pe_med is not None and market_pe_median is not None and market_pe_median > 0:
            # Negative values indicate relative undervaluation (value type), positive values indicate relative overvaluation (growth type).
            relative_strength = round((market_pe_median - pe_med) / market_pe_median, 4)

        sector_results.append({
            "industry": industry,
            "stock_count": data["count"],
            "pe_median": pe_med,
            "pb_median": pb_med,
            "total_mv_billion": round(data["total_mv"], 2),
            "relative_strength": relative_strength,
            "relative_valuation": (
                "价值" if relative_strength > 0.2
                else ("成长" if relative_strength < -0.2 else "中性")
            ),
        })

    # Sort by relative strength (value first)
    sector_results.sort(key=lambda x: x["relative_strength"], reverse=True)

    return {
        "market_pe_median": market_pe_median,
        "market_pb_median": market_pb_median,
        "total_industries": len(sector_results),
        "total_stocks_tracked": len(all_stocks),
        "sectors": sector_results,
    }


@tool
@register_tool(
    tool_id="get_sector_rotation_signals",
    name="行业轮动信号",
    description=(
        "Industry valuation data and real-time macro cycle signals based on the local database stock_basic_info,"
        "Analyze the relative valuation strength of each industry (PE/PB vs market median),"
        "Identify the current industry rotation stage (value-led/growth-led/defensive rotation/balanced),"
        "And gives ranking suggestions for defensive, cyclical and growth sectors."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["macro", "sector_rotation", "industry_analysis"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["行业轮动分析", "板块排名查询", "行业配置建议"],
    when_to_use=(
        "When users ask which industry sectors are currently performing well and what stage of industry rotation they are in,"
        "Use it when configuring cyclical or defensive sectors and industry valuation rankings."
    ),
    when_not_to_use=(
        "Not suitable for querying the valuation or market conditions of specific stocks (please use get_value_factor_bundle_tool or get_stock_fundamentals_unified)."
        "Not suitable for querying the real-time rise and fall of sector indexes (please use get_sector_daily);"
        "Not suitable for querying the list of sector constituents (please use get_sector_constituents)."
    ),
    returns=(
        "Returns a JSON string, including current_cycle_position_data (current cycle data),"
        "sector_ranking (Industry list sorted by relative strength), rotation_phase (rotation phase judgment),"
        "top_defensive (Defensive sectors are recommended), top_cyclical (cyclical sectors are recommended),"
        "data_quality (Data quality description) and other fields."
    ),
    example="get_sector_rotation_signals()",
    related_tools=["get_economic_cycle_position", "get_monetary_environment", "get_macro_dashboard"],
)
def get_sector_rotation_signals() -> str:
    """Get industry rotation signal analysis.

    Combine local industry valuation data and real-time macro cycle signals to determine the industry rotation stage
    And give the relative strength ranking of each industry.

    Returns:
        str: JSON String, field description——
            status: Status: "ok" | "error"
            analysis_date: Analysis date (YYYY-MM-DD)
            data_source: Data source description
            current_cycle_position_data: dict Current period data (included when real-time data is not available cycle_phase="Unknown (live data is not available)") ——
                — market_return_3m: CSI 300 return rate in the past 3 months
                — china_10y_yield: China 10-year yield
                — cycle_phase: cycle phase: "recovery" | "overheating" | "stagflation" | "recession" | "Transition" | "unknown" | "Unknown (live data is not available)"
            rotation_phase: dict rotation phase——
                — phase: stage: "Growth leads the way" | "Cycle leads the rise" | "defensive rotation" | "Value leads the gains" | "balanced rotation"
                — description: Stage description
                — methodology: Methodological statement
            sector_ranking: list[dict] Industry ranking (top 30), element structure——
                — industry: Industry name
                — stock_count: Number of shares
                — pe_median: PE median
                — pb_median: PB median
                — total_mv_billion: Total market value (100 million yuan)
                — relative_strength: relative strength
                — relative_valuation: relative valuation: "value" | "grow" | "Neutral"
            market_valuation_context: dict market valuation context——
                — market_pe_median: Market PE median
                — market_pb_median: Market PB Median
                — total_industries: Total number of industries
                — total_stocks_tracked: Total number of stocks tracked
            top_defensive: list[dict] Recommend defensive sectors (the structure is the same as sector_ranking element)
            top_cyclical: list[dict] Recommended cyclical sectors (the structure is the same as sector_ranking element)
            data_quality: dict Data quality——
                — industry_count: Number of industries
                — defensive_found: Number of defensive tiles found
                — cyclical_found: Number of cyclical sectors found
                — cycle_data_available: Is there real-time cycle data?
                — note: Description text
            message: Error message (only status="error" exist)
    """
    try:
        today = datetime.date.today()

        # 1. Get a snapshot of industry valuations
        snapshot = _get_industry_sector_snapshot()
        sectors = snapshot.get("sectors", [])

        # 2. Try to obtain real-time periodic signals (non-blocking, failure will not affect industry data)
        cycle_info = None
        try:
            import akshare as ak

            rate_df = ak.bond_zh_us_rate()
            rate_df["日期"] = pd.to_datetime(rate_df["日期"])
            latest_rate = rate_df.sort_values("日期").iloc[-1]
            china_10y = _safe_float(latest_rate.get("中国国债收益率10年"))

            # CSI 300 return rate in the past 3 months
            idx_df = ak.stock_zh_index_daily("sh000300")
            idx_df["date"] = pd.to_datetime(idx_df["date"])
            idx_df = idx_df.sort_values("date")
            if len(idx_df) >= 2:
                latest_close = float(idx_df["close"].iloc[-1])
                three_m_ago = float(idx_df["close"].iloc[0])
                mkt_return = round((latest_close - three_m_ago) / three_m_ago * 100, 2)
            else:
                mkt_return = None

            # Simple cycle judgment
            if mkt_return is not None and china_10y is not None:
                if mkt_return > 5:
                    if china_10y > 3.0:
                        cycle_phase = "过热"
                    else:
                        cycle_phase = "复苏"
                elif mkt_return < -5:
                    if china_10y > 3.0:
                        cycle_phase = "滞涨"
                    else:
                        cycle_phase = "衰退"
                else:
                    cycle_phase = "过渡"
            else:
                cycle_phase = "未知"

            cycle_info = {
                "market_return_3m": mkt_return,
                "china_10y_yield": china_10y,
                "cycle_phase": cycle_phase,
            }
        except Exception as e:
            logger.debug("Failed to obtain cycle data, only industry valuation data is used: %s", e)
            cycle_info = {"cycle_phase": "未知（实时数据不可用）"}

        # 3. Determine the rotation stage
        # Identifying rotation stages based on industry valuation distribution characteristics
        top_value = [s for s in sectors[:10] if s.get("relative_valuation") == "价值"]
        top_growth = [s for s in sectors[-10:] if s.get("relative_valuation") == "成长"]
        defensive_industries = {"银行", "公用事业", "食品饮料", "医药生物", "交通运输", "保险"}
        cyclical_industries = {"有色金属", "钢铁", "煤炭", "基础化工", "建筑材料", "房地产", "机械设备"}

        value_score = len(top_value)  # Number of value sectors
        growth_score = len(top_growth)  # Number of growth sectors

        if cycle_info and isinstance(cycle_info, dict):
            cycle_phase = cycle_info.get("cycle_phase", "")
            if cycle_phase == "复苏":
                rotation_phase = "成长领涨"
                rotation_desc = "During economic recovery, growth and high-beta sectors usually outperform"
            elif cycle_phase == "过热":
                rotation_phase = "周期领涨"
                rotation_desc = "During periods of economic overheating, cyclical sectors (resources, raw materials) usually lead the way."
            elif cycle_phase == "滞涨":
                rotation_phase = "防御轮动"
                rotation_desc = "During stagflation, defensive sectors (utilities, pharmaceuticals, consumer staples) usually outperform"
            elif cycle_phase == "衰退":
                rotation_phase = "防御轮动"
                rotation_desc = "During recessions, defensive sectors and bond-related assets often outperform"
            else:
                # Inference based on valuation data
                if value_score > growth_score + 3:
                    rotation_phase = "价值领涨"
                    rotation_desc = "The relative strength of the value sector is outstanding, and the market favors low valuation defense"
                elif growth_score > value_score + 3:
                    rotation_phase = "成长领涨"
                    rotation_desc = "The relative strength of growth sectors is outstanding, and the market prefers high growth"
                else:
                    rotation_phase = "均衡轮动"
                    rotation_desc = "The relative strengths of value and growth sectors are close, and the market has no obvious preference."
        else:
            if value_score > growth_score + 3:
                rotation_phase = "价值领涨"
                rotation_desc = "The relative strength of the value sector is outstanding, and the market favors low valuation defense"
            elif growth_score > value_score + 3:
                rotation_phase = "成长领涨"
                rotation_desc = "The relative strength of growth sectors is outstanding, and the market prefers high growth"
            else:
                rotation_phase = "均衡轮动"
                rotation_desc = "The relative strengths of value and growth sectors are close, and the market has no obvious preference."

        # 4. Identify defensive and cyclical sector recommendations
        def _filter_by_industry_list(sectors_list: List[dict], industry_set: set) -> List[dict]:
            return [
                s for s in sectors_list
                if s["industry"] in industry_set and s["relative_strength"] is not None
            ]

        top_defensive = sorted(
            _filter_by_industry_list(sectors, defensive_industries),
            key=lambda x: x["relative_strength"],
            reverse=True,
        )[:5]

        top_cyclical = sorted(
            _filter_by_industry_list(sectors, cyclical_industries),
            key=lambda x: x["relative_strength"],
            reverse=True,
        )[:5]

        # 5. Build return results (only the first 30 industries are returned to control output size)
        payload = {
            "status": "ok",
            "analysis_date": today.isoformat(),
            "data_source": (
                "Industry valuation data comes from the local database stock_basic_info collection,"
                "The periodic signal comes from akshare.bond_zh_us_rate() / stock_zh_index_daily()"
            ),
            "current_cycle_position_data": cycle_info,
            "rotation_phase": {
                "phase": rotation_phase,
                "description": rotation_desc,
                "methodology": (
                    "Comprehensive judgment based on macro cycle stage (if any) and industry relative valuation distribution."
                    "Defensive sector reference: banking, public utilities, food and beverages, pharmaceuticals and biology, transportation, and insurance;"
                    "Cyclical sector reference: non-ferrous metals, steel, coal, basic chemicals, building materials, real estate, machinery and equipment."
                ),
            },
            "sector_ranking": sectors[:30],  # Top 30 industries
            "market_valuation_context": {
                "market_pe_median": snapshot.get("market_pe_median"),
                "market_pb_median": snapshot.get("market_pb_median"),
                "total_industries": snapshot.get("total_industries"),
                "total_stocks_tracked": snapshot.get("total_stocks_tracked"),
            },
            "top_defensive": top_defensive,
            "top_cyclical": top_cyclical,
            "data_quality": {
                "industry_count": len(sectors),
                "defensive_found": len(top_defensive),
                "cyclical_found": len(top_cyclical),
                "cycle_data_available": isinstance(cycle_info, dict) and cycle_info.get("cycle_phase") != "未知（实时数据不可用）",
                "note": (
                    "Industry rankings are based on the deviation of PE/PB from the market median,"
                    "It only reflects the relative strength signal at the valuation level and does not constitute investment advice."
                    "The actual rotation also needs to be combined with comprehensive judgments such as capital flow, policy catalysis, and prosperity."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except Exception as exc:
        logger.error("Industry rotation signal analysis failed: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "get_economic_cycle_position",
    "get_monetary_environment",
    "get_sector_rotation_signals",
]
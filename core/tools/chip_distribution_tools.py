"""
Chip distribution tool function

Provides chip distribution data acquisition, supporting two data sources: AkShare (priority) and Tushare (backup).

Data source priority:
  AkShare (Free, Dongcai Reptile) → Tushare (Official API, requires 5000 points)
"""

import logging
import random
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# === Mock Switch: When set to True, the real API is not called and random simulated data is returned. ===
_MOCK_CHIP_DATA = False


def _normalize_ticker(ticker: str) -> str:
    """Standardized stock symbol (removes exchange suffix)"""
    if "." in ticker:
        return ticker.split(".")[0]
    return ticker


def _normalize_ts_code(ticker: str) -> str:
    """Convert to Tushare ts_code format (such as 000001.SZ)"""
    if "." in ticker:
        return ticker.upper()
    code = ticker.strip()
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"


def get_chip_distribution_akshare(ticker: str, trade_date: str) -> Optional[Dict[str, Any]]:
    """
    Obtain chip distribution data through AkShare
    
    Use the stock_cyq_em interface to obtain Oriental Fortune chip distribution data.
    
    Args:
        ticker: Stock code (e.g. 000001)
        trade_date: Transaction date (format: YYYY-MM-DD)
    
    Returns:
        Dictionary of chip distribution data, or None on failure
    """
    try:
        import akshare as ak

        symbol = _normalize_ticker(ticker)
        t0 = time.time()
        logger.info(f"[AkShare chips] Start calling stock_cyq_em: symbol={symbol}, adjust=''")
        # akshare stock_cyq_em Return to historical chip distribution
        df = ak.stock_cyq_em(symbol=symbol, adjust="")
        elapsed = time.time() - t0
        logger.info(f"[AkShare筹码] stock_cyq_em 调用完成: 耗时={elapsed:.2f}s, 行数={len(df) if df is not None else 0}")

        if df is None or df.empty:
            logger.warning(f"[AkShare筹码] {symbol} 返回空数据 (耗时={elapsed:.2f}s)")
            return None

        # Normalize date column
        date_col = "日期" if "日期" in df.columns else df.columns[0]
        df[date_col] = df[date_col].astype(str)

        # Try to find the data closest to the target date
        target = trade_date.replace("-", "")
        # Prioritize exact matches
        row = df[df[date_col].str.replace("-", "") == target]
        if row.empty:
            # Get the latest data
            row = df.tail(1)

        if row.empty:
            return None

        r = row.iloc[0]
        # Column name mapping (Dongcai interface)
        col_map = {
            "获利比例": "profit_ratio",
            "平均成本": "avg_cost",
            "90成本-低": "cost_90_low",
            "90成本-高": "cost_90_high",
            "90集中度": "concentration_90",
            "70成本-低": "cost_70_low",
            "70成本-高": "cost_70_high",
            "70集中度": "concentration_70",
        }

        result: Dict[str, Any] = {
            "code": symbol,
            "date": str(r.get(date_col, trade_date)),
            "source": "akshare",
            "profit_ratio": 0.0,
            "avg_cost": 0.0,
            "cost_90_low": 0.0,
            "cost_90_high": 0.0,
            "concentration_90": 0.0,
            "cost_70_low": 0.0,
            "cost_70_high": 0.0,
            "concentration_70": 0.0,
        }

        for ch_col, en_key in col_map.items():
            if ch_col in r.index:
                try:
                    val = float(r[ch_col])
                    result[en_key] = val
                except (ValueError, TypeError):
                    pass

        # Centralization is a common silent failure point (when the interface list changes, it will all degrade to 0), explicit traces are left
        if not result["concentration_90"] and not result["concentration_70"]:
            logger.warning(f"[AkShare筹码] {symbol} 未取到集中度，接口实际列名: {list(df.columns)}")

        logger.info(f"[AkShare筹码] {symbol} 获取成功，来源日期: {result['date']}")
        return result

    except ImportError:
        logger.warning("[AkShare chips] akshare Not installed")
        return None
    except Exception as e:
        logger.warning(f"[AkShare筹码] {ticker} 获取失败: {e}")
        return None


def get_chip_distribution_tushare(ticker: str, trade_date: str) -> Optional[Dict[str, Any]]:
    """
    Obtain chip distribution data through Tushare (cyq_perf interface, requires 5000 points)

    Args:
        ticker: Stock code (e.g. 000001)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        Dictionary of chip distribution data, or None on failure
    """
    try:
        t0 = time.time()
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider or not provider.is_available():
            logger.debug("[Tushare chips] Tushare Not initialized or unavailable")
            return None

        ts_code = _normalize_ts_code(ticker)
        trade_date_fmt = trade_date.replace("-", "")

        import asyncio
        loop = None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        logger.info(f"[Tushare chips] Start calling cyq_perf: ts_code={ts_code}, trade_date={trade_date_fmt}")
        # Tushare cyq_perf API: Chip analysis
        df = provider.api.cyq_perf(
            ts_code=ts_code,
            trade_date=trade_date_fmt,
            fields="ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,"
                   "cost_85pct,cost_95pct,weight_avg,winner_rate"
        )

        if df is None or df.empty:
            # Try to get the data for the last few days
            start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y%m%d")
            logger.info(f"[Tushare chips] There is no data for the exact date, fall back to the query range: {start}~{trade_date_fmt}")
            df = provider.api.cyq_perf(
                ts_code=ts_code,
                start_date=start,
                end_date=trade_date_fmt,
                fields="ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,"
                       "cost_85pct,cost_95pct,weight_avg,winner_rate"
            )
            if df is None or df.empty:
                logger.warning(f"[Tushare筹码] {ts_code} 返回空数据")
                return None
            df = df.sort_values("trade_date", ascending=False)

        r = df.iloc[0]
        symbol = _normalize_ticker(ticker)
        result: Dict[str, Any] = {
            "code": symbol,
            "date": str(r.get("trade_date", trade_date_fmt)),
            "source": "tushare",
            "profit_ratio": float(r.get("winner_rate", 0)) / 100.0 if r.get("winner_rate") else 0.0,
            "avg_cost": float(r.get("weight_avg", 0)) if r.get("weight_avg") else 0.0,
            "cost_90_low": float(r.get("cost_5pct", 0)) if r.get("cost_5pct") else 0.0,
            "cost_90_high": float(r.get("cost_95pct", 0)) if r.get("cost_95pct") else 0.0,
            "concentration_90": 0.0,
            "cost_70_low": float(r.get("cost_15pct", 0)) if r.get("cost_15pct") else 0.0,
            "cost_70_high": float(r.get("cost_85pct", 0)) if r.get("cost_85pct") else 0.0,
            "concentration_70": 0.0,
        }
        # Calculate concentration: standard caliber (high-low)/(high+low), Consistent with Dongcai/Tongdaxin/Flush, the smaller the value, the more concentrated it is.
        if result["cost_90_high"] + result["cost_90_low"] > 0:
            rng90 = result["cost_90_high"] - result["cost_90_low"]
            result["concentration_90"] = round(rng90 / (result["cost_90_high"] + result["cost_90_low"]), 4)
        if result["cost_70_high"] + result["cost_70_low"] > 0:
            rng70 = result["cost_70_high"] - result["cost_70_low"]
            result["concentration_70"] = round(rng70 / (result["cost_70_high"] + result["cost_70_low"]), 4)

        logger.info(f"[Tushare筹码] {ts_code} 获取成功 (耗时={time.time() - t0:.2f}s)")
        return result

    except Exception as e:
        logger.warning(f"[Tushare筹码] {ticker} 获取失败: {e}")
        return None


def _mock_chip_report(symbol: str, trade_date: str) -> str:
    """Generate random simulated chip distribution report (for isolation testing)"""
    avg_cost = round(random.uniform(8.0, 15.0), 2)
    current_price = round(avg_cost * random.uniform(0.85, 1.15), 2)
    profit_ratio = round(random.uniform(25, 60), 1)
    cost_90_low = round(avg_cost * random.uniform(0.75, 0.88), 2)
    cost_90_high = round(avg_cost * random.uniform(1.12, 1.35), 2)
    conc_90 = round((cost_90_high - cost_90_low) / avg_cost, 4)
    cost_70_low = round(avg_cost * random.uniform(0.85, 0.93), 2)
    cost_70_high = round(avg_cost * random.uniform(1.05, 1.15), 2)
    conc_70 = round((cost_70_high - cost_70_low) / avg_cost, 4)

    logger.info(f"[筹码分布-MOCK] {symbol} 返回模拟数据 (avg_cost={avg_cost}, profit_ratio={profit_ratio}%)")

    return f"""## 📊 筹码分布分析 - {symbol} ({trade_date})

**数据来源**: mock（模拟数据，用于功能验证）

### 核心指标
- **获利比例**: {profit_ratio}%（当前价格下持有浮盈的筹码占比）
- **平均成本**: {avg_cost} 元

### 筹码集中度
| 区间 | 成本下限 | 成本上限 | 集中度 |
|------|---------|---------|------|
| 90%筹码 | {cost_90_low} 元 | {cost_90_high} 元 | {conc_90} |
| 70%筹码 | {cost_70_low} 元 | {cost_70_high} 元 | {conc_70} |

### 分析要点
- 当前价格: {current_price} 元 (vs 平均成本 {avg_cost} 元)
- 90%筹码区间: [{cost_90_low}, {cost_90_high}]，集中度 {conc_90}（{'较为集中' if conc_90 < 0.3 else '较为分散'}）
- 70%筹码区间: [{cost_70_low}, {cost_70_high}]，集中度 {conc_70}

> ⚠️ 此数据为模拟生成，仅用于排除 API 调用问题。如需真实数据请关闭 mock 模式。
"""


def get_chip_distribution_unified(ticker: str, trade_date: str) -> str:
    """
    Unified chip distribution interface (AkShare is preferred, Tushare is backup)

    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Chip distribution analysis report text
    """
    symbol = _normalize_ticker(ticker)
    t0 = time.time()

    # Mock Mode: Return random simulation data directly without calling the real API
    if _MOCK_CHIP_DATA:
        return _mock_chip_report(symbol, trade_date)

    # Priority AkShare
    logger.info(f"[筹码分布] 开始获取 {symbol} 筹码数据，优先使用 AkShare")
    data = get_chip_distribution_akshare(symbol, trade_date)
    if data is None:
        elapsed_ak = time.time() - t0
        logger.info(f"[Chip distribution] AkShare failed (Time consuming={elapsed_ak:.2f}s), switch to Tushare: {symbol}")
        data = get_chip_distribution_tushare(symbol, trade_date)

    total_elapsed = time.time() - t0
    if data is None:
        logger.warning(f"[筹码分布] {symbol} 所有数据源均失败 (总耗时={total_elapsed:.2f}s)")
        return (
            f"❌ 无法获取 {ticker} 的筹码分布数据（{trade_date}）。\n"
            "Possible reasons: the data source is unavailable, the date is not a trading day, or the stock code is incorrect."
        )

    logger.info(f"[筹码分布] {symbol} 获取成功 (总耗时={total_elapsed:.2f}s, 来源={data['source']})")

    # Formatted output
    profit_pct = data["profit_ratio"] * 100 if data["profit_ratio"] <= 1 else data["profit_ratio"]
    report = f"""## 📊 筹码分布分析 - {symbol} ({data['date']})

**数据来源**: {data['source']}

### 核心指标
- **获利比例**: {profit_pct:.1f}%（当前价格下持有浮盈的筹码占比）
- **平均成本**: {data['avg_cost']:.2f} 元

### 筹码集中度
| 区间 | 成本下限 | 成本上限 | 集中度 |
|------|---------|---------|------|
| 90%筹码 | {data['cost_90_low']:.2f} 元 | {data['cost_90_high']:.2f} 元 | {data['concentration_90']:.4f} |
| 70%筹码 | {data['cost_70_low']:.2f} 元 | {data['cost_70_high']:.2f} 元 | {data['concentration_70']:.4f} |

### 筹码分析说明
- 获利比例越高，说明持仓者整体盈利，抛压可能较大
- 获利比例越低，说明大多数持仓者亏损，下方支撑较强
- 筹码集中度越低（数值越小），说明筹码越集中，趋势可能越稳定
- 90%筹码范围表示全市场90%的持仓者的成本区间
"""
    return report


def get_chip_distribution_sync(ticker: str, trade_date: str) -> str:
    """Synchronous packaging (alias, called by the tool layer)"""
    return get_chip_distribution_unified(ticker, trade_date)


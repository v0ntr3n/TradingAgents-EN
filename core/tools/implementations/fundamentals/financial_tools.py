"""
Special financial analysis tools

8 segmented financial tools are available:
1. get_income_analysis - Income statement analysis (revenue, profit trends)
2. get_balance_sheet_analysis - Balance Sheet Analysis (Financial Health)
3. get_cashflow_analysis - Cash Flow Statement Analysis
4. get_goodwill_analysis - Goodwill analysis (valuation, impairment risk signals)
5. get_dupont_analysis - DuPont analysis (ROE three-factor/five-factor dismantling)
6. get_dividend_data - Dividend share data
7. get_main_business - Main business composition
8. get_accounts_receivable_risk_analyzer - Three-dimensional analysis of accounts receivable risk (recovery efficiency+Income quality+Provision prudence)
"""

import logging
import asyncio
from typing import Annotated, Optional, Dict, Any, List

from langchain_core.tools import tool
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _get_tushare_provider():
    """Delayed import acquisition Tushare Provider"""
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    return get_tushare_provider()


def _get_mongodb_cache():
    """Lazy Import Gets MongoDB Cache Adapter"""
    try:
        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
        return get_mongodb_cache_adapter()
    except Exception:
        return None


def _safe_val(val, fmt: str = ",.2f") -> str:
    """安全格式化数值"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        return f"{float(val):{fmt}}"
    except (ValueError, TypeError):
        return str(val)


def _safe_pct(val) -> str:
    """安全格式化百分比"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return str(val)


def _coerce_float(val) -> Optional[float]:
    if val is None or val in ("N/A", "", "--"):
        return None
    try:
        numeric = float(val)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _resolve_gross_margin_percent(data: Dict[str, Any], indicator_list: List[Dict[str, Any]]) -> Optional[float]:
    for candidate in (data.get('grossprofit_margin'), data.get('gross_margin')):
        numeric = _coerce_float(candidate)
        if numeric is not None and -100 <= numeric <= 100:
            return numeric

    for record in indicator_list or []:
        for candidate in (record.get('grossprofit_margin'), record.get('gross_margin')):
            numeric = _coerce_float(candidate)
            if numeric is not None and -100 <= numeric <= 100:
                return numeric

    return None


def _wan_yi(val) -> str:
    """将数值转为 万/亿 显示"""
    if val is None or val == "N/A":
        return "N/A"
    try:
        v = float(val)
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f}亿"
        elif abs(v) >= 1e4:
            return f"{v / 1e4:.2f}万"
        else:
            return f"{v:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _run_async(coro):
    """
    Run asynchronous coroutines in a synchronization context, compatible with main threads and worker threads.

    - If the current thread has a running event loop → in new thread asyncio.run()
    - If the current thread does not have an event loop → direct asyncio.run()
    """
    try:
        asyncio.get_running_loop()
        # The current thread has a running event loop and cannot directly asyncio.run()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        # The current thread does not have a running event loop and can directly asyncio.run()
        return asyncio.run(coro)


def _get_financial_data_from_cache_or_api(symbol: str, limit: int = 8) -> Optional[Dict[str, Any]]:
    """
    Get complete financial data (with raw_data) from MongoDB cache or Tushare API

    Read the MongoDB stock_financial_data collection first, if not, call the Tushare API.
    Returns the standardized data (including lists such as raw_data.income_statement).
    """
    code6 = str(symbol).replace('.SH', '').replace('.SZ', '').replace('.BJ', '').zfill(6)

    # 1. Try MongoDB caching
    cache = _get_mongodb_cache()
    if cache and cache.use_app_cache:
        doc = cache.get_financial_data(code6)
        if doc and doc.get('raw_data'):
            logger.info(f"💰 [Special finance] Using MongoDB cache: {symbol}")
            return doc

    # 2. tune Tushare API
    try:
        provider = _get_tushare_provider()
        if provider and provider.is_available():
            logger.info(f"📊 [Special finance] Get data from Tushare: {symbol}, limit={limit}")
            data = _run_async(provider.get_financial_data(symbol, limit=limit))
            if data:
                return data
    except Exception as e:
        logger.warning(f"⚠️ [Special finance] Tushare Failed to obtain: {e}")

    return None


# ============================================================
# Tool 1: Income statement analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_income_analysis",
    name="利润表分析",
    description="Analyze the core indicators of stock income statements and multi-period growth trends, and return structured multi-period sequence data of revenue, net profit, gross profit margin, net profit rate, expense ratio, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_income_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Income statement analysis tools —— Get a stock s revenue, profits and growth trends

    The analysis content includes: operating income, net profit, gross profit margin, net profit rate, expense ratio, etc.
    Supports multi-period (last N quarters) trend display.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        periods: Number of analysis periods, default 8 (last 8 quarters)

    Returns:
        str: Income statement analysis report (Markdown format)
    """
    logger.info(f"📊 [利润表分析] 分析股票: {ticker}, 期数: {periods}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据，请确认股票代码正确"

        raw = data.get("raw_data", {})
        income_list = raw.get("income_statement", [])
        indicator_list = raw.get("financial_indicators", [])

        lines = [f"# {ticker} 利润表分析\n"]

        # Overview of the latest issue
        lines.append("## 📊 最新一期概览")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        lines.append(f"- **营业收入**: {_wan_yi(data.get('revenue'))}")
        lines.append(f"- **operating income(TTM)**: {_wan_yi(data.get('revenue_ttm'))}")
        lines.append(f"- **归母净利润**: {_wan_yi(data.get('net_profit'))}")
        lines.append(f"- **Net profit attributable to parent company(TTM)**: {_wan_yi(data.get('net_profit_ttm'))}")
        lines.append(f"- **营业利润**: {_wan_yi(data.get('oper_profit'))}")
        lines.append(f"- **营业成本**: {_wan_yi(data.get('oper_cost'))}")
        lines.append(f"- **毛利率**: {_safe_pct(_resolve_gross_margin_percent(data, indicator_list))}")
        lines.append(f"- **净利率**: {_safe_pct(data.get('netprofit_margin'))}")
        lines.append(f"- **研发费用**: {_wan_yi(data.get('rd_exp'))}")
        lines.append("")

        # fee structure
        lines.append("## 💰 费用结构")
        lines.append(f"- **Selling expenses/revenue**: {_safe_pct(data.get('saleexp_to_gr'))}")
        lines.append(f"- **overhead/revenue**: {_safe_pct(data.get('adminexp_of_gr'))}")
        lines.append(f"- **Financial expenses/revenue**: {_safe_pct(data.get('finaexp_of_gr'))}")
        lines.append(f"- **销售成本率**: {_safe_pct(data.get('cogs_of_sales'))}")
        lines.append(f"- **期间费用率**: {_safe_pct(data.get('expense_of_sales'))}")
        lines.append("")

        # multi-period trend
        if income_list and len(income_list) > 1:
            lines.append("## 📈 多期趋势")
            lines.append("| reporting period | operating income | Net profit attributable to parent company | operating profit |")
            lines.append("|--------|----------|------------|----------|")
            for rec in income_list[:periods]:
                period = rec.get('end_date', 'N/A')
                rev = _wan_yi(rec.get('revenue'))
                np_ = _wan_yi(rec.get('n_income_attr_p'))
                op = _wan_yi(rec.get('oper_profit'))
                lines.append(f"| {period} | {rev} | {np_} | {op} |")
            lines.append("")

        # Profitability indicator trends
        if indicator_list and len(indicator_list) > 1:
            lines.append("## 📊 盈利能力趋势")
            lines.append("| reporting period | Gross profit margin | net profit margin | ROE |")
            lines.append("|--------|--------|--------|-----|")
            for rec in indicator_list[:periods]:
                period = rec.get('end_date', 'N/A')
                gm = _safe_pct(_resolve_gross_margin_percent({}, [rec]))
                nm = _safe_pct(rec.get('netprofit_margin'))
                roe = _safe_pct(rec.get('roe'))
                lines.append(f"| {period} | {gm} | {nm} | {roe} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Income statement analysis] Execution failed: {e}")
        return f"❌ 利润表分析执行失败: {e}"


# ============================================================
# Tool 2: Balance Sheet Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_balance_sheet_analysis",
    name="资产负债表分析",
    description="Analyze the asset-liability structure, solvency and financial health of stocks, and structurally return indicators such as asset-liability ratio, current ratio, quick ratio, equity multiplier, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_balance_sheet_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Balance Sheet Analysis Tools —— Analyze financial health

    Analysis content: asset-liability ratio, current ratio, quick ratio, cash ratio, asset structure, etc.

    Args:
        ticker: Stock code
        periods: Number of analysis periods, default 8

    Returns:
        str: Balance Sheet Analysis Report
    """
    logger.info(f"📊 [Balance Sheet Analysis] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])
        indicator_list = raw.get("financial_indicators", [])

        lines = [f"# {ticker} 资产负债表分析\n"]

        # Latest issue
        lines.append("## 📊 Latest asset and liability status")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        lines.append(f"- **总资产**: {_wan_yi(data.get('total_assets'))}")
        lines.append(f"- **总负债**: {_wan_yi(data.get('total_liab'))}")
        lines.append(f"- **股东权益**: {_wan_yi(data.get('total_equity'))}")
        lines.append(f"- **货币资金**: {_wan_yi(data.get('money_cap'))}")
        lines.append(f"- **应收账款**: {_wan_yi(data.get('accounts_receiv'))}")
        lines.append(f"- **存货**: {_wan_yi(data.get('inventories'))}")
        lines.append(f"- **固定资产**: {_wan_yi(data.get('fix_assets'))}")

        # Goodwill (valid value only when disclosed in annual report)
        goodwill = data.get('goodwill')
        if goodwill is not None and goodwill > 0:
            lines.append(f"- **商誉**: {_wan_yi(goodwill)} | 商誉/净资产: {_safe_pct(goodwill / data.get('total_equity') * 100 if data.get('total_equity') else None)}")
        else:
            lines.append(f"- **goodwill**: Insufficient data (quarterly reports usually do not disclose goodwill details, it is recommended to check annual report data)")
        lines.append("")

        # Solvency
        lines.append("## 🏦 偿债能力指标")
        lines.append(f"- **资产负债率**: {_safe_pct(data.get('debt_to_assets'))}")
        lines.append(f"- **流动比率**: {_safe_val(data.get('current_ratio'))}")
        lines.append(f"- **速动比率**: {_safe_val(data.get('quick_ratio'))}")
        lines.append(f"- **现金比率**: {_safe_val(data.get('cash_ratio'))}")
        lines.append(f"- **权益乘数**: {_safe_val(data.get('assets_to_eqt'))}")
        lines.append("")

        # Asset structure
        lines.append("## 📊 资产结构")
        lines.append(f"- **流动资产**: {_wan_yi(data.get('total_cur_assets'))}")
        lines.append(f"- **非流动资产**: {_wan_yi(data.get('total_nca'))}")
        lines.append(f"- **Proportion of current assets**: {_safe_pct(data.get('ca_to_assets'))}")
        lines.append(f"- **Proportion of non-current assets**: {_safe_pct(data.get('nca_to_assets'))}")
        lines.append(f"- **流动负债**: {_wan_yi(data.get('total_cur_liab'))}")
        lines.append(f"- **非流动负债**: {_wan_yi(data.get('total_ncl'))}")
        lines.append("")

        # multi-period trend
        if balance_list and len(balance_list) > 1:
            lines.append("## 📈 资产负债趋势")
            lines.append("| reporting period | total assets | total liabilities | Shareholders equity | Monetary funds | goodwill |")
            lines.append("|--------|--------|--------|----------|----------|------|")
            for rec in balance_list[:periods]:
                period = rec.get('end_date', 'N/A')
                ta = _wan_yi(rec.get('total_assets'))
                tl = _wan_yi(rec.get('total_liab'))
                eq = _wan_yi(rec.get('total_hldr_eqy_exc_min_int'))
                mc = _wan_yi(rec.get('money_cap'))
                gw = _wan_yi(rec.get('goodwill'))
                lines.append(f"| {period} | {ta} | {tl} | {eq} | {mc} | {gw} |")
            lines.append("")

        # Solvency Trends
        if indicator_list and len(indicator_list) > 1:
            lines.append("## 📊 偿债能力趋势")
            lines.append("| reporting period | Asset-liability ratio | current ratio | quick ratio |")
            lines.append("|--------|-----------|---------|---------|")
            for rec in indicator_list[:periods]:
                period = rec.get('end_date', 'N/A')
                dta = _safe_pct(rec.get('debt_to_assets'))
                cr = _safe_val(rec.get('current_ratio'))
                qr = _safe_val(rec.get('quick_ratio'))
                lines.append(f"| {period} | {dta} | {cr} | {qr} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Balance Sheet Analysis] Execution failed: {e}")
        return f"❌ Balance sheet analysis execution failed: {e}"


# ============================================================
# Tool 3: Cash Flow Statement Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_cashflow_analysis",
    name="现金流量表分析",
    description=(
        "Analyze a stock s operating/investing/financing cash flows and assess cash flow health."
        "Suitable for cash flow deterioration analysis, identification of continued decline in operating cash flow, identification of negative free cash flow, judgment of cash income quality,"
        "Profit value assessment and financial risk signal investigation."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["cashflow_analysis", "cashflow_quality", "cashflow_deterioration", "operating_cashflow", "free_cashflow", "financial_risk"],
    tool_role_hint="specialized",
    output_shape="markdown_report",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "financial_statement_analysis"],
    when_to_use="Use it when you need to explain the operating/investing/financing cash flow, multi-period cash flow trend, free cash flow, cash flow health, cash flow deterioration risk and profit content in terms of financial statements.",
    when_not_to_use="It is not used for analysis of main capital flow, northbound capital, transaction capital flow or short-term trading capital; these are market capital flows, not financial report cash flows. If you need structured long-term cash flow quality indicators, use get_cashflow_quality_trend_tool first.",
)
def get_cashflow_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (most recent quarters), default 8"] = 8
) -> str:
    """
    Cash Flow Statement Analysis Tools —— Assess cash flow health

    Analysis content: operating cash flow, investment cash flow, financing cash flow, free cash flow, etc.

    Args:
        ticker: Stock code
        periods: Number of analysis periods, default 8

    Returns:
        str: Cash flow statement analysis report
    """
    logger.info(f"📊 [cash flow analysis] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        cashflow_list = raw.get("cashflow_statement", [])

        lines = [f"# {ticker} 现金流量表分析\n"]

        # Latest issue
        lines.append("## 📊 最新现金流状况")
        lines.append(f"- **报告期**: {data.get('report_period', 'N/A')}")
        ocf = data.get('n_cashflow_act')
        icf = data.get('n_cashflow_inv_act')
        fcf_val = data.get('n_cashflow_fin_act')
        lines.append(f"- **Net cash flow from operating activities**: {_wan_yi(ocf)}")
        lines.append(f"- **Net cash flow from investing activities**: {_wan_yi(icf)}")
        lines.append(f"- **Net cash flow from financing activities**: {_wan_yi(fcf_val)}")
        lines.append(f"- **Closing cash and equivalents**: {_wan_yi(data.get('c_cash_equ_end_period'))}")
        lines.append(f"- **Opening cash and equivalents**: {_wan_yi(data.get('c_cash_equ_beg_period'))}")
        lines.append("")

        # Simple Free Cash Flow Estimate
        if ocf is not None and icf is not None:
            try:
                free_cf = float(ocf) + float(icf)
                lines.append(f"## 💡 Free cash flow (simple estimate)")
                lines.append(f"- **free cash flow ≈ operating cash flow + investment cash flow**: {_wan_yi(free_cf)}")
                if free_cf > 0:
                    lines.append(f"- **judge**: ✅ Free cash flow is positive, and the company s hematopoietic ability is good.")
                else:
                    lines.append(f"- **judge**: ⚠️ Free cash flow is negative, need to pay attention to financial pressure")
                lines.append("")
            except (ValueError, TypeError):
                pass

        # Cash flow quality analysis
        net_profit = data.get('net_profit')
        if ocf is not None and net_profit is not None:
            try:
                ocf_f = float(ocf)
                np_f = float(net_profit)
                if np_f != 0:
                    ratio = ocf_f / np_f
                    lines.append("## 🔍 现金流质量")
                    lines.append(f"- **Operating cash flow/net profit attributable to parent company**: {ratio:.2f}")
                    if ratio > 1:
                        lines.append("- **judge**: ✅ Excellent cash flow quality (>1) , High profit content")
                    elif ratio > 0.5:
                        lines.append("- **judge**: 🟡 Cash flow quality is average (0.5~1) , Part of the profit has not yet been repaid")
                    else:
                        lines.append("- **judge**: ⚠️ Cash flow quality is weak (<0.5) , Low profit content")
                    lines.append("")
            except (ValueError, TypeError):
                pass

        # multi-period trend
        if cashflow_list and len(cashflow_list) > 1:
            lines.append("## 📈 现金流趋势")
            lines.append("| reporting period | operating cash flow | investment cash flow | Financing cash flow | Ending cash |")
            lines.append("|--------|-----------|-----------|-----------|---------|")
            for rec in cashflow_list[:periods]:
                period = rec.get('end_date', 'N/A')
                o = _wan_yi(rec.get('n_cashflow_act'))
                i = _wan_yi(rec.get('n_cashflow_inv_act'))
                f_ = _wan_yi(rec.get('n_cashflow_fin_act'))
                e = _wan_yi(rec.get('c_cash_equ_end_period'))
                lines.append(f"| {period} | {o} | {i} | {f_} | {e} |")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [cash flow analysis] Execution failed: {e}")
        return f"❌ 现金流分析执行失败: {e}"


# ============================================================
# Tool 4: Goodwill analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_goodwill_analysis",
    name="商誉分析",
    description="Analyze the size, proportion and change trend of goodwill of stocks, and assess the risk of goodwill impairment. Extract the goodwill field from the annual report balance sheet and calculate the goodwill/net assets ratio and year-on-year change.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_goodwill_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 002230, 600519, 000001)"],
    years: Annotated[int, "Number of years to look back, default is 5 years"] = 5
) -> str:
    """
    Goodwill Analysis Tool —— Assessing goodwill scale and impairment risk

    Extract goodwill from balance sheet annual report data(goodwill)Field, calculation:
    - Carrying amount of goodwill
    - Goodwill/Net Assets Ratio
    - Goodwill/total assets ratio
    - Year-on-year trend (identifying impairment signals)

    ⚠️ Goodwill is only fully disclosed in the annual report (Q4). This tool filters annual report data from raw_data.
    There will be no issue of null values in quarterly reports.

    Args:
        ticker: Stock code (e.g. 002230, 600519)
        years: Number of years to look back, default is 5 years

    Returns:
        str: Goodwill Analysis Report
    """
    logger.info(f"📊 [商誉分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])

        # Filter annual reports: take the last reporting period of each year (end_date contains -12-31 or remove duplicates by year and take the last one)
        annual_records: List[Dict[str, Any]] = []
        seen_years: set = set()
        for rec in balance_list:
            end_date = str(rec.get('end_date', '') or rec.get('f_ann_date', ''))
            if not end_date:
                continue
            # Year of extraction
            year = end_date[:4]
            if year not in seen_years:
                seen_years.add(year)
                annual_records.append(rec)

        # Get the annual report of the most recent years
        annual_records = sorted(annual_records, key=lambda r: str(r.get('end_date', '')), reverse=True)[:years]

        if not annual_records:
            return f"📊 {ticker} There is currently no goodwill data (annual report records are not found in the balance sheet cache, it is recommended to pull the data first)"

        goodwill_by_year: Dict[str, Optional[float]] = {}
        equity_by_year: Dict[str, Optional[float]] = {}
        assets_by_year: Dict[str, Optional[float]] = {}

        for rec in annual_records:
            year = str(rec.get('end_date', ''))[:4] or 'N/A'
            goodwill_by_year[year] = rec.get('goodwill')
            equity_by_year[year] = rec.get('total_hldr_eqy_exc_min_int')
            assets_by_year[year] = rec.get('total_assets')

        lines = [f"# {ticker} 商誉分析\n"]

        # The latest issue of Goodwill Profile
        latest_year = list(goodwill_by_year.keys())[0]
        latest_gw = goodwill_by_year.get(latest_year)
        latest_equity = equity_by_year.get(latest_year)
        latest_assets = assets_by_year.get(latest_year)

        lines.append("## 📊 The latest issue of Goodwill Profile")
        lines.append(f"- **报告年度**: {latest_year}")

        if latest_gw is not None and latest_gw > 0:
            lines.append(f"- **Carrying amount of goodwill**: {_wan_yi(latest_gw)}")
            if latest_equity:
                gw_to_equity = latest_gw / latest_equity * 100
                lines.append(f"- **Goodwill/Net Assets**: {gw_to_equity:.1f}%")
                risk_flag = "🔴 High risk (the ratio of goodwill to net assets is too high, and the pressure for impairment is high)" if gw_to_equity > 20 else ("🟡 关注（商誉占比偏高）" if gw_to_equity > 10 else "🟢 正常")
                lines.append(f"- **风险信号**: {risk_flag}")
            if latest_assets:
                lines.append(f"- **Goodwill/Total Assets**: {latest_gw / latest_assets * 100:.1f}%")
        elif latest_gw is not None and latest_gw == 0:
            lines.append(f"- **Carrying amount of goodwill**: 0 (The company has no goodwill)")
            lines.append(f"- **risk signal**: 🟢 No goodwill impairment risk")
        else:
            lines.append(f"- **Carrying amount of goodwill**: Missing data (the annual report does not disclose the goodwill field)")
            lines.append(f"- **risk signal**: ⬜ Insufficient data to judge")
        lines.append("")

        # Multi-year trend
        if len(annual_records) > 1:
            lines.append("## 📈 商誉年度趋势")
            lines.append("| reporting year | goodwill | net worth | Goodwill/Net Assets | Goodwill/Total Assets |")
            lines.append("|----------|------|--------|------------|------------|")
            sorted_years = sorted(goodwill_by_year.keys(), reverse=True)
            prev_gw = None
            for year in sorted_years:
                gw = goodwill_by_year.get(year)
                eq = equity_by_year.get(year)
                ta = assets_by_year.get(year)
                gwe = f"{gw / eq * 100:.1f}%" if (gw is not None and eq and eq > 0) else "-"
                gwt = f"{gw / ta * 100:.1f}%" if (gw is not None and ta and ta > 0) else "-"
                lines.append(f"| {year} | {_wan_yi(gw)} | {_wan_yi(eq)} | {gwe} | {gwt} |")

                # Detect significant year-on-year decline (impairment signal)
                if prev_gw is not None and gw is not None and prev_gw > 0 and gw > 0:
                    change = (gw - prev_gw) / prev_gw * 100
                    if change < -20:
                        lines.append(f"  ⚠️ {year}年商誉同比下降 {abs(change):.0f}%，可能存在减值！")
                prev_gw = gw
            lines.append("")

        lines.append("## 🔍 减值风险判读")
        if latest_gw is not None and latest_gw > 0 and latest_equity:
            ratio = latest_gw / latest_equity * 100
            lines.append(f"- 商誉/净资产比率 = {ratio:.1f}%")
            if ratio > 20:
                lines.append(f"- ⚠️ Exceeding the 20% warning line, impairment has a significant impact on net assets")
                lines.append(f"- It is recommended to pay attention to: the completion of the target company s performance commitments and changes in industry prosperity")
            elif ratio > 10:
                lines.append(f"- It is in the 10%-20% attention range and needs to be tracked continuously.")
            else:
                lines.append(f"- Less than 10%, goodwill impairment has limited impact on net assets")
        lines.append("")

        lines.append("---")
        lines.append("*Data source: Annual report balance sheet (Tushare) | The goodwill field is only fully disclosed in the annual report*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Goodwill analysis] Execution failed: {e}")
        return f"❌ 商誉分析执行失败: {e}"


# ============================================================
# Tool 5: DuPont Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_dupont_analysis",
    name="杜邦分析",
    description="Conduct DuPont analysis on the stock and break down ROE into three factors (net interest rate×asset turnover rate×equity multiplier) and five factors (tax burden×interest burden×operating profit margin×asset turnover rate×Equity Multiplier), supporting multi-year trend comparisons.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_dupont_analysis(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001, 002230)"],
    years: Annotated[int, "Number of years to look back, default is 5 years"] = 5
) -> str:
    """
    DuPont Analytical Tools — ROE Three-factor / five-factor decomposition

    Read TTM income statement and balance sheet data from cache and calculate:

    **Three-factor decomposition**: 
    - net profit margin = net profit(TTM) / operating income(TTM)
    - asset turnover rate = operating income(TTM) / total assets
    - equity multiplier = total assets/net assets
    - ROE = net profit margin × asset turnover rate × equity multiplier

    **Five factors breakdown** (Operating profit data required):
    - tax burden factor = Net profit / total profit
    - interest burden = Total profit/operating profit
    - operating profit margin = Operating profit/operating income
    - asset turnover rate = Operating income / total assets
    - equity multiplier = total assets/net assets

    Args:
        ticker: Stock code (e.g. 600519, 002230)
        years: Number of years to look back, default is 5 years

    Returns:
        str: DuPont Analysis Report
    """
    logger.info(f"📊 [杜邦分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        lines = [f"# {ticker} 杜邦分析\n"]

        # ── Three factor dupont ──
        npm, at, em, roe_3f = None, None, None, None

        revenue = _coerce_float(data.get('revenue_ttm'))
        net_profit = _coerce_float(data.get('net_profit_ttm'))
        total_assets = _coerce_float(data.get('total_assets'))
        total_equity = _coerce_float(data.get('total_equity'))

        if all([net_profit, revenue, total_assets, total_equity]) and revenue != 0 and total_equity != 0:
            npm = net_profit / revenue  # Net interest rate (decimal)
            at = revenue / total_assets   # asset turnover rate
            em = total_assets / total_equity  # equity multiplier
            roe_3f = npm * at * em * 100     # DuPont ROE (percent)
            roe_direct = net_profit / total_equity * 100

            lines.append("## Three-factor breakdown (standard DuPont)\n")
            lines.append(f"**ROE = net profit margin × asset turnover rate × equity multiplier**\n")
            lines.append("| factor | meaning | numerical value |")
            lines.append("|------|------|------|")
            lines.append(f"| net profit margin | net profit(TTM) / operating income(TTM) | {npm*100:.2f}% |")
            lines.append(f"| 资产周转率 | 营业收入(TTM) / 总资产 | {at:.3f} 次 |")
            lines.append(f"| equity multiplier | total assets/net assets | {em:.2f} |")
            lines.append(f"| **ROE** | Multiplying three factors | **{roe_3f:.2f}%** |")
            lines.append("")
            lines.append(f"- Verification: Direct ROE = Net profit/net assets = {roe_direct:.2f}% ({'✅ consistent' if abs(roe_3f - roe_direct) < 0.1 else '⚠️ Deviation (may be due to rounding)'}) ")
            lines.append("")

            # ROE Quality Tips
            lines.append("### ROE Driver judgment\n")
            parts = []
            if npm and npm * 100 > 15:
                parts.append(f"- 🟢 **Driven by high profit margins**: net profit margin {npm*100:.1f}%, Strong product/brand barriers")
            elif npm and npm * 100 < 3:
                parts.append(f"- 🔴 **low profit margin**: net profit margin only {npm*100:.1f}%, Profit margin is thin")
            else:
                parts.append(f"- 🟡 **medium profit margin**: net profit margin {npm*100:.1f}%")
            if at and at > 1:
                parts.append(f"- 🟢 **Efficient asset turnover**: turnover rate {at:.2f} times, light asset model or efficient operation")
            elif at and at < 0.3:
                parts.append(f"- 🔴 **Asset turnover is slow**: turnover rate only {at:.2f} times, heavy assets or production capacity are not fully utilized")
            if em and em > 3:
                parts.append(f"- 🔴 **High leverage**: equity multiplier {em:.1f}, Financial leverage magnifies returns and risks")
            elif em and em < 1.5:
                parts.append(f"- 🟢 **low leverage**: equity multiplier {em:.1f}, Stable financial structure")
            lines.extend(parts)
            lines.append("")
        else:
            lines.append("## Three-factor breakdown (standard DuPont)\n")
            lines.append("⚠️ There is insufficient data to complete the three-factor disassembly.")
            lines.append(f"  revenue_ttm={revenue}  net_profit_ttm={net_profit}  total_assets={total_assets}  total_equity={total_equity}")
            lines.append("")

        # ── Five Factor DuPont ──
        oper_profit = _coerce_float(data.get('oper_profit'))
        total_profit = _coerce_float(data.get('total_profit'))

        if all([net_profit, total_profit, oper_profit, revenue, total_assets, total_equity]) \
                and revenue != 0 and total_equity != 0 and oper_profit != 0:
            tb = net_profit / total_profit        # tax burden factor
            ib = total_profit / oper_profit       # interest burden
            om = oper_profit / revenue            # operating profit margin
            roe_5f = tb * ib * om * at * em * 100

            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append(f"**ROE = tax burden factor × interest burden × operating profit margin × asset turnover rate × equity multiplier**\n")
            lines.append("| factor | meaning | numerical value |")
            lines.append("|------|------|------|")
            lines.append(f"| tax burden factor | Net profit / total profit | {tb:.3f} ({'income tax rate ' + str(int((1-tb)*100)) + '%' if 0 < tb <= 1 else 'Abnormal'}) |")
            lines.append(f"| interest burden | Total profit/operating profit | {ib:.3f} ({'Low interest erosion' if 0.9 < ib < 1.1 else 'Interest/non-recurring gains and losses have a significant impact'}) |")
            lines.append(f"| operating profit margin | Operating profit/operating income(TTM) | {om*100:.2f}% |")
            lines.append(f"| 资产周转率 | 营业收入(TTM) / 总资产 | {at:.3f} 次 |")
            lines.append(f"| equity multiplier | total assets/net assets | {em:.2f} |")
            lines.append(f"| **ROE** | Multiplying five factors | **{roe_5f:.2f}%** |")
            lines.append("")

            # Evaluation
            qualifiers = []
            if 0.7 <= tb <= 0.9:
                qualifiers.append("税负水平正常")
            if ib > 1.1:
                qualifiers.append("⚠️ interest burden factor > 1, Non-operating income contributes significantly to profits (non-operating income)")
            elif ib < 0.9:
                qualifiers.append("⚠️ interest burden factor < 1, Financial charges/non-recurring losses erode operating profit")
            if om and om > 0.2:
                qualifiers.append("经营利润率优秀")
            if qualifiers:
                lines.append("### 评价\n")
                for q in qualifiers:
                    lines.append(f"- {q}")
                lines.append("")
        elif oper_profit is None:
            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append("⚠️ The operating profit data is missing and the five-factor disassembly cannot be completed.")
            lines.append("*If the data source is Tushare and has just been repaired `operate_profit` Field mapping requires re-pulling data.*")
            lines.append("")
        else:
            lines.append("## Five Factor Breakdown (Extended Dupont)\n")
            lines.append("⚠️ The fields required for the five-factor split are abnormal (may have zero values or incomplete data).")
            lines.append("")

        # ── Multi-year trend ──
        raw = data.get("raw_data", {})
        inc_list = raw.get("income_statement", [])
        bs_list = raw.get("balance_sheet", [])

        if inc_list and bs_list:
            # Take annual report data for trends
            annual_inc = {}
            for rec in inc_list:
                end = str(rec.get('end_date', ''))
                if not end:
                    continue
                year = end[:4]
                if year not in annual_inc:
                    annual_inc[year] = rec

            annual_bs = {}
            for rec in bs_list:
                end = str(rec.get('end_date', ''))
                if not end:
                    continue
                year = end[:4]
                if year not in annual_bs:
                    annual_bs[year] = rec

            # Cross alignment
            common_years = sorted(set(annual_inc.keys()) & set(annual_bs.keys()), reverse=True)[:years]

            if len(common_years) >= 2:
                lines.append("## 杜邦因子年度趋势\n")
                lines.append("| annual | net profit margin | asset turnover rate | equity multiplier | ROE |")
                lines.append("|------|--------|------------|----------|-----|")
                for yr in common_years:
                    inc = annual_inc[yr]
                    bs = annual_bs[yr]
                    r = _coerce_float(inc.get('total_revenue') or inc.get('revenue'))
                    n = _coerce_float(inc.get('n_income') or inc.get('n_income_attr_p'))
                    ta = _coerce_float(bs.get('total_assets'))
                    eq = _coerce_float(bs.get('total_hldr_eqy_exc_min_int'))
                    if all([n, r, ta, eq]) and r != 0 and eq != 0:
                        n_pm = n / r * 100
                        a_t = r / ta
                        e_m = ta / eq
                        r_oe = n / eq * 100
                        lines.append(f"| {yr} | {n_pm:.1f}% | {a_t:.3f} | {e_m:.2f} | {r_oe:.2f}% |")
                lines.append("")

        lines.append("---")
        lines.append("*DuPont Analysis — ROE = net profit margin × asset turnover rate × equity multiplier*")
        lines.append(f"*Data source:Tushare | Calculated based on TTM data*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [DuPont Analysis] Execution failed: {e}")
        return f"❌ 杜邦分析执行失败: {e}"


# ============================================================
# Tool 6: Dividend share data
# ============================================================
@tool
@register_tool(
    tool_id="get_dividend_data",
    name="分红送股数据",
    description="Obtain the historical dividend and share record of the stock, including dividend per share, transfer ratio, dividend rate, etc.",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_dividend_data(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    years: Annotated[int, "Query the dividend records in recent years, default 5"] = 5
) -> str:
    """
    Dividend bonus data tool —— Get historical dividend records and dividend rates

    Analysis content: cash dividend per share, bonus share conversion ratio, dividend year, implementation progress, etc.
    need Tushare 2000+ Points authority.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        years: Query the dividend records in recent years, the default is 5 years

    Returns:
        str: Dividend share analysis report
    """
    logger.info(f"💰 [分红数据] 查询股票: {ticker}, 最近{years}年")
    try:
        provider = _get_tushare_provider()
        if not provider or not provider.is_available():
            return f"❌ Tushare 服务不可用，无法获取 {ticker} 的分红数据"

        # Call Tushare dividend API (use _run_async compatible worker thread)
        try:
            records = _run_async(provider.get_dividend_data(ticker, limit=years * 3))
        except Exception as e:
            logger.warning(f"⚠️ [Dividend data] Tushare call failed: {e}")
            return f"❌ 获取 {ticker} 分红数据失败: {e}（需要 Tushare 2000+ 积分权限）"

        if not records:
            return f"📊 {ticker} 暂无分红送股记录"

        lines = [f"# {ticker} 分红送股数据\n"]

        # Statistical overview
        implemented = [r for r in records if r.get('div_proc') == '实施']
        total_cash_div = sum(float(r.get('cash_div_tax', 0) or 0) for r in implemented)

        lines.append("## 📊 分红概览")
        lines.append(f"- **总记录数**: {len(records)} 条")
        lines.append(f"- **已实施分红**: {len(implemented)} 次")
        lines.append(f"- **累计每股分红（税前）**: {total_cash_div:.4f} 元")
        lines.append("")

        # Dividend details table
        lines.append("## 💰 分红明细")
        lines.append("| dividend year | Progress | Dividend per share(before tax) | Dividend per share(After tax) | Bonus shares per share | Conversion per share | ex-rights ex-dividend date |")
        lines.append("|---------|------|---------------|---------------|---------|---------|-----------|")
        for rec in records:
            end_date = rec.get('end_date', 'N/A')
            proc = rec.get('div_proc', 'N/A')
            cash_tax = _safe_val(rec.get('cash_div_tax'), ".4f")
            cash_after = _safe_val(rec.get('cash_div'), ".4f")
            stk_bo = _safe_val(rec.get('stk_bo_rate'), ".2f")
            stk_co = _safe_val(rec.get('stk_co_rate'), ".2f")
            ex_date = rec.get('ex_date') or 'N/A'
            lines.append(f"| {end_date} | {proc} | {cash_tax} | {cash_after} | {stk_bo} | {stk_co} | {ex_date} |")
        lines.append("")

        # Dividend trend analysis
        if len(implemented) >= 2:
            lines.append("## 📈 分红趋势")
            cash_vals = [float(r.get('cash_div_tax', 0) or 0) for r in implemented[:years]]
            if all(v > 0 for v in cash_vals):
                if cash_vals[0] >= cash_vals[-1]:
                    lines.append("- **Trend judgment**: ✅ The amount of dividends has generally increased or remained the same, and shareholders have a good awareness of returns.")
                else:
                    lines.append("- **Trend judgment**: 🟡 The amount of dividends has dropped recently, and we need to pay attention to the reasons.")
            elif any(v > 0 for v in cash_vals):
                lines.append("- **Trend judgment**: 🟡 Dividends are discontinuous and there are no cash dividends in some years.")
            else:
                lines.append("- **Trend judgment**: ⚠️ No record of cash dividends in recent years")
            lines.append("")

        lines.append("---")
        lines.append("*Data source: Tushare dividend API (Need 2000+ points authority)*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Dividend data] Execution failed: {e}")
        return f"❌ 分红数据查询失败: {e}"


# ============================================================
# Tool 7: Main business composition
# ============================================================
@tool
@register_tool(
    tool_id="get_main_business",
    name="主营业务构成",
    description="Obtain the main business structure of the stock and analyze the revenue source structure, and return structured data such as revenue proportion, gross profit margin, concentration, etc. by product/region segment",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_main_business(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    periods: Annotated[int, "Number of analysis periods (the most recent reporting periods), default 4"] = 4
) -> str:
    """
    Main business composition tools —— Analyze revenue sources and business structure

    Display the main business revenue structure by product/region dimension.

    Args:
        ticker: Stock code (e.g. 600519, 000001)
        periods: Number of analysis periods, default 4

    Returns:
        str: Main business composition analysis report
    """
    logger.info(f"📊 [Main business] Analyze stocks: {ticker}")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=periods)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        mainbz_list = raw.get("main_business", [])

        if not mainbz_list:
            return f"📊 {ticker} There is currently no main business composition data (some companies may not have disclosed it yet)"

        lines = [f"# {ticker} 主营业务构成\n"]

        # Group by reporting period
        from collections import defaultdict
        period_groups = defaultdict(list)
        for rec in mainbz_list:
            period = rec.get('end_date', 'N/A')
            period_groups[period].append(rec)

        # Display in descending order of reporting period
        sorted_periods = sorted(period_groups.keys(), reverse=True)

        for idx, period in enumerate(sorted_periods[:periods]):
            items = period_groups[period]
            # By product category and region
            products = [r for r in items if r.get('bz_item') and r.get('bz_sales') is not None]

            if not products:
                continue

            lines.append(f"## 📊 {period} 主营业务构成")

            # Calculate total revenue
            total_sales = sum(float(r.get('bz_sales', 0) or 0) for r in products)

            if total_sales > 0:
                lines.append(f"**总营业收入**: {_wan_yi(total_sales)}\n")
                lines.append("| Business/Products | operating income | operating costs | Gross profit margin | Revenue proportion |")
                lines.append("|----------|---------|---------|--------|---------|")

                # Sort by income
                sorted_items = sorted(products, key=lambda x: float(x.get('bz_sales', 0) or 0), reverse=True)
                for item in sorted_items:
                    name = item.get('bz_item', 'N/A')
                    sales = float(item.get('bz_sales', 0) or 0)
                    cost = float(item.get('bz_cost', 0) or 0)
                    profit = float(item.get('bz_profit', 0) or 0)

                    gm = f"{(profit / sales * 100):.1f}%" if sales > 0 else "N/A"
                    pct = f"{(sales / total_sales * 100):.1f}%" if total_sales > 0 else "N/A"

                    lines.append(f"| {name} | {_wan_yi(sales)} | {_wan_yi(cost)} | {gm} | {pct} |")

                lines.append("")
            else:
                lines.append("- 无有效数据\n")

        lines.append("---")
        lines.append("*Data source: Tushare fina_mainbz / MongoDB cache*")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Main business] Execution failed: {e}")
        return f"❌ Main business composition query failed: {e}"


# ============================================================
# Tool 8: Accounts Receivable Risk Analysis
# ============================================================
@tool
@register_tool(
    tool_id="get_accounts_receivable_risk_analyzer",
    name="应收账款风险分析",
    description="Three-dimensional assessment of accounts receivable risk: collection efficiency (turnover days), revenue quality (receivable-revenue growth rate deviation), accrual prudence (credit impairment loss trend), and cross-validation to generate a comprehensive risk rating",
    category="fundamentals",
    is_online=True,
    auto_register=True
)
def get_accounts_receivable_risk_analyzer(
    ticker: Annotated[str, "Stock code, 6 digits (such as 600519, 000001)"],
    years: Annotated[int, "Number of years to look back, default is 4 years"] = 4
) -> str:
    """
    Accounts Receivable Risk Analysis Tool —— Three-dimensional cross-validation

    Three dimensions:
    1. Collection efficiency: accounts receivable turnover days and changing trends
    2. Income quality: the deviation between the growth rate of accounts receivable and the growth rate of revenue
    3. Provision prudence: credit impairment losses/changes in accounts receivable, cross comparison of turnover days

    Comprehensive rules:
    - All three are normal → low risk
    - Single deterioration → Follow
    - Deterioration in turnover + Decline in provision → High risk (suspected of whitewashing)
    - All three worsen at the same time → extremely high risk

    Args:
        ticker: Stock code
        years: Look back years

    Returns:
        str: Accounts receivable risk analysis report
    """
    logger.info(f"📊 [应收账款风险分析] 分析股票: {ticker}, 回溯{years}年")
    try:
        data = _get_financial_data_from_cache_or_api(ticker, limit=years * 4 + 4)
        if not data:
            return f"❌ 未获取到 {ticker} 的财务数据"

        raw = data.get("raw_data", {})
        balance_list = raw.get("balance_sheet", [])
        income_list = raw.get("income_statement", [])
        indicator_list = raw.get("financial_indicators", [])

        # ---- Extract annual report data (get the last record for each year) ----
        def _extract_annual(records: list, fields: list) -> dict:
            """Extract the last record of each year from the quarter list and return {year: {field: value}}"""
            by_year: Dict[str, Dict[str, Any]] = {}
            for rec in records:
                end_date = str(rec.get('end_date', '') or rec.get('f_ann_date', ''))
                if not end_date:
                    continue
                year = end_date[:4]
                # For the same year, take the larger end_date (i.e. annual report)
                if year not in by_year or str(rec.get('end_date', '')) > str(by_year[year].get('end_date', '')):
                    by_year[year] = rec
            # Get the most recent years, in descending order of years
            sorted_years = sorted(by_year.keys(), reverse=True)[:years]
            result = {}
            for y in sorted_years:
                result[y] = {f: _coerce_float(by_year[y].get(f)) for f in fields}
            return result

        # Extract Balance Sheet Annual Report: Accounts Receivable
        ar_annual = _extract_annual(balance_list, ['accounts_receiv'])
        # Extract the income statement annual report: operating income, credit impairment losses
        income_annual = _extract_annual(income_list, ['revenue', 'credit_impa_loss', 'assets_impair_loss'])
        # Extract financial indicators from the annual report: accounts receivable turnover days
        indicator_annual = _extract_annual(indicator_list, ['arturn_days'])

        year_keys = sorted(set(list(ar_annual.keys()) + list(income_annual.keys())), reverse=True)[:years]

        # ---- Jump to missing data ----
        if len(year_keys) < 2:
            return f"📊 {ticker} Insufficient annual report data (requires at least 2 years) to conduct trend analysis"

        # ---- Build a year-by-year data table ----
        records = []
        for y in year_keys:
            ar_val = _coerce_float(ar_annual.get(y, {}).get('accounts_receiv'))
            rev_val = _coerce_float(income_annual.get(y, {}).get('revenue'))
            impa_val = _coerce_float(income_annual.get(y, {}).get('credit_impa_loss'))
            arturn_days_val = _coerce_float(indicator_annual.get(y, {}).get('arturn_days'))

            records.append({
                'year': y,
                'accounts_receiv': ar_val,
                'revenue': rev_val,
                'credit_impa_loss': impa_val,
                'arturn_days': arturn_days_val,
            })

        # ---- Calculate trend indicators ----
        def _safe_ratio(curr, prev) -> Optional[float]:
            if curr is not None and prev is not None and prev != 0:
                return (curr - prev) / abs(prev)
            return None

        # Calculate the turnover days of accounts receivable (self-calculated, verified against arturn_days)
        for i, rec in enumerate(records):
            if rec['accounts_receiv'] and rec['revenue'] and rec['revenue'] != 0:
                rec['ar_turnover_days_self'] = 365 * rec['accounts_receiv'] / rec['revenue']
            else:
                rec['ar_turnover_days_self'] = None

        # Calculate growth rate and deviation
        for i in range(len(records) - 1):
            curr, prev = records[i], records[i + 1]
            curr['ar_growth'] = _safe_ratio(curr['accounts_receiv'], prev['accounts_receiv'])
            curr['rev_growth'] = _safe_ratio(curr['revenue'], prev['revenue'])
            if curr['ar_growth'] is not None and curr['rev_growth'] is not None:
                curr['deviation'] = curr['ar_growth'] - curr['rev_growth']
            else:
                curr['deviation'] = None
            # Provision ratio
            if curr['credit_impa_loss'] is not None and curr['accounts_receiv'] is not None and curr['accounts_receiv'] != 0:
                curr['impa_ratio'] = curr['credit_impa_loss'] / curr['accounts_receiv']
            else:
                curr['impa_ratio'] = None

        # ---- Output report ----
        lines = [f"# {ticker} 应收账款风险三维分析\n"]

        # Overview of the latest issue
        latest = records[0]
        lines.append("## 📊 最新一期快照")
        lines.append(f"- **报告年度**: {latest['year']}")
        lines.append(f"- **应收账款**: {_wan_yi(latest['accounts_receiv'])}")
        lines.append(f"- **营业收入**: {_wan_yi(latest['revenue'])}")
        if latest['arturn_days'] is not None:
            lines.append(f"- **应收账款周转天数** (数据源): {latest['arturn_days']:.1f} 天")
        if latest.get('ar_turnover_days_self') is not None:
            lines.append(f"- **应收账款周转天数** (自算): {latest['ar_turnover_days_self']:.1f} 天")
        if latest.get('ar_growth') is not None:
            lines.append(f"- **应收账款增速**: {latest['ar_growth'] * 100:+.1f}% (同比)")
        if latest.get('rev_growth') is not None:
            lines.append(f"- **营收增速**: {latest['rev_growth'] * 100:+.1f}% (同比)")
        if latest.get('deviation') is not None:
            lines.append(f"- **增速偏离度**: {latest['deviation'] * 100:+.1f} 百分点（正值 = 应收跑赢营收，虚胖信号）")
        if latest.get('impa_ratio') is not None:
            lines.append(f"- **Credit impairment loss/accounts receivable**: {latest['impa_ratio'] * 100:.2f}%")
        lines.append("")

        # Year-by-year trend table
        lines.append("## 📈 逐年趋势")
        header = "| annual | Accounts receivable | operating income | Turnover days(source) | Turnover days(Calculate) | Growth rate of receivables | revenue growth | Deviation | Impairment/receivable |"
        lines.append(header)
        lines.append("|" + "|".join(["------"] * 9) + "|")
        for rec in records:
            ar = _wan_yi(rec['accounts_receiv'])
            rev = _wan_yi(rec['revenue'])
            atd = f"{rec['arturn_days']:.1f}" if rec['arturn_days'] is not None else "-"
            atds = f"{rec.get('ar_turnover_days_self'):.1f}" if rec.get('ar_turnover_days_self') is not None else "-"
            arg = f"{rec.get('ar_growth') * 100:+.1f}%" if rec.get('ar_growth') is not None else "-"
            revg = f"{rec.get('rev_growth') * 100:+.1f}%" if rec.get('rev_growth') is not None else "-"
            dev = f"{rec.get('deviation') * 100:+.1f}pp" if rec.get('deviation') is not None else "-"
            impa = f"{rec.get('impa_ratio') * 100:.2f}%" if rec.get('impa_ratio') is not None else "-"
            lines.append(f"| {rec['year']} | {ar} | {rev} | {atd} | {atds} | {arg} | {revg} | {dev} | {impa} |")
        lines.append("")

        # ---- Three-dimensional cross-risk assessment ----
        lines.append("## 🔍 三维风险评估")

        # Determine the status of each dimension
        def _assess_turnover(rec) -> tuple:
            """Determine the trend of turnover days:(direction, degree)"""
            atd = rec.get('arturn_days')
            if atd is None:
                return ("unknown", "数据缺失")
            # Compare with previous issue
            idx = records.index(rec)
            if idx < len(records) - 1:
                prev_atd = records[idx + 1].get('arturn_days')
                if prev_atd is not None:
                    change_pct = (atd - prev_atd) / prev_atd if prev_atd != 0 else 0
                    if change_pct > 0.15:
                        return ("worsening", f"大幅恶化 (+{change_pct * 100:.0f}%)")
                    elif change_pct > 0.05:
                        return ("worsening", f"轻微恶化 (+{change_pct * 100:.0f}%)")
                    elif change_pct < -0.05:
                        return ("improving", f"改善 ({change_pct * 100:.0f}%)")
                    else:
                        return ("stable", "基本稳定")
            # Absolute value judgment
            if atd > 365:
                return ("worsening", f"严重: {atd:.0f}天 (>1年)")
            elif atd > 180:
                return ("worsening", f"偏高: {atd:.0f}天")
            elif atd > 90:
                return ("stable", f"正常偏高: {atd:.0f}天")
            else:
                return ("stable", f"健康: {atd:.0f}天")

        def _assess_deviation(rec) -> tuple:
            dev = rec.get('deviation')
            if dev is None:
                return ("unknown", "数据缺失")
            if dev > 0.2:
                return ("worsening", f"大幅偏离 (+{dev * 100:.0f}pp)")
            elif dev > 0.1:
                return ("worsening", f"明显偏离 (+{dev * 100:.0f}pp)")
            elif dev > 0.05:
                return ("stable", f"轻微偏离 (+{dev * 100:.0f}pp)")
            else:
                return ("stable", "正常")

        def _assess_provision(rec) -> tuple:
            """Determine the prudence of provision: If the turnover deteriorates but the provision ratio decreases instead → suspected of whitewashing"""
            impa = rec.get('impa_ratio')
            if impa is None:
                # Check if there is assets_impair_loss as an alternative
                return ("unknown", "信用减值损失数据缺失")
            idx = records.index(rec)
            # Current accrual ratio
            curr_ratio = impa
            # Compare with previous issue
            if idx < len(records) - 1:
                prev_rec = records[idx + 1]
                prev_ratio = prev_rec.get('impa_ratio')
                prev_atd = prev_rec.get('arturn_days')
                curr_atd = rec.get('arturn_days')
                if prev_ratio is not None and curr_atd is not None and prev_atd is not None:
                    ratio_change = (curr_ratio - prev_ratio) / prev_ratio if prev_ratio != 0 else 0
                    atd_change = (curr_atd - prev_atd) / prev_atd if prev_atd != 0 else 0
                    # Core logic: turnover deterioration + Decline in provision = suspected of whitewashing
                    if atd_change > 0.05 and ratio_change < -0.1:
                        return ("worsening", f"⚠️ 粉饰嫌疑: 周转恶化({atd_change * 100:+.0f}%)但计提下降({ratio_change * 100:+.0f}%)")
                    elif atd_change > 0.05 and ratio_change > 0.1:
                        return ("stable", f"正常响应: 周转恶化({atd_change * 100:+.0f}%)→计提同步上升({ratio_change * 100:+.0f}%)")
                    elif atd_change < -0.05 and ratio_change < -0.1:
                        return ("stable", f"reasonable: Turnover improvement→Decline in provision")
                    else:
                        return ("stable", "基本稳定")
            return ("unknown", "缺少对比数据")

        # The latest assessment
        turnover_status, turnover_detail = _assess_turnover(latest)
        dev_status, dev_detail = _assess_deviation(latest)
        provision_status, provision_detail = _assess_provision(latest)

        # Aggregate signals
        signals = []
        if turnover_status == "worsening":
            signals.append(f"🔴 回收效率: {turnover_detail}")
        elif turnover_status == "stable":
            signals.append(f"🟡 回收效率: {turnover_detail}")
        else:
            signals.append(f"⬜ 回收效率: {turnover_detail}")

        if dev_status == "worsening":
            signals.append(f"🔴 收入质量: {dev_detail}")
        elif dev_status == "stable":
            signals.append(f"🟡 收入质量: {dev_detail}")
        else:
            signals.append(f"⬜ 收入质量: {dev_detail}")

        if provision_status == "worsening":
            signals.append(f"🔴 计提审慎性: {provision_detail}")
        elif provision_status == "stable":
            signals.append(f"🟢 计提审慎性: {provision_detail}")
        else:
            signals.append(f"⬜ 计提审慎性: {provision_detail}")

        for s in signals:
            lines.append(f"- {s}")

        # Overall rating
        worsening_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "worsening")
        stable_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "stable")
        unknown_count = sum(1 for status in [turnover_status, dev_status, provision_status] if status == "unknown")

        lines.append("")
        lines.append("## 🏷️ 综合风险评级")

        if worsening_count == 0 and unknown_count == 0:
            lines.append("> ✅ **low risk** — All three indicators are normal, and the quality of accounts receivable is healthy.")
        elif worsening_count == 1:
            if turnover_status == "worsening":
                lines.append("> ⚠️ **Concern (recycling deterioration)** — The speed of repayment is declining. Pay attention to the customer s repayment ability and changes in credit policies.")
            elif dev_status == "worsening":
                lines.append("> ⚠️ **Attention (income quality issues)** — The expansion of accounts receivable exceeds revenue growth, and there may be aggressive behavior in revenue recognition.")
            else:
                lines.append("> ⚠️ **Attention (accrual issues)** — Abnormal accrual behavior")
        elif worsening_count == 2:
            if turnover_status == "worsening" and provision_status == "worsening":
                lines.append("> 🔴 **high risk — Suspected of financial whitewashing** — Receipts worsen + Provisions fell instead of rising. The company may be deliberately lowering impairments to beautify profits.")
            elif turnover_status == "worsening" and dev_status == "worsening":
                lines.append("> 🔴 **high risk — double aggravation** — The quality of income has declined and it is difficult to collect payments, and operating cash flow has been under pressure.")
            elif dev_status == "worsening" and provision_status == "worsening":
                lines.append("> 🔴 **high risk — Income puffiness + Insufficient provision** — While receivables are inflated, impairment provisions are insufficient, and the credibility of the income statement is questionable.")
            else:
                lines.append("> 🔴 **high risk** — Two indicators have deteriorated and need to be focused on")
        elif worsening_count == 3:
            lines.append("> 🔴🔴 **extremely high risk — perfect storm** — Recovery, income quality, and accrual are all deteriorating at the same time, so we need to be highly vigilant about the possibility of financial fraud.")
        elif unknown_count >= 2:
            lines.append("> ⬜ **Not enough data** — Key fields are missing and a complete evaluation cannot be completed. It is recommended to check the data source.")
        else:
            lines.append("> 🟡 **Unable to determine** — Please evaluate manually based on specific indicators.")

        lines.append("")
        lines.append("---")
        lines.append("*Description: Growth rate deviation = Receivable growth rate - revenue growth rate, a positive value means that accounts receivable are expanding faster than revenue growth, which is'Wealth on paper'signal*")
        lines.append("*Provision prudence = Credit impairment loss/accounts receivable. When turnover deteriorates, this ratio should rise simultaneously. If it deviates, it will be suspected of whitewashing.*")
        lines.append("*Data source: Tushare / MongoDB cache*")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"❌ [Accounts Receivable Risk Analysis] Execution failed: {e}", exc_info=True)
        return f"❌ Accounts receivable risk analysis failed: {e}"
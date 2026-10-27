"""Management evaluation data acquisition tool - A-share audit opinions, information disclosure ratings, equity incentives, violation penalties

stk_audit / disclosure_rating / equity_incentive / stk_penalty interface based on Tushare Provider
"""

import asyncio
import json
import logging
import threading
from typing import Optional

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _ticker_to_ts_code(ticker: str) -> str:
    """Convert general ticker to Tushare ts_code format"""
    ticker = str(ticker).strip()
    if "." in ticker:
        return ticker  # Already in ts_code format
    # Pure numbers, judged based on the market
    if ticker.startswith("6"):
        return f"{ticker}.SH"
    elif ticker.startswith(("0", "3")):
        return f"{ticker}.SZ"
    return f"{ticker}.SH"


def _run_async_in_thread(coro, timeout: int = 30):
    """在独立线程中运行异步协程"""
    container = {"result": None, "error": None}

    def _run():
        try:
            container["result"] = asyncio.run(coro)
        except Exception as exc:
            container["error"] = exc

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=timeout)
    if "error" in container and container["error"] is not None:
        raise container["error"]
    return container["result"]


@tool
@register_tool(
    tool_id="get_audit_opinion",
    name="审计意见查询",
    description="Obtain the type of historical audit opinions of A-share companies (standard unqualified/emphasized matters/qualified/negative/unable to express), audit institutions, audit fees, etc., to evaluate financial integrity",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["审计", "审计意见", "审计机构", "财务诚信", "A股", "管理层"],
    when_to_use="Used when assessing management s financial integrity, checking for abnormalities in audit opinions, and judging the reliability of financial information.",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_audit_opinion(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain audit opinions from A-share companies

    Args:
        ticker: Stock code, such as 600519,000001
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_audit_opinion(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到审计意见数据",
                "records": [],
                "latest_opinion": "未知",
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "报告期": str(row.get("end_date", row.get("报告期", ""))),
                "审计意见": str(row.get("audit_result", row.get("审计结果", ""))),
                "审计机构": str(row.get("audit_company", row.get("审计机构", ""))),
                "审计费用(元)": row.get("audit_fees", row.get("审计费用", "")),
            }
            records.append(rec)

        latest = records[0]["审计意见"] if records else "未知"
        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "total_records": len(records),
            "latest_opinion": latest,
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 审计意见查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_disclosure_rating",
    name="信息披露评级查询",
    description="Obtain the exchange s annual evaluation results (A/B/C/D) on A-share companies information disclosure to evaluate corporate governance transparency",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["信息披露", "信披评级", "公司治理", "透明度", "A股", "管理层"],
    when_to_use="Used when assessing the quality of company information disclosure and checking exchange information disclosure evaluation records.",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_disclosure_rating(
    ticker: str = "600519",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain exchange information disclosure evaluation results

    Args:
        ticker: Stock code, such as 600519
        end_date: Closing reporting period
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_disclosure_rating(
                ts_code=ts_code,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到信息披露评级数据",
                "records": [],
                "latest_rating": "未知",
            }, ensure_ascii=False)

        # Tushare disclosure_rating Return fields:ts_code, end_date, announcement_date, disclosure_result
        records = []
        for _, row in df.iterrows():
            rec = {
                "考评年度": str(row.get("end_date", row.get("考评年度", ""))),
                "考评结果": str(row.get("disclosure_result", row.get("考评结果", ""))),
            }
            records.append(rec)

        latest = records[0]["考评结果"] if records else "未知"
        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "total_records": len(records),
            "latest_rating": latest,
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ Information disclosure rating query failed: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_equity_incentive",
    name="股权激励计划查询",
    description="Obtain the details of the A-share company s equity incentive plan (incentive plan, grant price, exercise conditions, incentive period, proportion of total equity) to evaluate the rationality of management incentives",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["股权激励", "激励计划", "行权条件", "管理层激励", "A股", "管理层"],
    when_to_use="Used when assessing the rationality of management s equity incentives, checking incentive coverage and exercise conditions, and judging the impact of incentive plans on shareholder interests.",
    tool_role_hint="specialized",
    output_shape="structured_records",
)
def get_equity_incentive(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Get Equity Incentive Plan Details

    Args:
        ticker: Stock code, such as 600519
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_equity_incentive(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "未查询到股权激励计划数据",
                "has_incentive_plan": False,
                "records": [],
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "激励方案": str(row.get("inc_plan", row.get("激励方案", ""))),
                "授予数量(万股)": str(row.get("grant_num", row.get("授予数量", ""))),
                "授予价格": str(row.get("grant_price", row.get("授予价格", ""))),
                "激励年限": str(row.get("inc_duration", row.get("激励年限", ""))),
                "行权条件": str(row.get("inc_perf", row.get("行权条件", ""))),
                "总股本占比": str(row.get("stockholder_rt", row.get("总股本占比", ""))),
            }
            records.append(rec)

        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "has_incentive_plan": True,
            "total_plans": len(records),
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 股权激励查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)


@tool
@register_tool(
    tool_id="get_management_penalties",
    name="管理层违规处罚查询",
    description="Obtain the historical violation penalty records of A-share companies and their management (penalty type, penalty object, penalty amount, violation reasons) to assess management behavioral risks",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    capability_tags=["违规", "处罚", "管理层", "监管", "行为风险", "A股", "管理层"],
    when_to_use="Used when assessing management s historical behavioral risks, checking violation penalty records, and judging the company s compliance culture",
    tool_role_hint="primary",
    output_shape="structured_records",
)
def get_management_penalties(
    ticker: str = "600519",
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> str:
    """Obtain management violation penalty records

    Args:
        ticker: Stock code, such as 600519
        start_date: start date
        end_date: Deadline
    """
    try:
        from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

        provider = get_tushare_provider()
        if not provider.is_available():
            return json.dumps({"error": "Tushare Not available (Token is not configured or library is not installed)", "ticker": ticker}, ensure_ascii=False)

        ts_code = _ticker_to_ts_code(ticker)

        async def _fetch():
            return await provider.get_management_penalties(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        df = _run_async_in_thread(_fetch())

        if df is None or df.empty:
            return json.dumps({
                "ticker": ticker,
                "ts_code": ts_code,
                "message": "No violation penalty records found (no violation records in the past 5 years, a positive sign)",
                "has_penalties": False,
                "total_records": 0,
                "records": [],
            }, ensure_ascii=False)

        records = []
        for _, row in df.iterrows():
            rec = {
                "公告日期": str(row.get("ann_date", row.get("公告日期", ""))),
                "处罚类型": str(row.get("punish_type", row.get("处罚类型", ""))),
                "处罚对象": str(row.get("punish_object", row.get("处罚对象", ""))),
                "违规类型": str(row.get("violat_type", row.get("违规类型", ""))),
                "违规事由": str(row.get("violate_content", row.get("违规事由", "")))[:300],
                "处罚金额(万元)": str(row.get("punish_amount", row.get("处罚金额", ""))),
            }
            records.append(rec)

        return json.dumps({
            "ticker": ticker,
            "ts_code": ts_code,
            "has_penalties": True,
            "total_records": len(records),
            "records": records,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ 违规处罚查询失败: {e}")
        return json.dumps({"error": str(e), "ticker": ticker}, ensure_ascii=False)

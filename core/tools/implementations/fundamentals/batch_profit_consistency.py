"""
Batch profit stability verification tool

once $in Query stock_financial_periods and calculate the stability of ROE / net profit in the past N years,
Avoid issuing N separate queries for each stock, greatly improving efficiency.
"""

import json
import logging
import math
from typing import Annotated, List, Dict, Any

from langchain_core.tools import tool
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

MAX_DETAIL_PER_GROUP = 5


@tool
@register_tool(
    tool_id="batch_check_profit_consistency",
    name="批量验证盈利稳定性",
    description=(
        "Verify the stability of ROE/net profit of multiple stocks in the past N years in batches, and return the earnings stability assessment of all stocks in one query."
        "Input the stock code list (JSON array) and the number of years of testing, and return the stability conclusion (stable/unstable) of each stock,"
        "coefficient of variation (CV=Standard deviation/mean) and ROE data in the past N years."
        "It is used for secondary verification of profit quality of candidate stocks after batch screening, and the efficiency is much higher than stock-by-stock query."
    ),
    category="screening",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["profit_consistency", "batch_screening", "roe", "profitability", "stability", "screening", "earnings_quality"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["batch_profitability_screening", "earnings_stability_verification", "roe_consistency_check"],
    data_source_handling="local_only",
)
async def batch_check_profit_consistency(
    stock_codes_json: Annotated[
        str,
        'Stock code JSON array, such as ["000001", "600519", "000858"]',
    ],
    years: Annotated[int, "Number of years for inspection, default is 3 years (only annual report data is taken)"] = 3,
    threshold_cv: Annotated[
        float,
        "The coefficient of variation threshold. If it exceeds the threshold, it is determined to be unstable. The default is 0.3 (i.e. fluctuation > 30% of the mean)",
    ] = 0.3,
) -> str:
    """Verify the profitability stability of multiple stocks in the past N years in batches (once $in query, efficient)"""
    try:
        codes = json.loads(stock_codes_json)
        if not isinstance(codes, list) or len(codes) == 0:
            return "Error: stock_codes_json must be a non-empty JSON array."
        if len(codes) > 200:
            return "Error: A maximum of 200 stocks can be verified at a time, please submit in batches."
        years = max(2, min(years, 10))
    except json.JSONDecodeError as e:
        return f"Error: stock_codes_json is not in the correct format:{e}"

    return await _async_check(codes, years, threshold_cv)


def _build_annual_roe_pipeline(codes: List[str]) -> List[Dict[str, Any]]:
    return [
        {
            "$addFields": {
                "normalized_code": {"$ifNull": ["$code", "$symbol"]},
                "effective_roe": {
                    "$ifNull": [
                        "$financial_indicators.roe",
                        "$roe",
                    ]
                },
                "has_roe": {
                    "$cond": [
                        {
                            "$ne": [
                                {
                                    "$ifNull": [
                                        "$financial_indicators.roe",
                                        "$roe",
                                    ]
                                },
                                None,
                            ]
                        },
                        1,
                        0,
                    ]
                },
            }
        },
        {
            "$match": {
                "normalized_code": {"$in": codes},
                "report_type": "annual",
            }
        },
        {
            "$sort": {
                "normalized_code": 1,
                "report_period": -1,
                "has_roe": -1,
                "ann_date": -1,
                "updated_at": -1,
            }
        },
        {
            "$group": {
                "_id": {
                    "code": "$normalized_code",
                    "report_period": "$report_period",
                },
                "roe": {"$first": "$effective_roe"},
                "period": {"$first": "$report_period"},
            }
        },
        {"$match": {"roe": {"$ne": None}}},
        {"$sort": {"_id.code": 1, "period": -1}},
        {
            "$group": {
                "_id": "$_id.code",
                "roe_list": {"$push": "$roe"},
                "periods": {"$push": "$period"},
            }
        },
    ]


async def _async_check(
    codes: List[str],
    years: int,
    threshold_cv: float,
) -> str:
    from app.core.database import init_database, get_mongo_db

    try:
        await init_database()
    except Exception:
        pass

    db = get_mongo_db()
    collection = db["stock_financial_periods"]
    pipeline = _build_annual_roe_pipeline(codes)

    results_map: Dict[str, Any] = {}
    async for doc in collection.aggregate(pipeline):
        code = doc["_id"]
        all_roe = [v for v in doc.get("roe_list", []) if v is not None]
        all_periods = doc.get("periods", [])

        roe_values = all_roe[:years]
        periods_used = all_periods[:years]

        results_map[code] = {
            "roe_values": roe_values,
            "periods": periods_used,
        }

    return _format_results(codes, results_map, years, threshold_cv)


def _cv(values: List[float]) -> float:
    """coefficient of variation = Standard deviation / absolute value of the mean (to prevent division by zero if the mean is close to 0)"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if abs(mean) < 1e-9:
        return 999.0  # The mean value is close to 0, which is considered extremely unstable.
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return std / abs(mean)


def _build_detail_line(
    code: str,
    roe_values: List[float],
    periods: List[str],
    cv_val: float,
    threshold_cv: float,
    all_positive: bool,
    is_stable: bool,
) -> str:
    actual_years = len(roe_values)
    roe_str = " / ".join(f"{v:.1f}%" for v in roe_values)
    periods_str = " / ".join(p[:4] for p in periods)

    if is_stable:
        return (
            f"  ✅ {code}：稳定 | CV={cv_val:.2f} | ROE连续为正=是"
            f" | near{actual_years}year ROE({periods_str}): {roe_str}"
        )

    reasons = []
    if cv_val > threshold_cv:
        reasons.append(f"CV={cv_val:.2f}>{threshold_cv:.0%}")
    if not all_positive:
        reasons.append("ROE含负值")
    reason_text = " / ".join(reasons) if reasons else "波动偏大"
    return (
        f"  ❌ {code}：不稳定 | {reason_text}"
        f" | near{actual_years}year ROE({periods_str}): {roe_str}"
    )


def _append_group_preview(lines: List[str], title: str, entries: List[str], total_count: int) -> None:
    if not entries:
        return
    lines.append(title)
    lines.extend(entries[:MAX_DETAIL_PER_GROUP])
    if total_count > len(entries[:MAX_DETAIL_PER_GROUP]):
        lines.append(f"  ... 其余 {total_count - len(entries[:MAX_DETAIL_PER_GROUP])} 只已省略详细展开")
    lines.append("")


def _format_results(
    codes: List[str],
    results_map: Dict[str, Any],
    years: int,
    threshold_cv: float,
) -> str:
    lines = [
        f"共验证 {len(codes)} 只股票近 {years} 年盈利稳定性（变异系数阈值 ≤ {threshold_cv:.0%}）。",
        "The results have been condensed into a summary summary; if you need to continue filtering, please use the code list below first.",
        "",
    ]

    stable_codes, volatile_codes, no_data_codes = [], [], []
    stable_details: List[str] = []
    volatile_details: List[str] = []

    for code in codes:
        data = results_map.get(code)
        if not data or len(data.get("roe_values", [])) < years:
            no_data_codes.append(code)
            continue

        roe_values = data["roe_values"]
        periods = data["periods"]
        cv_val = _cv(roe_values)
        all_positive = all(v > 0 for v in roe_values)

        # Determine stability: CV required ≤ threshold and ROE is continuously positive
        is_stable = (cv_val <= threshold_cv) and all_positive

        if is_stable:
            stable_codes.append(code)
            stable_details.append(
                _build_detail_line(
                    code, roe_values, periods, cv_val, threshold_cv, all_positive, is_stable=True
                )
            )
        else:
            volatile_codes.append(code)
            volatile_details.append(
                _build_detail_line(
                    code, roe_values, periods, cv_val, threshold_cv, all_positive, is_stable=False
                )
            )

    lines.append(f"📊 汇总：稳定 {len(stable_codes)} 只 | 不稳定 {len(volatile_codes)} 只 | 无数据 {len(no_data_codes)} 只")
    lines.append("")

    _append_group_preview(lines, "Stable example:", stable_details, len(stable_codes))
    _append_group_preview(lines, "Unstable example:", volatile_details, len(volatile_codes))

    if stable_codes:
        lines.append(f"✅ Stable stock code:{', '.join(stable_codes)}")
    if volatile_codes:
        lines.append(f"❌ Unstable stock code:{', '.join(volatile_codes)}")
    if no_data_codes:
        lines.append(f"⚪ No data stock code:{', '.join(no_data_codes)}")

    return "\n".join(lines)


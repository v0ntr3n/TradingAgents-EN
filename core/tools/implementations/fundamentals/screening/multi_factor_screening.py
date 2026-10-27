"""Multi-factor stock picking tool.

Screen and score the entire A-share market based on user-specified factor conditions (PE, ROE, asset-liability ratio, etc.).
"""

import json
import logging
from typing import Annotated, Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from core.skill_runtime.data_access import get_stock_financial_periods
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

# The upper limit of the candidate pool (the top N based on total market value are only used as screening candidates)
MAX_CANDIDATES = 500
DEFAULT_LIMIT = 30

# Supported factors and their field names in the data
SUPPORTED_FACTORS = {
    "pe_ttm": {"label": "市盈率(TTM)", "source": "basic_info", "fields": ["pe_ttm", "pe"]},
    "pb": {"label": "市净率", "source": "basic_info", "fields": ["pb", "pb_mrq"]},
    "ps_ttm": {"label": "市销率(TTM)", "source": "basic_info", "fields": ["ps_ttm", "ps"]},
    "total_mv": {"label": "总市值", "source": "basic_info", "fields": ["total_mv"]},
    "roe": {"label": "净资产收益率", "source": "financial", "fields": ["roe", "roe_avg", "roe_waa"]},
    "roa": {"label": "总资产收益率", "source": "financial", "fields": ["roa", "roa2"]},
    "debt_to_assets": {"label": "资产负债率", "source": "financial", "fields": ["debt_to_assets"]},
    "gross_margin": {"label": "毛利率", "source": "financial", "fields": ["grossprofit_margin", "gross_margin"]},
    "netprofit_margin": {"label": "净利率", "source": "financial", "fields": ["netprofit_margin"]},
    "current_ratio": {"label": "流动比率", "source": "financial", "fields": ["current_ratio"]},
}


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


def _get_field(record: Dict[str, Any], *field_names: str) -> Optional[float]:
    """Attempts to get field values from records in order of priority."""
    for field_name in field_names:
        value = _safe_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _parse_criteria(criteria_json: str) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    """Parse filter condition JSON and return (conditional dictionary, warning list). """
    warnings: List[str] = []
    try:
        raw = json.loads(criteria_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Conditional JSON parsing failed: {exc}")

    if not isinstance(raw, dict):
        raise ValueError("The condition must be a JSON object, such as {\"pe_ttm\": {\"min\": 0, \"max\": 20}}")

    parsed: Dict[str, Dict[str, float]] = {}
    for factor_key, constraints in raw.items():
        if factor_key not in SUPPORTED_FACTORS:
            warnings.append(f"不支持因子 '{factor_key}'，已忽略。支持: {', '.join(SUPPORTED_FACTORS)}")
            continue
        if not isinstance(constraints, dict):
            warnings.append(f"因子 '{factor_key}' 的条件格式错误，已忽略")
            continue
        parsed[factor_key] = {}
        for op_key in ("min", "max"):
            if op_key in constraints:
                try:
                    parsed[factor_key][op_key] = float(constraints[op_key])
                except (TypeError, ValueError):
                    warnings.append(f"因子 '{factor_key}' 的 {op_key} 值不是有效数值，已忽略")

    if not parsed:
        raise ValueError("未解析出任何有效条件")

    return parsed, warnings


def _fetch_candidate_universe() -> List[Dict[str, Any]]:
    """Get the candidate stock pool from stock_basic_info (take the top N by market capitalization and PE>0) . """
    db = _get_db()
    col = db["stock_basic_info"]

    cursor = col.find(
        {
            "total_mv": {"$gt": 0, "$exists": True},
            "pe_ttm": {"$gt": 0, "$exists": True},
        },
        {
            "_id": 0,
            "symbol": 1,
            "name": 1,
            "industry": 1,
            "pe_ttm": 1,
            "pe": 1,
            "pb": 1,
            "pb_mrq": 1,
            "ps_ttm": 1,
            "ps": 1,
            "total_mv": 1,
        },
    ).sort("total_mv", -1).limit(MAX_CANDIDATES)

    return list(cursor)


def _enrich_with_financials(stocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Supplement the most recent financial metrics (ROE, debt-to-asset ratio, etc.) for each stock."""
    enriched: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        symbol = str(stock.get("symbol") or "").strip().zfill(6)
        if not symbol:
            continue

        # Copy from existing fields in basic_info
        enriched[symbol] = {
            "symbol": symbol,
            "name": stock.get("name", ""),
            "industry": stock.get("industry", ""),
            "pe_ttm": _get_field(stock, "pe_ttm", "pe"),
            "pb": _get_field(stock, "pb", "pb_mrq"),
            "ps_ttm": _get_field(stock, "ps_ttm", "ps"),
            "total_mv": _safe_float(stock.get("total_mv")),
        }

        # Obtain financial cycle data to supplement ROE, asset-liability ratio, etc.
        try:
            periods = get_stock_financial_periods(symbol, limit=1)
            if periods and isinstance(periods, list) and len(periods) > 0:
                latest = periods[0]
                roe = _get_field(latest, "roe", "roe_avg", "roe_waa")
                if roe is not None:
                    enriched[symbol]["roe"] = roe

                debt_to_assets = _get_field(latest, "debt_to_assets")
                if debt_to_assets is not None:
                    enriched[symbol]["debt_to_assets"] = debt_to_assets

                gross_margin = _get_field(latest, "grossprofit_margin", "gross_margin")
                if gross_margin is not None:
                    enriched[symbol]["gross_margin"] = gross_margin

                netprofit_margin = _get_field(latest, "netprofit_margin")
                if netprofit_margin is not None:
                    enriched[symbol]["netprofit_margin"] = netprofit_margin

                roa = _get_field(latest, "roa", "roa2")
                if roa is not None:
                    enriched[symbol]["roa"] = roa

                current_ratio = _get_field(latest, "current_ratio")
                if current_ratio is not None:
                    enriched[symbol]["current_ratio"] = current_ratio

        except Exception:
            pass  # Missing financial data does not block screening

    return enriched


def _get_factor_value(
    stock: Dict[str, Any],
    factor_key: str,
) -> Optional[float]:
    """Gets the value of the specified factor from stock data."""
    factor_def = SUPPORTED_FACTORS.get(factor_key)
    if not factor_def:
        return None
    return _get_field(stock, *factor_def["fields"])


def _normalize_score(value: float, min_val: float, max_val: float) -> float:
    """Values are normalized to a scale of 0-100."""
    if max_val <= min_val:
        return 50.0
    clipped = max(min_val, min(max_val, value))
    return (clipped - min_val) / (max_val - min_val) * 100.0


def _score_stock(
    stock: Dict[str, Any],
    criteria: Dict[str, Dict[str, float]],
) -> Tuple[float, Dict[str, Any], List[str]]:
    """Score individual stocks.

    Returns:
        (total score, Scores and indicators for each factor, warning list)
    """
    all_warnings: List[str] = []
    factor_scores: Dict[str, Any] = {}
    score_sum = 0.0
    valid_factors = 0

    for factor_key, constraints in criteria.items():
        value = _get_factor_value(stock, factor_key)
        factor_label = SUPPORTED_FACTORS.get(factor_key, {}).get("label", factor_key)

        if value is None:
            all_warnings.append(f"{stock.get('symbol', '')} 缺少 {factor_label}")
            factor_scores[factor_key] = {"value": None, "score": 0, "passed": False}
            continue

        factor_scores[factor_key] = {"value": round(value, 4)}

        # Check if conditions are met
        passed = True
        min_val = constraints.get("min")
        max_val = constraints.get("max")

        if min_val is not None and value < min_val:
            passed = False
        if max_val is not None and value > max_val:
            passed = False

        factor_scores[factor_key]["passed"] = passed

        if not passed:
            factor_scores[factor_key]["score"] = 0
            continue

        # Calculate normalized score
        norm_min = min_val if min_val is not None else 0.0
        norm_max = max_val if max_val is not None else value * 2.0
        if min_val is None and max_val is not None:
            norm_min = 0.0
        if max_val is None and min_val is not None:
            norm_max = min_val * 2.0

        score = _normalize_score(value, norm_min, norm_max) if norm_max > norm_min else 50.0
        factor_scores[factor_key]["score"] = round(score, 1)
        score_sum += score
        valid_factors += 1

    total_score = round(score_sum / max(valid_factors, 1), 1)
    return total_score, factor_scores, all_warnings


@tool
@register_tool(
    tool_id="get_multi_factor_screening",
    name="多因子选股",
    description=(
        "Screen stocks from the entire A-share market based on user-specified multi-factor conditions and score each stock."
        "Supported factors: pe_ttm (price-to-earnings ratio), pb (price-to-book ratio), ps_ttm (price-to-sales ratio),"
        "total_mv (total market capitalization), roe (return on net assets), roa (return on total assets),"
        "debt_to_assets (Asset-liability ratio), gross_margin (gross profit margin),"
        "netprofit_margin (net interest rate), current_ratio (current ratio)."
        "The conditional format is JSON, such as {\"pe_ttm\": {\"min\": 0, \"max\": 20}, \"roe\": {\"min\": 15}}. "
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=["screening", "multi_factor", "fundamentals"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["多因子条件选股", "全市场批量筛选", "因子评分排序"],
    when_to_use=(
        "Use it when you need to screen stocks from the entire market based on multiple fundamental factors."
        "For example:PE<20 and ROE>15% And the debt-to-asset ratio<50%. "
        "The candidate pool selects the top 500 stocks based on total market capitalization."
    ),
    when_not_to_use=(
        "Not suitable for querying the detailed fundamental factors of a single stock (please use get_fundamental_factor_snapshot_tool);"
        "Not suitable for technical indicator stock selection or K-line pattern screening."
    ),
    returns=(
        "Returns a JSON string, including criteria_applied (applied conditions), total_screened (total number of candidates),"
        "passed (Number of passes), results (ranking list, including each factor score and total score), data_quality (data description)."
    ),
    example=(
        'get_multi_factor_screening(criteria=\'{"pe_ttm": {"min": 0, "max": 20}, '
        '"roe": {"min": 15}, "debt_to_assets": {"max": 50}}\')'
    ),
    related_tools=[
        "screen_stocks_by_criteria",
        "get_fundamental_factor_snapshot_tool",
        "get_value_factor_bundle_tool",
    ],
)
def get_multi_factor_screening(
    criteria: Annotated[str, "Factor condition JSON string, e.g. '{\"pe_ttm\": {\"min\": 0, \"max\": 20}, \"roe\": {\"min\": 15}}'"],
    sort_by: Annotated[str, "Sorting fields: score (total score), pe_ttm, pb, roe, total_mv, default score"] = "score",
    limit: Annotated[int, "Returns the top N stocks, default 30"] = DEFAULT_LIMIT,
) -> str:
    """Multi-factor stock picking tool.

    Screen the stocks that meet the multi-factor conditions from the entire A-share market (the top 500 stocks based on total market value are taken as the candidate pool),
    and calculate the overall score.

    Args:
        criteria: factor conditions JSON
        sort_by: sort field
        limit: Return quantity

    Returns:
        JSON Filter results in string format
    """
    try:
        limit = max(1, min(int(limit), 100))

        # 1. parsing conditions
        parsed_criteria, parse_warnings = _parse_criteria(criteria)

        # 2. Get candidate pool
        raw_candidates = _fetch_candidate_universe()
        total_candidates = len(raw_candidates)

        if total_candidates == 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No valid candidate stocks were obtained from stock_basic_info",
                },
                ensure_ascii=False,
                default=str,
            )

        # 3. Supplementary financial data
        enriched = _enrich_with_financials(raw_candidates)

        # 4. Rating and filtering
        scored_results: List[Dict[str, Any]] = []
        all_warnings: List[str] = list(parse_warnings)

        for symbol, stock_data in enriched.items():
            total_score, factor_scores, stock_warnings = _score_stock(stock_data, parsed_criteria)
            all_warnings.extend(stock_warnings)

            # Check if all conditions are met (hard filtering)
            all_passed = all(
                fs.get("passed", False) for fs in factor_scores.values()
            )

            if all_passed:
                metrics = {
                    "pe_ttm": stock_data.get("pe_ttm"),
                    "pb": stock_data.get("pb"),
                    "total_mv": stock_data.get("total_mv"),
                }
                # Supplementary financial indicators
                for fin_key in ("roe", "roa", "debt_to_assets", "gross_margin", "netprofit_margin", "current_ratio"):
                    if fin_key in stock_data:
                        metrics[fin_key] = stock_data[fin_key]

                scored_results.append({
                    "symbol": symbol,
                    "name": stock_data.get("name", ""),
                    "industry": stock_data.get("industry", ""),
                    "score": total_score,
                    "factor_scores": factor_scores,
                    "metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items() if v is not None},
                })

        # 5. sort
        reverse = True
        if sort_by in ("pe_ttm",):
            reverse = False  # The lower the valuation, the better

        if sort_by == "score":
            scored_results.sort(key=lambda x: x["score"], reverse=True)
        elif sort_by == "pe_ttm":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("pe_ttm", float("inf")),
                reverse=reverse,
            )
        elif sort_by == "pb":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("pb", float("inf")),
                reverse=reverse,
            )
        elif sort_by == "roe":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("roe", 0),
                reverse=True,
            )
        elif sort_by == "total_mv":
            scored_results.sort(
                key=lambda x: x.get("metrics", {}).get("total_mv", 0),
                reverse=True,
            )

        top_results = scored_results[:limit]

        # 6. Build output
        ranked_results = []
        for rank, item in enumerate(top_results, 1):
            ranked_results.append({
                "rank": rank,
                "symbol": item["symbol"],
                "name": item["name"],
                "industry": item["industry"],
                "score": item["score"],
                "factor_scores": item["factor_scores"],
                "metrics": item["metrics"],
            })

        payload = {
            "criteria_applied": {
                k: {op: round(v, 4) if isinstance(v, float) else v for op, v in constraints.items()}
                for k, constraints in parsed_criteria.items()
            },
            "total_screened": total_candidates,
            "passed": len(scored_results),
            "returned": len(ranked_results),
            "sort_by": sort_by,
            "results": ranked_results,
            "data_quality": {
                "candidates_examined": total_candidates,
                "financial_data_enriched": len(enriched),
                "warnings": all_warnings[:20],  # Truncate too long warning
                "note": (
                    "The candidate pool is the top 500 A-shares sorted by total market capitalization (pe_ttm>0 and total_mv>0) . "
                    "ROE, Financial indicators such as asset-liability ratio are obtained from the latest financial report, which may be incomplete due to data synchronization delays."
                ),
            },
        }

        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    except ValueError as ve:
        return json.dumps({"status": "error", "message": str(ve)}, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("多因子选股失败: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2, default=str)


__all__ = ["get_multi_factor_screening"]

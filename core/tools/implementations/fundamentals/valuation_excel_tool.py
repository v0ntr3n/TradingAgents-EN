"""Valuation calculation form generation tool (A10-D2)

Declaratively callable deterministic deliverable tools for smart assistants:
  Data automatic assembly (valuation_bundle_builder)
  → LLM Generate model specifications (valuation_spec_generator)
  → Excel rendering + File verification (valuation_excel)

The fixed analysis process has zero changes; the tool returns Markdown (including download link and data source statement).
"""

import logging
import time
from typing import Annotated

from langchain_core.tools import tool

from core.deliverables.valuation_bundle_builder import ValuationDataError, build_valuation_bundle
from core.deliverables.valuation_excel import (
    render_valuation_excel,
    validate_valuation_excel,
    ValuationSpecError,
)
from core.deliverables.valuation_spec_generator import generate_valuation_spec
from core.tools.base import register_tool

logger = logging.getLogger(__name__)

_OUTPUT_DIR = "data/deliverables"


def _resolve_spec_llm():
    """Build specifications to generate LLM (model parsing chain is consistent with agent_executor, openai compatible access)"""
    from app.core.database import get_mongo_db_sync
    from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
    from core.llm.models import LLMConfig, LLMProvider
    from core.llm.unified_client import UnifiedLLMClient

    db = get_mongo_db_sync()
    config_doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)]) or {}
    default_models = config_doc.get("default_models") or {}
    system_settings = config_doc.get("system_settings") or {}

    target_model = (
        default_models.get("deep_reasoning_model")
        or system_settings.get("deep_reasoning_model")
        or default_models.get("deep_analysis_model")
        or system_settings.get("deep_analysis_model")
    )
    if not target_model:
        raise RuntimeError("The system is not configured with a deep analysis model (deep_reasoning_model / deep_analysis_model)")

    provider_info = get_provider_and_url_by_model_sync(target_model)
    if not provider_info:
        raise RuntimeError(f"无法获取模型 {target_model} 的供应商配置")

    # Valuation specification JSON structured output: unified access via OpenAI compatible adapter (all compatible with Volcano Ark/Bai Lian, etc.)
    llm = UnifiedLLMClient.from_config(
        LLMConfig(
            provider=LLMProvider.OPENAI,
            model=target_model,
            api_key=provider_info.get("api_key"),
            base_url=provider_info.get("backend_url"),
            temperature=0.2,
            max_tokens=4096,
            timeout=300,
        )
    )
    return target_model, llm


def _format_failure(title: str, detail: str) -> str:
    return f"### Valuation calculation sheet generation failed\n\n**{title}**\n\n{detail}\n\n*Please complete data synchronization or adjust requirements before trying again.*"


@tool
@register_tool(
    tool_id="generate_valuation_excel_tool",
    name="估值测算表格生成",
    description=(
        "Based on local synchronized annual report financial data and the latest market conditions, generate profit deduction and PE valuation scenario calculation tables for the next 1-3 years"
        " (xlsx file with real Excel formulas and editable hypothetical grids)."
        "When the user explicitly requests'Valuation calculation form''Profit Calculation Sheet''Valuation model Excel'Called when waiting for file deliverables."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="heavy",
    capability_tags=[
        "valuation_excel", "earnings_forecast", "pe_valuation",
        "financial_modeling", "target_price_scenario", "deliverable_generation",
    ],
    tool_role_hint="specialized",
    output_shape="structured_markdown",
    when_to_use=(
        "Called when the user explicitly requests to generate valuation calculation tables, profit deduction models, valuation scenario Excel and other document deliverables;"
        "The system will automatically verify whether the annual report/market/equity data has been synchronized before generation."
    ),
    when_not_to_use=(
        "Do not call in the following situations:1) Users only ask about valuation indicators (PE/PB/market capitalization) or general valuation knowledge,"
        "Answer directly or use the market/financial inquiry tool;2) User requirements**Data, tables, and"
        "Prediction results** (Such as sales forecast, revenue calculation and other non-valuation models) are made/exported Excel——This does not require modeling,"
        "You must use export_table_excel_tool instead (second-level export, this tool will take several minutes to re-model)."
    ),
    returns=(
        "Markdown Text: Generation results, valuation scenario target price summary table, file download link, data source description;"
        "A clear failure reason is returned when the data is not synchronized or specification verification fails."
    ),
    example="generate_valuation_excel_tool(symbol='601127', forecast_years=2)",
    related_tools=["get_historical_financial_annual_series_tool"],
)
def generate_valuation_excel_tool(
    symbol: Annotated[str, "A Stock stock code, 6 digits, such as 601127"],
    context_notes: Annotated[str, "Optional: Summary of research conclusions/profit expectations in the current analysis as a reference for calculating assumptions"] = "",
    forecast_years: Annotated[int, "Number of forecast years, 1-3, default 2"] = 2,
) -> str:
    """Generate valuation calculation Excel sheet (profit deduction + valuation scenario).

    Args:
        symbol: A Stock code, 6 digits
        context_notes: Optional summary of research conclusions
        forecast_years: Number of forecast years (1-3)

    Returns:
        Markdown text(result summary + Download link, or clear explanation of failure)
    """
    t0 = time.time()
    try:
        # 1. Data is automatically assembled (if missing, an error will be clearly reported, and replacement will not be estimated)
        try:
            bundle = build_valuation_bundle(symbol, context_notes=context_notes, forecast_years=forecast_years)
        except ValuationDataError as exc:
            return _format_failure("必需数据未同步", str(exc))

        # 2. LLM Generate model specifications (automatic feedback and retry if verification fails)
        try:
            model_name, llm = _resolve_spec_llm()
        except Exception as exc:  # noqa: BLE001
            logger.error("[ValuationExcelTool] LLM Build failed: %s", exc, exc_info=True)
            return _format_failure("模型配置不可用", str(exc))

        spec_result = generate_valuation_spec(bundle, llm, max_attempts=3)
        if not spec_result.get("passed"):
            errors = "\n".join(f"- {e}" for e in (spec_result.get("errors") or ["未知原因"]))
            return _format_failure(
                f"模型规格生成未通过校验（{spec_result.get('attempts')} 次尝试）", errors
            )
        spec = spec_result["spec"]

        # 3. rendering Excel
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"valuation_{bundle['ticker']}_{stamp}.xlsx"
        output_path = f"{_OUTPUT_DIR}/{filename}"
        try:
            render_valuation_excel(spec, output_path)
        except ValuationSpecError as exc:
            return _format_failure("规格渲染被阻断", str(exc))

        # 4. Restart file verification
        check = validate_valuation_excel(spec, output_path)
        if not check.get("passed"):
            errors = "\n".join(f"- {e}" for e in (check.get("errors") or ["未知原因"]))
            return _format_failure("生成文件校验未通过", errors)

        # Signed download link: The browser clicks directly without JWT header and must use presigned URL for authentication.
        from core.deliverables.download_links import sign_deliverable_query

        download_url = f"/api/assistant/deliverables/{filename}?{sign_deliverable_query(filename)}"

        # 5. Assembly result Markdown
        scenarios = check.get("summary", {}).get("scenarios", {})
        scenario_rows = "\n".join(
            f"| {name} | PE | {scen['eps']:.3f} | {scen['target_price']:.2f} |"
            for name, scen in scenarios.items()
        )
        elapsed = time.time() - t0
        data_notes = "；".join(bundle.get("data_notes") or []) or "Data source: Local synchronized annual report (Tushare/AKShare) and latest market prices"
        warnings = check.get("warnings") or []
        warning_lines = ""
        if warnings:
            warning_lines = "\n\n**Tips**: \n" + "\n".join(f"- {w}" for w in warnings)

        return (
            f"### 估值测算表已生成 ✅\n\n"
            f"**{bundle['stock_name']} ({bundle['ticker']}) ** · Current price {bundle['current_price']:.2f} Yuan"
            f" · total share capital {bundle['share_count']:.2f} 100 million shares · Time consuming to generate {elapsed:.0f} seconds\n\n"
            f"**Valuation Scenario (EPS Benchmark → target price)**\n\n"
            f"| Scenario | method | EPS (Yuan) | Target price (yuan) |\n"
            f"|------|------|-----------|--------------|\n"
            f"{scenario_rows}\n\n"
            f"📎 [Download Valuation Calculation Sheet]({download_url})\n\n"
            f"The table contains two sheets: profit deduction (revenue/net interest rate assumptions can be edited, and the formulas are automatically linked) and valuation scenarios (PE multiples can be adjusted)."
            f"{warning_lines}\n\n"
            f"**Data caliber**: {data_notes}\n\n"
            f"*This table is generated by AI (model:{model_name}) , It is for research reference only and does not constitute investment advice.*"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[ValuationExcelTool] Build failed: %s", exc, exc_info=True)
        return _format_failure("执行异常", str(exc))

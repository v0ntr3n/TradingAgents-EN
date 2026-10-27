"""
code generator — LLM Driven Skill code generation

Core competencies:
1. Built-in tool template reference — Read encoding specifications from core/tools/implementations/
2. Skill reference generated — Query similar cases from MongoDB external_skills
3. LLM code generation — structured Prompt → Python function + metadata + test case
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.llm import UnifiedLLMClient, Message

from .skill_spec import GeneratedCode, ImplementationFactReport, SkillSpec, TestCase
from .symbol_utils import SYMBOL_NORMALIZE_INLINE
from .external_data_source_catalog import (
    build_external_data_source_doc_for_skill,
    is_known_external_source,
)
from .data_contracts import build_data_contract_doc_for_skill
from core.skill_runtime import build_factor_catalog_prompt_context
from .stock_data_catalog import build_stock_data_collection_doc_for_skill

logger = logging.getLogger(__name__)

# It often takes 3-6 minutes for the deep thinking model to generate the complete Skill code, and it times out multiple times in 240s;
# Passable run_agentic(codegen_timeout=...) Pay-per-view coverage (can be adjusted to retry after front-end failure)
CODEGEN_LLM_TIMEOUT_SECONDS = 480

# ==================== Built-in tool template mapping ====================

# category → Reference file path (relative to project root)
BUILTIN_TEMPLATES: Dict[str, str] = {
    "news": "core/tools/implementations/news/stock_news.py",
    "market": "core/tools/implementations/market/stock_market_data.py",
    "fundamentals": "core/tools/implementations/fundamentals/financial_tools.py",
    "social": "core/tools/implementations/social/stock_sentiment.py",
    "trade_review": "core/tools/implementations/trade_review/trade_info.py",
    "technical": "core/tools/implementations/market/stock_market_data.py",
    "utility": "core/tools/implementations/fundamentals/financial_tools.py",
}

# Coding convention mode (always injected into Prompt)
CODING_PATTERNS = """\
 [Coding standards — 10 An iron rule]
1. Pure function: generates a normal Python function without using any decorators (no @tool, Don t @register_tool) 
2. Parameter annotations: use type hints (e.g. symbol: str = "000001") , Parameters have default values for easy testing
3. Return type: Returns dict (structured data, must contain status and data fields) or str (Markdown format)
4. Error handling: All external calls are wrapped with try/except and returned when an error occurs {"status": "error", "message": "..."}
5. Log specification: use logger = logging.getLogger(__name__), Use emoji logs of key steps
6. Import specifications: only use standard libraries and common third-party libraries (requests, pandas, akshare etc.); only allowed to import project runtime capabilities from core.skill_runtime.data_access or core.skill_runtime.project_access; direct import of tradingagents.dataflows.interface, tradingagents.dataflows.providers and any of their submodules is strictly prohibited; inventing other undocumented project interfaces is prohibited
7. function body < 100 OK, exceeding means doing too much.**Strictly control code length**: No more than 250 lines including auxiliary functions to avoid code being truncated by LLM output and causing syntax errors. Auxiliary functions (such as _normalize_a_share_symbol, _safe_divide) should be condensed to 5-10 lines, and do not write large comments.
8. Stock code parameters: The stock code transmitted by this system is a 6-digit pure number (such as 600519, 000001) without the .SH/.SZ suffix. The generated function parameters must accept this format; if the data source API requires other formats (such as 600519.SH), they need to be converted within the function themselves, and do not require the caller to pass in the suffixed format.
9. Mock data is prohibited: The use of mocks, simulations, fake data, and placeholder data is strictly prohibited. The data source (API, akshare, tushare, local database, etc.) must be actually called to obtain the data. If there is no data, return {"status": "success", "data": [], "message": "No xxx data found"}, False data must never be returned.
10. Placeholder code is prohibited: It is strictly prohibited to write comments such as actual API calls are required here , because it cannot be called directly , API key configuration is required and then not be implemented. Complete executable API calls (requests.get/post, etc.) must be written. If an API requires a paid token, use free alternatives such as akshare and tushare to implement it, and do not use placeholder logic instead.
11. It is forbidden to create your own project capabilities: do not create MongoClient by yourself, do not hard-code the database name, do not invent get_mongo_connection or undocumented provider methods; give priority to reusing the local_data helper and external data source entry given in the prompt word.
"""

# Stock code parameter name (used to determine whether multiple format support needs to be injected)
SYMBOL_PARAM_NAMES = frozenset({"symbol", "stock_code", "code", "stock_symbol"})

# Local Data API Compact Index (local_data pattern injection; replaces full LOCAL_DATA_API_DOC,
# The detailed signature/Returns structure is injected on demand by the reconnaissance report fact_report to avoid prompt expansion and attention dilution)
LOCAL_DATA_API_INDEX = """\
 [local data access — API Index (detailed signature and return structure shall be subject to the reconnaissance report)] 
Prioritize local, then external.from core.skill_runtime.data_access import ...
- get_stock_basic_info(symbol) -> dict|None: Basic stock information (name/industry/total_mv/pe_ttm/pb)
- get_stock_daily_quotes(symbol, start_date, end_date, period="daily", limit=1000) -> list: Daily market price (open/high/low/close/volume)
- get_stock_news(symbol, start_date=None, end_date=None, limit=20) -> list: Stock news (title/content/publish_time/url); used by date range get_stock_news_by_date_range
- get_market_quotes(symbol) -> dict|None: Real-time market snapshot (close/pct_chg/volume/amount)
- get_latest_stock_price(symbol) -> float|None: Standard price entry (valuation class is used first, do not set the price to 0)
- get_stock_financial_data(symbol, start_date=None, end_date=None, limit=20) -> list: Financial data (compatible with report_period/report_date)
- get_stock_financial_periods(symbol, limit=20) -> list: Standard financial records by reporting period (year-on-year/CAGR/multi-period calculations are preferred)
- get_stock_valuation_context(symbol) -> dict: Valuation standard entrance (basic_info/market_quotes/current_price/pe_ttm/pb/ps_ttm/financial_data)
- get_industry_peer_basic_info(industry, exclude_symbol=None, limit=200) -> list: Sample of local peers (industry comparison/relative valuation)
- summarize_industry_valuation(industry, metric="pb", exclude_symbol=None) -> dict: Industry valuation statistics average/median/min/max/count (relative valuation is used first, do not write aggregation yourself)
 [Standard structured financial data]from core.skill_runtime.standard_financial_apis import ...
- get_historical_financial_annual_series(symbol, years=10) -> dict: Annual report sequence for the last N years (revenue/net_profit/roe/gross_margin/operating_cashflow/free_cashflow, etc.)
- get_profitability_stability_metrics(symbol, years=10) -> dict: Profit stability statistics (mean/median/volatility/coefficient of variation)
- get_cashflow_quality_trend(symbol, years=10) -> dict: Cash flow quality trend (OCF/net profit, FCF/net profit, OCF/FCF margin)
- get_historical_valuation_percentile(symbol, metrics=None, lookback_years=5) -> dict: pe_ttm/pb/ps_ttm/pcf_ttm Historical quantiles and current values
⚠️ For historical valuation quantiles, do not use get_market_quotes/get_latest_stock_price (current snapshot only), use get_historical_valuation_percentile."""

# Project Data Access Compact Index (local_data mode injection; replaces full PROJECT_DATA_ACCESS_DOC)
PROJECT_ACCESS_INDEX = """\
 [Project data access — API Index (synchronous function, async/await prohibited)]
from core.skill_runtime.project_access import ...
- query_stock_collection(collection, filters=None, projection=None, sort=None, limit=100) -> list: Local collection generic query (stock_basic_info/market_quotes/stock_daily_quotes/stock_financial_data/stock_financial_periods/stock_news)
- aggregate_stock_collection(collection, pipeline, limit=100) -> list: Local aggregation (reused when helper cannot satisfy the requirement)
- list_supported_stock_collections() -> list: Accessible collection directory
- get_external_stock_news(symbol, limit=10) -> dict: external news {source, data}
- get_external_historical_data(symbol, start_date, end_date, period="daily") -> dict: External historical quotes (OHLCV only, excluding valuation)
- get_external_financial_data(symbol, report_type="quarterly", limit=4) -> dict: external financial data
- get_external_valuation_data(symbol, start_date, end_date) -> dict: External historical valuation sequence (pe_ttm/pb_mrq/ps_ttm/pcf_ttm; this is preferred for valuation classes)
- get_external_query_news(query, curr_date, look_back_days=7) -> dict: Google News/Finnhub News
Hard rules: don t import pymongo/MongoClient; don t hardcode the database name; don t await provider directly;inspect_* Recon use only; do not import the external_sources/sync_wrappers/catalog internal module."""

# External interface integration rules (external_api pattern injection; this type of requirement does not involve local stock data assets)
EXTERNAL_API_RULES = """\
⚠️ Key requirements for external interface integration:
- The generated code must be a standalone runnable synchronous pure Python function (async def / await is prohibited)
- HTTP The call must set a timeout (e.g. requests.get(url, headers=..., timeout=10)) , and wrap it with try-except
- External interfaces may be current-limited/fail occasionally: calls to the same interface within a single execution must be restrained (merge requests, set paging upper limit), and add time.sleep to temporarily back off when necessary; do not call interfaces one by one in a loop
- Parameter defense: when a required parameter is missing or has an illegal format, a structured error will be returned immediately and no network request will be initiated.
- Return gracefully when the data is empty/the interface returns nothing:{"status": "success", "data": [], "message": "No xxx data found"}, Never falsify data
- Return value consistency: Regardless of success or failure, the returned dict must contain the status field ("success"/"error") ; On failure, contains error_code and message
- Exception coverage: The main function body is wrapped with try-except. After catching the exception, a structured error response is returned. Do not throw uncaught exceptions.
- The interface fields are subject to the actual response: field mapping must come from the response structure confirmed by the reconnaissance report, and fabricated field names are prohibited."""

VALUATION_KEYWORDS = (
    "估值", "valuation", "pe", "pb", "ps", "dcf", "市盈率", "市净率", "市销率",
)


class CodeGenerator:
    """
    LLM code generator

    Generate complete Python tool function code according to SkillSpec.
    """

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
    ):
        """
        Args:
            llm_client: Preconfigured LLM client (preferred)
            provider: LLM provider (used when llm_client is empty)
            model: Model name (optional)
        """
        self._client = llm_client
        self._provider = provider
        self._model = model

    def _get_client(self, timeout_seconds: Optional[int] = None) -> UnifiedLLMClient:
        """Lazy loading of LLM clients; timeout_seconds can override the default timeout on a per-time basis"""
        timeout = timeout_seconds or CODEGEN_LLM_TIMEOUT_SECONDS
        if self._client is None:
            kwargs = {"timeout": timeout}
            if self._model:
                kwargs["model"] = self._model
            self._client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
        else:
            adapter = getattr(self._client, "_adapter", None)
            config = getattr(adapter, "config", None)
            if config and getattr(config, "timeout", 0) != timeout:
                config.timeout = timeout
                try:
                    adapter.initialize()
                except Exception as e:
                    logger.warning(f"Update code generation LLM timeout failed: {e}")
        return self._client

    def generate(
        self,
        spec: SkillSpec,
        feedback: str = "",
        previous_code: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        timeout_seconds: Optional[int] = None,
        on_thinking: Optional[Callable[[str, str], None]] = None,
        iteration_mode: str = "repair",
    ) -> GeneratedCode:
        """
        Generate skill code

        Args:
            spec: Skill Specifications
            feedback: Feedback from the previous round (used during iteration)
            previous_code: Code generated in the previous round (used when iterating)
            timeout_seconds: Single LLM call timeout (seconds), None uses the default value
            on_thinking: thought process callback on_thinking(kind, text), 
                kind ∈ {"reset", "reasoning", "content"}, Used for front-end real-time display
            iteration_mode: "repair"=Directed repair after failure (default);
                "upgrade"=Make minimal changes to upgrade the proven old version of the code

        Returns:
            GeneratedCode Contains code, metadata and test cases
        """
        start = time.time()
        client = self._get_client(timeout_seconds)

        # build Prompt
        system_prompt = self._build_system_prompt(spec)
        user_prompt = self._build_user_prompt(
            spec, feedback, previous_code, fact_report, iteration_mode=iteration_mode
        )

        # Write the complete prompt to the log file to facilitate troubleshooting the problem that LLM does not call the recommended helper
        self._dump_prompt_to_logfile(spec, system_prompt, user_prompt, fact_report)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        # call LLM — Code generation requires larger output space, explicitly set max_tokens
        # Note: 8192 tokens may not be enough for complex financial analysis functions with Chinese annotations (about 4000 lines of code),
        # There have been cases where code was truncated resulting in syntax errors. Raise to 12288 to ensure full output.
        logger.info(
            f"\n{'─'*50}\n"
            f"📤 [CodeGenerator] LLM input (tool_id={spec.tool_id})\n"
            f"{'─'*50}\n"
            f"🔧 System Prompt ({len(system_prompt)} character):\n{system_prompt[:2000]}\n"
            f"{'...(Truncate)' if len(system_prompt) > 2000 else ''}\n"
            f"📝 User Prompt ({len(user_prompt)} character):\n{user_prompt[:3000]}\n"
            f"{'...(Truncate)' if len(user_prompt) > 3000 else ''}\n"
            f"{'─'*50}"
        )
        # When there is a thinking callback, use streaming (the reasoning_content increment of the reasoning model is revealed in real time),
        # Keep the original non-streaming call when there is no callback
        if on_thinking is not None:
            response = client.chat_stream(messages, on_delta=on_thinking, max_tokens=12288)
        else:
            response = client.chat(messages, max_tokens=12288)
        raw = response.content or ""
        logger.info(
            f"\n{'─'*50}\n"
            f"📥 [CodeGenerator] LLM output ({len(raw)} character)\n"
            f"{'─'*50}\n"
            f"{raw[:3000]}\n"
            f"{'...(Truncate)' if len(raw) > 3000 else ''}\n"
            f"{'─'*50}"
        )

        # Parse results
        result = self._parse_response(raw, spec)
        result.generation_time = round(time.time() - start, 2)
        result.generation_model = response.model or self._provider

        return result

    async def agenerate(
        self,
        spec: SkillSpec,
        feedback: str = "",
        previous_code: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        iteration_mode: str = "repair",
    ) -> GeneratedCode:
        """asynchronous version generate"""
        start = time.time()
        client = self._get_client()

        system_prompt = self._build_system_prompt(spec)
        user_prompt = self._build_user_prompt(
            spec, feedback, previous_code, fact_report, iteration_mode=iteration_mode
        )

        # Write the complete prompt to the log file to facilitate troubleshooting the problem that LLM does not call the recommended helper
        self._dump_prompt_to_logfile(spec, system_prompt, user_prompt, fact_report)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        logger.info(
            f"\n{'─'*50}\n"
            f"📤 [CodeGenerator.async] LLM input (tool_id={spec.tool_id})\n"
            f"{'─'*50}\n"
            f"🔧 System Prompt ({len(system_prompt)} character):\n{system_prompt[:2000]}\n"
            f"{'...(Truncate)' if len(system_prompt) > 2000 else ''}\n"
            f"📝 User Prompt ({len(user_prompt)} character):\n{user_prompt[:3000]}\n"
            f"{'...(Truncate)' if len(user_prompt) > 3000 else ''}\n"
            f"{'─'*50}"
        )
        response = await client.achat(messages, max_tokens=12288)
        raw = response.content or ""
        logger.info(
            f"\n{'─'*50}\n"
            f"📥 [CodeGenerator.async] LLM output ({len(raw)} character)\n"
            f"{'─'*50}\n"
            f"{raw[:3000]}\n"
            f"{'...(Truncate)' if len(raw) > 3000 else ''}\n"
            f"{'─'*50}"
        )

        result = self._parse_response(raw, spec)
        result.generation_time = round(time.time() - start, 2)
        result.generation_model = response.model or self._provider

        return result

    # ==================== Prompt log dump ====================

    def _dump_prompt_to_logfile(
        self,
        spec: SkillSpec,
        system_prompt: str,
        user_prompt: str,
        fact_report: Optional[ImplementationFactReport],
    ) -> None:
        """Write the complete system_prompt and user_prompt to the log file to facilitate troubleshooting the problem of LLM not calling the recommended helper.

        Log file location:logs/codegen_prompts/<tool_id>_<timestamp>.log
        Each build overwrites the latest log for the same tool_id and retains historical versions (with timestamps).
        """
        try:
            from datetime import datetime
            log_dir = Path("logs/codegen_prompts")
            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_tool_id = re.sub(r"[^\w\-]", "_", spec.tool_id or "unknown")

            # Build a helper summary (allowing you to see at a glance which helpers are recommended during troubleshooting)
            helper_summary = " (no fact_report)"
            if fact_report:
                if fact_report.available_helpers:
                    helper_lines = []
                    for h in fact_report.available_helpers:
                        helper_lines.append(
                            f"  - {h.module}.{h.name} | signature={h.signature or ''} | "
                            f"data_source_handling={h.data_source_handling or ''} | reason={h.reason or ''}"
                        )
                    helper_summary = f"共 {len(fact_report.available_helpers)} 个:\n" + "\n".join(helper_lines)
                else:
                    helper_summary = "available_helpers is empty"

            content = (
                f"{'=' * 80}\n"
                f"# CodeGenerator Prompt Dump\n"
                f"{'=' * 80}\n"
                f"# tool_id: {spec.tool_id}\n"
                f"# timestamp: {timestamp}\n"
                f"# spec.display_name: {spec.display_name}\n"
                f"# spec.description: {spec.description[:200] if spec.description else ''}\n"
                f"# system_prompt length: {len(system_prompt)} character\n"
                f"# user_prompt length: {len(user_prompt)} character\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## Recommended by the reconnaissance layer available_helpers\n"
                f"{'─' * 80}\n"
                f"{helper_summary}\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## System Prompt (complete)\n"
                f"{'─' * 80}\n"
                f"{system_prompt}\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## User Prompt (complete)\n"
                f"{'─' * 80}\n"
                f"{user_prompt}\n"
            )

            # Write a timestamped historical version
            hist_path = log_dir / f"{safe_tool_id}_{timestamp}.log"
            hist_path.write_text(content, encoding="utf-8")

            # Covers the latest version (convenient to check the latest version)
            latest_path = log_dir / f"{safe_tool_id}_latest.log"
            latest_path.write_text(content, encoding="utf-8")

            logger.info(
                f"[CodeGenerator] Prompt dump 已写入: {latest_path} "
                f"(system={len(system_prompt)}character, user={len(user_prompt)}character, "
                f"helpers={len(fact_report.available_helpers) if fact_report else 0}a)"
            )
        except Exception as exc:
            logger.warning(f"[CodeGenerator] Failed to write prompt dump log: {exc}", exc_info=True)

    # ==================== Prompt build ====================

    def _build_system_prompt(self, spec: SkillSpec) -> str:
        """Build system prompt words (cut documents according to demand type and inject on demand).

        - external_api (External interface integration, such as understanding Chedi): only keep external data source descriptions + external interface
          rules + Coding standards, do not inject local stock collection directories/data contracts/local API documentation/reference templates.
        - local_data (Default): Replace full API documentation with compact API index; detailed signatures and Returns
          The structure is injected on demand in the user prompt by the fact_report.
        """
        from .requirement_analyzer import classify_requirement_mode

        mode = classify_requirement_mode(spec)
        external_source_doc = build_external_data_source_doc_for_skill(spec)

        # Data sources outside the directory (such as dongchedi): system directories (AKShare/Tushare, etc.) have nothing to do with requirements.
        # Injecting the complete directory instead induces LLM to bypass the user-specified interface; instead, an out-of-directory integration instruction is used.
        if spec.data_source and not is_known_external_source(spec.data_source):
            external_source_doc = (
                f" [External data source] The data source for this requirement [{spec.data_source}] Not in the system external data source directory"
                " (AKShare, Tushare Pro etc.), which belongs to the interface integration outside the directory:\n"
                "- Implemented directly using the interface specifications (URL, request headers, parameters, return fields) provided by the user as the only source of truth\n"
                "- It is strictly prohibited to use other data sources in the system directory (such as AKShare/Tushare) to replace the user-specified interface.\n"
                "- It is strictly prohibited to make up interface paths or fields; do not assume anything that is not mentioned in the interface specifications."
            )

        if mode == "external_api":
            logger.info(
                f"[CodeGenerator] requirement_mode=external_api, system prompt Only inject external interface rules "
                f"(tool_id={spec.tool_id}, data_source={spec.data_source})"
            )
            return f"""You are a professional Python tool function generator. Your task is to generate a complete, directly executable pure Python function based on the user s requirement specification (SkillSpec).

This requirement is external interface integration: data comes from external API (independent of local stock database). Do not import any local data modules under core.skill_runtime, do not query the MongoDB stock collection, and do not use the local stock data helper.

{external_source_doc}

{EXTERNAL_API_RULES}

{CODING_PATTERNS}

 [Output format]
You must output strictly in the following format, separated by three blocks:

```python
# === CODE START ===
<Complete Python code>
# === CODE END ===
```

```json
// === METADATA START ===
{{"tool_id": "...", "name": "...", "description": "...", "category": "...", "is_online": true}}
// === METADATA END ===
```

```json
// === TESTS START ===
[{{"input": {{}}, "expected_fields": [], "expected_type": "list"}}]
// === TESTS END ===
```
"""

        template_code = self._get_builtin_template(spec.category)
        stock_data_doc = build_stock_data_collection_doc_for_skill(spec)
        data_contract_doc = build_data_contract_doc_for_skill(spec)
        factor_catalog_doc = build_factor_catalog_prompt_context(
            spec.description,
            category=spec.category,
            expected_fields=list(spec.expected_output.fields or []),
        )
        template_section = ""
        if template_code:
            # Intercept the first 80 lines as a reference and remove the decorator-related lines
            lines = []
            for line in template_code.split("\n")[:80]:
                # Skip decorator lines and core module import lines
                stripped = line.strip()
                if stripped.startswith("@tool") or stripped.startswith("@register_tool"):
                    continue
                if "from core.tools.base import" in stripped:
                    continue
                if "from langchain_core.tools import tool" in stripped:
                    continue
                lines.append(line)
            template_section = f"""
 [Reference template — Code style of similar built-in tools (only refer to logic, do not copy decorators and imports)] 
```python
{chr(10).join(lines)}
```"""
        return f"""You are a professional Python tool function generator. Your task is to generate a complete, directly executable pure Python function based on the user s requirement specification (SkillSpec).

{LOCAL_DATA_API_INDEX}

{PROJECT_ACCESS_INDEX}

{stock_data_doc}

{data_contract_doc}

{external_source_doc}

{factor_catalog_doc}

⚠️ Key requirements:
- Do not use @tool, @register_tool Wait for any decorator
- Generated Skill To access project capabilities, the following modules are allowed to be imported:
  - core.skill_runtime.data_access / core.skill_runtime.project_access / core.skill_runtime.standard_financial_apis (Standard data access and financial analysis package)
  - core.tools.implementations.fundamentals / market / technical / portfolio / risk / news / social / trade_review / legacy_bridge (180+ analysis tool, shared with the agent workshop)
- Do not directly import core.skill_runtime.catalog, core.skill_runtime.external_sources, core.skill_runtime.sync_wrappers and other internal implementation modules
- Do not directly import tradingagents.dataflows.interface, tradingagents.dataflows.providers or any of their submodules
- Do not import core.tools.implementations.agent_builder / assistant_ops / skill_builder (these are process tools and should not be called by skill code)
- Do not import any module from langchain_core.xxx
- The generated code must be a standalone, runnable pure Python function
- **🚫 Script entry and debugging code are prohibited (must be observed)**: Skill It is a pure function called externally, not a script. end of code**strictly prohibited**appear `if __name__ == "__main__":` block,`print(xxx(...))` form of local debugging calls, or any"Demonstrate usage"code. Test calls are executed uniformly by the JSON declaration of the TESTS block and the sandbox (`func(**test_args)`) , LLM No need to be in code"Demo"How to call. Function behavior is completely determined by parameters, and required parameters must have reasonable default values ​​or pre-validation.
- Existing tools must be reused: If there are already tools in fact_report.available_helpers that complete the target capabilities, they must be directly from <module_path> import <function_name> Call, it is forbidden to implement equivalent data acquisition logic by yourself
- **🚨 Helper The iron law of transparent transmission (highest priority)**: helper The data returned has been aggregated, calculated, and formatted. Your code just needs to be ① call helper → ②.get()Get field → ③ Assembly output.**It is strictly forbidden to realize it yourself**Group aggregation/trend calculation/field mapping derivation/risk level calculation.**Guessing field names is strictly prohibited**, Write strictly according to the helper s Returns instructions.
- **⚠️ Defensive programming (status checks)**: helper The returned status field may have multiple values ("success" | "no_data" | "no_pledge" | "error" wait). when status is not "success" When , data fields (metrics/top_pledgers/records/series, etc.) may be empty dictionaries {{}}, empty list [] Or does not exist, and must be handled defensively:① Check status first before accessing data fields;② Use for lists for item in (list or []) rather than direct indexing [0]; ③ use .get("field", {{}}) or .get("field", []) Set default value.
- Prioritize reusing advanced packages in standard_financial_apis (such as get_historical_financial_annual_series, get_profitability_stability_metrics, get_cashflow_quality_trend, get_historical_valuation_percentile, etc.) to avoid manual repeated calculation of indicators such as ROIC, CAGR, coefficient of variation, etc.
- If the task hits the common analysis factor whitelist, give priority to reusing the existing factor_id, bundle helper and fixed formula in the catalog, and do not create new underlying factor fields.
- **Data source label usage rules** (Decision based on data_source_handling tag of each helper in available_helpers):
  - `self_contained`: helper It has been called by the self-contained data source (MongoDB/external API has been encapsulated internally), just call it directly.**Don t**Then additionally call external data sources to supplement the data.
  - `local_only`: helper Only check the local MongoDB. If the return is empty or there is insufficient data, you need to supplement the external data source call (such as tushare/akshare/finnhub) or the project external data interface (core.skill_runtime.external_sources) in the skill.
  - `partial`: helper Only covers part of the requirements and needs to be used in conjunction with other helpers or supplementary data sources/calculation logic

🛡️ General error prevention (must be followed to avoid edge test failures):
1. **Stock code validity pre-check**: The function must start by verifying that the stock symbol exists in the underlying data. Use get_stock_basic_info(symbol) Obtain basic information. If the return is empty or an error is reported, return a structured error response immediately (do not continue to execute subsequent queries to avoid API call timeout). Example:
   ```python
   basic_info = get_stock_basic_info(symbol)
   if not basic_info:
       return {{"status": "error", "error_code": "symbol_not_found", "message": f"Stock code {{symbol}} does not exist in the underlying data", "symbol": symbol}}
   ```
2. **Return gracefully when the data is empty**: All data query results must be checked to see if they are empty. Return a structured error response if key data is empty (don t let subsequent calculations crash with None/empty lists).
3. **divide-by-zero protection**: All ratio calculations must use safe division. Example:`ratio = numerator / denominator if denominator else None` or `ratio = round(numerator / denominator, 4) if abs(denominator) > 1e-9 else None`. 
4. **Degrade when time series data is insufficient**: If the historical data is less than N years, don t collapse, instead use the existing data to calculate and label `data_sufficient: false`. 
5. **API Call timeout protection**: Don t call external APIs repeatedly in a loop; if you must, set a reasonable timeout (such as 5 seconds) and try-except degradation.
6. **Extraordinary secrecy**: The main function body is wrapped with try-except. After catching the exception, a structured error response (including error_code, message, symbol) is returned. Do not throw uncaught exceptions.
7. **Return value consistency**: Regardless of success or failure, the returned dict must contain `status` field("success"/"error") and `symbol` fields to ensure that the caller can handle them uniformly.

{CODING_PATTERNS}
{template_section}
 [Output format]
You must output strictly in the following format, separated by three blocks:

```python
# === CODE START ===
<Complete Python code>
# === CODE END ===
```

```json
// === METADATA START ===
{{"tool_id": "...", "name": "...", "description": "...", "category": "...", "is_online": true}}
// === METADATA END ===
```

```json
// === TESTS START ===
[{{"input": {{}}, "expected_fields": [], "expected_type": "list"}}]
// === TESTS END ===
```
"""

    def _needs_symbol_normalize(self, spec: SkillSpec) -> tuple[bool, str | None]:
        """Determine whether it is an A-share related Skill and contains stock code parameters. Multi-format support needs to be injected."""
        param_names = {p.name.lower() for p in spec.parameters}
        for name in SYMBOL_PARAM_NAMES:
            if name in param_names:
                # Further judgment: The description or data source involves A shares/stocks
                desc_lower = (spec.description or "").lower()
                ds_lower = (spec.data_source or "").lower()
                if any(k in desc_lower or k in ds_lower for k in ("a股", "股票", "上市公司", "joinquant", "聚宽", "akshare", "tushare")):
                    return True, name
                # Default: If there is symbol and it is fundamentals/market/news, etc., it is regarded as A-share
                if spec.category in ("fundamentals", "market", "news", "utility"):
                    return True, name
        return False, None

    @staticmethod
    def _format_previous_code_for_prompt(
        previous_code: str,
        *,
        full_code_line_limit: int = 260,
        head_lines: int = 140,
        tail_lines: int = 100,
    ) -> str:
        """Priority is given to retaining the complete previous round of code, and if it is too long, it will be reduced to the first and last key fragments."""
        if not previous_code:
            return ""

        code_lines = previous_code.splitlines()
        if len(code_lines) <= full_code_line_limit:
            return previous_code

        return (
            "\n".join(code_lines[:head_lines])
            + f"\n# ... (中间省略，共 {len(code_lines)} 行) ...\n"
            + "\n".join(code_lines[-tail_lines:])
        )

    @staticmethod
    def _truncate_feedback_for_prompt(
        feedback: str,
        *,
        max_chars: int = 6000,
        head_chars: int = 3500,
    ) -> str:
        """Preserve the execution context at the beginning of the feedback and the root cause/remediation plan at the end to avoid losing critical information."""
        if len(feedback) <= max_chars:
            return feedback

        tail_chars = max_chars - head_chars - 24
        if tail_chars <= 0:
            return feedback[:max_chars]

        return (
            feedback[:head_chars]
            + "\n... (Omit the middle) ...\n"
            + feedback[-tail_chars:]
        )

    @staticmethod
    def _build_fact_report_block(fact_report: Optional[ImplementationFactReport]) -> str:
        """Format fact reports produced by the recon layer into structured Prompt blocks.

        Divided into sub-blocks, LLM clearly distinguishes between different types of implementation facts:
        - Strategy Summary: Overall Implementation Direction
        - Available Helpers: Recommended functions and signatures to call
        - Database field facts: field names that actually exist in the collection
        - Confirmed facts: specific facts discovered by schema detection
        - Forbidden path & Gap: Implementation path that must be avoided
        - Acceptance conditions: business checks that must be met to generate code
        """
        if not fact_report:
            return ""

        sections: list[str] = []

        # ── block 1: Strategy Summary ──
        summary_lines: list[str] = []
        if fact_report.task_summary:
            summary_lines.append(f"任务: {fact_report.task_summary}")
        if fact_report.recommended_strategy:
            summary_lines.append(f"推荐策略: {fact_report.recommended_strategy}")
        if summary_lines:
            sections.append("▸ 策略概要\n" + "\n".join(f"  {l}" for l in summary_lines))

        # ── block 2: Available Helper functions ──
        if fact_report.available_helpers:
            helper_lines: list[str] = []
            # data_source_handling Label description (let LLM understand how each helper handles the data source)
            ds_label_map = {
                "self_contained": "self contained(Encapsulated data source,call directly)",
                "local_only": "local only MongoDB(May need to supplement external data sources)",
                "partial": "partial coverage(May need to be supplemented by other data sources or calculations)",
            }
            # Limit the number of helpers to avoid prompt expansion, but keep enough to ensure that key helpers are not truncated
            # before [:8] As a result, some key helpers (such as the pledge function) are truncated, and LLM implements it by itself, causing failure.
            helpers_to_show = fact_report.available_helpers[:20]
            logger.info(
                f"[CodeGenerator] available_helpers 总数={len(fact_report.available_helpers)}, "
                f"before display {len(helpers_to_show)} a: "
                f"{[h.name for h in helpers_to_show]}"
            )
            for h in helpers_to_show:
                line = f"  from {h.module} import {h.name}"
                if h.signature:
                    line += f"  # 签名: {h.signature}"
                if h.description:
                    logger.info(
                        f"[CodeGenerator] helper={h.name} desc_len={len(h.description)} "
                        f"has_returns={'Returns:' in h.description}"
                    )
                    desc = h.description
                    if len(desc) > 400:
                        # Show the Returns section first
                        returns_idx = desc.find("Returns:")
                        if returns_idx > 0:
                            desc_excerpt = desc[returns_idx:returns_idx + 350]
                            line += f"\n    📋 返回结构:\n      {desc_excerpt}"
                        else:
                            # truncate end
                            line += f"\n    📋 {desc[-350:]}"
                    else:
                        line += f"\n    📋 {desc}"
                # Explicitly display the data_source_handling tag to let LLM determine whether it needs to supplement the data source
                ds_label = ds_label_map.get(h.data_source_handling, h.data_source_handling)
                line += f"  # 数据源: {ds_label}"
                if h.reason:
                    line += f"  # {h.reason}"
                helper_lines.append(line)
            sections.append(
                "▸ Helper is available (you must prioritize reusing these functions to obtain data, and you are prohibited from implementing equivalent logic by yourself)\n"
                + "  Data source label description: self_contained=self contained(call directly); local_only=local only MongoDB(May need to supplement external data sources); partial=partial coverage\n"
                + "\n".join(helper_lines)
            )
            # 🚨 Key reminder: The helper has aggregated the data and directly transparently transmits it.
            sections.append(
                "▸ 🚨 Helper Use iron rules (failure to follow will result in iteration failure)\n"
                "  - helper The returned data has been aggregated, calculated and formatted, and its return value can be used directly\n"
                "  - It is forbidden to implement grouping aggregation, trend calculation, field mapping and other logic by yourself (the helper has been prepared)\n"
                "  - Use directly .get() Take fields from helper return values, do not guess or deduce field names\n"
                "  - If there is a Returns description in the description of the helper, write the code strictly according to the field names and types.\n"
                "  - ⚠️ Defensive programming: first check the status field returned by the helper. status is not 'success' when,\n"
                "    Data fields (metrics/top_pledgers/records/series, etc.) may be empty dictionaries/empty lists.\n"
                "    Use for lists for item in (list or []) Traverse, do not index directly [0]. \n"
                "    use .get('field', {}) or .get('field', []) Set default value"
            )

        # ── block 3: Database collection fields (from sample_fields)──
        if fact_report.sample_fields:
            field_lines: list[str] = []
            for coll, fields in list(fact_report.sample_fields.items())[:4]:
                field_lines.append(f"  {coll}: {', '.join(fields[:15])}")
            sections.append(
                "▸ Database collection actual fields (reconnaissance has verified that they exist, please use these field names directly)\n"
                + "\n".join(field_lines)
            )

        # ── block 4: Confirmed Schema Facts ──
        if fact_report.schema_facts:
            fact_lines: list[str] = []
            for f in fact_report.schema_facts[:10]:
                evidence_tag = f" [{f.evidence}]" if f.evidence else ""
                fact_lines.append(f"  • [{f.source}] {f.fact}{evidence_tag}")
            sections.append("▸ 已确认事实\n" + "\n".join(fact_lines))

        # ── block 4.5: financial schema guidance card ──
        schema_bundle_context = fact_report.schema_bundle_context or {}
        method = schema_bundle_context.get("method") or {}
        contract = schema_bundle_context.get("contract") or {}
        verifier_rule = schema_bundle_context.get("verifier_rule") or {}
        applicability_rules = schema_bundle_context.get("applicability_rules") or {}
        if method or contract or verifier_rule or applicability_rules:
            schema_lines: list[str] = []
            if method:
                method_name = str(method.get("name") or schema_bundle_context.get("method_id") or "schema_method")
                schema_lines.append(f"  方法: {method_name}")
                objective = str(method.get("objective") or "").strip()
                if objective:
                    schema_lines.append(f"  目标: {objective}")
                required_metrics = list(method.get("required_metrics") or [])
                if required_metrics:
                    schema_lines.append(f"  必需指标: {', '.join(required_metrics[:6])}")
                required_fields = list(method.get("required_fields") or [])
                if required_fields:
                    schema_lines.append(f"  必需输入字段: {', '.join(required_fields[:8])}")
                steps = [str(item).strip() for item in method.get("steps") or [] if str(item).strip()]
                if steps:
                    schema_lines.append("  推荐步骤: " + " -> ".join(steps[:5]))
                limitations = [str(item).strip() for item in method.get("limitations") or [] if str(item).strip()]
                if limitations:
                    schema_lines.append("  方法局限: " + "；".join(limitations[:4]))

            if contract:
                contract_fields = [
                    str((field_def or {}).get("field_name") or "").strip()
                    for field_def in contract.get("required_fields") or []
                    if str((field_def or {}).get("field_name") or "").strip()
                ]
                if contract_fields:
                    schema_lines.append(f"  输出契约字段: {', '.join(contract_fields[:10])}")
                narrative_requirements = [
                    str(item).strip()
                    for item in contract.get("narrative_requirements") or []
                    if str(item).strip()
                ]
                if narrative_requirements:
                    schema_lines.append("  叙述要求: " + "；".join(narrative_requirements[:4]))
                prohibited_patterns = [
                    str(item).strip()
                    for item in contract.get("prohibited_patterns") or []
                    if str(item).strip()
                ]
                if prohibited_patterns:
                    schema_lines.append("  禁止模式: " + "；".join(prohibited_patterns[:3]))

            if verifier_rule:
                failure_message = str(verifier_rule.get("failure_message") or "").strip()
                remediation_hint = str(verifier_rule.get("remediation_hint") or "").strip()
                if failure_message:
                    schema_lines.append(f"  验收失败语义: {failure_message}")
                if remediation_hint:
                    schema_lines.append(f"  修复提示: {remediation_hint}")

            if applicability_rules:
                rule_lines = []
                for rule_id, rule in list(applicability_rules.items())[:4]:
                    human_description = str((rule or {}).get("human_description") or rule_id).strip()
                    rationale = str((rule or {}).get("rationale") or "").strip()
                    line = human_description
                    if rationale:
                        line += f" ({rationale})"
                    rule_lines.append(line)
                if rule_lines:
                    schema_lines.append("  适用性规则: " + "；".join(rule_lines))

            sections.append(
                "▸ Financial schema guidance card (these methods/rules/contracts must be implemented explicitly when generating code)\n"
                + "\n".join(schema_lines)
            )

        # ── block 5: Forbidden path ──
        if fact_report.blocked_paths:
            blocked_lines = [
                f"  ✘ {item.path}: {item.reason} ({item.severity})"
                for item in fact_report.blocked_paths[:5]
            ]
            sections.append("▸ Forbidden paths (do not use the following method to achieve)\n" + "\n".join(blocked_lines))

        # ── block 6: Runtime notch ──
        if fact_report.runtime_gaps:
            gap_lines = [
                f"  ⚠ {item.path or '(unknown)'}: {item.reason}"
                for item in fact_report.runtime_gaps[:4]
            ]
            sections.append("▸ Runtime Gaps (limitations to note)\n" + "\n".join(gap_lines))

        # ── block 7: Acceptance conditions (code must meet)──
        if fact_report.validation_checks:
            check_lines: list[str] = []
            for vc in fact_report.validation_checks[:8]:
                desc = vc.description or vc.name
                field_tag = f" [字段: {vc.field}]" if vc.field else ""
                check_lines.append(f"  ☑ {desc}{field_tag}")
            sections.append(
                "▸ Acceptance conditions (the output of the generated code must meet the following checks)\n"
                + "\n".join(check_lines)
            )

        # ── block 8: Remarks ──
        if fact_report.notes:
            note_lines = [f"  - {n}" for n in fact_report.notes[:4]]
            sections.append("▸ 侦察备注\n" + "\n".join(note_lines))

        if not sections:
            return ""

        header = (
            "\n [Verified implementation facts — Reconnaissance layer output, confidence level {:.0%}] \n"
            "The following facts come from actual detections at the forward reconnaissance layer. Code generation must be strictly based on these facts,\n"
            "Don t guess at new internal interfaces, provider methods, or field names."
        ).format(fact_report.confidence)

        return header + "\n\n" + "\n\n".join(sections)

    def _build_preflight_facts_block(self, spec: SkillSpec) -> str:
        """Interface preflight measured fact block (injected when spec.metadata.interface_preflight exists).

        In the pre-inspection stage, the sandbox has actually called the interface during the specification confirmation stage, and the connectivity, number of returned items, and
        Returns the true fields of the entry, validating the available query parameters. Feed LLM these facts:
        - The referenced fields are subject to the actual measured list, do not make up field names.
        - Business filter conditions (such as brand) are not included in the measured query parameters → May not be spelled into the URL,
          The full amount of data must be pulled and then filtered locally by the return field.
        Block text shares the same implementation as the Agent Loop coordinator prompt (interface_preflight.
        build_preflight_facts_text) , Make sure the rules are consistent in both places.
        """
        from .interface_preflight import build_preflight_facts_text

        preflight = (getattr(spec, "metadata", None) or {}).get("interface_preflight")
        return build_preflight_facts_text(preflight)

    def _build_user_prompt(
        self,
        spec: SkillSpec,
        feedback: str = "",
        previous_code: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        iteration_mode: str = "repair",
    ) -> str:
        """构建用户提示词"""
        from .requirement_analyzer import classify_requirement_mode

        # Skip illegal Python identifiers/keyword parameters (requirement analysis may put HTTP request headers such as
        # headers.User-Agent Mistakenly included as a function parameter and cannot appear in the function signature)
        from .static_validator import _is_unusable_param_name

        valid_params = [p for p in spec.parameters if not _is_unusable_param_name(p.name)]
        skipped_params = [p.name for p in spec.parameters if p not in valid_params]
        if skipped_params:
            logger.warning(
                f"[CodeGenerator] spec Contains illegal identifier parameter, user prompt has been skipped: {skipped_params}"
            )
        params_desc = "\n".join(
            f"  - {p.name} ({p.type}): {p.description}"
            + (f" [可选, 默认={p.default}]" if not p.required else " [必填]")
            for p in valid_params
        )

        output_desc = (
            f"  类型: {spec.expected_output.type}\n"
            f"  Field: {', '.join(spec.expected_output.fields) or 'No specific requirements'}\n"
            f"  Description: {spec.expected_output.description}"
        )

        validation_desc = "\n".join(
            f"  - [{check.rule_level}] {check.name}: {check.description}"
            + (" (阻断)" if check.blocking else " (告警)")
            for check in spec.validation_checks[:10]
        ) or "  无"

        constraints_desc = "\n".join(f"  - {c}" for c in spec.constraints) or "  无"

        # Interface specification block: Entries containing URLs in constraints are listed in separate columns and must be used verbatim.
        # Background: LLM once rewritten the rank_data provided by the user into rank/data, resulting in 404.
        interface_lines = [c for c in spec.constraints if re.search(r"https?://", str(c))]
        interface_block = ""
        if interface_lines:
            interface_desc = "\n".join(f"  {line}" for line in interface_lines)
            interface_block = f"""

 [🌐 Interface specifications — The only source of truth, no rewriting is allowed]
{interface_desc}

- The interface URL, path segment, and query parameter name must use the original text in the specifications above verbatim. It is strictly prohibited to use your training memory."correct"Or rewrite the path
   (For example, if the specification gives rank_data, it must not be written as rank/data)
- Do not add paths/parameters not mentioned in the specifications; request headers are set according to the specifications.
"""

        # Interface preflight measured facts: In external_api mode, the service layer injects the preflight results into spec.metadata.
        # Inform LLM of real fields and measured available parameters (anti-fake fields/fake query parameters, including local filtering rules)
        preflight_block = self._build_preflight_facts_block(spec)

        is_valuation_skill = any(keyword in (spec.description or "").lower() for keyword in VALUATION_KEYWORDS)
        valuation_section = ""
        if is_valuation_skill:
            valuation_section = """

 [⚠️ Valuation Skill Implementation Paradigm — Must comply]
- Priority call from core.skill_runtime.data_access import get_stock_valuation_context
- current_price must come from get_stock_valuation_context()['current_price'] or get_latest_stock_price(symbol)
- If current_price is missing,<=0, Error/invalid must be returned directly, and it is forbidden to continue the evaluation after setting it to 0 by default.
- Financial data must preferentially use the financial_data returned by core.skill_runtime.data_access and be compatible with report_period / report_date
- raw_data.financial_indicators[].end_date / report_period It is often a mixed series of quarterly reports and annual reports, and cannot be pressed by default. Continuous Annual Report understand
- growth_years If it is currently 1, it means year-on-year for the same caliber; use netprofit_yoy / growth_YOYNI first. If you calculate the year-on-year manually, you must also compare the same caliber period, and you cannot directly compare 2025Q3 with the 2024 annual report.
- PE/PB/PS If the evaluation lacks necessary input, it should return invalid and prohibit output. fair_value=0
- DCF If total_shares/net profit/effective growth rate is missing, invalid or downgrade instructions must be returned explicitly, and silent returns are prohibited. 0
- Don t just spell the price field from basic_info; the price priority should be market_quotes -> basic_info

Recommended skeleton:
```python
from core.skill_runtime.data_access import get_stock_valuation_context

ctx = get_stock_valuation_context(symbol)
current_price = ctx["current_price"]
if current_price is None or current_price <= 0:
    return {"status": "error", "message": f"Didn t get the stock {symbol} The effective current price of"}

pe_ttm = ctx["pe_ttm"]
pb = ctx["pb"]
ps_ttm = ctx["ps_ttm"]
financial_data = ctx["financial_data"]
```
"""

        symbol_section = ""
        needs_norm, param_name = self._needs_symbol_normalize(spec)
        if needs_norm and param_name:
            symbol_section = f"""
 [⚠️ Stock code multi-format support — Must be realized]
parameters {param_name} Multiple input formats need to be supported. Users may input: 600519, SH600519, 600519.SH, 600519.SS, SZ000001, 000001.SZ, etc.
Please correct at the beginning of the function {param_name} To normalize, inline the following helper functions into your code and execute them before calling the data source API:
{param_name} = _normalize_a_share_symbol({param_name})

Helper functions (must be included outside or inside a function):
{SYMBOL_NORMALIZE_INLINE}
"""

        fact_report_block = self._build_fact_report_block(fact_report)
        # The factor whitelist is a directory of stock analysis factors (MA/RSI/MACD, etc.) and has nothing to do with external interface integration;
        # Keyword matching is prone to false hits for non-stock needs (such as"monthly/period"hit technical_core)
        is_external_api = classify_requirement_mode(spec) == "external_api"
        if is_external_api:
            factor_catalog_doc = ""
            # Skill Runtime Interface constraints/factor constraints are local data oriented, external interface requirements are not injected
            runtime_interface_section = ""
            factor_rules_section = ""
            # ""Switching paid tokens to akshare/tushare" will induce LLM to abandon the user-specified interface and replace it with the external interface version.
            no_mock_section = """
 [⚠️ Simulation/placeholder is strictly prohibited — Must be truly realized]
- Mock, simulation, fake data, placeholder data, _generate_mock_data, etc. are prohibited
- Placeholder comments are prohibited: such as actual API calls are required here , because it cannot be called directly , key configuration is required , etc. You must write out the actual executable requests.get/post call
- Other data sources (AKShare/Tushare, etc.) may not be used instead of user-specified external interfaces
- If there is no data: return {{"status": "success", "data": [], "message": "No xxx data found"}}, Fake data cannot be returned
"""
        else:
            factor_catalog_doc = build_factor_catalog_prompt_context(
                spec.description,
                category=spec.category,
                expected_fields=list(spec.expected_output.fields or []),
            )
            runtime_interface_section = """
 [⚠️ Skill Runtime Interface constraints — Must comply]
- This project has only two official runtime interfaces for generating Skills: core.skill_runtime.data_access and core.skill_runtime.project_access
- Database helper, external data source bridge, and synchronization wrapper have all been integrated into skill_runtime; the generated code should not be directly imported into its internal segmentation module.
- If you need local database data, use it first core.skill_runtime.data_access
- If you need external data source bridging, synchronization wrapper or general collection query, use it first core.skill_runtime.project_access
- It is strictly prohibited to directly import tradingagents.dataflows.interface, tradingagents.dataflows.providers or any of their submodules. Even if you know that these internal implementations exist, you cannot use them directly in the generated code.
- If a capability does not currently exist in the skill_runtime public interface, do not bypass the public interface and directly connect to the internal provider; instead, use the existing public interface reconstruction solution, or return a clear downgrade result
"""
            factor_rules_section = """
 [⚠️ Common analysis factor constraints — Must comply when hitting the whitelist]
- If the requirement is essentially just existing factor reading, combination or fixed formula calculation in value_core / quality_core / growth_cashflow_core / technical_core, prioritize reusing existing helpers or bundles rather than reinventing synonymous fields.
- If expected_output.fields has hit the catalog factor field, the return structure must continue to use these factor_id, and do not rewrite it with new names such as growth_rate, profit_margin_pct, macdValue.
- If the demand exceeds the current whitelist factor range, the minimum new fields/calculation gaps should be clearly defined, and the entire Skill implementation should not be based on self-made underlying factors.
"""
            no_mock_section = """
 [⚠️ Simulation/placeholder is strictly prohibited — Must be truly realized]
- Mock, simulation, fake data, placeholder data, _generate_mock_data, etc. are prohibited
- Placeholder comments are prohibited: such as actual API calls are required here , because it cannot be called directly , key configuration is required , etc. Real calls such as executable requests.get/post or akshare must be written.
- If an API requires a paid token (such as JoinQuant), use free alternatives such as akshare and tushare to implement it. Do not use placeholder logic or return API configuration required prompts
- If there is no data: return {{"status": "success", "data": [], "message": "No xxx data found"}}, Fake data cannot be returned
"""

        prompt = f"""请根据以下 Skill 规格书生成 Python 工具函数代码：

【基本信息】
- tool_id: {spec.tool_id}
- 显示名称: {spec.display_name}
- 功能描述: {spec.description}
- 分类: {spec.category}
- 数据源: {spec.data_source or '无'}

【参数定义】
{params_desc}

【期望输出】
{output_desc}

【输出字段命名约束】
- expected_output.fields 中列出的字段名是最终契约，必须严格使用，不要擅自改名、缩写或换同义词。
- 例如规格若要求 earnings_growth_rate 和 peg_ratio，就不能输出成 growth_rate 或 peg。
- 若某字段当前无法提供，应保留该字段语义并通过 failure_reason 等失效字段说明原因，不要私自改成另一套返回结构。

【规格级验收规则】
{validation_desc}

【行为约束】
{constraints_desc}
{interface_block}
{preflight_block}
{valuation_section}
{symbol_section}
{factor_catalog_doc}
{fact_report_block}
{runtime_interface_section}
{factor_rules_section}
{no_mock_section}

【测试输入】
{json.dumps(spec.test_input, ensure_ascii=False) if spec.test_input else '无'}
"""
        if previous_code:
            truncated_code = self._format_previous_code_for_prompt(previous_code)
            if iteration_mode == "upgrade":
                # Version upgrade: The parent version is a verified baseline that requires minimal changes like human maintainers.
                # Rather than rewriting from scratch (historical lesson: rewriting will lose the details that were repaired in multiple iterations of the parent version,
                # Such as paging/retry/local filtering/brand alias matching, etc.)
                upgrade_ask = self._truncate_feedback_for_prompt(feedback) if feedback else ""
                upgrade_ask_section = ""
                if upgrade_ask:
                    upgrade_ask_section = f"\n Requirements for this upgrade:\n{upgrade_ask}\n"
                prompt += f"""
 [⬆️ Version upgrade — Make minimal changes based on the current verified version, and rewriting from scratch is strictly prohibited]

Current version code (has been verified and is the baseline for this upgrade):
```python
{truncated_code}
```
{upgrade_ask_section}
 [Upgrade requirements — extremely important]
1. **minimal changes**: Like human maintainers changing code——When adding fields, only add fields, when adding parameters, only add parameters, and only move code directly related to new requirements.
2. **Keep verified logic**: The logic that has been run through such as request structure, paging/page turning, retry backoff, response parsing, local filtering, field mapping, exception handling, etc. is retained as it is, and casual rewriting or optimization is strictly prohibited.
3. **No redesign**: Keep the function structure, naming style, and return structure unchanged (except for changes explicitly required by new specifications)
4. **The function name is subject to the new specifications**: The output function name/tool_id must be consistent with the new specification (the version number may have changed)
5. **Output complete code**: After making changes to the baseline, output the complete function code. Do not output diff, and do not use comments to omit the unmodified parts.
"""
            else:
                truncated_feedback = self._truncate_feedback_for_prompt(feedback)
                prompt += f"""
 [⚠️ Iterative repair — There was a problem with the last round of code, please fix it]

Last round of code:
```python
{truncated_code}
```

Full execution context and feedback:
{truncated_feedback or '(None)'}

 [Repair request — extremely important]
1. **directed repair**: Only modify the problematic code and keep the parts that already work correctly
2. **Don t redesign**: Keep the overall architecture unchanged unless the architecture itself is the problem
3. **Focus on root causes**: Prioritize addressing core issues identified in root cause analysis
4. **Verify fix**: Ensure that the repaired code handles the scenarios exposed in the above execution context
5. **Output complete code**: Even if only a few lines are modified, the complete function code must be output
"""
        return prompt

    # ==================== Template loading ====================

    def _get_builtin_template(self, category: str) -> str:
        """
        Get the built-in tool template code

        Args:
            category: Skill Classification (news, market, fundamentals, etc.)

        Returns:
            Template code string, if not found, returns an empty string
        """
        template_path = BUILTIN_TEMPLATES.get(category)
        if not template_path:
            template_path = BUILTIN_TEMPLATES.get("utility", "")

        if not template_path:
            return ""

        try:
            # Read from project root directory
            full_path = Path(__file__).parent.parent.parent.parent / template_path
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
            else:
                logger.warning(f"模板文件不存在: {full_path}")
                return ""
        except Exception as e:
            logger.warning(f"读取模板文件失败: {e}")
            return ""

    # ==================== Response parsing ====================

    def _parse_response(self, raw: str, spec: SkillSpec) -> GeneratedCode:
        """Parse LLM output, extract code, metadata, test cases"""
        code = self._extract_block(raw, "CODE START", "CODE END")
        metadata = self._extract_json_block(raw, "METADATA START", "METADATA END")
        tests_raw = self._extract_json_block(raw, "TESTS START", "TESTS END")

        # If extraction fails, try to extract from markdown code block
        if not code:
            code = self._extract_markdown_code(raw)

        if not code:
            logger.warning("Unable to extract code from LLM output")
            code = raw  # Bottom line: use full output

        code = self._sanitize_extracted_code(code)

        # Build test cases
        test_cases = []
        if isinstance(tests_raw, list):
            for t in tests_raw:
                if isinstance(t, dict):
                    test_cases.append(TestCase(
                        input=t.get("input", {}),
                        expected_fields=t.get("expected_fields", []),
                        expected_type=t.get("expected_type", "list"),
                    ))

        return GeneratedCode(
            code=code,
            metadata=metadata if isinstance(metadata, dict) else {},
            test_cases=test_cases,
        )

    def _sanitize_extracted_code(self, code: str) -> str:
        """Clean up residual Markdown fence and CODE START/END tags in LLM output."""
        text = str(code or "").strip()

        # LLM Sometimes the output is not closed ```python fence, fallback raw Later, fence will be regarded as the first line of code.
        text = re.sub(r"^```(?:python|py)?\s*\n", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n```\s*$", "", text)

        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"^#\s*===\s*CODE\s+(START|END)\s*===\s*$", stripped, flags=re.IGNORECASE):
                continue
            if stripped == "```":
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _extract_block(self, text: str, start_marker: str, end_marker: str) -> str:
        """提取标记之间的文本块"""
        pattern = rf"#\s*===\s*{start_marker}\s*===\s*\n(.*?)#\s*===\s*{end_marker}\s*==="
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_json_block(
        self, text: str, start_marker: str, end_marker: str
    ) -> Any:
        """Extract JSON chunks between tags"""
        pattern = rf"//\s*===\s*{start_marker}\s*===\s*\n(.*?)//\s*===\s*{end_marker}\s*==="
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        return {}

    def _extract_markdown_code(self, text: str) -> str:
        """Extract Python code from Markdown code blocks"""
        pattern = r"```python\s*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            # Returns the longest block of code (usually the main code)
            return max(matches, key=len).strip()
        return ""


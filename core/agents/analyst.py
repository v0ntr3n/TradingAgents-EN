import math
from core.agents.base import BaseAgent, GENERIC_REPORT_FALLBACK
"""
Analyst Agent base class

Used to implement various analyst agents (market analysts, news analysts, fundamental analysts, etc.)
v2.0 New: configuration-based analyst agent architecture
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .base import BaseAgent
from .config import AgentMetadata, AgentCategory

logger = logging.getLogger(__name__)




def extract_structured_posterior(report_text: str) -> Dict[str, Any]:
    """
    Extract or derive a normalized 3-class directional posterior distribution
    from an analyst report text or embedded JSON block.
    Schema:
      {
        "p_optimistic": float,
        "p_neutral": float,
        "p_cautious": float,
        "expected_move_bps": float,
        "confidence": float,
        "market_regime": "bull" | "bear" | "sideways"
      }
    """
    import json
    import re

    default_posterior = {
        "p_optimistic": 1.0 / 3.0,
        "p_neutral": 1.0 / 3.0,
        "p_cautious": 1.0 / 3.0,
        "expected_move_bps": 50.0,
        "confidence": 0.5,
        "market_regime": "sideways",
    }
    if not report_text or not isinstance(report_text, str):
        return default_posterior

    # 1. Try parsing an explicit JSON block containing p_optimistic
    json_matches = re.findall(r'\{[^{}]*"p_optimistic"[^{}]*\}', report_text, re.DOTALL)
    if json_matches:
        try:
            raw = json.loads(json_matches[-1])
            p_opt = max(0.0, float(raw.get("p_optimistic", 1.0 / 3.0)))
            p_neu = max(0.0, float(raw.get("p_neutral", 1.0 / 3.0)))
            p_cau = max(0.0, float(raw.get("p_cautious", 1.0 / 3.0)))
            total = p_opt + p_neu + p_cau
            if total > 0:
                p_opt, p_neu, p_cau = p_opt / total, p_neu / total, p_cau / total
            else:
                p_opt = p_neu = p_cau = 1.0 / 3.0
            regime = str(raw.get("market_regime", "sideways")).lower()
            if regime not in ("bull", "bear", "sideways"):
                regime = "sideways"
            return {
                "p_optimistic": round(p_opt, 6),
                "p_neutral": round(p_neu, 6),
                "p_cautious": round(p_cau, 6),
                "expected_move_bps": float(raw.get("expected_move_bps", 50.0)),
                "confidence": max(0.0, min(1.0, float(raw.get("confidence", max(p_opt, p_neu, p_cau))))),
                "market_regime": regime,
            }
        except Exception:
            pass

    # 2. Deterministic keyword-calibrated fallback when free-text report has no JSON block
    text_lower = report_text.lower()
    opt_keywords = ["optimistic", "bullish", "growth", "opportunity", "upward", "strong", "positive", "乐观", "看多", "上涨", "增长", "机会", "突破"]
    cau_keywords = ["cautious", "prudence", "bearish", "risk", "decline", "weak", "downward", "negative", "审慎", "谨慎", "看空", "下跌", "风险", "回撤"]
    neu_keywords = ["neutral", "balanced", "sideways", "shock", "consolidation", "中性", "震荡", "平衡", "观望"]

    opt_hits = sum(text_lower.count(k) for k in opt_keywords) + 1.0
    cau_hits = sum(text_lower.count(k) for k in cau_keywords) + 1.0
    neu_hits = sum(text_lower.count(k) for k in neu_keywords) + 1.0
    total_hits = opt_hits + cau_hits + neu_hits

    p_opt = opt_hits / total_hits
    p_neu = neu_hits / total_hits
    p_cau = cau_hits / total_hits
    # Ensure exact normalization
    p_cau = max(0.0, 1.0 - round(p_opt, 6) - round(p_neu, 6))

    if p_opt > p_cau + 0.10:
        regime = "bull"
    elif p_cau > p_opt + 0.10:
        regime = "bear"
    else:
        regime = "sideways"

    entropy = 0.0
    for p in (p_opt, p_neu, p_cau):
        if p > 1e-12:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(3.0)
    confidence = max(0.0, min(1.0, 1.0 - (entropy / max_entropy)))
    expected_move_bps = round(40.0 + 160.0 * abs(p_opt - p_cau), 2)

    return {
        "p_optimistic": round(p_opt, 6),
        "p_neutral": round(p_neu, 6),
        "p_cautious": round(p_cau, 6),
        "expected_move_bps": expected_move_bps,
        "confidence": round(confidence, 4),
        "market_regime": regime,
    }


class AnalystAgent(BaseAgent):
    """
    Analyst Agent base class
    
    Working mode: call tool → LLM analysis → Generate report
    
    Features:
    - Need to call tools to obtain data
    - Analysis using LLM
    - Output format:{type}_report
    - Processing market type (A shares/Hong Kong stocks/US stocks)
    
    Workflow:
    1. Read input from state(ticker, date etc.)
    2. Call tools to get data
    3. Analyze data using LLM
    4. Generate analysis report
    5. Output to state["{type}_report"]
    
    Subclasses need to implement:
    - _build_system_prompt(): Build system prompt words
    - _build_user_prompt(): Build user prompt words
    - _parse_response(): Parse LLM response
    """
    
    # Analyst type (subclass definition)
    analyst_type: str = None
    
    # Output field name (subclass definition)
    output_field: str = None
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        tool_ids: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialization Analyst Agent
        
        Args:
            config: Agent Configuration
            llm: LLM Example
            tool_ids: Tool ID list
            **kwargs: Other parameters
        """
        super().__init__(config=config, llm=llm, tool_ids=tool_ids, **kwargs)
        
        logger.debug(f"AnalystAgent '{self.agent_id}' Initialization completed")

    @staticmethod
    def _build_post_tool_analysis_prompt() -> str:
        return """The tool call has been completed and all required data has been obtained.

Please write a detailed Chinese analysis report directly now without calling any tools.

Reporting requirements:
1. **Analysis is strictly based on real data returned by the tool**: All conclusions must come from the data returned by the tool, no fabrication, assumptions or speculation are allowed
2. **Missing data handling**: If there is no data for a certain dimension in the data returned by the tool, do not analyze the dimension or list it separately. Unobtained data dimensions  Data gap description or missing dimension list. Only when the tool clearly returns exceptions, deletions, caliber conflicts, etc., can it briefly describe its limitations on the conclusion in one sentence in the corresponding paragraph.
3. **Multi-caliber data processing**: If the tool returns Summary caliber/detailed caliber  Summary of caliber differences or other multiple sets of statistical calibers. The text must retain both sets of values and clearly write them out. There is a caliber difference ; Compression to a single count is prohibited, and do not write Among them … home This type of inclusion relationship.
4. Clear structure and rigorous logic
5. The conclusion is clear and well-founded
6. Use Chinese output
7. Directly output the report content, do not return the tool call

**Important reminder**: Carefully examine the data returned by the tool and analyze only the dimensions that actually exist in the data. Do not add additional dimensions that are not provided, such as KOL opinions, retail investor sentiment, institutional positions, industry capital flows, etc., and do not generate This report did not obtain the following dimension data and does not conduct relevant analysis. Chapters like this.

Start writing your report now:"""
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform analysis

        Args:
            state: Workflow status dictionary, including:
                - ticker: Stock code
                - analysis_date: Analysis date
                - market_type: Market type (optional)
                - trade_info: Transaction information (transaction review scenario)

        Returns:
            Updated status dictionary with analysis reports
        """
        logger.info(f"Start an Executive Analyst Agent: {self.agent_id}")
        self._current_state = state

        # P1: Start execution trace collection
        from core.agents.execution_trace_recorder import (
            start_execution_trace, is_trace_enabled
        )
        recorder = None
        if is_trace_enabled():
            try:
                recorder = start_execution_trace(self, state)
                self._last_trace_id = recorder.trace_id
            except Exception as e:
                logger.warning(f"⚠️ [{self.agent_id}] Failed to start trajectory collection (does not affect agent): {e}")
                self._last_trace_id = None

        try:
            # 1. Extract input parameters (unified use of base class methods, compatible with various field names and scenarios)
            ticker, analysis_date = self._extract_common_params(state)

            market_type = state.get("market_type", "A shares")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")

            # 🔥 Extract AgentContext (for debug mode)
            context = None
            if "context" in state:
                context = state["context"]
            elif "agent_context" in state:
                # Compatible with old formats: agent_context is a dictionary
                from tradingagents.agents.utils.agent_context import AgentContext
                ctx_dict = state["agent_context"]
                if isinstance(ctx_dict, dict):
                    context = AgentContext(**ctx_dict)
                else:
                    context = ctx_dict

            # 🔍 Debug log: check if it is debug mode
            if context:
                is_debug = getattr(context, 'is_debug_mode', False)
                debug_template_id = getattr(context, 'debug_template_id', None)
                if is_debug and debug_template_id:
                    logger.info(
                        f"🔍 [{self.agent_id}] Debug mode is enabled, template ID: {debug_template_id}"
                    )
                else:
                    logger.debug(f"[{self.agent_id}] Normal mode, context exists but not debug mode")
            else:
                logger.debug(f"[{self.agent_id}] Normal mode, none context")

            # 2. Build prompt words
            # 🔑 Pass state to _build_system_prompt to extract variables from state to complete the template
            system_prompt = self._build_system_prompt(market_type, context=context, state=state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, {}, state)

            # 3. Call LLM analysis (using tool call)
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # 🔥 Detailed log: print the complete content and length of the system prompt word
            logger.info(f"System prompt word (length: {len(system_prompt)}): {system_prompt}")
            logger.info(f"User prompt words (length: {len(user_prompt)}): {user_prompt}")

            # P1: record Prompt
            if recorder:
                try:
                    recorder.record_inputs({"ticker": ticker, "analysis_date": analysis_date, "market_type": market_type})
                    recorder.record_prompts(system_prompt, user_prompt)
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Record Prompt failure (does not affect agent): {e}")
            
            # 🔥 Verification: Check whether the content of SystemMessage sent to LLM is consistent with system_prompt
            actual_system_content = messages[0].content if messages and hasattr(messages[0], 'content') else None
            if actual_system_content != system_prompt:
                logger.error(f"❌ Warning: SystemMessage content is inconsistent with system_prompt!")
                logger.error(f"   system_prompt length: {len(system_prompt)}")
                logger.error(f"   SystemMessage.content length: {len(actual_system_content) if actual_system_content else 0}")
                logger.error(f"   system_prompt first 500 characters: {system_prompt[:500]}")
                logger.error(f"   SystemMessage.content first 500 characters: {actual_system_content[:500] if actual_system_content else '(None)'}")
            else:
                logger.info(f"✅ Verification passed: SystemMessage content is consistent with system_prompt (length: {len(system_prompt)})")

            if self._llm:
                # Support tool invocation using invoke_with_tools
                if self._langchain_tools:
                    logger.info(f"[{self.agent_id}] Usage tool call mode, number of tools: {len(self._langchain_tools)}")
                    logger.info(f"[{self.agent_id}] Tool list: {[tool.name for tool in self._langchain_tools]}")

                    # Construct analysis prompts to explicitly tell LLM to generate reports based on tool results
                    analysis_prompt = self._build_post_tool_analysis_prompt()

                    report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    # 🔑 LLM The response has been automatically logged by _record_llm_response_to_trace inside invoke_with_tools
                else:
                    # No tools, call directly LLM
                    logger.warning(f"[{self.agent_id}] There is no configuration tool, use normal mode")
                    import time as _time_llm
                    _llm_start = _time_llm.time()
                    response = self._llm.invoke(messages)
                    _llm_duration_ms = int((_time_llm.time() - _llm_start) * 1000)
                    # Directly returns the string content, consistent with invoke_with_tools
                    report = response.content if hasattr(response, 'content') else str(response)

                    # P1: Logging LLM response
                    if recorder:
                        try:
                            recorder.record_llm_response(response, llm_duration_ms=_llm_duration_ms)
                        except Exception as e:
                            logger.debug(f"[{self.agent_id}] Log LLM response failure (does not affect agent): {e}")
            else:
                raise ValueError("LLM not initialized")

            # P1: Record parsed output
            if recorder:
                try:
                    recorder.record_parsed_output({"report": report[:500] if isinstance(report, str) else str(report)[:500]})
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Record parsing output failure (does not affect agent): {e}")

            # 🆕 v3.5.0 Quality access control: Check report integrity, retry once if failed, still marked as failed low_quality
            quality_flag = self._check_and_retry_quality(
                report=report,
                messages=messages,
                analysis_prompt=analysis_prompt if self._langchain_tools else None,
                ticker=ticker,
            )
            # When the retry is successful, the original report is replaced with the report after the retry.
            if quality_flag is None and hasattr(self, "_retry_report") and self._retry_report:
                report = self._retry_report
                self._retry_report = None  # Clean up to avoid affecting the next call

            # 5. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.analyst_type}_report"

            logger.info(f"analyst Agent {self.agent_id} Executed successfully")
            posterior = extract_structured_posterior(report if isinstance(report, str) else str(report))
            existing_posteriors = dict(state.get("analyst_posteriors") or {})
            existing_posteriors[self.agent_id] = posterior
            state["analyst_posteriors"] = existing_posteriors
            result = {
                output_key: report,
                "analyst_posteriors": existing_posteriors,
            }
            if self.agent_id in ("index_analyst_v2", "index_analyst"):
                state["market_regime"] = posterior["market_regime"]
                result["market_regime"] = posterior["market_regime"]

            # Quality gate flag (write state.quality_flags, the downstream can know which reports are of poor quality)
            if quality_flag:
                result["quality_flags"] = [quality_flag]

            # 🆕 v3.6.0 Item 5 Closed loop: Collection quality indicators are written to MongoDB (for dashboard query)
            # Does not block the main process and silently degrades on failure
            try:
                from app.services.quality_metrics_service import QualityMetricsService
                from app.core.database import get_mongo_db_sync
                metrics_db = get_mongo_db_sync()
                if metrics_db is not None:
                    user_id = state.get("user_id") or state.get("userId") or "default_user"
                    # Detect whether the hidden copy copy is hit
                    hit_fallback = bool(quality_flag and quality_flag.get("severity") == "critical")
                    fallback_pattern = quality_flag.get("reason", "") if quality_flag else ""
                    # v3.6.0 fix: Only the critical level is marked as low quality, and the warning level is not marked.
                    is_low_quality = bool(quality_flag and quality_flag.get("severity") == "critical")
                    retry_count = 1 if (quality_flag and quality_flag.get("retried")) else 0
                    QualityMetricsService(db=metrics_db).record_analysis_metrics_sync(
                        user_id=user_id,
                        ticker=ticker,
                        agent_id=self.agent_id,
                        agent_type=self.analyst_type,
                        report_content=report[:500] if isinstance(report, str) else "",
                        report_length=len(report) if isinstance(report, str) else 0,
                        is_low_quality=is_low_quality,
                        quality_flags=[quality_flag] if quality_flag else [],
                        hit_fallback=hit_fallback,
                        fallback_pattern=fallback_pattern,
                        retry_count=retry_count,
                        analysis_date=analysis_date,
                        workflow_id=state.get("workflow_id", ""),
                    )
            except Exception as metrics_exc:
                logger.debug(f"[Analyst] Quality indicator collection failed (not blocking): {metrics_exc}")

            # 🆕 Comes with tool call summary for reference by downstream agents
            tool_summary = self._format_tool_call_summary()
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
                logger.info(f"📊 [{self.agent_id}] Tool call summary generated ({len(self._tool_call_summaries_collected)} calls)")

            return result

        except Exception as e:
            logger.error(f"analyst Agent {self.agent_id} Execution failed: {e}", exc_info=True)
            # P1: Log exception
            if recorder:
                try:
                    recorder.record_error(e)
                except Exception:
                    pass
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.analyst_type}_report"
            return {
                output_key: {
                    "error": GENERIC_REPORT_FALLBACK,
                    "success": False
                }
            }
        finally:
            self._current_state = None
            # P1: Complete trajectory collection and write to MongoDB (non-blocking)
            if recorder:
                try:
                    recorder.finish()
                except Exception:
                    pass

    def _check_and_retry_quality(
        self,
        report: str,
        messages: list,
        analysis_prompt: Optional[str],
        ticker: str,
    ) -> Optional[Dict[str, Any]]:
        """v3.5.0 Quality access control: Check report integrity, retry once if failed, and return quality_flag if still failed.

        Hierarchical downgrade strategy:
        - critical Level failure (empty report/cover copy)→ Retry 1 time
        - warning Level failed (missing conclusion keyword)→ Don t retry, just mark
        - Still failed after retrying → Return quality_flag dictionary writing state.quality_flags

        Args:
            report: Original report content
            messages: Original message list (reused during retries)
            analysis_prompt: Post-tool analysis prompt word (reused when retrying, None in tool-less mode)
            ticker: Stock symbol (used for log and alert metadata)

        Returns:
            None Indicates quality passed; Dict indicates quality flag (should be written to state.quality_flags)
        """
        from core.agents.quality_gate import validate_analyst_report

        report_str = report if isinstance(report, str) else str(report)
        qc_result = validate_analyst_report(
            content=report_str,
            agent_id=self.agent_id,
            ticker=ticker,
        )

        if qc_result.is_valid:
            logger.info(f"[QualityGate] {self.agent_id} Report quality passed")
            return None

        # warning Level: No retry, just mark
        if not qc_result.should_retry:
            logger.warning(
                f"[QualityGate] {self.agent_id} Report quality warning:{qc_result.reason}"
            )
            return {
                "agent_id": self.agent_id,
                "analyst_type": self.analyst_type,
                "ticker": ticker,
                "reason": qc_result.reason,
                "severity": qc_result.severity,
                "retried": False,
            }

        # critical Level: Retry 1 time
        logger.warning(
            f"[QualityGate] {self.agent_id} Report quality critical:{qc_result.reason}, Retry 1 time"
        )
        try:
            retry_messages = list(messages) + [
                HumanMessage(content=(
                    f"Note: There is a problem with the report you just generated ({qc_result.reason}) . "
                    "Please regenerate a complete analysis report, which must contain clear conclusions (such as recommendations/judgments/risks, etc.)."
                    "Directly output the report content without calling any tools."
                ))
            ]
            if self._langchain_tools and analysis_prompt:
                retry_report = self.invoke_with_tools(retry_messages, analysis_prompt=analysis_prompt)
            elif self._llm:
                retry_response = self._llm.invoke(retry_messages)
                retry_report = retry_response.content if hasattr(retry_response, 'content') else str(retry_response)
            else:
                retry_report = report  # Unable to retry, keep original report

            # Second verification
            retry_str = retry_report if isinstance(retry_report, str) else str(retry_report)
            qc_result2 = validate_analyst_report(
                content=retry_str,
                agent_id=self.agent_id,
                ticker=ticker,
            )

            if qc_result2.is_valid:
                logger.info(f"[QualityGate] {self.agent_id} Quality passed after retrying")
                # Replace the original report with the retried report (passed back to execute via instance properties)
                # Note: The local variable report of execute cannot be modified directly here.
                # So pass it with _retry_report attribute
                self._retry_report = retry_report
                return None
            else:
                logger.error(
                    f"[QualityGate] {self.agent_id} Still failed after trying again:{qc_result2.reason}, mark low_quality"
                )
                return {
                    "agent_id": self.agent_id,
                    "analyst_type": self.analyst_type,
                    "ticker": ticker,
                    "reason": qc_result2.reason,
                    "severity": qc_result2.severity,
                    "retried": True,
                }
        except Exception as retry_err:
            logger.error(f"[QualityGate] {self.agent_id} Retry exception:{retry_err}", exc_info=True)
            return {
                "agent_id": self.agent_id,
                "analyst_type": self.analyst_type,
                "ticker": ticker,
                "reason": f"Retry exception: {retry_err}",
                "severity": "critical",
                "retried": True,
            }

    def _fetch_data_with_tools(
        self, 
        ticker: str, 
        analysis_date: str, 
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use tools to get data
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            state: Workflow status
            
        Returns:
            Data dictionary returned by the tool
        """
        tool_data = {}
        
        # If you have LangChain tool, use invoke_with_tools
        if self._langchain_tools and self._llm:
            # Build tool invocation tips
            tool_prompt = self._build_tool_prompt(ticker, analysis_date)
            result = self.invoke_with_tools(tool_prompt)
            tool_data = result
        
        return tool_data
    
    def _build_tool_prompt(self, ticker: str, analysis_date: str) -> str:
        """
        Build tool call prompt word
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            
        Returns:
            Prompt word string
        """
        return f"please get {ticker} in {analysis_date} related data"

    # Note:_get_prompt_from_template() Method has been moved to BaseAgent base class, shared by all Agents

    @abstractmethod
    def _build_system_prompt(self, market_type: str, context=None, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (subclass implementation)

        Args:
            market_type: market type
            context: AgentContext Object (for debug mode)
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)

        Returns:
            System prompt word
        """
        pass
    
    @abstractmethod
    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        tool_data: Dict[str, Any],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (subclass implementation)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            tool_data: Data returned by the tool
            state: Workflow status

        Returns:
            User prompt words
        """
        pass

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response (can be overridden by subclasses)

        Args:
            response: LLM response text

        Returns:
            Parsed report dictionary
        """
        # Default implementation: return text directly
        return {
            "content": response,
            "posterior": extract_structured_posterior(response),
            "success": True
        }

    @property
    def agent_id(self) -> str:
        """get Agent ID"""
        if self.metadata:
            return self.metadata.id
        return self.__class__.__name__.lower()


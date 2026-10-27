"""
ResearcherAgent base class

Used to implement researcher agents (active evidence researchers, cautious evidence researchers, etc.)
v2.0 New: configuration-based researcher agent architecture
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .base import BaseAgent
from .config import AgentMetadata, AgentCategory

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """
    ResearcherAgent base class
    
    Working mode: Reading multiple reports → LLM Comprehensive research and judgment → generate opinions
    
    Features:
    - Tools are not called (or rarely called)
    - Rely on the output of other agents
    - Requires memory system (memory)
    - Output format: Opinion report
    
    Workflow:
    1. Read multiple analysis reports from state
    2. Comprehensive analysis using LLM
    3. Generate investment ideas
    4. Output to state["bull_report"/"bear_report"]
    
    Subclasses need to implement:
    - _build_system_prompt(): Build system prompt words
    - _build_user_prompt(): Build user prompt words
    - _get_required_reports(): Get a list of required reports
    """
    
    # Researcher Type (Subclass Definition)
    researcher_type: str = None

    # Output field name (subclass definition)
    output_field: str = None

    # Research stance (bull/bear/risky/safe/neutral)
    stance: str = None

    # Debate related configuration (can be overridden by subclasses)
    debate_state_field: str = "investment_debate_state"  # or "risk_debate_state"
    history_field: str = None  # "bull_history", "bear_history" Wait
    opponent_history_field: str = None  # The other party's history field
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        memory: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialization Researcher Agent
        
        Args:
            config: Agent Configuration
            llm: LLM Example
            memory: Memory system example
            **kwargs: Other parameters
        """
        super().__init__(config=config, llm=llm, **kwargs)
        
        self.memory = memory
        
        logger.debug(f"ResearcherAgent '{self.agent_id}' Initialization completed")
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform research analysis

        Args:
            state: Workflow status dictionary, including:
                - ticker: Stock code
                - analysis_date: Analysis date
                - market_report: Market analysis report (optional)
                - news_report: News analysis report (optional)
                - fundamentals_report: Fundamental analysis report (optional)
                - trade_info: Transaction information (transaction review scenario)
                - Other analysis reports...

        Returns:
            Updated status dictionary with research perspectives
        """
        logger.info(f"Start an executive researcher Agent: {self.agent_id}")

        import time as _time_exec
        _exec_start = _time_exec.time()

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
            # 🔍 Debug log: troubleshooting ticker loss problem
            logger.error(
                f"🔍 [{self.agent_id}] state keys: {list(state.keys())[:20]}, "
                f"ticker={state.get('ticker')}, company_of_interest={state.get('company_of_interest')}, "
                f"trade_info exist={('trade_info' in state)}, code={state.get('trade_info', {}).get('code') if isinstance(state.get('trade_info'), dict) else 'N/A'}"
            )

            # 1. Extract input parameters (unified use of base class methods, compatible with various field names and scenarios)
            ticker, analysis_date = self._extract_common_params(state)

            if not ticker:
                logger.error(f"❌ [{self.agent_id}] ticker Not found! state all keys: {list(state.keys())}")
                raise ValueError("Missing required parameters: ticker")
            
            logger.info(f"✅ [{self.agent_id}] ticker Parsed successfully: {ticker}")
            
            # 2. Collect required reports
            reports = self._collect_reports(state)

            if not reports:
                raise ValueError("No reports available for analysis")

            # 3. Detect debate patterns and get context
            is_debate_mode = self._is_debate_mode(state)

            if is_debate_mode:
                # Debate Mode: Get Debate Context + Vector cache history experience
                debate_context = self._get_debate_context(state)
                memory_context = self._get_memory_context(ticker, reports) if self.memory else None
                
                # Merge debate context and vector cache context
                context_parts = []
                if debate_context:
                    context_parts.append(debate_context)
                if memory_context:
                    context_parts.append(f"\n [Historical experience (vector cache)]\n{memory_context}")
                
                historical_context = "\n".join(context_parts) if context_parts else None
                logger.info(f"[debate mode] {self.agent_id} Read debate history + vector cache")
            else:
                # Single analysis mode: obtaining historical context from the memory system
                historical_context = self._get_memory_context(ticker, reports) if self.memory else None
                logger.info(f"[Single analysis mode] {self.agent_id} Use vector caching")

            # v3.5.0 Item 1 Closed loop: Check the quality gate mark, low quality report is prompted in prompt
            # Allow researchers to perceive which analysts' reports are of questionable quality, thereby reducing the weight of conclusions
            quality_flags = state.get("quality_flags") or []
            if quality_flags:
                quality_hint = self._build_quality_hint(quality_flags)
                if quality_hint:
                    historical_context = (
                        quality_hint + "\n" + (historical_context or "")
                    ).strip()
                    logger.info(
                        f"[Researcher] detected {len(quality_flags)} quality mark, quality prompt has been injected"
                    )

            # 4. Build prompt words
            # Pass the state parameter (subclasses can extract variables from state such as company_name, ticker etc.)
            system_prompt = self._build_system_prompt(self.stance, state)

            user_prompt = self._build_user_prompt(ticker, analysis_date, reports, historical_context, state)
            
            # 5. Call LLM analysis
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")

            # P1: record Prompt
            if recorder:
                try:
                    recorder.record_inputs({"ticker": ticker, "analysis_date": analysis_date, "reports_keys": list(reports.keys()) if isinstance(reports, dict) else []})
                    recorder.record_prompts(system_prompt, user_prompt)
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Record Prompt failure (does not affect agent): {e}")
            
            if self._llm:
                import time
                _llm_start = time.time()
                logger.info(f"⏳ [{self.agent_id}] Start calling LLM (timeout={getattr(self._llm, 'timeout', '?')}, max_retries={getattr(self._llm, 'max_retries', '?')})...")
                try:
                    response = self._llm.invoke(messages)
                    _llm_elapsed = time.time() - _llm_start
                    logger.info(f"✅ [{self.agent_id}] LLM Call completed, Time consuming: {_llm_elapsed:.1f}s, response length: {len(response.content) if response.content else 0}")
                except Exception as _llm_err:
                    _llm_elapsed = time.time() - _llm_start
                    logger.error(f"❌ [{self.agent_id}] LLM call failed, Time consuming: {_llm_elapsed:.1f}s, Error: {_llm_err}", exc_info=True)
                    raise
                report = self._parse_response(response.content)

                # P1: Logging LLM responses and parsing output
                if recorder:
                    try:
                        recorder.record_llm_response(response, llm_duration_ms=int(_llm_elapsed * 1000))
                        recorder.record_parsed_output({"report": report[:500] if isinstance(report, str) else str(report)[:500]})
                    except Exception as e:
                        logger.debug(f"[{self.agent_id}] Log LLM response failure (does not affect agent): {e}")
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Save to memory system (if available)
            if self.memory:
                # 🔥 v2.0: In debate mode, it is also saved to the vector cache for subsequent use.
                # v3.5.0 Item 3: At the same time trigger reflection and refinement, and refine the report into structured lessons
                self._save_to_memory(ticker, report, state=state)
                if is_debate_mode:
                    logger.info(f"[debate mode] {self.agent_id} Saved to vector cache")

            # 7. Build output
            output_key = self.output_field or f"{self.researcher_type}_report"
            result = {output_key: report}

            # 8. Update debate status (if in debate mode)
            if is_debate_mode:
                result = self._update_debate_state(state, report, result)
                logger.info(f"[debate mode] {self.agent_id} Update debate status")

            logger.info(f"researcher Agent {self.agent_id} Executed successfully (Total time spent: {_time_exec.time() - _exec_start:.1f}s)")
            return result

        except Exception as e:
            logger.error(f"researcher Agent {self.agent_id} Execution failed (Total time spent: {_time_exec.time() - _exec_start:.1f}s): {e}", exc_info=True)
            # P1: Log exception
            if recorder:
                try:
                    recorder.record_error(e)
                except Exception:
                    pass
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.researcher_type}_report"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }
        finally:
            # P1: Complete trajectory collection and write to MongoDB (non-blocking)
            if recorder:
                try:
                    recorder.finish()
                except Exception:
                    pass
    
    def _collect_reports(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect required reports
        
        Args:
            state: Workflow status
            
        Returns:
            report dictionary
        """
        required_reports = self._get_required_reports()
        reports = {}
        
        for report_key in required_reports:
            if report_key in state:
                reports[report_key] = state[report_key]

        return reports

    def _build_quality_hint(self, quality_flags: List[Dict[str, Any]]) -> str:
        """Build quality prompt text (v3.5.0 item 1 closed loop).

        Convert analyst report quality gate flags into prompt prompts,
        Allow researchers to perceive which analysts reports are of questionable quality, thereby reducing the weight of their conclusions.

        Args:
            quality_flags: A list of quality marks, each containing agent_id/severity/reason

        Returns:
            Quality prompt text, or empty string
        """
        if not quality_flags:
            return ""

        hints: List[str] = []
        for flag in quality_flags:
            if not isinstance(flag, dict):
                continue
            agent_id = flag.get("agent_id", "Unknown analyst")
            severity = flag.get("severity", "")
            reason = flag.get("reason", "")
            retried = flag.get("retried", False)

            if severity == "critical":
                retry_note = " (Tried again and still failed)" if retried else ""
                hints.append(
                    f"⚠️ {agent_id} Unsatisfactory report quality{retry_note}: {reason}. "
                    f"Please refer to the analyst s conclusions with caution, and it is recommended to focus on other analyst reports."
                )
            elif severity == "warning":
                hints.append(
                    f"⚠️ {agent_id} Report quality is questionable:{reason}. "
                    f"It is recommended that the reference weight of this conclusion be reduced."
                )

        if not hints:
            return ""

        return " [Quality Tips]\n" + "\n".join(hints)
    
    def _get_historical_context(self, ticker: str) -> Optional[str]:
        """
        Get historical context from memory system

        Args:
            ticker: Stock code

        Returns:
            historical context text
        """
        if not self.memory:
            return None

        try:
            # This needs to be implemented based on the actual memory system
            # Return temporarily None
            return None
        except Exception as e:
            logger.warning(f"Failed to obtain historical context: {e}")
            return None

    def _save_to_memory(self, ticker: str, report: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> None:
        """
        Save to memory system

        Args:
            ticker: Stock code
            report: research report
            state: Workflow state (used to extract context such as user_id, required by v3.5.0 item 3 reflection node)
        """
        if not self.memory:
            return

        try:
            # Extract report content
            if isinstance(report, dict):
                content = report.get("content", str(report))
            else:
                content = str(report)

            # Prepare metadata
            from datetime import datetime
            metadata = {
                "ticker": ticker,
                "stance": self.stance,
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat()
            }

            if not hasattr(self.memory, 'add_memory'):
                logger.warning("Memory instances do not support add_memory, saving has been skipped: %s", type(self.memory).__name__)
                return

            success = self.memory.add_memory(
                content=content,
                metadata=metadata
            )
            if success:
                logger.info(f"✅ Save to memory system: {ticker}, stance={self.stance}")

            # v3.5.0 Item 3: Reflection and refinement of researcher's report
            # After writing the original text, add structured lesson nodes to refine the report into 4-dimensional experience
            # Write to ANALYSIS_INSIGHT scope,memory_kind=analysis_lesson
            # When it fails, the helper has been downgraded internally and does not block the main process.
            self._reflect_on_analysis(ticker, report, content, state=state)

        except Exception as e:
            logger.warning(f"Failed to save to memory system: {e}")

    def _reflect_on_analysis(
        self,
        ticker: str,
        report: Dict[str, Any],
        original_content: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Researcher report reflection and refinement (v3.5.0 item 3).

        Distill this analysis report into structured lessons (reasoning/improvement/summary/query),
        Write to ANALYSIS_INSIGHT scope,memory_kind=analysis_lesson. 

        Next time when analyzing the same stock, _get_memory_context can give priority to recalling the structured lessons instead of the original text.

        Downgrade strategy:
        - LLM Timeout/return non JSON → fallback Write the original text (reflection_success=False) 
        - mem0 Not available → skip
        - any exception → Does not block the main process
        """
        try:
            from core.agents.reflection_helper import run_reflection_sync
            from core.agents.reflection_prompts import (
                ANALYSIS_REFLECTION_SYSTEM_PROMPT,
                build_analysis_reflection_user_prompt,
            )
            from core.memory.models import MemoryScope

            # Extract report content for reflection
            if isinstance(report, dict):
                stance = report.get("stance", self.stance)
            else:
                stance = self.stance

            analysis_date = ""
            if state:
                analysis_date = state.get("analysis_date") or state.get("trade_date") or ""
            if not analysis_date:
                try:
                    from datetime import datetime
                    analysis_date = datetime.now().strftime("%Y-%m-%d")
                except Exception:
                    pass

            user_prompt = build_analysis_reflection_user_prompt(
                ticker=ticker,
                report=report,
                analysis_date=analysis_date,
            )
            if not user_prompt.strip():
                return

            # Get db handle (for MemoryService)
            db = self._get_db_handle(state=state)
            if db is None:
                logger.debug("[Researcher] Reflection skipped: db handle not obtained")
                return

            user_id = self._get_user_id(state=state) or "default_user"

            success = run_reflection_sync(
                db=db,
                user_id=user_id,
                agent_id=self.agent_id,
                scope=MemoryScope.ANALYSIS_INSIGHT,
                memory_kind="analysis_lesson",
                system_prompt=ANALYSIS_REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                fallback_content=original_content,
                fallback_metadata={
                    "symbol": str(ticker).upper(),
                    "stance": stance,
                    "agent_id": self.agent_id,
                    "analysis_date": analysis_date,
                    "source": "researcher_reflection",
                },
            )
            if success:
                logger.info(
                    f"[Researcher] Analysis_lesson lesson written: ticker={ticker} stance={stance}"
                )
        except Exception as e:
            logger.warning(f"[Researcher] analysis_lesson Reflection exception: {e}", exc_info=True)

    def _reflect_on_debate(
        self,
        ticker: str,
        debate_history: str,
        conclusion: str,
        debate_type: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Debate reflection and refinement (v3.6.0 item 8).

        Triggered after the maximum number of rounds of multi-scenario studies/risk reviews has been reached, and the multi-scenario study history and final verdict
        Distill into structured lessons (reasoning/improvement/summary/query) and write
        AGENT_EXPERIENCE scope，memory_kind=debate_lesson。

        The next time you analyze the same stock, _get_memory_context can recall the multi-scenario research lessons.
        Let multiple perspectives compare from"Confrontation"upgraded to"accumulate". 

        Downgrade strategy:
        - LLM Timeout/return non JSON → fallback Write a research history summary (reflection_success=False) 
        - mem0 Not available → skip
        - any exception → Does not block the main process
        """
        try:
            from core.agents.reflection_helper import run_reflection_sync
            from core.agents.reflection_prompts import (
                DEBATE_REFLECTION_SYSTEM_PROMPT,
                build_debate_reflection_user_prompt,
            )
            from core.memory.models import MemoryScope

            if not debate_history.strip() and not conclusion.strip():
                return

            user_prompt = build_debate_reflection_user_prompt(
                ticker=ticker,
                debate_history=debate_history,
                conclusion=conclusion,
                debate_type=debate_type,
            )
            if not user_prompt.strip():
                return

            db = self._get_db_handle(state=state)
            if db is None:
                logger.debug("[Researcher] Debate reflection skipped: db handle not obtained")
                return

            user_id = self._get_user_id(state=state) or "default_user"

            # fallback Content: Take the end of debate history + Conclusion (avoid empty string as fallback)
            fallback_parts = [f"Debate reflection {ticker} ({debate_type})"]
            if debate_history:
                # Only keep the last 800 words to avoid the fallback being too long
                fallback_parts.append(debate_history[-800:])
            if conclusion:
                fallback_parts.append(f"final verdict: {conclusion[:300]}")
            fallback_content = "\n\n".join(fallback_parts)

            success = run_reflection_sync(
                db=db,
                user_id=user_id,
                agent_id=self.agent_id,
                scope=MemoryScope.AGENT_EXPERIENCE,
                memory_kind="debate_lesson",
                system_prompt=DEBATE_REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                fallback_content=fallback_content,
                fallback_metadata={
                    "symbol": str(ticker).upper() if ticker else "",
                    "stance": self.stance or "",
                    "agent_id": self.agent_id,
                    "debate_type": debate_type,
                    "source": "debate_reflection",
                },
            )
            if success:
                logger.info(
                    f"[Researcher] Debate_lesson lesson written: ticker={ticker} type={debate_type}"
                )
        except Exception as e:
            logger.warning(f"[Researcher] debate_lesson Reflection exception: {e}", exc_info=True)

    def _get_db_handle(self, state: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Gets the MongoDB database handle (for MemoryService).

        ResearcherAgent May be called in different contexts (workflow engine, independent call, etc.),
        Try to get db handle from multiple sources.
        """
        # 1. Get from state (workflow engine injection)
        if state and isinstance(state, dict):
            db = state.get("_db") or state.get("db")
            if db is not None:
                return db

        # 2. Get from self._db if present
        if hasattr(self, "_db") and self._db is not None:
            return self._db

        # 3. Get from self.config.prompt_variables (Pydantic model)
        try:
            if hasattr(self, "config") and self.config is not None:
                prompt_vars = getattr(self.config, "prompt_variables", None) or {}
                if isinstance(prompt_vars, dict):
                    db = prompt_vars.get("db") or prompt_vars.get("database")
                    if db is not None:
                        return db
        except Exception:
            pass

        # 4. Get from global get_mongo_db
        try:
            from app.core.database import get_mongo_db_sync
            return get_mongo_db_sync()
        except Exception:
            pass

        # 5. Try constructing directly from settings
        try:
            from pymongo import MongoClient
            from app.core.config import settings
            client = MongoClient(settings.MONGO_URI)
            return client[settings.MONGO_DB]
        except Exception as e:
            logger.debug(f"[Researcher] Failed to obtain db handle: {e}")
            return None

    def _get_user_id(self, state: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Get the current user ID (for mem0 metadata)."""
        # 1. Get from state
        if state and isinstance(state, dict):
            user_id = state.get("user_id") or state.get("userId")
            if user_id:
                return str(user_id)

        # 2. Get from self._user_id
        if hasattr(self, "_user_id") and self._user_id:
            return str(self._user_id)

        # 3. Get from self.config.prompt_variables
        try:
            if hasattr(self, "config") and self.config is not None:
                prompt_vars = getattr(self.config, "prompt_variables", None) or {}
                if isinstance(prompt_vars, dict):
                    user_id = prompt_vars.get("user_id")
                    if user_id:
                        return str(user_id)
        except Exception:
            pass

        return None

    @abstractmethod
    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (subclass implementation)

        Args:
            stance: Research stance (bull/bear)
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
        reports: Dict[str, Any],
        historical_context: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (subclass implementation)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            reports: Collected report dictionary
            historical_context: historical context
            state: Workflow status

        Returns:
            User prompt words
        """
        pass

    @abstractmethod
    def _get_required_reports(self) -> List[str]:
        """
        Get the required report list (subclass implementation)

        Returns:
            Report field name list
        """
        pass

    # Note:_get_prompt_from_template() Method has been moved to BaseAgent base class, shared by all Agents

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
            "stance": self.stance,
            "success": True
        }

    @property
    def agent_id(self) -> str:
        """get Agent ID"""
        if self.metadata:
            return self.metadata.id
        return self.__class__.__name__.lower()

    # ========== Debate Support Methods ==========

    def _is_debate_mode(self, state: Dict[str, Any]) -> bool:
        """
        Check whether it is in debate mode

        Args:
            state: Workflow status

        Returns:
            True If it is debate mode
        """
        return self.debate_state_field in state and isinstance(state.get(self.debate_state_field), dict)

    def _get_debate_context(self, state: Dict[str, Any]) -> str:
        """
        Get debate context

        Args:
            state: Workflow status

        Returns:
            Debate context string (contains debate history and opponent s point of view)
        """
        debate_state = state.get(self.debate_state_field, {})

        # Full debate history
        history = debate_state.get("history", "")

        # The other party's latest views
        current_response = debate_state.get("current_response", "")

        # Opponent history (if opponent_history_field is configured)
        opponent_history = ""
        if self.opponent_history_field:
            opponent_history = debate_state.get(self.opponent_history_field, "")

        # Build context
        context_parts = []

        if history:
            context_parts.append(f" [Full debate history]\n{history}")

        if current_response:
            context_parts.append(f"\n [The other party s latest views]\n{current_response}")

        if opponent_history and opponent_history != history:
            context_parts.append(f"\n [The other party s historical perspective]\n{opponent_history}")

        return "\n".join(context_parts) if context_parts else ""

    def _get_memory_context(self, ticker: str, reports: Dict[str, Any]) -> str:
        """
        Get historical experience from Memory system

        Args:
            ticker: Stock code
            reports: current report

        Returns:
            historical experience string
        """
        if not self.memory:
            return ""

        try:
            # 🔥 Construct query text: use key information rather than full report
            # The purpose of vector retrieval is to find similar historical experiences, and key information should be used as a query
            # Instead of merging all reports (this will cause the query text to be too long and is not a good query method)
            
            query_parts = []
            
            # 1. Basic stock information (the most important query criteria)
            if ticker:
                query_parts.append(f"Stock code: {ticker}")
            
            # 2. Extract key information from reports (if any)
            # Note: reports may contain dictionaries or strings and need to be processed
            company_name = None
            industry = None
            current_price = None
            
            for key, value in reports.items():
                if not value:
                    continue
                
                # Handling dictionary type values
                if isinstance(value, dict):
                    company_name = value.get("company_name") or value.get("name") or company_name
                    industry = value.get("industry") or industry
                    current_price = value.get("current_price") or current_price
                elif isinstance(value, str):
                    # String type value, trying to extract key information
                    if key in ["company_name", "name"]:
                        company_name = value
                    elif key == "industry":
                        industry = value
                    elif key == "current_price":
                        try:
                            current_price = float(value)
                        except:
                            pass
            
            if company_name:
                query_parts.append(f"Company name: {company_name}")
            if industry:
                query_parts.append(f"Industry: {industry}")
            if current_price:
                query_parts.append(f"current price: {current_price}")
            
            # 3. Use the summary/key portion of the report (only the first 300 characters)
            # This retains key information but doesn't make it too long
            MAX_SUMMARY_LENGTH = 300
            for key, value in reports.items():
                # Skip already processed fields and null values
                if key in ["company_name", "name", "industry", "current_price", "ticker"] or not value:
                    continue
                
                report_text = str(value)
                # Take only the first N characters as summary
                summary = report_text[:MAX_SUMMARY_LENGTH]
                if len(report_text) > MAX_SUMMARY_LENGTH:
                    summary += "..."
                query_parts.append(f"{key}Summary: {summary}")
            
            # Build query text
            curr_situation = "\n".join(query_parts)
            
            # 🔥 Limit the total length of query text to ensure it does not exceed the Embedding API limit
            MAX_QUERY_LENGTH = 2000  # Use key information and should not be too long
            if len(curr_situation) > MAX_QUERY_LENGTH:
                logger.warning(f"⚠️ Query text is too long ({len(curr_situation):,} > {MAX_QUERY_LENGTH:,}), truncate")
                curr_situation = curr_situation[:MAX_QUERY_LENGTH] + "..."
                logger.info(f"📝 Query text length after truncation: {len(curr_situation):,} character")
            
            logger.debug(f"🔍 Build query text (using key information): {curr_situation[:500]}...")

            # 🔧 Check whether the memory function is enabled (the first level analysis depth does not use memory)
            # 🔥 self.config Yes AgentConfig (Pydantic BaseModel), Direct access to properties
            memory_enabled = getattr(self.config, "memory_enabled", True)
            if not memory_enabled:
                logger.info(f"📭 Memory function disabled (quick analysis mode)")
                return ""

            if not hasattr(self.memory, 'search_memories'):
                logger.warning("Memories do not support search_memories, recall skipped: %s", type(self.memory).__name__)
                return ""

            past_memories = self.memory.search_memories(
                query=curr_situation,
                n_results=3,
                filter_metadata={"ticker": ticker} if ticker else None
            )

            memory_str = ""
            for i, mem in enumerate(past_memories, 1):
                content = mem.get("content", "")
                similarity = mem.get("similarity", 0.0)

                # Use only similarity > 0.7 memory
                if similarity > 0.7:
                    memory_str += f"[Similarity: {similarity:.2f}] {content}\n\n"

            # v3.5.0 Closed loop L2/L3: Prioritize recall of reflection lessons in mem0
            # Reflection lessons are written to mem0 through reflection_helper.run_reflection,
            # Here, recall_lessons_sync is used to recall and inject prompt to form a complete closed loop.
            lessons_str = ""
            try:
                from core.agents.reflection_helper import recall_lessons_sync
                db = self._get_db_handle()
                if db is not None:
                    user_id = self._get_user_id() or "default_user"
                    lessons_str = recall_lessons_sync(
                        db=db,
                        user_id=user_id,
                        query=curr_situation,
                        agent_id=self.agent_id,
                        limit=3,
                        max_chars=1500,
                    )
                    if lessons_str:
                        logger.info(f"🧠 Recall reflection lessons from mem0 (closed loop L2/L3)")
            except Exception as lessons_exc:
                logger.debug(f"[Researcher] Recall reflection and lesson failure (not blocking): {lessons_exc}")

            # The lessons are placed at the front (reference is given priority), and the original text is placed at the back.
            if lessons_str and memory_str:
                return f"\n{lessons_str}\n [Historical experience]\n{memory_str}"
            elif lessons_str:
                return f"\n{lessons_str}"
            elif memory_str:
                logger.info(f"🧠 retrieved from memory system {len(past_memories)} relevant experience")
                return f"\n [Historical experience]\n{memory_str}"

        except Exception as e:
            logger.warning(f"Failed to obtain Memory context: {e}")

        return ""

    def _update_debate_state(
        self,
        state: Dict[str, Any],
        response: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update debate status

        Note: count is automatically incremented by the debate participant wrapper in the workflow layer and does not need to be managed by the Agent layer

        Args:
            state: Workflow status
            response: LLM Response (report content)
            result: current results dictionary

        Returns:
            Updated results dictionary
        """
        debate_state = state.get(self.debate_state_field, {})

        # Format speech
        speaker_label = self._get_speaker_label()

        # Extract report content
        if isinstance(response, dict):
            content = response.get("content", str(response))
        else:
            content = str(response)

        argument = f"{speaker_label}: {content}"

        # Construct a new debate state (excluding count, managed by the workflow layer)
        new_debate_state = debate_state.copy()

        # Update full history
        new_debate_state["history"] = debate_state.get("history", "") + "\n" + argument

        # Update your history
        if self.history_field:
            new_debate_state[self.history_field] = debate_state.get(self.history_field, "") + "\n" + argument

        # Update latest remarks
        new_debate_state["current_response"] = argument

        # Update latest speaker if field exists
        if "latest_speaker" in debate_state:
            new_debate_state["latest_speaker"] = self.stance

        # Add to results
        result[self.debate_state_field] = new_debate_state

        return result

    def _get_speaker_label(self) -> str:
        """
        Get speaker label

        Returns:
            speaker label string
        """
        labels = {
            "bull": "Bull Analyst",
            "bear": "Bear Analyst",
            "risky": "Risky Analyst",
            "safe": "Safe Analyst",
            "neutral": "Neutral Analyst",
        }
        return labels.get(self.stance, "Analyst")


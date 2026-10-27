# tradingagents/core/engine/phase_executors/research_debate.py
"""
Research debate stage executor

Perform long and short research and debate:
1. BullResearcher (See more researchers) - Analyze from an optimistic perspective
2. BearResearcher (bearish researcher) - Analyze from a cautious perspective
3. ResearchManager (research manager) - Moderate debates and formulate investment recommendations
"""

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import DataLayer
from .base import PhaseExecutor

logger = get_logger("default")


class ResearchDebatePhase(PhaseExecutor):
    """
    Research debate stage executor

    Coordinating long and short researchers to debate,
    Investment recommendations synthesized by research managers
    """

    phase_name = "ResearchDebatePhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        debate_rounds: int = 1,
        integrator: Any = None,
        memory_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize research debate phase

        Args:
            llm_provider: LLM provider
            config: stage configuration
            debate_rounds: Debate rounds
            integrator: AgentIntegrator Example
            memory_config: Memory Configuration dictionary
        """
        super().__init__(llm_provider, config)
        self.debate_rounds = debate_rounds
        self.integrator = integrator
        self.memory_config = memory_config or {}

        # Researcher Agent Cache
        self._bull_researcher = None
        self._bear_researcher = None
        self._research_manager = None

    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Executive Research Debate Stage
        """
        self.log_start()

        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"🔬 [{self.phase_name}] research debate: {ticker}")

        outputs = {
            "ticker": ticker,
            "debate_rounds": self.debate_rounds,
            "bull_report": None,
            "bear_report": None,
            "investment_plan": None
        }

        # 1. Collect analyst reports
        analyst_reports = self._collect_analyst_reports(context)
        logger.info(f"📋 [{self.phase_name}] collected {len(analyst_reports)} analysis report")

        # 2. Build initial state (Compatible with existing Agent)
        state = self._build_initial_state(context, analyst_reports)

        # 3. Execute multiple rounds of debate
        for round_num in range(self.debate_rounds):
            logger.info(f"💬 [{self.phase_name}] Debate No. {round_num + 1}/{self.debate_rounds} wheel")

            # Read more researchers' speeches
            state = self._run_bull_researcher(state)
            bull_argument = state["investment_debate_state"].get("current_response", "")

            # Bearish researcher speaks
            state = self._run_bear_researcher(state)
            bear_argument = state["investment_debate_state"].get("current_response", "")

            logger.info(f"📈 [Long] argument length: {len(bull_argument)} character")
            logger.info(f"📉 [short] argument length: {len(bear_argument)} character")

        # 4. Research managers summarize and formulate investment recommendations
        state = self._run_research_manager(state)
        investment_plan = state.get("investment_plan", "")

        # 5. Save results to Context
        bull_history = state["investment_debate_state"].get("bull_history", "")
        bear_history = state["investment_debate_state"].get("bear_history", "")

        context.set(DataLayer.REPORTS, "bull_report", bull_history, source="bull_researcher")
        context.set(DataLayer.REPORTS, "bear_report", bear_history, source="bear_researcher")
        context.set(DataLayer.DECISIONS, "investment_plan", investment_plan, source="research_manager")
        context.set(DataLayer.DECISIONS, "investment_debate_state",
                   state["investment_debate_state"], source="research_debate")

        outputs["bull_report"] = "generated" if bull_history else None
        outputs["bear_report"] = "generated" if bear_history else None
        outputs["investment_plan"] = "generated" if investment_plan else None

        logger.info(f"📝 [{self.phase_name}] Investment advice length: {len(investment_plan)} character")

        self.log_end(outputs)
        return outputs

    def _collect_analyst_reports(self, context: AnalysisContext) -> Dict[str, str]:
        """Collect all analyst reports"""
        # Dynamically get report fields from configuration
        try:
            from core.agents.config import BUILTIN_AGENTS, AgentCategory
            report_fields = []
            for agent_id, metadata in BUILTIN_AGENTS.items():
                if metadata.category == AgentCategory.ANALYST:
                    if hasattr(metadata, 'output_field') and metadata.output_field:
                        report_fields.append(metadata.output_field)
        except ImportError:
            # Fallback to hardcoding
            report_fields = [
                "market_report", "news_report", "sentiment_report",
                "fundamentals_report", "sector_report", "index_report",
            ]

        reports = {}
        for field in report_fields:
            report = context.get(DataLayer.REPORTS, field)
            if report:
                reports[field] = report

        return reports

    def _build_initial_state(
        self,
        context: AnalysisContext,
        analyst_reports: Dict[str, str]
    ) -> Dict[str, Any]:
        """Build an initial state that is compatible with existing Agents"""
        ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
        trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

        # Build status
        state = {
            "company_of_interest": ticker,
            "trade_date": trade_date,
            "messages": [],
            # The state of the investment debate
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "bear_history": "",
                "current_response": "",
                "count": 0,
                "judge_decision": ""
            }
        }

        # Add analyst report
        for field, report in analyst_reports.items():
            state[field] = report

        return state

    def _get_bull_researcher(self):
        """Get or create a multi-viewer"""
        if self._bull_researcher is None:
            try:
                from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
                memory = self.memory_config.get("bull_memory")
                self._bull_researcher = create_bull_researcher(self.llm_provider, memory)
                logger.debug("🐂 [ResearchDebate] Create BullResearcher Agent")
            except Exception as e:
                logger.error(f"❌ [ResearchDebate] Failed to create BullResearcher: {e}")
        return self._bull_researcher

    def _get_bear_researcher(self):
        """Get or create a bearish researcher"""
        if self._bear_researcher is None:
            try:
                from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
                memory = self.memory_config.get("bear_memory")
                self._bear_researcher = create_bear_researcher(self.llm_provider, memory)
                logger.debug("🐻 [ResearchDebate] Create BearResearcher Agent")
            except Exception as e:
                logger.error(f"❌ [ResearchDebate] Failed to create BearResearcher: {e}")
        return self._bear_researcher

    def _get_research_manager(self):
        """Get or create a research manager"""
        if self._research_manager is None:
            try:
                from tradingagents.agents.managers.research_manager import create_research_manager
                memory = self.memory_config.get("invest_judge_memory")
                self._research_manager = create_research_manager(self.llm_provider, memory)
                logger.debug("👔 [ResearchDebate] Create ResearchManager Agent")
            except Exception as e:
                logger.error(f"❌ [ResearchDebate] Failed to create ResearchManager: {e}")
        return self._research_manager

    def _run_bull_researcher(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute long research"""
        agent = self._get_bull_researcher()
        if agent:
            try:
                result = agent(state)
                # Merge results into state
                if "investment_debate_state" in result:
                    state["investment_debate_state"] = result["investment_debate_state"]
                logger.info(f"🐂 [multi-investigator] Speech completed")
            except Exception as e:
                logger.error(f"❌ [multi-investigator] Execution failed: {e}")
        else:
            # pile implementation
            logger.warning("⚠️ [ResearchDebate] BullResearcher Not available, use stubs to implement")
            state["investment_debate_state"]["bull_history"] = "[pile] Read more analysis reports"
            state["investment_debate_state"]["count"] += 1
        return state

    def _run_bear_researcher(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform bearish research"""
        agent = self._get_bear_researcher()
        if agent:
            try:
                result = agent(state)
                if "investment_debate_state" in result:
                    state["investment_debate_state"] = result["investment_debate_state"]
                logger.info(f"🐻 [short researcher] Speech completed")
            except Exception as e:
                logger.error(f"❌ [short researcher] Execution failed: {e}")
        else:
            logger.warning("⚠️ [ResearchDebate] BearResearcher Not available, use stubs to implement")
            state["investment_debate_state"]["bear_history"] = "[pile] Bearish analysis report"
            state["investment_debate_state"]["count"] += 1
        return state

    def _run_research_manager(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Executive Research Manager Summary"""
        agent = self._get_research_manager()
        if agent:
            try:
                result = agent(state)
                if "investment_debate_state" in result:
                    state["investment_debate_state"] = result["investment_debate_state"]
                if "investment_plan" in result:
                    state["investment_plan"] = result["investment_plan"]
                logger.info(f"👔 [research manager] Investment advice generation completed")
            except Exception as e:
                logger.error(f"❌ [research manager] Execution failed: {e}")
                state["investment_plan"] = "[Error] Investment advice generation failed"
        else:
            logger.warning("⚠️ [ResearchDebate] ResearchManager Not available, use stubs to implement")
            state["investment_plan"] = "[pile] investment advice"
        return state


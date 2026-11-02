from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['base', 'data_collection', 'analysts', 'research_debate', 'risk_assessment', 'trade_decision']:
    _sys.modules[f"tradingagents.core.engine.phase_executors.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === base.py ===
# tradingagents/core/engine/phase_executors/base.py
"""
stage executor base class

Define standard interfaces and common functions for phase execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import AgentDataContract, DataLayer

logger = get_logger("default")


@dataclass
class PhaseContext:
    """
    stage execution context
    
    All dependencies required for encapsulation phase execution
    """
    analysis_context: AnalysisContext
    data_manager: DataAccessManager
    llm_provider: Any = None
    config: Dict[str, Any] = field(default_factory=dict)
    
    def get_ticker(self) -> str:
        """Get stock code"""
        return self.analysis_context.get(DataLayer.CONTEXT, "ticker") or ""
    
    def get_trade_date(self) -> str:
        """Get transaction date"""
        return self.analysis_context.get(DataLayer.CONTEXT, "trade_date") or ""
    
    def get_market_type(self) -> str:
        """Get market type"""
        return self.analysis_context.get(DataLayer.CONTEXT, "market_type") or "cn"


class PhaseExecutor(ABC):
    """
    stage executor base class
    
    All stage executors need to inherit this class and implement the execute method
    
    Usage:
        class DataCollectionPhase(PhaseExecutor):
            def execute(self, context, data_manager):
                # Perform data collection
                return {"collected": True}
    """
    
    # Stage name (subclasses should override)
    phase_name: str = "base"
    
    # List of contracts required by the stage (can be overridden by subclasses)
    required_contracts: List[AgentDataContract] = []
    
    def __init__(self, llm_provider: Any = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialization phase executor
        
        Args:
            llm_provider: LLM provider instance
            config: stage configuration
        """
        self.llm_provider = llm_provider
        self.config = config or {}
    
    @abstractmethod
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execution phase
        
        Args:
            context: Analyze context
            data_manager: Data Access Manager
            
        Returns:
            stage output dictionary
        """
        pass
    
    def validate_inputs(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> bool:
        """
        Validation phase input
        
        Check if all required input data exists
        
        Args:
            context: Analyze context
            data_manager: Data Access Manager
            
        Returns:
            Verification passed
        """
        for contract in self.required_contracts:
            for access in contract.inputs:
                if access.required:
                    for field_name in access.fields:
                        value = context.get(access.layer, field_name)
                        if value is None:
                            logger.warning(
                                f"⚠️ [{self.phase_name}] Missing required input: "
                                f"{access.layer.value}.{field_name}"
                            )
                            return False
        return True
    
    def create_phase_context(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> PhaseContext:
        """Create stage context"""
        return PhaseContext(
            analysis_context=context,
            data_manager=data_manager,
            llm_provider=self.llm_provider,
            config=self.config
        )
    
    def log_start(self) -> None:
        """Recording phase begins"""
        logger.info(f"▶️ [{self.phase_name}] stage starts execution")
    
    def log_end(self, outputs: Dict[str, Any]) -> None:
        """End of recording phase"""
        output_keys = list(outputs.keys()) if outputs else []
        logger.info(f"✅ [{self.phase_name}] Stage execution completed, output: {output_keys}")


# === data_collection.py ===
# tradingagents/core/engine/phase_executors/data_collection.py
"""
Data collection phase executor (initialization phase)

Responsibilities:
- Initialize basic information of the analysis context
- Verify the validity of input parameters
- Optional: Preload public basic data (such as basic company information)

Note:
- This stage does not replace the Agent s tools data acquisition capabilities.
- Agent Still get the required data from dataflows through their respective tools
- Agent Write the analysis results to the Context for other Agents to read
"""

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import DataLayer

logger = get_logger("default")


class DataCollectionPhase(PhaseExecutor):
    """
    Data collection phase executor (actually initialization phase)

    Main responsibilities:
    1. Validate and normalize input parameters (ticker, trade_date etc.)
    2. Initialize basic information of Context
    3. Optional: Preload public data such as basic company information

    Note: Original data acquisition is completed by each Agent through tools.
    """

    phase_name = "DataCollectionPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initial data collection phase

        Args:
            llm_provider: LLM Provider (not required at this stage)
            config: stage configuration
        """
        super().__init__(llm_provider, config)

    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execute initialization phase

        Args:
            context: Analyze context
            data_manager: Data Access Manager

        Returns:
            Summary of initialization results
        """
        self.log_start()

        # Obtain and verify contextual information
        ticker = context.get(DataLayer.CONTEXT, "ticker")
        trade_date = context.get(DataLayer.CONTEXT, "trade_date")
        company_name = context.get(DataLayer.CONTEXT, "company_name")
        market_type = context.get(DataLayer.CONTEXT, "market_type") or self._detect_market_type(ticker)

        logger.info(f"📊 [{self.phase_name}] Initialize analysis context: {ticker} ({trade_date})")

        # Verify necessary parameters
        if not ticker:
            raise ValueError("ticker is a required parameter")
        if not trade_date:
            raise ValueError("trade_date is a required parameter")

        # Normalize ticker format
        normalized_ticker = self._normalize_ticker(ticker, market_type)
        if normalized_ticker != ticker:
            context.set(DataLayer.CONTEXT, "ticker", normalized_ticker, source=self.phase_name)
            logger.debug(f"📊 [{self.phase_name}] ticker Standardize: {ticker} -> {normalized_ticker}")

        # Set market type (if not set)
        if not context.get(DataLayer.CONTEXT, "market_type"):
            context.set(DataLayer.CONTEXT, "market_type", market_type, source=self.phase_name)

        # Build output summary
        outputs = {
            "ticker": normalized_ticker,
            "trade_date": trade_date,
            "company_name": company_name,
            "market_type": market_type,
            "initialized": True
        }

        self.log_end(outputs)
        return outputs

    def _detect_market_type(self, ticker: str) -> str:
        """
        Detect market type based on ticker format

        Args:
            ticker: Stock code

        Returns:
            market type ("cn", "us", "hk")
        """
        if not ticker:
            return "cn"

        ticker_upper = ticker.upper()

        # China A share format
        if ticker_upper.endswith((".SZ", ".SH", ".BJ")):
            return "cn"
        if ticker.isdigit() and len(ticker) == 6:
            return "cn"

        # Hong Kong stock format
        if ticker_upper.endswith(".HK"):
            return "hk"

        # Default is US stocks
        return "us"

    def _normalize_ticker(self, ticker: str, market_type: str) -> str:
        """
        Normalize ticker format

        Note: The front and back ends agree that A-share codes use pure 6-digit numbers without suffixes.

        Args:
            ticker: Original stock symbol
            market_type: market type

        Returns:
            Standardized stock code
        """
        import re

        if not ticker:
            return ticker

        ticker = ticker.strip().upper()

        if market_type == "cn":
            # China A-shares: remove the suffix and keep only the pure 6-digit number (the front and back ends are unified)
            ticker = re.sub(r'\.(SZ|SH|BJ)$', '', ticker)
            return ticker

        # Other markets remain as is
        return ticker


# === analysts.py ===
# tradingagents/core/engine/phase_executors/analysts.py
"""
Analyst stage executor

Execute multiple analyst agents in parallel:
- MarketAnalyst (Technical analysis)
- NewsAnalyst (news analysis)
- SentimentAnalyst (sentiment analysis)
- FundamentalsAnalyst (fundamental analysis)
- SectorAnalyst (Sector analysis)
- IndexAnalyst (Market analysis)
"""

from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import DataLayer, AgentDataContract
from .agent_integrator import AgentIntegrator

logger = get_logger("default")


class AnalystsPhase(PhaseExecutor):
    """
    Analyst stage executor

    Execute all selected analyst agents in parallel,
    Collect analysis reports and write them to the Reports layer
    """

    phase_name = "AnalystsPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        selected_analysts: Optional[List[str]] = None,
        max_workers: int = 4,
        llm: Any = None,
        toolkit: Any = None,
        use_stub: bool = False
    ):
        """
        Initialize analyst phase

        Args:
            llm_provider: LLM Provider (used to create LLM)
            config: stage configuration
            selected_analysts: Selected analyst list, None means all
            max_workers: Maximum number of worker threads for parallel execution
            llm: Created LLM instance (preferred)
            toolkit: Toolset examples
            use_stub: Whether to use stub implementation (for testing)
        """
        super().__init__(llm_provider, config)
        self.selected_analysts = selected_analysts
        self.max_workers = max_workers
        self.use_stub = use_stub

        # Agent Integrator (lazy initialization)
        self._integrator: Optional[AgentIntegrator] = None
        self._llm = llm
        self._toolkit = toolkit
    
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Executive analyst stage
        
        Args:
            context: Analyze context
            data_manager: Data Access Manager
            
        Returns:
            Summary of analysis results
        """
        self.log_start()
        
        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"📊 [{self.phase_name}] Analyze stocks: {ticker}")
        
        # Get the list of analysts to execute
        analysts_to_run = self._get_analysts_to_run()
        
        outputs = {
            "ticker": ticker,
            "analysts_run": [],
            "analysts_failed": [],
            "reports_generated": []
        }
        
        # Parallel Execution Analyst
        if self.max_workers > 1 and len(analysts_to_run) > 1:
            self._run_parallel(analysts_to_run, context, data_manager, outputs)
        else:
            self._run_sequential(analysts_to_run, context, data_manager, outputs)
        
        self.log_end(outputs)
        return outputs
    
    def _get_analysts_to_run(self) -> List[str]:
        """Get the list of analysts to execute"""
        # Default analyst list
        default_analysts = [
            "market_analyst",
            "news_analyst",
            "sentiment_analyst",
            "fundamentals_analyst",
            "sector_analyst",
            "index_analyst",
        ]
        
        if self.selected_analysts:
            return [a for a in self.selected_analysts if a in default_analysts]
        return default_analysts
    
    def _run_sequential(
        self,
        analysts: List[str],
        context: AnalysisContext,
        data_manager: DataAccessManager,
        outputs: Dict[str, Any]
    ) -> None:
        """sequential execution analyst"""
        for analyst_id in analysts:
            try:
                result = self._run_single_analyst(analyst_id, context, data_manager)
                outputs["analysts_run"].append(analyst_id)
                if result.get("report_field"):
                    outputs["reports_generated"].append(result["report_field"])
            except Exception as e:
                logger.error(f"❌ [{self.phase_name}] {analyst_id} Execution failed: {e}")
                outputs["analysts_failed"].append(analyst_id)
    
    def _run_parallel(
        self,
        analysts: List[str],
        context: AnalysisContext,
        data_manager: DataAccessManager,
        outputs: Dict[str, Any]
    ) -> None:
        """Parallel Execution Analyst"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._run_single_analyst, analyst_id, context, data_manager
                ): analyst_id
                for analyst_id in analysts
            }
            
            for future in as_completed(futures):
                analyst_id = futures[future]
                try:
                    result = future.result()
                    outputs["analysts_run"].append(analyst_id)
                    if result.get("report_field"):
                        outputs["reports_generated"].append(result["report_field"])
                except Exception as e:
                    logger.error(f"❌ [{self.phase_name}] {analyst_id} Execution failed: {e}")
                    outputs["analysts_failed"].append(analyst_id)

    def _get_integrator(self) -> Optional[AgentIntegrator]:
        """Get or create an Agent integrator"""
        if self._integrator is not None:
            return self._integrator

        if self._llm is not None and self._toolkit is not None:
            self._integrator = AgentIntegrator(self._llm, self._toolkit)
            logger.debug(f"🔧 [{self.phase_name}] Create Agent Integrator")
            return self._integrator

        return None

    def _run_single_analyst(
        self,
        analyst_id: str,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execute a single analyst

        Args:
            analyst_id: analyst ID
            context: Analyze context
            data_manager: Data Access Manager

        Returns:
            Execution result
        """
        logger.info(f"🔍 [{self.phase_name}] executive analyst: {analyst_id}")

        # Force the use of stubs or use stubs when there is no integrator
        if self.use_stub:
            return self._run_stub_analyst(analyst_id, context)

        # Get Agent Integrator
        integrator = self._get_integrator()
        if integrator is None:
            logger.debug(f"⚠️ [{self.phase_name}] No integrator, use stubs: {analyst_id}")
            return self._run_stub_analyst(analyst_id, context)

        # get Agent
        agent = integrator.get_agent(analyst_id)
        if agent is None:
            logger.debug(f"⚠️ [{self.phase_name}] Agent Not available, use stub: {analyst_id}")
            return self._run_stub_analyst(analyst_id, context)

        # Execute actual Agent
        return self._run_real_analyst(analyst_id, agent, context, integrator)

    def _run_real_analyst(
        self,
        analyst_id: str,
        agent: Any,
        context: AnalysisContext,
        integrator: AgentIntegrator
    ) -> Dict[str, Any]:
        """
        Analysts who perform actual Agent

        Args:
            analyst_id: analyst ID
            agent: Agent node function
            context: Analyze context
            integrator: Agent integrator

        Returns:
            Execution result
        """
        try:
            # Convert Context to AgentState
            state = integrator.context_to_state(context)

            logger.debug(f"📤 [{self.phase_name}] call Agent: {analyst_id}")

            # Use the complete tool to call loop execution Agent
            result = integrator.run_agent_with_tools(agent, state, analyst_id)

            # Extract report
            report_field, report_content = integrator.extract_report(analyst_id, result)

            if report_content:
                # Write to Reports layer
                context.set(DataLayer.REPORTS, report_field, report_content, source=analyst_id)
                logger.info(f"📝 [{self.phase_name}] Generate report: {report_field} ({len(report_content)} character)")
            else:
                logger.warning(f"⚠️ [{self.phase_name}] Agent Report not returned: {analyst_id}")

            return {"analyst_id": analyst_id, "report_field": report_field}

        except Exception as e:
            logger.error(f"❌ [{self.phase_name}] Agent Execution exception {analyst_id}: {e}")
            raise

    def _run_stub_analyst(
        self,
        analyst_id: str,
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """
        Run stub analyst (for testing)

        Generate placeholder reports and write them to the Reports layer
        """
        # Analyst output field mapping
        output_field_map = {
            "market_analyst": "market_report",
            "news_analyst": "news_report",
            "sentiment_analyst": "sentiment_report",
            "fundamentals_analyst": "fundamentals_report",
            "sector_analyst": "sector_report",
            "index_analyst": "index_report",
        }

        report_field = output_field_map.get(analyst_id)
        if report_field:
            # Generate placeholder report
            ticker = context.get(DataLayer.CONTEXT, "ticker")
            stub_report = f"[{analyst_id}] Analysis report placeholder - {ticker}"

            # Write to Reports layer
            context.set(DataLayer.REPORTS, report_field, stub_report, source=analyst_id)

            logger.debug(f"📝 [{self.phase_name}] Generate stub report: {report_field}")

        return {"analyst_id": analyst_id, "report_field": report_field}

    def set_dependencies(self, llm: Any, toolkit: Any) -> "AnalystsPhase":
        """
        Set dependencies

        Args:
            llm: LLM Example
            toolkit: Toolset examples

        Returns:
            self (Supports chain calls)
        """
        self._llm = llm
        self._toolkit = toolkit
        self._integrator = None  # reset integrator
        return self

# === research_debate.py ===
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

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import DataLayer

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
                logger.info("🐂 [multi-investigator] Speech completed")
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
                logger.info("🐻 [short researcher] Speech completed")
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
                logger.info("👔 [research manager] Investment advice generation completed")
            except Exception as e:
                logger.error(f"❌ [research manager] Execution failed: {e}")
                state["investment_plan"] = "[Error] Investment advice generation failed"
        else:
            logger.warning("⚠️ [ResearchDebate] ResearchManager Not available, use stubs to implement")
            state["investment_plan"] = "[pile] investment advice"
        return state


# === risk_assessment.py ===
# tradingagents/core/engine/phase_executors/risk_assessment.py
"""
Risk assessment stage executor

Perform a multi-dimensional risk assessment:
1. RiskyRisk (Radical risk control) - High risk tolerance
2. SafeRisk (Robust risk control) - Low risk tolerance
3. NeutralRisk (Neutral risk control) - Balance risk and reward
4. RiskManager (Risk Control Manager) - Comprehensive evaluation to form final decision
"""

from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import DataLayer

logger = get_logger("default")


class RiskAssessmentPhase(PhaseExecutor):
    """
    Risk assessment stage executor

    Perform multi-dimensional risk assessments to form final analysis results
    """

    phase_name = "RiskAssessmentPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        risk_profiles: Optional[List[str]] = None,
        debate_rounds: int = 1,
        memory_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initial risk assessment phase

        Args:
            llm_provider: LLM provider
            config: stage configuration
            risk_profiles: Risk control type list, default all
            debate_rounds: Debate rounds
            memory_config: Memory Configuration
        """
        super().__init__(llm_provider, config)
        self.risk_profiles = risk_profiles or ["risky", "safe", "neutral"]
        self.debate_rounds = debate_rounds
        self.memory_config = memory_config or {}

        # Agent cache
        self._risky_analyst = None
        self._safe_analyst = None
        self._neutral_analyst = None
        self._risk_manager = None
    
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Perform risk assessment phase
        """
        self.log_start()

        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"⚖️ [{self.phase_name}] risk assessment: {ticker}")

        outputs = {
            "ticker": ticker,
            "risk_reports": [],
            "final_decision": None
        }

        # Get trading signals and trader plans
        trade_signal = context.get(DataLayer.DECISIONS, "trade_signal")
        trader_plan = context.get(DataLayer.DECISIONS, "trader_investment_plan")
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan")

        if trade_signal is None and trader_plan is None:
            logger.warning(f"⚠️ [{self.phase_name}] No trading signal found, risk assessment skipped")
            self.log_end(outputs)
            return outputs

        # Build initial state
        state = self._build_initial_state(context, trader_plan or str(investment_plan))

        # Conduct multiple rounds of risk control debates
        for round_num in range(self.debate_rounds):
            logger.info(f"💬 [{self.phase_name}] Risk Control Debate No. {round_num + 1}/{self.debate_rounds} wheel")

            # Radical risk control speech
            if "risky" in self.risk_profiles:
                state = self._run_risky_analyst(state)
                outputs["risk_reports"].append("risky")

            # Speech on Steady Risk Control
            if "safe" in self.risk_profiles:
                state = self._run_safe_analyst(state)
                outputs["risk_reports"].append("safe")

            # Neutral risk control speech
            if "neutral" in self.risk_profiles:
                state = self._run_neutral_analyst(state)
                outputs["risk_reports"].append("neutral")

        # Risk control manager summary
        state = self._run_risk_manager(state)

        # Save results
        risk_debate_state = state.get("risk_debate_state", {})

        # 🔥 Modification: Generate final_trade_decision (comprehensive investment advice, trading plan, risk assessment)
        final_trade_decision = self._generate_final_trade_decision(context)
        state["final_trade_decision"] = final_trade_decision

        context.set(DataLayer.DECISIONS, "risk_debate_state", risk_debate_state, source="risk_assessment")
        context.set(DataLayer.DECISIONS, "final_trade_decision", final_trade_decision, source="risk_assessment")

        # Generate final decision
        final_decision = self._form_final_decision_from_text(context, trade_signal, final_trade_decision)
        context.set(DataLayer.DECISIONS, "final_decision", final_decision, source="risk_manager")
        outputs["final_decision"] = final_decision.get("action")

        logger.info(f"📝 [{self.phase_name}] final decision: {final_decision.get('action')}")

        self.log_end(outputs)
        return outputs

    def _build_initial_state(self, context: AnalysisContext, trader_plan: str) -> Dict[str, Any]:
        """Build initial state"""
        ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
        trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

        return {
            "company_of_interest": ticker,
            "trade_date": trade_date,
            "trader_investment_plan": trader_plan,
            "investment_plan": context.get(DataLayer.DECISIONS, "investment_plan") or "",
            "market_report": context.get(DataLayer.REPORTS, "market_report") or "",
            "sentiment_report": context.get(DataLayer.REPORTS, "sentiment_report") or "",
            "news_report": context.get(DataLayer.REPORTS, "news_report") or "",
            "fundamentals_report": context.get(DataLayer.REPORTS, "fundamentals_report") or "",
            "risk_debate_state": {
                "history": "",
                "risky_history": "",
                "safe_history": "",
                "neutral_history": "",
                "current_risky_response": "",
                "current_safe_response": "",
                "current_neutral_response": "",
                "count": 0,
                "judge_decision": ""
            }
        }

    def _get_risky_analyst(self):
        """Obtain or create aggressive risk controls"""
        if self._risky_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator
                self._risky_analyst = create_risky_debator(self.llm_provider)
                logger.debug("🔥 [RiskAssessment] Create RiskyAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating RiskyAnalyst failed: {e}")
        return self._risky_analyst

    def _get_safe_analyst(self):
        """Obtain or create robust risk controls"""
        if self._safe_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator
                self._safe_analyst = create_safe_debator(self.llm_provider)
                logger.debug("🛡️ [RiskAssessment] Create SafeAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating SafeAnalyst failed: {e}")
        return self._safe_analyst

    def _get_neutral_analyst(self):
        """Obtain or create neutral risk controls"""
        if self._neutral_analyst is None:
            try:
                from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
                self._neutral_analyst = create_neutral_debator(self.llm_provider)
                logger.debug("⚖️ [RiskAssessment] Create NeutralAnalyst")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Failed to create NeutralAnalyst: {e}")
        return self._neutral_analyst

    def _get_risk_manager(self):
        """Get or create a risk control manager"""
        if self._risk_manager is None:
            try:
                from tradingagents.agents.managers.risk_manager import create_risk_manager
                memory = self.memory_config.get("risk_memory")
                self._risk_manager = create_risk_manager(self.llm_provider, memory)
                logger.debug("👔 [RiskAssessment] Create RiskManager")
            except Exception as e:
                logger.error(f"❌ [RiskAssessment] Creating RiskManager failed: {e}")
        return self._risk_manager

    def _run_risky_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement aggressive risk control"""
        agent = self._get_risky_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("🔥 [Radical risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Radical risk control] Execution failed: {e}")
        return state

    def _run_safe_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement robust risk control"""
        agent = self._get_safe_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("🛡️ [Robust risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Robust risk control] Execution failed: {e}")
        return state

    def _run_neutral_analyst(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Implement neutral risk control"""
        agent = self._get_neutral_analyst()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                logger.info("⚖️ [Neutral risk control] Speech completed")
            except Exception as e:
                logger.error(f"❌ [Neutral risk control] Execution failed: {e}")
        return state

    def _run_risk_manager(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Executive risk control manager summary"""
        agent = self._get_risk_manager()
        if agent:
            try:
                result = agent(state)
                if "risk_debate_state" in result:
                    state["risk_debate_state"] = result["risk_debate_state"]
                if "final_trade_decision" in result:
                    state["final_trade_decision"] = result["final_trade_decision"]
                logger.info("👔 [Risk Control Manager] The final decision is generated")
            except Exception as e:
                logger.error(f"❌ [Risk Control Manager] Execution failed: {e}")
                state["final_trade_decision"] = "[Error] Risk control decision generation failed"
        return state

    def _form_final_decision_from_text(
        self,
        context: AnalysisContext,
        trade_signal: Optional[Dict[str, Any]],
        final_text: str
    ) -> Dict[str, Any]:
        """Generate final decision from risk text (using SignalProcessor to maintain consistency with legacy)"""
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # 🔥 Use SignalProcessor to process final_trade_decision text
        # This can extract target_price and reasoning, consistent with the old version
        try:
            from tradingagents.graph.signal_processing import SignalProcessor
            signal_processor = SignalProcessor()
            decision = signal_processor.process_signal(final_text, ticker)
            logger.info(f"✅ [RiskAssessment] Use SignalProcessor to handle decisions: {decision}")

            # Map reasoning to rationale to maintain compatibility
            if "reasoning" in decision and "rationale" not in decision:
                decision["rationale"] = decision["reasoning"]

            # Add risk_level field
            if "risk_level" not in decision:
                decision["risk_level"] = self._determine_risk_level_from_text(final_text)

            # Add ticker field
            decision["ticker"] = ticker

            # If there is a raw trading signal, add original_rationale
            if trade_signal and isinstance(trade_signal, dict):
                original_rationale = trade_signal.get("rationale", "")
                decision["original_rationale"] = original_rationale[:200] if original_rationale else ""

            return decision

        except Exception as e:
            logger.warning(f"⚠️ [RiskAssessment] SignalProcessor Handling failed, use simple parsing: {e}")

            # Downgrade to simple parsing
            action, confidence = self._parse_action_from_text(final_text)

            # If there are original trading signals, merge the information
            if trade_signal and isinstance(trade_signal, dict):
                original_position = trade_signal.get("position_size", 0.0)
                original_rationale = trade_signal.get("rationale", "")
            else:
                original_position = 0.5
                original_rationale = ""

            # Adjust positions according to risk control recommendations
            if action == "HOLD":
                position_size = 0.0
            else:
                position_size = min(confidence, 1.0) * original_position if original_position > 0 else confidence * 0.5

            return {
                "ticker": ticker,
                "action": action,
                "position_size": position_size,
                "confidence": confidence,
                "risk_level": self._determine_risk_level_from_text(final_text),
                "rationale": final_text[:500] if len(final_text) > 500 else final_text,
                "reasoning": final_text[:500] if len(final_text) > 500 else final_text,  # Add reasoning field
                "original_rationale": original_rationale[:200] if original_rationale else "",
                "target_price": None,  # Add target_price field
                "risk_score": 0.5,  # Add risk_score field
            }

    def _parse_action_from_text(self, text: str) -> tuple:
        """Parse transaction actions from text"""
        text_lower = text.lower()

        buy_keywords = ["buy", "Overweight", "long", "Recommended to buy", "buy", "bullish"]
        sell_keywords = ["sell", "Reduce holdings", "bearish", "Recommended to sell", "sell", "bearish"]
        hold_keywords = ["hold", "wait and see", "hold", "neutral", "Neutral"]

        buy_score = sum(1 for kw in buy_keywords if kw in text_lower)
        sell_score = sum(1 for kw in sell_keywords if kw in text_lower)
        hold_score = sum(1 for kw in hold_keywords if kw in text_lower)

        if buy_score > sell_score and buy_score > hold_score:
            return "BUY", min(0.5 + buy_score * 0.1, 0.9)
        elif sell_score > buy_score and sell_score > hold_score:
            return "SELL", min(0.5 + sell_score * 0.1, 0.9)
        else:
            return "HOLD", 0.5

    def _determine_risk_level_from_text(self, text: str) -> str:
        """Determine risk level from text"""
        text_lower = text.lower()

        high_risk_keywords = ["high risk", "Riskier", "cautious", "danger", "high risk"]
        low_risk_keywords = ["low risk", "safe", "Robust", "low risk"]

        high_score = sum(1 for kw in high_risk_keywords if kw in text_lower)
        low_score = sum(1 for kw in low_risk_keywords if kw in text_lower)

        if high_score > low_score:
            return "high"
        elif low_score > high_score:
            return "low"
        else:
            return "medium"

    def _generate_final_trade_decision(self, context: "AnalysisContext") -> str:
        """
        Generate final analysis results

        Taking into account the following:
        1. investment_plan (Research Manager s Investment Advice)
        2. trader_investment_plan (Trader s Trading Plan)
        3. risk_debate_state.judge_decision (Risk assessment for risk managers)

        Args:
            context: Analyze context

        Returns:
            Final analysis result text (Markdown format)
        """
        from tradingagents.core.engine.data_layer import DataLayer

        # Extract individual reports
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan") or ""
        trader_plan = context.get(DataLayer.DECISIONS, "trader_investment_plan") or ""
        risk_debate_state = context.get(DataLayer.DECISIONS, "risk_debate_state") or {}
        risk_assessment = risk_debate_state.get("judge_decision", "") if isinstance(risk_debate_state, dict) else ""

        # If all three are empty, return an empty string
        if not any([investment_plan, trader_plan, risk_assessment]):
            logger.warning("⚠️ [RiskAssessment] Unable to generate final_trade_decision: all input reports are empty")
            return ""

        # Build the final decision (Markdown format)
        sections = []

        if investment_plan:
            sections.append(f"## 📋 investment advice\n\n{investment_plan}")

        if trader_plan:
            sections.append(f"## 💼 trading plan\n\n{trader_plan}")

        if risk_assessment:
            sections.append(f"## ⚠️ risk assessment\n\n{risk_assessment}")

        final_decision = "\n\n".join(sections)
        logger.info(f"✅ [RiskAssessment] Generate final_trade_decision, containing {len(sections)} parts")

        return final_decision


# === trade_decision.py ===
# tradingagents/core/engine/phase_executors/trade_decision.py
"""
Trade decision stage executor

Generate trading signals based on research conclusions:
- Trader (trader) - Generate specific trading signals
"""

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_access_manager import DataAccessManager
from .data_contract import DataLayer

logger = get_logger("default")


class TradeDecisionPhase(PhaseExecutor):
    """
    Trade decision stage executor

    Generate specific trading signals based on investment recommendations
    """

    phase_name = "TradeDecisionPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None,
        memory_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize transaction decision phase

        Args:
            llm_provider: LLM provider
            config: stage configuration
            memory_config: Memory Configuration
        """
        super().__init__(llm_provider, config)
        self.memory_config = memory_config or {}
        self._trader = None
    
    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execution transaction decision stage
        """
        self.log_start()

        ticker = context.get(DataLayer.CONTEXT, "ticker")
        logger.info(f"💹 [{self.phase_name}] Generate trading signals: {ticker}")

        outputs = {
            "ticker": ticker,
            "trade_signal": None,
            "trader_investment_plan": None
        }

        # Get investment advice
        investment_plan = context.get(DataLayer.DECISIONS, "investment_plan")

        if investment_plan is None:
            logger.warning(f"⚠️ [{self.phase_name}] No investment advice found, trading decision skipped")
            self.log_end(outputs)
            return outputs

        # use actual Trader Agent
        trader_result = self._run_trader(context, investment_plan)

        if trader_result:
            trader_plan = trader_result.get("trader_investment_plan", "")

            # Save a trader's investment plan
            context.set(DataLayer.DECISIONS, "trader_investment_plan", trader_plan, source="trader")
            outputs["trader_investment_plan"] = "generated" if trader_plan else None

            # Parse trading signals from trader results
            trade_signal = self._parse_trade_signal(context, trader_plan, investment_plan)
            context.set(DataLayer.DECISIONS, "trade_signal", trade_signal, source="trader")
            outputs["trade_signal"] = trade_signal.get("action")

            logger.info(f"📝 [{self.phase_name}] trading signals: {trade_signal.get('action')}, "
                       f"Confidence: {trade_signal.get('confidence', 0):.2f}")
        else:
            # Fallback to simple parsing
            trade_signal = self._generate_trade_signal(context, investment_plan)
            context.set(DataLayer.DECISIONS, "trade_signal", trade_signal, source="trader")
            outputs["trade_signal"] = trade_signal.get("action")

        self.log_end(outputs)
        return outputs

    def _get_trader(self):
        """Get or create Trader Agent"""
        if self._trader is None:
            try:
                from tradingagents.agents.trader.trader import create_trader
                # Supports two key formats: "trader" or "trader_memory"
                memory = self.memory_config.get("trader") or self.memory_config.get("trader_memory")
                self._trader = create_trader(self.llm_provider, memory)
                logger.debug("💰 [TradeDecision] Create Trader Agent")
            except Exception as e:
                logger.error(f"❌ [TradeDecision] Failed to create Trader: {e}")
        return self._trader

    def _run_trader(self, context: AnalysisContext, investment_plan: Any) -> Optional[Dict[str, Any]]:
        """run Trader Agent"""
        trader = self._get_trader()
        if not trader:
            logger.warning("⚠️ [TradeDecision] Trader Not available, use simple parsing")
            return None

        try:
            # Build state that is compatible with existing agents
            ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
            trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

            state = {
                "company_of_interest": ticker,
                "trade_date": trade_date,
                "investment_plan": investment_plan if isinstance(investment_plan, str) else str(investment_plan),
                # Collect all analysis reports
                "market_report": context.get(DataLayer.REPORTS, "market_report") or "",
                "sentiment_report": context.get(DataLayer.REPORTS, "sentiment_report") or "",
                "news_report": context.get(DataLayer.REPORTS, "news_report") or "",
                "fundamentals_report": context.get(DataLayer.REPORTS, "fundamentals_report") or "",
                "sector_report": context.get(DataLayer.REPORTS, "sector_report") or "",
                "index_report": context.get(DataLayer.REPORTS, "index_report") or "",
            }

            result = trader(state)
            logger.info("💰 [Trader] Transaction decision generation completed")
            return result

        except Exception as e:
            logger.error(f"❌ [Trader] Execution failed: {e}")
            return None

    def _parse_trade_signal(
        self,
        context: AnalysisContext,
        trader_plan: str,
        investment_plan: Any
    ) -> Dict[str, Any]:
        """Parsing trading signals from trader plans"""
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # Merge text for analysis
        combined_text = trader_plan
        if isinstance(investment_plan, str):
            combined_text = f"{investment_plan}\n{trader_plan}"

        recommendation, confidence = self._parse_recommendation_from_text(combined_text)

        action_map = {
            "buy": "BUY",
            "sell": "SELL",
            "hold": "HOLD"
        }
        action = action_map.get(recommendation.lower(), "HOLD")

        if action == "HOLD":
            position_size = 0.0
        else:
            position_size = min(confidence, 1.0)

        return {
            "ticker": ticker,
            "action": action,
            "position_size": position_size,
            "confidence": confidence,
            "rationale": trader_plan[:500] if len(trader_plan) > 500 else trader_plan,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "timestamp": None
        }
    
    def _generate_trade_signal(
        self,
        context: AnalysisContext,
        investment_plan: Any
    ) -> Dict[str, Any]:
        """
        Generate trading signals

        TODO: Integrate actual Trader Agent

        Args:
            context: Analyze context
            investment_plan: investment advice (may be a dictionary or string)

        Returns:
            trading signals
        """
        ticker = context.get(DataLayer.CONTEXT, "ticker")

        # Handle different types of investment advice
        if isinstance(investment_plan, dict):
            recommendation = investment_plan.get("recommendation", "hold")
            confidence = investment_plan.get("confidence", 0.5)
            rationale = investment_plan.get("rationale", "")
        elif isinstance(investment_plan, str):
            # Extract suggestions from text
            recommendation, confidence = self._parse_recommendation_from_text(investment_plan)
            rationale = investment_plan[:500] if len(investment_plan) > 500 else investment_plan
        else:
            recommendation = "hold"
            confidence = 0.5
            rationale = ""

        # Generate trading signals based on investment recommendations
        action_map = {
            "buy": "BUY",
            "sell": "SELL",
            "hold": "HOLD"
        }

        action = action_map.get(recommendation.lower(), "HOLD")

        # Calculate positions based on confidence
        if action == "HOLD":
            position_size = 0.0
        else:
            position_size = min(confidence, 1.0)  # maximum 100%

        return {
            "ticker": ticker,
            "action": action,
            "position_size": position_size,
            "confidence": confidence,
            "rationale": rationale,
            "entry_price": None,  # Need real-time quotes
            "stop_loss": None,
            "take_profit": None,
            "timestamp": None
        }

    def _parse_recommendation_from_text(self, text: str) -> tuple:
        """
        Parse investment advice from text

        Args:
            text: investment advice text

        Returns:
            (recommendation, confidence) tuple
        """
        text_lower = text.lower()

        # Simple keyword matching
        buy_keywords = ["buy", "Overweight", "long", "Recommended to buy", "buy", "bullish", "bullish"]
        sell_keywords = ["sell", "Reduce holdings", "bearish", "Recommended to sell", "sell", "bearish", "Bearish"]
        hold_keywords = ["hold", "wait and see", "hold", "neutral", "Neutral"]

        buy_score = sum(1 for kw in buy_keywords if kw in text_lower)
        sell_score = sum(1 for kw in sell_keywords if kw in text_lower)
        hold_score = sum(1 for kw in hold_keywords if kw in text_lower)

        # Confirm recommendations
        if buy_score > sell_score and buy_score > hold_score:
            recommendation = "buy"
            confidence = min(0.5 + buy_score * 0.1, 0.9)
        elif sell_score > buy_score and sell_score > hold_score:
            recommendation = "sell"
            confidence = min(0.5 + sell_score * 0.1, 0.9)
        else:
            recommendation = "hold"
            confidence = 0.5

        return recommendation, confidence


# === __init__.py ===
# tradingagents/core/engine/phase_executors/__init__.py
"""
stage executor module

Provides executor implementation for each stage of stock analysis
"""

__all__ = [
    "PhaseExecutor",
    "PhaseContext",
    "DataCollectionPhase",
    "AnalystsPhase",
    "ResearchDebatePhase",
    "TradeDecisionPhase",
    "RiskAssessmentPhase",
]

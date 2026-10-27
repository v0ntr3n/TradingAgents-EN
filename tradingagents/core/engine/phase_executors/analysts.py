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

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import DataLayer, AgentDataContract
from ..agent_integrator import AgentIntegrator
from .base import PhaseExecutor

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

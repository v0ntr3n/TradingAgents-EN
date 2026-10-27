# tradingagents/core/engine/stock_analysis_engine.py
"""
Stock analysis engine

The main engine class coordinates the entire analysis process:
1. data collection → 2. Analyst analysis → 3. research debate → 4. trading decisions → 5. risk assessment

Design principles:
- Agent collaboration based on data contract
- Hierarchical data management (Context → RawData → AnalysisData → Reports → Decisions) 
- Complete data lineage tracing
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from datetime import datetime

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_contract import DataLayer, AgentDataContract
from .data_access_manager import DataAccessManager
from .data_schema import data_schema

logger = get_logger("default")


class AnalysisPhase(str, Enum):
    """Analysis phase enumeration"""
    DATA_COLLECTION = "data_collection"
    ANALYSTS = "analysts"
    RESEARCH_DEBATE = "research_debate"
    TRADE_DECISION = "trade_decision"
    RISK_ASSESSMENT = "risk_assessment"


@dataclass
class PhaseResult:
    """Stage execution results"""
    phase: AnalysisPhase
    success: bool
    duration_seconds: float
    error: Optional[str] = None
    outputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Analyze results"""
    ticker: str
    trade_date: str
    success: bool
    final_decision: Optional[Dict[str, Any]] = None
    phase_results: List[PhaseResult] = field(default_factory=list)
    context: Optional[AnalysisContext] = None
    error: Optional[str] = None
    total_duration_seconds: float = 0.0


class StockAnalysisEngine:
    """
    Stock analysis engine
    
    Coordinate multiple Agents to complete the stock analysis process:
    1. Initialize analysis context
    2. Execute analysis stages in sequence
    3. Collect and return analysis results
    
    Usage:
        engine = StockAnalysisEngine(llm_provider=llm)
        result = engine.analyze(
            ticker="000858.SZ",
            trade_date="2024-01-15",
            company_name="Wuliangye"
        )
    """
    
    def __init__(
        self,
        llm_provider: Any = None,
        selected_analysts: Optional[List[str]] = None,
        enable_data_lineage: bool = True,
        debug_mode: bool = False,
        llm: Any = None,
        toolkit: Any = None,
        use_stub: bool = False,
        memory_enabled: bool = True,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the analysis engine

        Args:
            llm_provider: LLM provider instance
            selected_analysts: Selected analyst list, None means use all
            enable_data_lineage: Whether to enable data lineage tracking
            debug_mode: debug mode
            llm: LLM instance created (for Agent invocation)
            toolkit: Toolset instance (for Agent invocation)
            use_stub: Whether to use stub implementation (for testing)
            memory_enabled: Whether to enable the Memory function
            config: Configuration dictionary (used to create Memory, etc.)
        """
        self.llm_provider = llm_provider
        self.selected_analysts = selected_analysts
        self.enable_data_lineage = enable_data_lineage
        self.debug_mode = debug_mode
        self.llm = llm
        self.toolkit = toolkit
        self.use_stub = use_stub
        self.memory_enabled = memory_enabled
        self.config = config

        # Stage executor (lazy initialization)
        self._phase_executors: Dict[AnalysisPhase, Any] = {}

        # Memory Provider (lazy initialization)
        self._memory_provider = None

        logger.info("📊 [StockAnalysisEngine] Engine initialization completed")
        if memory_enabled:
            logger.info("🧠 [StockAnalysisEngine] Memory Feature is enabled")
            if self.config and not self.config.get("memory_use_mem0_compat", True):
                logger.warning("⚠️ [StockAnalysisEngine] Currently explicitly using legacy-only memory paths")

    def _get_memory_provider(self):
        """Get or create a Memory provider"""
        if self._memory_provider is None:
            from .memory_provider import MemoryProvider
            self._memory_provider = MemoryProvider(
                config=self.config,
                memory_enabled=self.memory_enabled
            )
        return self._memory_provider

    def _get_memory_config(self) -> Dict[str, Any]:
        """Get Memory configuration"""
        return self._get_memory_provider().get_memory_config()
    
    def analyze(
        self,
        ticker: str,
        trade_date: str,
        company_name: Optional[str] = None,
        market_type: str = "cn",
        **kwargs
    ) -> AnalysisResult:
        """
        Perform stock analysis
        
        Args:
            ticker: Stock code, such as "000858.SZ"
            trade_date: Transaction date, such as "2024-01-15"
            company_name: Company name (optional)
            market_type: market type,"cn" or "us"
            **kwargs: Other context parameters
            
        Returns:
            AnalysisResult: Analyze results
        """
        start_time = datetime.now()
        
        logger.info(f"🚀 [StockAnalysisEngine] Start analysis: {ticker} ({trade_date})")
        
        # 1. Create analysis context
        context = self._create_context(
            ticker=ticker,
            trade_date=trade_date,
            company_name=company_name,
            market_type=market_type,
            **kwargs
        )
        
        # 2. Create a data access manager
        data_manager = DataAccessManager(context)
        
        # 3. Prepare results
        result = AnalysisResult(
            ticker=ticker,
            trade_date=trade_date,
            success=True,
            context=context
        )
        
        # 4. Execute stages in order
        phases = [
            AnalysisPhase.DATA_COLLECTION,
            AnalysisPhase.ANALYSTS,
            AnalysisPhase.RESEARCH_DEBATE,
            AnalysisPhase.TRADE_DECISION,
            AnalysisPhase.RISK_ASSESSMENT,
        ]
        
        for phase in phases:
            phase_result = self._execute_phase(phase, context, data_manager)
            result.phase_results.append(phase_result)
            
            if not phase_result.success:
                result.success = False
                result.error = f"stage {phase.value} Execution failed: {phase_result.error}"
                logger.error(f"❌ [StockAnalysisEngine] {result.error}")
                break
        
        # 5. Extract final decision
        if result.success:
            result.final_decision = context.get(DataLayer.DECISIONS, "final_decision")

        # 6. Calculate total time
        end_time = datetime.now()
        result.total_duration_seconds = (end_time - start_time).total_seconds()

        status = "✅" if result.success else "❌"
        logger.info(
            f"{status} [StockAnalysisEngine] Analysis completed: {ticker} "
            f"Time consuming {result.total_duration_seconds:.2f}s"
        )

        return result

    def _create_context(
        self,
        ticker: str,
        trade_date: str,
        company_name: Optional[str] = None,
        market_type: str = "cn",
        **kwargs
    ) -> AnalysisContext:
        """Create analysis context"""
        context = AnalysisContext()

        # Set base context
        context.set(DataLayer.CONTEXT, "ticker", ticker, source="init")
        context.set(DataLayer.CONTEXT, "trade_date", trade_date, source="init")
        context.set(DataLayer.CONTEXT, "market_type", market_type, source="init")

        if company_name:
            context.set(DataLayer.CONTEXT, "company_name", company_name, source="init")

        # Set additional parameters
        for key, value in kwargs.items():
            context.set(DataLayer.CONTEXT, key, value, source="init")

        logger.debug(f"📋 [StockAnalysisEngine] Context creation completed: {context.context}")
        return context

    def _execute_phase(
        self,
        phase: AnalysisPhase,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> PhaseResult:
        """Execute a single stage"""
        start_time = datetime.now()

        logger.info(f"⏳ [StockAnalysisEngine] Execution phase: {phase.value}")

        try:
            # Get stage executor
            executor = self._get_phase_executor(phase)

            if executor is None:
                # Stage executor not implemented, skipped
                logger.warning(f"⚠️ [StockAnalysisEngine] Stage executor is not implemented: {phase.value}")
                return PhaseResult(
                    phase=phase,
                    success=True,
                    duration_seconds=0.0,
                    outputs={"skipped": True}
                )

            # Execution phase
            outputs = executor.execute(context, data_manager)

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(f"✅ [StockAnalysisEngine] stage completed: {phase.value} ({duration:.2f}s)")

            return PhaseResult(
                phase=phase,
                success=True,
                duration_seconds=duration,
                outputs=outputs or {}
            )

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.error(f"❌ [StockAnalysisEngine] stage failed: {phase.value} - {str(e)}")

            return PhaseResult(
                phase=phase,
                success=False,
                duration_seconds=duration,
                error=str(e)
            )

    def _get_phase_executor(self, phase: AnalysisPhase) -> Optional[Any]:
        """Get stage executor"""
        if phase not in self._phase_executors:
            # Delayed import and creation of executors
            self._phase_executors[phase] = self._create_phase_executor(phase)
        return self._phase_executors.get(phase)

    def _create_phase_executor(self, phase: AnalysisPhase) -> Optional[Any]:
        """Create stage executor"""
        from .phase_executors import (
            DataCollectionPhase,
            AnalystsPhase,
            ResearchDebatePhase,
            TradeDecisionPhase,
            RiskAssessmentPhase,
        )

        # Get Memory configuration
        memory_config = self._get_memory_config()

        if phase == AnalysisPhase.DATA_COLLECTION:
            return DataCollectionPhase(
                llm_provider=self.llm_provider
            )

        if phase == AnalysisPhase.ANALYSTS:
            return AnalystsPhase(
                llm_provider=self.llm_provider,
                config={"selected_analysts": self.selected_analysts},
                selected_analysts=self.selected_analysts,
                llm=self.llm,
                toolkit=self.toolkit,
                use_stub=self.use_stub
            )

        if phase == AnalysisPhase.RESEARCH_DEBATE:
            return ResearchDebatePhase(
                llm_provider=self.llm or self.llm_provider,
                debate_rounds=1,
                memory_config=memory_config
            )

        if phase == AnalysisPhase.TRADE_DECISION:
            return TradeDecisionPhase(
                llm_provider=self.llm or self.llm_provider,
                memory_config=memory_config
            )

        if phase == AnalysisPhase.RISK_ASSESSMENT:
            return RiskAssessmentPhase(
                llm_provider=self.llm or self.llm_provider,
                debate_rounds=1,
                memory_config=memory_config
            )

        return None

    def register_phase_executor(self, phase: AnalysisPhase, executor: Any) -> None:
        """
        Register stage executor

        Allow external registration of custom stage executors

        Args:
            phase: analysis stage
            executor: Executor instance (requires execute(context, data_manager) method)
        """
        self._phase_executors[phase] = executor
        logger.debug(f"📋 [StockAnalysisEngine] Register stage executor: {phase.value}")

    def get_context_summary(self, result: AnalysisResult) -> Dict[str, Any]:
        """
        Get analysis context summary

        Args:
            result: Analyze results

        Returns:
            context summary dictionary
        """
        if result.context is None:
            return {}

        return {
            "context": result.context.context,
            "reports": list(result.context.reports.keys()),
            "decisions": list(result.context.decisions.keys()),
            "lineage_count": len(result.context.data_lineage),
        }


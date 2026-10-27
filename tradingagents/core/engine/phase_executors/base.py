# tradingagents/core/engine/phase_executors/base.py
"""
stage executor base class

Define standard interfaces and common functions for phase execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import AgentDataContract, DataLayer

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


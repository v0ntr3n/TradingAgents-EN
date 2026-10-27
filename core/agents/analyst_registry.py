"""
Analyst Registration Form

Specializes in managing analyst-type Agents and provides functions related to workflow construction

Extended functions:
- Support data contract registration and verification
- Automatically register Agent output fields to the data dictionary
"""

from typing import Dict, List, Optional, Type, Callable, Any
from .base import BaseAgent
from .config import AgentCategory, AgentMetadata, BUILTIN_AGENTS
from .registry import AgentRegistry, get_registry

# Data contract related import
from tradingagents.core.engine.data_contract import AgentDataContract
from tradingagents.core.engine.data_schema import data_schema
from tradingagents.core.engine.contract_validator import ContractValidator

# Import logs
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class AnalystRegistry:
    """
    Analyst Registration Form
    
    Extend AgentRegistry to specifically manage analyst type Agents,
    Provides functions related to workflow construction and report aggregation
    
    Usage:
        registry = AnalystRegistry()
        
        # Certified Analyst
        registry.register("sector", SectorAnalystAgent, metadata)
        
        # Get all analysts (in order of execution)
        analysts = registry.get_analysts_ordered()
        
        # Get analyst metadata
        meta = registry.get_analyst_metadata("sector")
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AnalystRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._analysts: Dict[str, Type[BaseAgent]] = {}
            self._analyst_factories: Dict[str, Callable] = {}  # Factory function
            self._analyst_metadata: Dict[str, AgentMetadata] = {}
            self._contracts: Dict[str, AgentDataContract] = {}  # data contract
            self._contract_validator = ContractValidator()  # contract validator
            self._load_builtin_analysts()
            self._initialized = True
    
    def _load_builtin_analysts(self) -> None:
        """Load built-in analyst metadata"""
        for agent_id, metadata in BUILTIN_AGENTS.items():
            if metadata.category == AgentCategory.ANALYST:
                self._analyst_metadata[agent_id] = metadata
    
    def register(
        self,
        analyst_id: str,
        agent_class: Optional[Type[BaseAgent]] = None,
        factory: Optional[Callable] = None,
        metadata: Optional[AgentMetadata] = None,
        contract: Optional[AgentDataContract] = None,
        override: bool = False
    ) -> None:
        """
        Certified Analyst

        Args:
            analyst_id: Analyst ID, such as "sector"
            agent_class: Agent class (optional)
            factory: Factory function (optional), used to create Agent instances
            metadata: Metadata (optional, if not provided built-in metadata will be used)
            contract: Data contract (optional), defining input and output fields
            override: Whether to overwrite existing registrations
        """
        if analyst_id in self._analysts and not override:
            raise ValueError(f"analyst '{analyst_id}' Registered, using override=True Cover")

        if agent_class:
            self._analysts[analyst_id] = agent_class
        if factory:
            self._analyst_factories[analyst_id] = factory
        if metadata:
            self._analyst_metadata[analyst_id] = metadata

        # Registration Data Contract
        if contract:
            self._register_contract(analyst_id, contract)

        logger.debug(f"📋 [AnalystRegistry] Certified Analyst: {analyst_id}")

    def _register_contract(self, analyst_id: str, contract: AgentDataContract) -> None:
        """
        Registration Data Contract

        1. Verify the legality of the contract
        2. Register output fields to the data dictionary
        3. Save contract to registry

        Args:
            analyst_id: analyst ID
            contract: data contract
        """
        # Verify contract
        result = self._contract_validator.validate_contract(contract)
        if not result.is_valid:
            error_msgs = [e.message for e in result.errors]
            raise ValueError(f"Contract verification failed [{analyst_id}]: {error_msgs}")

        # Register output fields to the data dictionary
        data_schema.register_agent_fields(analyst_id, contract.outputs)

        # preservation deed
        self._contracts[analyst_id] = contract
        self._contract_validator.register_contract(contract)

        logger.debug(f"📋 [AnalystRegistry] registration deed: {analyst_id}")
    
    def get_analyst_class(self, analyst_id: str) -> Optional[Type[BaseAgent]]:
        """Get analyst class"""
        return self._analysts.get(analyst_id)
    
    def get_analyst_factory(self, analyst_id: str) -> Optional[Callable]:
        """Get analyst factory function"""
        return self._analyst_factories.get(analyst_id)
    
    def get_analyst_metadata(self, analyst_id: str) -> Optional[AgentMetadata]:
        """Get analyst metadata"""
        return self._analyst_metadata.get(analyst_id)
    
    def get_analysts_ordered(self, selected: Optional[List[str]] = None) -> List[AgentMetadata]:
        """
        Get a list of analysts (sorted by execution_order)
        
        Args:
            selected: Specified list of analyst IDs, if None returns all
            
        Returns:
            Analyst metadata list in order of execution
        """
        analysts = []
        for analyst_id, metadata in self._analyst_metadata.items():
            if selected is None or analyst_id in selected:
                # Make sure to only include analysts with registered implementations, or built-in analysts
                if analyst_id in self._analysts or analyst_id in self._analyst_factories:
                    analysts.append(metadata)
                elif metadata.category == AgentCategory.ANALYST:
                    # Built-in but unregistered implementations of analysts are also included (handled by the original setup.py)
                    analysts.append(metadata)
        
        # Sort by execution_order
        return sorted(analysts, key=lambda m: m.execution_order)
    
    def get_output_fields(self, selected: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Get output field mappings for all analysts
        
        Args:
            selected: List of specified analyst IDs
            
        Returns:
            {analyst_id: output_field} mapping
        """
        result = {}
        for analyst_id, metadata in self._analyst_metadata.items():
            if selected is None or analyst_id in selected:
                if metadata.output_field:
                    result[analyst_id] = metadata.output_field
        return result
    
    def is_registered(self, analyst_id: str) -> bool:
        """Check if the analyst has registered the implementation"""
        return analyst_id in self._analysts or analyst_id in self._analyst_factories

    def list_all(self) -> List[str]:
        """List all known analysts ID"""
        return list(self._analyst_metadata.keys())

    # =========================================
    # Contract related methods
    # =========================================

    def get_contract(self, analyst_id: str) -> Optional[AgentDataContract]:
        """Get an analyst s data contract"""
        return self._contracts.get(analyst_id)

    def get_all_contracts(self) -> Dict[str, AgentDataContract]:
        """Get all registered deeds"""
        return self._contracts.copy()

    def has_contract(self, analyst_id: str) -> bool:
        """Check if analyst has data contract"""
        return analyst_id in self._contracts

    def validate_all_contracts(self) -> Dict[str, Any]:
        """
        Verify dependencies of all registered contracts

        Returns:
            Verify result dictionary {analyst_id: ValidationResult}
        """
        contracts = list(self._contracts.values())
        return self._contract_validator.validate_all_contracts(contracts)


# global instance
_analyst_registry: Optional[AnalystRegistry] = None


def get_analyst_registry() -> AnalystRegistry:
    """Get global analyst registry instance"""
    global _analyst_registry
    if _analyst_registry is None:
        _analyst_registry = AnalystRegistry()
    return _analyst_registry


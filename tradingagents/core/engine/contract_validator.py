# tradingagents/core/engine/contract_validator.py
"""
contract validator

Verify the legality of the Agent data contract, including:
- Whether the input field exists in the data dictionary
- Whether the output field conflicts with the core field
- Is the dependency relationship reasonable?
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from tradingagents.core.engine.data_contract import AgentDataContract, DataLayer
from tradingagents.core.engine.data_schema import DynamicDataSchema, data_schema


@dataclass
class ValidationError:
    """Validation error"""
    agent_id: str
    error_type: str  # 'invalid_input', 'core_conflict', 'missing_dependency'
    message: str
    field_name: Optional[str] = None
    layer: Optional[DataLayer] = None


@dataclass
class ValidationResult:
    """Verification results"""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, error: ValidationError):
        """add error"""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        """add warning"""
        self.warnings.append(warning)


class ContractValidator:
    """
    Data Contract Validator
    
    Verify the legality of the Agent contract to ensure:
    1. The input field must exist in the data dictionary
    2. Output fields cannot cover core fields
    3. The dependent Agent must exist (optional check)
    """
    
    def __init__(self, schema: DynamicDataSchema = None):
        """
        Initialize validator
        
        Args:
            schema: Data dictionary instance, using global singleton by default
        """
        self.schema = schema or data_schema
        self._registered_agents: Dict[str, AgentDataContract] = {}
    
    def register_contract(self, contract: AgentDataContract) -> None:
        """
        Register contract (for dependency checking)
        
        Args:
            contract: Agent data contract
        """
        self._registered_agents[contract.agent_id] = contract
    
    def validate_contract(
        self, 
        contract: AgentDataContract,
        check_dependencies: bool = False,
        strict_input_check: bool = False
    ) -> ValidationResult:
        """
        Verify the legality of a single Agent contract
        
        Args:
            contract: Contract to be verified
            check_dependencies: Whether to check whether the dependent Agent has been registered
            strict_input_check: Whether to strictly check input fields (fields must pre-exist)
            
        Returns:
            ValidationResult Verification results
        """
        result = ValidationResult(is_valid=True)
        
        # 1. Validate input fields
        if strict_input_check:
            self._validate_inputs(contract, result)
        
        # 2. Verify that output fields do not conflict with core fields
        self._validate_outputs(contract, result)
        
        # 3. Verify dependencies
        if check_dependencies:
            self._validate_dependencies(contract, result)
        
        return result
    
    def _validate_inputs(self, contract: AgentDataContract, result: ValidationResult) -> None:
        """Validate input fields"""
        for access in contract.inputs:
            # If fields is empty, it means that the entire layer is accessed and no specific fields need to be verified.
            if not access.fields:
                continue
            
            for field_name in access.fields:
                if not self.schema.is_valid_field(access.layer, field_name):
                    result.add_error(ValidationError(
                        agent_id=contract.agent_id,
                        error_type="invalid_input",
                        message=f"Invalid input field: {access.layer.value}.{field_name}",
                        field_name=field_name,
                        layer=access.layer
                    ))
    
    def _validate_outputs(self, contract: AgentDataContract, result: ValidationResult) -> None:
        """
        Validate output fields

        Rules:
        - DECISIONS The layer s core fields allow writing (these are the predefined decision output locations)
        - Core fields of other layers are not allowed to be overwritten (such as the ticker of the CONTEXT layer)
        """
        from tradingagents.core.engine.data_contract import DataLayer

        for access in contract.outputs:
            for field_name in access.fields:
                if self.schema.is_core_field(access.layer, field_name):
                    # DECISIONS The layer's core fields allow writing
                    if access.layer == DataLayer.DECISIONS:
                        continue

                    # Core fields of other layers are not allowed to be overwritten.
                    result.add_error(ValidationError(
                        agent_id=contract.agent_id,
                        error_type="core_conflict",
                        message=f"Cannot override core fields: {access.layer.value}.{field_name}",
                        field_name=field_name,
                        layer=access.layer
                    ))
    
    def _validate_dependencies(self, contract: AgentDataContract, result: ValidationResult) -> None:
        """Verify whether the dependent Agent has been registered"""
        for dep_id in contract.depends_on:
            if dep_id not in self._registered_agents:
                result.add_error(ValidationError(
                    agent_id=contract.agent_id,
                    error_type="missing_dependency",
                    message=f"The dependent Agent is not registered: {dep_id}"
                ))
    
    def validate_all_contracts(
        self, 
        contracts: List[AgentDataContract],
        check_dependencies: bool = True
    ) -> Dict[str, ValidationResult]:
        """
        Verify multiple Agent contracts
        
        Args:
            contracts: contract list
            check_dependencies: Whether to check dependencies
            
        Returns:
            agent_id -> ValidationResult dictionary
        """
        # Register all deeds first
        for contract in contracts:
            self.register_contract(contract)
        
        # Verify one by one
        results = {}
        for contract in contracts:
            results[contract.agent_id] = self.validate_contract(
                contract, 
                check_dependencies=check_dependencies
            )
        
        return results


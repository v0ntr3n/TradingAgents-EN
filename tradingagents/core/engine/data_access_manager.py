# tradingagents/core/engine/data_access_manager.py
"""
Data Access Manager

Provide contract-based data access control, including:
- Permission verification: Verify read and write permissions according to the contract
- Data reading: aggregating input data by contract
- Data writing: write output data according to contract and record bloodline
- Access log: records all data access operations
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

from tradingagents.core.engine.data_contract import AgentDataContract, DataAccess, DataLayer
from tradingagents.core.engine.analysis_context import AnalysisContext


@dataclass
class AccessLogEntry:
    """access log entries"""
    agent_id: str
    layer: str
    fields: List[str]
    action: str  # 'read' or 'write'
    timestamp: str
    success: bool = True
    error: Optional[str] = None


class DataAccessManager:
    """
    Data access rights manager
    
    Control data access based on Agent contract:
    - Verify input permissions when reading and aggregate the data declared by the contract
    - Verify output permissions when writing and record data lineage
    - Logs of all access operations
    
    Attributes:
        context: Analyze context
        access_log: Access log list
    """
    
    def __init__(self, context: AnalysisContext):
        """
        Initialize the data access manager
        
        Args:
            context: Analysis context instance
        """
        self.context = context
        self.access_log: List[AccessLogEntry] = []
    
    def get_data(self, agent_id: str, contract: AgentDataContract) -> Dict[str, Any]:
        """
        Get the input data of the Agent according to the contract
        
        Aggregate data by input layers and fields declared by the contract:
        - When fields are specified, only these fields are returned
        - fields Returns all data in the entire layer when empty
        
        Args:
            agent_id: Agent logo
            contract: Agent data contract
            
        Returns:
            Aggregated input data dictionary
            
        Raises:
            PermissionError: If data not declared in the contract is accessed
        """
        data = {}
        
        for access in contract.inputs:
            layer_data = self.context.get_layer(access.layer)
            
            if access.fields:
                # Get the specified field
                for field_name in access.fields:
                    if field_name in layer_data:
                        data[field_name] = layer_data[field_name]
                    elif access.required:
                        # You can choose to report an error or return when the required field does not exist None
                        data[field_name] = None
            else:
                # Get the entire layer of data
                data.update(layer_data)
            
            # Record access log
            self._log_access(agent_id, access.layer, access.fields or list(layer_data.keys()), "read")
        
        return data
    
    def set_data(
        self, 
        agent_id: str, 
        contract: AgentDataContract, 
        outputs: Dict[str, Any]
    ) -> None:
        """
        Write the data produced by the Agent according to the contract
        
        Write data according to the output layer and fields declared in the contract, and record the data lineage.
        
        Args:
            agent_id: Agent logo
            contract: Agent data contract
            outputs: Dictionary of output data to write
            
        Raises:
            PermissionError: If a field not declared in the contract is written
        """
        for access in contract.outputs:
            for field_name in access.fields:
                if field_name in outputs:
                    # Write data and record lineage
                    self.context.set(access.layer, field_name, outputs[field_name], agent_id)
                    self._log_access(agent_id, access.layer, [field_name], "write")
    
    def _log_access(
        self, 
        agent_id: str, 
        layer: DataLayer, 
        fields: List[str], 
        action: str,
        success: bool = True,
        error: str = None
    ) -> None:
        """Record data access logs"""
        entry = AccessLogEntry(
            agent_id=agent_id,
            layer=layer.value,
            fields=fields,
            action=action,
            timestamp=datetime.now().isoformat(),
            success=success,
            error=error
        )
        self.access_log.append(entry)
    
    def get_access_log(self, agent_id: str = None) -> List[AccessLogEntry]:
        """
        Get access log
        
        Args:
            agent_id: Optional, filter the logs of the specified Agent
            
        Returns:
            Access log list
        """
        if agent_id:
            return [log for log in self.access_log if log.agent_id == agent_id]
        return self.access_log.copy()
    
    def get_data_lineage(self, layer: DataLayer = None, field_name: str = None) -> Dict[str, str]:
        """
        Get data lineage information

        Args:
            layer: Optional, filter the specified layer
            field_name: Optional, filter specified fields

        Returns:
            field path -> Source Agent s dictionary
        """
        lineage = self.context.data_lineage.copy()

        if layer:
            prefix = f"{layer.value}."
            lineage = {k: v for k, v in lineage.items() if k.startswith(prefix)}

        if field_name:
            lineage = {k: v for k, v in lineage.items() if k.endswith(f".{field_name}")}

        return lineage

    def validate_access(self, agent_id: str, contract: AgentDataContract,
                       layer: DataLayer, field_name: str, action: str) -> bool:
        """
        Verify that the Agent has access to the specified field

        Args:
            agent_id: Agent logo
            contract: Agent data contract
            layer: data layer
            field_name: Field name
            action: 'read' or 'write'

        Returns:
            Do you have permission?
        """
        if action == "read":
            return contract.has_input_access(layer, field_name)
        elif action == "write":
            return contract.has_output_access(layer, field_name)
        return False

    def get_all_reports(self) -> Dict[str, str]:
        """
        Get all reports (convenient method)

        Returns:
            report name -> Dictionary of report contents
        """
        return self.context.get_layer(DataLayer.REPORTS)

    def get_context_info(self) -> Dict[str, Any]:
        """
        Get basic context information (convenient method)

        Returns:
            contains ticker, trade_date Dictionary of basic information
        """
        return self.context.get_layer(DataLayer.CONTEXT)

    def clear_access_log(self) -> None:
        """Clear access log"""
        self.access_log.clear()

    def get_access_summary(self) -> Dict[str, Any]:
        """
        Get access statistics summary

        Returns:
            Contains statistical information such as read and write times, Agent activities, etc.
        """
        read_count = sum(1 for log in self.access_log if log.action == "read")
        write_count = sum(1 for log in self.access_log if log.action == "write")

        agents = set(log.agent_id for log in self.access_log)
        layers_accessed = set(log.layer for log in self.access_log)

        return {
            "total_operations": len(self.access_log),
            "read_count": read_count,
            "write_count": write_count,
            "unique_agents": len(agents),
            "agents": list(agents),
            "layers_accessed": list(layers_accessed),
        }


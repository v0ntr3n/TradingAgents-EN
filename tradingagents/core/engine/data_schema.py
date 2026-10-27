# tradingagents/core/engine/data_schema.py
"""
dynamic data dictionary

Manages all legal data field definitions and supports three field sources:
1. Core fields - code hardcoded, system required
2. Agent Field - automatically added when Agent registers
3. Extension fields - YAML configuration file definition
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Any, Optional, List
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from tradingagents.core.engine.data_contract import DataLayer


@dataclass
class FieldDefinition:
    """
    Field definition
    
    Attributes:
        name: Field name
        field_type: field type (string, object, array, number, boolean, any) 
        required: Is it required?
        default: Default value
        description: Field description
        source: Data source (Agent ID or 'core' or 'config') 
    """
    name: str
    field_type: str = "any"
    required: bool = False
    default: Any = None
    description: str = ""
    source: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "type": self.field_type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "source": self.source,
        }


class DynamicDataSchema:
    """
    dynamic data dictionary
    
    Three field sources are supported:
    1. Core fields - code hardcoded, system required
    2. Agent Field - automatically added when Agent registers
    3. Extension fields - YAML configuration file definition
    
    Use singleton mode to ensure that there is only one data dictionary instance globally.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 1️⃣ Core fields (hardcoded, system required)
        self._core_fields: Dict[DataLayer, Dict[str, FieldDefinition]] = self._init_core_fields()
        
        # 2️⃣ Agent Dynamic fields (added when Agent registers)
        self._agent_fields: Dict[DataLayer, Dict[str, FieldDefinition]] = {
            layer: {} for layer in DataLayer
        }
        
        # 3️⃣ Extension fields (loaded from YAML)
        self._extend_fields: Dict[DataLayer, Dict[str, FieldDefinition]] = {
            layer: {} for layer in DataLayer
        }
        
        # Load YAML configuration
        self._load_extend_schema()
    
    def _init_core_fields(self) -> Dict[DataLayer, Dict[str, FieldDefinition]]:
        """Initialize core fields (hardcoded)"""
        return {
            DataLayer.CONTEXT: {
                "ticker": FieldDefinition(
                    name="ticker",
                    field_type="string",
                    required=True,
                    description="Stock code, such as 000858.SZ",
                    source="core"
                ),
                "trade_date": FieldDefinition(
                    name="trade_date",
                    field_type="string",
                    required=True,
                    description="parse date, format YYYY-MM-DD",
                    source="core"
                ),
                "market_type": FieldDefinition(
                    name="market_type",
                    field_type="string",
                    default="A_SHARE",
                    description="market type: A_SHARE, HK, US",
                    source="core"
                ),
                "company_name": FieldDefinition(
                    name="company_name",
                    field_type="string",
                    default="",
                    description="Company name",
                    source="core"
                ),
                "currency": FieldDefinition(
                    name="currency",
                    field_type="string",
                    default="CNY",
                    description="currency code: CNY, HKD, USD",
                    source="core"
                ),
            },
            DataLayer.RAW_DATA: {},
            DataLayer.ANALYSIS_DATA: {},
            DataLayer.REPORTS: {},
            DataLayer.DECISIONS: {
                "investment_debate": FieldDefinition(
                    name="investment_debate",
                    field_type="object",
                    description="Investment Debate History",
                    source="core"
                ),
                "investment_plan": FieldDefinition(
                    name="investment_plan",
                    field_type="string",
                    description="investment plan",
                    source="core"
                ),
                "trade_signal": FieldDefinition(
                    name="trade_signal",
                    field_type="object",
                    description="trading signals",
                    source="core"
                ),
                "risk_assessment": FieldDefinition(
                    name="risk_assessment",
                    field_type="object",
                    description="risk assessment",
                    source="core"
                ),
                "final_decision": FieldDefinition(
                    name="final_decision",
                    field_type="string",
                    description="Final analysis results",
                    source="core"
                ),
            },
        }

    def _load_extend_schema(self, config_path: str = None):
        """
        Load extension fields from YAML configuration file

        Args:
            config_path: Configuration file path, default is config/data_schema.yaml
        """
        if config_path is None:
            # Try multiple possible paths
            possible_paths = [
                Path("config/data_schema.yaml"),
                Path(__file__).parent.parent.parent.parent / "config" / "data_schema.yaml",
            ]
            for p in possible_paths:
                if p.exists():
                    config_path = str(p)
                    break

        if not config_path:
            return

        path = Path(config_path)
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception:
            return

        if not config or "layers" not in config:
            return

        for layer_name, layer_config in config["layers"].items():
            try:
                layer = DataLayer(layer_name)
            except ValueError:
                continue

            fields = layer_config.get("fields", {})
            for field_name, field_config in fields.items():
                # Skip core fields (overrides not allowed)
                if field_name in self._core_fields.get(layer, {}):
                    continue

                self._extend_fields[layer][field_name] = FieldDefinition(
                    name=field_name,
                    field_type=field_config.get("type", "any"),
                    required=field_config.get("required", False),
                    default=field_config.get("default"),
                    description=field_config.get("description", ""),
                    source=field_config.get("source", "config"),
                )

    def register_agent_fields(self, agent_id: str, outputs: List) -> None:
        """
        Agent When registering, automatically add its output fields to the data dictionary

        Args:
            agent_id: Agent logo
            outputs: Agent list of output declarations [DataAccess, ...]
        """
        for access in outputs:
            for field_name in access.fields:
                # Skip core fields
                if field_name in self._core_fields.get(access.layer, {}):
                    continue

                self._agent_fields[access.layer][field_name] = FieldDefinition(
                    name=field_name,
                    field_type="dynamic",
                    source=agent_id,
                    description=f"by {agent_id} output"
                )

    def get_all_fields(self, layer: DataLayer) -> Dict[str, FieldDefinition]:
        """
        Get all fields of a certain layer (merging three sources)

        Priority: core fields > Agent Field > extension fields

        Args:
            layer: data layer

        Returns:
            Field name -> FieldDefinition dictionary
        """
        result = {}

        # Load extension fields first (lowest priority)
        result.update(self._extend_fields.get(layer, {}))

        # Reload the Agent field
        result.update(self._agent_fields.get(layer, {}))

        # Load core fields last (highest priority)
        result.update(self._core_fields.get(layer, {}))

        return result

    def get_field_names(self, layer: DataLayer) -> Set[str]:
        """Get all field names of a certain layer"""
        return set(self.get_all_fields(layer).keys())

    def is_valid_field(self, layer: DataLayer, field_name: str) -> bool:
        """Check if the field is legal"""
        return field_name in self.get_field_names(layer)

    def get_field_info(self, layer: DataLayer, field_name: str) -> Optional[FieldDefinition]:
        """Get field details"""
        return self.get_all_fields(layer).get(field_name)

    def get_fields_by_source(self, source: str) -> Dict[DataLayer, List[str]]:
        """
        Get all fields output by a source

        Args:
            source: Data source (Agent ID or 'core' or 'config') 

        Returns:
            data layer -> A dictionary of field name lists
        """
        result = {}
        for layer in DataLayer:
            fields = []
            for field_name, field_def in self.get_all_fields(layer).items():
                if field_def.source == source:
                    fields.append(field_name)
            if fields:
                result[layer] = fields
        return result

    def is_core_field(self, layer: DataLayer, field_name: str) -> bool:
        """Check if it is a core field"""
        return field_name in self._core_fields.get(layer, {})

    def reset_agent_fields(self) -> None:
        """Reset all Agent dynamic fields (for testing)"""
        self._agent_fields = {layer: {} for layer in DataLayer}

    def reload_extend_schema(self, config_path: str = None) -> None:
        """Reload extension field configuration"""
        self._extend_fields = {layer: {} for layer in DataLayer}
        self._load_extend_schema(config_path)


# Global singleton
data_schema = DynamicDataSchema()


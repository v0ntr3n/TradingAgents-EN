"""
agent API

Provide query and management interface for intelligent agents
"""

from typing import Any, Dict, List, Optional

from ..agents import (
    AgentRegistry,
    AgentFactory,
    AgentMetadata,
    AgentCategory,
    AgentMaintenanceStatus,
    LicenseTier,
    get_registry,
)
from ..licensing import LicenseManager


class AgentAPI:
    """
    agent API
    
    Provide query, filtering and metadata acquisition functions for intelligent agents
    """
    
    def __init__(self):
        self._registry = get_registry()
        self._factory = AgentFactory(self._registry)
        self._license_manager = LicenseManager()
    
    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all agents
        
        Returns:
            Agent metadata list
        """
        agents = []
        for metadata in self._registry.list_all():
            agents.append(self._metadata_to_dict(metadata))
        return agents
    
    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        List agents by category
        
        Args:
            category: Category name (analyst/researcher/trader/risk/manager)
            
        Returns:
            Agent metadata list
        """
        try:
            cat = AgentCategory(category)
        except ValueError:
            return []
        
        agents = []
        for metadata in self._registry.list_by_category(cat):
            agents.append(self._metadata_to_dict(metadata))
        return agents
    
    def list_available(self) -> List[Dict[str, Any]]:
        """
        List agents available with current license (using local license)

        Returns:
            List of available agent metadata
        """
        current_tier = self._license_manager.tier
        return self.list_available_for_tier(current_tier.value if hasattr(current_tier, 'value') else current_tier)

    def list_available_for_tier(self, tier_str: str) -> List[Dict[str, Any]]:
        """
        Lists the agents under maintenance that are visible under the specified license level

        Args:
            tier_str: license level string ("free", "basic", "pro", "enterprise")

        Returns:
            List of agent metadata being maintained, including availability flags
        """
        # Convert to LicenseTier
        try:
            tier = LicenseTier(tier_str)
        except ValueError:
            tier = LicenseTier.FREE

        tier_order = ["free", "basic", "pro", "enterprise"]
        current_tier_str = tier.value if hasattr(tier, 'value') else tier
        current_index = tier_order.index(current_tier_str)

        agents = []
        all_agents = self._registry.list_all()

        for metadata in all_agents:
            if self._resolve_maintenance_status(metadata) != AgentMaintenanceStatus.MAINTAINED.value:
                continue

            agent_dict = self._metadata_to_dict(metadata)

            tier_value = metadata.license_tier.value if hasattr(metadata.license_tier, 'value') else metadata.license_tier
            required_index = tier_order.index(tier_value)
            agent_dict["is_available"] = current_index >= required_index

            if not agent_dict["is_available"]:
                tier_labels = {
                    "free": "free",
                    "basic": "Basics",
                    "pro": "Advanced",
                    "enterprise": "enterprise"
                }
                tier_label = tier_labels.get(tier_value, tier_value)
                agent_dict["locked_reason"] = f"need{tier_label}Student permissions"

            agents.append(agent_dict)

        return agents
    
    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get agent details
        
        Args:
            agent_id: agent ID
            
        Returns:
            Agent metadata, returned if it does not exist None
        """
        metadata = self._registry.get_metadata(agent_id)
        if metadata is None:
            return None
        
        agent_dict = self._metadata_to_dict(metadata)
        
        # Add availability information
        current_tier = self._license_manager.tier
        tier_order = [LicenseTier.FREE, LicenseTier.BASIC, LicenseTier.PRO, LicenseTier.ENTERPRISE]
        current_index = tier_order.index(current_tier)
        required_index = tier_order.index(metadata.license_tier)
        
        agent_dict["is_available"] = current_index >= required_index
        agent_dict["is_implemented"] = self._registry.is_registered(agent_id)
        
        return agent_dict
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """
        Get all categories
        
        Returns:
            Category list
        """
        categories = []
        for cat in AgentCategory:
            count = sum(
                1
                for metadata in self._registry.list_by_category(cat)
                if self._resolve_maintenance_status(metadata) == AgentMaintenanceStatus.MAINTAINED.value
            )
            categories.append({
                "id": cat.value,
                "name": self._get_category_name(cat),
                "count": count,
            })
        return categories
    
    def _metadata_to_dict(self, metadata: AgentMetadata) -> Dict[str, Any]:
        """Convert metadata to dictionary"""
        # Processing enumeration values: may be an enumeration type or a string (use_enum_values=True) 
        category = metadata.category.value if hasattr(metadata.category, 'value') else metadata.category
        license_tier = metadata.license_tier.value if hasattr(metadata.license_tier, 'value') else metadata.license_tier
        maintenance_status = self._resolve_maintenance_status(metadata)

        return {
            "id": metadata.id,
            "name": metadata.name,
            "description": metadata.description,
            "category": category,
            "version": metadata.version,
            "license_tier": license_tier,
            "maintenance_status": maintenance_status,
            "inputs": metadata.inputs,
            "outputs": metadata.outputs,
            "icon": metadata.icon,
            "color": metadata.color,
            "tags": metadata.tags,
            "tools": metadata.tools,
            "default_tools": metadata.default_tools,
            "max_tool_calls": metadata.max_tool_calls,
        }

    def _resolve_maintenance_status(self, metadata: AgentMetadata) -> str:
        """Unified calculation of Agent maintenance status."""
        raw_status = getattr(metadata, "maintenance_status", None)
        if raw_status:
            status_value = raw_status.value if hasattr(raw_status, 'value') else str(raw_status)
            if status_value == AgentMaintenanceStatus.UNMAINTAINED.value:
                return status_value

        version = str(getattr(metadata, "version", "") or "").strip().lower()
        if version.startswith("1") or version.startswith("v1"):
            return AgentMaintenanceStatus.UNMAINTAINED.value

        return AgentMaintenanceStatus.MAINTAINED.value
    
    def _get_category_name(self, category: AgentCategory) -> str:
        """Get the Chinese name of the category"""
        names = {
            AgentCategory.ANALYST: "analyst",
            AgentCategory.RESEARCHER: "researcher",
            AgentCategory.TRADER: "research integrator",
            AgentCategory.RISK: "risk management",
            AgentCategory.MANAGER: "manager",
            AgentCategory.POST_PROCESSOR: "post processor",
        }
        return names.get(category, category.value)


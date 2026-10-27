"""
Test Agent plug-in architecture

Verify functionality of AnalystRegistry and ReportAggregator
"""

import pytest


class TestAnalystRegistry:
    """Test Analyst Registration Form"""
    
    def test_registry_singleton(self):
        """Test the registration form singleton pattern"""
        from core.agents.analyst_registry import get_analyst_registry
        
        registry1 = get_analyst_registry()
        registry2 = get_analyst_registry()
        
        assert registry1 is registry2
    
    def test_builtin_analysts_loaded(self):
        """Test built-in analyst metadata loaded"""
        from core.agents.analyst_registry import get_analyst_registry
        
        registry = get_analyst_registry()
        
        # Check the built-in analysts
        assert "market_analyst" in registry.list_all()
        assert "news_analyst" in registry.list_all()
        assert "social_analyst" in registry.list_all()
        assert "fundamentals_analyst" in registry.list_all()
        assert "sector_analyst" in registry.list_all()
        assert "index_analyst" in registry.list_all()
    
    def test_extension_analysts_registered(self):
        """Test Extension Analyst Registered"""
        # Trigger module loading (this automatically registers extension analysts)
        from core.agents.adapters import SectorAnalystAgent, IndexAnalystAgent
        from core.agents.analyst_registry import get_analyst_registry
        
        registry = get_analyst_registry()
        
        # Check if the extension analyst has registered the implementation
        assert registry.is_registered("sector_analyst")
        assert registry.is_registered("index_analyst")
    
    def test_get_analyst_metadata(self):
        """Test getting analyst metadata"""
        from core.agents.analyst_registry import get_analyst_registry
        
        registry = get_analyst_registry()
        
        # Get sector analyst metadata
        sector_meta = registry.get_analyst_metadata("sector_analyst")
        assert sector_meta is not None
        assert sector_meta.output_field == "sector_report"
        assert sector_meta.requires_tools == False
        
        # Get broad market analyst metadata
        index_meta = registry.get_analyst_metadata("index_analyst")
        assert index_meta is not None
        assert index_meta.output_field == "index_report"
        assert index_meta.requires_tools == False
    
    def test_get_output_fields(self):
        """Test to get all output fields"""
        from core.agents.analyst_registry import get_analyst_registry
        
        registry = get_analyst_registry()
        
        output_fields = registry.get_output_fields()
        
        # Check output field mapping
        assert "sector_analyst" in output_fields
        assert output_fields["sector_analyst"] == "sector_report"
        assert "index_analyst" in output_fields
        assert output_fields["index_analyst"] == "index_report"


class TestReportAggregator:
    """Test report aggregator"""
    
    def test_aggregate_reports(self):
        """Test aggregation reporting"""
        from core.utils.report_aggregator import get_all_reports
        
        # Simulation state
        state = {
            "market_report": "Market analysis report content",
            "sentiment_report": "Sentiment analysis report content",
            "news_report": "News analysis report content",
            "fundamentals_report": "Fundamental analysis report content",
            "sector_report": "Sector analysis report content",
            "index_report": "Market analysis report content",
        }
        
        reports = get_all_reports(state)
        
        # Number of inspection reports
        assert len(reports) == 6
        
        # Check report content
        assert reports.get("sector_report") == "Sector analysis report content"
        assert reports.get("index_report") == "Market analysis report content"
    
    def test_to_text(self):
        """test convert to text"""
        from core.utils.report_aggregator import get_all_reports
        
        state = {
            "index_report": "Market report",
            "sector_report": "Sector report",
            "market_report": "market report",
        }
        
        reports = get_all_reports(state)
        text = reports.to_text()
        
        # Check text contains all reports
        assert "Market report" in text
        assert "Sector report" in text
        assert "market report" in text
    
    def test_empty_reports(self):
        """Test empty report handling"""
        from core.utils.report_aggregator import get_all_reports
        
        state = {}
        
        reports = get_all_reports(state)
        
        # Empty status should return an empty report
        assert len(reports) == 0
        assert reports.to_text() == ""


class TestPluginArchitectureIntegration:
    """Test plug-in architecture integration"""
    
    def test_extension_analyst_in_workflow(self):
        """Test extension analysts can be loaded by workflows"""
        # Trigger module loading
        from core.agents.adapters import SectorAnalystAgent, IndexAnalystAgent
        from core.agents.analyst_registry import get_analyst_registry
        
        registry = get_analyst_registry()
        
        # Get sector analyst class
        sector_class = registry.get_analyst_class("sector_analyst")
        assert sector_class is SectorAnalystAgent
        
        # Get the broad market analyst category
        index_class = registry.get_analyst_class("index_analyst")
        assert index_class is IndexAnalystAgent


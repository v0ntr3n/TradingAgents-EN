"""
Market/Index Analyst Unit Test
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import pandas as pd


class TestIndexTools:
    """Test Exponential Analysis Tool Function"""
    
    @pytest.fixture
    def mock_tushare_provider(self):
        """Emulate Tushare provider"""
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        return mock_provider
    
    @pytest.mark.asyncio
    async def test_get_index_trend(self, mock_tushare_provider):
        """Test index trend analysis"""
        # Simulate index daily data
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': [f'202412{i:02d}' for i in range(1, 22)],
            'close': [3000 + i * 10 for i in range(21)],
            'high': [3010 + i * 10 for i in range(21)],
            'low': [2990 + i * 10 for i in range(21)],
            'pct_chg': [0.5] * 21
        }))
        
        with patch('core.tools.index_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.index_tools import get_index_trend
            
            result = await get_index_trend("2024-12-21")
            
            assert "Major index trend analysis" in result
            assert "Shanghai Composite Index" in result or "No data yet" in result
    
    @pytest.mark.asyncio
    async def test_get_market_breadth(self, mock_tushare_provider):
        """Test market breadth analysis"""
        mock_tushare_provider.get_daily_info = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20241221'],
            'up_count': [2500],
            'down_count': [1500],
            'amount': [500000000000]  # 5000 billion
        }))
        
        with patch('core.tools.index_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.index_tools import get_market_breadth
            
            result = await get_market_breadth("2024-12-21")
            
            assert "Market Breadth Analysis" in result
            assert "Up and down statistics" in result or "None yet" in result
    
    @pytest.mark.asyncio
    async def test_get_market_environment(self, mock_tushare_provider):
        """Test market environment assessment"""
        mock_tushare_provider.get_index_dailybasic = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['000001.SH'],
            'pe': [12.5],
            'pb': [1.2],
            'turnover_rate': [0.8],
            'total_mv': [50000000000000]  # 50 trillions
        }))
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': [f'202412{i:02d}' for i in range(1, 22)],
            'close': [3000 + i for i in range(21)],
            'pct_chg': [0.5, -0.3, 0.2, -0.1, 0.4] * 4 + [0.3]
        }))
        
        with patch('core.tools.index_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.index_tools import get_market_environment
            
            result = await get_market_environment("2024-12-21")
            
            assert "Market environment assessment" in result
    
    @pytest.mark.asyncio
    async def test_identify_market_cycle(self, mock_tushare_provider):
        """Test market cycle identification"""
        # Create simulated uptrend data
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': [f'2024{(i//30+1):02d}{(i%30+1):02d}' for i in range(120)],
            'close': [3000 + i * 5 for i in range(120)],
            'high': [3010 + i * 5 for i in range(120)],
            'low': [2990 + i * 5 for i in range(120)],
        }))
        
        with patch('core.tools.index_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.index_tools import identify_market_cycle
            
            result = await identify_market_cycle("2024-12-21")
            
            assert "Market cycle judgment" in result


class TestIndexAnalystAgent:
    """Test market analysts Agent"""
    
    def test_agent_metadata(self):
        """Test Agent Metadata"""
        from core.agents.adapters.index_analyst import IndexAnalystAgent
        
        metadata = IndexAnalystAgent.get_metadata()
        
        assert metadata.id == "index_analyst"
        assert metadata.name == "Market/Index Analyst"
        assert "Market" in metadata.tags or "Index" in metadata.tags
    
    def test_agent_execute(self):
        """Test Agent execution"""
        from core.agents.adapters.index_analyst import IndexAnalystAgent
        
        agent = IndexAnalystAgent()
        
        # Simulation Analysis Tools
        mock_report = "Test market analysis report"
        with patch('core.tools.index_tools.analyze_index_sync', return_value=mock_report):
            state = {
                "trade_date": "2024-12-21",
                "messages": []
            }
            
            result = agent.execute(state)
            
            assert "index_report" in result
            assert result["index_report"] == mock_report


class TestAgentStateIndexField:
    """Test the index_report field in AgentState"""
    
    def test_index_report_field_exists(self):
        """Test that index_report field exists"""
        from tradingagents.agents.utils.agent_states import AgentState
        
        annotations = AgentState.__annotations__
        
        assert 'index_report' in annotations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


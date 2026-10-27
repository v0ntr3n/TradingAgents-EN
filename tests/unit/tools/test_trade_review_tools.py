"""
Trading review toolset testing

Test the transaction review tool in the v2.0 tool system
"""

import pytest
from core.tools.registry import ToolRegistry


class TestTradeReviewTools:
    """Trading review tool testing"""
    
    def test_tools_registered(self):
        """Test whether the tool is correctly registered"""
        registry = ToolRegistry()
        
        # Check if the tool exists
        tool_ids = [
            "get_trade_records",
            "build_trade_info",
            "get_account_info",
            "get_market_snapshot_for_review"
        ]
        
        for tool_id in tool_ids:
            assert registry.get_function(tool_id) is not None, f"Tools {tool_id} Not registered"
    
    def test_tool_metadata(self):
        """Test tool metadata"""
        registry = ToolRegistry()
        
        # Check get_account_info tool metadata
        tool_func = registry.get_function("get_account_info")
        assert tool_func is not None
        
        # Check if the tool has correct metadata
        assert hasattr(tool_func, '__name__')
        assert tool_func.__name__ == 'get_account_info'
    
    def test_build_trade_info_tool(self):
        """Test the build_trade_info tool"""
        from core.tools.implementations.trade_review import build_trade_info
        
        # Test empty data
        result = build_trade_info([], None)
        assert result["success"] is False
        
        # Test valid data
        trade_records = [
            {
                "_id": "123",
                "code": "688111",
                "market": "CN",
                "side": "buy",
                "quantity": 100,
                "price": 100.0,
                "amount": 10000.0,
                "pnl": 0.0,
                "timestamp": "2025-01-01T10:00:00"
            },
            {
                "_id": "124",
                "code": "688111",
                "market": "CN",
                "side": "sell",
                "quantity": 100,
                "price": 110.0,
                "amount": 11000.0,
                "pnl": 1000.0,
                "timestamp": "2025-01-10T10:00:00"
            }
        ]
        
        result = build_trade_info(trade_records, "688111")
        assert result["success"] is True
        
        data = result["data"]
        assert data["code"] == "688111"
        assert data["total_buy_quantity"] == 100
        assert data["total_sell_quantity"] == 100
        assert data["realized_pnl"] == 1000.0
        assert data["holding_days"] == 9
    
    def test_agent_tools_binding(self):
        """Test Agent Tool Binding"""
        from core.agents.config import BUILTIN_AGENTS

        # Check if position_analyst is bound to a new tool
        position_analyst = BUILTIN_AGENTS.get("position_analyst")
        assert position_analyst is not None

        expected_tools = [
            "get_trade_records",
            "build_trade_info",
            "get_account_info",
            "get_market_snapshot_for_review"
        ]

        for tool_id in expected_tools:
            assert tool_id in position_analyst.tools, \
                f"Tools {tool_id} not bound to position_analyst"

        # Check default tools
        assert "build_trade_info" in position_analyst.default_tools
        assert "get_account_info" in position_analyst.default_tools

    def test_emotion_analyst_tools_binding(self):
        """Testing the emotion_analyst tool binding"""
        from core.agents.config import BUILTIN_AGENTS

        emotion_analyst = BUILTIN_AGENTS.get("emotion_analyst")
        assert emotion_analyst is not None

        # Check whether the transaction review tool is bound
        expected_tools = [
            "get_trade_records",
            "build_trade_info",
            "get_account_info"
        ]

        for tool_id in expected_tools:
            assert tool_id in emotion_analyst.tools, \
                f"Tools {tool_id} not bound to emotion_analyst"

        # Check default tools
        assert "build_trade_info" in emotion_analyst.default_tools
        assert "get_account_info" in emotion_analyst.default_tools

        # Check requires_tools flag
        assert emotion_analyst.requires_tools is True

    def test_review_manager_tools_binding(self):
        """Test review_manager tool binding"""
        from core.agents.config import BUILTIN_AGENTS

        review_manager = BUILTIN_AGENTS.get("review_manager")
        assert review_manager is not None

        # Check whether the transaction review tool is bound
        expected_tools = [
            "get_trade_records",
            "build_trade_info",
            "get_account_info",
            "get_market_snapshot_for_review"
        ]

        for tool_id in expected_tools:
            assert tool_id in review_manager.tools, \
                f"Tools {tool_id} not bound to review_manager"

        # Check default tools
        assert "build_trade_info" in review_manager.default_tools
        assert "get_account_info" in review_manager.default_tools

        # Check requires_tools flag
        assert review_manager.requires_tools is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


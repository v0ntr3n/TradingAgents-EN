"""
Test node mapping fix

Verify:
1. All v2 nodes have mappings (including neutral_analyst_v2 etc.)
2. step_name is different from message
3. step_name is the short Chinese name
4. message is a detailed description
"""

import pytest
from core.workflow.engine import WorkflowEngine


def test_v2_risk_analysts_mapping():
    """Test v2 risk analyst node mapping"""
    
    engine = WorkflowEngine(None)
    
    # Test all v2 risk analyst nodes
    test_cases = [
        ("risky_analyst_v2", "Highly Resilient Scenario Analyst", "⚡ High-resilience scenario analysts are reviewing conditions for upward revisions to conclusions..."),
        ("safe_analyst_v2", "Defense Scenario Analyst", "🛡️ Defense scenario analysts reviewing vulnerabilities and critical risks..."),
        ("neutral_analyst_v2", "Baseline Scenario Analyst", "⚖️ Baseline scenario analysts are reviewing the baseline scenario and evidence completeness..."),
        ("risk_manager_v2", "risk assessor", "👔 Risk assessors are reviewing the robustness of research conclusions..."),
    ]
    
    print("\n Test v2 risk analyst node mapping:")
    for node_name, expected_step_name, expected_message in test_cases:
        progress, message, step_name = engine._get_node_progress_info(node_name)
        
        print(f"\n node: {node_name}")
        print(f"  Progress: {progress}%")
        print(f"  step name: {step_name}")
        print(f"  news: {message}")
        
        # Verification step name and message are different
        assert step_name != message, f"Step name and message should not be the same: {node_name}"
        
        # Verification step name is short in Chinese
        assert step_name == expected_step_name, f"Step names don t match: Expectation '{expected_step_name}', actual '{step_name}'"
        
        # The verification message is a detailed description
        assert message == expected_message, f"Message does not match: Expectation '{expected_message}', actual '{message}'"
        
        # Verification step name does not contain English underscores
        assert "_" not in step_name, f"Step names should not contain underscores: {step_name}"
        
        print(f"  ✅ Verification passed")


def test_all_v2_nodes_mapping():
    """Test that all v2 nodes have correct mappings"""
    
    engine = WorkflowEngine(None)
    
    # All v2 nodes
    v2_nodes = [
        # analyst
        "market_analyst_v2",
        "fundamentals_analyst_v2",
        "news_analyst_v2",
        "social_analyst_v2",
        "sector_analyst_v2",
        "index_analyst_v2",
        # researcher
        "bull_researcher_v2",
        "bear_researcher_v2",
        "research_manager_v2",
        # trader
        "trader_v2",
        # risk management
        "risky_analyst_v2",
        "safe_analyst_v2",
        "neutral_analyst_v2",
        "risk_manager_v2",
    ]
    
    print("\n Test all v2 node mappings:")
    for node_name in v2_nodes:
        progress, message, step_name = engine._get_node_progress_info(node_name)
        
        print(f"\n{node_name}:")
        print(f"  step name: {step_name}")
        print(f"  news: {message}")
        
        # Verify that the return value is not empty
        assert progress is not None, f"Progress should not be empty: {node_name}"
        assert message is not None, f"Message should not be empty: {node_name}"
        assert step_name is not None, f"Step name should not be empty: {node_name}"
        
        # Verification step name and message are different
        assert step_name != message, f"Step name and message should not be the same: {node_name}"
        
        # The verification step name is in Chinese (without the _v2 suffix)
        assert "_v2" not in step_name, f"Step names should not contain _v2: {step_name}"
        assert "_" not in step_name, f"Step names should not contain underscores: {step_name}"
        
        # Verification message contains emoji and Chinese description
        assert len(message) > len(step_name), f"The message should be more detailed than the step name: {node_name}"
        
        print(f"  ✅ Verification passed")


def test_step_name_vs_message_difference():
    """Differences between test step names and messages"""
    
    engine = WorkflowEngine(None)
    
    test_cases = [
        ("market_analyst_v2", "market analyst", "📈 Market analysts are analyzing technical indicators and market trends..."),
        ("neutral_analyst_v2", "Baseline Scenario Analyst", "⚖️ Baseline scenario analysts are reviewing the baseline scenario and evidence completeness..."),
        ("trader_v2", "research integrator", "🧩 Research integrator is generating a user version of the research brief..."),
    ]
    
    print("\n Differences between test step names and messages:")
    for node_name, expected_step_name, expected_message in test_cases:
        progress, message, step_name = engine._get_node_progress_info(node_name)
        
        print(f"\n node: {node_name}")
        print(f"  step name (current_step_name): {step_name}")
        print(f"  news (message): {message}")
        
        # Verification step names are short
        assert len(step_name) < 12, f"Step names should be short: {step_name}"
        
        # The verification message is detailed
        assert len(message) > 10, f"The message should be detailed: {message}"
        
        # Verification step name does not contain emoji
        assert not any(ord(c) > 127 for c in step_name if c in "📈💰📰💬📊🐂🐻🔬💼⚡🛡️⚖️👔"), \
            f"Step names should not contain emoji: {step_name}"
        
        # The verification message contains emoji
        assert any(ord(c) > 127 for c in message), f"The message should contain emoji: {message}"
        
        print(f"  ✅ Verification passed")


def test_v1_nodes_also_updated():
    """Test v1 nodes are also updated"""
    
    engine = WorkflowEngine(None)
    
    test_cases = [
        ("market_analyst", "market analyst"),
        ("neutral_analyst", "neutral analyst"),
    ]
    
    print("\n Test v1 nodes are also updated:")
    for node_name, expected_step_name in test_cases:
        progress, message, step_name = engine._get_node_progress_info(node_name)
        
        print(f"\n node: {node_name}")
        print(f"  step name: {step_name}")
        print(f"  news: {message}")
        
        # Verification step name is in Chinese
        assert step_name == expected_step_name, f"Step names don t match: Expectation '{expected_step_name}', actual '{step_name}'"
        
        # Verification step name and message are different
        assert step_name != message, f"Step name and message should not be the same: {node_name}"
        
        print(f"  ✅ Verification passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


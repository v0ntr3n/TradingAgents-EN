"""Separation of test step names and messages

Verify:
1. current_step_name Should be a short Chinese name (such as "market analyst") 
2. message should be a detailed description (e.g. "📈 Market analysts are analyzing technical indicators and market trends...") 
3. current_step_description Should be the same as message
"""

import pytest


def test_node_mapping_returns_three_values():
    """The test node mapping returns three values: progress, message, step name"""
    from core.workflow.engine import WorkflowEngine
    
    # Create engine instance
    engine = WorkflowEngine()
    
    # Test several key nodes
    test_nodes = [
        "market_analyst_v2",
        "fundamentals_analyst_v2",
        "news_analyst_v2",
        "neutral_analyst_v2",
        "risk_manager_v2",
    ]
    
    for node_name in test_nodes:
        progress, message, step_name = engine._get_node_progress_info(node_name)
        
        print(f"\n node: {node_name}")
        print(f"  Progress: {progress}%")
        print(f"  step name: {step_name}")
        print(f"  news: {message}")
        
        # Verify return value
        assert progress is not None, f"{node_name} The progress of should not be None"
        assert isinstance(progress, (int, float)), f"{node_name} The progress should be a number"
        assert message is not None, f"{node_name} The message should not be None"
        assert step_name is not None, f"{node_name} The step name should not be None"
        
        # Verification step name and message are different
        assert step_name != message, f"{node_name} The step name and message should be different"
        
        # Verification step names are short (without emojis and detailed descriptions)
        assert len(step_name) < len(message), f"{node_name} The step name should be shorter than the message"
        
        # Verification message contains emoji or detailed description
        assert len(message) > 10, f"{node_name} The message should be a detailed description"


def test_progress_callback_parameters():
    """Test progress callback receives correct parameters"""
    from core.workflow.engine import WorkflowEngine
    
    # Create engine instance
    engine = WorkflowEngine()
    
    # Record callback parameters
    callback_params = []
    
    def test_callback(progress: float, message: str, **kwargs):
        """Test callback function"""
        callback_params.append({
            "progress": progress,
            "message": message,
            "step_name": kwargs.get("step_name"),
            "kwargs": kwargs
        })
    
    # Set callback
    engine.set_progress_callback(test_callback)
    
    # Simulation progress report
    engine._report_progress(
        progress=50,
        message="📈 Market analysts are analyzing technical indicators and market trends...",
        step_name="market analyst"
    )
    
    # Validate callback parameters
    assert len(callback_params) == 1, "The callback should be called once"
    
    params = callback_params[0]
    assert params["progress"] == 50, "The progress should be 50"
    assert params["message"] == "📈 Market analysts are analyzing technical indicators and market trends...", "The message should be detailed"
    assert params["step_name"] == "market analyst", "Step names should be short names"
    
    print("\n✅ Progress callback parameter verification passed:")
    print(f"  Progress: {params['progress']}%")
    print(f"  step name: {params['step_name']}")
    print(f"  news: {params['message']}")


def test_redis_progress_tracker_fields():
    """Test the fields of RedisProgressTracker"""
    from app.services.progress.tracker import RedisProgressTracker
    
    # Create tracker
    tracker = RedisProgressTracker(
        task_id="test_task",
        analysts=["market", "fundamentals"],
        research_depth="Standard",
        llm_provider="dashscope"
    )
    
    # Update progress (simulated workflow engine callback)
    tracker.update_progress({
        "progress_percentage": 50,
        "last_message": "📈 Market analysts are analyzing technical indicators and market trends...",
        "current_step_name": "market analyst",
        "current_step_description": "📈 Market analysts are analyzing technical indicators and market trends...",
    })
    
    # Get dictionary
    data = tracker.to_dict()
    
    print("\n✅ RedisProgressTracker Field validation:")
    print(f"  current_step_name: {data.get('current_step_name')}")
    print(f"  current_step_description: {data.get('current_step_description')}")
    print(f"  last_message: {data.get('last_message')}")
    
    # Validate fields
    assert "current_step_name" in data, "Should contain current_step_name field"
    assert "current_step_description" in data, "Should contain current_step_description field"
    assert data["current_step_name"] == "market analyst", "Step names should be short names"
    assert data["current_step_description"] == "📈 Market analysts are analyzing technical indicators and market trends...", "The description should be a detailed description"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


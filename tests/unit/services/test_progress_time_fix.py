"""
Time calculation fix for test progress tracker

Verify:
1. elapsed_time, remaining_time, estimated_total_time mathematical consistency of
2. v2 Versioned node name mapping
"""

import time
import pytest
from app.services.progress.tracker import RedisProgressTracker
from core.workflow.engine import WorkflowEngine


def test_time_calculation_consistency():
    """Test time calculation consistency"""
    # Create a progress tracker
    tracker = RedisProgressTracker(
        task_id="test_task_001",
        analysts=["market_analyst_v2", "fundamentals_analyst_v2", "news_analyst_v2"],
        research_depth="Depth",
        llm_provider="dashscope"
    )
    
    # wait 1 second
    time.sleep(1)
    
    # Update progress to 50%
    tracker.update_progress({
        'progress_percentage': 50,
        'last_message': 'Analysis in progress...'
    })
    
    # Get progress data
    progress_data = tracker.to_dict()
    
    # Verify time field exists
    assert 'elapsed_time' in progress_data
    assert 'remaining_time' in progress_data
    assert 'estimated_total_time' in progress_data
    
    elapsed = progress_data['elapsed_time']
    remaining = progress_data['remaining_time']
    estimated_total = progress_data['estimated_total_time']
    
    # Verify mathematical consistency:elapsed + remaining ≈ estimated_total
    # Allow 1 second error (due to slight delay in calculation time)
    sum_time = elapsed + remaining
    diff = abs(sum_time - estimated_total)
    
    print(f"\n Time calculation verification:")
    print(f"  elapsed time: {elapsed:.2f}seconds")
    print(f"  Estimated remaining: {remaining:.2f}seconds")
    print(f"  Estimated total duration: {estimated_total:.2f}seconds")
    print(f"  sum: {sum_time:.2f}seconds")
    print(f"  Difference: {diff:.2f}seconds")
    
    assert diff < 1.0, f"Inconsistent time calculations: {elapsed} + {remaining} = {sum_time} ≠ {estimated_total}"
    
    # Verify that the elapsed time is greater than 0 (because we waited 1 second)
    assert elapsed >= 1.0, f"The elapsed time should be at least 1 second, the actual: {elapsed}"
    
    # Verify that the estimated total duration is as expected (3 analysts + In-depth analysis = 330 * 2.0 = 660 seconds)
    expected_total = 660
    assert abs(estimated_total - expected_total) < 10, f"Estimated total duration should be approximately{expected_total}seconds, actual: {estimated_total}"


def test_v2_node_name_mapping():
    """Testing node name mapping for v2 version"""
    engine = WorkflowEngine()

    # Test v2 analyst node
    v2_nodes = [
        ("market_analyst_v2", "market analyst"),
        ("fundamentals_analyst_v2", "fundamental analyst"),
        ("news_analyst_v2", "news analyst"),
        ("social_analyst_v2", "social media analyst"),
        ("sector_analyst_v2", "Sector Analyst"),
        ("index_analyst_v2", "Market Analyst"),
    ]

    print("\nv2 Node name mapping verification:")
    for node_id, expected_keyword in v2_nodes:
        progress, message, step_name = engine._get_node_progress_info(node_id)
        
        print(f"  {node_id}:")
        print(f"    Progress: {progress}%")
        print(f"    news: {message}")
        print(f"    step name: {step_name}")
        
        # Verify that the return value is not None
        assert progress is not None, f"node {node_id} There should be a progress map"
        assert message is not None, f"node {node_id} There should be a message map"
        assert step_name is not None, f"node {node_id} There should be step name mapping"
        
        # Verify that the message contains the expected keywords
        assert expected_keyword in message, f"node {node_id} The message should contain '{expected_keyword}'"
        
        # Verify that the step name is consistent with the node ID
        assert step_name == node_id, f"node {node_id} The step name should be {node_id}, actual: {step_name}"


def test_progress_update_time_recalculation():
    """The test recalculates the time every time the progress is updated"""
    tracker = RedisProgressTracker(
        task_id="test_task_002",
        analysts=["market_analyst_v2"],
        research_depth="fast",
        llm_provider="dashscope"
    )
    
    # First acquisition time
    time.sleep(0.5)
    tracker.update_progress({'progress_percentage': 25})
    data1 = tracker.to_dict()
    elapsed1 = data1['elapsed_time']
    
    # Second acquisition time (after waiting 1 second)
    time.sleep(1)
    tracker.update_progress({'progress_percentage': 50})
    data2 = tracker.to_dict()
    elapsed2 = data2['elapsed_time']
    
    print(f"\n Time recalculation verification:")
    print(f"  First time elapsed: {elapsed1:.2f}seconds")
    print(f"  Second time elapsed: {elapsed2:.2f}seconds")
    print(f"  time difference: {elapsed2 - elapsed1:.2f}seconds")
    
    # Verify that the second elapsed time is greater than the first time (at least 1 second more)
    assert elapsed2 > elapsed1, "The elapsed time for the second time should be greater than the first time"
    assert (elapsed2 - elapsed1) >= 0.9, f"The time difference should be at least 0.9 seconds, actual: {elapsed2 - elapsed1}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


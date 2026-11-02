"""
Post-processing Agent Test

Test post-processing of ReportSaver, EmailNotifier, SystemNotifier, etc.Agent
"""

import pytest
from datetime import datetime
from pathlib import Path
import json

from core.agents.post_processors import (
    ReportSaverAgent,
    EmailNotifierAgent,
    SystemNotifierAgent
)


class TestReportSaverAgent:
    """Save test report Agent"""
    
    def test_save_to_file(self, tmp_path):
        """Save test to file"""
        # Create Agent
        agent = ReportSaverAgent(
            operations=[
                {
                    "type": "save_to_file",
                    "path": str(tmp_path / "{ticker}_{date}.json"),
                    "format": "json"
                }
            ]
        )
        
        # Prepare test data
        state = {
            "ticker": "AAPL",
            "analysis_date": "20231215",
            "market_report": "Market analysis report...",
            "news_report": "News analysis report...",
            "investment_plan": {
                "recommendation": "buy",
                "confidence_score": 0.85
            }
        }
        
        # Execute save
        result = agent.execute(state)
        
        # Verification results
        assert result["report_saver_status"]["success"] is True
        assert len(result["report_saver_status"]["results"]) == 1
        
        # Verification file created
        saved_file = tmp_path / "AAPL_20231215.json"
        assert saved_file.exists()
        
        # Verify file contents
        with open(saved_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data["ticker"] == "AAPL"
            assert data["analysis_date"] == "20231215"
    
    def test_condition_check(self):
        """Test condition check"""
        # Create a conditional Agent
        agent = ReportSaverAgent(
            operations=[
                {
                    "type": "save_to_file",
                    "path": "test.json",
                    "format": "json"
                }
            ],
            conditions=[
                {
                    "field": "success",
                    "operator": "equals",
                    "value": True
                }
            ]
        )
        
        # Test conditions are met
        state_success = {"success": True, "ticker": "AAPL"}
        result = agent.execute(state_success)
        assert result["report_saver_status"]["success"] is True
        
        # Test conditions are not met
        state_fail = {"success": False, "ticker": "AAPL"}
        result = agent.execute(state_fail)
        assert result["report_saver_status"]["skipped"] is True


class TestEmailNotifierAgent:
    """Test email notification Agent"""
    
    def test_template_rendering(self):
        """Test template rendering"""
        agent = EmailNotifierAgent(
            operations=[
                {
                    "type": "send_email",
                    "to": "user@example.com",
                    "subject": "{ticker} Analysis completed - {recommendation}",
                    "template": "analysis_complete"
                }
            ]
        )
        
        state = {
            "ticker": "AAPL",
            "investment_plan": {
                "recommendation": "buy"
            }
        }
        
        # Test template rendering
        rendered = agent._render_template("{ticker} Analysis completed - {recommendation}", state)
        assert "AAPL" in rendered
        assert "buy" in rendered
    
    def test_conditional_email(self):
        """Test condition email sending"""
        agent = EmailNotifierAgent(
            operations=[
                {
                    "type": "send_email",
                    "to": "user@example.com",
                    "subject": "important signal",
                    "template": "important_signal"
                }
            ],
            conditions=[
                {
                    "field": "investment_plan.recommendation",
                    "operator": "in",
                    "value": ["buy", "sell"]
                },
                {
                    "field": "investment_plan.confidence_score",
                    "operator": "greater_than",
                    "value": 0.7
                }
            ]
        )
        
        # Test conditions are met
        state_match = {
            "investment_plan": {
                "recommendation": "buy",
                "confidence_score": 0.85
            }
        }
        result = agent.execute(state_match)
        assert result["email_notifier_status"]["success"] is True
        
        # The test conditions are not met (low confidence)
        state_no_match = {
            "investment_plan": {
                "recommendation": "buy",
                "confidence_score": 0.5
            }
        }
        result = agent.execute(state_no_match)
        assert result["email_notifier_status"]["skipped"] is True


class TestSystemNotifierAgent:
    """Test system notification Agent"""
    
    def test_notification_creation(self):
        """Test notification creation"""
        agent = SystemNotifierAgent(
            operations=[
                {
                    "type": "send_notification",
                    "notification_type": "analysis",
                    "title": "{ticker} Analysis completed",
                    "content": "{summary}",
                    "severity": "info"
                }
            ]
        )
        
        state = {
            "user_id": "user123",
            "ticker": "AAPL",
            "investment_plan": {
                "recommendation": "buy",
                "confidence_score": 0.85
            }
        }
        
        result = agent.execute(state)
        assert result["system_notifier_status"]["success"] is True
        assert result["system_notifier_status"]["user_id"] == "user123"


class TestConditionEvaluation:
    """Test condition evaluation"""
    
    def test_operators(self):
        """Test various operators"""
        agent = ReportSaverAgent()
        
        state = {
            "score": 0.85,
            "recommendation": "buy",
            "tags": ["tech", "growth"]
        }
        
        # equals
        assert agent._evaluate_condition(
            {"field": "recommendation", "operator": "equals", "value": "buy"},
            state
        ) is True
        
        # in
        assert agent._evaluate_condition(
            {"field": "recommendation", "operator": "in", "value": ["buy", "sell"]},
            state
        ) is True
        
        # greater_than
        assert agent._evaluate_condition(
            {"field": "score", "operator": "greater_than", "value": 0.7},
            state
        ) is True
        
        # less_than
        assert agent._evaluate_condition(
            {"field": "score", "operator": "less_than", "value": 0.9},
            state
        ) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


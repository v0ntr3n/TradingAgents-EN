#!/usr/bin/env python3
"""
Configuration management function testing
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.config.config_manager import ConfigManager, ModelConfig, PricingConfig, TokenTracker


def test_config_manager():
    """Test basic functionality of Configuration Manager"""
    print("🧪 Test Configuration Manager")
    print("=" * 50)
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(temp_dir)
        
        # Test model configuration
        print("📝 Test model configuration...")
        models = config_manager.load_models()
        assert len(models) > 0, "There should be a default model configuration"
        
        # Add new model
        new_model = ModelConfig(
            provider="test_provider",
            model_name="test_model",
            api_key="test_key_123",
            max_tokens=2000,
            temperature=0.5
        )
        
        models.append(new_model)
        config_manager.save_models(models)
        
        # Reload verification
        reloaded_models = config_manager.load_models()
        assert len(reloaded_models) == len(models), "The number of models should match"
        
        test_model = next((m for m in reloaded_models if m.provider == "test_provider"), None)
        assert test_model is not None, "The test model should be found"
        assert test_model.api_key == "test_key_123", "API The key should match"
        
        print("✅ Model configuration test passed")
        
        # Test pricing configuration
        print("📝 Test pricing configuration...")
        pricing_configs = config_manager.load_pricing()
        assert len(pricing_configs) > 0, "There should be a default pricing configuration"
        
        # Add new pricing
        new_pricing = PricingConfig(
            provider="test_provider",
            model_name="test_model",
            input_price_per_1k=0.001,
            output_price_per_1k=0.002,
            currency="CNY"
        )
        
        pricing_configs.append(new_pricing)
        config_manager.save_pricing(pricing_configs)
        
        # Test cost calculation
        cost = config_manager.calculate_cost("test_provider", "test_model", 1000, 500)
        expected_cost = (1000 / 1000) * 0.001 + (500 / 1000) * 0.002
        assert abs(cost - expected_cost) < 0.000001, f"Cost calculation error: {cost} != {expected_cost}"
        
        print("✅ Pricing configuration test passed")
        
        # Test usage record
        print("📝 Test usage record...")
        record = config_manager.add_usage_record(
            provider="test_provider",
            model_name="test_model",
            input_tokens=1000,
            output_tokens=500,
            session_id="test_session",
            analysis_type="test_analysis"
        )
        
        assert record.cost == expected_cost, "The usage record cost should match"
        
        # test statistics
        stats = config_manager.get_usage_statistics(30)
        assert stats["total_requests"] >= 1, "There should be at least one usage record"
        assert stats["total_cost"] >= expected_cost, "Total cost should include test records"
        
        print("✅ Test passed using record")
        
        # Test setup
        print("📝 Test system settings...")
        settings = config_manager.load_settings()
        assert "default_provider" in settings, "There should be a default setting"
        
        settings["test_setting"] = "test_value"
        config_manager.save_settings(settings)
        
        reloaded_settings = config_manager.load_settings()
        assert reloaded_settings["test_setting"] == "test_value", "Settings should be saved"
        
        print("✅ System settings test passed")


def test_token_tracker():
    """Test Token Tracker"""
    print("\n🧪 Test Token Tracker")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(temp_dir)
        token_tracker = TokenTracker(config_manager)
        
        # Test usage tracking
        print("📝 Test usage tracking...")
        record = token_tracker.track_usage(
            provider="dashscope",
            model_name="qwen-turbo",
            input_tokens=2000,
            output_tokens=1000,
            session_id="test_session_123",
            analysis_type="stock_analysis"
        )
        
        assert record is not None, "Usage records should be returned"
        assert record.input_tokens == 2000, "The input token number should match"
        assert record.output_tokens == 1000, "The output token number should match"
        assert record.cost > 0, "The cost should be greater than 0"
        
        print("✅ Test passes using trace")
        
        # Test cost estimate
        print("📝 Test cost estimate...")
        estimated_cost = token_tracker.estimate_cost(
            provider="dashscope",
            model_name="qwen-turbo",
            estimated_input_tokens=1000,
            estimated_output_tokens=500
        )
        
        assert estimated_cost > 0, "The estimated cost should be greater than 0"
        
        print("✅ Cost estimation test passed")
        
        # Test session cost
        print("📝 Test session cost...")
        session_cost = token_tracker.get_session_cost("test_session_123")
        assert session_cost == record.cost, "Session cost should match record cost"
        
        print("✅ Session cost test passed")


def test_pricing_accuracy():
    """Test pricing accuracy"""
    print("\n🧪 Test pricing accuracy")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(temp_dir)
        
        # Test pricing from different vendors
        test_cases = [
            ("dashscope", "qwen-turbo", 1000, 500),
            ("dashscope", "qwen-plus", 2000, 1000),
            ("openai", "gpt-3.5-turbo", 1000, 500),
            ("google", "gemini-pro", 1000, 500),
        ]
        
        for provider, model, input_tokens, output_tokens in test_cases:
            cost = config_manager.calculate_cost(provider, model, input_tokens, output_tokens)
            print(f"📊 {provider} {model}: {input_tokens}+{output_tokens} tokens = ¥{cost:.6f}")
            
            # Validate costing logic
            pricing_configs = config_manager.load_pricing()
            pricing = next((p for p in pricing_configs if p.provider == provider and p.model_name == model), None)
            
            if pricing:
                expected_cost = (input_tokens / 1000) * pricing.input_price_per_1k + (output_tokens / 1000) * pricing.output_price_per_1k
                assert abs(cost - expected_cost) < 0.000001, f"Cost calculation error: {cost} != {expected_cost}"
            else:
                assert cost == 0.0, f"Unknown model should return 0 cost but gets {cost}"
        
        print("✅ Pricing accuracy test passed")


def test_usage_statistics():
    """Test usage statistics function"""
    print("\n🧪 Test usage statistics function")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(temp_dir)
        
        # Add multiple usage records
        test_records = [
            ("dashscope", "qwen-turbo", 1000, 500, "session1", "stock_analysis"),
            ("dashscope", "qwen-plus", 2000, 1000, "session2", "stock_analysis"),
            ("openai", "gpt-3.5-turbo", 1500, 750, "session3", "news_analysis"),
            ("google", "gemini-pro", 1200, 600, "session4", "social_analysis"),
        ]
        
        total_expected_cost = 0
        for provider, model, input_tokens, output_tokens, session_id, analysis_type in test_records:
            record = config_manager.add_usage_record(
                provider=provider,
                model_name=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                session_id=session_id,
                analysis_type=analysis_type
            )
            total_expected_cost += record.cost
        
        # test statistics
        stats = config_manager.get_usage_statistics(30)
        
        assert stats["total_requests"] == len(test_records), f"The number of requests should be {len(test_records)}"
        print(f"📊 Statistical total cost: {stats['total_cost']:.6f}, expected total cost: {total_expected_cost:.6f}")
        assert abs(stats["total_cost"] - total_expected_cost) < 0.001, "Total cost should match"
        
        # Test statistics by supplier
        provider_stats = stats["provider_stats"]
        assert "dashscope" in provider_stats, "There should be dashscope statistics"
        assert "openai" in provider_stats, "There should be openai statistics"
        assert "google" in provider_stats, "There should be Google statistics"
        
        dashscope_stats = provider_stats["dashscope"]
        assert dashscope_stats["requests"] == 2, "dashscope There should be 2 requests"
        
        print("✅ Pass using statistical tests")


def main():
    """Main test function"""
    print("🧪 Configuration management function testing")
    print("=" * 60)
    
    try:
        test_config_manager()
        test_token_tracker()
        test_pricing_accuracy()
        test_usage_statistics()
        
        print("\n🎉 All tests passed!")
        print("=" * 60)
        print("✅ Configuration management function is normal")
        print("✅ Token Tracking function is normal")
        print("✅ Accurate cost calculation")
        print("✅ Correct usage statistics")
        
        return True
        
    except Exception as e:
        print(f"\n❌ test failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

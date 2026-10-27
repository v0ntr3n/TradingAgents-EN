"""
Configure system unit tests

Test new configuration management systems, including:
- Configure validator
- Configuration service
- Configuration provider
- Configure compatibility layer
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.startup_validator import (
    StartupValidator,
    ConfigItem,
    ConfigLevel,
    ValidationResult,
    ConfigurationError
)


class TestStartupValidator:
    """Test launch configuration validator"""
    
    def test_config_item_creation(self):
        """Test configuration item creation"""
        config = ConfigItem(
            key="TEST_KEY",
            level=ConfigLevel.REQUIRED,
            description="Test configuration",
            example="test_value"
        )
        
        assert config.key == "TEST_KEY"
        assert config.level == ConfigLevel.REQUIRED
        assert config.description == "Test configuration"
        assert config.example == "test_value"
    
    def test_validation_result_creation(self):
        """Test verification result creation"""
        result = ValidationResult(
            success=True,
            missing_required=[],
            missing_recommended=[],
            invalid_configs=[],
            warnings=[]
        )
        
        assert result.success is True
        assert len(result.missing_required) == 0
        assert len(result.missing_recommended) == 0
    
    @patch.dict(os.environ, {}, clear=True)
    def test_validate_missing_required_configs(self):
        """Test is missing validation of required configuration"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is False
        assert len(result.missing_required) > 0
        
        # Check whether required configuration items are included
        required_keys = [config.key for config in result.missing_required]
        assert "MONGODB_HOST" in required_keys
        assert "MONGODB_PORT" in required_keys
        assert "JWT_SECRET" in required_keys
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "27017",
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "test-secret-key-with-enough-length"
    })
    def test_validate_with_required_configs(self):
        """Test verification with required configuration"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is True
        assert len(result.missing_required) == 0
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "invalid_port",  # Invalid port
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "test-secret-key-with-enough-length"
    })
    def test_validate_invalid_port(self):
        """Test invalid port verification"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is False
        assert len(result.invalid_configs) > 0
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "27017",
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "short"  # Key too short
    })
    def test_validate_short_jwt_secret(self):
        """Testing for JWT keys that are too short"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is False
        assert len(result.invalid_configs) > 0
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "27017",
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "your-super-secret-jwt-key-change-in-production"  # Default value
    })
    def test_validate_default_jwt_secret_warning(self):
        """Warning when testing using default JWT key"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is True
        assert len(result.warnings) > 0
        assert any("JWT_SECRET" in warning for warning in result.warnings)
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "27017",
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "test-secret-key-with-enough-length"
    })
    def test_validate_missing_recommended_configs(self):
        """Testing is missing recommended configuration"""
        validator = StartupValidator()
        result = validator.validate()
        
        assert result.success is True
        assert len(result.missing_recommended) > 0
        
        # Check recommended configuration
        recommended_keys = [config.key for config in result.missing_recommended]
        assert "DEEPSEEK_API_KEY" in recommended_keys or "DASHSCOPE_API_KEY" in recommended_keys
    
    @patch.dict(os.environ, {}, clear=True)
    def test_raise_if_failed(self):
        """Exception thrown when test verification fails"""
        validator = StartupValidator()
        validator.validate()
        
        with pytest.raises(ConfigurationError):
            validator.raise_if_failed()
    
    @patch.dict(os.environ, {
        "MONGODB_HOST": "localhost",
        "MONGODB_PORT": "27017",
        "MONGODB_DATABASE": "test_db",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "JWT_SECRET": "test-secret-key-with-enough-length"
    })
    def test_raise_if_failed_success(self):
        """No exception is thrown when test verification is successful"""
        validator = StartupValidator()
        validator.validate()
        
        # should not throw exception
        validator.raise_if_failed()


class TestConfigCompat:
    """Test configuration compatibility layer"""
    
    def test_config_manager_compat_creation(self):
        """Test Configuration Manager Compatibility Layer Creation"""
        from app.core.config_compat import ConfigManagerCompat
        
        config_manager = ConfigManagerCompat()
        assert config_manager is not None
    
    def test_get_data_dir(self):
        """Test to obtain data directory"""
        from app.core.config_compat import ConfigManagerCompat
        
        config_manager = ConfigManagerCompat()
        data_dir = config_manager.get_data_dir()
        
        assert data_dir is not None
        assert isinstance(data_dir, str)
    
    @patch.dict(os.environ, {"DATA_DIR": "/custom/data/dir"})
    def test_get_data_dir_from_env(self):
        """Test to get the data directory from environment variables"""
        from app.core.config_compat import ConfigManagerCompat
        
        config_manager = ConfigManagerCompat()
        data_dir = config_manager.get_data_dir()
        
        assert data_dir == "/custom/data/dir"
    
    def test_load_settings(self):
        """Test loading system settings"""
        from app.core.config_compat import ConfigManagerCompat
        
        config_manager = ConfigManagerCompat()
        settings = config_manager.load_settings()
        
        assert settings is not None
        assert isinstance(settings, dict)
        assert "max_debate_rounds" in settings
    
    def test_token_tracker_compat_creation(self):
        """Test Token tracker compatibility layer creation"""
        from app.core.config_compat import TokenTrackerCompat
        
        tracker = TokenTrackerCompat()
        assert tracker is not None
    
    def test_track_usage(self):
        """Test record Token usage"""
        from app.core.config_compat import TokenTrackerCompat
        
        tracker = TokenTrackerCompat()
        tracker.track_usage(
            provider="test_provider",
            model_name="test_model",
            input_tokens=100,
            output_tokens=50,
            cost=0.01
        )
        
        summary = tracker.get_usage_summary()
        assert "test_provider:test_model" in summary
        assert summary["test_provider:test_model"]["total_input_tokens"] == 100
        assert summary["test_provider:test_model"]["total_output_tokens"] == 50
        assert summary["test_provider:test_model"]["call_count"] == 1
    
    def test_reset_usage(self):
        """Test reset usage statistics"""
        from app.core.config_compat import TokenTrackerCompat
        
        tracker = TokenTrackerCompat()
        tracker.track_usage("test", "model", 100, 50, 0.01)
        
        assert len(tracker.get_usage_summary()) > 0
        
        tracker.reset_usage()
        assert len(tracker.get_usage_summary()) == 0


class TestConfigPriority:
    """Test configuration priority"""
    
    @patch.dict(os.environ, {
        "TEST_CONFIG": "from_env",
        "MONGODB_HOST": "localhost"
    })
    def test_env_priority(self):
        """Test environment variable priority"""
        # Environment variables should have the highest priority
        assert os.getenv("TEST_CONFIG") == "from_env"
    
    def test_default_values(self):
        """Test defaults"""
        from app.core.config_compat import ConfigManagerCompat
        
        config_manager = ConfigManagerCompat()
        settings = config_manager._get_default_settings()
        
        assert settings["max_debate_rounds"] == 1
        assert settings["online_tools"] is True
        assert settings["memory_enabled"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


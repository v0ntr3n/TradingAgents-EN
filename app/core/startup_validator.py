"""
Start configuration validator

Verify the required configuration items required for system startup and provide friendly error prompts.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ConfigLevel(Enum):
    """configuration level"""
    REQUIRED = "required"      # Required configuration, if it is missing, it will not start.
    RECOMMENDED = "recommended"  # Recommended configuration, lack of it will affect functionality
    OPTIONAL = "optional"      # Optional configuration, lack of which does not affect basic functions


@dataclass
class ConfigItem:
    """Configuration items"""
    key: str                    # Configuration key name
    level: ConfigLevel          # configuration level
    description: str            # Configuration description
    example: Optional[str] = None  # Configuration example
    help_url: Optional[str] = None  # Help link
    validator: Optional[callable] = None  # Custom validation function


@dataclass
class ValidationResult:
    """Verification results"""
    success: bool               # Is the verification successful?
    missing_required: List[ConfigItem]  # Missing required configuration
    missing_recommended: List[ConfigItem]  # Missing recommended configuration
    invalid_configs: List[tuple[ConfigItem, str]]  # Invalid configuration (configuration item, error message)
    warnings: List[str]         # warning message


class StartupValidator:
    """Start configuration validator"""
    
    # Required configuration items
    REQUIRED_CONFIGS = [
        ConfigItem(
            key="MONGODB_HOST",
            level=ConfigLevel.REQUIRED,
            description="MongoDB host address",
            example="localhost"
        ),
        ConfigItem(
            key="MONGODB_PORT",
            level=ConfigLevel.REQUIRED,
            description="MongoDB port",
            example="27017",
            validator=lambda v: v.isdigit() and 1 <= int(v) <= 65535
        ),
        ConfigItem(
            key="MONGODB_DATABASE",
            level=ConfigLevel.REQUIRED,
            description="MongoDB Database name",
            example="tradingagents"
        ),
        ConfigItem(
            key="REDIS_HOST",
            level=ConfigLevel.REQUIRED,
            description="Redis host address",
            example="localhost"
        ),
        ConfigItem(
            key="REDIS_PORT",
            level=ConfigLevel.REQUIRED,
            description="Redis port",
            example="6379",
            validator=lambda v: v.isdigit() and 1 <= int(v) <= 65535
        ),
        ConfigItem(
            key="JWT_SECRET",
            level=ConfigLevel.REQUIRED,
            description="JWT Key (used to generate authentication tokens)",
            example="your-super-secret-jwt-key-change-in-production",
            validator=lambda v: len(v) >= 16
        ),
    ]
    
    # Recommended configuration items
    RECOMMENDED_CONFIGS = [
        ConfigItem(
            key="DEEPSEEK_API_KEY",
            level=ConfigLevel.RECOMMENDED,
            description="DeepSeek API Key (recommended, cost-effective)",
            example="sk-xxx",
            help_url="https://platform.deepseek.com/"
        ),
        ConfigItem(
            key="DASHSCOPE_API_KEY",
            level=ConfigLevel.RECOMMENDED,
            description="Alibaba Bailian API key (recommended, domestically produced and stable)",
            example="sk-xxx",
            help_url="https://dashscope.aliyun.com/"
        ),
        ConfigItem(
            key="TUSHARE_TOKEN",
            level=ConfigLevel.RECOMMENDED,
            description="Tushare Token (Recommended, professional A-share data)",
            example="xxx",
            help_url="https://tushare.pro/weborder/#/login?reg=tacn"
        ),
    ]
    
    def __init__(self):
        self.result = ValidationResult(
            success=True,
            missing_required=[],
            missing_recommended=[],
            invalid_configs=[],
            warnings=[]
        )

    def _is_valid_api_key(self, api_key: str) -> bool:
        """
        Determine whether the API Key is valid (not a placeholder)

        Args:
            api_key: To be verified API Key

        Returns:
            bool: True Indicates valid, False indicates invalid or placeholder
        """
        if not api_key:
            return False

        # Remove leading and trailing spaces and quotes
        api_key = api_key.strip().strip('"').strip("'")

        # Check if it is empty
        if not api_key:
            return False

        # Check if it is a placeholder (prefix)
        if api_key.startswith('your_') or api_key.startswith('your-'):
            return False

        # Check if it is a placeholder (suffix)
        if api_key.endswith('_here') or api_key.endswith('-here'):
            return False

        # Check length (allow shorter test keys, but still exclude obviously invalid values)
        if len(api_key) < 5:
            return False

        return True

    def validate(self) -> ValidationResult:
        """
        Verify configuration
        
        Returns:
            ValidationResult: Verification results
        """
        logger.info("🔍 Start verifying startup configuration...")
        
        # Verify required configuration
        self._validate_required_configs()
        
        # Verify recommended configuration
        self._validate_recommended_configs()
        
        # Check security configuration
        self._check_security_configs()
        
        # Set verification results
        self.result.success = len(self.result.missing_required) == 0 and len(self.result.invalid_configs) == 0
        
        # Output verification results
        self._print_validation_result()
        
        return self.result
    
    def _validate_required_configs(self):
        """Verify required configuration"""
        for config in self.REQUIRED_CONFIGS:
            value = os.getenv(config.key)
            
            if not value:
                self.result.missing_required.append(config)
                logger.error(f"❌ Missing required configuration: {config.key}")
            elif config.validator and not config.validator(value):
                self.result.invalid_configs.append((config, "Configuration value format is incorrect"))
                logger.error(f"❌ Configuration format error: {config.key}")
            else:
                logger.debug(f"✅ {config.key}: configured")
    
    def _validate_recommended_configs(self):
        """Verify recommended configuration"""
        for config in self.RECOMMENDED_CONFIGS:
            value = os.getenv(config.key)

            if not value:
                self.result.missing_recommended.append(config)
                logger.warning(f"⚠️  Missing recommended configuration: {config.key}")
            elif not self._is_valid_api_key(value):
                # API Key Exists but is a placeholder, treated as unconfigured
                self.result.missing_recommended.append(config)
                logger.warning(f"⚠️  {config.key} Configured as placeholder, treated as unconfigured")
            else:
                logger.debug(f"✅ {config.key}: configured")
    
    def _check_security_configs(self):
        """Check security configuration"""
        # Check if JWT key is using default value
        jwt_secret = os.getenv("JWT_SECRET", "")
        if jwt_secret in ["change-me-in-production", "your-super-secret-jwt-key-change-in-production"]:
            self.result.warnings.append(
                "⚠️  JWT_SECRET Use the default value, please be sure to modify it for production environment!"
            )
        
        # Check if CSRF key is using default value
        csrf_secret = os.getenv("CSRF_SECRET", "")
        if csrf_secret in ["change-me-csrf-secret", "your-csrf-secret-key-change-in-production"]:
            self.result.warnings.append(
                "⚠️  CSRF_SECRET Use the default value, please be sure to modify it for production environment!"
            )
        
        # Check whether DEBUG mode is used in production environment
        debug = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes", "on")
        if not debug:
            logger.info("ℹ️  Production environment mode")
        else:
            logger.info("ℹ️  Development environment mode (DEBUG=true) ")
    
    def _print_validation_result(self):
        """Output verification results"""
        logger.info("\n" + "=" * 70)
        logger.info("TradingAgents-CN Configuration Validation Result")
        logger.info("=" * 70)
        
        # Required configuration
        if self.result.missing_required:
            logger.info("\nMissing required configurations:")
            for config in self.result.missing_required:
                logger.info(f"   - {config.key}")
                logger.info(f"     Description: {config.description}")
                if config.example:
                    logger.info(f"     Example: {config.example}")
                if config.help_url:
                    logger.info(f"     Help: {config.help_url}")
        else:
            logger.info("\nAll required configurations are complete")

        # Invalid configuration
        if self.result.invalid_configs:
            logger.info("\nInvalid configurations:")
            for config, error in self.result.invalid_configs:
                logger.info(f"   - {config.key}: {error}")
                if config.example:
                    logger.info(f"     Example: {config.example}")

        # Recommended configuration
        if self.result.missing_recommended:
            logger.info("\nMissing recommended configurations (won't affect startup):")
            for config in self.result.missing_recommended:
                logger.info(f"   - {config.key}")
                logger.info(f"     Description: {config.description}")
                if config.help_url:
                    logger.info(f"     Get it from: {config.help_url}")

        # warning message
        if self.result.warnings:
            logger.info("\nSecurity warnings:")
            for warning in self.result.warnings:
                logger.info(f"   - {warning}")

        # Summary
        logger.info("\n" + "=" * 70)
        if self.result.success:
            logger.info("Configuration validation passed, system can start")
            if self.result.missing_recommended:
                logger.info("Tip: Configure recommended items for better functionality")
        else:
            logger.info("Configuration validation failed, please check the above items")
            logger.info("Configuration guide: docs/configuration_guide.md")
        logger.info("=" * 70 + "\n")
    
    def raise_if_failed(self):
        """Throws an exception if validation fails"""
        if not self.result.success:
            error_messages = []
            
            if self.result.missing_required:
                error_messages.append(
                    f"Missing required configuration: {', '.join(c.key for c in self.result.missing_required)}"
                )
            
            if self.result.invalid_configs:
                error_messages.append(
                    f"Configuration format error: {', '.join(c.key for c, _ in self.result.invalid_configs)}"
                )
            
            raise ConfigurationError(
                "Configuration verification failed:\n" + "\n".join(f"  • {msg}" for msg in error_messages) +
                "\n\n Please check the .env file and refer to docs/configuration_guide.md"
            )


class ConfigurationError(Exception):
    """Configuration error exception"""
    pass


def validate_startup_config() -> ValidationResult:
    """
    Verify startup configuration (convenience function)
    
    Returns:
        ValidationResult: Verification results
    
    Raises:
        ConfigurationError: If verification fails
    """
    validator = StartupValidator()
    result = validator.validate()
    validator.raise_if_failed()
    return result


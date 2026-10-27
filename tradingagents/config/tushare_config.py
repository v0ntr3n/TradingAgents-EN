#!/usr/bin/env python3
"""
Tushare Configuration management
Specially handles Tushare-related environment variable configuration, compatible with Python 3.13+
"""

import os
from typing import Dict, Any, Optional
from .env_utils import parse_bool_env, parse_str_env, get_env_info, validate_required_env_vars


class TushareConfig:
    """Tushare configuration manager"""
    
    def __init__(self):
        """Initialize Tushare configuration"""
        self.load_config()
    
    def load_config(self):
        """Load Tushare configuration"""
        # try to load python-dotenv
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        
        # Parse configuration
        self.token = parse_str_env("TUSHARE_TOKEN", "")
        self.enabled = parse_bool_env("TUSHARE_ENABLED", False)
        self.default_source = parse_str_env("DEFAULT_CHINA_DATA_SOURCE", "akshare")
        
        # Cache configuration
        self.cache_enabled = parse_bool_env("ENABLE_DATA_CACHE", True)
        self.cache_ttl_hours = parse_str_env("TUSHARE_CACHE_TTL_HOURS", "24")
        
        # debugging information
        self._debug_config()
    
    def _debug_config(self):
        """Output debugging configuration information"""
        print(f"🔍 Tushare Configure debugging information:")
        print(f"   TUSHARE_TOKEN: {'Already set' if self.token else 'not set'} ({len(self.token)}character)")
        print(f"   TUSHARE_ENABLED: {self.enabled} (original value: {os.getenv('TUSHARE_ENABLED', 'None')})")
        print(f"   DEFAULT_CHINA_DATA_SOURCE: {self.default_source}")
        print(f"   ENABLE_DATA_CACHE: {self.cache_enabled}")
    
    def is_valid(self) -> bool:
        """Check if the configuration is valid"""
        if not self.enabled:
            return False
        
        if not self.token:
            return False
        
        # Check the token format (Tushare token is usually a 40-character hexadecimal string)
        if len(self.token) < 30:
            return False
        
        return True
    
    def get_validation_result(self) -> Dict[str, Any]:
        """Get detailed verification results"""
        result = {
            'valid': False,
            'enabled': self.enabled,
            'token_set': bool(self.token),
            'token_length': len(self.token),
            'issues': [],
            'suggestions': []
        }
        
        # Check enabled status
        if not self.enabled:
            result['issues'].append("TUSHARE_ENABLED Not enabled")
            result['suggestions'].append("Set in .env file TUSHARE_ENABLED=true")
        
        # Check token
        if not self.token:
            result['issues'].append("TUSHARE_TOKEN not set")
            result['suggestions'].append("Set in .env file TUSHARE_TOKEN=your_token_here")
        elif len(self.token) < 30:
            result['issues'].append("TUSHARE_TOKEN The format may be incorrect")
            result['suggestions'].append("Check if the token is complete (usually 40 characters)")
        
        # If there are no problems, mark it as valid
        if not result['issues']:
            result['valid'] = True
        
        return result
    
    def get_env_debug_info(self) -> Dict[str, Any]:
        """Get environment variable debugging information"""
        env_vars = [
            "TUSHARE_TOKEN",
            "TUSHARE_ENABLED", 
            "DEFAULT_CHINA_DATA_SOURCE",
            "ENABLE_DATA_CACHE"
        ]
        
        debug_info = {}
        for var in env_vars:
            debug_info[var] = get_env_info(var)
        
        return debug_info
    
    def test_boolean_parsing(self) -> Dict[str, Any]:
        """Test boolean parsing compatibility"""
        test_cases = [
            ("true", True),
            ("True", True), 
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("", False),  # null value
            ("invalid", False)  # Invalid value
        ]
        
        results = {}
        for test_value, expected in test_cases:
            # Temporarily set environment variables
            original_value = os.getenv("TEST_BOOL_VAR")
            os.environ["TEST_BOOL_VAR"] = test_value
            
            # Test parsing
            parsed = parse_bool_env("TEST_BOOL_VAR", False)
            results[test_value] = {
                'expected': expected,
                'parsed': parsed,
                'correct': parsed == expected
            }
            
            # Restore original value
            if original_value is not None:
                os.environ["TEST_BOOL_VAR"] = original_value
            else:
                os.environ.pop("TEST_BOOL_VAR", None)
        
        return results
    
    def fix_common_issues(self) -> Dict[str, str]:
        """Fix common configuration issues"""
        fixes = {}
        
        # Check the FAQ for TUSHARE_ENABLED
        enabled_raw = os.getenv("TUSHARE_ENABLED", "")
        if enabled_raw.lower() in ["true", "1", "yes", "on"] and not self.enabled:
            fixes["TUSHARE_ENABLED"] = f"detected '{enabled_raw}', But it resolves to False, there may be compatibility issues"
        
        return fixes


def get_tushare_config() -> TushareConfig:
    """Get Tushare configuration example"""
    return TushareConfig()


def check_tushare_compatibility() -> Dict[str, Any]:
    """Check Tushare configuration compatibility"""
    config = get_tushare_config()
    
    return {
        'config_valid': config.is_valid(),
        'validation_result': config.get_validation_result(),
        'env_debug_info': config.get_env_debug_info(),
        'boolean_parsing_test': config.test_boolean_parsing(),
        'common_fixes': config.fix_common_issues()
    }


def diagnose_tushare_issues():
    """Diagnosing Tushare configuration issues"""
    print("🔍 Tushare Configuration diagnostics")
    print("=" * 60)
    
    compatibility = check_tushare_compatibility()
    
    # Show configuration status
    print(f"\n📊 configuration status:")
    validation = compatibility['validation_result']
    print(f"   Configuration is valid: {'✅' if validation['valid'] else '❌'}")
    print(f"   Tushare enable: {'✅' if validation['enabled'] else '❌'}")
    print(f"   Token settings: {'✅' if validation['token_set'] else '❌'}")
    
    # display problem
    if validation['issues']:
        print(f"\n⚠️ Found problem:")
        for issue in validation['issues']:
            print(f"   - {issue}")
    
    # Show suggestions
    if validation['suggestions']:
        print(f"\n💡 Repair suggestions:")
        for suggestion in validation['suggestions']:
            print(f"   - {suggestion}")
    
    # Show environment variable details
    print(f"\n🔍 Environment variable details:")
    for var, info in compatibility['env_debug_info'].items():
        status = "✅" if info['exists'] and not info['empty'] else "❌"
        print(f"   {var}: {status} {info['value']}")
    
    # Show boolean parsing test
    print(f"\n🧪 Boolean parsing test:")
    bool_tests = compatibility['boolean_parsing_test']
    failed_tests = [k for k, v in bool_tests.items() if not v['correct']]
    
    if failed_tests:
        print(f"   ❌ failed test: {failed_tests}")
        print(f"   ⚠️ There may be Python version compatibility issues")
    else:
        print(f"   ✅ All boolean parsing tests pass")
    
    # Show repair suggestions
    fixes = compatibility['common_fixes']
    if fixes:
        print(f"\n🔧 Automatic repair suggestions:")
        for var, fix in fixes.items():
            print(f"   {var}: {fix}")


if __name__ == "__main__":
    diagnose_tushare_issues()

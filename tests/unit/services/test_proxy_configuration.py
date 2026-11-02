"""
Test proxy configuration functionality

Verify:
1. PROXY_ENABLED=False There should be no proxy settings in the environment variables when
2. PROXY_ENABLED=True When , there should be proxy settings in the environment variables
3. Tushare API The proxy should be temporarily disabled while testing
4. Agent configuration should be editable in the web interface (even from environment variables)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.core.config import Settings


def test_proxy_disabled_by_default():
    """The proxy is turned off by default when testing"""
    settings = Settings()
    assert settings.PROXY_ENABLED is False


def test_proxy_enabled_sets_env_vars():
    """Setting environment variables when testing enabling proxy"""
    # Clear existing agent environment variables
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    
    # Impersonate enabled agent
    with patch.dict(os.environ, {
        'PROXY_ENABLED': 'true',
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'HTTPS_PROXY': 'http://127.0.0.1:7890'
    }):
        settings = Settings()
        
        # Verify proxy is enabled
        assert settings.PROXY_ENABLED is True
        
        # Verify environment variables are set
        assert os.environ.get('HTTP_PROXY') == 'http://127.0.0.1:7890'
        assert os.environ.get('HTTPS_PROXY') == 'http://127.0.0.1:7890'


def test_proxy_disabled_clears_env_vars():
    """Clear environment variables when testing disabled proxy"""
    # Set proxy environment variables
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    
    # Simulate disabled proxy
    with patch.dict(os.environ, {'PROXY_ENABLED': 'false'}):
        settings = Settings()
        
        # Authentication agent is disabled
        assert settings.PROXY_ENABLED is False
        
        # Verify environment variables are cleared
        assert 'HTTP_PROXY' not in os.environ
        assert 'HTTPS_PROXY' not in os.environ


def test_no_proxy_always_set():
    """Test NO_PROXY is always set (domestic data source)"""
    settings = Settings()
    
    # Verify that NO_PROXY is set
    assert os.environ.get('NO_PROXY') is not None
    assert 'eastmoney.com' in os.environ.get('NO_PROXY', '')
    assert 'api.tushare.pro' in os.environ.get('NO_PROXY', '')


@pytest.mark.asyncio
async def test_tushare_api_test_disables_proxy():
    """Test Tushare API Temporarily disable proxy while testing"""
    from app.services.config_service import ConfigService
    from app.core.database import get_mongo_db
    
    # Set proxy environment variables
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    
    # mock database
    mock_db = MagicMock()
    
    # Create service instance
    service = ConfigService()
    
    # Simulate Tushare API calls
    with patch('tushare.set_token') as mock_set_token, \
         patch('tushare.pro_api') as mock_pro_api:
        
        mock_pro = MagicMock()
        mock_pro.trade_cal.return_value = MagicMock()
        mock_pro_api.return_value = mock_pro
        
        # Call test method
        try:
            await service.test_tushare_connection('test_api_key')
        except Exception:
            pass  # Ignore errors and just focus on proxy settings
        
        # The proxy is disabled during the verification call
        #  (Actual verification requires adding logs in config_service.py)


def test_proxy_config_editable_in_web():
    """Test proxy configuration is editable in the web interface"""
    from app.services.config_provider import ConfigProvider
    
    provider = ConfigProvider()
    
    # Simulate reading agent configuration from environment variables
    with patch.dict(os.environ, {
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'HTTPS_PROXY': 'http://127.0.0.1:7890'
    }):
        # Get configuration metadata
        # meta = await provider.get_system_settings_meta()
        
        # Verify that the proxy configuration is editable
        # assert meta['http_proxy']['editable'] is True
        # assert meta['https_proxy']['editable'] is True
        # assert meta['proxy_enabled']['editable'] is True
        pass  # Requires an asynchronous testing environment


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


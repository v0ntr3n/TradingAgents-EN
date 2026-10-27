"""
test unified TushareProvider
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, date
import pandas as pd

from tradingagents.dataflows.providers.tushare_provider import TushareProvider


class TestTushareProvider:
    """Test TushareProvider class"""
    
    @pytest.fixture
    def provider(self):
        """Create TushareProvider instance"""
        return TushareProvider()
    
    @pytest.fixture
    def mock_tushare_api(self):
        """Simulation Tushare API"""
        mock_api = Mock()
        
        # Simulate stock_basic return data
        mock_basic_data = pd.DataFrame({
            'ts_code': ['000001.SZ', '000002.SZ'],
            'symbol': ['000001', '000002'],
            'name': ['Ping An Bank', 'Vanke A'],
            'area': ['Shenzhen', 'Shenzhen'],
            'industry': ['bank', 'Nationwide Real Estate'],
            'market': ['motherboard', 'motherboard'],
            'exchange': ['SZSE', 'SZSE'],
            'list_date': ['19910403', '19910129'],
            'is_hs': ['S', 'S']
        })
        mock_api.stock_basic.return_value = mock_basic_data
        
        # Simulate daily return data
        mock_daily_data = pd.DataFrame({
            'ts_code': ['000001.SZ'],
            'trade_date': ['20241201'],
            'open': [12.50],
            'high': [12.80],
            'low': [12.30],
            'close': [12.60],
            'pre_close': [12.40],
            'change': [0.20],
            'pct_chg': [1.61],
            'vol': [1000000],
            'amount': [12600000]
        })
        mock_api.daily.return_value = mock_daily_data
        
        # Simulate daily_basic return data
        mock_basic_daily = pd.DataFrame({
            'ts_code': ['000001.SZ'],
            'total_mv': [250000],
            'circ_mv': [200000],
            'pe': [5.2],
            'pb': [0.8],
            'turnover_rate': [2.5]
        })
        mock_api.daily_basic.return_value = mock_basic_daily
        
        return mock_api
    
    @pytest.mark.asyncio
    async def test_connect_success(self, provider, mock_tushare_api):
        """Test connection successful"""
        with patch('tradingagents.dataflows.providers.tushare_provider.TUSHARE_AVAILABLE', True), \
             patch('tradingagents.dataflows.providers.tushare_provider.ts') as mock_ts, \
             patch.object(provider, 'config', {'token': 'test_token'}):
            
            mock_ts.pro_api.return_value = mock_tushare_api
            
            result = await provider.connect()
            
            assert result is True
            assert provider.connected is True
            assert provider.api is not None
            mock_ts.set_token.assert_called_once_with('test_token')
    
    @pytest.mark.asyncio
    async def test_connect_no_token(self, provider):
        """Testing connection without token failed"""
        with patch('tradingagents.dataflows.providers.tushare_provider.TUSHARE_AVAILABLE', True), \
             patch.object(provider, 'config', {'token': ''}):
            
            result = await provider.connect()
            
            assert result is False
            assert provider.connected is False
    
    @pytest.mark.asyncio
    async def test_get_stock_list(self, provider, mock_tushare_api):
        """Test to get the stock list"""
        provider.connected = True
        provider.api = mock_tushare_api
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_tushare_api.stock_basic.return_value
            
            result = await provider.get_stock_list(market="CN")
            
            assert result is not None
            assert len(result) == 2
            assert result[0]['code'] == '000001'
            assert result[0]['name'] == 'Ping An Bank'
            assert result[0]['market_info']['market'] == 'CN'
            assert result[0]['market_info']['exchange'] == 'SZSE'
    
    @pytest.mark.asyncio
    async def test_get_stock_basic_info_single(self, provider, mock_tushare_api):
        """Test to obtain basic information of a single stock"""
        provider.connected = True
        provider.api = mock_tushare_api
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            # Return a single row of data
            single_stock_data = mock_tushare_api.stock_basic.return_value.iloc[:1]
            mock_to_thread.return_value = single_stock_data
            
            result = await provider.get_stock_basic_info('000001')
            
            assert result is not None
            assert result['code'] == '000001'
            assert result['name'] == 'Ping An Bank'
            assert result['industry'] == 'bank'
            assert result['data_source'] == 'tushare'
    
    @pytest.mark.asyncio
    async def test_get_stock_quotes(self, provider, mock_tushare_api):
        """Test to get real-time quotes"""
        provider.connected = True
        provider.api = mock_tushare_api
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            # Simulating realtime_quote fails and falls back to daily
            mock_to_thread.side_effect = [
                Exception("Insufficient permissions"),  # realtime_quote failed
                mock_tushare_api.daily.return_value,  # daily success
                mock_tushare_api.daily_basic.return_value  # daily_basic success
            ]
            
            result = await provider.get_stock_quotes('000001')
            
            assert result is not None
            assert result['code'] == '000001'
            assert result['close'] == 12.60
            assert result['current_price'] == 12.60
            assert result['pct_chg'] == 1.61
            assert result['pe'] == 5.2
            assert result['data_source'] == 'tushare'
    
    @pytest.mark.asyncio
    async def test_get_historical_data(self, provider, mock_tushare_api):
        """Test to obtain historical data"""
        provider.connected = True
        provider.api = mock_tushare_api
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_tushare_api.daily.return_value
            
            result = await provider.get_historical_data('000001', '2024-11-01', '2024-12-01')
            
            assert result is not None
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 1
            assert 'volume' in result.columns  # Check column renaming
    
    def test_normalize_ts_code(self, provider):
        """Test ts_code normalization"""
        # Test code that already has a suffix
        assert provider._normalize_ts_code('000001.SZ') == '000001.SZ'
        
        # Test the SSE code
        assert provider._normalize_ts_code('600000') == '600000.SH'
        assert provider._normalize_ts_code('688001') == '688001.SH'
        
        # Test the Shenzhen Stock Exchange code
        assert provider._normalize_ts_code('000001') == '000001.SZ'
        assert provider._normalize_ts_code('300001') == '300001.SZ'
    
    def test_determine_market_info_from_ts_code(self, provider):
        """Test market information to determine"""
        # Test the Shanghai Stock Exchange
        market_info = provider._determine_market_info_from_ts_code('600000.SH')
        assert market_info['market'] == 'CN'
        assert market_info['exchange'] == 'SSE'
        assert market_info['exchange_name'] == 'Shanghai Stock Exchange'
        
        # Test Shenzhen Stock Exchange
        market_info = provider._determine_market_info_from_ts_code('000001.SZ')
        assert market_info['market'] == 'CN'
        assert market_info['exchange'] == 'SZSE'
        assert market_info['exchange_name'] == 'Shenzhen Stock Exchange'
        
        # Test the North Exchange
        market_info = provider._determine_market_info_from_ts_code('830001.BJ')
        assert market_info['market'] == 'CN'
        assert market_info['exchange'] == 'BSE'
        assert market_info['exchange_name'] == 'Beijing Stock Exchange'
    
    def test_standardize_basic_info(self, provider):
        """Test basic information standardization"""
        raw_data = {
            'ts_code': '000001.SZ',
            'symbol': '000001',
            'name': 'Ping An Bank',
            'area': 'Shenzhen',
            'industry': 'bank',
            'market': 'motherboard',
            'list_date': '19910403',
            'is_hs': 'S'
        }
        
        result = provider.standardize_basic_info(raw_data)
        
        assert result['code'] == '000001'
        assert result['name'] == 'Ping An Bank'
        assert result['full_symbol'] == '000001.SZ'
        assert result['list_date'] == '1991-04-03'
        assert result['market_info']['exchange'] == 'SZSE'
        assert result['data_source'] == 'tushare'
        assert isinstance(result['updated_at'], datetime)
    
    def test_standardize_quotes(self, provider):
        """Test market data standardization"""
        raw_data = {
            'ts_code': '000001.SZ',
            'trade_date': '20241201',
            'close': 12.60,
            'open': 12.50,
            'high': 12.80,
            'low': 12.30,
            'vol': 1000000,
            'amount': 12600000,
            'pct_chg': 1.61,
            'pe': 5.2,
            'pb': 0.8
        }
        
        result = provider.standardize_quotes(raw_data)
        
        assert result['code'] == '000001'
        assert result['close'] == 12.60
        assert result['current_price'] == 12.60
        assert result['volume'] == 1000000
        assert result['pct_chg'] == 1.61
        assert result['trade_date'] == '2024-12-01'
        assert result['data_source'] == 'tushare'
    
    def test_format_date_output(self, provider):
        """Test date formatting"""
        # Test YYYYMMDD format
        assert provider._format_date_output('19910403') == '1991-04-03'
        assert provider._format_date_output('20241201') == '2024-12-01'
        
        # test date object
        test_date = date(2024, 12, 1)
        assert provider._format_date_output(test_date) == '2024-12-01'
        
        # test None
        assert provider._format_date_output(None) is None
        assert provider._format_date_output('') is None
    
    def test_convert_to_float(self, provider):
        """Test numeric conversion"""
        assert provider._convert_to_float(12.5) == 12.5
        assert provider._convert_to_float('12.5') == 12.5
        assert provider._convert_to_float('12') == 12.0
        assert provider._convert_to_float(None) is None
        assert provider._convert_to_float('') is None
        assert provider._convert_to_float('invalid') is None

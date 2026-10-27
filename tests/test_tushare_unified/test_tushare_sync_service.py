"""
test TushareSyncService
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from app.worker.tushare_sync_service import TushareSyncService


class TestTushareSyncService:
    """Test TushareSyncService class"""
    
    @pytest.fixture
    def sync_service(self):
        """Create TushareSyncService instance"""
        with patch('app.worker.tushare_sync_service.get_mongo_db') as mock_get_db, \
             patch('app.worker.tushare_sync_service.get_stock_data_service') as mock_get_service:

            # Mock databases and services
            mock_get_db.return_value = Mock()
            mock_get_service.return_value = Mock()

            service = TushareSyncService()

            # Simulation initialization
            service.provider = Mock()
            service.provider.is_available.return_value = True

            return service
    
    @pytest.fixture
    def mock_stock_list(self):
        """Simulated stock list data"""
        return [
            {
                "code": "000001",
                "name": "Ping An Bank",
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "industry": "bank",
                "market_info": {"market": "CN", "exchange": "SZSE"},
                "data_source": "tushare",
                "updated_at": datetime.utcnow()
            },
            {
                "code": "000002",
                "name": "Vanke A",
                "symbol": "000002",
                "full_symbol": "000002.SZ",
                "industry": "Nationwide Real Estate",
                "market_info": {"market": "CN", "exchange": "SZSE"},
                "data_source": "tushare",
                "updated_at": datetime.utcnow()
            }
        ]
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, sync_service):
        """Test initialization successful"""
        sync_service.provider.connect = AsyncMock(return_value=True)
        
        await sync_service.initialize()
        
        sync_service.provider.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self, sync_service):
        """Test initialization failed"""
        sync_service.provider.connect = AsyncMock(return_value=False)
        
        with pytest.raises(RuntimeError, match="Tushare Connection failed"):
            await sync_service.initialize()
    
    @pytest.mark.asyncio
    async def test_sync_stock_basic_info_success(self, sync_service, mock_stock_list):
        """Test synchronization of basic stock information successful"""
        # Simulate getting a stock list
        sync_service.provider.get_stock_list = AsyncMock(return_value=mock_stock_list)
        
        # Simulate batch processing
        sync_service._process_basic_info_batch = AsyncMock(return_value={
            "success_count": 2,
            "error_count": 0,
            "skipped_count": 0,
            "errors": []
        })
        
        with patch(
            'app.services.official_industry_service.upsert_industry_mapping_from_records',
            new_callable=AsyncMock,
            return_value={"provider": "tushare_fallback", "total": 2, "upserted": 2, "modified": 0}
        ) as mock_upsert_industry:
            result = await sync_service.sync_stock_basic_info()
        
        assert result["total_processed"] == 2
        assert result["success_count"] == 2
        assert result["error_count"] == 0
        assert "duration" in result
        sync_service.provider.get_stock_list.assert_called_once_with(market="CN")
        mock_upsert_industry.assert_awaited_once_with(mock_stock_list, provider="tushare_fallback")

    
    @pytest.mark.asyncio
    async def test_sync_stock_basic_info_no_data(self, sync_service):
        """No data when testing synchronized stock basic information"""
        sync_service.provider.get_stock_list = AsyncMock(return_value=None)
        
        result = await sync_service.sync_stock_basic_info()
        
        assert result["total_processed"] == 0
        assert result["success_count"] == 0
        assert result["error_count"] == 0
    
    @pytest.mark.asyncio
    async def test_process_basic_info_batch_success(self, sync_service, mock_stock_list):
        """Test processing basic information batch successful"""
        # Simulate database operations
        sync_service.stock_service.get_stock_basic_info = AsyncMock(return_value=None)
        sync_service.stock_service.update_stock_basic_info = AsyncMock(return_value=True)
        
        result = await sync_service._process_basic_info_batch(mock_stock_list, force_update=False)
        
        assert result["success_count"] == 2
        assert result["error_count"] == 0
        assert result["skipped_count"] == 0
        assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_process_basic_info_batch_skip_fresh_data(self, sync_service, mock_stock_list):
        """Test skips fresh data"""
        # Simulate the presence of fresh data
        fresh_data = {"updated_at": datetime.utcnow()}
        sync_service.stock_service.get_stock_basic_info = AsyncMock(return_value=fresh_data)
        sync_service._is_data_fresh = Mock(return_value=True)
        
        result = await sync_service._process_basic_info_batch(mock_stock_list, force_update=False)
        
        assert result["success_count"] == 0
        assert result["error_count"] == 0
        assert result["skipped_count"] == 2
    
    @pytest.mark.asyncio
    async def test_sync_realtime_quotes_success(self, sync_service):
        """Test synchronization of real-time market conditions successful"""
        # Simulate database queries
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__.return_value = [
            {"code": "000001"},
            {"code": "000002"}
        ]
        sync_service.db.stock_basic_info.find.return_value = mock_cursor
        
        # Simulate batch processing
        sync_service._process_quotes_batch = AsyncMock(return_value={
            "success_count": 2,
            "error_count": 0,
            "errors": []
        })
        
        result = await sync_service.sync_realtime_quotes()
        
        assert result["total_processed"] == 2
        assert result["success_count"] == 2
        assert result["error_count"] == 0
    
    @pytest.mark.asyncio
    async def test_process_quotes_batch_success(self, sync_service):
        """Test processing of quotation batches successful"""
        batch = ["000001", "000002"]
        
        # Simulate getting and saving quotes
        sync_service._get_and_save_quotes = AsyncMock(return_value=True)
        
        result = await sync_service._process_quotes_batch(batch)
        
        assert result["success_count"] == 2
        assert result["error_count"] == 0
        assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_get_and_save_quotes_success(self, sync_service):
        """Tested to obtain and save market data successfully"""
        mock_quotes = {
            "code": "000001",
            "close": 12.60,
            "current_price": 12.60,
            "data_source": "tushare"
        }
        
        sync_service.provider.get_stock_quotes = AsyncMock(return_value=mock_quotes)
        sync_service.stock_service.update_market_quotes = AsyncMock(return_value=True)
        
        result = await sync_service._get_and_save_quotes("000001")
        
        assert result is True
        sync_service.provider.get_stock_quotes.assert_called_once_with("000001")
        sync_service.stock_service.update_market_quotes.assert_called_once_with("000001", mock_quotes)
    
    @pytest.mark.asyncio
    async def test_get_and_save_quotes_no_data(self, sync_service):
        """There is no data in the test to obtain the market price."""
        sync_service.provider.get_stock_quotes = AsyncMock(return_value=None)
        
        result = await sync_service._get_and_save_quotes("000001")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_sync_historical_data_success(self, sync_service):
        """Test synchronization of historical data successful"""
        # Simulate database queries
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__.return_value = [
            {"code": "000001"},
            {"code": "000002"}
        ]
        sync_service.db.stock_basic_info.find.return_value = mock_cursor
        
        # Simulate obtaining historical data
        import pandas as pd
        mock_df = pd.DataFrame({
            'date': ['2024-12-01'],
            'close': [12.60],
            'volume': [1000000]
        })
        sync_service.provider.get_historical_data = AsyncMock(return_value=mock_df)
        sync_service._save_historical_data = AsyncMock(return_value=1)
        sync_service._get_last_sync_date = AsyncMock(return_value='2024-11-01')
        
        result = await sync_service.sync_historical_data(incremental=True)
        
        assert result["total_processed"] == 2
        assert result["success_count"] == 2
        assert result["total_records"] == 2
        assert result["error_count"] == 0
    
    @pytest.mark.asyncio
    async def test_sync_financial_data_success(self, sync_service):
        """Test synchronization of financial data successful"""
        # Simulate database queries
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__.return_value = [
            {"code": "000001"},
            {"code": "000002"}
        ]
        sync_service.db.stock_basic_info.find.return_value = mock_cursor
        
        # Simulate obtaining financial data
        mock_financial_data = {
            "symbol": "000001",
            "revenue": 1000000,
            "net_income": 100000,
            "data_source": "tushare"
        }
        sync_service.provider.get_financial_data = AsyncMock(return_value=mock_financial_data)
        sync_service._save_financial_data = AsyncMock(return_value=True)
        
        result = await sync_service.sync_financial_data()
        
        assert result["total_processed"] == 2
        assert result["success_count"] == 2
        assert result["error_count"] == 0
    
    def test_is_data_fresh(self, sync_service):
        """Test data freshness check"""
        # Test on fresh data
        fresh_time = datetime.utcnow() - timedelta(hours=1)
        assert sync_service._is_data_fresh(fresh_time, hours=24) is True
        
        # Test expired data
        old_time = datetime.utcnow() - timedelta(hours=25)
        assert sync_service._is_data_fresh(old_time, hours=24) is False
        
        # test None
        assert sync_service._is_data_fresh(None, hours=24) is False
    
    @pytest.mark.asyncio
    async def test_get_sync_status_success(self, sync_service):
        """Test to obtain synchronization status successfully"""
        # Simulate database queries
        sync_service.db.stock_basic_info.count_documents = AsyncMock(return_value=5000)
        sync_service.db.market_quotes.count_documents = AsyncMock(return_value=5000)
        
        sync_service.db.stock_basic_info.find_one = AsyncMock(return_value={
            "updated_at": datetime.utcnow()
        })
        sync_service.db.market_quotes.find_one = AsyncMock(return_value={
            "updated_at": datetime.utcnow()
        })
        
        result = await sync_service.get_sync_status()
        
        assert result["provider_connected"] is True
        assert result["collections"]["stock_basic_info"]["count"] == 5000
        assert result["collections"]["market_quotes"]["count"] == 5000
        assert "status_time" in result

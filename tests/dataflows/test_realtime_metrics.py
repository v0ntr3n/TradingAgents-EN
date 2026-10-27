"""
Test real-time PE/PB calculation capabilities
"""
import pytest
from tradingagents.dataflows.realtime_metrics import (
    calculate_realtime_pe_pb,
    validate_pe_pb,
    get_pe_pb_with_fallback
)


def test_validate_pe_pb():
    """Test PE/PB verification"""
    # normal range
    assert validate_pe_pb(20.5, 3.2) == True
    assert validate_pe_pb(50, 2.5) == True
    assert validate_pe_pb(-10, 1.5) == True  # Negative PE is allowed (loss-making enterprises)
    
    # PE Abnormal
    assert validate_pe_pb(1500, 3.2) == False  # PE Too big
    assert validate_pe_pb(-150, 3.2) == False  # PE too small
    
    # PB Abnormal
    assert validate_pe_pb(20.5, 150) == False  # PB Too big
    assert validate_pe_pb(20.5, 0.05) == False  # PB too small
    
    # None value
    assert validate_pe_pb(None, 3.2) == True
    assert validate_pe_pb(20.5, None) == True
    assert validate_pe_pb(None, None) == True


def test_calculate_realtime_pe_pb_with_mock_data(monkeypatch):
    """Test real-time PE/PB calculation (using mock data)"""
    # Mock MongoDB data
    class MockCollection:
        def find_one(self, query):
            code = query.get("code")
            if code == "000001":
                if "market_quotes" in str(self):
                    # Return to real-time quotes
                    return {
                        "code": "000001",
                        "close": 10.5,
                        "updated_at": "2025-10-14T10:30:00"
                    }
                else:
                    # Return to basic information
                    return {
                        "code": "000001",
                        "total_share": 100000,  # 10 Ten million shares = 10 100 million shares
                        "net_profit": 50000,    # 5 Tens of millions of yuan = 5 billion
                        "total_hldr_eqy_exc_min_int": 200000  # 20 Tens of millions of yuan = 20 billion
                    }
            return None
    
    class MockDB:
        def __getitem__(self, name):
            return MockCollection()
    
    class MockClient:
        def __getitem__(self, name):
            return MockDB()
    
    # Execute tests
    result = calculate_realtime_pe_pb("000001", MockClient())
    
    # Verification results
    assert result is not None
    assert result["price"] == 10.5
    assert result["is_realtime"] == True
    assert result["source"] == "realtime_calculated"
    
    # Verify PE Calculation: Market Cap = 10.5 * 100000 = 1050000 Ten thousand yuan,PE = 1050000 / 50000 = 21
    assert result["pe"] == 21.0
    
    # Verify PB calculation:PB = 1050000 / 200000 = 5.25
    assert result["pb"] == 5.25


def test_calculate_realtime_pe_pb_missing_data(monkeypatch):
    """What to do when testing is missing data"""
    class MockCollection:
        def find_one(self, query):
            return None
    
    class MockDB:
        def __getitem__(self, name):
            return MockCollection()
    
    class MockClient:
        def __getitem__(self, name):
            return MockDB()
    
    # Execute tests
    result = calculate_realtime_pe_pb("999999", MockClient())
    
    # Verification results
    assert result is None


def test_get_pe_pb_with_fallback_success(monkeypatch):
    """Testing the get function with degradation (successful scenario)"""
    # Mock Real-time calculation successful
    def mock_calculate(symbol, db_client):
        return {
            "pe": 22.5,
            "pb": 3.2,
            "pe_ttm": 23.1,
            "pb_mrq": 3.3,
            "source": "realtime_calculated",
            "is_realtime": True,
            "updated_at": "2025-10-14T10:30:00"
        }
    
    import tradingagents.dataflows.realtime_metrics as metrics_module
    monkeypatch.setattr(metrics_module, "calculate_realtime_pe_pb", mock_calculate)
    
    # Execute tests
    result = get_pe_pb_with_fallback("000001", None)
    
    # Verification results
    assert result["pe"] == 22.5
    assert result["pb"] == 3.2
    assert result["is_realtime"] == True


def test_get_pe_pb_with_fallback_to_static(monkeypatch):
    """Tests downgrade to static data"""
    # Mock Real-time calculation failed
    def mock_calculate(symbol, db_client):
        return None
    
    # Mock Static data acquisition
    class MockCollection:
        def find_one(self, query):
            return {
                "code": "000001",
                "pe": 20.0,
                "pb": 3.0,
                "pe_ttm": 21.0,
                "pb_mrq": 3.1,
                "updated_at": "2025-10-13T16:00:00"
            }
    
    class MockDB:
        def __getitem__(self, name):
            return MockCollection()
    
    class MockClient:
        def __getitem__(self, name):
            return MockDB()
    
    import tradingagents.dataflows.realtime_metrics as metrics_module
    monkeypatch.setattr(metrics_module, "calculate_realtime_pe_pb", mock_calculate)
    
    # Execute tests
    result = get_pe_pb_with_fallback("000001", MockClient())
    
    # Verification results
    assert result["pe"] == 20.0
    assert result["pb"] == 3.0
    assert result["is_realtime"] == False
    assert result["source"] == "daily_basic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


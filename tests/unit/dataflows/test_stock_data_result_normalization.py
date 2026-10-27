from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager
from tradingagents.dataflows.optimized_china_data import _coerce_stock_info_text


def test_get_stock_data_normalizes_tuple_fallback_result(monkeypatch):
    manager = DataSourceManager.__new__(DataSourceManager)
    manager.current_source = ChinaDataSource.TUSHARE

    monkeypatch.setattr(
        manager,
        "_get_tushare_data",
        lambda symbol, start_date, end_date, period="daily": "❌ Current data source failed",
    )
    monkeypatch.setattr(
        manager,
        "_try_fallback_sources",
        lambda symbol, start_date, end_date, period="daily": ("Stock code: 000001\n Stock name: Ping An Bank", "mongodb"),
    )

    result = manager.get_stock_data("000001", "2026-04-08", "2026-04-10")

    assert isinstance(result, str)
    assert "Stock name: Ping An Bank" in result


def test_coerce_stock_info_text_accepts_tuple_payload():
    stock_info = (
        {
            "name": "Ping An Bank",
            "area": "Shenzhen",
            "industry": "bank",
            "market": "motherboard",
            "list_date": "19910403",
            "current_price": 12.34,
            "change_pct": 1.23,
            "volume": 456789,
        },
        "app_cache",
    )

    text = _coerce_stock_info_text(stock_info, "000001")

    assert "Stock code: 000001" in text
    assert "Stock name: Ping An Bank" in text
    assert "current price: 12.34" in text
    assert "Increase or decrease: +1.23%" in text
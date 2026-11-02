import asyncio
from unittest.mock import Mock, patch

import pandas as pd

from tradingagents.dataflows.providers.china.akshare import AKShareProvider


def test_get_stock_quotes_handles_dash_placeholder_values():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider.ak = Mock()
    provider.ak.stock_bid_ask_em = Mock(return_value=pd.DataFrame([
        {"item": "Latest", "value": 432.93},
        {"item": "Increase", "value": 1.23},
        {"item": "ups and downs", "value": 5.26},
        {"item": "Chief", "value": "-"},
        {"item": "Amount", "value": "-"},
        {"item": "Change hands", "value": 0.0},
        {"item": "Quantity ratio", "value": "-"},
        {"item": "highest", "value": "-"},
        {"item": "lowest", "value": "-"},
        {"item": "Open today", "value": "-"},
        {"item": "Collected yesterday", "value": 427.67},
    ]))

    quotes = asyncio.run(provider.get_stock_quotes("300750"))

    assert quotes is not None
    assert quotes["code"] == "300750"
    assert quotes["price"] == 432.93
    assert quotes["change_percent"] == 1.23
    assert quotes["volume"] == 0
    assert quotes["amount"] == 0.0
    assert quotes["open"] == 0.0
    assert quotes["high"] == 0.0
    assert quotes["low"] == 0.0
    assert quotes["volume_ratio"] == 0.0
    assert quotes["pre_close"] == 427.67
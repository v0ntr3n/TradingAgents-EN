import asyncio


def test_single_stock_high_dividend_query_short_circuits_screening_flow(monkeypatch):
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())

    async def fake_get_context_messages(user_id, conversation_id=None):
        return "conv-single-stock", []

    async def fake_fetch_single_stock_item(keyword):
        assert keyword == "Moutai"
        return {
            "code": "600519",
            "name": "Kweichow Moutai",
            "industry": "Liquor",
            "close": 1680.0,
            "dividend_yield": 3.18,
            "pe_ttm": 27.6,
            "pb": 8.5,
            "roe": 31.2,
            "report_period": "20250930",
        }

    saved = {}

    async def fake_save_message(user_id, conversation_id, user_msg, assistant_reply, tools_used, stocks, phase, is_fallback=False):
        saved["conversation_id"] = conversation_id
        saved["assistant_reply"] = assistant_reply
        saved["stocks"] = stocks
        saved["phase"] = phase

    async def fail_ensure_client():
        raise AssertionError("single-stock direct query should not require LLM client")

    monkeypatch.setattr(service, "_get_context_messages", fake_get_context_messages)
    monkeypatch.setattr(service, "_fetch_single_stock_item", fake_fetch_single_stock_item)
    monkeypatch.setattr(service, "_save_message", fake_save_message)
    monkeypatch.setattr(service, "_ensure_client", fail_ensure_client)

    result = asyncio.run(service.chat("user-1", "Is Moutai a high dividend stock?"))

    assert result["phase"] == "result"
    assert result["tools_used"] == []
    assert result["conversation_id"] == "conv-single-stock"
    assert result["stocks"][0]["code"] == "600519"
    assert result["stocks"][0]["reason"].startswith("Single stock verification")
    assert "Kweichow Moutai" in result["reply"]
    assert "Will not recommend other stocks instead" not in result["reply"]
    assert "Filter by original requirements" not in result["reply"]
    assert "Yuntianhua" not in result["reply"]
    assert saved["phase"] == "result"


def test_single_stock_judgement_detection_does_not_capture_multi_stock_screening_request():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())

    assert service._looks_like_single_stock_judgement_query("Help me choose some high dividend stocks") is False
    assert service._looks_like_single_stock_judgement_query("Is Moutai a high dividend stock?") is True
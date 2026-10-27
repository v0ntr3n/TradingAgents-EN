import asyncio
import json
from types import SimpleNamespace


def test_determine_phase_resets_to_confirmation_for_new_request_after_result():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    history = [
        {"role": "assistant", "phase": "result", "content": "The screening results have been given in the previous round"},
    ]

    phase = service._determine_phase(history, "Help me choose some stocks with high dividends")

    assert phase == "confirmation"


def test_select_phase_history_drops_stale_history_for_fresh_confirmation():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    history = [
        {"role": "user", "content": "Execute screening plan"},
        {"role": "assistant", "phase": "result", "content": "Last round results JSON"},
        {"role": "user", "content": "Why is the financial reporting period still 20250930"},
        {"role": "assistant", "phase": "result", "content": "This is the data caliber explanation"},
    ]

    selected = service._select_phase_history(history, "confirmation", "Help me choose some stocks with high dividends")

    assert selected == []


def test_select_phase_history_keeps_latest_planning_only_for_result_execution():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    history = [
        {"role": "user", "content": "Help me choose some stocks with high dividends"},
        {"role": "assistant", "phase": "confirmation", "content": "needs analysis"},
        {"role": "user", "content": "Filter after taking suggestions"},
        {"role": "assistant", "phase": "planning", "content": "Strictly enforce dividend_yield>=5, pe_ttm<=15"},
        {"role": "user", "content": "Execute screening plan"},
        {"role": "assistant", "phase": "result", "content": "Old results and timeout description"},
        {"role": "user", "content": "Why is the financial reporting period still 20250930"},
        {"role": "assistant", "phase": "result", "content": "Old financial reporting periods explained"},
    ]

    selected = service._select_phase_history(history, "result", "Execute screening plan")

    assert selected == [history[3]]


def test_select_phase_history_keeps_latest_result_when_user_references_current_stocks():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    history = [
        {"role": "assistant", "phase": "planning", "content": "screening plan"},
        {"role": "assistant", "phase": "result", "content": "5 stocks currently recommended"},
    ]

    selected = service._select_phase_history(history, "result", "Add these 5 stocks to your watch list")

    assert selected == history


def test_extract_locked_execution_plan_keeps_planning_parameters():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    history = [
        {
            "role": "assistant",
            "phase": "planning",
            "content": (
                "### Tool call\n"
                "**steps 1**: call `screen_stocks_by_criteria`\n"
                "- `conditions`: `[{\"field\": \"dividend_yield\", \"operator\": \">=\", \"value\": 5}, {\"field\": \"pe_ttm\", \"operator\": \"<=\", \"value\": 15}]`\n"
                "- `limit`: 50\n"
                '- `order_by_field`: "dividend_yield"\n'
                '- `order_direction`: "desc"\n\n'
                "**steps 2**: call `batch_check_profit_consistency`\n"
                "- `years`: 3\n"
                "- `threshold_cv`: 0.3\n"
            ),
        }
    ]

    plan = service._extract_locked_execution_plan(history)

    assert plan is not None
    assert json.loads(plan["screen"]["conditions_json"])[1]["field"] == "pe_ttm"
    assert plan["screen"]["limit"] == 50
    assert plan["screen"]["order_by_field"] == "dividend_yield"
    assert plan["batch"]["years"] == 3
    assert plan["batch"]["threshold_cv"] == 0.3


def test_run_locked_result_execution_uses_locked_plan_arguments(monkeypatch):
    from app.services import intelligent_screening_service as service_module

    service = service_module.IntelligentScreeningService(db=object())
    calls = []

    async def fake_execute_screening_query(raw_conditions, limit, order_by_field, order_direction):
        calls.append(("screen_query", {
            "raw_conditions": raw_conditions,
            "limit": limit,
            "order_by_field": order_by_field,
            "order_direction": order_direction,
        }))
        return [
            {
                "code": "600566",
                "name": "Jichuan Pharmaceutical",
                "industry": "Medicine",
                "dividend_yield": 5.41,
                "pe": 16.28,
                "pe_ttm": 11.88,
                "pb": 2.10,
                "roe": 18.2,
                "debt_to_assets": 24.1,
                "n_cashflow_act": 2.8e9,
                "close": 31.2,
                "report_period": "20250930",
            },
            {
                "code": "601921",
                "name": "Zhejiang version media",
                "industry": "media",
                "dividend_yield": 5.92,
                "pe": 13.40,
                "pe_ttm": 9.56,
                "pb": 1.55,
                "roe": 12.4,
                "debt_to_assets": 21.3,
                "n_cashflow_act": 1.9e9,
                "close": 8.6,
                "report_period": "20250930",
            },
        ], 2

    monkeypatch.setattr(service_module, "_execute_screening_query", fake_execute_screening_query)

    async def fake_batch(**kwargs):
        calls.append(("batch", kwargs))
        return (
            "📊 Summary: stable 1 | Unstable 0 | No data 1\n"
            "✅ Stable stock code:601921\n"
            "⚪ No data stock code:600566"
        )

    service._tool_functions = {
        "batch_check_profit_consistency": fake_batch,
    }

    locked_plan = {
        "planning_content": "Plan approved",
        "screen": {
            "conditions_json": json.dumps([
                {"field": "dividend_yield", "operator": ">=", "value": 5},
                {"field": "pe_ttm", "operator": "<=", "value": 15},
            ], ensure_ascii=False),
            "limit": 50,
            "order_by_field": "dividend_yield",
            "order_direction": "desc",
        },
        "batch": {"years": 3, "threshold_cv": 0.3},
    }

    content, tools_used, stocks = asyncio.run(
        service._run_locked_result_execution("Execute screening plan", locked_plan)
    )

    assert "601921" in content
    assert "PE(TTM)" in content
    assert tools_used == ["screen_stocks_by_criteria", "batch_check_profit_consistency"]
    assert calls[0][0] == "screen_query"
    assert calls[0][1]["raw_conditions"][1]["field"] == "pe_ttm"
    assert calls[1][0] == "batch"
    assert json.loads(calls[1][1]["stock_codes_json"]) == ["600566", "601921"]
    assert len(stocks) == 1
    assert stocks[0]["code"] == "601921"
    assert stocks[0]["pe"] == 9.56
    assert stocks[0]["pe_display_label"] == "PE(TTM)"
    assert stocks[0]["pb_display_label"] == "PB"


def test_locked_result_summary_is_compacted_for_llm():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())
    locked_plan = {
        "screen": {
            "conditions_json": json.dumps([
                {"field": "dividend_yield", "operator": ">=", "value": 4},
                {"field": "pe_ttm", "operator": "<=", "value": 15},
            ], ensure_ascii=False),
            "limit": 50,
            "order_by_field": "dividend_yield",
            "order_direction": "desc",
        },
        "batch": {"years": 3, "threshold_cv": 0.3},
    }
    screening_output = (
        "A total of 37 stocks that met the criteria were found.\n"
        "1. 601919 COSCO Shipping Holdings\n"
        "2. 603565 medium grain flow\n"
        "3. 000915 Walter Dyne\n"
        "4. 002818 Fusenmei\n"
        "5. 300770 New Media Shares\n"
        "6. 002867 Zhou Dasheng\n"
        "Candidate code list (currently sorted, 37 in total): 601919, 603565, 000915, 002818, 300770, 002867"
    )
    batch_output = (
        "A total of 37 stocks have been verified for their earnings stability in the past three years.\n"
        "📊 Summary: 9 stable | Unstable 0 | No data 28 only\n"
        "✅ Stable stock code:601919, 600803, 600096, 600211, 601857, 600066, 603558, 603444, 600377\n"
        "⚪ No data stock code:603565, 000915, 002818, 300770, 002867, 600729, 601928"
    )

    compact_plan = service._build_locked_plan_summary(locked_plan)
    compact_screen = service._compact_screening_output_for_llm(screening_output)
    compact_batch = service._compact_batch_output_for_llm(batch_output)

    assert "planning_content" not in compact_plan
    assert "Candidate code list" not in compact_screen
    assert "The remaining 1 candidate has been omitted" in compact_screen
    assert "⚪ No data stock code" not in compact_batch
    assert "No data stock number: 28" in compact_batch
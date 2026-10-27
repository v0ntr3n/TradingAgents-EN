import asyncio


def test_screening_tool_returns_hard_no_match_message(monkeypatch):
    from core.tools.implementations.market import stock_screening_tool as tool_module

    class DummyScreeningService:
        async def screen_stocks(self, **kwargs):
            return [], 0

    async def fake_init_database():
        return None

    monkeypatch.setattr("app.services.database_screening_service.get_database_screening_service", lambda: DummyScreeningService())
    monkeypatch.setattr("app.core.database.init_database", fake_init_database)

    result = asyncio.run(tool_module._run_screening([], 20, "total_mv", "desc"))

    assert result == "No matching stocks found. There is currently no target that meets the screening requirements. Do not recommend other stocks that do not meet the conditions."


def test_system_prompt_forbids_recommending_other_stocks_on_empty_screening():
    from app.services.intelligent_assistant_service import _get_system_prompt
    from app.services.intelligent_screening_service import IntelligentScreeningService

    prompt = _get_system_prompt()
    confirmation_prompt = IntelligentScreeningService(db=object())._get_system_prompt("confirmation", "")
    screening_prompt = IntelligentScreeningService(db=object())._get_system_prompt("result", "")
    planning_prompt = IntelligentScreeningService(db=object())._get_system_prompt("planning", "Tool list")

    assert "No matching stocks found" in prompt
    assert "strictly prohibited for Give some reference And recommend other stocks that do not meet the screening conditions" in prompt
    assert "If the user uses low valuation  low PE  low PB Such vague valuation descriptions" in confirmation_prompt
    assert "PE Relevant calibers should be distinguished `pe` (PE) and `pe_ttm` (PE(TTM)) " in confirmation_prompt
    assert "PB Relevant calibers should be distinguished `pb` (PB) and `pb_mrq` (PB(MRQ)) " in confirmation_prompt
    assert "The default is to execute at most **Two rounds of data tool calls**" in screening_prompt
    assert "Once enough data is available to generate final recommendations,**Stop calling tools immediately**" in screening_prompt
    assert "Don t just write in general terms PE/PB " in planning_prompt
    assert 'Use `pe_ttm` (PE(TTM)) <= 15' in planning_prompt
    assert 'order_by_field: "pb_mrq"' in planning_prompt


def test_screening_tool_compresses_large_candidate_output(monkeypatch):
    from core.tools.implementations.market import stock_screening_tool as tool_module

    class DummyScreeningService:
        async def screen_stocks(self, **kwargs):
            items = []
            for index in range(12):
                items.append({
                    "code": f"6000{index:02d}",
                    "name": f"Sample stocks{index}",
                    "industry": "bank",
                    "dividend_yield": 4.2 + index * 0.1,
                    "pe": 8.5 + index,
                    "pb": 0.9 + index * 0.05,
                    "roe": 10.0 + index * 0.2,
                    "debt_to_assets": 45.0 + index,
                    "n_cashflow_act": 1.2e9 + index * 1e8,
                    "total_mv": 120.0 + index,
                    "close": 12.3 + index,
                    "pct_chg": 1.5,
                    "report_period": "20241231",
                })
            return items, len(items)

    async def fake_init_database():
        return None

    monkeypatch.setattr("app.services.database_screening_service.get_database_screening_service", lambda: DummyScreeningService())
    monkeypatch.setattr("app.core.database.init_database", fake_init_database)

    result = asyncio.run(tool_module._run_screening([], 20, "dividend_yield", "desc"))

    assert "A total of 12 stocks that meet the criteria were found. The top 8 core candidates are shown below." in result
    assert "Candidate code list (currently sorted, 12 in total)" in result
    assert "600011" in result
    assert "Detailed expansion of the remaining 4 candidates has been omitted." in result
    assert "Gross profit margin=" not in result


def test_screening_tool_uses_pe_ttm_display_when_condition_targets_pe_ttm(monkeypatch):
    from core.tools.implementations.market import stock_screening_tool as tool_module

    class DummyScreeningService:
        async def screen_stocks(self, **kwargs):
            return [
                {
                    "code": "002818",
                    "name": "Fusenmei",
                    "industry": "commercial trade",
                    "dividend_yield": 8.6164,
                    "pe": 16.2629,
                    "pe_ttm": 11.3633,
                    "pb": 1.5115,
                    "roe": 8.4305,
                    "debt_to_assets": 13.4508,
                    "n_cashflow_act": 1019082738.94,
                    "total_mv": 110.0,
                    "report_period": "20250930",
                }
            ], 1

    async def fake_init_database():
        return None

    monkeypatch.setattr("app.services.database_screening_service.get_database_screening_service", lambda: DummyScreeningService())
    monkeypatch.setattr("app.core.database.init_database", fake_init_database)

    result = asyncio.run(
        tool_module._run_screening(
            [{"field": "pe_ttm", "operator": "<=", "value": 15}],
            20,
            "total_mv",
            "desc",
        )
    )

    assert "PE(TTM)=11.36" in result
    assert "PE=16.26" not in result


def test_screening_tool_uses_pb_mrq_display_when_condition_targets_pb_mrq(monkeypatch):
    from core.tools.implementations.market import stock_screening_tool as tool_module

    class DummyScreeningService:
        async def screen_stocks(self, **kwargs):
            return [
                {
                    "code": "600519",
                    "name": "Kweichow Moutai",
                    "industry": "food and beverage",
                    "dividend_yield": 3.15,
                    "pe": 22.8,
                    "pb": 8.4,
                    "pb_mrq": 7.2,
                    "roe": 31.5,
                    "debt_to_assets": 18.2,
                    "n_cashflow_act": 5.8e10,
                    "total_mv": 21000.0,
                    "report_period": "20250930",
                }
            ], 1

    async def fake_init_database():
        return None

    monkeypatch.setattr("app.services.database_screening_service.get_database_screening_service", lambda: DummyScreeningService())
    monkeypatch.setattr("app.core.database.init_database", fake_init_database)

    result = asyncio.run(
        tool_module._run_screening(
            [{"field": "pb_mrq", "operator": "<=", "value": 8}],
            20,
            "total_mv",
            "desc",
        )
    )

    assert "PB(MRQ)=7.20" in result
    assert "PB=8.40" not in result


def test_batch_profit_consistency_compresses_large_output():
    from core.tools.implementations.fundamentals import batch_profit_consistency as tool_module

    codes = [f"6000{i:02d}" for i in range(12)]
    results_map = {
        code: {
            "roe_values": [12.0 + index, 11.5 + index, 11.0 + index],
            "periods": ["20241231", "20231231", "20221231"],
        }
        for index, code in enumerate(codes[:7])
    }
    results_map.update({
        code: {
            "roe_values": [18.0, -2.0, 9.0],
            "periods": ["20241231", "20231231", "20221231"],
        }
        for code in codes[7:10]
    })

    result = tool_module._format_results(codes, results_map, years=3, threshold_cv=0.3)

    assert "📊 Summary: 7 stable | Unstable 3 | No data 2 only" in result
    assert "Stable example:" in result
    assert "Unstable example:" in result
    assert "... Detailed expansion of the remaining 2 has been omitted." in result
    assert "✅ Stable stock code:600000, 600001, 600002" in result
    assert "❌ Unstable stock code:600007, 600008, 600009" in result
    assert "⚪ No data stock code:600010, 600011" in result


def test_batch_profit_consistency_uses_period_collection_pipeline(monkeypatch):
    from core.tools.implementations.fundamentals import batch_profit_consistency as tool_module

    class _AsyncCursor:
        def __init__(self, docs):
            self._docs = docs

        async def __aiter__(self):
            for doc in self._docs:
                yield doc

    class _FakeCollection:
        def __init__(self, docs):
            self._docs = docs
            self.last_pipeline = None

        def aggregate(self, pipeline):
            self.last_pipeline = pipeline
            return _AsyncCursor(self._docs)

    class _FakeDB:
        def __init__(self, period_collection):
            self._period_collection = period_collection

        def __getitem__(self, name: str):
            if name == "stock_financial_periods":
                return self._period_collection
            if name == "stock_financial_data":
                raise AssertionError("should query stock_financial_periods for annual ROE history")
            raise KeyError(name)

    period_collection = _FakeCollection([
        {
            "_id": "600600",
            "roe_list": [15.3681, 15.3778, 16.1220],
            "periods": ["20251231", "20241231", "20231231"],
        }
    ])

    async def _fake_init_database():
        return None

    monkeypatch.setattr("app.core.database.init_database", _fake_init_database)
    monkeypatch.setattr("app.core.database.get_mongo_db", lambda: _FakeDB(period_collection))

    result = asyncio.run(tool_module._async_check(["600600"], years=3, threshold_cv=0.3))

    assert "600600: stable" in result
    assert "last 3 years ROE(2025 / 2024 / 2023): 15.4% / 15.4% / 16.1%" in result
    assert period_collection.last_pipeline is not None
    first_group_stage = next(
        stage["$group"]
        for stage in period_collection.last_pipeline
        if "$group" in stage and isinstance(stage["$group"].get("_id"), dict)
    )
    assert first_group_stage["_id"] == {"code": "$normalized_code", "report_period": "$report_period"}


def test_batch_profit_consistency_treats_insufficient_years_as_no_data():
    from core.tools.implementations.fundamentals import batch_profit_consistency as tool_module

    result = tool_module._format_results(
        ["600600", "600601"],
        {
            "600600": {
                "roe_values": [15.3681],
                "periods": ["20251231"],
            },
            "600601": {
                "roe_values": [12.0, 11.8, 11.6],
                "periods": ["20241231", "20231231", "20221231"],
            },
        },
        years=3,
        threshold_cv=0.3,
    )

    assert "📊 Summary: stable 1 | Unstable 0 | No data 1" in result
    assert "⚪ No data stock code:600600" in result
    assert "600600: stable" not in result


def test_init_database_skips_reinitialization_when_bindings_are_healthy(monkeypatch):
    from app.core import database as database_module

    sentinel_mongo_client = object()
    sentinel_mongo_db = object()
    sentinel_redis_client = object()
    sentinel_redis_pool = object()

    async def fail_init_mongodb():
        raise AssertionError("init_mongodb should not run when healthy bindings already exist")

    async def fail_init_redis():
        raise AssertionError("init_redis should not run when healthy bindings already exist")

    monkeypatch.setattr(database_module, "mongo_client", sentinel_mongo_client)
    monkeypatch.setattr(database_module, "mongo_db", sentinel_mongo_db)
    monkeypatch.setattr(database_module, "redis_client", sentinel_redis_client)
    monkeypatch.setattr(database_module, "redis_pool", sentinel_redis_pool)
    monkeypatch.setattr(database_module.db_manager, "_mongo_healthy", True)
    monkeypatch.setattr(database_module.db_manager, "_redis_healthy", True)
    monkeypatch.setattr(database_module.db_manager, "init_mongodb", fail_init_mongodb)
    monkeypatch.setattr(database_module.db_manager, "init_redis", fail_init_redis)

    asyncio.run(database_module.init_database())

    assert database_module.mongo_client is sentinel_mongo_client
    assert database_module.mongo_db is sentinel_mongo_db
    assert database_module.redis_client is sentinel_redis_client
    assert database_module.redis_pool is sentinel_redis_pool
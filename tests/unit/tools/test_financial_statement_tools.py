"""Fundamental financial reporting tool testing."""

import pandas as pd

from core.agents.config import BUILTIN_AGENTS
from core.tools.implementations.fundamentals import stock_fundamentals as fundamentals_tools
from core.tools.registry import ToolRegistry
from tradingagents.utils.stock_utils import StockUtils


def _mock_financial_payload() -> dict:
    return {
        "ticker": "000001",
        "market_info": {
            "market_name": "China A shares",
            "is_china": True,
        },
        "data_source": "mock_cache",
        "income_statement": [
            {
                "end_date": "20240930",
                "revenue": 12800000000,
                "operate_profit": 2100000000,
                "n_income_attr_p": 1680000000,
                "n_income": 1650000000,
                "basic_eps": 1.23,
            },
            {
                "end_date": "20240630",
                "revenue": 11900000000,
                "operate_profit": 1600000000,
                "n_income_attr_p": 1500000000,
                "n_income": 1480000000,
                "basic_eps": 1.10,
            },
            {
                "end_date": "20240331",
                "revenue": 5200000000,
                "operate_profit": 620000000,
                "n_income_attr_p": 580000000,
                "n_income": 570000000,
                "basic_eps": 0.42,
            },
        ],
        "balance_sheet": [
            {
                "end_date": "20240930",
                "total_assets": 512000000000,
                "total_liab": 468000000000,
                "total_hldr_eqy_exc_min_int": 44000000000,
                "total_cur_assets": 188000000000,
                "total_cur_liab": 320000000000,
                "money_cap": 92000000000,
            }
        ],
        "cash_flow": [
            {
                "end_date": "20240930",
                "n_cashflow_act": 2250000000,
                "n_cashflow_inv_act": -980000000,
                "n_cash_flows_fnc_act": -420000000,
                "c_cash_equ_beg_period": 84500000000,
                "c_cash_equ_end_period": 86200000000,
            }
            ,
            {
                "end_date": "20240630",
                "n_cashflow_act": 1700000000,
                "n_cashflow_inv_act": -630000000,
                "n_cash_flows_fnc_act": -310000000,
                "c_cash_equ_beg_period": 83100000000,
                "c_cash_equ_end_period": 84500000000,
            },
            {
                "end_date": "20240331",
                "n_cashflow_act": 550000000,
                "n_cashflow_inv_act": -210000000,
                "n_cash_flows_fnc_act": -100000000,
                "c_cash_equ_beg_period": 82000000000,
                "c_cash_equ_end_period": 83100000000,
            }
        ],
        "financial_indicators": [
            {
                "end_date": "20240930",
                "roe": 11.6,
                "roa": 0.84,
                "gross_margin": 35.2,
                "netprofit_margin": 12.9,
                "debt_to_assets": 91.4,
                "current_ratio": 0.88,
            }
        ],
    }


def _mock_financial_payload_with_raw_gross_margin_conflict() -> dict:
    payload = _mock_financial_payload()
    payload["financial_indicators"] = [
        {
            "end_date": "20240930",
            "roe": 11.6,
            "roa": 0.84,
            "gross_margin": 139609610.88,
            "grossprofit_margin": 26.8,
            "netprofit_margin": 12.9,
            "debt_to_assets": 91.4,
            "current_ratio": 0.88,
        }
    ]
    return payload


class TestFinancialStatementTools:
    def test_historical_valuation_section_from_frame(self):
        valuation_df = pd.DataFrame([
            {"trade_date": "20240930", "pe": 11.0, "pe_ttm": 10.5, "pb": 1.10, "ps_ttm": 2.10},
            {"trade_date": "20240927", "pe": 10.0, "pe_ttm": 9.8, "pb": 1.00, "ps_ttm": 1.90},
            {"trade_date": "20240926", "pe": 9.0, "pe_ttm": 8.9, "pb": 0.95, "ps_ttm": 1.80},
        ] * 25)

        result = fundamentals_tools._build_historical_valuation_section_from_frame(
            valuation_df,
            window_start="2021-10-01",
            window_end="2024-09-30",
            requested_analysis_date="2024-10-01",
            effective_analysis_date="2024-09-30",
        )

        assert "sample window: 2021-10-01 to 2024-09-30" in result
        assert "There is currently no post-closing daily frequency data required for the valuation analysis of 2024-10-01. This analysis is performed based on the caliber of the previous available trading day, 2024-09-30." in result
        assert "PE(TTM): Current 10.50 times" in result
        assert "PB: Current 1.10 times" in result
        assert "PEG: The current tool does not provide stable daily PEG historical series" in result

    def test_load_recent_financial_data_prefers_db_cache(self, monkeypatch):
        db_payload = _mock_financial_payload()

        class FakeOptimizedProvider:
            def _get_cached_raw_financial_data(self, ticker):
                assert ticker == "000001"
                return db_payload

        class ForbiddenTushareProvider:
            def get_financial_data(self, *args, **kwargs):
                raise AssertionError("should not be called after hitting the database Tushare")

        class ForbiddenAKShareProvider:
            def get_financial_data(self, *args, **kwargs):
                raise AssertionError("should not be called after hitting the database AKShare")

        monkeypatch.setattr(
            "tradingagents.dataflows.optimized_china_data.OptimizedChinaDataProvider",
            FakeOptimizedProvider,
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.providers.china.tushare.TushareProvider",
            ForbiddenTushareProvider,
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.providers.china.akshare.AKShareProvider",
            ForbiddenAKShareProvider,
        )

        result = fundamentals_tools._load_recent_financial_data("000001.SZ", limit=4)

        assert result["ticker"] == "000001"
        assert result["data_source"] == "optimized_cache"
        assert result["income_statement"]
        assert result["cash_flow"]

    def test_stock_utils_supports_a_share_suffixes(self):
        for ticker in ("000001.SZ", "600000.SH", "430001.BJ"):
            market_info = StockUtils.get_market_info(ticker)

            assert market_info["is_china"] is True
            assert market_info["market_name"] == "China A shares"

    def test_tools_registered(self):
        registry = ToolRegistry()

        assert registry.get_function("get_financial_statements") is not None
        assert registry.get_function("get_cash_flow_statement") is not None

    def test_financial_statements_output(self, monkeypatch):
        monkeypatch.setattr(
            fundamentals_tools,
            "_load_recent_financial_data",
            lambda ticker, limit=4: _mock_financial_payload(),
        )

        result = fundamentals_tools.get_financial_statements.invoke({"ticker": "000001", "limit": 4})

        assert "Financial report details for the last three quarters" in result
        assert "2024-09-30" in result
        assert "Income statement (single quarter derivation)" in result
        assert "Income Statement (original reporting period cumulative/snapshot)" in result
        assert "balance sheet" in result
        assert "core financial indicators" in result
        assert "Return on net assets during the reporting period ROE" in result
        assert "Total operating income (single quarter derivation): 9.00 billion" in result
        assert "Net profit attributable to parent company (single quarter derivation): 1.80 billion" in result
        assert "Single quarter net profit margin (derivation): 20.00%" in result

    def test_financial_statements_prefer_grossprofit_margin_over_raw_gross_margin(self, monkeypatch):
        monkeypatch.setattr(
            fundamentals_tools,
            "_load_recent_financial_data",
            lambda ticker, limit=4: _mock_financial_payload_with_raw_gross_margin_conflict(),
        )

        result = fundamentals_tools.get_financial_statements.invoke({"ticker": "000001", "limit": 4})

        assert "Gross profit margin during the reporting period: 26.80%" in result
        assert "139609610.88%" not in result

    def test_financial_statement_tools_prefer_db_loaded_payload(self, monkeypatch):
        captured = []

        def fake_loader(ticker, limit=4):
            captured.append((ticker, limit))
            payload = _mock_financial_payload()
            payload["data_source"] = "optimized_cache"
            return payload

        monkeypatch.setattr(fundamentals_tools, "_load_recent_financial_data", fake_loader)

        financial_result = fundamentals_tools.get_financial_statements.invoke({"ticker": "000001.SZ", "limit": 4})
        cash_flow_result = fundamentals_tools.get_cash_flow_statement.invoke({"ticker": "000001.SZ", "limit": 4})

        assert captured == [("000001.SZ", 5), ("000001.SZ", 5)]
        assert "**Data source**: optimized_cache" in financial_result
        assert "**Data source**: optimized_cache" in cash_flow_result

    def test_cash_flow_output(self, monkeypatch):
        monkeypatch.setattr(
            fundamentals_tools,
            "_load_recent_financial_data",
            lambda ticker, limit=4: _mock_financial_payload(),
        )

        result = fundamentals_tools.get_cash_flow_statement.invoke({"ticker": "000001", "limit": 4})

        assert "cash flow statement" in result
        assert "Net cash flow from operating activities (single quarter derivation): 5.50 billion" in result
        assert "Net cash flow from investing activities (single quarter derivation): -3.50 billion" in result
        assert "Net operating cash in a single quarter/net profit attributable to parent company (derivation): 3.06 times" in result
        assert "Cumulative net operating cash/net profit attributable to parent company during the reporting period" in result

    def test_single_quarter_derivation_helpers(self):
        records_by_period = {
            "20240930": {"revenue": 12800000000, "n_income_attr_p": 1680000000},
            "20240630": {"revenue": 11900000000, "n_income_attr_p": 1500000000},
            "20240331": {"revenue": 5200000000, "n_income_attr_p": 580000000},
        }

        revenue_q3, revenue_status = fundamentals_tools._derive_single_quarter_value(
            "20240930", records_by_period, ["revenue"]
        )
        profit_q1, profit_status = fundamentals_tools._derive_single_quarter_value(
            "20240331", records_by_period, ["n_income_attr_p"]
        )

        assert revenue_status == "derived"
        assert revenue_q3 == 900000000
        assert profit_status == "q1"
        assert profit_q1 == 580000000

    def test_agent_default_tools_binding(self):
        fundamentals_agent = BUILTIN_AGENTS.get("fundamentals_analyst")
        fundamentals_agent_v2 = BUILTIN_AGENTS.get("fundamentals_analyst_v2")

        assert fundamentals_agent is not None
        assert fundamentals_agent_v2 is not None

        for agent in (fundamentals_agent, fundamentals_agent_v2):
            assert "get_financial_statements" in agent.tools
            assert "get_cash_flow_statement" in agent.tools
            assert "get_financial_statements" in agent.default_tools
            assert "get_cash_flow_statement" in agent.default_tools

    def test_unified_fundamentals_unknown_market_does_not_fall_back_to_us(self):
        result = fundamentals_tools.get_stock_fundamentals_unified.invoke({"ticker": "INVALID.CODE"})

        assert "No supported stock market recognized" in result
        assert "U.S. stock fundamentals data" not in result

    def test_unified_fundamentals_prefers_db_snapshot_for_china(self, monkeypatch):
        captured = {}

        class FakeAnalyzer:
            def _generate_fundamentals_report(self, ticker, stock_data, analysis_modules="standard"):
                captured["ticker"] = ticker
                captured["stock_data"] = stock_data
                captured["analysis_modules"] = analysis_modules
                return "## 📊 Basic stock information\n- **Stock code**: 000001\n- **Stock name**: Ping An Bank\n- **current stock price**: 12.34\n- **Total market capitalization**: 1234 billion\n\nmock fundamentals"

        monkeypatch.setattr(
            "tradingagents.dataflows.cache.app_adapter.get_basics_from_cache",
            lambda ticker: {
                "code": ticker,
                "name": "Ping An Bank",
                "area": "Shenzhen",
                "industry": "bank",
                "market": "motherboard",
                "list_date": "19910403",
            },
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.cache.app_adapter.get_market_quote_dataframe",
            lambda ticker: pd.DataFrame([
                {"close": 12.34, "pct_chg": 1.23, "volume": 456789}
            ]),
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.interface.get_china_stock_data_unified",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Should not fall back to the market provider")),
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.optimized_china_data.OptimizedChinaDataProvider",
            FakeAnalyzer,
        )
        monkeypatch.setattr(
            fundamentals_tools,
            "_get_historical_valuation_summary",
            lambda ticker, curr_date, lookback_years=3: (
                "- Last available valuation snapshot date: 2026-04-20\n"
                "- PE(TTM): Current 12.30 times (2026-04-20) | Historical median 10.00 times | historical quantile 70.0% | historical location: High in history"
            ),
        )

        result = fundamentals_tools.get_stock_fundamentals_unified.invoke({"ticker": "000001.SZ"})

        assert "Ping An Bank" in result
        assert "A Basic company information" in result
        assert "A Explanation of stock fundamental analysis caliber" in result
        assert "current price: 12.34" not in result
        assert "Increase or decrease: +1.23%" not in result
        assert "- **current stock price**:" not in result
        assert "- **Total market capitalization**:" not in result
        assert "mock fundamentals" in result
        assert "A Stock historical valuation quantile" in result
        assert "historical quantile 70.0%" in result
        assert "Valuation snapshot caliber" in result
        assert "The valuation snapshot date adopted this time" in result
        assert "Last available valuation snapshot date" in result
        assert captured["ticker"] == "000001"
        assert "Stock code: 000001" in captured["stock_data"]
        assert "current price" not in captured["stock_data"]
        assert captured["analysis_modules"] == "standard"
import asyncio
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _load_module(relative_path: str, module_name: str):
    module_path = ROOT / relative_path
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _make_index_daily_frame(days: int = 260) -> pd.DataFrame:
    rows = []
    for index in range(days):
        close = 3000 + index
        rows.append(
            {
                "trade_date": f"2024{(index // 28) + 1:02d}{(index % 28) + 1:02d}",
                "close": close,
                "high": close + 20,
                "low": close - 20,
                "pct_chg": 0.5,
            }
        )
    return pd.DataFrame(rows)


def test_market_environment_uses_actual_trade_date_and_omits_pe_pb(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_market_environment")

    class FakeProvider:
        async def get_index_dailybasic(self, ts_code: str, trade_date: str) -> pd.DataFrame:
            return pd.DataFrame([
                {"turnover_rate": 1.23, "total_mv": 1_500_000_000_000}
            ])

        async def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
            return _make_index_daily_frame(30)

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_market_environment("2026-04-11"))

    assert "2026-04-10" in report
    assert "PE:" not in report
    assert "PB:" not in report
    assert "20 daily annualized volatility" in report
    assert "medium risk" not in report
    assert "high risk" not in report
    assert "low risk" not in report


def test_market_breadth_omits_activity_labels(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_market_breadth")

    class FakeProvider:
        async def get_daily_info(self, trade_date: str) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"ts_code": "SH_MARKET", "amount": 9567.54, "vol": 250.00, "com_count": 2300},
                    {"ts_code": "SZ_MARKET", "amount": 13678.81, "vol": 296.68, "com_count": 3100},
                ]
            )

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_market_breadth("2026-04-11"))

    assert "Total turnover" in report
    assert "Average turnover per listed company" in report
    assert "market activity" not in report
    assert "Extremely active" not in report


def test_identify_market_cycle_removes_operation_advice(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_market_cycle")

    class FakeProvider:
        async def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
            return _make_index_daily_frame(260)

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.identify_market_cycle("2026-04-11"))

    assert "2026-04-10" in report
    assert "Operation suggestions" not in report
    assert "Does not represent trend confirmation" in report
    assert "Rule recognition interval" in report
    assert "bull market stage" not in report
    assert "bear market stage" not in report
    assert "adjustment stage" not in report


def test_north_flow_uses_actual_trade_date_in_report(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_north_flow")

    class FakeProvider:
        async def get_hsgt_moneyflow(self, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"trade_date": "20260410", "hgt": 120000.0, "sgt": 80000.0},
                    {"trade_date": "20260409", "hgt": 100000.0, "sgt": 60000.0},
                ]
            )

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_north_flow("2026-04-11", lookback_days=10))

    assert "📅 Date: 2026-04-10" in report
    assert "Switched to the most recent trading day 2026-04-10" in report
    assert " [Fund sentiment]" not in report
    assert "Active inflow of foreign capital" not in report


def test_margin_trading_flags_anomalous_change_fields(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_margin_trading")

    class FakeProvider:
        async def get_margin_detail(self, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"trade_date": "20260410", "exchange_id": "SSE", "rzye": 5000.00 * 100000000, "rqye": 40.00 * 100000000, "rzrqye": 5040.00 * 100000000},
                    {"trade_date": "20260410", "exchange_id": "SZSE", "rzye": 7000.00 * 100000000, "rqye": 70.00 * 100000000, "rzrqye": 7070.00 * 100000000},
                    {"trade_date": "20260410", "exchange_id": "BSE", "rzye": 1156.60 * 100000000, "rqye": 14.15 * 100000000, "rzrqye": 1170.75 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "SSE", "rzye": 3500.00 * 100000000, "rqye": 45.00 * 100000000, "rzrqye": 3545.00 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "SZSE", "rzye": 4800.00 * 100000000, "rqye": 60.00 * 100000000, "rzrqye": 4860.00 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "BSE", "rzye": 700.00 * 100000000, "rqye": 15.00 * 100000000, "rzrqye": 715.00 * 100000000},
                    {"trade_date": "20260408", "exchange_id": "SSE", "rzye": 3200.00 * 100000000, "rqye": 40.00 * 100000000, "rzrqye": 3240.00 * 100000000},
                    {"trade_date": "20260408", "exchange_id": "SZSE", "rzye": 4200.00 * 100000000, "rqye": 55.00 * 100000000, "rzrqye": 4255.00 * 100000000},
                    {"trade_date": "20260408", "exchange_id": "BSE", "rzye": 600.00 * 100000000, "rqye": 15.00 * 100000000, "rzrqye": 615.00 * 100000000},
                    {"trade_date": "20260407", "exchange_id": "SSE", "rzye": 2800.00 * 100000000, "rqye": 35.00 * 100000000, "rzrqye": 2835.00 * 100000000},
                    {"trade_date": "20260407", "exchange_id": "SZSE", "rzye": 3600.00 * 100000000, "rqye": 50.00 * 100000000, "rzrqye": 3650.00 * 100000000},
                    {"trade_date": "20260407", "exchange_id": "BSE", "rzye": 600.00 * 100000000, "rqye": 15.00 * 100000000, "rzrqye": 615.00 * 100000000},
                    {"trade_date": "20260406", "exchange_id": "SSE", "rzye": 2400.00 * 100000000, "rqye": 30.00 * 100000000, "rzrqye": 2430.00 * 100000000},
                    {"trade_date": "20260406", "exchange_id": "SZSE", "rzye": 3000.00 * 100000000, "rqye": 45.00 * 100000000, "rzrqye": 3045.00 * 100000000},
                    {"trade_date": "20260406", "exchange_id": "BSE", "rzye": 600.00 * 100000000, "rqye": 15.00 * 100000000, "rzrqye": 615.00 * 100000000},
                ]
            )

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_margin_trading("2026-04-11", lookback_days=10))

    assert "Field consistency check" in report
    assert "Variable fields may have caliber differences or outliers" in report
    assert "We will not extend our interpretation of the leverage direction based on this for now." in report
    assert " [Balance level signal]" not in report
    assert "Financing balance is in a relatively cautious range" not in report
    assert " [Usage restrictions]" in report
    assert "Currently, only the balance value can be quoted, and the direction of funds should not be judged based on the abnormal change field." in report


def test_margin_trading_reports_missing_exchange_coverage(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_margin_trading_incomplete")

    class FakeProvider:
        async def get_margin_detail(self, start_date: str, end_date: str) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"trade_date": "20260410", "exchange_id": "SSE", "rzye": 13156.60 * 100000000, "rqye": 124.15 * 100000000, "rzrqye": 13280.75 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "SSE", "rzye": 13000.00 * 100000000, "rqye": 120.00 * 100000000, "rzrqye": 13120.00 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "SZSE", "rzye": 12000.00 * 100000000, "rqye": 60.00 * 100000000, "rzrqye": 12060.00 * 100000000},
                    {"trade_date": "20260409", "exchange_id": "BSE", "rzye": 902.06 * 100000000, "rqye": 5.05 * 100000000, "rzrqye": 907.11 * 100000000},
                ]
            )

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_margin_trading("2026-04-11", lookback_days=10))

    assert " [Data integrity]" in report
    assert "Data status: incomplete" in report
    assert "Returned to exchange: SSE" in report
    assert "Missing exchange: SZSE, BSE" in report
    assert "The current data only covers some exchanges and does not represent the coverage of the entire A-share market." in report
    assert "This should not be used to judge the balance level, single-day changes or the direction of leveraged funds." in report
    assert "Financing anomaly" not in report
    assert " [Today s balance of financing and financing]" not in report
    assert " [Balance level signal]" not in report


def test_index_technical_returns_rule_tags_without_summary_judgment(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_technical")

    class FakeProvider:
        async def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
            return _make_index_daily_frame(120)

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_index_technical("2026-04-11", lookback_days=60))

    assert " [Indicator rules label]" in report
    assert "Number of upper-biased rule labels" in report
    assert "Number of lower rule labels" in report
    assert "Not equivalent to market conclusion" in report
    assert " [Comprehensive technical aspects]" not in report
    assert "More technical aspects, more characteristics are dominant" not in report
    assert "The technical aspect is bearish, and weak features dominate" not in report
    assert "Technically neutral" not in report
    assert "Indicators are bullish" not in report
    assert "Indicators are bearish" not in report
    assert "Many parties have the upper hand" not in report
    assert "Short side dominates" not in report
    assert "The bottom golden cross is formed" not in report
    assert "High golden cross" not in report


def test_limit_stats_uses_neutral_distribution_wording(monkeypatch) -> None:
    module = _load_module("core/tools/index_tools.py", "index_tools_limit_stats")

    class FakeProvider:
        async def get_daily_stats(self, trade_date: str):
            return {
                "up_count": 3977,
                "up_ratio": 72.4,
                "down_count": 1397,
                "down_ratio": 25.4,
                "flat_count": 121,
                "up_gt5": 244,
                "up_3_5": 324,
                "down_gt5": 55,
                "down_3_5": 111,
            }

        async def get_limit_list(self, trade_date: str) -> pd.DataFrame:
            up_rows = [{"limit": "U", "up_stat": "2"} for _ in range(17)]
            up_rows.extend({"limit": "U", "up_stat": "1"} for _ in range(42))
            down_rows = [{"limit": "D", "up_stat": "0"} for _ in range(8)]
            return pd.DataFrame(up_rows + down_rows)

    async def fake_latest_trade_date(trade_date: str) -> str:
        return "20260410"

    monkeypatch.setattr(module, "_get_tushare_provider", lambda: FakeProvider())
    monkeypatch.setattr(module, "_get_latest_trade_date", fake_latest_trade_date)

    report = asyncio.run(module.get_limit_stats("2026-04-11"))

    assert "The number of stocks with the largest increase was significantly greater than the number of stocks with the largest decrease." in report
    assert "Strong money-making effect" not in report
    assert " [Market Sentiment]" not in report
    assert "extremely optimistic" not in report
    assert "Optimistic" not in report
    assert "tend to be pessimistic" not in report
    assert " [Price limit statistics]" in report
    assert "  • daily limit: 59 home" in report
    assert "  • Limit down: 8 home" in report
    assert "  • Even board: 17 home" in report
    assert " [Price limit statistics (summary caliber)]" not in report
    assert " [Price limit statistics (detailed caliber)]" not in report
    assert " [Summary of caliber differences]" not in report
    assert "Summary caliber" not in report
    assert "Among them, the number of companies with daily limit" not in report
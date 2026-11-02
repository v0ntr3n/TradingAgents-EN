"""Unified DataFrame acquisition with multi-source fallback (Tushare -> AKShare -> BaoStock)."""
from __future__ import annotations

from typing import Any
import pandas as pd


def get_tushare_adapter() -> Any:
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

    return get_tushare_provider()


def get_akshare_provider() -> Any:
    from tradingagents.dataflows.providers.china.akshare import get_akshare_provider as _get_ak

    return _get_ak()


def get_baostock_provider() -> Any:
    from tradingagents.dataflows.providers.china.baostock import get_baostock_provider as _get_bs

    return _get_bs()


def get_data_source_manager() -> Any:
    from tradingagents.dataflows.data_source_manager import get_data_source_manager as _get_dsm

    return _get_dsm()


def _standardize_daily_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.rename(columns={col: str(col).strip().lower() for col in df.columns})
    if "trade_date" in out.columns and "date" not in out.columns:
        out["date"] = out["trade_date"]
    return out


def _resolve_provider_order(dsm: Any) -> list[str]:
    current = getattr(getattr(dsm, "current_source", None), "value", "akshare")
    avail = [getattr(s, "value", str(s)).lower() for s in getattr(dsm, "available_sources", [])]
    candidates = [str(current).lower(), "tushare", "akshare", "baostock"] + avail
    return list(dict.fromkeys(c for c in candidates if c))


def _try_fetch_from_provider(getter: Any, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        provider = getter()
        if hasattr(provider, "get_stock_data"):
            return _standardize_daily_df(provider.get_stock_data(symbol, start_date, end_date))
    except Exception:
        pass
    return pd.DataFrame()


def get_china_daily_df_unified(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch standardized daily China A-share DataFrame with automatic provider fallback."""
    providers = {
        "tushare": get_tushare_adapter,
        "akshare": get_akshare_provider,
        "baostock": get_baostock_provider,
    }
    for src in _resolve_provider_order(get_data_source_manager()):
        getter = providers.get(src)
        if getter is not None:
            df = _try_fetch_from_provider(getter, symbol, start_date, end_date)
            if not df.empty:
                return df
    return pd.DataFrame()

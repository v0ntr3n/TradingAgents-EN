"""
Data source manager that orchestrates multiple adapters with priority and optional consistency checks
"""
from typing import List, Optional, Tuple, Dict
import logging
import time
from datetime import datetime, timedelta
import pandas as pd

from .base import DataSourceAdapter
from .local_adapter import LocalAdapter
from .tushare_adapter import TushareAdapter
from .akshare_adapter import AKShareAdapter
from .baostock_adapter import BaoStockAdapter
from .qmt_adapter import QMTAdapter

logger = logging.getLogger(__name__)


class DataSourceManager:
    """
    Data source manager
    - Manage multiple adapters, sorted based on priority
    - Provide fallback acquisition capabilities
    - Optional: Consistency check (if dependencies exist)
    """

    def __init__(self):
        self._configured_enabled_map: Dict[str, bool] = {}
        self.adapters: List[DataSourceAdapter] = [
            LocalAdapter(),      # Local data source (user imports through API)
            TushareAdapter(),
            AKShareAdapter(),
            BaoStockAdapter(),
            QMTAdapter(),        # Xuntou QMT (QMT is required to run, AKShare is used for news)
        ]

        # Load configuration using unified data source priority module
        self._load_priority_from_unified_config()

        # Sort by priority (larger numbers have higher priority, so sort in descending order)
        self.adapters.sort(key=lambda x: x.priority, reverse=True)

        try:
            from .data_consistency_checker import DataConsistencyChecker  # type: ignore
            self.consistency_checker = DataConsistencyChecker()
        except Exception:
            logger.warning("⚠️ Data consistency checker is unavailable")
            self.consistency_checker = None

    def _load_priority_from_unified_config(self):
        """Use the unified configuration module to load data source priorities"""
        try:
            from app.core.unified_config import UnifiedConfigManager

            config = UnifiedConfigManager()
            data_source_configs = config.get_data_source_configs()

            # Create a name-to-priority mapping
            priority_map = {}
            for ds_config in data_source_configs:
                data_source_name = ds_config.type.lower()
                priority = ds_config.priority
                enabled = ds_config.enabled

                self._configured_enabled_map[data_source_name] = bool(enabled)

                if enabled:
                    priority_map[data_source_name] = priority

            # 🔥 Force .env switch override (.env has the highest priority and ignores database cache)
            self._apply_dotenv_overrides()

            # Update the priority of each Adapter
            for adapter in self.adapters:
                if adapter.name in priority_map:
                    adapter._priority = priority_map[adapter.name]
                else:
                    adapter._priority = adapter._get_default_priority()

        except Exception as e:
            logger.warning(f"⚠️ Loading priorities from unified configuration failed: {e}, Use default priority")
            import traceback
            logger.warning(f"堆栈跟踪:\n{traceback.format_exc()}")
            # Use default priority
            for adapter in self.adapters:
                adapter._priority = adapter._get_default_priority()

    def _apply_dotenv_overrides(self):
        """Force application of data source switches in .env (highest priority)

        Read values explicitly set in .env via Pydantic BaseSettings.
        Multiple keys are arranged in priority, and the first explicitly set value takes effect.
        """
        try:
            from app.core.config import settings as runtime_settings

            # Arranged by priority: the key actually set by the user in .env is placed first
            env_overrides = {
                "baostock": ["BAOSTOCK_UNIFIED_ENABLED", "ENABLE_BAOSTOCK"],
                "tushare": ["ENABLE_TUSHARE"],
            }

            for adapter_name, env_keys in env_overrides.items():
                effective_key = None
                env_val = None

                for key in env_keys:
                    val = getattr(runtime_settings, key, None)

                    # Only overridden when the value is False (disabled).
                    # True It may be the Pydantic default value, do not use the default True to override the database's False.
                    if val is False:
                        env_val = False
                        effective_key = key
                        break

                if effective_key:
                    old_val = self._configured_enabled_map.get(adapter_name)
                    self._configured_enabled_map[adapter_name] = env_val
                    logger.info(f"🔧 [DataSourceManager] .env Disable ({effective_key}): {adapter_name} enabled=False (Original={old_val})")
        except Exception as e:
            logger.warning(f"⚠️ [DataSourceManager] .env Overwrite failed: {e}")

    def get_available_adapters(self) -> List[DataSourceAdapter]:
        available: List[DataSourceAdapter] = []
        for adapter in self.adapters:
            if self._configured_enabled_map.get(adapter.name) is False:
                logger.info(f"Data source {adapter.name} is disabled in unified config, skipping availability probe")
                continue

            if adapter.is_available():
                available.append(adapter)
                logger.info(
                    f"Data source {adapter.name} is available (priority: {adapter.priority})"
                )
            else:
                log_message = f"Data source {adapter.name} is not available"
                if adapter.name == "qmt":
                    logger.info(log_message)
                else:
                    logger.warning(log_message)
        return available

    def get_stock_list_with_fallback(self, preferred_sources: Optional[List[str]] = None, exclude_local: bool = False) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Get a stock list and support specifying priority data sources

        Args:
            preferred_sources: A list of preferred data sources to use, e.g. ['akshare', 'baostock']
                             If None, follow default priority order
            exclude_local: Whether to exclude local data sources (should be set to True during synchronization operations)

        Returns:
            (DataFrame, source_name) or (None, None)
        """
        available_adapters = self.get_available_adapters()

        # Exclude local data sources (for sync operations)
        if exclude_local:
            available_adapters = [a for a in available_adapters if a.name != 'local']
            logger.info("🚫 Exclude local data sources (local) and only use external data sources for synchronization")

        # If a preferred data source is specified, reorder
        if preferred_sources:
            logger.info(f"Using preferred data sources: {preferred_sources}")
            # Create priority mapping
            priority_map = {name: idx for idx, name in enumerate(preferred_sources)}
            # Sort the specified data source first, and keep the others in their original order.
            preferred = [a for a in available_adapters if a.name in priority_map]
            others = [a for a in available_adapters if a.name not in priority_map]
            # Sort by preferred_sources
            preferred.sort(key=lambda a: priority_map.get(a.name, 999))
            available_adapters = preferred + others
            logger.info(f"Reordered adapters: {[a.name for a in available_adapters]}")

        for adapter in available_adapters:
            try:
                adapter_start = time.perf_counter()
                logger.info(f"Trying to fetch stock list from {adapter.name}")
                df = adapter.get_stock_list()
                if df is not None and not df.empty:
                    logger.info(
                        "Stock list fetch succeeded from %s: records=%s elapsed=%.2fs",
                        adapter.name,
                        len(df),
                        time.perf_counter() - adapter_start,
                    )
                    return df, adapter.name
                logger.warning(
                    "Stock list fetch returned empty from %s after %.2fs",
                    adapter.name,
                    time.perf_counter() - adapter_start,
                )
            except Exception as e:
                logger.error(
                    "Failed to fetch stock list from %s after %.2fs: %s",
                    adapter.name,
                    time.perf_counter() - adapter_start,
                    e,
                )
                continue
        return None, None

    def get_daily_basic_with_fallback(self, trade_date: str, preferred_sources: Optional[List[str]] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Obtain daily basic data and support specifying priority data sources

        Args:
            trade_date: transaction date
            preferred_sources: List of preferred data sources to use

        Returns:
            (DataFrame, source_name) or (None, None)
        """
        available_adapters = self.get_available_adapters()

        # If a preferred data source is specified, reorder
        if preferred_sources:
            priority_map = {name: idx for idx, name in enumerate(preferred_sources)}
            preferred = [a for a in available_adapters if a.name in priority_map]
            others = [a for a in available_adapters if a.name not in priority_map]
            preferred.sort(key=lambda a: priority_map.get(a.name, 999))
            available_adapters = preferred + others

        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch daily basic data from {adapter.name}")
                df = adapter.get_daily_basic(trade_date)
                if df is not None and not df.empty:
                    return df, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch daily basic data from {adapter.name}: {e}")
                continue
        return None, None

    def find_latest_trade_date_with_fallback(self, preferred_sources: Optional[List[str]] = None) -> Optional[str]:
        """
        Find the latest transaction date and support specifying priority data sources

        Args:
            preferred_sources: List of preferred data sources to use

        Returns:
            Transaction date string (YYYYMMDD format) or None
        """
        available_adapters = self.get_available_adapters()

        # If a preferred data source is specified, reorder
        if preferred_sources:
            priority_map = {name: idx for idx, name in enumerate(preferred_sources)}
            preferred = [a for a in available_adapters if a.name in priority_map]
            others = [a for a in available_adapters if a.name not in priority_map]
            preferred.sort(key=lambda a: priority_map.get(a.name, 999))
            available_adapters = preferred + others

        for adapter in available_adapters:
            try:
                trade_date = adapter.find_latest_trade_date()
                if trade_date:
                    return trade_date
            except Exception as e:
                logger.error(f"Failed to find trade date from {adapter.name}: {e}")
                continue
        return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    def get_realtime_quotes_with_fallback(self) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Obtain a real-time snapshot of the entire market, try in sequence by adapter priority, and return the first successful result.
        Returns: (quotes_dict, source_name)
        quotes_dict shaped like { '000001': {'close': 10.0, 'pct_chg': 1.2, 'amount': 1.2e8}, ... }
        """
        available_adapters = self.get_available_adapters()
        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch realtime quotes from {adapter.name}")
                data = adapter.get_realtime_quotes()
                if data:
                    return data, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch realtime quotes from {adapter.name}: {e}")
                continue
        return None, None


    def get_daily_basic_with_consistency_check(
        self, trade_date: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[Dict]]:
        """
        Get daily base data using consistency checks

        Returns:
            Tuple[DataFrame, source_name, consistency_report]
        """
        available_adapters = self.get_available_adapters()
        if len(available_adapters) < 2:
            df, source = self.get_daily_basic_with_fallback(trade_date)
            return df, source, None
        primary_adapter = available_adapters[0]
        secondary_adapter = available_adapters[1]
        try:
            logger.info(
                f"🔍 Get data for consistency check: {primary_adapter.name} vs {secondary_adapter.name}"
            )
            primary_data = primary_adapter.get_daily_basic(trade_date)
            secondary_data = secondary_adapter.get_daily_basic(trade_date)
            if primary_data is None or primary_data.empty:
                logger.warning(f"⚠️ 主数据源{primary_adapter.name}失败，使用fallback")
                df, source = self.get_daily_basic_with_fallback(trade_date)
                return df, source, None
            if secondary_data is None or secondary_data.empty:
                logger.warning(f"⚠️ 次数据源{secondary_adapter.name}失败，使用主数据源")
                return primary_data, primary_adapter.name, None
            if self.consistency_checker:
                consistency_result = self.consistency_checker.check_daily_basic_consistency(
                    primary_data,
                    secondary_data,
                    primary_adapter.name,
                    secondary_adapter.name,
                )
                final_data, resolution_strategy = self.consistency_checker.resolve_data_conflicts(
                    primary_data, secondary_data, consistency_result
                )
                consistency_report = {
                    'is_consistent': consistency_result.is_consistent,
                    'confidence_score': consistency_result.confidence_score,
                    'recommended_action': consistency_result.recommended_action,
                    'resolution_strategy': resolution_strategy,
                    'differences': consistency_result.differences,
                    'primary_source': primary_adapter.name,
                    'secondary_source': secondary_adapter.name,
                }
                logger.info(
                    f"📊 数据一致性检查完成: 置信度={consistency_result.confidence_score:.2f}, 策略={consistency_result.recommended_action}"
                )
                return final_data, primary_adapter.name, consistency_report
            else:
                logger.warning("⚠️ Consistency checker is not available, use primary data source")
                return primary_data, primary_adapter.name, None
        except Exception as e:
            logger.error(f"❌ 一致性检查失败: {e}")
            df, source = self.get_daily_basic_with_fallback(trade_date)
            return df, source, None



    def get_kline_with_fallback(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Try to get the K line according to priority and return(items, source)"""
        available_adapters = self.get_available_adapters()
        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch kline from {adapter.name}")
                items = adapter.get_kline(code=code, period=period, limit=limit, adj=adj)
                if items:
                    return items, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch kline from {adapter.name}: {e}")
                continue
        return None, None

    def get_news_with_fallback(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Try to get news and announcements by priority, return(items, source)"""
        available_adapters = self.get_available_adapters()
        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch news from {adapter.name}")
                items = adapter.get_news(code=code, days=days, limit=limit, include_announcements=include_announcements)
                if items:
                    return items, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch news from {adapter.name}: {e}")
                continue
        return None, None

    def get_daily_ohlc_with_fallback(self, code: str, trade_date: str, adj: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Prioritizes attempts to obtain daily OHLC data for a specified date.

        Args:
            code: 6 stock code
            trade_date: Transaction date, format YYYY-MM-DD or YYYYMMDD
            adj: Restoration method,None=Not regaining power,"qfq"=Before regaining power,"hfq"=Restoration of rights later

        Returns:
            (ohlc_dict, source_name) or (None, None)
            ohlc_dict: {"date", "open", "high", "low", "close"}
        """
        available_adapters = self.get_available_adapters()
        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch daily OHLC from {adapter.name} (adj={adj})")
                ohlc = adapter.get_daily_ohlc(code=code, trade_date=trade_date, adj=adj)
                if ohlc:
                    return ohlc, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch daily OHLC from {adapter.name}: {e}")
                continue
        return None, None

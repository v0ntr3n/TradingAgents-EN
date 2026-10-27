"""
Base classes and shared typing for data source adapters
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict
import pandas as pd


class DataSourceAdapter(ABC):
    """数据源适配器基类"""

    def __init__(self):
        self._priority: Optional[int] = None  # Dynamic priority, loaded from database

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""
        raise NotImplementedError

    @property
    def priority(self) -> int:
        """Data source priority (the smaller the number, the higher the priority)"""
        # If there is a dynamically set priority, use the dynamic priority; otherwise use the default priority
        if self._priority is not None:
            return self._priority
        return self._get_default_priority()

    @abstractmethod
    def _get_default_priority(self) -> int:
        """Get the default priority (subclass implementation)"""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        raise NotImplementedError

    @abstractmethod
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        raise NotImplementedError

    @abstractmethod
    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        raise NotImplementedError

    @abstractmethod
    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        raise NotImplementedError

    # Newly added: Real-time snapshot of the entire market (near-real-time price/increase/decrease/transaction volume), the key is a 6-digit code
    @abstractmethod
    def get_realtime_quotes(self) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
        """Return { '000001': {'close': 10.0, 'pct_chg': 1.2, 'amount': 1.2e8}, ... }"""
        raise NotImplementedError

    # Newly added: K-line and news abstract interface
    @abstractmethod
    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """Get the K-line and return the list in chronological order: [{time, open, high, low, close, volume, amount}]"""
        raise NotImplementedError

    @abstractmethod
    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """Get news/announcements, return [{title, source, time, url, type}], type in ['news','announcement']"""
        raise NotImplementedError

    def get_daily_ohlc(self, code: str, trade_date: str, adj: Optional[str] = None) -> Optional[Dict]:
        """
        Obtain daily OHLC data for the specified date (optional re-weighting method).

        Args:
            code: 6 stock code
            trade_date: Transaction date, format YYYY-MM-DD or YYYYMMDD
            adj: Restoration method,None=Not regaining power,"qfq"=Before regaining power,"hfq"=Restoration of rights later

        Returns:
            {"date": str, "open": float, "high": float, "low": float, "close": float} or None
        """
        # Default implementation: get data through get_kline, filter target date
        try:
            # The standardized target date format is YYYY-MM-DD
            target_date = trade_date.replace("-", "") if "-" in trade_date else trade_date
            if len(target_date) == 8:
                target_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"

            # Based on the distance between the target date and today, dynamically calculate the required limit
            # Approximately 250 trading days per year, with a 20% margin reserved
            from datetime import datetime
            try:
                target_dt = datetime.strptime(target_date, "%Y-%m-%d")
                days_diff = (datetime.now() - target_dt).days
                # Minimum 30 trading days, maximum 1500 trading days (approximately 6 years)
                limit = max(30, min(1500, int(days_diff * 250 / 365 * 1.2) + 30))
            except (ValueError, TypeError):
                limit = 120  # Default

            items = self.get_kline(code=code, period="day", limit=limit, adj=adj)
            if not items:
                return None

            for item in items:
                item_date = item.get("time", "")
                # Standardize item date format
                if len(item_date) == 8:
                    item_date = f"{item_date[:4]}-{item_date[4:6]}-{item_date[6:8]}"
                elif len(item_date) > 10:
                    item_date = item_date[:10]  # intercept YYYY-MM-DD

                if item_date == target_date:
                    return {
                        "date": target_date,
                        "open": item.get("open"),
                        "high": item.get("high"),
                        "low": item.get("low"),
                        "close": item.get("close"),
                    }

            return None  # Target date is not in the returned data
        except Exception:
            return None

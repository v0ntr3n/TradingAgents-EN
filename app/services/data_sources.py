from __future__ import annotations
import sys as _sys
__path__ = []
_self_mod = _sys.modules[__name__]
for _sub in ['base', 'akshare_adapter', 'tushare_adapter', 'baostock_adapter', 'qmt_adapter', 'local_adapter', 'data_consistency_checker', 'manager']:
    _sys.modules[f"app.services.data_sources.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === base.py ===
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

# === akshare_adapter.py ===
"""
AKShare data source adapter
"""
from typing import Optional, Dict
import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class AKShareAdapter(DataSourceAdapter):
    """AKShare data source adapter"""

    def __init__(self):
        super().__init__()  # Call parent class initialization

    @property
    def name(self) -> str:
        return "akshare"

    def _get_default_priority(self) -> int:
        return 2  # The larger the number, the higher the priority.

    def is_available(self) -> bool:
        """Check if AKShare is available"""
        try:
            import akshare as ak  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _generate_ts_code(code: str) -> str:
        """Generate ts_code based on the stock code."""
        if not code:
            return ""
        code = str(code).zfill(6)
        # Shanghai Stock Exchange: 60/68 (A shares), 50/51/52/58/56 (ETF/LOF, etc.), 11 (treasury bonds/convertible bonds), 90 (B shares)
        if code.startswith(("60", "68", "90", "50", "51", "52", "58", "56", "11")):
            return f"{code}.SH"
        # Shenzhen Stock Exchange: 00/30 (A shares), 15/16/12 (ETF/LOF/convertible bonds, etc.), 20 (B shares)
        if code.startswith(("00", "30", "20", "15", "16", "12")):
            return f"{code}.SZ"
        if code.startswith(("8", "4", "92")):
            return f"{code}.BJ"
        return f"{code}.SZ"

    @staticmethod
    def _get_market(code: str) -> str:
        """Judge the market based on stock symbols."""
        if not code:
            return ""
        code = str(code).zfill(6)
        if code.startswith("000"):
            return "主板"
        if code.startswith("002"):
            return "中小板"
        if code.startswith("300"):
            return "创业板"
        if code.startswith("60"):
            return "主板"
        if code.startswith("688"):
            return "科创板"
        if code.startswith("8") or code.startswith("92"):
            return "北交所"
        if code.startswith("4"):
            return "新三板"
        return "未知"

    def _normalize_stock_list(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Standardized AKShare stock list structure."""
        if df is None or df.empty:
            return None

        normalized = df.rename(columns={
            "code": "symbol",
            "代码": "symbol",
            "A股代码": "symbol",
            "name": "name",
            "名称": "name",
            "A股简称": "name",
            "所属行业": "industry",
            "A股上市日期": "list_date",
            "板块": "market",
        }).copy()

        if "symbol" not in normalized.columns or "name" not in normalized.columns:
            logger.error(f"AKShare: Unexpected stock list columns: {normalized.columns.tolist()}")
            return None

        normalized["symbol"] = normalized["symbol"].astype(str).str.extract(r"(\d+)", expand=False).fillna("").str.zfill(6)
        normalized = normalized[normalized["symbol"] != ""]
        normalized["name"] = normalized["name"].astype(str).fillna("")
        normalized["ts_code"] = normalized["symbol"].apply(self._generate_ts_code)
        normalized["market"] = normalized.get("market", normalized["symbol"].apply(self._get_market)).fillna("")
        normalized["area"] = normalized.get("area", "")
        normalized["industry"] = normalized.get("industry", "")
        normalized["list_date"] = normalized.get("list_date", "")

        return normalized[["symbol", "name", "ts_code", "area", "industry", "market", "list_date"]]

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """To obtain the stock list, use stock_info_a_code_name first. If failed, fall back to the Oriental Fortune real-time list."""
        if not self.is_available():
            return None
        import akshare as ak

        data_sources = [
            ("stock_info_a_code_name", ak.stock_info_a_code_name),
            ("stock_zh_a_spot_em", ak.stock_zh_a_spot_em),
            ("stock_zh_a_spot", ak.stock_zh_a_spot),
        ]

        for source_name, fetcher in data_sources:
            try:
                logger.info(f"AKShare: Fetching stock list from {source_name}()...")
                df = fetcher()
                normalized = self._normalize_stock_list(df)
                if normalized is not None and not normalized.empty:
                    logger.info(f"AKShare: Successfully fetched {len(normalized)} stocks from {source_name}()")
                    return normalized
                logger.warning(f"AKShare: {source_name}() returned empty or unsupported data")
            except Exception as e:
                logger.warning(
                    f"AKShare: {source_name}() failed with {type(e).__name__}: {e}",
                    exc_info=True,
                )

        logger.error("AKShare: All stock list fetch strategies failed")
        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Get daily basic financial data (quick version)"""
        if not self.is_available():
            return None
        try:
            import akshare as ak  # noqa: F401
            logger.info(f"AKShare: Attempting to get basic financial data for {trade_date}")

            stock_df = self.get_stock_list()
            if stock_df is None or stock_df.empty:
                logger.warning("AKShare: No stock list available")
                return None

            max_stocks = 10
            stock_list = stock_df.head(max_stocks)

            basic_data = []
            processed_count = 0
            import time
            start_time = time.time()
            timeout_seconds = 30

            for _, stock in stock_list.iterrows():
                if time.time() - start_time > timeout_seconds:
                    logger.warning(f"AKShare: Timeout reached, processed {processed_count} stocks")
                    break
                try:
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', '')
                    ts_code = stock.get('ts_code', '')
                    if not symbol:
                        continue
                    info_data = ak.stock_individual_info_em(symbol=symbol)
                    if info_data is not None and not info_data.empty:
                        info_dict = {}
                        for _, row in info_data.iterrows():
                            item = row.get('item', '')
                            value = row.get('value', '')
                            info_dict[item] = value
                        latest_price = self._safe_float(info_dict.get('最新', 0))
                        # 🔥 AKShare of"Total market capitalization"The unit is 10,000 yuan, which needs to be converted into 100 million yuan (consistent with Tushare)
                        total_mv_wan = self._safe_float(info_dict.get('总市值', 0))  # Ten thousand yuan
                        total_mv_yi = total_mv_wan / 10000 if total_mv_wan else None  # Convert to 100 million yuan
                        basic_data.append({
                            'ts_code': ts_code,
                            'trade_date': trade_date,
                            'name': name,
                            'close': latest_price,
                            'total_mv': total_mv_yi,  # 100 million yuan (consistent with Tushare)
                            'turnover_rate': None,
                            'pe': None,
                            'pb': None,
                        })
                        processed_count += 1
                        if processed_count % 5 == 0:
                            logger.debug(f"AKShare: Processed {processed_count} stocks in {time.time() - start_time:.1f}s")
                except Exception as e:
                    logger.debug(f"AKShare: Failed to get data for {symbol}: {e}")
                    continue

            if basic_data:
                df = pd.DataFrame(basic_data)
                logger.info(f"AKShare: Successfully fetched basic data for {trade_date}, {len(df)} records")
                return df
            else:
                logger.warning("AKShare: No basic data collected")
                return None
        except Exception as e:
            logger.error(f"AKShare: Failed to fetch basic data for {trade_date}: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_akshare_cn_symbol(code: str) -> str:
        code6 = str(code).zfill(6)
        if code6.startswith(("60", "68", "90")):
            return f"sh{code6}"
        if code6.startswith(("00", "30", "20")):
            return f"sz{code6}"
        if code6.startswith(("8", "4")):
            return f"bj{code6}"
        return code6

    @staticmethod
    def _get_kline_fallback_window(period: str, limit: int) -> int:
        if period == "week":
            return max(limit * 10, 365)
        if period == "month":
            return max(limit * 35, 1095)
        return max(limit * 4, 180)

    @staticmethod
    def _normalize_kline_frame(df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized = normalized.rename(columns={
            "日期": "date",
            "day": "date",
            "时间": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        })

        if "date" in normalized.columns:
            normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

        for column in ["open", "high", "low", "close", "volume", "amount"]:
            if column in normalized.columns:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

        return normalized

    def _resample_daily_kline(self, df: pd.DataFrame, period: str) -> Optional[pd.DataFrame]:
        normalized = self._normalize_kline_frame(df)
        if "date" not in normalized.columns:
            return None

        normalized = normalized.dropna(subset=["date", "open", "high", "low", "close"])
        if normalized.empty:
            return None

        normalized = normalized.sort_values("date").set_index("date")
        rule = "W-FRI" if period == "week" else "ME"

        aggregation = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if "volume" in normalized.columns:
            aggregation["volume"] = "sum"
        if "amount" in normalized.columns:
            aggregation["amount"] = "sum"

        resampled = normalized.resample(rule).agg(aggregation)
        resampled = resampled.dropna(subset=["open", "high", "low", "close"]).reset_index()
        if resampled.empty:
            return None
        resampled["date"] = resampled["date"].dt.strftime("%Y-%m-%d")
        return resampled

    def _build_kline_items(self, df: pd.DataFrame, period: str, limit: int):
        items = []
        if df is None or getattr(df, 'empty', True):
            return items

        normalized = self._normalize_kline_frame(df)
        if normalized.empty:
            return items

        normalized = normalized.tail(limit)
        for _, row in normalized.iterrows():
            date_value = row.get("date")
            if hasattr(date_value, "strftime"):
                time_value = date_value.strftime("%Y-%m-%d")
            else:
                time_value = str(date_value or "")
            items.append({
                "time": time_value,
                "open": self._safe_float(row.get("open")),
                "high": self._safe_float(row.get("high")),
                "low": self._safe_float(row.get("low")),
                "close": self._safe_float(row.get("close")),
                "volume": self._safe_float(row.get("volume")),
                "amount": self._safe_float(row.get("amount")),
            })
        return items


    def get_realtime_quotes(self, source: str = "eastmoney"):
        """
        Get a real-time snapshot of the entire market and return a dictionary with 6-digit codes as keys

        Args:
            source: data source selection,"eastmoney" (Oriental Fortune) or "sina" (Sina Finance)

        Returns:
            Dict[str, Dict]: {code: {close, pct_chg, amount, ...}}
        """
        if not self.is_available():
            return None

        try:
            import akshare as ak  # type: ignore

            # Select the interface based on the source parameter
            if source == "sina":
                df = ak.stock_zh_a_spot()  # Sina Finance Interface
                logger.info("Use AKShare Sina Finance interface to obtain real-time quotes")
            else:  # Use Oriental Fortune by default
                df = ak.stock_zh_a_spot_em()  # Oriental Wealth Interface
                logger.info("Use AKShare Oriental Wealth Interface to obtain real-time quotes")

            if df is None or getattr(df, "empty", True):
                logger.warning(f"AKShare {source} 返回空数据")
                return None

            # Column names are compatible (the column names of the two interfaces may be different)
            code_col = next((c for c in ["代码", "code", "symbol", "股票代码"] if c in df.columns), None)
            price_col = next((c for c in ["最新价", "现价", "最新价(元)", "price", "最新", "trade"] if c in df.columns), None)
            pct_col = next((c for c in ["涨跌幅", "涨跌幅(%)", "涨幅", "pct_chg", "changepercent"] if c in df.columns), None)
            amount_col = next((c for c in ["成交额", "成交额(元)", "amount", "成交额(万元)", "amount(万元)"] if c in df.columns), None)
            open_col = next((c for c in ["今开", "开盘", "open", "今开(元)"] if c in df.columns), None)
            high_col = next((c for c in ["最高", "high"] if c in df.columns), None)
            low_col = next((c for c in ["最低", "low"] if c in df.columns), None)
            pre_close_col = next((c for c in ["昨收", "昨收(元)", "pre_close", "昨收价", "settlement"] if c in df.columns), None)
            volume_col = next((c for c in ["成交量", "成交量(手)", "volume", "成交量(股)", "vol"] if c in df.columns), None)

            if not code_col or not price_col:
                logger.error(f"AKShare {source} 缺少必要列: code={code_col}, price={price_col}, columns={list(df.columns)}")
                return None

            result: Dict[str, Dict[str, Optional[float]]] = {}
            for _, row in df.iterrows():  # type: ignore
                code_raw = row.get(code_col)
                if not code_raw:
                    continue
                # Standardized ticker: handles exchange prefixes (e.g. sz000001, sh600036) 
                code_str = str(code_raw).strip()

                # If the code length exceeds 6 characters, remove the previous exchange prefix (such as sz, sh) 
                if len(code_str) > 6:
                    # Remove leading non-numeric characters (usually the 2-character exchange code)
                    code_str = ''.join(filter(str.isdigit, code_str))

                # If it is a pure number, remove the leading 0 and pad it to 6 digits.
                if code_str.isdigit():
                    code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
                    code = code_clean.zfill(6)  # Complete to 6 digits
                else:
                    # If it's not purely numeric, try to extract the numeric part
                    code_digits = ''.join(filter(str.isdigit, code_str))
                    if code_digits:
                        code = code_digits.zfill(6)
                    else:
                        # Unable to extract valid code, skip
                        continue

                close = self._safe_float(row.get(price_col))
                pct = self._safe_float(row.get(pct_col)) if pct_col else None
                amt = self._safe_float(row.get(amount_col)) if amount_col else None
                op = self._safe_float(row.get(open_col)) if open_col else None
                hi = self._safe_float(row.get(high_col)) if high_col else None
                lo = self._safe_float(row.get(low_col)) if low_col else None
                pre = self._safe_float(row.get(pre_close_col)) if pre_close_col else None
                vol = self._safe_float(row.get(volume_col)) if volume_col else None

                # 🔥 Log: Record the trading volume returned by AKShare
                if code in ["300750", "000001", "600000"]:  # Only record a few example stocks
                    logger.info(f"📊 [AKShare real time] {code} - volume_col={volume_col}, vol={vol}, amount={amt}")

                result[code] = {
                    "close": close,
                    "pct_chg": pct,
                    "amount": amt,
                    "volume": vol,
                    "open": op,
                    "high": hi,
                    "low": lo,
                    "pre_close": pre
                }

            logger.info(f"✅ AKShare {source} 获取到 {len(result)} 只股票的实时行情")
            return result

        except Exception as e:
            logger.error(f"获取AKShare {source} 实时快照失败: {e}")
            return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """AKShare K-line as fallback. Daily/weekly/monthly retry Tencent and Sina when Eastmoney fails."""
        if not self.is_available():
            return None
        try:
            import akshare as ak
            code6 = str(code).zfill(6)
            if period in ("day", "week", "month"):
                period_map = {"day": "daily", "week": "weekly", "month": "monthly"}
                adjust_map = {None: "", "qfq": "qfq", "hfq": "hfq"}
                symbol = self._get_akshare_cn_symbol(code6)
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=self._get_kline_fallback_window(period, limit))).strftime("%Y%m%d")

                fetchers = [
                    (
                        "eastmoney",
                        lambda: ak.stock_zh_a_hist(
                            symbol=code6,
                            period=period_map[period],
                            adjust=adjust_map.get(adj, "")
                        ),
                        False,
                    ),
                    (
                        "sina",
                        lambda: ak.stock_zh_a_daily(
                            symbol=symbol,
                            start_date=start_date,
                            end_date=end_date,
                            adjust=adjust_map.get(adj, "")
                        ),
                        period != "day",
                    ),
                    (
                        "tencent",
                        lambda: ak.stock_zh_a_hist_tx(
                            symbol=symbol,
                            start_date=start_date,
                            end_date=end_date,
                            adjust=adjust_map.get(adj, "")
                        ),
                        period != "day",
                    ),
                ]

                for source_name, fetcher, needs_resample in fetchers:
                    try:
                        df = fetcher()
                        if df is None or getattr(df, 'empty', True):
                            logger.warning(f"AKShare {source_name} get_kline returned empty for {code6}")
                            continue
                        if needs_resample:
                            df = self._resample_daily_kline(df, period)
                            if df is None or getattr(df, 'empty', True):
                                logger.warning(f"AKShare {source_name} get_kline resample returned empty for {code6}")
                                continue
                        return self._build_kline_items(df, period, limit)
                    except Exception as source_error:
                        logger.warning(f"AKShare {source_name} get_kline failed for {code6}: {source_error}")
                return None
            else:
                # minutes
                per_map = {"5m": "5", "15m": "15", "30m": "30", "60m": "60"}
                if period not in per_map:
                    return None
                df = ak.stock_zh_a_minute(symbol=code6, period=per_map[period], adjust=adj if adj in ("qfq", "hfq") else "")
                if df is None or getattr(df, 'empty', True):
                    return None
                return self._build_kline_items(df, period, limit)
        except Exception as e:
            logger.error(f"AKShare get_kline failed: {e}")
            return None

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """AKShare-based news/announcements fallback"""
        if not self.is_available():
            return None
        try:
            import akshare as ak
            code6 = str(code).zfill(6)
            items = []
            # news
            try:
                dfn = ak.stock_news_em(symbol=code6)
                if dfn is not None and not dfn.empty:
                    for _, row in dfn.head(limit).iterrows():
                        items.append({
                            # AkShare Standardize fields to Chinese column names: news title/article source/release time/news link
                            "title": str(row.get('新闻标题') or row.get('标题') or row.get('title') or ''),
                            "source": str(row.get('文章来源') or row.get('来源') or row.get('source') or 'akshare'),
                            "time": str(row.get('发布时间') or row.get('time') or ''),
                            "url": str(row.get('新闻链接') or row.get('url') or ''),
                            "type": "news",
                        })
            except Exception:
                pass
            # announcements
            try:
                if include_announcements:
                    dfa = ak.stock_announcement_em(symbol=code6)
                    if dfa is not None and not dfa.empty:
                        for _, row in dfa.head(max(0, limit - len(items))).iterrows():
                            items.append({
                                "title": str(row.get('公告标题') or row.get('title') or ''),
                                "source": "akshare",
                                "time": str(row.get('公告时间') or row.get('time') or ''),
                                "url": str(row.get('公告链接') or row.get('url') or ''),
                                "type": "announcement",
                            })
            except Exception:
                pass
            return items if items else None
        except Exception as e:
            logger.error(f"AKShare get_news failed: {e}")
            return None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find latest trading date via Trading Calendar API (with caching)"""
        if not self.is_available():
            return None
        
        # Try to get it from cache first
        try:
            from app.services.trade_date_cache_service import get_trade_date_cache_service
            
            cache_service = get_trade_date_cache_service()
            cached_date = cache_service.get_cached_trade_date_sync("akshare")
            if cached_date:
                logger.debug(f"AKShare: Using cached trade date: {cached_date}")
                return cached_date
        except Exception as e:
            logger.debug(f"AKShare: Cache check failed: {e}, will fetch from API")
        
        # The cache does not exist or has expired. Call the API to obtain it.
        try:
            import akshare as ak
            
            # call tool_trade_date_hist_sina() Get trading calendar
            # Return format: DataFrame, containing one column 'trade_date', The format is 'YYYY-MM-DD'
            df = ak.tool_trade_date_hist_sina()
            
            if df is not None and not df.empty:
                # Get data 1 month ahead of today
                today = datetime.now()
                one_month_ago = today - timedelta(days=30)
                
                # tool_trade_date_hist_sina() The column names returned are 'trade_date'
                if 'trade_date' in df.columns:
                    # Convert date column to datetime type
                    df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
                    
                    # Filter the trading days of the last month
                    mask = (df['trade_date'] >= one_month_ago) & (df['trade_date'] <= today)
                    recent_trading_days = df[mask]
                    
                    latest_date_str = None
                    if not recent_trading_days.empty:
                        # Sort by date, take the last one (latest trading day)
                        recent_trading_days = recent_trading_days.sort_values('trade_date', ascending=False)
                        latest_date = recent_trading_days.iloc[0]['trade_date']
                        
                        # Convert to YYYYMMDD format
                        if isinstance(latest_date, pd.Timestamp):
                            latest_date_str = latest_date.strftime("%Y%m%d")
                        else:
                            latest_date_str = str(latest_date).replace('-', '')[:8]
                        
                        logger.info(f"AKShare: Found latest trade date from calendar: {latest_date_str}")
                    else:
                        # If there is no trading day in the last month, take the last row of the entire DataFrame (the latest trading day)
                        df_sorted = df.sort_values('trade_date', ascending=False)
                        latest_date = df_sorted.iloc[0]['trade_date']
                        if isinstance(latest_date, pd.Timestamp):
                            latest_date_str = latest_date.strftime("%Y%m%d")
                        else:
                            latest_date_str = str(latest_date).replace('-', '')[:8]
                        logger.info(f"AKShare: Found latest trade date from calendar (all data): {latest_date_str}")
                    
                    if latest_date_str:
                        # Save to cache
                        try:
                            from app.services.trade_date_cache_service import get_trade_date_cache_service
                            cache_service = get_trade_date_cache_service()
                            cache_service.set_cached_trade_date_sync("akshare", latest_date_str)
                        except Exception as e:
                            logger.debug(f"AKShare: Failed to cache trade date: {e}")
                        
                        return latest_date_str
            
            # If trading calendar API fails, fall back to yesterday
            logger.warning("AKShare: Trade calendar API failed, using yesterday")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            
            # Save to cache (consistent with success branch, use synchronized method to avoid calling asyncio.run in event loop)
            try:
                from app.services.trade_date_cache_service import get_trade_date_cache_service
                cache_service = get_trade_date_cache_service()
                cache_service.set_cached_trade_date_sync("akshare", yesterday)
            except Exception as e:
                logger.debug(f"AKShare: Failed to cache trade date: {e}")
            
            return yesterday
        except Exception as e:
            logger.error(f"AKShare: Failed to find latest trade date: {e}")
            # Go back to yesterday
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            return yesterday


# === tushare_adapter.py ===
"""
Tushare data source adapter
"""
from typing import Optional, Dict
import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class TushareAdapter(DataSourceAdapter):
    """Tusharedata source adapter"""

    def __init__(self):
        super().__init__()  # Call parent class initialization
        self._provider = None
        self._initialize()

    def _initialize(self):
        """Initialize Tushare provider"""
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            self._provider = get_tushare_provider()
        except Exception as e:
            logger.warning(f"Failed to initialize Tushare provider: {e}")
            self._provider = None

    @property
    def name(self) -> str:
        return "tushare"

    def _get_default_priority(self) -> int:
        return 3  # highest priority (The larger the number, the higher the priority.)  # highest priority

    def get_token_source(self) -> Optional[str]:
        """获取 Token 来源"""
        if self._provider:
            return getattr(self._provider, "token_source", None)
        return None

    def is_available(self) -> bool:
        """Check whether Tushare is available"""
        # If not connected, try to connect
        if self._provider and not getattr(self._provider, "connected", False):
            try:
                self._provider.connect_sync()
            except Exception as e:
                logger.debug(f"Tushare: Auto-connect failed: {e}")

        return (
            self._provider is not None
            and getattr(self._provider, "connected", False)
            and self._provider.api is not None
        )

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """Get stock list"""
        # If not connected, try to connect
        if self._provider and not self.is_available():
            logger.info("Tushare: Provider not connected, attempting to connect...")
            try:
                self._provider.connect_sync()
            except Exception as e:
                logger.warning(f"Tushare: Failed to connect: {e}")

        if not self.is_available():
            logger.warning("Tushare: Provider is not available")
            return None
        try:
            # Synchronization method using TushareProvider
            df = self._provider.get_stock_list_sync()
            if df is not None and not df.empty:
                logger.info(f"Tushare: Successfully fetched {len(df)} stocks")
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch stock list: {e}")
        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Get daily basic financial data"""
        if not self.is_available():
            return None
        try:
            # 🔥 New ps, ps_ttm, total_share, float_share, dv_ratio, dv_ttm Field
            fields = "ts_code,total_mv,circ_mv,pe,pb,ps,turnover_rate,volume_ratio,pe_ttm,pb_mrq,ps_ttm,total_share,float_share,dv_ratio,dv_ttm"
            df = self._provider.api.daily_basic(trade_date=trade_date, fields=fields)
            if df is not None and not df.empty:
                logger.info(
                    f"Tushare: Successfully fetched daily data for {trade_date}, {len(df)} records"
                )
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch daily data for {trade_date}: {e}")
        return None


    def get_realtime_quotes(self):
        """Get full-market near real-time quotes via Tushare rt_k fallback
        Returns dict keyed by 6-digit code: {'000001': {'close': ..., 'pct_chg': ..., 'amount': ...}}
        
        🔥 Disabled: Tushare real-time market interface is managed by the scheduled task run_tushare_realtime_quotes_hourly
        Avoid conflict with the scheduled task of 31 minutes per hour (free users can only call it once per hour)
        """
        # 🔥 Tushare real-time market interface calls have been disabled and are managed by scheduled tasks.
        logger.info("⏸️ Tushare The real-time market interface has been disabled and the call is skipped (managed by scheduled tasks)")
        return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """Get K-line bars using tushare pro_bar
        period: day/week/month/5m/15m/30m/60m
        adj: None/qfq/hfq
        Returns: list of {time, open, high, low, close, volume, amount}
        """
        if not self.is_available():
            return None
        try:
            from tushare.pro.data_pro import pro_bar
        except Exception:
            logger.error("Tushare pro_bar not available")
            return None
        try:
            prov = self._provider
            if prov is None or prov.api is None:
                return None
            # normalize ts_code
            ts_code = prov._normalize_symbol(code) if hasattr(prov, "_normalize_symbol") else code
            # map period -> freq
            freq_map = {
                "day": "D",
                "week": "W",
                "month": "M",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "60m": "60min",
            }
            freq = freq_map.get(period, "D")
            adj_arg = adj if adj in (None, "qfq", "hfq") else None

            # Determine requested fields based on frequency
            # Only trade_date is available for the daily line and above periods, and it is only available for the minute line. trade_time
            if freq in ["5min", "15min", "30min", "60min"]:
                fields = "open,high,low,close,vol,amount,trade_date,trade_time"
            else:
                fields = "open,high,low,close,vol,amount,trade_date"

            df = pro_bar(ts_code=ts_code, api=prov.api, freq=freq, adj=adj_arg, limit=limit, fields=fields)
            if df is None or getattr(df, 'empty', True):
                return None
            # standardize columns
            items = []
            # choose time column
            tcol = 'trade_time' if 'trade_time' in df.columns else 'trade_date' if 'trade_date' in df.columns else None
            if tcol is None:
                logger.error(f'Tushare pro_bar missing time column: {list(df.columns)}')
                return None
            df = df.sort_values(tcol)
            for _, row in df.iterrows():
                tval = row.get(tcol)
                try:
                    # keep as string; if Timestamp, convert
                    time_str = str(tval)
                    items.append({
                        "time": time_str,
                        "open": float(row.get('open')) if row.get('open') is not None else None,
                        "high": float(row.get('high')) if row.get('high') is not None else None,
                        "low": float(row.get('low')) if row.get('low') is not None else None,
                        "close": float(row.get('close')) if row.get('close') is not None else None,
                        "volume": float(row.get('vol')) if row.get('vol') is not None else None,
                        "amount": float(row.get('amount')) if row.get('amount') is not None else None,
                    })
                except Exception:
                    continue
            return items
        except Exception as e:
            logger.error(f"Failed to fetch kline from Tushare: {e}")
            return None

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """Try to fetch news/announcements via tushare pro api if available.
        Returns list of {title, source, time, url, type}
        """
        if not self.is_available():
            return None
        api = self._provider.api if self._provider else None
        if api is None:
            return None
        items = []
        # resolve ts_code and date range
        try:
            ts_code = self._provider._normalize_symbol(code) if hasattr(self._provider, "_normalize_symbol") else code
        except Exception:
            ts_code = code
        try:
            from datetime import datetime, timedelta
            end = datetime.now()
            start = end - timedelta(days=max(1, days))
            start_str = start.strftime('%Y%m%d')
            end_str = end.strftime('%Y%m%d')
        except Exception:
            start_str = end_str = ""
        # Attempt announcements first (if requested)
        try:
            if include_announcements and hasattr(api, 'anns'):
                df_anns = api.anns(ts_code=ts_code, start_date=start_str, end_date=end_str)
                if df_anns is not None and not df_anns.empty:
                    for _, row in df_anns.head(limit).iterrows():
                        items.append({
                            "title": row.get('title') or row.get('ann_title') or '',
                            "source": "tushare",
                            "time": str(row.get('ann_date') or row.get('pub_date') or ''),
                            "url": row.get('url') or row.get('ann_url') or '',
                            "type": "announcement",
                        })
        except Exception:
            pass
        # Attempt news
        try:
            if hasattr(api, 'news'):
                df_news = api.news(ts_code=ts_code, start_date=start_str, end_date=end_str)
                if df_news is not None and not df_news.empty:
                    for _, row in df_news.head(max(0, limit - len(items))).iterrows():
                        items.append({
                            "title": row.get('title') or '',
                            "source": row.get('src') or 'tushare',
                            "time": str(row.get('pub_time') or row.get('pub_date') or ''),
                            "url": row.get('url') or '',
                            "type": "news",
                        })
        except Exception:
            pass
        return items if items else None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find latest trading date via Trading Calendar API (with caching)"""
        if not self.is_available():
            return None
        
        # Try to get it from cache first
        try:
            from app.services.trade_date_cache_service import get_trade_date_cache_service
            
            cache_service = get_trade_date_cache_service()
            cached_date = cache_service.get_cached_trade_date_sync("tushare")
            if cached_date:
                logger.debug(f"Tushare: Using cached trade date: {cached_date}")
                return cached_date
        except Exception as e:
            logger.debug(f"Tushare: Cache check failed: {e}, will fetch from API")
        
        # The cache does not exist or has expired. Call the API to obtain it.
        try:
            api = self._provider.api if self._provider else None
            if api is None:
                return None
            
            # Get a trading calendar 1 month ahead from today
            today = datetime.now()
            end_date = today.strftime("%Y%m%d")
            start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
            
            # Call the trade_cal API to get the trading calendar
            df = api.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty:
                # Filter out trading days (is_open == 1) 
                trading_days = df[df['is_open'] == 1]
                if not trading_days.empty:
                    # Sort by date, take the last one (latest trading day)
                    trading_days = trading_days.sort_values('cal_date', ascending=False)
                    latest_date = str(trading_days.iloc[0]['cal_date'])
                    logger.info(f"Tushare: Found latest trade date from calendar: {latest_date}")
                    
                    # Save to cache
                    try:
                        from app.services.trade_date_cache_service import get_trade_date_cache_service
                        cache_service = get_trade_date_cache_service()
                        cache_service.set_cached_trade_date_sync("tushare", latest_date)
                    except Exception as e:
                        logger.debug(f"Tushare: Failed to cache trade date: {e}")
                    
                    return latest_date
            
            # If the trading calendar API fails, fall back to the original method
            logger.warning("Tushare: Trade calendar API failed, falling back to daily_basic probing")
            for delta in range(0, 10):  # up to 10 days back
                d = (today - timedelta(days=delta)).strftime("%Y%m%d")
                try:
                    db = api.daily_basic(trade_date=d, fields="ts_code,total_mv")
                    if db is not None and not db.empty:
                        logger.info(f"Tushare: Found latest trade date by probing: {d}")
                        
                        # Save to cache
                        try:
                            import asyncio
                            from app.services.trade_date_cache_service import get_trade_date_cache_service
                            cache_service = get_trade_date_cache_service()
                            asyncio.run(cache_service.set_cached_trade_date("tushare", d))
                        except Exception as e:
                            logger.debug(f"Tushare: Failed to cache trade date: {e}")
                        
                        return d
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Tushare: Failed to find latest trade date: {e}")
        return None


# === baostock_adapter.py ===
"""
BaoStock data source adapter
"""
from typing import Optional
import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class BaoStockAdapter(DataSourceAdapter):
    """BaoStockdata source adapter"""

    def __init__(self):
        super().__init__()  # Call parent class initialization

    @property
    def name(self) -> str:
        return "baostock"

    def _get_default_priority(self) -> int:
        return 1  # lowest priority (The larger the number, the higher the priority.)

    def is_available(self) -> bool:
        try:
            import baostock as bs  # noqa: F401
            return True
        except ImportError:
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        if not self.is_available():
            return None
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock: Login failed: {lg.error_msg}")
                return None
            try:
                logger.info("BaoStock: Querying stock basic info...")
                rs = bs.query_stock_basic()
                if rs.error_code != '0':
                    logger.error(f"BaoStock: Query failed: {rs.error_msg}")
                    return None
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                if not data_list:
                    return None
                df = pd.DataFrame(data_list, columns=rs.fields)
                df = df[df['type'] == '1']
                df['symbol'] = df['code'].str.replace(r'^(sh|sz)\.', '', regex=True)
                df['ts_code'] = (
                    df['code'].str.replace('sh.', '').str.replace('sz.', '')
                    + df['code'].str.extract(r'^(sh|sz)\.').iloc[:, 0].str.upper().str.replace('SH', '.SH').str.replace('SZ', '.SZ')
                )
                df['name'] = df['code_name']
                df['area'] = ''

                # Get industry information
                logger.info("BaoStock: Querying stock industry info...")
                industry_rs = bs.query_stock_industry()
                if industry_rs.error_code == '0':
                    industry_list = []
                    while (industry_rs.error_code == '0') & industry_rs.next():
                        industry_list.append(industry_rs.get_row_data())
                    if industry_list:
                        industry_df = pd.DataFrame(industry_list, columns=industry_rs.fields)

                        # Remove the industry coding prefix (e.g. "I65 Software and information technology services industry" -> "Software and information technology services industry") 
                        def clean_industry_name(industry_str):
                            if not industry_str or pd.isna(industry_str):
                                return ''
                            # Use regular expressions to remove the preceding letter and number codes (such as I65, C31, etc.)
                            import re
                            cleaned = re.sub(r'^[A-Z]\d+', '', str(industry_str))
                            return cleaned.strip()

                        industry_df['industry_clean'] = industry_df['industry'].apply(clean_industry_name)

                        # Create an industry mapping dictionary {code: industry_clean}
                        industry_map = dict(zip(industry_df['code'], industry_df['industry_clean']))
                        # Merge industry information into main DataFrame
                        df['industry'] = df['code'].map(industry_map).fillna('')
                        logger.info(f"BaoStock: Successfully mapped industry info for {len(industry_map)} stocks")
                    else:
                        df['industry'] = ''
                        logger.warning("BaoStock: No industry data returned")
                else:
                    df['industry'] = ''
                    logger.warning(f"BaoStock: Failed to query industry info: {industry_rs.error_msg}")

                df['market'] = '\u4e3b\u677f'
                df['list_date'] = ''
                logger.info(f"BaoStock: Successfully fetched {len(df)} stocks")
                return df[['symbol', 'name', 'ts_code', 'area', 'industry', 'market', 'list_date']]
            finally:
                bs.logout()
        except Exception as e:
            logger.error(f"BaoStock: Failed to fetch stock list: {e}")
            return None

    def get_daily_basic(self, trade_date: str, max_stocks: int = None) -> Optional[pd.DataFrame]:
        """
        Get daily basic data (including PE, PB, total market capitalization, etc.)

        Args:
            trade_date: transaction date (YYYYMMDD)
            max_stocks: Maximum number of stocks processed, None means processing all stocks
        """
        if not self.is_available():
            return None
        try:
            import baostock as bs
            logger.info(f"BaoStock: Attempting to get valuation data for {trade_date}")
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock: Login failed: {lg.error_msg}")
                return None
            try:
                logger.info("BaoStock: Querying stock basic info...")
                rs = bs.query_stock_basic()
                if rs.error_code != '0':
                    logger.error(f"BaoStock: Query stock list failed: {rs.error_msg}")
                    return None
                stock_list = []
                while (rs.error_code == '0') & rs.next():
                    stock_list.append(rs.get_row_data())
                if not stock_list:
                    logger.warning("BaoStock: No stocks found")
                    return None

                total_stocks = len([s for s in stock_list if len(s) > 5 and s[4] == '1' and s[5] == '1'])
                logger.info(f"📊 BaoStock: found {total_stocks} Only active stocks, start processing{'All' if max_stocks is None else f'before {max_stocks} only'}...")

                basic_data = []
                processed_count = 0
                failed_count = 0
                for stock in stock_list:
                    if max_stocks and processed_count >= max_stocks:
                        break
                    code = stock[0] if len(stock) > 0 else ''
                    name = stock[1] if len(stock) > 1 else ''
                    stock_type = stock[4] if len(stock) > 4 else '0'
                    status = stock[5] if len(stock) > 5 else '0'
                    if stock_type == '1' and status == '1':
                        try:
                            formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                            # 🔥 Get valuation data and total equity
                            rs_valuation = bs.query_history_k_data_plus(
                                code,
                                "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
                                start_date=formatted_date,
                                end_date=formatted_date,
                                frequency="d",
                                adjustflag="3",
                            )
                            if rs_valuation.error_code == '0':
                                valuation_data = []
                                while (rs_valuation.error_code == '0') & rs_valuation.next():
                                    valuation_data.append(rs_valuation.get_row_data())
                                if valuation_data:
                                    row = valuation_data[0]
                                    symbol = code.replace('sh.', '').replace('sz.', '')
                                    ts_code = f"{symbol}.SH" if code.startswith('sh.') else f"{symbol}.SZ"
                                    pe_ttm = self._safe_float(row[3]) if len(row) > 3 else None
                                    pb_mrq = self._safe_float(row[4]) if len(row) > 4 else None
                                    ps_ttm = self._safe_float(row[5]) if len(row) > 5 else None
                                    pcf_ttm = self._safe_float(row[6]) if len(row) > 6 else None
                                    close_price = self._safe_float(row[2]) if len(row) > 2 else None

                                    # 🔥 BaoStock Do not directly provide total market capitalization and total share capital
                                    # In order to avoid synchronization timeout, no additional API is called here to obtain the total equity
                                    # total_mv Leave it blank, you can add it later through other data sources.
                                    total_mv = None

                                    basic_data.append({
                                        'ts_code': ts_code,
                                        'trade_date': trade_date,
                                        'name': name,
                                        'pe': pe_ttm,  # 🔥 Price to Earnings Ratio (TTM)
                                        'pb': pb_mrq,  # 🔥 Price to Book Ratio (MRQ)
                                        'ps': ps_ttm,  # price to sales ratio
                                        'pcf': pcf_ttm,  # price to cash ratio
                                        'close': close_price,
                                        'total_mv': total_mv,  # ⚠️ BaoStock Not provided, leave blank
                                        'turnover_rate': None,  # ⚠️ BaoStock Not available
                                    })
                                    processed_count += 1

                                    # 🔥 Output a progress log every time 50 stocks are processed
                                    if processed_count % 50 == 0:
                                        progress_pct = (processed_count / total_stocks) * 100
                                        logger.info(f"📈 BaoStock 同步进度: {processed_count}/{total_stocks} ({progress_pct:.1f}%) - 最新: {name}({ts_code})")
                                else:
                                    failed_count += 1
                            else:
                                failed_count += 1
                        except Exception as e:
                            failed_count += 1
                            if failed_count % 50 == 0:
                                logger.warning(f"⚠️ BaoStock: 已有 {failed_count} 只股票获取失败")
                            logger.debug(f"BaoStock: Failed to get valuation for {code}: {e}")
                            continue
                if basic_data:
                    df = pd.DataFrame(basic_data)
                    logger.info(f"✅ BaoStock Synchronization completed: success {len(df)} Only, failed {failed_count} only, date {trade_date}")
                    return df
                else:
                    logger.warning(f"⚠️ BaoStock: 未获取到任何估值数据（失败 {failed_count} 只）")
                    return None
            finally:
                bs.logout()
        except Exception as e:
            logger.error(f"BaoStock: Failed to fetch valuation data for {trade_date}: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None


    def get_realtime_quotes(self):
        """Placeholder: BaoStock does not provide full-market realtime snapshot in our adapter.
        Return None to allow fallback to higher-priority sources.
        """
        if not self.is_available():
            return None
        return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """BaoStock not used for K-line here; return None to allow fallback"""
        if not self.is_available():
            return None
        return None

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """BaoStock does not provide news in this adapter; return None"""
        if not self.is_available():
            return None
        return None

        """Placeholder: BaoStock  does not provide full-market realtime snapshot in our adapter.
        Return None to allow fallback to higher-priority sources.
        """

    def find_latest_trade_date(self) -> Optional[str]:
        """Find latest trading date via Trading Calendar API (with caching)"""
        if not self.is_available():
            return None
        
        # Try to get it from cache first
        try:
            from app.services.trade_date_cache_service import get_trade_date_cache_service
            
            cache_service = get_trade_date_cache_service()
            cached_date = cache_service.get_cached_trade_date_sync("baostock")
            if cached_date:
                logger.debug(f"BaoStock: Using cached trade date: {cached_date}")
                return cached_date
        except Exception as e:
            logger.debug(f"BaoStock: Cache check failed: {e}, will fetch from API")
        
        # The cache does not exist or has expired. Call the API to obtain it.
        try:
            import baostock as bs
            
            # Login BaoStock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock: Login failed: {lg.error_msg}")
                bs.logout()
                return None
            
            try:
                # Get a trading calendar 1 month ahead from today
                today = datetime.now()
                end_date = today.strftime("%Y-%m-%d")
                start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                
                # Call query_trade_dates API to get the trading calendar
                rs = bs.query_trade_dates(start_date=start_date, end_date=end_date)
                
                if rs.error_code == '0':
                    # Convert the result to DataFrame
                    data_list = []
                    while (rs.error_code == '0') & rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        # Create DataFrame
                        df = pd.DataFrame(data_list, columns=rs.fields)
                        
                        # Filter out trading days (is_trading_day == '1') 
                        trading_days = df[df['is_trading_day'] == '1']
                        
                        if not trading_days.empty:
                            # Sort by date, take the last one (latest trading day)
                            trading_days = trading_days.sort_values('calendar_date', ascending=False)
                            latest_date_str = trading_days.iloc[0]['calendar_date']
                            
                            # Convert to YYYYMMDD format
                            latest_date = latest_date_str.replace('-', '')
                            logger.info(f"BaoStock: Found latest trade date from calendar: {latest_date}")
                            
                            # Save to cache
                            try:
                                from app.services.trade_date_cache_service import get_trade_date_cache_service
                                cache_service = get_trade_date_cache_service()
                                cache_service.set_cached_trade_date_sync("baostock", latest_date)
                            except Exception as e:
                                logger.debug(f"BaoStock: Failed to cache trade date: {e}")
                            
                            return latest_date
                
                # If trading calendar API fails, fall back to yesterday
                logger.warning(f"BaoStock: Trade calendar API failed: {rs.error_msg}")
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
                
                # Save to cache
                try:
                    import asyncio
                    from app.services.trade_date_cache_service import get_trade_date_cache_service
                    cache_service = get_trade_date_cache_service()
                    asyncio.run(cache_service.set_cached_trade_date("baostock", yesterday))
                except Exception as e:
                    logger.debug(f"BaoStock: Failed to cache trade date: {e}")
                
                return yesterday
            finally:
                bs.logout()
        except Exception as e:
            logger.error(f"BaoStock: Failed to find latest trade date: {e}")
            # Go back to yesterday
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            return yesterday


# === qmt_adapter.py ===
"""
QMT (Xuntou QMT trading terminal) data source adapter

Connect to the local QMT trading terminal through xtquant.xtdata to obtain market data, and pass xtquant.xttrader
Provides read-only position/asset query capabilities.
Prerequisites:
    1. QMT The trading terminal needs to be started (only supported by Windows)
    2. Obtaining market data does not require logging into a brokerage account
    3. Position/asset query requires that the brokerage account has been logged in to the QMT trading terminal (this adapter does not provide the ability to place orders)
News is not supported and the AKShare data source is used uniformly.
"""
from typing import Optional, Dict, List, Any, Tuple
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

# xtquant Optional dependency, the adapter is unavailable when not installed
_xtdata = None
_xtdatacenter = None
_xttrader = None


def _iter_qmt_root_candidates() -> List[Path]:
    """Collect QMT installation root path candidates for automatic discovery of xtquant packages."""
    raw_candidates: List[Path] = []
    configured = os.getenv("QMT_DATA_DIR", "")
    if configured:
        raw_candidates.append(Path(configured).expanduser())

    raw_candidates.extend([
        Path(r"D:\gjzq\bin.x64"),
        Path(r"D:\gjzq"),
        Path(r"C:\gjzq\bin.x64"),
        Path(r"C:\gjzq"),
    ])

    seen: set[str] = set()
    roots: List[Path] = []
    for base in raw_candidates:
        for candidate in (base, base.parent, base.parent.parent):
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if not resolved.exists():
                continue
            key = str(resolved).lower()
            if key in seen:
                continue
            seen.add(key)
            roots.append(resolved)
    return roots


def _ensure_qmt_python_path() -> Optional[str]:
    """Add QMT s own xtquant/site-packages to sys.path."""
    for root in _iter_qmt_root_candidates():
        for site_packages in (
            root / "Lib" / "site-packages",
            root / "bin.x64" / "Lib" / "site-packages",
        ):
            xtquant_dir = site_packages / "xtquant"
            if not xtquant_dir.is_dir():
                continue

            site_packages_str = str(site_packages)
            if site_packages_str not in sys.path:
                sys.path.insert(0, site_packages_str)
                logger.info("QMT: xtquant path added %s", site_packages_str)
            return site_packages_str
    return None


def _get_xtdata():
    """Delayed import xtquant.xtdata"""
    global _xtdata
    if _xtdata is None:
        try:
            _ensure_qmt_python_path()
            import xtquant.xtdata as xt  # type: ignore
            _xtdata = xt
        except ImportError:
            logger.debug("xtquant Not installed, QMT adapter is not available")
            return None
    return _xtdata


def _get_xtdatacenter():
    """Delayed import xtquant.xtdatacenter"""
    global _xtdatacenter
    if _xtdatacenter is None:
        try:
            _ensure_qmt_python_path()
            from xtquant import xtdatacenter as xtdc  # type: ignore
            _xtdatacenter = xtdc
        except ImportError:
            logger.debug("xtquant.xtdatacenter Not installed, skip QMT active initialization")
            return None
    return _xtdatacenter


def _get_xttrader():
    """Delayed import xtquant.xttrader"""
    global _xttrader
    if _xttrader is None:
        try:
            _ensure_qmt_python_path()
            from xtquant import xttrader as xtt  # type: ignore
            _xttrader = xtt
        except ImportError:
            logger.debug("xtquant.xttrader Not installed, skip QMT position query")
            return None
    return _xttrader


def _normalize_code(code: str) -> str:
    """Convert 6-digit code to xtdata format:000001.SZ / 600000.SH"""
    raw_code = str(code).strip().upper()
    if raw_code.endswith((".SH", ".SZ", ".BJ")):
        suffix = raw_code[-3:]
        digits = "".join(filter(str.isdigit, raw_code[:-3])).zfill(6)
        if len(digits) == 6:
            return f"{digits}{suffix}"

    code = raw_code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    code = "".join(filter(str.isdigit, code)).zfill(6)
    if not code or len(code) != 6:
        return ""
    if code.startswith(("50", "51", "52", "56", "58")):
        return f"{code}.SH"
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20", "15", "16", "18")):
        return f"{code}.SZ"
    if code.startswith(("8", "4", "92")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _code_to_6digit(xt_code: str) -> str:
    """xtdata Convert code to 6-digit pure number"""
    s = str(xt_code).split(".")[0]
    return "".join(filter(str.isdigit, s)).zfill(6)


class QMTAdapter(DataSourceAdapter):
    """QMT Data source adapter (requires QMT trading terminal to run, AKShare for news)"""

    _UNAVAILABLE_CACHE_UNTIL = 0.0
    _AVAILABLE_CACHE_UNTIL = 0.0
    _AVAILABILITY_PROBE_UNTIL = 0.0
    _UNAVAILABLE_CACHE_SECONDS = 30.0
    _AVAILABLE_CACHE_SECONDS = 10.0
    _PROBE_GUARD_SECONDS = 5.0

    def __init__(self):
        super().__init__()
        self._available: Optional[bool] = None
        self._bootstrapped = False
        self._sector_data_prepared = False
        # Data quality statistics
        self._quality_stats: Dict[str, Any] = {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "last_error": None,
            "last_error_time": None,
            "by_method": {},
        }

    @property
    def name(self) -> str:
        return "qmt"

    def _get_default_priority(self) -> int:
        return 2  # Same level as AKShare, the larger the number, the higher the priority.

    def _safe_float(self, value) -> Optional[float]:
        try:
            if value is None or value == "" or (hasattr(value, "__float__") and str(value) == "nan"):
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value) -> Optional[int]:
        try:
            if value is None or value == "" or (hasattr(value, "__int__") and str(value) == "nan"):
                return None
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _resolve_qmt_userdata_dir(self) -> Optional[str]:
        """Parse QMT userdata directory for xttrader read-only queries."""
        raw_candidates: List[Path] = []
        configured = self._get_runtime_setting("QMT_DATA_DIR", "")
        if configured:
            raw_candidates.append(Path(str(configured)).expanduser())

        raw_candidates.extend([
            Path(r"D:\gjzq\userdata"),
            Path(r"D:\gjzq\userdata_mini"),
            Path(r"D:\gjzq\bin.x64"),
            Path(r"D:\gjzq"),
            Path(r"C:\gjzq\userdata"),
            Path(r"C:\gjzq\userdata_mini"),
            Path(r"C:\gjzq\bin.x64"),
            Path(r"C:\gjzq"),
        ])

        seen: set[str] = set()
        for base in raw_candidates:
            for candidate in (
                base,
                base.parent,
                base.parent.parent,
            ):
                try:
                    resolved = candidate.resolve()
                except Exception:
                    continue
                if not resolved.exists():
                    continue
                key = str(resolved).lower()
                if key in seen:
                    continue
                seen.add(key)

                if resolved.name.lower() in {"userdata", "userdata_mini"}:
                    return str(resolved)

                for child_name in ("userdata", "userdata_mini"):
                    child = resolved / child_name
                    if child.is_dir():
                        return str(child)

        return None

    def _get_runtime_setting(self, name: str, default: Any = None) -> Any:
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value

        try:
            from app.core.config import settings as app_settings
            return getattr(app_settings, name)
        except Exception:
            return default

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _parse_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raw = str(value).replace(";", ",").replace("\n", ",")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _parse_port_range(self, value: Any) -> Optional[Tuple[int, int]]:
        if value is None or value == "":
            return None
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return int(value[0]), int(value[1])
            except (TypeError, ValueError):
                return None

        text = str(value).strip()
        delimiter = "-" if "-" in text else "," if "," in text else None
        if not delimiter:
            return None
        parts = [part.strip() for part in text.split(delimiter) if part.strip()]
        if len(parts) != 2:
            return None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    def query_account_snapshot(self, account_id: str, account_type: str = "STOCK") -> Optional[Dict[str, Any]]:
        """Read-only query QMT account snapshot, return position DataFrame and account asset summary."""
        account_id = str(account_id or "").strip()
        if not account_id:
            logger.warning("QMT: The account number is empty and the account snapshot cannot be queried.")
            return None

        xttrader = _get_xttrader()
        if xttrader is None:
            logger.warning("QMT: xttrader Unavailable, unable to query account snapshot")
            return None

        userdata_dir = self._resolve_qmt_userdata_dir()
        if not userdata_dir:
            logger.warning("QMT: The userdata directory was not found and the account snapshot could not be queried.")
            return None

        try:
            from xtquant.xttype import StockAccount  # type: ignore
        except ImportError:
            logger.warning("QMT: xttype Unavailable, cannot build account object")
            return None

        trader = None
        try:
            session = int(time.time() * 1000) % 2147483647
            trader = xttrader.XtQuantTrader(userdata_dir, session)
            trader.start()
            connect_result = trader.connect()
            if connect_result != 0:
                logger.warning("QMT: Trading client connection failed, return code=%s", connect_result)
                return None

            account = StockAccount(account_id, account_type)
            positions = trader.query_stock_positions(account) or []
            asset = trader.query_stock_asset(account)
            xt = _get_xtdata()

            rows: List[Dict[str, Any]] = []
            for item in positions:
                stock_code = getattr(item, "stock_code", "") or getattr(item, "m_strStockCode", "")
                code6 = _code_to_6digit(stock_code)
                volume = self._safe_int(getattr(item, "volume", None))
                if not code6 or volume is None or volume <= 0:
                    continue

                can_use_volume = self._safe_int(getattr(item, "can_use_volume", None))
                open_price = self._safe_float(getattr(item, "open_price", None))
                market_value = self._safe_float(getattr(item, "market_value", None))
                frozen_volume = self._safe_int(getattr(item, "frozen_volume", None))
                on_road_volume = self._safe_int(getattr(item, "on_road_volume", None))
                yesterday_volume = self._safe_int(getattr(item, "yesterday_volume", None))

                xt_code = _normalize_code(code6)
                name = code6
                if xt is not None and xt_code:
                    try:
                        name = self._get_instrument_name(xt, xt_code, code6)
                    except Exception:
                        name = code6

                notes = f"QMT Position import | Account {account_id}"
                if can_use_volume is not None and can_use_volume != volume:
                    notes += f" | 可用 {can_use_volume}"
                if frozen_volume is not None and frozen_volume > 0:
                    notes += f" | 冻结 {frozen_volume}"
                if on_road_volume is not None and on_road_volume > 0:
                    notes += f" | 在途 {on_road_volume}"
                if yesterday_volume is not None and yesterday_volume > 0:
                    notes += f" | 昨仓 {yesterday_volume}"

                rows.append({
                    "code": code6,
                    "name": name,
                    "market": "CN",
                    "currency": "CNY",
                    "quantity": volume,
                    "cost_price": round(open_price, 4) if open_price is not None else 0.0,
                    "buy_date": None,
                    "notes": notes,
                    "qmt_stock_code": stock_code,
                    "can_use_quantity": can_use_volume,
                    "market_value": market_value,
                    "frozen_volume": frozen_volume,
                    "on_road_volume": on_road_volume,
                    "yesterday_volume": yesterday_volume,
                })

            columns = [
                "code", "name", "market", "currency", "quantity", "cost_price",
                "buy_date", "notes", "qmt_stock_code", "can_use_quantity",
                "market_value", "frozen_volume", "on_road_volume", "yesterday_volume",
            ]
            df = pd.DataFrame(rows, columns=columns)

            market_value_total = 0.0
            if not df.empty and "market_value" in df.columns:
                market_value_total = float(df["market_value"].fillna(0).sum())

            asset_cash = self._safe_float(getattr(asset, "cash", None)) if asset is not None else None
            asset_frozen_cash = self._safe_float(getattr(asset, "frozen_cash", None)) if asset is not None else None
            asset_market_value = self._safe_float(getattr(asset, "market_value", None)) if asset is not None else None
            asset_total_asset = self._safe_float(getattr(asset, "total_asset", None)) if asset is not None else None

            if asset_market_value is None:
                asset_market_value = round(market_value_total, 2)
            if asset_total_asset is None and asset_cash is not None:
                asset_total_asset = round(asset_cash + (asset_market_value or 0.0), 2)

            asset_summary = {
                "cash": asset_cash,
                "frozen_cash": asset_frozen_cash,
                "market_value": asset_market_value,
                "total_asset": asset_total_asset,
            }

            if asset is not None:
                logger.info(
                    "QMT: Position inquiry completed, account=%s, Position=%s Cash only=%s, total assets=%s",
                    account_id,
                    len(df),
                    getattr(asset, "cash", None),
                    getattr(asset, "total_asset", None),
                )
            else:
                logger.info("QMT: Position inquiry completed, account=%s, Position=%s only", account_id, len(df))

            return {
                "account_id": account_id,
                "account_type": account_type,
                "positions_df": df,
                "asset": asset_summary,
            }
        except Exception as e:
            logger.error(f"QMT: Failed to query account snapshot: {e}")
            return None
        finally:
            if trader is not None:
                try:
                    trader.stop()
                except Exception:
                    pass

    def query_account_positions(self, account_id: str, account_type: str = "STOCK") -> Optional[pd.DataFrame]:
        """Read-only query QMT account positions and return a DataFrame that can be imported into the positions."""
        snapshot = self.query_account_snapshot(account_id, account_type)
        if snapshot is None:
            return None
        return snapshot.get("positions_df")

    def _has_existing_connection(self, xt: Any) -> bool:
        """Prioritize reusing started QMT connections to avoid default configuration accidentally triggering independent initialization."""
        if xt is None:
            return False
        try:
            ticks = xt.get_full_tick([])
            if ticks is not None:
                self._available = True
                return True
            # get_full_tick([]) May return an empty dict, also considered available
            self._available = True
            return True
        except Exception:
            return False

    def _should_initialize_connection(
        self,
        token: str,
        optimize_addresses: List[str],
        mirror_markets: List[str],
        mirror_enabled: bool,
        start_local_service: bool,
        listen_port: Any,
    ) -> bool:
        """Perform xtdatacenter active initialization only in explicit independent connection scenarios."""
        try:
            parsed_port = int(listen_port or 0)
        except (TypeError, ValueError):
            parsed_port = 0

        return any(
            [
                bool(token),
                bool(optimize_addresses),
                bool(mirror_markets),
                bool(mirror_enabled),
                bool(start_local_service),
                parsed_port > 0,
            ]
        )

    def _bootstrap_connection(self) -> None:
        if self._bootstrapped:
            return

        self._bootstrapped = True

        xt = _get_xtdata()
        xtdc = _get_xtdatacenter()
        if xt is None or xtdc is None:
            return

        data_dir = self._get_runtime_setting("QMT_DATA_DIR", "")
        token = self._get_runtime_setting("QMT_TOKEN", "")
        init_markets = self._parse_list(self._get_runtime_setting("QMT_INIT_MARKETS", ""))
        optimize_addresses = self._parse_list(self._get_runtime_setting("QMT_ALLOW_OPTIMIZE_ADDRESSES", ""))
        mirror_markets = self._parse_list(self._get_runtime_setting("QMT_KLINE_MIRROR_MARKETS", ""))
        mirror_enabled = self._parse_bool(self._get_runtime_setting("QMT_KLINE_MIRROR_ENABLED", False))
        start_local_service = self._parse_bool(self._get_runtime_setting("QMT_START_LOCAL_SERVICE", False))
        listen_port = self._get_runtime_setting("QMT_LISTEN_PORT", 0)
        listen_port_range = self._parse_port_range(self._get_runtime_setting("QMT_LISTEN_PORT_RANGE", "58620-58650"))

        if self._has_existing_connection(xt):
            logger.info("QMT: Existing QMT connection detected, active initialization skipped")
            return

        should_initialize = self._should_initialize_connection(
            token=token,
            optimize_addresses=optimize_addresses,
            mirror_markets=mirror_markets,
            mirror_enabled=mirror_enabled,
            start_local_service=start_local_service,
            listen_port=listen_port,
        )
        if not should_initialize:
            logger.info(
                "QMT: No existing QMT connection detected and default QMT mode is currently in place,"
                "Skip xtdatacenter active initialization, please start and keep the QMT trading terminal running first"
            )
            return

        try:
            if data_dir:
                xtdc.set_data_home_dir(str(data_dir))
            if token:
                xtdc.set_token(str(token))
            if optimize_addresses:
                xtdc.set_allow_optmize_address(optimize_addresses)
            if mirror_markets:
                xtdc.set_kline_mirror_markets(mirror_markets)
            elif mirror_enabled:
                xtdc.set_kline_mirror_enabled(True)
            if init_markets:
                xtdc.set_init_markets(init_markets)

            xtdc.init(start_local_service=start_local_service)

            port = 0
            try:
                port = int(listen_port or 0)
            except (TypeError, ValueError):
                port = 0

            if port > 0:
                listen_result = xtdc.listen(port=port)
            elif listen_port_range:
                listen_result = xtdc.listen(port=listen_port_range)
            else:
                listen_result = xtdc.listen(port=(58620, 58650))

            if isinstance(listen_result, tuple):
                connect_port = int(listen_result[-1])
            else:
                connect_port = int(listen_result)

            xt.connect(port=connect_port)
            logger.info(f"QMT: The connection has been initialized according to the configuration, port {connect_port}")
        except Exception as e:
            logger.warning(f"QMT: If the active initialization of the connection fails, it will fall back to the existing QMT connection.: {e}")

    def _prepare_sector_data(self) -> None:
        if self._sector_data_prepared:
            return

        # By default, sector data is not automatically downloaded to avoid xt.download_sector_data / download_history_data2 from getting stuck.
        if self._parse_bool(self._get_runtime_setting("QMT_AUTO_DOWNLOAD_SECTOR", False)):
            xt = _get_xtdata()
            if xt is None:
                self._sector_data_prepared = True
                return

            try:
                logger.info("QMT: Downloading section data (closed by default)")
                xt.download_sector_data()
            except Exception as e:
                logger.debug(f"QMT: Failed to download section data, will continue to try to read the local cache: {e}")
            finally:
                self._sector_data_prepared = True
        else:
            self._sector_data_prepared = True

    def _download_history_if_needed(self, xt_code: str, xt_period: str) -> None:
        if not self._parse_bool(self._get_runtime_setting("QMT_AUTO_DOWNLOAD_HISTORY", True)):
            return

        xt = _get_xtdata()
        if xt is None:
            return

        start_time = str(self._get_runtime_setting("QMT_HISTORY_START_TIME", "") or "")
        try:
            xt.download_history_data(xt_code, period=xt_period, start_time=start_time, incrementally=True)
        except TypeError:
            try:
                xt.download_history_data(xt_code, period=xt_period, start_time=start_time)
            except Exception as e:
                logger.debug(f"QMT: Automatic download of historical data failed {xt_code}: {e}")
        except Exception as e:
            logger.debug(f"QMT: Automatic download of historical data failed {xt_code}: {e}")

    def _download_financial_if_needed(self, code: str, table_list: Optional[List[str]], start_time: str, end_time: str) -> None:
        if not self._parse_bool(self._get_runtime_setting("QMT_AUTO_DOWNLOAD_FINANCIAL", False)):
            return
        self.download_financial_data([code], table_list=table_list, start_time=start_time, end_time=end_time)

    def _is_etf_code(self, code: str) -> bool:
        code = str(code).strip().zfill(6)
        return code.startswith(("50", "51", "52", "56", "58", "15", "16", "18"))

    def _mark_qmt_available(self) -> None:
        type(self)._AVAILABLE_CACHE_UNTIL = time.monotonic() + self._AVAILABLE_CACHE_SECONDS
        type(self)._UNAVAILABLE_CACHE_UNTIL = 0.0
        self._available = True

    def _mark_qmt_unavailable(self) -> None:
        type(self)._UNAVAILABLE_CACHE_UNTIL = time.monotonic() + self._UNAVAILABLE_CACHE_SECONDS
        type(self)._AVAILABLE_CACHE_UNTIL = 0.0
        self._available = False

    def is_available(self) -> bool:
        """Check if xtquant is available and QMT is connected"""
        now = time.monotonic()
        if now < type(self)._UNAVAILABLE_CACHE_UNTIL:
            return False
        if now < type(self)._AVAILABLE_CACHE_UNTIL:
            return True
        if now < type(self)._AVAILABILITY_PROBE_UNTIL:
            logger.debug("QMT Availability probe is in progress, current request is skipped quickly")
            return False

        # Fast short circuit: If QMT is not enabled in the configuration, return False directly (skip connection detection)
        try:
            from app.core.config import settings as app_settings
            if not app_settings.QMT_UNIFIED_ENABLED:
                self._mark_qmt_unavailable()
                return False
        except Exception:
            pass

        type(self)._AVAILABILITY_PROBE_UNTIL = now + self._PROBE_GUARD_SECONDS
        try:
            self._bootstrap_connection()

            xt = _get_xtdata()
            if xt is None:
                self._mark_qmt_unavailable()
                return False
            if self._has_existing_connection(xt):
                self._mark_qmt_available()
                return True

            logger.debug("QMT Not available: No reusable QMT connection detected")
            self._mark_qmt_unavailable()
            return False
        finally:
            type(self)._AVAILABILITY_PROBE_UNTIL = 0.0

    # ==================== Data quality monitoring ====================

    def _record_quality(self, method: str, success: bool, error: Optional[str] = None, duration_ms: float = 0) -> None:
        """Record data to obtain quality indicators."""
        self._quality_stats["total_calls"] += 1
        if success:
            self._quality_stats["success_calls"] += 1
        else:
            self._quality_stats["failed_calls"] += 1
            self._quality_stats["last_error"] = error
            self._quality_stats["last_error_time"] = datetime.now().isoformat()

        by_method = self._quality_stats["by_method"]
        if method not in by_method:
            by_method[method] = {"total": 0, "success": 0, "failed": 0, "avg_duration_ms": 0, "last_error": None}
        m = by_method[method]
        m["total"] += 1
        if success:
            m["success"] += 1
        else:
            m["failed"] += 1
            m["last_error"] = error
        if duration_ms > 0:
            m["avg_duration_ms"] = (m["avg_duration_ms"] * (m["total"] - 1) + duration_ms) / m["total"]

    def get_quality_stats(self) -> Dict[str, Any]:
        """Get data quality statistics."""
        stats = dict(self._quality_stats)
        stats["success_rate"] = (
            stats["success_calls"] / stats["total_calls"] * 100
            if stats["total_calls"] > 0 else 0
        )
        return stats

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """Get the stock list (via Shanghai and Shenzhen constituent stocks portfolio)"""
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None
        try:
            start_time = time.perf_counter()

            # Shanghai and Shenzhen A-shares: obtained through the sector (no waiting for sector data to be downloaded)
            sector_query_start = time.perf_counter()
            sh_stocks = xt.get_stock_list_in_sector("沪深A股", 0) or []
            if not sh_stocks:
                sh_stocks = xt.get_stock_list_in_sector("沪市A股", 0) or []
                sz_stocks = xt.get_stock_list_in_sector("深市A股", 0) or []
                stocks = list(sh_stocks) + list(sz_stocks)
            else:
                stocks = list(sh_stocks)
            sector_query_elapsed = time.perf_counter() - sector_query_start

            if not stocks:
                logger.warning("QMT: No stock list obtained")
                return None

            max_count_raw = self._get_runtime_setting("QMT_STOCK_LIST_MAX_COUNT", 10000)
            detail_limit_raw = self._get_runtime_setting("QMT_STOCK_LIST_DETAIL_LIMIT", 300)
            detail_budget_raw = self._get_runtime_setting("QMT_STOCK_LIST_DETAIL_TIMEOUT_SECONDS", 5)
            try:
                max_count = max(1, int(str(max_count_raw)))
            except (TypeError, ValueError):
                max_count = 10000
            try:
                detail_lookup_limit = max(0, int(str(detail_limit_raw)))
            except (TypeError, ValueError):
                detail_lookup_limit = 300
            try:
                detail_time_budget = max(0.0, float(str(detail_budget_raw)))
            except (TypeError, ValueError):
                detail_time_budget = 5.0

            rows = []
            detail_lookup_count = 0
            detail_lookup_start = time.perf_counter()
            detail_budget_exhausted = False

            for xt_code in stocks[:max_count]:
                code6 = _code_to_6digit(xt_code)
                if len(code6) != 6:
                    continue

                use_detail_lookup = (
                    detail_lookup_count < detail_lookup_limit
                    and (time.perf_counter() - detail_lookup_start) < detail_time_budget
                )
                try:
                    name = ""
                    if use_detail_lookup:
                        detail = xt.get_instrument_detail(xt_code)
                        detail_lookup_count += 1
                        if detail and isinstance(detail, dict):
                            name = detail.get("InstrumentName", "") or detail.get("name", "")
                        elif detail and hasattr(detail, "InstrumentName"):
                            name = getattr(detail, "InstrumentName", "")
                    else:
                        detail_budget_exhausted = True
                    rows.append({
                        "symbol": code6,
                        "ts_code": xt_code,
                        "name": name or code6,
                        "market": "",
                        "area": "",
                        "industry": "",
                        "list_date": "",
                    })
                except Exception:
                    rows.append({"symbol": code6, "ts_code": xt_code, "name": code6, "market": "", "area": "", "industry": "", "list_date": ""})

            if rows:
                df = pd.DataFrame(rows)
                total_elapsed = time.perf_counter() - start_time
                logger.info(
                    "QMT: Obtained %s stocks, sector query %.2fs, details supplement %s/%s, details budget %.2fs, time-consuming %.2fs%s",
                    len(df),
                    sector_query_elapsed,
                    detail_lookup_count,
                    min(len(stocks), max_count),
                    detail_time_budget,
                    total_elapsed,
                    "（已提前停止详情补充）" if detail_budget_exhausted else "",
                )
                return df
            return None
        except Exception as e:
            logger.error(f"QMT: Failed to get stock list: {e}")
            return None

    def get_etf_list(self) -> Optional[pd.DataFrame]:
        """Get list of ETFs (filtered by QMT sector list and ticker prefix)"""
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None

        try:
            sector_candidates = [
                "沪深ETF",
                "ETF",
                "沪市ETF",
                "深市ETF",
                "上证ETF",
                "深证ETF",
                "场内基金",
            ]

            etf_codes: List[str] = []
            for sector_name in sector_candidates:
                try:
                    sector_codes = xt.get_stock_list_in_sector(sector_name, 0) or []
                    if sector_codes:
                        etf_codes.extend(list(sector_codes))
                except Exception:
                    continue

            unique_codes: List[str] = []
            seen_codes = set()
            for xt_code in etf_codes:
                code6 = _code_to_6digit(xt_code)
                if not self._is_etf_code(code6):
                    continue
                if code6 in seen_codes:
                    continue
                seen_codes.add(code6)
                unique_codes.append(xt_code)

            if not unique_codes:
                logger.warning("QMT: No ETF list obtained")
                return None

            rows = []
            for xt_code in unique_codes:
                code6 = _code_to_6digit(xt_code)
                try:
                    detail = xt.get_instrument_detail(xt_code)
                    name = ""
                    if detail and isinstance(detail, dict):
                        name = detail.get("InstrumentName", "") or detail.get("name", "")
                    elif detail and hasattr(detail, "InstrumentName"):
                        name = getattr(detail, "InstrumentName", "")
                    rows.append({
                        "symbol": code6,
                        "code": code6,
                        "ts_code": xt_code,
                        "name": name or code6,
                        "fund_type": "ETF",
                    })
                except Exception:
                    rows.append({"symbol": code6, "code": code6, "ts_code": xt_code, "name": code6, "fund_type": "ETF"})

            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            logger.error(f"QMT: Failed to get ETF list: {e}")
            return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Get daily basic data (via get_market_data_ex daily line)"""
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None
        try:
            stock_list = self.get_stock_list()
            if stock_list is None or stock_list.empty:
                return None
            codes = stock_list["ts_code"].head(500).tolist()
            # get_market_data_ex The start_time/end_time requires YYYYMMDD format
            trade_date_compact = trade_date.replace("-", "")

            data = xt.get_market_data_ex(
                field_list=["open", "high", "low", "close", "volume", "amount"],
                stock_list=codes,
                period="1d",
                start_time=trade_date_compact,
                end_time=trade_date_compact,
            )
            if not data or not isinstance(data, dict):
                return None

            rows = []
            for xt_code, df in data.items():
                if df is None:
                    continue
                code6 = _code_to_6digit(xt_code)
                if len(code6) != 6:
                    continue
                close, vol, amt = None, None, None
                if isinstance(df, pd.DataFrame) and not df.empty:
                    row0 = df.iloc[0]
                    close = row0.get("close")
                    vol = row0.get("volume")
                    amt = row0.get("amount")
                elif isinstance(df, dict):
                    close = df.get("close")
                    vol = df.get("volume")
                    amt = df.get("amount")
                rows.append({
                    "ts_code": xt_code,
                    "trade_date": trade_date,
                    "close": self._safe_float(close),
                    "vol": self._safe_float(vol),
                    "amount": self._safe_float(amt),
                    "total_mv": None,
                    "circ_mv": None,
                    "pe": None,
                    "pb": None,
                    "turnover_rate": None,
                })
            if rows:
                return pd.DataFrame(rows)
            return None
        except Exception as e:
            logger.error(f"QMT: Failed to get daily_basic: {e}")
            return None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find the latest trading date (use the latest daily line of the Shanghai Composite Index to judge, lightweight and efficient)"""
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None
        try:
            data = xt.get_market_data_ex(
                field_list=["close"],
                stock_list=["000001.SH"],
                period="1d",
                count=1,
            )
            if data and isinstance(data, dict):
                for xt_code, df in data.items():
                    if df is not None and not df.empty:
                        latest = df.index[-1]
                        # index May be a string or Timestamp
                        return str(latest)[:10].replace("-", "")
            # Keep everything in mind
            return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        except Exception as e:
            logger.error(f"QMT: find_latest_trade_date failed: {e}")
            return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    def get_realtime_quotes(self, symbols: Optional[List[str]] = None) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
        """Get real-time snapshot

        Args:
            symbols: Optional, specify the stock code list (6 pure numbers), if empty, get the whole market
        """
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None
        try:
            # Convert 6-digit code to xtdata format (such as 300750 -> 300750.SZ) 
            # If symbols are not passed, market codes are used. ['SH', 'SZ'] Get all market information in Shanghai and Shenzhen
            xt_codes = []
            if symbols:
                for s in symbols:
                    code = _normalize_code(str(s).strip())
                    if code:
                        xt_codes.append(code)
            else:
                xt_codes = ["SH", "SZ", "BJ"]

            ticks = xt.get_full_tick(xt_codes)
            if not ticks or not isinstance(ticks, dict):
                return None
            # A shares+ETF Valid prefixes:00/30/20(Shenzhen A shares) 60/68(Shanghai A shares) 8/4/9(Beijing Exchange)
            # 50/51/52/56/58(Shanghai Stock Exchange ETF) 15/16/18(Shenzhen City ETF)
            # Excluding bonds, etc.: 10/11/12/13/18/19/7x etc.
            _STOCK_ETF_PREFIXES = ("00", "30", "20", "60", "68", "50", "51", "52", "56", "58", "15", "16", "18", "8", "4", "9")

            result: Dict[str, Dict[str, Optional[float]]] = {}
            for xt_code, t in ticks.items():
                if t is None:
                    continue
                code6 = _code_to_6digit(xt_code)
                if len(code6) != 6:
                    continue
                if not code6.startswith(_STOCK_ETF_PREFIXES):
                    continue
                last_price = getattr(t, "lastPrice", None) or (t.get("lastPrice") if isinstance(t, dict) else None)
                pct = getattr(t, "pctChange", None) or (t.get("pctChange") if isinstance(t, dict) else None)
                amt = getattr(t, "amount", None) or (t.get("amount") if isinstance(t, dict) else None)
                result[code6] = {
                    "close": float(last_price) if last_price is not None else None,
                    "pct_chg": float(pct) if pct is not None else None,
                    "amount": float(amt) if amt is not None else None,
                }
            if result:
                logger.info(f"QMT: 获取到 {len(result)} 只股票实时行情")
                return result
            return None
        except Exception as e:
            logger.error(f"QMT: Failed to obtain real-time quotes: {e}")
            return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Get K-line data

        According to Xuntou official documentation:
        1. Before use, make sure QMT has the required data
        2. If there is no data locally, first call download_history_data to download
        3. It is recommended to use the get_market_data_ex interface
        """
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None
        _start = time.perf_counter()
        try:
            xt_code = _normalize_code(code)
            if not xt_code:
                self._record_quality("get_kline", False, "invalid_code")
                return None
            period_map = {
                "day": "1d",
                "week": "1w",
                "month": "1mon",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "60m": "1h",
            }
            xt_period = period_map.get(period, "1d")

            self._download_history_if_needed(xt_code, xt_period)

            # According to the official documentation, use the get_market_data_ex interface
            # Passing in an empty field_list means getting all fields
            data = xt.get_market_data_ex(
                field_list=[],  # An empty list means getting all fields
                stock_list=[xt_code],
                period=xt_period,
                count=limit  # Get the latest N pieces of data
            )
            if not data or xt_code not in data:
                return None
            df = data[xt_code]
            if df is None or (hasattr(df, "empty") and df.empty):
                return None
            # xtdata Return {stock_code: pd.DataFrame}
            if isinstance(df, pd.DataFrame):
                df = df.tail(limit)
                items = []
                for idx, row in df.iterrows():
                    # get_market_data_ex Use the index of the DataFrame as the time
                    # The index is usually pandas Timestamp or timestamp
                    if hasattr(idx, 'strftime'):
                        # pandas Timestamp object
                        date_str = idx.strftime("%Y-%m-%d")
                    elif isinstance(idx, (int, float)):
                        # Timestamp (milliseconds)
                        from datetime import datetime
                        date_str = datetime.fromtimestamp(idx / 1000).strftime("%Y-%m-%d")
                    elif isinstance(idx, str) and len(idx) == 8 and idx.isdigit():
                        # YYYYMMDD format, converted to YYYY-MM-DD
                        date_str = f"{idx[:4]}-{idx[4:6]}-{idx[6:8]}"
                    else:
                        # Other formats, directly convert to string
                        date_str = str(idx)

                    items.append({
                        "date": date_str,
                        "open": self._safe_float(row.get("open")),
                        "high": self._safe_float(row.get("high")),
                        "low": self._safe_float(row.get("low")),
                        "close": self._safe_float(row.get("close")),
                        "volume": self._safe_float(row.get("volume")),
                        "amount": self._safe_float(row.get("amount")),
                    })
                self._record_quality("get_kline", True, duration_ms=(time.perf_counter() - _start) * 1000)
                return items
            self._record_quality("get_kline", False, "no_data_format")
            return None
        except Exception as e:
            logger.error(f"QMT: get_kline failed: {e}", exc_info=True)
            self._record_quality("get_kline", False, str(e)[:200], (time.perf_counter() - _start) * 1000)
            return None

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True) -> Optional[List[Dict]]:
        """QMT News is not supported, returns None, falls back to by DataSourceManager AKShare"""
        logger.debug("QMT: News is not supported, please use AKShare")
        return None

    # ==================== Financial data interface (extended functions) ====================

    def download_financial_data(
        self,
        stock_list: List[str],
        table_list: Optional[List[str]] = None,
        start_time: str = '',
        end_time: str = '',
        callback=None
    ) -> bool:
        """
        Download financial data to local

        Args:
            stock_list: Stock code list (6-digit code, automatically converted to QMT format)
            table_list: List of financial report types, supporting:
                - 'Balance': balance sheet
                - 'Income': income statement
                - 'CashFlow': cash flow statement
                - 'Pershareindex': Per Share Indicators (Main Indicators)
                - 'Capital': share capital table
                - 'Top10holder': Top ten shareholders
                - 'Top10flowholder': Top ten tradable shareholders
                - 'Holdernum': Number of shareholders
            start_time: Start time (YYYYMMDD), filter by disclosure date
            end_time: End time (YYYYMMDD), filter by disclosure date
            callback: Progress callback function, the parameters are dict:
                - total: Total number of tasks
                - finished: Completed
                - stockcode: Current ticker
                - message: news

        Returns:
            bool: Is the download successful?
        """
        if not self.is_available():
            return False
        xt = _get_xtdata()
        if xt is None:
            return False

        try:
            # Convert ticker to QMT format
            xt_codes = []
            for code in stock_list:
                xt_code = _normalize_code(code)
                if xt_code:
                    xt_codes.append(xt_code)

            if not xt_codes:
                logger.warning("QMT: No valid ticker symbol")
                return False

            # Download all reports by default
            if table_list is None:
                table_list = [
                    'Balance',          # balance sheet
                    'Income',           # income statement
                    'CashFlow',         # cash flow statement
                    'Pershareindex',    # per share indicator
                    'Capital',          # share capital table
                ]

            logger.info(f"QMT: 开始下载财务数据 - {len(xt_codes)} 只股票, {len(table_list)} 种报表")

            # Using download_financial_data2 (with callback)
            xt.download_financial_data2(
                stock_list=xt_codes,
                table_list=table_list,
                start_time=start_time,
                end_time=end_time,
                callback=callback
            )

            logger.info("QMT: Financial data download completed")
            return True

        except Exception as e:
            logger.error(f"QMT: Failed to download financial data: {e}", exc_info=True)
            return False

    def get_financial_data(
        self,
        code: str,
        table_list: Optional[List[str]] = None,
        start_time: str = '',
        end_time: str = '',
        report_type: str = 'report_time'
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        Get financial data (from local cache)

        Args:
            code: Stock code (6-digit code)
            table_list: List of financial report types, main reports are obtained by default
            start_time: Starting time (YYYYMMDD)
            end_time: End time (YYYYMMDD)
            report_type: Report filtering method
                - 'report_time': Filter by deadline
                - 'announce_time': Filter by disclosure date

        Returns:
            dict: {table_name: DataFrame} or None
                For example: {'Income': DataFrame, 'Balance': DataFrame}
        """
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None

        try:
            xt_code = _normalize_code(code)
            if not xt_code:
                return None

            # Get the main report by default
            if table_list is None:
                table_list = [
                    'Pershareindex',    # per share indicator
                    'Income',           # income statement
                    'Balance',          # balance sheet
                ]

            self._download_financial_if_needed(code, table_list, start_time, end_time)

            # Get financial data
            data = xt.get_financial_data(
                stock_list=[xt_code],
                table_list=table_list,
                start_time=start_time,
                end_time=end_time,
                report_type=report_type
            )

            if not data or xt_code not in data:
                return None

            stock_data = data[xt_code]

            # filter out empty DataFrame
            result = {}
            for table_name, df in stock_data.items():
                if df is not None and not df.empty:
                    result[table_name] = df

            return result if result else None

        except Exception as e:
            logger.error(f"QMT: Failed to get financial data {code}: {e}", exc_info=True)
            return None

    # ==================== Market/industry analysis auxiliary interface ====================

    @staticmethod
    def _is_market_session() -> bool:
        """Determine whether it is currently in the A-share trading session (including the 30-minute buffer period after the market close)."""
        try:
            from app.utils.trading_time import is_trading_time
            return is_trading_time()
        except Exception:
            # When it cannot be judged, conservatively return True and let the real-time snapshot try first.
            return True

    def get_limit_stats(self, trade_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtain price limit statistics (prioritize real-time snapshots, automatically switch to historical daily lines after the market opens)

        Args:
            trade_date: Transaction date (format YYYY-MM-DD or YYYYMMDD), if empty, the latest transaction date will be taken

        Returns:
            dict: {
                "up_limit": Daily limit number,
                "down_limit": Lower limit number,
                "rising": Increase,
                "falling": Number of declines,
                "flat": Number of flat games,
                "total": total,
                "up_limit_stocks": [(code, name, pct), ...],  # Before daily limit stocks 20
                "down_limit_stocks": [(code, name, pct), ...],  # Before stocks fall to their limit 20
                "source": "realtime" | "history",
            }
        """
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None

        # After-hours/closed market, directly follow the historical daily line to avoid invalid real-time snapshot requests.
        if not self._is_market_session():
            logger.info("QMT: During the current non-trading period, directly use the historical daily line to calculate the price limit")
            result = self._get_limit_stats_history(xt, trade_date)
            if result:
                result["source"] = "history"
            return result

        # Try real-time snapshots first during the session
        result = self._get_limit_stats_realtime(xt)
        if result and result.get("total", 0) > 0:
            result["source"] = "realtime"
            return result

        # There is no data in the real-time snapshot, switch to the historical daily line
        logger.info("QMT: There is no price limit data in the real-time snapshot, switch to historical daily line back calculation")
        result = self._get_limit_stats_history(xt, trade_date)
        if result:
            result["source"] = "history"
        return result

    def _get_limit_stats_realtime(self, xt) -> Optional[Dict[str, Any]]:
        """Price limit statistics based on real-time snapshots."""
        try:
            ticks = xt.get_full_tick(["SH", "SZ", "BJ"])
            if not ticks or not isinstance(ticks, dict):
                return None

            _STOCK_PREFIXES = ("00", "30", "20", "60", "68", "8", "4")
            _EXCLUDE_PREFIXES = ("000", "399", "899", "204", "1318")

            up_limit_stocks = []
            down_limit_stocks = []
            rising = 0
            falling = 0
            flat = 0

            for xt_code, t in ticks.items():
                if t is None:
                    continue
                code6 = _code_to_6digit(xt_code)
                if len(code6) != 6 or not code6.startswith(_STOCK_PREFIXES):
                    continue
                if code6.startswith(_EXCLUDE_PREFIXES):
                    continue

                last_price = getattr(t, "lastPrice", None) or (t.get("lastPrice") if isinstance(t, dict) else None)
                pct = getattr(t, "pctChange", None) or (t.get("pctChange") if isinstance(t, dict) else None)
                up_stop = getattr(t, "upStopPrice", None) or (t.get("upStopPrice") if isinstance(t, dict) else None)
                down_stop = getattr(t, "downStopPrice", None) or (t.get("downStopPrice") if isinstance(t, dict) else None)

                if last_price is None or pct is None:
                    continue

                try:
                    last_price = float(last_price)
                    pct = float(pct)
                    up_stop = float(up_stop) if up_stop is not None else None
                    down_stop = float(down_stop) if down_stop is not None else None
                except (ValueError, TypeError):
                    continue

                is_up_limit = self._check_up_limit(code6, pct, last_price, up_stop)
                is_down_limit = self._check_down_limit(code6, pct, last_price, down_stop)

                if is_up_limit:
                    name = self._get_instrument_name(xt, xt_code, code6)
                    up_limit_stocks.append((code6, name, pct))
                elif is_down_limit:
                    name = self._get_instrument_name(xt, xt_code, code6)
                    down_limit_stocks.append((code6, name, pct))
                elif pct > 0:
                    rising += 1
                elif pct < 0:
                    falling += 1
                else:
                    flat += 1

            return {
                "up_limit": len(up_limit_stocks),
                "down_limit": len(down_limit_stocks),
                "rising": rising,
                "falling": falling,
                "flat": flat,
                "total": len(up_limit_stocks) + len(down_limit_stocks) + rising + falling + flat,
                "up_limit_stocks": sorted(up_limit_stocks, key=lambda x: x[2], reverse=True)[:20],
                "down_limit_stocks": sorted(down_limit_stocks, key=lambda x: x[2])[:20],
            }
        except Exception as e:
            logger.error(f"QMT: Real-time snapshot price limit statistics failed: {e}")
            return None

    def _get_limit_stats_history(self, xt, trade_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Price limit statistics based on historical daily lines (after-hours downgrade)."""
        try:
            # Get the list of Shanghai and Shenzhen A shares
            stock_list = xt.get_stock_list_in_sector("沪深A股")
            if not stock_list:
                return None

            # Use directly get_market_data_ex + count=1 Get the latest daily line
            # There is no need to download_history_data2, QMT already caches the data locally.
            stock_codes = list(stock_list)

            # Obtain in batches (1000 per batch to avoid memory problems)
            batch_size = 1000
            all_rows = []  # [(code6, name, close, preClose, pct)]

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                try:
                    data = xt.get_market_data_ex([], batch, "1d", count=1)
                except Exception:
                    continue

                if not data:
                    continue

                for xt_code, df in data.items():
                    if df is None or df.empty:
                        continue
                    code6 = _code_to_6digit(xt_code)
                    if len(code6) != 6:
                        continue

                    row = df.iloc[-1]
                    close = row.get("close")
                    pre_close = row.get("preClose")
                    suspend = row.get("suspendFlag", 0)

                    if close is None or pre_close is None or pre_close == 0:
                        continue
                    if suspend and int(suspend) != 0:
                        continue

                    try:
                        close = float(close)
                        pre_close = float(pre_close)
                    except (ValueError, TypeError):
                        continue

                    pct = (close - pre_close) / pre_close * 100
                    name = self._get_instrument_name(xt, xt_code, code6)
                    all_rows.append((code6, name, close, pre_close, pct))

            if not all_rows:
                return None

            up_limit_stocks = []
            down_limit_stocks = []
            rising = 0
            falling = 0
            flat = 0

            for code6, name, close, pre_close, pct in all_rows:
                # Use close / pre_close to determine whether the price limit has been reached
                up_stop = round(pre_close * 1.1, 2) if code6.startswith(("60", "00")) else \
                          round(pre_close * 1.2, 2) if code6.startswith(("30", "68")) else \
                          round(pre_close * 1.3, 2) if code6.startswith(("8", "4")) else None
                down_stop = round(pre_close * 0.9, 2) if code6.startswith(("60", "00")) else \
                            round(pre_close * 0.8, 2) if code6.startswith(("30", "68")) else \
                            round(pre_close * 0.7, 2) if code6.startswith(("8", "4")) else None

                is_up_limit = False
                if up_stop and close >= up_stop:
                    is_up_limit = True
                elif pct >= 9.9 and code6.startswith(("60", "00")):
                    is_up_limit = True
                elif pct >= 19.9 and code6.startswith(("30", "68")):
                    is_up_limit = True
                elif pct >= 29.9 and code6.startswith(("8", "4")):
                    is_up_limit = True

                is_down_limit = False
                if down_stop and close <= down_stop:
                    is_down_limit = True
                elif pct <= -9.9 and code6.startswith(("60", "00")):
                    is_down_limit = True
                elif pct <= -19.9 and code6.startswith(("30", "68")):
                    is_down_limit = True
                elif pct <= -29.9 and code6.startswith(("8", "4")):
                    is_down_limit = True

                if is_up_limit:
                    up_limit_stocks.append((code6, name, pct))
                elif is_down_limit:
                    down_limit_stocks.append((code6, name, pct))
                elif pct > 0:
                    rising += 1
                elif pct < 0:
                    falling += 1
                else:
                    flat += 1

            return {
                "up_limit": len(up_limit_stocks),
                "down_limit": len(down_limit_stocks),
                "rising": rising,
                "falling": falling,
                "flat": flat,
                "total": len(up_limit_stocks) + len(down_limit_stocks) + rising + falling + flat,
                "up_limit_stocks": sorted(up_limit_stocks, key=lambda x: x[2], reverse=True)[:20],
                "down_limit_stocks": sorted(down_limit_stocks, key=lambda x: x[2])[:20],
            }
        except Exception as e:
            logger.error(f"QMT: Historical daily price limit statistics failed: {e}")
            return None

    @staticmethod
    def _check_up_limit(code6: str, pct: float, last_price: float, up_stop: Optional[float]) -> bool:
        """Determine whether the limit is reached."""
        if up_stop and up_stop > 0 and last_price >= up_stop * 0.998:
            return True
        if pct >= 9.9 and code6.startswith(("60", "00")):
            return True
        if pct >= 19.9 and code6.startswith(("30", "68")):
            return True
        if pct >= 29.9 and code6.startswith(("8", "4")):
            return True
        return False

    @staticmethod
    def _check_down_limit(code6: str, pct: float, last_price: float, down_stop: Optional[float]) -> bool:
        """Determine whether it falls to the limit."""
        if down_stop and down_stop > 0 and last_price <= down_stop * 1.002:
            return True
        if pct <= -9.9 and code6.startswith(("60", "00")):
            return True
        if pct <= -19.9 and code6.startswith(("30", "68")):
            return True
        if pct <= -29.9 and code6.startswith(("8", "4")):
            return True
        return False

    @staticmethod
    def _get_instrument_name(xt, xt_code: str, code6: str) -> str:
        """Get the stock name."""
        try:
            detail = xt.get_instrument_detail(xt_code)
            if detail and isinstance(detail, dict):
                return detail.get("InstrumentName", code6)
        except Exception:
            pass
        return code6

    def get_amount_ranking(self, top_n: int = 20, trade_date: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Obtain transaction volume ranking (prioritize real-time snapshots, automatically switch to historical daily lines after the market opens)

        Args:
            top_n: Return the first N items
            trade_date: Transaction date (format YYYY-MM-DD or YYYYMMDD), if empty, the latest transaction date will be taken

        Returns:
            list: [{"code": str, "name": str, "amount": float, "pct_chg": float}, ...]
        """
        if not self.is_available():
            return None
        xt = _get_xtdata()
        if xt is None:
            return None

        # After the market opens/the market is closed, go directly to the historical daily line
        if not self._is_market_session():
            logger.info("QMT: During the current non-trading period, directly use the historical daily line to obtain the transaction volume ranking.")
            return self._get_amount_ranking_history(xt, top_n, trade_date)

        # Try real-time snapshots first during the session
        result = self._get_amount_ranking_realtime(xt, top_n)
        # If the real-time snapshot returns data but too much increase or decrease is missing (remaining from the after-hours snapshot), the historical downgrade will be performed.
        if result:
            missing_pct = sum(1 for r in result if r.get("pct_chg") is None)
            if missing_pct > len(result) * 0.5:
                logger.info("QMT: There is too much missing in the real-time snapshot, so switch to the historical daily line.")
                result = self._get_amount_ranking_history(xt, top_n, trade_date)
        if result:
            return result

        # After-Hour Downgrade: Historical Daily Line
        logger.info("QMT: There is no transaction volume data in the real-time snapshot, switch to the historical daily line")
        return self._get_amount_ranking_history(xt, top_n, trade_date)

    def _get_amount_ranking_realtime(self, xt, top_n: int) -> Optional[List[Dict[str, Any]]]:
        """Turnover ranking based on real-time snapshots."""
        try:
            ticks = xt.get_full_tick(["SH", "SZ", "BJ"])
            if not ticks or not isinstance(ticks, dict):
                return None

            _STOCK_PREFIXES = ("00", "30", "20", "60", "68", "8", "4")
            _EXCLUDE_PREFIXES = ("000", "399", "899", "204", "1318")
            rows = []

            for xt_code, t in ticks.items():
                if t is None:
                    continue
                code6 = _code_to_6digit(xt_code)
                if len(code6) != 6 or not code6.startswith(_STOCK_PREFIXES):
                    continue
                if code6.startswith(_EXCLUDE_PREFIXES):
                    continue

                amt = getattr(t, "amount", None) or (t.get("amount") if isinstance(t, dict) else None)
                pct = getattr(t, "pctChange", None) or (t.get("pctChange") if isinstance(t, dict) else None)

                if amt is None:
                    continue
                try:
                    amt = float(amt)
                    pct = float(pct) if pct is not None else None
                except (ValueError, TypeError):
                    continue

                # Filter out those with a trading volume of 0 (remaining after-hours snapshots)
                if amt <= 0:
                    continue

                name = self._get_instrument_name(xt, xt_code, code6)
                rows.append({"code": code6, "name": name, "amount": amt, "pct_chg": pct})

            if not rows:
                return None
            rows.sort(key=lambda x: x["amount"], reverse=True)
            return rows[:top_n]
        except Exception as e:
            logger.error(f"QMT: Real-time snapshot turnover ranking failed: {e}")
            return None

    def _get_amount_ranking_history(self, xt, top_n: int, trade_date: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Ranking based on historical daily trading volume (downgraded after hours)."""
        try:
            stock_list = xt.get_stock_list_in_sector("沪深A股")
            if not stock_list:
                return None

            stock_codes = list(stock_list)
            batch_size = 1000
            rows = []

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                try:
                    data = xt.get_market_data_ex([], batch, "1d", count=1)
                except Exception:
                    continue

                if not data:
                    continue

                for xt_code, df in data.items():
                    if df is None or df.empty:
                        continue
                    code6 = _code_to_6digit(xt_code)
                    if len(code6) != 6:
                        continue

                    row = df.iloc[-1]
                    amt = row.get("amount")
                    close = row.get("close")
                    pre_close = row.get("preClose")
                    suspend = row.get("suspendFlag", 0)

                    if amt is None or close is None or pre_close is None or pre_close == 0:
                        continue
                    if suspend and int(suspend) != 0:
                        continue

                    try:
                        amt = float(amt)
                        close = float(close)
                        pre_close = float(pre_close)
                    except (ValueError, TypeError):
                        continue

                    if amt <= 0:
                        continue

                    pct = (close - pre_close) / pre_close * 100
                    name = self._get_instrument_name(xt, xt_code, code6)
                    rows.append({"code": code6, "name": name, "amount": amt, "pct_chg": pct})

            if not rows:
                return None
            rows.sort(key=lambda x: x["amount"], reverse=True)
            return rows[:top_n]
        except Exception as e:
            logger.error(f"QMT: Historical daily turnover ranking failed: {e}")
            return None


# === local_adapter.py ===
"""
Local data source adapter for user-imported data
"""
from typing import Optional, Dict
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class LocalAdapter(DataSourceAdapter):
    """Local data source adapter (data imported by users through API)"""

    def __init__(self):
        super().__init__()  # Call parent class initialization

    @property
    def name(self) -> str:
        return "local"

    def _get_default_priority(self) -> int:
        return 10  # The default is the highest priority (the larger the number, the higher the priority)

    def is_available(self) -> bool:
        """Check if the local data source is available (check if there is local data in MongoDB)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_basic_info
            
            # Check if there is source='local' data
            count = collection.count_documents({"source": "local"}, limit=1)
            return count > 0
        except Exception as e:
            logger.warning(f"Local: Failed to check availability: {e}")
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取本地股票列表"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_basic_info
            
            # Query source='local' stocks
            cursor = collection.find({"source": "local"})
            stocks = list(cursor)
            
            if not stocks:
                logger.info("Local: No local stocks found")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(stocks)
            
            # Standardize field names (make sure you have the required fields)
            if 'symbol' in df.columns and 'name' in df.columns:
                logger.info(f"Local: Successfully fetched {len(df)} local stocks")
                return df
            else:
                logger.warning("Local: Missing required fields (symbol, name)")
                return None
                
        except Exception as e:
            logger.error(f"Local: Failed to fetch stock list: {e}")
            return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Obtain daily basic financial data (local data sources are not supported yet)"""
        logger.warning("Local: get_daily_basic not supported")
        return None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find the latest transaction date (from local K-line data)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_daily_quotes

            # Query data_source='local' latest transaction date
            cursor = collection.find(
                {"data_source": "local"},
                {"trade_date": 1}
            ).sort("trade_date", -1).limit(1)

            result = list(cursor)
            if result:
                latest_date = result[0].get('trade_date')
                logger.info(f"Local: Latest trade date: {latest_date}")
                return latest_date
            else:
                logger.info("Local: No trade date found")
                return None

        except Exception as e:
            logger.error(f"Local: Failed to find latest trade date: {e}")
            return None

    def get_realtime_quotes(self) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
        """Get real-time quotes (read from local database)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.market_quotes
            
            # Query all market data
            cursor = collection.find({})
            quotes = list(cursor)
            
            if not quotes:
                logger.info("Local: No local quotes found")
                return None
            
            # Convert to dictionary format
            result = {}
            for quote in quotes:
                symbol = quote.get('symbol')
                if symbol:
                    result[symbol] = {
                        'close': quote.get('close'),
                        'pct_chg': quote.get('pct_chg'),
                        'amount': quote.get('amount')
                    }
            
            logger.info(f"Local: Successfully fetched {len(result)} quotes")
            return result
            
        except Exception as e:
            logger.error(f"Local: Failed to fetch realtime quotes: {e}")
            return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """Get K-line data (read from local database)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_daily_quotes

            period_map = {
                "day": "daily",
                "week": "weekly",
                "month": "monthly",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "60m": "60min",
            }
            normalized_period = period_map.get(period, period)
            
            # Query K line data
            cursor = collection.find(
                {"symbol": code, "data_source": "local", "period": normalized_period}
            ).sort("trade_date", 1).limit(limit)
            
            klines = list(cursor)
            
            if not klines:
                logger.info(f"Local: No kline data found for {code} (period={normalized_period})")
                return []
            
            # Convert to standard format
            result = []
            for kline in klines:
                result.append({
                    'time': kline.get('trade_date'),
                    'open': kline.get('open'),
                    'high': kline.get('high'),
                    'low': kline.get('low'),
                    'close': kline.get('close'),
                    'volume': kline.get('volume'),
                    'amount': kline.get('amount')
                })
            
            logger.info(f"Local: Successfully fetched {len(result)} klines for {code} (period={normalized_period})")
            return result
            
        except Exception as e:
            logger.error(f"Local: Failed to fetch kline for {code}: {e}")
            return []

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """Get news/announcements (not supported by local data sources)"""
        logger.warning("Local: get_news not supported")
        return []


# === data_consistency_checker.py ===
"""
Minimal stub for DataConsistencyChecker
- Purpose: eliminate warning and provide no-op consistency checking
- Behavior: always mark data as consistent and prefer primary source
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import pandas as pd


@dataclass
class DataConsistencyResult:
    is_consistent: bool = True
    confidence_score: float = 1.0
    recommended_action: str = "use_primary"
    differences: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.differences is None:
            self.differences = []


class DataConsistencyChecker:
    """No-op checker: always returns consistent and uses primary data.
    This is a lightweight placeholder so that DataSourceManager can import it
    without printing warnings when the full checker isn't provided.
    """

    def check_daily_basic_consistency(
        self,
        primary: pd.DataFrame,
        secondary: pd.DataFrame,
        primary_name: str,
        secondary_name: str,
    ) -> DataConsistencyResult:
        # In stub, we do not compute differences; always consistent.
        return DataConsistencyResult()

    def resolve_data_conflicts(
        self,
        primary: pd.DataFrame,
        secondary: pd.DataFrame,
        result: DataConsistencyResult,
    ) -> Tuple[pd.DataFrame, str]:
        # Always choose primary data
        return primary, "use_primary"


# === manager.py ===
"""
Data source manager that orchestrates multiple adapters with priority and optional consistency checks
"""
from typing import List, Optional, Tuple, Dict
import logging
import time
from datetime import datetime, timedelta
import pandas as pd

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

# === __init__.py ===
"""
Data sources subpackage.
Expose adapters and manager for backward-compatible imports.
"""

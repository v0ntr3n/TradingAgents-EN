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

from .base import DataSourceAdapter

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

            logger.info(f"QMT: Financial data download completed")
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


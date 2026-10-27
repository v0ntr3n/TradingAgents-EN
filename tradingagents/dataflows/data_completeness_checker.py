#!/usr/bin/env python3
"""
Data integrity checker
Used to check whether historical data is complete and includes the latest trading day, and automatically re-pulls it when needed.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
import pandas as pd

logger = logging.getLogger(__name__)


class DataCompletenessChecker:
    """数据完整性检查器"""
    
    def __init__(self):
        self.logger = logger
    
    def check_data_completeness(
        self,
        symbol: str,
        data: str,
        start_date: str,
        end_date: str,
        market: str = "CN"
    ) -> Tuple[bool, str, dict]:
        """
        Check data integrity
        
        Args:
            symbol: Stock code
            data: data string
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            market: market type (CN/HK/US)
        
        Returns:
            (is_complete, message, details)
            - is_complete: Is the data complete?
            - message: Check result message
            - details: Detail dictionary
        """
        details = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "market": market,
            "data_rows": 0,
            "expected_rows": 0,
            "missing_days": 0,
            "has_latest_trade_date": False,
            "latest_date_in_data": None,
            "latest_trade_date": None,
            "completeness_ratio": 0.0
        }
        
        # 1. Check if the data is empty or wrong
        if not data or "❌" in data or "错误" in data or "获取失败" in data:
            return False, "数据为空或包含错误", details
        
        # 2. Try to parse the data
        try:
            df = self._parse_data_to_dataframe(data)
            if df is None or df.empty:
                return False, "无法解析数据或数据为空", details
            
            details["data_rows"] = len(df)
            
            # 3. Get the date range in the data
            if 'date' in df.columns:
                date_col = 'date'
            elif 'trade_date' in df.columns:
                date_col = 'trade_date'
            else:
                # Try to find date column
                date_col = None
                for col in df.columns:
                    if 'date' in col.lower() or '日期' in col:
                        date_col = col
                        break
                
                if not date_col:
                    self.logger.warning(f"⚠️ 无法找到日期列: {symbol}")
                    return False, "无法找到日期列", details
            
            # The conversion date is listed as datetime
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col)
            
            data_start_date = df[date_col].min()
            data_end_date = df[date_col].max()
            details["latest_date_in_data"] = data_end_date.strftime('%Y-%m-%d')
            
            # 4. Get the latest trading day
            latest_trade_date = self._get_latest_trade_date(market)
            details["latest_trade_date"] = latest_trade_date
            
            # 5. Check if the latest trading day is included
            if latest_trade_date:
                latest_trade_dt = datetime.strptime(latest_trade_date, '%Y-%m-%d')
                details["has_latest_trade_date"] = data_end_date.date() >= latest_trade_dt.date()
            
            # 6. Calculate expected number of trading days (rough estimate)
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            total_days = (end_dt - start_dt).days + 1
            
            # Assume trading days account for approximately 70% of total days (taking into account weekends and holidays)
            expected_trade_days = int(total_days * 0.7)
            details["expected_rows"] = expected_trade_days
            
            # 7. Calculate completeness ratio
            if expected_trade_days > 0:
                completeness_ratio = len(df) / expected_trade_days
                details["completeness_ratio"] = completeness_ratio
            
            # 8. Check for data gaps
            missing_days = self._check_data_gaps(df, date_col)
            details["missing_days"] = len(missing_days)
            
            # 9. Comprehensive judgment
            is_complete = True
            messages = []
            
            # Check 1: Is the amount of data sufficient?
            if len(df) < expected_trade_days * 0.5:  # less than expected 50%
                is_complete = False
                messages.append(f"数据量不足（{len(df)}条，预期约{expected_trade_days}条）")
            
            # Check 2: Whether the latest trading day is included
            if not details["has_latest_trade_date"]:
                is_complete = False
                messages.append(f"缺少最新交易日数据（最新: {details['latest_date_in_data']}, 应为: {latest_trade_date}）")
            
            # Check 3: Are there many gaps?
            if len(missing_days) > expected_trade_days * 0.1:  # gap exceeds 10%
                is_complete = False
                messages.append(f"数据缺口较多（{len(missing_days)}个缺口）")
            
            if is_complete:
                message = f"✅ 数据完整（{len(df)}条记录，完整性{completeness_ratio:.1%}）"
            else:
                message = "⚠️ 数据不完整: " + "; ".join(messages)
            
            return is_complete, message, details
            
        except Exception as e:
            self.logger.error(f"❌ 检查数据完整性失败: {e}")
            return False, f"检查失败: {str(e)}", details
    
    def _parse_data_to_dataframe(self, data: str) -> Optional[pd.DataFrame]:
        """Parse the data string into DataFrame"""
        try:
            # Try multiple parsing methods
            
            # Method 1: Assuming it is CSV format
            from io import StringIO
            try:
                df = pd.read_csv(StringIO(data))
                if not df.empty:
                    return df
            except Exception:
                pass
            
            # Method 2: Assuming it is TSV format
            try:
                df = pd.read_csv(StringIO(data), sep='\t')
                if not df.empty:
                    return df
            except Exception:
                pass
            
            # Method 3: Assume it is separated by spaces
            try:
                df = pd.read_csv(StringIO(data), sep=r'\s+')
                if not df.empty:
                    return df
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 解析数据失败: {e}")
            return None
    
    def _get_latest_trade_date(self, market: str = "CN") -> Optional[str]:
        """获取最新交易日"""
        try:
            if market == "CN":
                # A Stocks: Use Tushare to find the latest trading day
                from tradingagents.dataflows.providers.china.tushare import TushareProvider
                import asyncio
                
                provider = TushareProvider()
                if provider.is_available():
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    latest_date = loop.run_until_complete(provider.find_latest_trade_date())
                    if latest_date:
                        return latest_date
            
            # Alternative: Assume the latest trading day is today or yesterday (or push forward if today is a weekend)
            today = datetime.now()
            for delta in range(0, 5):  # Look back up to 5 days
                check_date = today - timedelta(days=delta)
                # skip weekend
                if check_date.weekday() < 5:  # 0-4 It's Monday to Friday
                    return check_date.strftime('%Y-%m-%d')
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取最新交易日失败: {e}")
            return None
    
    def _check_data_gaps(self, df: pd.DataFrame, date_col: str) -> List[str]:
        """检查数据缺口"""
        try:
            df = df.sort_values(date_col)
            dates = df[date_col].tolist()
            
            missing_dates = []
            for i in range(len(dates) - 1):
                current_date = dates[i]
                next_date = dates[i + 1]
                
                # Calculate date difference
                delta = (next_date - current_date).days
                
                # If the gap is greater than 3 days (considering weekends), there may be a gap
                if delta > 3:
                    missing_dates.append(f"{current_date.strftime('%Y-%m-%d')} 到 {next_date.strftime('%Y-%m-%d')}")
            
            return missing_dates
            
        except Exception as e:
            self.logger.error(f"❌ 检查数据缺口失败: {e}")
            return []


# global instance
_checker = None

def get_data_completeness_checker() -> DataCompletenessChecker:
    """获取数据完整性检查器实例"""
    global _checker
    if _checker is None:
        _checker = DataCompletenessChecker()
    return _checker


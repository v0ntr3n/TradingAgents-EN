"""
China Market Overview Tool (Tushare version)
Replace the old version get_china_market_overview_legacy
"""
import logging
import pandas as pd
from typing import Annotated, Dict, Any, Optional
from langchain_core.tools import tool
from datetime import datetime

from core.tools.base import register_tool
from tradingagents.dataflows.providers.china.tushare import TushareProvider

logger = logging.getLogger(__name__)

@tool
@register_tool(
    tool_id="get_china_market_overview",
    name="China market overview (Tushare)",
    description="Get an overview of China s major stock market indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, Science and Technology Innovation 50)",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["china_market_overview", "market_overview", "index_data", "market_quote", "main_index"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["china_market_overview", "index_performance_review", "main_index_tracking"],
)
def get_china_market_overview(
    curr_date: Annotated[str, "current date, format yyyy-mm-dd"]
) -> str:
    """
    Get a comprehensive overview of China s stock market, including quotes from major indexes.
    Covers major indices such as Shanghai Composite Index, Shenzhen Composite Component Index, GEM Index, and Science and Technology Innovation 50 Index.
    
    Args:
        curr_date (str): current date, format yyyy-mm-dd
        
    Returns:
        str: Market overview report containing major index quotes
    """
    logger.info(f"📊 [China market overview] Start getting data, Date: {curr_date}")
    
    try:
        # initialization Tushare Provider
        provider = TushareProvider()
        if not provider.connect_sync():
            return "❌ Unable to connect to Tushare data source, please check API Token configuration."
            
        api = provider.api
        
        # Define major index codes
        indices = {
            "000001.SH": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000688.SH": "科创50"
        }
        
        results = []
        
        # Get index daily data
        # Note: Tushare index_daily interface
        # 🔑 Record actual date of use for reporting purposes
        actual_dates = []
        
        for code, name in indices.items():
            try:
                # 🔑 Get the data on the specified date. If there is no data on that day (such as weekend), search forward to the nearest day.
                # Use the end_date parameter,limit=1 Will return the most recent data before the specified date
                curr_date_clean = curr_date.replace('-', '')
                df = api.index_daily(ts_code=code, end_date=curr_date_clean, limit=1)
                
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    trade_date = row['trade_date']
                    close = row['close']
                    change = row['change']
                    pct_chg = row['pct_chg']
                    vol = row['vol']
                    amount = row['amount']
                    
                    # Format date
                    trade_date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                    actual_dates.append(trade_date_str)
                    
                    # 🔑 If the actual date does not match the requested date, state this in the report
                    date_note = ""
                    if trade_date_str != curr_date:
                        date_note = f" (Note:{curr_date} No data, use the latest trading day {trade_date_str})"
                    
                    # Format up/down symbols
                    sign = "+" if change > 0 else ""
                    
                    item = f"""### {name} ({code})
- **日期**: {trade_date_str}{date_note}
- **收盘**: {close:.2f}
- **涨跌**: {sign}{change:.2f} ({sign}{pct_chg:.2f}%)
- **成交量**: {vol/10000:.2f} 万手
- **成交额**: {amount/100000:.2f} 亿元
"""
                    results.append(item)
                else:
                    results.append(f"### {name} ({code})\n- No data yet (request date:{curr_date}) ")
                    
            except Exception as e:
                logger.error(f"❌ 获取指数 {name} 失败: {e}")
                results.append(f"### {name} ({code})\n- Failed to obtain: {e}")
        
        # 🔑 If the actual date is consistent for all indices, use the actual date; otherwise use the requested date
        if actual_dates and len(set(actual_dates)) == 1:
            actual_date = actual_dates[0]
            date_note = f" (Request date:{curr_date}, Actual use:{actual_date}) " if actual_date != curr_date else ""
        else:
            actual_date = curr_date
            date_note = ""
        
        # Portfolio Report
        report = f"""# 中国市场概览
**分析基准日期**: {curr_date}{date_note}

## 📉 主要指数表现
{chr(10).join(results)}

---
*数据来源: Tushare Pro*
"""
        logger.info(f"✅ [China market overview] get success")
        return report
        
    except Exception as e:
        error_msg = f"中国市场概览获取失败: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return error_msg

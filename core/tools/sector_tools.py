"""
Sector analysis tool function

Provides sector performance analysis, rotation identification, peer comparison and other functions
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================
# MongoDB Cache configuration — Section list & Constituent stocks (TTL=30 days)
# ============================================================

SECTOR_CACHE_COLLECTION = "ths_sector_cache"
SECTOR_CACHE_TTL_DAYS = 30

_sector_cache_db = None   # Lazy initialization


def _get_sector_cache_db():
    """Get a synchronous MongoDB connection (for caching reads and writes)"""
    global _sector_cache_db
    if _sector_cache_db is not None:
        return _sector_cache_db
    try:
        from app.core.database import get_mongo_db_sync
        _sector_cache_db = get_mongo_db_sync()
        return _sector_cache_db
    except Exception:
        return None


def _read_sector_cache(cache_key: str) -> Optional[pd.DataFrame]:
    """Read the section cache from MongoDB and return after expiration None"""
    db = _get_sector_cache_db()
    if db is None:
        return None
    try:
        doc = db[SECTOR_CACHE_COLLECTION].find_one(
            {"cache_key": cache_key, "expires_at": {"$gt": datetime.now(timezone.utc)}}
        )
        if doc and doc.get("data"):
            df = pd.DataFrame(doc["data"])
            logger.debug(f"📦 板块缓存命中: {cache_key} ({len(df)} 条)")
            return df
    except Exception as e:
        logger.debug(f"读取板块缓存失败: {e}")
    return None


def _write_sector_cache(cache_key: str, cache_type: str, df: pd.DataFrame):
    """Write section cache to MongoDB (upsert)"""
    db = _get_sector_cache_db()
    if db is None:
        return
    try:
        now = datetime.now(timezone.utc)
        db[SECTOR_CACHE_COLLECTION].update_one(
            {"cache_key": cache_key},
            {"$set": {
                "cache_type": cache_type,
                "data": df.to_dict("records"),
                "count": len(df),
                "updated_at": now,
                "expires_at": now + timedelta(days=SECTOR_CACHE_TTL_DAYS),
            }},
            upsert=True,
        )
        logger.info(f"✅ 板块缓存已更新: {cache_key} ({len(df)} 条, TTL={SECTOR_CACHE_TTL_DAYS}天)")
    except Exception as e:
        logger.debug(f"写入板块缓存失败: {e}")


async def _get_ths_index_list_cached(provider, index_type: str) -> Optional[pd.DataFrame]:
    """Obtain section list with MongoDB cache (cache for 30 days)"""
    cache_key = f"sector_list_{index_type}"

    # 1. read cache
    cached = _read_sector_cache(cache_key)
    if cached is not None:
        return cached

    # 2. tune Tushare API
    df = await provider.get_ths_index_list(index_type=index_type)
    if df is not None and not df.empty:
        _write_sector_cache(cache_key, "sector_list", df)
    return df


async def _get_ths_member_cached(provider, ts_code: str) -> Optional[pd.DataFrame]:
    """Sector component acquisition with MongoDB cache (forward: sector→Constituent stocks, cached for 30 days)"""
    cache_key = f"sector_member_{ts_code}"

    # 1. read cache
    cached = _read_sector_cache(cache_key)
    if cached is not None:
        return cached

    # 2. tune Tushare API
    df = await provider.get_ths_member(ts_code=ts_code)
    if df is not None and not df.empty:
        _write_sector_cache(cache_key, "sector_member", df)
    return df


async def _get_ths_member_reverse_cached(provider, con_code: str) -> Optional[pd.DataFrame]:
    """Obtain the sector to which individual stocks belong with MongoDB cache (reverse: individual stocks→The section to which it belongs, cached for 30 days)"""
    cache_key = f"stock_sectors_{con_code}"

    # 1. read cache
    cached = _read_sector_cache(cache_key)
    if cached is not None:
        return cached

    # 2. tune Tushare API
    df = await provider.get_ths_member(con_code=con_code)
    if df is not None and not df.empty:
        _write_sector_cache(cache_key, "stock_sectors", df)
    return df


def _get_tushare_provider():
    """Delayed import acquisition Tushare Provider"""
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    return get_tushare_provider()


def _clean_date_string(date_str: str) -> str:
    """Clean date string, remove possible time part"""
    if not date_str:
        return date_str
    return date_str.split()[0] if ' ' in date_str else date_str


async def _get_latest_trade_date(trade_date: str) -> str:
    """
    Get the latest available transaction date

    Obtain the data of the last 8 days at one time, and take the last valid transaction date

    Args:
        trade_date: original transaction date (YYYY-MM-DD or YYYYMMDD)

    Returns:
        Latest available transaction date (YYYYMMDD Format)
    """
    provider = _get_tushare_provider()
    # Clean date string, remove possible time part
    trade_date_clean = _clean_date_string(trade_date).replace('-', '')

    try:
        # Calculate date 8 days ago
        end_date = datetime.strptime(trade_date_clean, '%Y%m%d')
        start_date = end_date - timedelta(days=8)
        start_date_str = start_date.strftime('%Y%m%d')

        # Get the Shanghai Composite Index data for the last 8 days at one time
        df = await provider.get_index_daily(
            ts_code='000001.SH',
            start_date=start_date_str,
            end_date=trade_date_clean,
            use_cache=False  # No caching is used to ensure the latest data is obtained
        )

        if df is not None and not df.empty:
            # Sort by date, take the last item (latest trading day)
            df = df.sort_values('trade_date', ascending=False)
            latest_trade_date = str(df.iloc[0]['trade_date'])

            if latest_trade_date != trade_date_clean:
                logger.info(f"📅 {trade_date} No data, use the latest trading day {latest_trade_date}")

            return latest_trade_date

        # If neither is found, return the original date
        logger.warning(f"⚠️ Unable to find valid trading day, use original date {trade_date_clean}")
        return trade_date_clean

    except Exception as e:
        logger.error(f"❌ 获取最新交易日失败: {e}")
        return trade_date_clean


async def get_stock_sector_info(ticker: str) -> Dict[str, Any]:
    """
    Get sector information to which a stock belongs
    
    Args:
        ticker: Stock code (such as 000001 or 000001.SZ)
    
    Returns:
        Dictionary containing list of industries and sectors
    """
    provider = _get_tushare_provider()
    
    result = {
        "ticker": ticker,
        "industry": None,
        "sectors": [],
        "error": None
    }
    
    try:
        # 1. Get industry classification
        industry = await provider.get_stock_industry(ticker)
        result["industry"] = industry
        
        # 2. Get the sector you belong to (flush concept/industry sector)— With cache
        ts_code = provider._normalize_ts_code(ticker)
        sectors_df = await _get_ths_member_reverse_cached(provider, con_code=ts_code)

        if sectors_df is not None and not sectors_df.empty:
            result["sectors"] = sectors_df.to_dict('records')
        
        return result
        
    except Exception as e:
        logger.error(f"获取股票板块信息失败: {e}")
        result["error"] = str(e)
        return result


async def get_sector_performance(
    ticker: str, 
    trade_date: str,
    lookback_days: int = 20
) -> str:
    """
    Analyze the overall performance of the industry to which the target stock belongs
    
    Args:
        ticker: Stock code
        trade_date: transaction date (YYYY-MM-DD or YYYYMMDD)
        lookback_days: Number of days to look back
    
    Returns:
        Sector performance analysis report (string)
    """
    provider = _get_tushare_provider()
    
    try:
        # 1. Get the industry to which the stock belongs
        industry = await provider.get_stock_industry(ticker)
        if not industry:
            return f"⚠️ 无法获取股票 {ticker} 的行业信息"
        
        # 2. Get the sector to which the stock belongs — With cache
        ts_code = provider._normalize_ts_code(ticker)
        sectors_df = await _get_ths_member_reverse_cached(provider, con_code=ts_code)
        
        # 3. Calculate date range
        # Clean date string, remove possible time part
        trade_date_clean = _clean_date_string(trade_date).replace('-', '')
        end_date = datetime.strptime(trade_date_clean, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 10)  # Take extra days to deal with non-trading days
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = trade_date_clean
        
        report_lines = [
            f"📊 板块表现分析报告",
            f"{'='*50}",
            f"🎯 目标股票: {ticker}",
            f"🏭 所属行业: {industry}",
            f"📅 分析日期: {trade_date}",
            f"📆 回看周期: {lookback_days} 交易日",
            "",
        ]
        
        # 4. Analyze sector performance
        if sectors_df is not None and not sectors_df.empty:
            # ths_member The reverse check only contains the section code and the construction code→Name Mapping (N Industry Segment + I industry index)
            name_map = {}
            for idx_type in ["N", "I"]:
                ldf = await _get_ths_index_list_cached(provider, idx_type)
                if ldf is not None and not ldf.empty:
                    for _, r in ldf.iterrows():
                        name_map[r['ts_code']] = r['name']

            sector_count = len(sectors_df)
            report_lines.append(f"📌 所属板块数: {sector_count} 个")
            report_lines.append("")
            report_lines.append("【板块涨跌幅排行】")
            
            # Get market data for each sector
            sector_performance = []
            for _, row in sectors_df.head(10).iterrows():  # Analyze up to 10 sectors
                sector_code = row.get('ts_code')
                if not sector_code:
                    continue
                
                daily_df = await provider.get_ths_daily(
                    ts_code=sector_code,
                    start_date=start_date_str,
                    end_date=end_date_str
                )
                
                if daily_df is not None and not daily_df.empty:
                    # Calculate the cumulative increase and decrease
                    daily_df = daily_df.sort_values('trade_date')
                    if len(daily_df) >= 2:
                        first_close = daily_df.iloc[0]['close']
                        last_close = daily_df.iloc[-1]['close']
                        pct_change = ((last_close - first_close) / first_close) * 100
                        
                        # Get the latest one-day price increase and decrease
                        today_pct = daily_df.iloc[-1].get('pct_change', 0)
                        
                        sector_performance.append({
                            'code': sector_code,
                            'name': name_map.get(sector_code) or row.get('name', sector_code),
                            'period_pct': round(pct_change, 2),
                            'today_pct': round(today_pct, 2) if today_pct else 0
                        })
            
            # Sort by cumulative increase
            sector_performance.sort(key=lambda x: x['period_pct'], reverse=True)
            
            for i, sp in enumerate(sector_performance, 1):
                trend = "📈" if sp['period_pct'] > 0 else "📉"
                report_lines.append(
                    f"  {i}. {sp['name']}: {trend} {sp['period_pct']:+.2f}% "
                    f"(today: {sp['today_pct']:+.2f}%)"
                )
        
        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"板块表现分析失败: {e}")
        return f"❌ 板块表现分析失败: {e}"


async def get_sector_rotation(trade_date: str, top_n: int = 10,
                              lookback_days: int = 1) -> str:
    """
    Identify sector rotation trends

    Use industry sections(moneyflow_ind_ths)and concept section(moneyflow_cnt_ths)capital flow data,
    Analyze the direction of fund rotation in the sector. Supports single-day and multi-day (cumulative) modes.

    Args:
        trade_date: closing date
        top_n: Return the first N sections
        lookback_days: Looking back the number of days,1=On that day only,>1=Accumulated multi-day aggregation

    Returns:
        Sector rotation analysis report
    """
    provider = _get_tushare_provider()

    try:
        # Get the latest available trading day
        trade_date_clean = await _get_latest_trade_date(trade_date)
        trade_date_fmt = f"{trade_date_clean[:4]}-{trade_date_clean[4:6]}-{trade_date_clean[6:8]}"

        # ── Determine date range ──
        is_multi_day = lookback_days > 1
        if is_multi_day:
            from datetime import datetime, timedelta
            end_dt = datetime.strptime(trade_date_clean, '%Y%m%d')
            start_dt = end_dt - timedelta(days=lookback_days)
            start_date_str = start_dt.strftime('%Y%m%d')
            end_date_str = trade_date_clean
            period_label = f"{start_dt.strftime('%Y-%m-%d')} ~ {trade_date_fmt}（约{lookback_days}天）"
        else:
            start_date_str = None
            end_date_str = None
            period_label = trade_date_fmt

        report_lines = [
            f"🔄 Sector capital flow and rotation analysis",
            f"{'='*50}",
            f"📅 分析周期: {period_label}",
            f"📊 模式: {'累计聚合' if is_multi_day else '单日快照'}",
            "",
        ]

        # ── Pull data ──
        if is_multi_day:
            ind_df = await provider.get_moneyflow_ind_ths(
                start_date=start_date_str, end_date=end_date_str)
            cnt_df = await provider.get_moneyflow_cnt_ths(
                start_date=start_date_str, end_date=end_date_str)
        else:
            ind_df = await provider.get_moneyflow_ind_ths(
                trade_date=trade_date_clean)
            cnt_df = await provider.get_moneyflow_cnt_ths(
                trade_date=trade_date_clean)

        # ── 1. Industry sector capital flows ──
        if ind_df is not None and not ind_df.empty:
            if is_multi_day:
                trade_days = ind_df['trade_date'].nunique()
                report_lines.append(f"  ℹ️ 行业板块数据覆盖 {trade_days} 个交易日")
                report_lines.append("")
                ind_agg = _aggregate_multi_day(ind_df, name_col='industry')
            else:
                ind_agg = None

            report_lines.append(" [🏭 Industry sector — Net capital inflow TOP]")
            if is_multi_day and ind_agg is not None:
                _append_multi_day_rows(report_lines, ind_agg, top_n, ascending=False)
            else:
                _append_single_day_rows(report_lines, ind_df, top_n,
                                        name_col='industry', ascending=False)

            report_lines.append("")
            report_lines.append(" [🏭 Industry sector — Net outflow of funds TOP]")
            if is_multi_day and ind_agg is not None:
                _append_multi_day_rows(report_lines, ind_agg, top_n, ascending=True)
            else:
                _append_single_day_rows(report_lines, ind_df, top_n,
                                        name_col='industry', ascending=True)
            report_lines.append("")
        else:
            report_lines.append("⚠️ There is no data on capital flows of industry sectors.")
            report_lines.append("")

        # ── 2. Concept sector capital flow ──
        if cnt_df is not None and not cnt_df.empty:
            if is_multi_day:
                trade_days = cnt_df['trade_date'].nunique()
                report_lines.append(f"  ℹ️ 概念板块数据覆盖 {trade_days} 个交易日")
                report_lines.append("")
                cnt_agg = _aggregate_multi_day(cnt_df, name_col='name')
            else:
                cnt_agg = None

            report_lines.append(" [💡 Concept section — Net capital inflow TOP]")
            if is_multi_day and cnt_agg is not None:
                _append_multi_day_rows(report_lines, cnt_agg, top_n, ascending=False)
            else:
                _append_single_day_rows(report_lines, cnt_df, top_n,
                                        name_col='name', ascending=False)

            report_lines.append("")
            report_lines.append(" [💡 Concept section — Net outflow of funds TOP]")
            if is_multi_day and cnt_agg is not None:
                _append_multi_day_rows(report_lines, cnt_agg, top_n, ascending=True)
            else:
                _append_single_day_rows(report_lines, cnt_df, top_n,
                                        name_col='name', ascending=True)
            report_lines.append("")
        else:
            report_lines.append("⚠️ There is currently no data on capital flows in the concept sector.")
            report_lines.append("")

        # ── 3. rotation judgment ──
        report_lines.append("【🎯 轮动判断】")
        if ind_df is not None and not ind_df.empty:
            if is_multi_day and ind_agg is not None:
                total_net = ind_agg['cum_net'].sum()
                inflow_count = (ind_agg['cum_net'] > 0).sum()
                outflow_count = (ind_agg['cum_net'] < 0).sum()
                label = "累计"
            else:
                total_net = ind_df['net_amount'].sum()
                inflow_count = (ind_df['net_amount'] > 0).sum()
                outflow_count = (ind_df['net_amount'] < 0).sum()
                label = "当日"

            if total_net > 0 and inflow_count > outflow_count * 1.5:
                report_lines.append(f"  • {label}The overall funding level of the industry is relatively high, with most sectors receiving net inflows")
            elif total_net < 0 and outflow_count > inflow_count * 1.5:
                report_lines.append(f"  • {label}The overall financial situation of the industry is bearish, and most sectors have net outflows of funds.")
            else:
                report_lines.append(f"  • {label}The capital inflow and outflow of the industry is differentiated, and the sector rotation is obvious.")
            report_lines.append(
                f"  • 行业板块{label}净流入: {inflow_count} 个 | 净流出: {outflow_count} 个 | "
                f"Total net amount: {total_net:+.2f}billion"
            )

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"板块轮动分析失败: {e}")
        return f"❌ 板块轮动分析失败: {e}"


# ── Multi-day aggregation helper function ──

def _aggregate_multi_day(df, name_col: str):
    """
    Aggregate multi-day sector capital flow data into a cumulative value.

    Returns a DataFrame, sorted in descending order by cum_net, containing:
    - name: Section name
    - cum_net: Cumulative net inflow(billion)
    - avg_net: average daily net inflow(billion)
    - inflow_days: Net inflow days
    - total_days: Total trading days
    - avg_pct: Average increase or decrease during the period(%)
    """
    import pandas as pd

    total_days = df['trade_date'].nunique()

    agg = df.groupby(name_col).agg(
        cum_net=('net_amount', 'sum'),
        avg_net=('net_amount', 'mean'),
        inflow_days=('net_amount', lambda x: (x > 0).sum()),
        avg_pct=('pct_change', 'mean'),
    ).reset_index()

    agg = agg.rename(columns={name_col: 'name'})
    agg['total_days'] = total_days
    agg = agg.sort_values('cum_net', ascending=False)
    return agg


def _append_multi_day_rows(report_lines: list, agg_df, top_n: int,
                           ascending: bool):
    """向报告追加多日聚合排名行"""
    if ascending:
        rows = agg_df.tail(top_n).iloc[::-1]
    else:
        rows = agg_df.head(top_n)

    for i, row in enumerate(rows.itertuples(), 1):
        name = getattr(row, 'name', '')
        cum = getattr(row, 'cum_net', 0) or 0
        avg = getattr(row, 'avg_net', 0) or 0
        inflow_d = getattr(row, 'inflow_days', 0)
        total_d = getattr(row, 'total_days', 1)
        avg_pct = getattr(row, 'avg_pct', 0) or 0
        trend = "🔴" if cum > 0 else "🟢"
        report_lines.append(
            f"  {i}. {name}: {trend} 累计{cum:+.2f}亿 "
            f"(Daily average{avg:+.2f}billion, net inflow{inflow_d}/{total_d}day, "
            f"average increase or decrease{avg_pct:+.2f}%)"
        )


def _append_single_day_rows(report_lines: list, df, top_n: int,
                            name_col: str, ascending: bool):
    """向报告追加单日排名行"""
    sorted_df = df.sort_values('net_amount', ascending=ascending)
    if ascending:
        rows = sorted_df.head(top_n)
    else:
        rows = sorted_df.head(top_n)

    # For net outflow TOP, use ascending=True Take after sorting head
    if ascending:
        sorted_df_asc = df.sort_values('net_amount', ascending=True)
        rows = sorted_df_asc.head(top_n)
    else:
        sorted_df_desc = df.sort_values('net_amount', ascending=False)
        rows = sorted_df_desc.head(top_n)

    for i, row in enumerate(rows.itertuples(), 1):
        name = getattr(row, name_col, getattr(row, 'ts_code', ''))
        net_amt = getattr(row, 'net_amount', 0) or 0
        pct = getattr(row, 'pct_change', 0) or 0
        lead = getattr(row, 'lead_stock', '')
        trend = "🔴" if net_amt > 0 else "🟢"
        lead_str = f" | 领涨: {lead}" if lead else ""
        report_lines.append(
            f"  {i}. {name}: {trend} {net_amt:+.2f}亿  涨跌幅: {pct:+.2f}%{lead_str}"
        )


async def get_peer_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 10
) -> str:
    """
    Comparative analysis of competitors in the same industry

    Compare the performance of the target stock with other stocks in the same industry

    Args:
        ticker: target stock code
        trade_date: transaction date
        top_n: Number of peer companies compared

    Returns:
        Comparative analysis report of peers
    """
    provider = _get_tushare_provider()

    try:
        # 1. Get the industry to which the stock belongs
        industry = await provider.get_stock_industry(ticker)
        if not industry:
            return f"⚠️ 无法获取股票 {ticker} 的行业信息"

        # 2. Get the latest available trading day
        trade_date_clean = await _get_latest_trade_date(trade_date)
        trade_date_formatted = f"{trade_date_clean[:4]}-{trade_date_clean[4:6]}-{trade_date_clean[6:8]}"

        # 3. Obtain daily basic data of stocks in the same industry
        industry_df = await provider.get_sector_stocks_daily_basic(
            industry=industry,
            trade_date=trade_date_clean
        )

        report_lines = [
            f"📊 同业对比分析报告",
            f"{'='*50}",
            f"🎯 目标股票: {ticker}",
            f"🏭 所属行业: {industry}",
            f"📅 分析日期: {trade_date_formatted}",
            "",
        ]

        if industry_df is None or industry_df.empty:
            report_lines.append(f"⚠️ 暂无行业 {industry} 的对比数据")
            return "\n".join(report_lines)

        # 3. Sort by market value, take TOP N
        industry_df = industry_df.sort_values('total_mv', ascending=False)
        total_count = len(industry_df)
        report_lines.append(f"📌 行业内上市公司: {total_count} 家")
        report_lines.append("")

        # 4. Find data for the target stock
        ts_code = provider._normalize_ts_code(ticker)
        target_row = industry_df[industry_df['ts_code'] == ts_code]

        if not target_row.empty:
            target = target_row.iloc[0]
            target_rank = (industry_df['ts_code'] == ts_code).idxmax()
            target_rank_num = industry_df.index.get_loc(target_rank) + 1

            report_lines.append("【🎯 目标股票指标】")
            report_lines.append(f"  • 股票名称: {target.get('name', ticker)}")
            report_lines.append(f"  • 市值排名: {target_rank_num}/{total_count}")
            report_lines.append(f"  • 总市值: {target.get('total_mv', 0)/10000:.2f}亿")
            report_lines.append(f"  • PE(TTM): {target.get('pe_ttm', 'N/A')}")
            report_lines.append(f"  • PB: {target.get('pb', 'N/A')}")
            report_lines.append(f"  • 换手率: {target.get('turnover_rate', 'N/A')}%")
            report_lines.append("")

        # 5. Comparison of industry leaders
        report_lines.append(f"【🏆 行业龙头TOP{min(top_n, total_count)}】")
        for i, row in enumerate(industry_df.head(top_n).itertuples(), 1):
            name = getattr(row, 'name', getattr(row, 'ts_code', ''))
            total_mv = getattr(row, 'total_mv', 0) / 10000  # Convert to billions
            pe_ttm = getattr(row, 'pe_ttm', 'N/A')
            pb = getattr(row, 'pb', 'N/A')

            marker = "⭐" if getattr(row, 'ts_code', '') == ts_code else "  "
            report_lines.append(
                f"{marker}{i}. {name}: 市值{total_mv:.0f}亿 | "
                f"PE: {pe_ttm} | PB: {pb}"
            )

        # 6. Calculate industry statistics (filter out NaN values)
        import pandas as pd
        report_lines.append("")
        report_lines.append("【📈 行业统计】")

        pe_median = industry_df['pe_ttm'].dropna().median()
        pb_median = industry_df['pb'].dropna().median()
        pe_mean = industry_df['pe_ttm'].dropna().mean()
        pb_mean = industry_df['pb'].dropna().mean()

        if pd.notna(pe_median):
            report_lines.append(f"  • PE中位数: {pe_median:.2f} | PE均值: {pe_mean:.2f}")
        else:
            report_lines.append(f"  • PE data: No valid data yet")

        if pd.notna(pb_median):
            report_lines.append(f"  • PB中位数: {pb_median:.2f} | PB均值: {pb_mean:.2f}")
        else:
            report_lines.append(f"  • PB data: No valid data yet")

        # 7. The valuation position of the target stock in the industry
        if not target_row.empty:
            target_pe = target.get('pe_ttm')
            target_pb = target.get('pb')

            report_lines.append("")
            report_lines.append("【📊 估值评价】")

            # Handle PE valuation (check if None or NaN)
            if pd.notna(target_pe) and pd.notna(pe_median):
                if target_pe < pe_median * 0.8:
                    report_lines.append(f"  • PE估值: {target_pe:.2f}，低于行业中位数({pe_median:.1f})，估值偏低")
                elif target_pe > pe_median * 1.2:
                    report_lines.append(f"  • PE估值: {target_pe:.2f}，高于行业中位数({pe_median:.1f})，估值偏高")
                else:
                    report_lines.append(f"  • PE估值: {target_pe:.2f}，接近行业中位数({pe_median:.1f})，估值合理")
            else:
                report_lines.append(f"  • PE Valuation: Missing data (may be a loss or the data has not been updated)")

            # Handle PB estimates (check if None or NaN)
            if pd.notna(target_pb) and pd.notna(pb_median):
                if target_pb < pb_median * 0.8:
                    report_lines.append(f"  • PB估值: {target_pb:.2f}，低于行业中位数({pb_median:.1f})，估值偏低")
                elif target_pb > pb_median * 1.2:
                    report_lines.append(f"  • PB估值: {target_pb:.2f}，高于行业中位数({pb_median:.1f})，估值偏高")
                else:
                    report_lines.append(f"  • PB估值: {target_pb:.2f}，接近行业中位数({pb_median:.1f})，估值合理")
            else:
                report_lines.append(f"  • PB估值: 数据缺失")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"同业对比分析失败: {e}")
        return f"❌ 同业对比分析失败: {e}"


async def get_industry_top_companies(
    ticker: str,
    top_n: int = 5,
) -> str:
    """
    Get the list of TOP N companies in the same industry (light version, automatically get the latest trading day)

    Args:
        ticker: Target stock code (such as 600519 or 600519.SH)
        top_n: Returns the top N companies, default 5

    Returns:
        Brief list of TOP N companies in the same industry (code, name, market capitalization, PE, PB)
    """
    provider = _get_tushare_provider()

    try:
        # 1. Get the industry to which the stock belongs
        industry = await provider.get_stock_industry(ticker)
        if not industry:
            return f"⚠️ 无法获取股票 {ticker} 的行业信息"

        # 2. Automatically retrieve the latest trading day (use today to search forward)
        today_str = datetime.now().strftime('%Y-%m-%d')
        trade_date_clean = await _get_latest_trade_date(today_str)

        # 3. Obtain daily basic data of stocks in the same industry
        industry_df = await provider.get_sector_stocks_daily_basic(
            industry=industry,
            trade_date=trade_date_clean
        )

        if industry_df is None or industry_df.empty:
            return f"⚠️ 暂无行业「{industry}」在 {trade_date_clean} 的数据"

        # 4. Sort by market capitalization
        industry_df = industry_df.sort_values('total_mv', ascending=False)
        total_count = len(industry_df)
        top_n_actual = min(top_n, total_count)

        # 5. Find the ranking of target stocks
        ts_code = provider._normalize_ts_code(ticker)
        target_rank = 0
        target_row = industry_df[industry_df['ts_code'] == ts_code]
        if not target_row.empty:
            target_rank = industry_df.index.get_loc(target_row.index[0]) + 1

        trade_date_formatted = f"{trade_date_clean[:4]}-{trade_date_clean[4:6]}-{trade_date_clean[6:8]}"

        # 6. Build a profile
        lines = [
            f"🏭 {industry} — 同行业 TOP {top_n_actual} 公司",
            f"📅 数据日期: {trade_date_formatted} | 行业共 {total_count} 家",
            "",
            f"{'Ranking':>4}  {'code':<12} {'Name':<8} {'Market value(billion)':>10} {'PE':>8} {'PB':>8}",
            f"{'─'*4}  {'─'*12} {'─'*8} {'─'*10} {'─'*8} {'─'*8}",
        ]

        for i, row in enumerate(industry_df.head(top_n_actual).itertuples(), 1):
            name = str(getattr(row, 'name', ''))[:6]  # Chinese name truncation and alignment
            code = str(getattr(row, 'ts_code', ''))
            total_mv = getattr(row, 'total_mv', 0) or 0
            total_mv_yi = total_mv / 10000  # Ten thousand yuan → billion
            pe = getattr(row, 'pe_ttm', None)
            pb = getattr(row, 'pb', None)
            pe_str = f"{pe:.1f}" if pe and pe == pe else "N/A"
            pb_str = f"{pb:.2f}" if pb and pb == pb else "N/A"
            marker = "◄" if code == ts_code else " "
            lines.append(
                f"{marker}{i:>3}  {code:<12} {name:<8} {total_mv_yi:>10.1f} {pe_str:>8} {pb_str:>8}"
            )

        # 7. If the target stock is outside the TOP N, additional display
        if target_rank > top_n_actual:
            target = target_row.iloc[0]
            name = str(target.get('name', ''))[:6]
            total_mv_yi = (target.get('total_mv', 0) or 0) / 10000
            pe = target.get('pe_ttm')
            pb = target.get('pb')
            pe_str = f"{pe:.1f}" if pe and pe == pe else "N/A"
            pb_str = f"{pb:.2f}" if pb and pb == pb else "N/A"
            lines.append(f"{'─'*4}  {'─'*12} {'─'*8} {'─'*10} {'─'*8} {'─'*8}")
            lines.append(
                f" {target_rank:>3}  {ts_code:<12} {name:<8} {total_mv_yi:>10.1f} {pe_str:>8} {pb_str:>8} (目标)"
            )

        lines.append("")
        lines.append("💡 Tips: Use get_peer_comparison to obtain a more detailed peer comparison analysis report.")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Failed to obtain TOP company in the same industry: {e}")
        return f"❌ Failed to obtain TOP company in the same industry: {e}"


async def analyze_sector(ticker: str, trade_date: str) -> str:
    """
    Comprehensive sector analysis (SectorAnalyst main entrance)

    Integrate analysis from three dimensions: sector performance, rotation trends, and peer comparison

    Args:
        ticker: Target stock symbol (if it is "MARKET" Then analyze the overall sector situation)
        trade_date: transaction date

    Returns:
        Comprehensive sector analysis report
    """
    try:
        # Determine whether it is overall sector analysis or individual stock sector analysis
        is_market_analysis = (ticker == "MARKET" or not ticker)

        if is_market_analysis:
            # Overall sector analysis: only analyze sector rotation
            rotation_report = await get_sector_rotation(trade_date)

            # Portfolio Report
            full_report = [
                "=" * 60,
                "🏭 板块分析师综合报告",
                "=" * 60,
                "",
                rotation_report,
                "",
                "=" * 60,
                "📋 分析结论",
                "=" * 60,
            ]

            full_report.append("Please make a comprehensive judgment based on the above data:")
            full_report.append("1. Current market hot sectors and capital flows")
            full_report.append("2. The direction and intensity of plate rotation")
            full_report.append("3. 市场整体的风险偏好")

        else:
            # Individual stock sector analysis: analyze the sector to which the target stock belongs
            performance_task = get_sector_performance(ticker, trade_date)
            rotation_task = get_sector_rotation(trade_date)
            peer_task = get_peer_comparison(ticker, trade_date)

            performance_report, rotation_report, peer_report = await asyncio.gather(
                performance_task, rotation_task, peer_task
            )

            # Portfolio Report
            full_report = [
                "=" * 60,
                "🏭 板块分析师综合报告",
                "=" * 60,
                "",
                performance_report,
                "",
                rotation_report,
                "",
                peer_report,
                "",
                "=" * 60,
                "📋 分析结论",
                "=" * 60,
            ]

            full_report.append("Please make a comprehensive judgment based on the above data:")
            full_report.append("1. Whether the sector to which the target stock belongs is in hot rotation")
            full_report.append("2. The position and valuation level of individual stocks in the industry")
            full_report.append("3. Does the sector s capital flow support the current investment direction?")

        return "\n".join(full_report)

    except Exception as e:
        logger.error(f"综合板块分析失败: {e}")
        return f"❌ 综合板块分析失败: {e}"


# ============================================================
# Sector level tool function (use the sector name/code as the entry)
# ============================================================

# Common industry/concept aliases → Flush section keywords
# When the name of the Flush section is inconsistent with the common sense, be sure to explain (such as"Pig breeding industry"In the THS system it is called"Pork") 
# Note: The mapping target must be the real sector name keyword in the THS system
_SECTOR_SYNONYMS = {
    # Livestock and poultry breeding: THS None"Breeding/Animal Husbandry/Pigs"Sector, corresponding to A shares"Pork"
    "养殖": "猪",
    "生猪": "猪",
    "养猪": "猪",
    "畜牧": "猪",
    "猪周期": "猪",
    "肉鸡": "鸡",
    # Finance: THS None"securities"section, corresponding"Participating securities companies/Chinese securities companies"
    "证券": "券商",
    # new energy
    "新能源车": "新能源汽车",
    "电动车": "新能源汽车",
    "锂电": "锂电池",
    "锂矿": "锂",
    # Military and aerospace: THS correspondence"Military industry"
    "国防": "军工",
    "船舶": "船",
    # petrochemical
    "石化": "石油",
    # electronic
    "封测": "集成电路",
    "面板": "OLED",
    # car
    "汽车零部件": "汽车",
    "智能驾驶": "无人驾驶",
    # Agriculture
    "种业": "转基因",
    "渔业": "水产",
    # consumption
    "乳制品": "乳业",
    "奶牛": "乳",
    "零食": "休闲食品",
    "调味品": "调味",
    "家电": "家用电器",
    "中药": "中医药",
    "服装": "服饰",
    "造纸": "纸",
    # Infrastructure logistics
    "基建": "基础建设",
    "快递": "物流",
    "运营商": "电信运营",
    "水务": "污水",
    "机场": "航空",
}


def _synonym_keywords(keyword: str) -> List[str]:
    """Extended keywords: original word + Hit synonym mapping target (removing duplication and preserving order)."""
    candidates = [keyword]
    for k, v in _SECTOR_SYNONYMS.items():
        if k in keyword and v not in candidates:
            candidates.append(v)
    return candidates


def _suggest_similar_sectors(df, keyword: str, top_n: int = 5) -> List[tuple]:
    """Fuzzy recommendation with overlapping characters: When the section name and keyword overlap by at least 2 characters, recommendations are made in descending order of the number of overlaps."""
    if df is None or df.empty:
        return []
    chars = set(keyword)
    scored = []
    for _, row in df.iterrows():
        name = str(row['name'])
        overlap = len(chars & set(name))
        if overlap >= 2:
            scored.append((overlap, str(row['ts_code']), name, row.get('count', 'N/A')))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]


async def _sector_not_found_hint(provider, keyword: str) -> str:
    """Candidate suggestion text is generated when a section is missed to help the caller (LLM) self-correct the section name."""
    # 1. Synonyms retry prompt
    synonym_names = []
    for idx_type in ["N", "I", "S"]:
        df = await _get_ths_index_list_cached(provider, idx_type)
        if df is None or df.empty:
            continue
        for kw in _synonym_keywords(keyword)[1:]:
            matched = df[df['name'].str.contains(kw, case=False, na=False)]
            for _, row in matched.head(3).iterrows():
                synonym_names.append(f"{row['name']} ({row['ts_code']})")
        if synonym_names:
            break
    # 2. Character overlap candidates
    if not synonym_names:
        for idx_type in ["N", "I", "S"]:
            df = await _get_ths_index_list_cached(provider, idx_type)
            if df is not None and not df.empty:
                synonym_names = [
                    f"{name} ({code})" for _o, code, name, _c in _suggest_similar_sectors(df, keyword)
                ]
                if synonym_names:
                    break
    hint = f"⚠️ 未找到包含 \"{keyword}\" 的板块。"
    if synonym_names:
        hint += f"Similar sectors:{', '.join(synonym_names[:5])}. "
    hint += "Suggestions:① Try again with the above section name;② Call search_sector to search for the correct section name;③ If the stock code is known, use get_sector_performance(ticker) Check the sector by individual stocks."
    return hint


async def search_sector(
    keyword: str,
    sector_type: str = "N",
) -> str:
    """
    Search the Flush section by name and keywords

    Args:
        keyword: Section name keywords (such as "photovoltaic", "Semiconductor", "Liquor") 
        sector_type: Section type N=Industry sector I=Industry Index S=concept R=Region, default N

    Returns:
        Matching sector list (including code, name, number of constituent stocks)
    """
    provider = _get_tushare_provider()

    try:
        df = await _get_ths_index_list_cached(provider, sector_type)
        if df is None or df.empty:
            return f"⚠️ There is no section list data (type={sector_type}) "

        # fuzzy matching
        matched = df[df['name'].str.contains(keyword, case=False, na=False)]

        if matched.empty:
            # Try other types (including Type I industry index: complete industry system,"Breeding/Condiments"etc. only exist in category I)
            for alt_type in ["I", "N", "S", "R"]:
                if alt_type == sector_type:
                    continue
                alt_df = await _get_ths_index_list_cached(provider, alt_type)
                if alt_df is not None and not alt_df.empty:
                    matched = alt_df[alt_df['name'].str.contains(keyword, case=False, na=False)]
                    if not matched.empty:
                        sector_type = alt_type
                        break

        matched_kw = keyword
        if matched.empty:
            # Synonyms: such as"Breeding"→"pig" (THS The section naming is inconsistent with common sense)
            all_types = ["N", "I", "S", "R"]
            for kw in _synonym_keywords(keyword)[1:]:
                for t in all_types:
                    df_t = df if t == sector_type else await _get_ths_index_list_cached(provider, t)
                    if df_t is None or df_t.empty:
                        continue
                    hit = df_t[df_t['name'].str.contains(kw, case=False, na=False)]
                    if not hit.empty:
                        matched = hit
                        sector_type = t
                        matched_kw = kw
                        break
                if not matched.empty:
                    break

        if matched.empty:
            return await _sector_not_found_hint(provider, keyword)

        type_map = {"N": "行业", "S": "概念", "R": "地域", "I": "行业指数"}
        title_kw = f"\"{keyword}\"" if matched_kw == keyword else f"\"{keyword}\"（按同义词\"{matched_kw}\"匹配）"
        lines = [
            f"🔍 Section search results:{title_kw}",
            f"类型: {type_map.get(sector_type, sector_type)}",
            f"匹配数量: {len(matched)} 个",
            "",
        ]
        for _, row in matched.head(15).iterrows():
            count = row.get('count', 'N/A')
            lines.append(f"  • {row['name']} ({row['ts_code']}) — 成分股 {count} 只")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"板块搜索失败: {e}")
        return f"❌ 板块搜索失败: {e}"


async def get_sector_daily(
    sector_name: str,
    trade_date: str,
    lookback_days: int = 20,
) -> str:
    """
    Get the daily market price of sector index (by sector name)

    Args:
        sector_name: Section name keywords (such as "photovoltaic", "Semiconductor") 
        trade_date: transaction date YYYY-MM-DD
        lookback_days: Number of days to look back, default 20

    Returns:
        Sector index market report
    """
    provider = _get_tushare_provider()

    try:
        # 1. Search section code
        sector_code = await _resolve_sector_code(provider, sector_name)
        if not sector_code:
            return await _sector_not_found_hint(provider, sector_name)

        sector_ts_code, sector_display_name = sector_code

        # 2. Get daily data
        trade_date_clean = _clean_date_string(trade_date).replace('-', '')
        end_date = datetime.strptime(trade_date_clean, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 10)

        daily_df = await provider.get_ths_daily(
            ts_code=sector_ts_code,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=trade_date_clean,
        )

        lines = [
            f"📊 板块行情报告",
            f"{'='*50}",
            f"🏷️ 板块: {sector_display_name} ({sector_ts_code})",
            f"📅 截至: {trade_date}",
            "",
        ]

        if daily_df is None or daily_df.empty:
            lines.append("⚠️ There is currently no daily market data for this sector.")
            return "\n".join(lines)

        daily_df = daily_df.sort_values('trade_date', ascending=True)

        # Latest day
        latest = daily_df.iloc[-1]
        lines.append("【最新行情】")
        lines.append(f"  • 收盘: {latest.get('close', 'N/A')}")
        lines.append(f"  • 涨跌幅: {latest.get('pct_change', 0):+.2f}%")
        lines.append(f"  • 成交量: {latest.get('vol', 0):.0f}")
        lines.append(f"  • 换手率: {latest.get('turnover_rate', 0):.2f}%")
        if latest.get('total_mv'):
            lines.append(f"  • 总市值: {latest['total_mv']/10000:.0f}亿")
        lines.append("")

        # interval statistics
        if len(daily_df) >= 2:
            first_close = daily_df.iloc[0]['close']
            last_close = daily_df.iloc[-1]['close']
            period_pct = ((last_close - first_close) / first_close) * 100
            max_close = daily_df['close'].max()
            min_close = daily_df['close'].min()

            lines.append(f"【近 {len(daily_df)} 个交易日统计】")
            lines.append(f"  • 区间涨跌幅: {period_pct:+.2f}%")
            lines.append(f"  • 最高: {max_close}  最低: {min_close}")
            lines.append(f"  • 平均换手率: {daily_df['turnover_rate'].mean():.2f}%")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"板块行情获取失败: {e}")
        return f"❌ 板块行情获取失败: {e}"


async def get_sector_constituents(
    sector_name: str,
    trade_date: str,
    top_n: int = 15,
) -> str:
    """
    Get the list of sector constituent stocks and their performance

    Args:
        sector_name: Section name keywords (such as "photovoltaic", "Semiconductor") 
        trade_date: transaction date YYYY-MM-DD
        top_n: Returns the top N constituent stocks, default 15

    Returns:
        List of sector constituent stocks and market capitalization/valuation rankings
    """
    provider = _get_tushare_provider()

    try:
        # 1. Search section code
        sector_code = await _resolve_sector_code(provider, sector_name)
        if not sector_code:
            return await _sector_not_found_hint(provider, sector_name)

        sector_ts_code, sector_display_name = sector_code

        # 2. Get constituent stocks — With cache
        members_df = await _get_ths_member_cached(provider, sector_ts_code)
        if members_df is None or members_df.empty:
            return f"⚠️ 板块 {sector_display_name} 暂无成分股数据"

        lines = [
            f"📋 板块成分股报告",
            f"{'='*50}",
            f"🏷️ 板块: {sector_display_name} ({sector_ts_code})",
            f"📅 日期: {trade_date}",
            f"📌 成分股总数: {len(members_df)} 只",
            "",
        ]

        # 3. Get daily basic data of constituent stocks (market capitalization, PE, PB, etc.)
        trade_date_clean = await _get_latest_trade_date(trade_date)
        daily_df = None
        try:
            daily_df = await asyncio.to_thread(
                provider.api.daily_basic,
                trade_date=trade_date_clean,
                fields='ts_code,close,pe_ttm,pb,total_mv,circ_mv,turnover_rate'
            )
        except Exception as e:
            logger.warning(f"Failed to get daily_basic: {e}")

        if daily_df is not None and not daily_df.empty:
            # Combined constituents and daily data
            member_codes = set(members_df['code'].tolist()) if 'code' in members_df.columns else set()
            if not member_codes:
                # Try using the con_code field
                member_codes = set(members_df['con_code'].tolist()) if 'con_code' in members_df.columns else set()

            # match
            matched_daily = daily_df[daily_df['ts_code'].isin(member_codes)]
            if matched_daily.empty and member_codes:
                # Maybe the code format is different, try matching without suffix
                member_codes_short = {c.split('.')[0] for c in member_codes}
                daily_df['code_short'] = daily_df['ts_code'].str.split('.').str[0]
                matched_daily = daily_df[daily_df['code_short'].isin(member_codes_short)]

            if not matched_daily.empty:
                # Sort by market capitalization
                matched_daily = matched_daily.sort_values('total_mv', ascending=False)

                lines.append(f"【市值排名 TOP{min(top_n, len(matched_daily))}】")
                # merge name
                name_map = {}
                for _, row in members_df.iterrows():
                    code = row.get('code') or row.get('con_code', '')
                    name = row.get('name', code)
                    name_map[code] = name
                    # Also save short codes
                    name_map[code.split('.')[0]] = name

                for i, row in enumerate(matched_daily.head(top_n).itertuples(), 1):
                    ts_code = getattr(row, 'ts_code', '')
                    name = name_map.get(ts_code, name_map.get(ts_code.split('.')[0], ts_code))
                    total_mv = getattr(row, 'total_mv', 0)
                    mv_yi = total_mv / 10000 if total_mv else 0
                    pe = getattr(row, 'pe_ttm', None)
                    pb = getattr(row, 'pb', None)
                    pe_str = f"{pe:.1f}" if pe and pe == pe else "N/A"
                    pb_str = f"{pb:.2f}" if pb and pb == pb else "N/A"

                    lines.append(
                        f"  {i:>2}. {name}({ts_code}): "
                        f"Market value {mv_yi:.0f}billion | PE {pe_str} | PB {pb_str}"
                    )
            else:
                lines.append("⚠️ Unable to obtain market capitalization/valuation data for constituent stocks")
                lines.append("")
                lines.append("【成分股列表】")
                for i, row in enumerate(members_df.head(top_n).iterrows(), 1):
                    _, r = row
                    code = r.get('code') or r.get('con_code', '')
                    name = r.get('name', code)
                    lines.append(f"  {i:>2}. {name} ({code})")
        else:
            lines.append("【成分股列表】")
            for i, (_, r) in enumerate(members_df.head(top_n).iterrows(), 1):
                code = r.get('code') or r.get('con_code', '')
                name = r.get('name', code)
                lines.append(f"  {i:>2}. {name} ({code})")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"板块成分股获取失败: {e}")
        return f"❌ 板块成分股获取失败: {e}"


async def analyze_sector_by_name(
    sector_name: str,
    trade_date: str,
) -> str:
    """
    Comprehensive analysis of sectors (use sector name as entry)

    Integrate sector trends, leading component stocks, and capital flows for one-stop analysis.

    Args:
        sector_name: Section name keywords (such as "photovoltaic", "Semiconductor", "Liquor") 
        trade_date: transaction date YYYY-MM-DD

    Returns:
        Comprehensive sector analysis report
    """
    try:
        # Obtain data in three dimensions in parallel
        daily_task = get_sector_daily(sector_name, trade_date)
        members_task = get_sector_constituents(sector_name, trade_date, top_n=10)
        rotation_task = get_sector_rotation(trade_date, top_n=10)

        daily_report, members_report, rotation_report = await asyncio.gather(
            daily_task, members_task, rotation_task
        )

        full_report = [
            "=" * 60,
            f"🏭 板块综合分析报告 — {sector_name}",
            "=" * 60,
            "",
            daily_report,
            "",
            members_report,
            "",
            rotation_report,
            "",
            "=" * 60,
            "📋 分析要点",
            "=" * 60,
            "Please make a comprehensive judgment based on the above data:",
            "1. The sector s recent trends and financial attention",
            "2. Valuation level of leading stocks within the sector",
            "3. The position of the sector in the overall market capital flow",
        ]

        return "\n".join(full_report)

    except Exception as e:
        logger.error(f"板块综合分析失败: {e}")
        return f"❌ 板块综合分析失败: {e}"


# ============================================================
# Helper function
# ============================================================

async def _resolve_sector_code(
    provider, keyword: str
) -> Optional[tuple]:
    """
    Search sections based on keywords and return (ts_code, name) or None.
    The original word takes precedence N(Industry sector)/I(Industry Index)/S(concept)/R(Region) Search in four categories,
    If all misses, try again using the synonym list (e.g."Lithium battery"→"Lithium battery") . 
    Note: Category I (starting with 881/884) is a complete industry index system (about 1100).
    "Breeding/Pigs/Condiments/Ports"Such industries only exist in Category I and cannot be omitted.
    """
    candidates = _synonym_keywords(keyword)
    for kw in candidates:  # The original word takes priority, synonyms are used
        for idx_type in ["N", "I", "S", "R"]:
            df = await _get_ths_index_list_cached(provider, idx_type)
            if df is None or df.empty:
                continue
            matched = df[df['name'].str.contains(kw, case=False, na=False)]
            if not matched.empty:
                # Take the one with the most constituents (usually the most important sector)
                if 'count' in matched.columns:
                    matched = matched.sort_values('count', ascending=False)
                top = matched.iloc[0]
                return (top['ts_code'], top['name'])
    return None


# ==================== Synchronous wrapper function ====================
# Provides a synchronization interface for LangGraph tools

def analyze_sector_sync(ticker: str, trade_date: str) -> str:
    """analyze_sector synchronized version of"""
    return asyncio.run(analyze_sector(ticker, trade_date))


def get_sector_performance_sync(ticker: str, trade_date: str, lookback_days: int = 20) -> str:
    """get_sector_performance synchronized version of"""
    return asyncio.run(get_sector_performance(ticker, trade_date, lookback_days))


def get_sector_rotation_sync(trade_date: str, top_n: int = 10,
                             lookback_days: int = 1) -> str:
    """get_sector_rotation synchronized version of"""
    return asyncio.run(get_sector_rotation(trade_date, top_n, lookback_days))


def get_peer_comparison_sync(ticker: str, trade_date: str, top_n: int = 10) -> str:
    """get_peer_comparison synchronized version of"""
    return asyncio.run(get_peer_comparison(ticker, trade_date, top_n))


def get_industry_top_companies_sync(ticker: str, top_n: int = 5) -> str:
    """get_industry_top_companies synchronized version of"""
    return asyncio.run(get_industry_top_companies(ticker, top_n))


def search_sector_sync(keyword: str, sector_type: str = "N") -> str:
    """search_sector synchronized version of"""
    return asyncio.run(search_sector(keyword, sector_type))


def get_sector_daily_sync(sector_name: str, trade_date: str, lookback_days: int = 20) -> str:
    """get_sector_daily synchronized version of"""
    return asyncio.run(get_sector_daily(sector_name, trade_date, lookback_days))


def get_sector_constituents_sync(sector_name: str, trade_date: str, top_n: int = 15) -> str:
    """get_sector_constituents synchronized version of"""
    return asyncio.run(get_sector_constituents(sector_name, trade_date, top_n))


def analyze_sector_by_name_sync(sector_name: str, trade_date: str) -> str:
    """analyze_sector_by_name synchronized version of"""
    return asyncio.run(analyze_sector_by_name(sector_name, trade_date))


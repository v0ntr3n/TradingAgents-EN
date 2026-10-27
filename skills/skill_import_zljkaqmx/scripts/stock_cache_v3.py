#!/usr/bin/env python3
"""
Stock data local cache system V3 - supports incremental updates + human readable file name
- Automatically cache downloaded K-line data
- Support incremental updates (only download new data)
- Cache files are named with stock symbols for easy identification
"""

import os
import json
import pickle
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# cache directory
_STOCK_DIR = Path(__file__).parent
_BASE_DIR = _STOCK_DIR.parent
CACHE_DIR = _BASE_DIR / ".stock_cache"
CACHE_DIR.mkdir(exist_ok=True)

def normalize_symbol(symbol):
    """Standardized ticker format"""
    # Remove prefixes and unify format
    symbol = str(symbol).strip().lower()
    symbol = re.sub(r'^(sh|sz)', '', symbol)
    return symbol

def get_cache_filename(symbol, adjust):
    """Generate human-readable cache filenames"""
    symbol_clean = normalize_symbol(symbol)
    return f"{symbol_clean}_{adjust}"

def get_cache_path(symbol, adjust):
    """Get cache file path"""
    filename = get_cache_filename(symbol, adjust)
    return CACHE_DIR / f"{filename}.pkl"

def get_metadata_path(symbol, adjust):
    """Get metadata file path"""
    filename = get_cache_filename(symbol, adjust)
    return CACHE_DIR / f"{filename}_meta.json"

def load_cache_metadata(symbol, adjust):
    """Load cache metadata"""
    meta_path = get_metadata_path(symbol, adjust)
    
    if not meta_path.exists():
        return None
    
    try:
        with open(meta_path, 'r') as f:
            return json.load(f)
    except:
        return None

def load_cached_data(symbol, adjust):
    """Load complete data from cache"""
    cache_path = get_cache_path(symbol, adjust)
    symbol_clean = normalize_symbol(symbol)
    
    if not cache_path.exists():
        return None
    
    try:
        with open(cache_path, 'rb') as f:
            df = pickle.load(f)
        
        # Unified column name format
        column_mapping = {
            'Date': 'date', 'date': 'date',
            'Open': 'open', 'open': 'open',
            'close': 'close', 'close': 'close',
            'highest': 'high', 'high': 'high',
            'lowest': 'low', 'low': 'low',
            'turnover rate': 'turnover', 'turnover': 'turnover',
            'Volume': 'volume', 'volume': 'volume',
            'Turnover': 'amount', 'amount': 'amount'
        }
        
        # Rename columns
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        print(f"📂 Load from cache: {symbol_clean} ({len(df)} OK)")
        return df
    except Exception as e:
        print(f"⚠️ Cache loading failed: {e}")
        return None

def save_cache(df, symbol, adjust):
    """Save data to cache"""
    cache_path = get_cache_path(symbol, adjust)
    meta_path = get_metadata_path(symbol, adjust)
    symbol_clean = normalize_symbol(symbol)
    
    # save data
    with open(cache_path, 'wb') as f:
        pickle.dump(df, f)
    
    # Save metadata
    latest_date = df['date'].max() if 'date' in df.columns else str(datetime.now().date())
    earliest_date = df['date'].min() if 'date' in df.columns else str(datetime.now().date())
    
    metadata = {
        'symbol': symbol_clean,
        'adjust': adjust,
        'cached_at': datetime.now().isoformat(),
        'latest_date': str(latest_date),
        'earliest_date': str(earliest_date),
        'rows': len(df),
        'cache_file': str(cache_path),
        'version': '3.0'
    }
    
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"💾 Cached: {cache_path.name} ({len(df)} OK, {earliest_date} ~ {latest_date})")

def fetch_with_retry(symbol_ak, start_date, end_date, adjust="qfq", max_retries=3):
    """
    Stock data acquisition function with retry mechanism (using Sina Finance interface)
    
    Parameters:
        symbol_ak: akshare Format stock code (such as sh000001)
        start_date: start date
        end_date: end date
        adjust: Restoration method
        max_retries: Maximum number of retries
    
    Returns:
        DataFrame with stock data
    """
    import akshare as ak
    
    for attempt in range(max_retries):
        try:
            # Use Sina Finance interface
            # Note: There may be problems with the reweighting data of the Shanghai Composite Index (sh000001) and require special processing.
            df = ak.stock_zh_a_daily(symbol=symbol_ak, start_date=start_date, end_date=end_date, adjust=adjust)
            
            return df
        except Exception as e:
            # If it is a problem with the re-righting data of the Shanghai Composite Index, try to obtain the non-re-righting data.
            if symbol_ak == 'sh000001' and adjust in ['qfq', 'hfq'] and 'Length mismatch' in str(e):
                print(f"⚠️  Shanghai Composite Index re-righting data is abnormal, try to obtain non-re-righting data...")
                try:
                    df = ak.stock_zh_a_daily(symbol=symbol_ak, start_date=start_date, end_date=end_date, adjust='')
                    print(f"✅  Successfully obtained Shanghai Composite Index non-rights recovery data")
                    return df
                except Exception as e2:
                    print(f"❌  Obtaining Shanghai Composite Index non-rights data also failed.: {e2}")
                    raise e2
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # exponential backoff
                print(f"⚠️  No.{attempt+1}Failed to obtain: {e}, {wait_time}Try again in seconds...")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ all{max_retries}attempts failed: {e}")
                raise e

def get_stock_data(symbol, adjust="qfq", force_update=False):
    """
    Get stock data (supports incremental updates + readable cache filename)
    
    Parameters:
        symbol: Stock code (Such as "603716", "sh603716", "000547")
        adjust: Restoration method ("qfq" Former restoration of rights)
        force_update: Force update (ignore cache)
    
    Returns:
        DataFrame with OHLCV data
    """
    import akshare as ak
    
    symbol_clean = normalize_symbol(symbol)
    
    # Standardized code format (for akshare)
    if symbol_clean.startswith('6'):
        symbol_ak = f"sh{symbol_clean}"
    else:
        symbol_ak = f"sz{symbol_clean}"
    
    # Try loading cache
    cached_df = None
    if not force_update:
        cached_df = load_cached_data(symbol_clean, adjust)
    
    # If cached, check if incremental update is required
    if cached_df is not None and len(cached_df) > 0:
        cached_df['date'] = pd.to_datetime(cached_df['date'])
        latest_cached_date = cached_df['date'].max()
        today = pd.Timestamp.now().normalize()
        
        # Determine whether updates are needed
        need_update = False
        if today.weekday() < 5:  # Monday to Friday
            if latest_cached_date < today:
                need_update = True
                print(f"📅 cache latest: {latest_cached_date.date()}, today: {today.date()}")
                print(f"🔄 incremental update...")
        
        if not need_update:
            print(f"✅ cache is up to date")
            return cached_df
        
        # incremental update
        try:
            print(f"🌐 Download new data: {symbol_clean}...")
            # Use Sina Finance interface to obtain the latest data
            # Get the most recent year of data to ensure all new data is covered
            today = pd.Timestamp.now().normalize()
            one_year_ago = today - pd.Timedelta(days=365)
            
            new_df = ak.stock_zh_a_daily(symbol=symbol_ak, 
                                         start_date=one_year_ago.strftime('%Y%m%d'), 
                                         end_date=today.strftime('%Y%m%d'), 
                                         adjust=adjust)
            new_df['date'] = pd.to_datetime(new_df['date'])
            
            # Filter out new data
            new_data = new_df[new_df['date'] > latest_cached_date]
            
            if len(new_data) > 0:
                combined_df = pd.concat([cached_df, new_data], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['date'], keep='last')
                combined_df = combined_df.sort_values('date').reset_index(drop=True)
                
                print(f"✅ Update completed: +{len(new_data)} Article ({len(cached_df)} → {len(combined_df)})")
                save_cache(combined_df, symbol_clean, adjust)
                return combined_df
            else:
                print(f"✅ No new data")
                return cached_df
                
        except Exception as e:
            print(f"⚠️ Update failed: {e}")
            return cached_df
    
    else:
        # No caching, full download
        print(f"🌐 Download data: {symbol_clean}...")
        try:
            # Use Sina Finance interface
            # Get data for the last 5 years
            today = pd.Timestamp.now().normalize()
            five_years_ago = today - pd.Timedelta(days=5*365)
            
            df = ak.stock_zh_a_daily(symbol=symbol_ak, 
                                     start_date=five_years_ago.strftime('%Y%m%d'), 
                                     end_date=today.strftime('%Y%m%d'), 
                                     adjust=adjust)
            df['date'] = pd.to_datetime(df['date'])
            
            if len(df) > 0:
                save_cache(df, symbol_clean, adjust)
                return df
            else:
                return None
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None

def list_cached_stocks():
    """List all cached stocks"""
    stocks = []
    for meta_file in CACHE_DIR.glob("*_meta.json"):
        try:
            with open(meta_file, 'r') as f:
                metadata = json.load(f)
            
            if metadata.get('version', '').startswith('3.'):
                stocks.append({
                    'symbol': metadata['symbol'],
                    'adjust': metadata['adjust'],
                    'latest_date': metadata.get('latest_date', 'N/A'),
                    'earliest_date': metadata.get('earliest_date', 'N/A'),
                    'rows': metadata['rows'],
                    'cached_at': metadata['cached_at'][:10]
                })
        except:
            pass
    
    return sorted(stocks, key=lambda x: x['symbol'])

def get_cache_stats():
    """Get cache statistics"""
    stocks = list_cached_stocks()
    total_size = 0
    
    for stock in stocks:
        cache_path = get_cache_path(stock['symbol'], stock['adjust'])
        if cache_path.exists():
            total_size += cache_path.stat().st_size
    
    return {
        'total_stocks': len(stocks),
        'total_size_mb': total_size / (1024 * 1024),
        'stocks': stocks
    }

def delete_cache(symbol, adjust="qfq"):
    """Delete the cache of the specified stock"""
    symbol_clean = normalize_symbol(symbol)
    cache_path = get_cache_path(symbol_clean, adjust)
    meta_path = get_metadata_path(symbol_clean, adjust)
    
    deleted = False
    if cache_path.exists():
        cache_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    
    if deleted:
        print(f"🗑️ Deleted {symbol_clean} cache")
    else:
        print(f"⚠️ {symbol_clean} No cache")

def clear_all_cache():
    """clear all cache"""
    import shutil
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(exist_ok=True)
        print("🗑️ All caches cleared")

if __name__ == "__main__":
    print("=" * 70)
    print("Stock Data Cache System V3 - Readable File Name")
    print("=" * 70)
    
    # Test code input in different formats
    test_symbols = ["603716", "sh603716", "000547", "sz000547"]
    
    for symbol in test_symbols:
        print(f"\n[test] code: {symbol}")
        print(f"  Standardization: {normalize_symbol(symbol)}")
        print(f"  Cache file name: {get_cache_filename(symbol, 'qfq')}.pkl")
    
    # Show current cache
    print("\n" + "=" * 70)
    print("Current cache list")
    print("=" * 70)
    
    stats = get_cache_stats()
    print(f"\n total {stats['total_stocks']} only stocks, {stats['total_size_mb']:.2f} MB\n")
    
    for stock in stats['stocks']:
        print(f"📁 {stock['symbol']}_{stock['adjust']}.pkl")
        print(f"   data: {stock['earliest_date']} ~ {stock['latest_date']} ({stock['rows']} OK)")
        print(f"   Cache time: {stock['cached_at']}")
    
    print("\n" + "=" * 70)
    print("Test completed")
    print("=" * 70)

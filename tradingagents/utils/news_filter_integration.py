"""
News filtering integrated module
Integrate news filters into existing news acquisition processes
"""

import pandas as pd
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

def integrate_news_filtering(original_get_stock_news_em):
    """
    Decorator: Add news filtering function to get_stock_news_em function
    
    Args:
        original_get_stock_news_em: Original get_stock_news_em function
        
    Returns:
        Wrapped function with news filtering function
    """
    def filtered_get_stock_news_em(symbol: str, enable_filter: bool = True, min_score: float = 30, 
                                  use_semantic: bool = False, use_local_model: bool = False) -> pd.DataFrame:
        """
        Enhanced version of get_stock_news_em, integrated news filtering function
        
        Args:
            symbol: Stock code
            enable_filter: Whether to enable news filtering
            min_score: Minimum relevance score threshold
            use_semantic: Whether to use semantic similarity filtering
            use_local_model: Whether to use local classification model
            
        Returns:
            pd.DataFrame: Filtered news data
        """
        logger.info(f"[News filter integration] Start getting {symbol} news, filter switch: {enable_filter}")
        
        # Call the original function to get the news
        start_time = datetime.now()
        try:
            news_df = original_get_stock_news_em(symbol)
            fetch_time = (datetime.now() - start_time).total_seconds()
            
            if news_df.empty:
                logger.warning(f"[News filter integration] The original function was not obtained {symbol} news data")
                return news_df
            
            logger.info(f"[News filter integration] Original news obtained successfully: {len(news_df)}strips, time consuming: {fetch_time:.2f}seconds")
            
            # If filtering is not enabled, the original data will be returned directly.
            if not enable_filter:
                logger.info(f"[News filter integration] Filtering disabled, return raw news data")
                return news_df
            
            # Enable news filtering
            filter_start_time = datetime.now()
            
            try:
                # Import filters
                from tradingagents.utils.enhanced_news_filter import create_enhanced_news_filter
                
                # Create filter
                news_filter = create_enhanced_news_filter(
                    symbol, 
                    use_semantic=use_semantic, 
                    use_local_model=use_local_model
                )
                
                # Perform filtering
                filtered_df = news_filter.filter_news_enhanced(news_df, min_score=min_score)
                
                filter_time = (datetime.now() - filter_start_time).total_seconds()
                
                # Record filter statistics
                original_count = len(news_df)
                filtered_count = len(filtered_df)
                filter_rate = (original_count - filtered_count) / original_count * 100 if original_count > 0 else 0
                
                logger.info(f"[News filter integration] News filtering completed:")
                logger.info(f"  - original news: {original_count}Article")
                logger.info(f"  - filtered news: {filtered_count}Article")
                logger.info(f"  - Filtration rate: {filter_rate:.1f}%")
                logger.info(f"  - Filtration takes time: {filter_time:.2f}seconds")
                
                if not filtered_df.empty:
                    avg_score = filtered_df['final_score'].mean()
                    max_score = filtered_df['final_score'].max()
                    logger.info(f"  - average rating: {avg_score:.1f}")
                    logger.info(f"  - highest rating: {max_score:.1f}")
                
                return filtered_df
                
            except Exception as filter_error:
                logger.error(f"[News filter integration] News filtering failed: {filter_error}")
                logger.error(f"[News filter integration] Return original news data as backup")
                return news_df
                
        except Exception as fetch_error:
            logger.error(f"[News filter integration] Failed to get original news: {fetch_error}")
            return pd.DataFrame()  # Return empty DataFrame
    
    return filtered_get_stock_news_em


def patch_akshare_utils():
    """
    Add filtering function to get_stock_news_em function of akshare_utils module

    ⚠️ Deprecated: the akshare_utils module has been removed, this function is retained for backward compatibility only
    """
    logger.warning("[News filter integration] ⚠️ patch_akshare_utils Deprecated: akshare_utils module has been removed")


def create_filtered_realtime_news_function():
    """
    Create an enhanced version of the real-time news fetching function
    """
    def get_filtered_realtime_stock_news(ticker: str, curr_date: str, hours_back: int = 6, 
                                       enable_filter: bool = True, min_score: float = 30) -> str:
        """
        Enhanced version of real-time news acquisition function, integrated news filtering
        
        Args:
            ticker: Stock code
            curr_date: current date
            hours_back: Lookback hours
            enable_filter: Whether to enable news filtering
            min_score: Minimum relevance score threshold
            
        Returns:
            str: Formatted news reports
        """
        logger.info(f"[Enhance real-time news] Start getting {ticker} filter news")
        
        try:
            # Import original function
            from tradingagents.dataflows.news.realtime_news import get_realtime_stock_news

            # Call the original function to get the news
            original_report = get_realtime_stock_news(ticker, curr_date, hours_back)
            
            if not enable_filter:
                logger.info(f"[Enhance real-time news] Filtering disabled, return to original report")
                return original_report
            
            # If filtering is enabled and it is an A-share, try to obtain and filter again.
            if any(suffix in ticker for suffix in ['.SH', '.SZ', '.SS', '.XSHE', '.XSHG']) or \
               (not '.' in ticker and ticker.isdigit()):
                
                logger.info(f"[Enhance real-time news] A-share code detected, try to use the filtered version of Oriental Fortune News")
                
                try:
                    # NOTE: akshare_utils is deprecated, use AKShareProvider instead
                    from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

                    # Clean up ticker
                    clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                    .replace('.XSHE', '').replace('.XSHG', '')

                    # Use AKShareProvider to get news (if there is a way to do so)
                    provider = get_akshare_provider()
                    # TODO: Need to implement get_stock_news method
                    # original_news_df = provider.get_stock_news(clean_ticker)
                    # Skip for now and return to original report
                    logger.warning(f"[Enhance real-time news] AKShare The news function has not been implemented yet, return to the original report")
                    return original_report
                        
                except Exception as filter_error:
                    logger.error(f"[Enhance real-time news] News filtering failed: {filter_error}")
                    return original_report
            else:
                logger.info(f"[Enhance real-time news] Non-A share code, return to original report")
                return original_report
                
        except Exception as e:
            logger.error(f"[Enhance real-time news] Enhanced news acquisition failed: {e}")
            return f"❌ Failed to get news: {str(e)}"
    
    return get_filtered_realtime_stock_news


# Automatically apply patches
def apply_news_filtering_patches():
    """
    Automatically apply news filter patches
    """
    logger.info("[News filter integration] Start applying news filtering patch...")
    
    # 1. Enhance akshare_utils
    patch_akshare_utils()
    
    # 2. Create an enhanced live news function
    enhanced_function = create_filtered_realtime_news_function()
    
    logger.info("[News filter integration] ✅ News filter patch application completed")
    
    return enhanced_function


if __name__ == "__main__":
    # Test integration functionality
    print("=== Test the news filtering integration ===")
    
    # Apply patch
    enhanced_news_function = apply_news_filtering_patches()
    
    # Test enhanced functions
    test_result = enhanced_news_function(
        ticker="600036",
        curr_date="2024-07-28",
        enable_filter=True,
        min_score=30
    )
    
    print(f"Test result length: {len(test_result)} character")
    print(f"Test result preview: {test_result[:200]}...")
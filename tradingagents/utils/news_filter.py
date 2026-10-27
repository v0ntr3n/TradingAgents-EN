"""
News Relevance Filter
Used to filter news that is not relevant to specific stocks/companies and improve the quality of news analysis
"""

import pandas as pd
import re
from typing import List, Dict, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NewsRelevanceFilter:
    """Rule-based news relevance filter"""
    
    def __init__(self, stock_code: str, company_name: str):
        """
        Initialize filter
        
        Args:
            stock_code: Stock code, such as "600036"
            company_name: Company name, such as "China Merchants Bank"
        """
        self.stock_code = stock_code.upper()
        self.company_name = company_name
        
        # Exclude keywords - reduce relevance when these words occur
        self.exclude_keywords = [
            'etf', 'index fund', 'fund', 'Index', 'index', 'fund',
            'heavyweight stocks', 'Constituent stocks', 'plate', 'concept stocks', 'Theme Fund',
            'tracking index', 'Passive investing', 'Index investing', 'Fund positions'
        ]
        
        # Include keywords - increase relevancy when these words appear
        self.include_keywords = [
            'performance', 'financial report', 'Announcement', 'Reorganization', 'mergers and acquisitions', 'dividend', 'dividend',
            'executive', 'director', 'shareholders', 'Overweight', 'Reduce holdings', 'repurchase',
            'annual report', 'quarterly report', 'semi-annual report', 'Performance forecast', 'Performance report',
            'shareholders meeting', 'board of directors', 'supervisory board', 'major contracts',
            'investment', 'acquisition', 'for sale', 'transfer', 'cooperation', 'agreement'
        ]
        
        # Strongly relevant keywords - these words greatly increase relevance when they appear
        self.strong_keywords = [
            'trading suspension', 'Resumption of trading', 'daily limit', 'Limit down', 'Restricted sales lifted',
            'Equity incentives', 'employee stock ownership', 'Fixed increase', 'Allotment of shares', 'Bonus shares',
            'Asset restructuring', 'Backdoor listing', 'delisting', 'Take off your hat', 'ST'
        ]
    
    def calculate_relevance_score(self, title: str, content: str) -> float:
        """
        Calculate news relevance score
        
        Args:
            title: News headline
            content: News content
            
        Returns:
            float: Relevance score (0-100)
        """
        score = 0
        title_lower = title.lower()
        content_lower = content.lower()
        
        # 1. Directly mention the company name
        if self.company_name in title:
            score += 50  # High score if the company name appears in the title
            logger.debug(f"[filter] Title contains company name '{self.company_name}': +50 points")
        elif self.company_name in content:
            score += 25  # Company name appears in content, medium score
            logger.debug(f"[filter] Content contains company name '{self.company_name}': +25 points")
            
        # 2. Direct reference to stock symbol
        if self.stock_code in title:
            score += 40  # Stock code appears in the title, high score
            logger.debug(f"[filter] Title contains ticker symbol '{self.stock_code}': +40 points")
        elif self.stock_code in content:
            score += 20  # Stock code appears in content, medium score
            logger.debug(f"[filter] Content contains stock code '{self.stock_code}': +20 points")
            
        # 3. Strongly related keyword check
        strong_matches = []
        for keyword in self.strong_keywords:
            if keyword in title_lower:
                score += 30
                strong_matches.append(keyword)
            elif keyword in content_lower:
                score += 15
                strong_matches.append(keyword)
        
        if strong_matches:
            logger.debug(f"[filter] Strongly related keyword matching: {strong_matches}")
            
        # 4. Contains keyword checks
        include_matches = []
        for keyword in self.include_keywords:
            if keyword in title_lower:
                score += 15
                include_matches.append(keyword)
            elif keyword in content_lower:
                score += 8
                include_matches.append(keyword)
        
        if include_matches:
            logger.debug(f"[filter] Related keyword matching: {include_matches[:3]}...")  # Only show first 3
            
        # 5. Exclude keyword checks (minus points)
        exclude_matches = []
        for keyword in self.exclude_keywords:
            if keyword in title_lower:
                score -= 40  # If there are excluded words in the title, the score will be greatly reduced.
                exclude_matches.append(keyword)
            elif keyword in content_lower:
                score -= 20  # If excluded words appear in the content, points will be reduced moderately.
                exclude_matches.append(keyword)
        
        if exclude_matches:
            logger.debug(f"[filter] Exclude keyword matches: {exclude_matches[:3]}...")
            
        # 6. Special rule: If the title does not contain company information at all but contains excluded words, serious points will be deducted.
        if (self.company_name not in title and self.stock_code not in title and 
            any(keyword in title_lower for keyword in self.exclude_keywords)):
            score -= 30
            logger.debug(f"[filter] The title has no company information but contains exclusion words: -30 points")
        
        # Make sure the rating is in the 0-100 range
        final_score = max(0, min(100, score))
        
        logger.debug(f"[filter] final rating: {final_score}points - title: {title[:30]}...")
        
        return final_score
    
    def filter_news(self, news_df: pd.DataFrame, min_score: float = 30) -> pd.DataFrame:
        """
        filter news DataFrame
        
        Args:
            news_df: original news DataFrame
            min_score: Minimum relevance score threshold
            
        Returns:
            pd.DataFrame: Filtered News DataFrame, sorted by relevance score
        """
        if news_df.empty:
            logger.warning("[filter] The input news DataFrame is empty")
            return news_df
        
        logger.info(f"[filter] Start filtering news, original number: {len(news_df)}bar, minimum score threshold: {min_score}")
        
        filtered_news = []
        
        for idx, row in news_df.iterrows():
            title = row.get('新闻标题', row.get('标题', ''))
            content = row.get('新闻内容', row.get('内容', ''))
            
            # Calculate relevance score
            score = self.calculate_relevance_score(title, content)
            
            if score >= min_score:
                row_dict = row.to_dict()
                row_dict['relevance_score'] = score
                filtered_news.append(row_dict)
                
                logger.debug(f"[filter] keep news (Rating: {score:.1f}): {title[:50]}...")
            else:
                logger.debug(f"[filter] filter news (Rating: {score:.1f}): {title[:50]}...")
        
        # Create filtered DataFrame
        if filtered_news:
            filtered_df = pd.DataFrame(filtered_news)
            # Sort by relevance score
            filtered_df = filtered_df.sort_values('relevance_score', ascending=False)
            logger.info(f"[filter] Filtering completed, keep {len(filtered_df)}news")
        else:
            filtered_df = pd.DataFrame()
            logger.warning(f"[filter] All news has been filtered and no news meets the criteria")
            
        return filtered_df
    
    def get_filter_statistics(self, original_df: pd.DataFrame, filtered_df: pd.DataFrame) -> Dict:
        """
        Get filter statistics
        
        Args:
            original_df: original news DataFrame
            filtered_df: filtered news DataFrame
            
        Returns:
            Dict: Statistics
        """
        stats = {
            'original_count': len(original_df),
            'filtered_count': len(filtered_df),
            'filter_rate': (len(original_df) - len(filtered_df)) / len(original_df) * 100 if len(original_df) > 0 else 0,
            'avg_score': filtered_df['relevance_score'].mean() if not filtered_df.empty else 0,
            'max_score': filtered_df['relevance_score'].max() if not filtered_df.empty else 0,
            'min_score': filtered_df['relevance_score'].min() if not filtered_df.empty else 0
        }
        
        return stats


# Stock code to company name mapping
STOCK_COMPANY_MAPPING = {
    # A Major banks
    '600036': 'China Merchants Bank',
    '000001': 'Ping An Bank', 
    '600000': 'Shanghai Pudong Development Bank',
    '601166': 'Industrial Bank',
    '002142': 'Bank of Ningbo',
    '601328': 'Bank of Communications',
    '601398': 'ICBC',
    '601939': 'China Construction Bank',
    '601288': 'Agricultural Bank of China',
    '601818': 'China Everbright Bank',
    '600015': 'Hua Xia Bank',
    '600016': 'China Minsheng Bank',
    
    # A Major liquor stocks
    '000858': 'Wuliangye',
    '600519': 'Kweichow Moutai',
    '000568': 'Luzhou Laojiao',
    '002304': 'Yanghe shares',
    '000596': 'Gujing tribute wine',
    '603369': 'Fate in this life',
    '000799': 'Jiugui Liquor',
    
    # A Major Technology Stocks
    '000002': 'Vanke A',
    '000858': 'Wuliangye',
    '002415': 'Hikvision',
    '000725': 'BOE A',
    '002230': 'iFlytek',
    '300059': 'Oriental Fortune',
    
    # More stocks can continue to be added...
}

def get_company_name(ticker: str) -> str:
    """
    Get the company name corresponding to the stock code
    
    Args:
        ticker: Stock code
        
    Returns:
        str: Company name
    """
    # Clean up ticker (remove suffix)
    clean_ticker = ticker.split('.')[0]
    
    company_name = STOCK_COMPANY_MAPPING.get(clean_ticker)
    
    if company_name:
        logger.debug(f"[company mapping] {ticker} -> {company_name}")
        return company_name
    else:
        # If there is no mapping, return the default name
        default_name = f"stocks{clean_ticker}"
        logger.warning(f"[company mapping] not found {ticker} company name mapping, use the default: {default_name}")
        return default_name


def create_news_filter(ticker: str) -> NewsRelevanceFilter:
    """
    Convenience functions for creating news filters
    
    Args:
        ticker: Stock code
        
    Returns:
        NewsRelevanceFilter: Configured filter example
    """
    company_name = get_company_name(ticker)
    return NewsRelevanceFilter(ticker, company_name)


# Usage example
if __name__ == "__main__":
    # Test filter
    import pandas as pd
    
    # Simulated news data
    test_news = pd.DataFrame([
        {
            'News headline': 'China Merchants Bank releases third quarter performance report for 2024',
            'News content': 'China Merchants Bank released its third quarter financial report today, with net profit increasing year-on-year.8%...'
        },
        {
            'News headline': 'Shanghai Stock Exchange 180ETF Index Fund (530280) has its own barbell strategy',
            'News content': 'Data shows that the top ten heavyweight stocks in the Shanghai Stock Exchange 180 Index are Kweichow Moutai and China Merchants Bank.600036...'
        },
        {
            'News headline': 'Bank ETF Index(512730 Many constituent stocks rose',
            'News content': 'The banking sector performed strongly today, with many constituent stocks such as China Merchants Bank and Industrial and Commercial Bank of China rising....'
        }
    ])
    
    # Create filter
    filter = create_news_filter('600036')
    
    # filter news
    filtered_news = filter.filter_news(test_news, min_score=30)
    
    print(f"original news: {len(test_news)}Article")
    print(f"filtered news: {len(filtered_news)}Article")
    
    if not filtered_news.empty:
        print("\n filtered news:")
        for _, row in filtered_news.iterrows():
            print(f"- {row['News headline']} (Rating: {row['relevance_score']:.1f})")
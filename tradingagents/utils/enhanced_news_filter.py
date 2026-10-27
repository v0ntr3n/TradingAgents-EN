"""
Enhanced news filter - integrated rule filtering
The local semantic model (sentence-transformers) and the local classification model (transformers/torch) have been removed.
The remote API solution is used uniformly, and only rule filtering is retained here.
"""

import pandas as pd
import re
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# Import basic filters
from .news_filter import NewsRelevanceFilter, create_news_filter, get_company_name

logger = logging.getLogger(__name__)

class EnhancedNewsFilter(NewsRelevanceFilter):
    """Enhanced news filter (rule-based filtering)"""

    def __init__(self, stock_code: str, company_name: str, use_semantic: bool = True, use_local_model: bool = False):
        """
        Initialize enhanced filter

        Args:
            stock_code: Stock code
            company_name: Company name
            use_semantic: Deprecated (the local semantic model has been removed, this parameter is ignored)
            use_local_model: Deprecated (the local classification model has been removed, this parameter is ignored)
        """
        super().__init__(stock_code, company_name)
        # Local semantic/classification models (sentence-transformers/transformers/torch) have been removed,
        # Only rule filtering is retained. Parameters are retained for compatibility with older callers, but local models are no longer loaded.
        self.use_semantic = False
        self.use_local_model = False

    def calculate_enhanced_relevance_score(self, title: str, content: str) -> Dict[str, float]:
        """
        Calculate enhanced relevance score (currently rule filtering only)

        Args:
            title: News headline
            content: News content

        Returns:
            Dict: Dictionary containing various ratings
        """
        # 1. Basic rules scoring
        rule_score = super().calculate_relevance_score(title, content)

        # Local semantic/classification model removed, score fixed at 0 (keeps final score weight consistent with history)
        semantic_score = 0
        classification_score = 0

        # 2. Overall rating (weighted average)
        weights = {
            'rule': 0.4,          # Rule filter weight 40%
            'semantic': 0.35,     # Semantic similarity weight 35% (removed)
            'classification': 0.25  # Classification model weight 25% (removed)
        }

        final_score = (
            weights['rule'] * rule_score +
            weights['semantic'] * semantic_score +
            weights['classification'] * classification_score
        )

        logger.debug(f"[Enhance filter] Overall Rating - Rules:{rule_score:.1f}, "
                    f"Semantics:{semantic_score:.1f}, Classification:{classification_score:.1f}, eventually:{final_score:.1f}")

        return {
            'rule_score': rule_score,
            'semantic_score': semantic_score,
            'classification_score': classification_score,
            'final_score': final_score,
        }

    def filter_news_enhanced(self, news_df: pd.DataFrame, min_score: float = 40) -> pd.DataFrame:
        """
        Enhanced news filtering

        Args:
            news_df: original news DataFrame
            min_score: Minimum overall score threshold

        Returns:
            pd.DataFrame: Filtered news DataFrame, containing detailed rating information
        """
        if news_df.empty:
            logger.warning("[Enhance filter] The input news DataFrame is empty")
            return news_df

        logger.info(f"[Enhance filter] Start enhanced filtering, original quantity: {len(news_df)}bar, minimum score threshold: {min_score}")

        filtered_news = []

        for idx, row in news_df.iterrows():
            title = row.get('新闻标题', row.get('标题', ''))
            content = row.get('新闻内容', row.get('内容', ''))

            # Calculate enhancement score
            scores = self.calculate_enhanced_relevance_score(title, content)

            if scores['final_score'] >= min_score:
                row_dict = row.to_dict()
                row_dict.update(scores)  # Add all rating information
                filtered_news.append(row_dict)

                logger.debug(f"[Enhance filter] keep news (Overall rating: {scores['final_score']:.1f}): {title[:50]}...")
            else:
                logger.debug(f"[Enhance filter] filter news (Overall rating: {scores['final_score']:.1f}): {title[:50]}...")

        # Create filtered DataFrame
        if filtered_news:
            filtered_df = pd.DataFrame(filtered_news)
            # Sort by overall rating
            filtered_df = filtered_df.sort_values('final_score', ascending=False)
            logger.info(f"[Enhance filter] Enhanced filtering completed, retained {len(filtered_df)}news")
        else:
            filtered_df = pd.DataFrame()
            logger.warning(f"[Enhance filter] All news has been filtered and no news meets the criteria")

        return filtered_df


def create_enhanced_news_filter(ticker: str, use_semantic: bool = True, use_local_model: bool = False) -> EnhancedNewsFilter:
    """
    Convenience functions for creating enhanced news filters

    Args:
        ticker: Stock code
        use_semantic: Deprecated (the local semantic model has been removed, this parameter is ignored)
        use_local_model: Deprecated (the local classification model has been removed, this parameter is ignored)

    Returns:
        EnhancedNewsFilter: Configured enhanced filter example
    """
    company_name = get_company_name(ticker)
    return EnhancedNewsFilter(ticker, company_name, use_semantic, use_local_model)


# Usage example
if __name__ == "__main__":
    # Test enhanced filters
    import pandas as pd

    # Simulated news data
    test_news = pd.DataFrame([
        {
            'News headline': 'China Merchants Bank releases third quarter performance report for 2024',
            'News content': 'China Merchants Bank released its third quarter financial report today. Net profit increased by 8% year-on-year and asset quality continued to improve....'
        },
        {
            'News headline': 'Shanghai Stock Exchange 180ETF Index Fund (530280) has its own barbell strategy',
            'News content': 'Data shows that the top ten heavyweight stocks in the Shanghai Stock Exchange 180 Index are Kweichow Moutai and China Merchants Bank.600036...'
        },
        {
            'News headline': 'Bank ETF Index(512730)Many constituent stocks rose',
            'News content': 'The banking sector performed strongly today, with many constituent stocks such as China Merchants Bank and Industrial and Commercial Bank of China rising....'
        },
        {
            'News headline': 'China Merchants Bank signed a strategic cooperation agreement with a technology company',
            'News content': 'China Merchants Bank announced a strategic cooperation with a well-known technology company and will cooperate in depth in digital transformation....'
        }
    ])

    print("=== Test the enhanced news filter ===")

    # Create enhanced filters (only use rule filtering to avoid model dependencies)
    enhanced_filter = create_enhanced_news_filter('600036', use_semantic=False, use_local_model=False)

    # filter news
    filtered_news = enhanced_filter.filter_news_enhanced(test_news, min_score=30)

    print(f"original news: {len(test_news)}Article")
    print(f"filtered news: {len(filtered_news)}Article")

    if not filtered_news.empty:
        print("\n filtered news:")
        for _, row in filtered_news.iterrows():
            print(f"- {row['News headline']} (Overall rating: {row['final_score']:.1f})")
            print(f"  Rule scoring: {row['rule_score']:.1f}, Semantic scoring: {row['semantic_score']:.1f}, Classification rating: {row['classification_score']:.1f}")

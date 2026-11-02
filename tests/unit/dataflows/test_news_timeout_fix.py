#!/usr/bin/env python3
"""
Test news retrieval timeout fix

This test program verifies the effectiveness of the news fetch timeout fix, specifically the ability to correctly poll to the next news source when one news source fails.
"""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime

# Add project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the modules that need to be tested
from tradingagents.dataflows.realtime_news_utils import get_realtime_stock_news
from tradingagents.dataflows.googlenews_utils import getNewsData, make_request
from tradingagents.dataflows.akshare_utils import get_stock_news_em


class TestNewsTimeoutFix(unittest.TestCase):
    """Test news retrieval timeout fix"""

    def setUp(self):
        """Preparation before the test"""
        self.ticker = "600036.SH"  # China Merchants Bank
        self.curr_date = datetime.now().strftime("%Y-%m-%d")

    def test_make_request_timeout(self):
        """Test the timeout handling of the make_request function"""
        # Simulate request timeout
        with patch('requests.get') as mock_get:
            # Set mock to throw timeout exception
            import requests
            from tenacity import RetryError
            mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
            
            # Test the make_request function
            with self.assertRaises(RetryError):
                make_request("https://www.google.com", {})
                
            # Verification retry mechanism
            self.assertEqual(mock_get.call_count, 5)  # Should try 5 times

    def test_news_source_fallback(self):
        """Test the news source polling mechanism"""
        # Simulating real-time news aggregator fails
        with patch('tradingagents.dataflows.realtime_news_utils.RealtimeNewsAggregator.get_realtime_stock_news') as mock_aggregator:
            mock_aggregator.side_effect = Exception("Simulating real-time news aggregator fails")
            
            # Simulate Google News acquisition failure
            with patch('tradingagents.dataflows.interface.get_google_news') as mock_google_news:
                mock_google_news.side_effect = Exception("Simulate Google News acquisition failure")
                
                # Simulate Oriental Fortune News to achieve success
                with patch('tradingagents.dataflows.akshare_utils.get_stock_news_em') as mock_em_news:
                    # Create a mock DataFrame as return value
                    mock_df = pd.DataFrame({
                        'Title': ['test news 1', 'test news 2'],
                        'time': ['2023-01-01 12:00:00', '2023-01-01 13:00:00'],
                        'content': ['Test content 1', 'Test content 2'],
                        'link': ['http://example.com/1', 'http://example.com/2']
                    })
                    mock_em_news.return_value = mock_df
                    
                    # Call test function
                    result = get_realtime_stock_news(self.ticker, self.curr_date)
                    
                    # Verification results
                    self.assertIn("Oriental Fortune News Report", result)
                    self.assertIn("test news 1", result)
                    self.assertIn("test news 2", result)
                    
                    # Verify calling sequence
                    mock_aggregator.assert_called_once()
                    mock_google_news.assert_called_once()
                    mock_em_news.assert_called_once()

    def test_all_news_sources_fail(self):
        """Testing the case where all news sources fail"""
        # Simulating all news sources fails
        with patch('tradingagents.dataflows.realtime_news_utils.RealtimeNewsAggregator.get_realtime_stock_news') as mock_aggregator:
            mock_aggregator.side_effect = Exception("Simulating real-time news aggregator fails")
            
            with patch('tradingagents.dataflows.interface.get_google_news') as mock_google_news:
                mock_google_news.side_effect = Exception("Simulate Google News acquisition failure")
                
                with patch('tradingagents.dataflows.akshare_utils.get_stock_news_em') as mock_em_news:
                    mock_em_news.side_effect = Exception("Failed to obtain simulated Oriental Fortune News")
                    
                    # Call test function
                    result = get_realtime_stock_news(self.ticker, self.curr_date)
                    
                    # Verification results
                    self.assertIn("Failed to obtain real-time news", result)
                    self.assertIn("All available news sources failed to obtain relevant news", result)
                    
                    # Verify calling sequence
                    mock_aggregator.assert_called_once()
                    mock_google_news.assert_called_once()
                    mock_em_news.assert_called_once()


if __name__ == "__main__":
    unittest.main()
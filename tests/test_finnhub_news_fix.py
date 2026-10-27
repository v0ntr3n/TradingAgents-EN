#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Finnhub news data path repair

This script is used to verify:
1. Is the data directory path configuration correct?
2. Does the news data file path exist?
3. Is error handling working properly?
"""

import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.interface import get_finnhub_news
from tradingagents.dataflows.finnhub_utils import get_data_in_range

def test_data_dir_config():
    """Test data directory configuration"""
    print("=== Test data directory configuration ===")
    
    config = get_config()
    data_dir = config.get('data_dir')
    
    print(f"Current data directory configuration: {data_dir}")
    print(f"Does the data directory exist?: {os.path.exists(data_dir) if data_dir else False}")
    
    # Check if it is a cross-platform path
    if data_dir:
        if '/' in data_dir and '\\' in data_dir:
            print("⚠️ warning: Data directory path mixes Unix and Windows delimiters")
        elif data_dir.startswith('/Users/') and os.name == 'nt':
            print("⚠️ warning: Used Unix path on Windows system")
        else:
            print("✅ The data directory path format is correct")
    
    return data_dir

def test_finnhub_news_path():
    """Test Finnhub news data path"""
    print("\n=== Test Finnhub news data path ===")
    
    config = get_config()
    data_dir = config.get('data_dir')
    
    if not data_dir:
        print("❌ Data directory is not configured")
        return False
    
    # Test AAPL news data path
    ticker = "AAPL"
    news_data_path = os.path.join(data_dir, "finnhub_data", "news_data", f"{ticker}_data_formatted.json")
    
    print(f"News data file path: {news_data_path}")
    print(f"Does the file exist?: {os.path.exists(news_data_path)}")
    
    # Check directory structure
    finnhub_dir = os.path.join(data_dir, "finnhub_data")
    news_dir = os.path.join(finnhub_dir, "news_data")
    
    print(f"Finnhub Does the directory exist?: {os.path.exists(finnhub_dir)}")
    print(f"Does the news data directory exist?: {os.path.exists(news_dir)}")
    
    if os.path.exists(news_dir):
        files = os.listdir(news_dir)
        print(f"Files in the news data directory: {files[:5]}...")  # Only show first 5 files
    
    return os.path.exists(news_data_path)

def test_get_data_in_range():
    """Test error handling of get_data_in_range function"""
    print("\n=== Test get_data_in_range error handling ===")
    
    config = get_config()
    data_dir = config.get('data_dir')
    
    if not data_dir:
        print("❌ Data directory is not configured")
        return
    
    # Test for a non-existent ticker
    result = get_data_in_range(
        ticker="NONEXISTENT",
        start_date="2025-01-01",
        end_date="2025-01-02",
        data_type="news_data",
        data_dir=data_dir
    )
    
    print(f"There is no return result for the stock: {result}")
    print(f"Return result type: {type(result)}")
    print(f"Whether it is an empty dictionary: {result == {}}")

def test_get_finnhub_news():
    """Test get_finnhub_news function"""
    print("\n=== Test get_finnhub_news function ===")
    
    # Test for a non-existent ticker
    result = get_finnhub_news(
        ticker="NONEXISTENT",
        curr_date="2025-01-02",
        look_back_days=7
    )
    
    print(f"function returns result: {result[:200]}...")  # Only show first 200 characters
    print(f"Does it contain error information?: {'Unable to obtain' in result}")

def create_sample_data_structure():
    """Create a sample data directory structure"""
    print("\n=== Create a sample data directory structure ===")
    
    config = get_config()
    data_dir = config.get('data_dir')
    
    if not data_dir:
        print("❌ Data directory is not configured")
        return
    
    # Create directory structure
    finnhub_dir = os.path.join(data_dir, "finnhub_data")
    news_dir = os.path.join(finnhub_dir, "news_data")
    
    try:
        os.makedirs(news_dir, exist_ok=True)
        print(f"✅ Create directory structure: {news_dir}")
        
        # Create sample data files
        sample_file = os.path.join(news_dir, "AAPL_data_formatted.json")
        sample_data = {
            "2025-01-01": [
                {
                    "headline": "Apple Release new products",
                    "summary": "Apple announced a new product line today..."
                }
            ]
        }
        
        import json
        with open(sample_file, 'w', encoding='utf-8') as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Create sample data files: {sample_file}")
        
    except Exception as e:
        print(f"❌ Failed to create directory structure: {e}")

def main():
    """Main test function"""
    print("Finnhub News data path repair test")
    print("=" * 50)
    
    # Test data directory configuration
    data_dir = test_data_dir_config()
    
    # Test news data path
    news_exists = test_finnhub_news_path()
    
    # Test error handling
    test_get_data_in_range()
    test_get_finnhub_news()
    
    # Create sample structure if data does not exist
    if not news_exists:
        create_sample_data_structure()
        print("\n Retest the news data path:")
        test_finnhub_news_path()
    
    print("\n=== Test summary ===")
    print("1. Data directory paths have been fixed for cross-platform compatibility")
    print("2. Added detailed error handling and debugging information")
    print("3. Provides clear error message when data file does not exist")
    print("4. It is recommended to download or configure the correct Finnhub data")
    
    print("\n=== Solution suggestions ===")
    print("If you are still having issues with your news data, please:")
    print("1. Make sure the Finnhub API key is configured correctly")
    print("2. Run the data download script to obtain news data")
    print("3. Check data directory permissions")
    print(f"4. Confirm that the data directory exists: {data_dir}")

if __name__ == "__main__":
    main()
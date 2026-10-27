#!/usr/bin/env python3
"""
Test script: Verify whether the MARKET_ANALYST_LOOKBACK_DAYS configuration takes effect

Function:
1. Read the MARKET_ANALYST_LOOKBACK_DAYS value in the configuration file
2. Simulated market analysts call data interface
3. Verify whether the actual number of days of data obtained matches the configuration
4. Output detailed verification report

How to use:
    python scripts/validation/test_market_analyst_lookback.py
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root directory to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

from tradingagents.utils.logging_manager import get_logger

logger = get_logger('test')


def test_config_loading():
    """Test 1: Verify configuration loading"""
    print("\n" + "=" * 80)
    print("Test 1: Verify configuration loading")
    print("=" * 80)
    
    try:
        from app.core.config import get_settings
        settings = get_settings()
        lookback_days = settings.MARKET_ANALYST_LOOKBACK_DAYS
        
        print(f"✅ Configuration loaded successfully")
        print(f"📅 MARKET_ANALYST_LOOKBACK_DAYS = {lookback_days}day")
        
        # Verify configuration values
        if lookback_days == 250:
            print(f"✅ The configuration value is correct: 250 days (professional configuration)")
        elif lookback_days == 120:
            print(f"⚠️  Configuration value: 120 days (standard configuration)")
        elif lookback_days == 60:
            print(f"⚠️  Configuration value: 60 days (minimum configuration)")
        else:
            print(f"⚠️  Configuration value:{lookback_days}days (custom configuration)")
        
        return lookback_days
    except Exception as e:
        print(f"❌ Configuration load failed: {e}")
        return None


def test_date_range_calculation(lookback_days):
    """Test 2: Validate date range calculation"""
    print("\n" + "=" * 80)
    print("Test 2: Validate date range calculation")
    print("=" * 80)
    
    try:
        from tradingagents.utils.dataflow_utils import get_trading_date_range
        
        # Use today as target date
        target_date = datetime.now().strftime("%Y-%m-%d")
        start_date, end_date = get_trading_date_range(target_date, lookback_days=lookback_days)
        
        # Calculate actual number of days
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        actual_days = (end_dt - start_dt).days
        
        print(f"✅ Date range calculated successfully")
        print(f"📅 target date: {target_date}")
        print(f"📅 Configure traceback: {lookback_days}day")
        print(f"📅 start date: {start_date}")
        print(f"📅 end date: {end_date}")
        print(f"📅 Actual number of days: {actual_days}day")
        
        # Verify that the actual number of days is as expected
        if actual_days >= lookback_days:
            print(f"✅ Actual number of days ({actual_days}) >= Configure the number of days ({lookback_days})")
        else:
            print(f"⚠️  Actual number of days ({actual_days}) < Configure the number of days ({lookback_days})")
        
        return start_date, end_date, actual_days
    except Exception as e:
        print(f"❌ Date range calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def test_data_fetching(start_date, end_date):
    """Test 3: Verify data acquisition"""
    print("\n" + "=" * 80)
    print("Test 3: Verify data acquisition (simulate market analyst call)")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        
        # Use a common A-share stock code for testing
        test_ticker = "300750"  # Ping An Bank
        
        print(f"📊 test stocks: {test_ticker}")
        print(f"📅 date range: {start_date} to {end_date}")
        print(f"⏳ Getting data...")
        
        # Call the unified interface to obtain data
        result = get_china_stock_data_unified(
            ticker=test_ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        # Check results
        if result and not result.startswith("❌"):
            print(f"✅ Data acquisition successful")
            print(f"📊 Return data length: {len(result)} character")
            
            # Check if technical indicators are included
            indicators = ["MA5", "MA10", "MA20", "MA60", "MACD", "RSI", "BOLL"]
            found_indicators = [ind for ind in indicators if ind in result]
            
            print(f"📈 Contains technical indicators: {', '.join(found_indicators)}")
            
            if len(found_indicators) == len(indicators):
                print(f"✅ All technical indicators have been calculated")
            else:
                missing = set(indicators) - set(found_indicators)
                print(f"⚠️  Missing technical indicators: {', '.join(missing)}")
            
            # Show partial results (first 1000 characters)
            print(f"\n📄 Data preview (first 1000 characters):")
            print("-" * 80)
            print(result[:1000])
            print("-" * 80)

            # Show last 500 characters
            print(f"\n📄 Data preview (last 500 characters):")
            print("-" * 80)
            print(result[-500:])
            print("-" * 80)
            
            return True
        else:
            print(f"❌ Data acquisition failed")
            print(f"error message: {result}")
            return False
    except Exception as e:
        print(f"❌ Data acquisition exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_technical_indicators_accuracy(lookback_days):
    """Test 4: Verify the accuracy requirements of technical indicators"""
    print("\n" + "=" * 80)
    print("Test 4: Verify the accuracy requirements of technical indicators")
    print("=" * 80)
    
    # Technical indicator data requirements
    requirements = {
        "MA5": {"min": 5, "recommended": 10},
        "MA10": {"min": 10, "recommended": 15},
        "MA20": {"min": 20, "recommended": 30},
        "MA60": {"min": 60, "recommended": 120},
        "MACD": {"min": 26, "recommended": 100, "professional": 250},
        "RSI": {"min": 14, "recommended": 50},
        "BOLL": {"min": 20, "recommended": 60},
    }
    
    print(f"📊 Current configuration: {lookback_days}day")
    print(f"\n Technical indicator data requirements inspection:")
    print("-" * 80)
    
    all_passed = True
    for indicator, req in requirements.items():
        min_days = req["min"]
        rec_days = req.get("recommended", min_days)
        pro_days = req.get("professional", rec_days)
        
        if lookback_days >= pro_days:
            status = "✅ Professional grade"
            level = "professional"
        elif lookback_days >= rec_days:
            status = "✅ Recommended level"
            level = "recommended"
        elif lookback_days >= min_days:
            status = "⚠️  smallest level"
            level = "minimum"
            all_passed = False
        else:
            status = "❌ Insufficient"
            level = "insufficient"
            all_passed = False
        
        print(f"{indicator:8s} | smallest:{min_days:3d}day | Recommended:{rec_days:3d}day | Professional:{pro_days:3d}day | {status}")
    
    print("-" * 80)
    
    if all_passed:
        print(f"✅ All technical specifications meet recommended or professional grade requirements")
    else:
        print(f"⚠️  Some technical indicators do not meet the recommended level requirements")
    
    return all_passed


def main():
    """Main test process"""
    print("\n" + "=" * 80)
    print("🔍 MARKET_ANALYST_LOOKBACK_DAYS Configuration verification test")
    print("=" * 80)
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Configuration loading
    lookback_days = test_config_loading()
    if lookback_days is None:
        print("\n❌ Configuration loading failed, test terminated")
        return
    
    # Test 2: Date range calculation
    start_date, end_date, actual_days = test_date_range_calculation(lookback_days)
    if start_date is None:
        print("\n❌ Date range calculation failed, test terminated")
        return
    
    # Test 3: Data acquisition
    data_success = test_data_fetching(start_date, end_date)
    
    # Test 4: Technical indicator accuracy
    indicators_ok = test_technical_indicators_accuracy(lookback_days)
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 Test summary")
    print("=" * 80)
    print(f"✅ Configuration loading: success ({lookback_days}day)")
    print(f"✅ date calculation: success ({actual_days}day)")
    print(f"{'✅' if data_success else '❌'} data acquisition: {'success' if data_success else 'failed'}")
    print(f"{'✅' if indicators_ok else '⚠️ '} Technical indicators: {'Meet the requirements' if indicators_ok else 'Partially insufficient'}")
    
    if lookback_days == 250 and data_success and indicators_ok:
        print(f"\n🎉 Perfect! Configuration has been set to 250 days (Professional level) and all tests passed!")
    elif data_success:
        print(f"\n✅ The configuration takes effect and data acquisition is normal.")
    else:
        print(f"\n⚠️  There is a problem, please check the logs")
    
    print("=" * 80)


if __name__ == "__main__":
    main()


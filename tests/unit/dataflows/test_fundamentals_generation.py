#!/usr/bin/env python3
"""
Fundamental report generation test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_fundamentals_generation():
    """Test fundamentals report generation process"""
    print("\n🔍 Fundamental report generation test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print(f"\n🔧 steps 1: Get stock data...")
        
        # Get stock data
        from tradingagents.dataflows.interface import get_china_stock_data_tushare
        stock_data = get_china_stock_data_tushare(test_ticker, "2025-07-01", "2025-07-15")
        
        print(f"✅ Stock data acquisition completed, length: {len(stock_data) if stock_data else 0}")
        print(f"📄 The first 200 characters of stock data: {stock_data[:200] if stock_data else 'None'}")
        
        print(f"\n🔧 steps 2: Generate fundamental reports...")
        
        # Generate fundamental reports
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        
        fundamentals_report = analyzer._generate_fundamentals_report(test_ticker, stock_data)
        
        print(f"\n✅ Fundamental report generation completed")
        print(f"📊 Report length: {len(fundamentals_report) if fundamentals_report else 0}")
        
        # Check the stock symbol in the report
        if fundamentals_report:
            print(f"\n🔍 Check the stock symbol in the report...")
            if "002027" in fundamentals_report:
                print("✅ Reports contain correct ticker symbols 002027")
                # Count the number of occurrences
                count_002027 = fundamentals_report.count("002027")
                print(f"   002027 Number of occurrences: {count_002027}")
            else:
                print("❌ Report does not contain correct ticker symbol 002027")
                
            if "002021" in fundamentals_report:
                print("⚠️ Report contains incorrect stock symbol 002021")
                # Count the number of occurrences
                count_002021 = fundamentals_report.count("002021")
                print(f"   002021 Number of occurrences: {count_002021}")
                
                # Find the location of the error code
                import re
                positions = [m.start() for m in re.finditer("002021", fundamentals_report)]
                print(f"   002021 Appear location: {positions}")
                
                # Show text around error code
                for pos in positions[:3]:  # Only show first 3 positions
                    start = max(0, pos - 50)
                    end = min(len(fundamentals_report), pos + 50)
                    context = fundamentals_report[start:end]
                    print(f"   location {pos} surrounding text: ...{context}...")
            else:
                print("✅ Reports do not contain incorrect ticker symbols 002021")
                
            # Display the first 1000 characters of the report
            print(f"\n📄 Report first 1000 characters:")
            print("-" * 80)
            print(fundamentals_report[:1000])
            print("-" * 80)
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_industry_info():
    """Obtain testing industry information"""
    print("\n🔧 Obtain testing industry information")
    print("=" * 80)
    
    test_ticker = "002027"
    
    try:
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        
        print(f"🔧 test _get_industry_info...")
        industry_info = analyzer._get_industry_info(test_ticker)
        print(f"📊 Industry information: {industry_info}")
        
        print(f"\n🔧 test _estimate_financial_metrics...")
        financial_metrics = analyzer._estimate_financial_metrics(test_ticker, "¥7.67")
        print(f"📊 financial indicators: {financial_metrics}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start fundamental report generation testing")
    
    # test 1: Industry information acquisition
    success1 = test_industry_info()
    
    # test 2: Complete fundamental report generation
    success2 = test_fundamentals_generation()
    
    if success1 and success2:
        print("\n✅ All tests passed")
    else:
        print("\n❌ Some tests failed")

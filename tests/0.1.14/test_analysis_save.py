#!/usr/bin/env python3
"""
Test analysis result saving function
Saving process after simulation analysis is completed
"""

import sys
import os
from datetime import datetime

# Add project path
sys.path.append(os.path.join(os.path.dirname(__file__), 'web'))

def create_mock_analysis_results():
    """Create simulated analysis results data"""
    return {
        'stock_symbol': 'TEST123',
        'analysis_date': '2025-07-31',
        'analysts': ['market_analyst', 'fundamentals_analyst', 'trader_agent'],
        'research_depth': 3,
        'state': {
            'market_report': """# TEST123 Stock Technical Analysis Report

## 📈 Price trend analysis
The current stock price is showing an upward trend and the technical indicators are improving.

## 📊 Technical indicators
- RSI: 65.2 (Stronger)
- MACD: golden cross upward
- Volume: Rising on heavy volume

## 🎯 Operation suggestions
It is recommended to buy on a pullback with a target price increase of 15%.
""",
            'fundamentals_report': """# TEST123 Fundamental Analysis Report

## 💰 financial condition
The company s financial position is good and its profitability is strong.

## 📊 key indicators
- ROE: 18.5%
- PE: 15.2 times
- Net profit growth: 15.2%

## 💡 investment value
The valuation is reasonable and has investment value.
""",
            'final_trade_decision': """# TEST123 Final analysis results

## 🎯 investment advice
**action**: buy
**Confidence**: 85%
**target price**: rise 15-20%

## 💡 Decision basis
Based on comprehensive analysis of technical and fundamental aspects, it is recommended to buy.
"""
        },
        'decision': {
            'action': 'buy',
            'confidence': 0.85,
            'target_price': 'up 15-20%',
            'reasoning': 'Both technical and fundamental factors support a buying decision'
        },
        'summary': 'TEST123 Comprehensive analysis of the stock shows that it has good investment potential and it is recommended to buy.'
    }

def test_save_analysis_result():
    """Test save analysis results"""
    print("🧪 Test analysis result saving function")
    print("=" * 40)
    
    try:
        # Import save function
        from web.components.analysis_results import save_analysis_result
        
        # Create simulated data
        analysis_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        stock_symbol = "TEST123"
        analysts = ['market_analyst', 'fundamentals_analyst', 'trader_agent']
        research_depth = 3
        result_data = create_mock_analysis_results()
        
        print(f"📝 test data:")
        print(f"   analysis ID: {analysis_id}")
        print(f"   Stock code: {stock_symbol}")
        print(f"   analyst: {analysts}")
        print(f"   Research depth: {research_depth}")
        
        # Execute save
        print(f"\n💾 Start saving analysis results...")
        success = save_analysis_result(
            analysis_id=analysis_id,
            stock_symbol=stock_symbol,
            analysts=analysts,
            research_depth=research_depth,
            result_data=result_data,
            status="completed"
        )
        
        if success:
            print("✅ Analysis results saved successfully!")
            
            # Check if file is created
            print(f"\n📁 Check saved files:")
            
            # Check JSON file
            from web.components.analysis_results import get_analysis_results_dir
            results_dir = get_analysis_results_dir()
            json_file = results_dir / f"analysis_{analysis_id}.json"
            
            if json_file.exists():
                print(f"✅ JSON File created: {json_file}")
            else:
                print(f"❌ JSON File not found: {json_file}")
            
            # Check detailed report table of contents
            import os
            from pathlib import Path
            
            # Get the project root directory
            project_root = Path(__file__).parent
            results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./data/analysis_results")
            
            if not os.path.isabs(results_dir_env):
                detailed_results_dir = project_root / results_dir_env
            else:
                detailed_results_dir = Path(results_dir_env)
            
            analysis_date = datetime.now().strftime('%Y-%m-%d')
            reports_dir = detailed_results_dir / stock_symbol / analysis_date / "reports"
            
            print(f"📂 Detailed report directory: {reports_dir}")
            
            if reports_dir.exists():
                print("✅ Detailed report directory created")
                
                # List report files
                report_files = list(reports_dir.glob("*.md"))
                if report_files:
                    print(f"📄 report file ({len(report_files)} a):")
                    for file in report_files:
                        print(f"   - {file.name}")
                else:
                    print("⚠️ Report directory exists but no files")
            else:
                print(f"❌ Detailed report directory not created: {reports_dir}")
            
        else:
            print("❌ Failed to save analysis results")
        
        return success
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mongodb_save():
    """Test MongoDB save"""
    print(f"\n🗄️ Test MongoDB save...")
    
    try:
        from web.utils.mongodb_report_manager import mongodb_report_manager
        
        if not mongodb_report_manager.connected:
            print("❌ MongoDB Not connected")
            return False
        
        # Get the current number of records
        before_count = len(mongodb_report_manager.get_analysis_reports(limit=1000))
        print(f"📊 Number of MongoDB records before saving: {before_count}")
        
        # Execute test save
        test_save_analysis_result()
        
        # Get the number of records after saving
        after_count = len(mongodb_report_manager.get_analysis_reports(limit=1000))
        print(f"📊 Number of MongoDB records after saving: {after_count}")
        
        if after_count > before_count:
            print("✅ MongoDB The record is added and saved successfully")
            return True
        else:
            print("⚠️ MongoDB The number of records has not increased")
            return False
            
    except Exception as e:
        print(f"❌ MongoDB test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Analysis result saving function test")
    print("=" * 50)
    
    # Test basic save functionality
    save_success = test_save_analysis_result()
    
    # Test MongoDB save
    mongodb_success = test_mongodb_save()
    
    print(f"\n🎉 Test completed")
    print(f"📄 File saving: {'✅ success' if save_success else '❌ failed'}")
    print(f"🗄️ MongoDB save: {'✅ success' if mongodb_success else '❌ failed'}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Create a sample analysis report
Used to test the report display function of the web interface
"""

import sys
import os
from datetime import datetime

# Add project path
sys.path.append(os.path.join(os.path.dirname(__file__), 'web'))

def create_sample_report(stock_symbol: str, stock_name: str):
    """Create a sample analysis report"""
    
    # Analyze result data
    analysis_results = {
        "summary": f"{stock_name}({stock_symbol}) Comprehensive analysis shows that this stock has good investment potential and it is recommended to pay attention.",
        "analysts": ["market_analyst", "fundamentals_analyst", "trader_agent"]
    }
    
    # Report content
    reports = {
        "final_trade_decision": f"""# {stock_name}({stock_symbol}) Final analysis results

## 📊 investment advice
**action**: buy
**Confidence**: 85%
**risk score**: 25%
**target price**: current price increase 15-20%

## 🎯 Key takeaways
- Technicals show an uptrend
- Fundamental financial position is sound
- Market sentiment is positive
- Risk controllable

## 💡 analytical reasoning
Based on multi-dimensional analysis, the stock performs well in terms of technical, fundamental and market sentiment. Technical indicators point to a break above key resistance levels, with increased volume confirming the uptrend. Fundamental analysis shows that the company is financially sound and has strong profitability. A comprehensive assessment recommends buying and holding.

## ⚠️ Risk warning
- Overall market volatility risk
- Risks of industry policy changes
- It is recommended to set a stop loss level
""",

        "fundamentals_report": f"""# {stock_name}({stock_symbol}) Fundamental Analysis Report

## 📈 Financial indicator analysis
### Profitability
- **net profit growth rate**: 15.2% (Year-on-year)
- **ROE**: 18.5%
- **ROA**: 12.3%
- **Gross profit margin**: 35.8%

### Solvency
- **Asset-liability ratio**: 45.2%
- **current ratio**: 2.1
- **quick ratio**: 1.8
- **interest coverage ratio**: 8.5

### Operational capabilities
- **total asset turnover ratio**: 1.2
- **Inventory turnover**: 6.8
- **Accounts receivable turnover ratio**: 9.2

## 🏢 Basic information of the company
- **Industry status**: Industry leading companies
- **Main business**: Steady growth
- **market share**: Continue to expand
- **competitive advantage**: Leading technology and high brand awareness

## 📊 Valuation analysis
- **PE**: 15.2 times (Reasonable valuation range)
- **PB**: 2.1 times
- **PEG**: 0.8 (Below 1, it has investment value)

## 💰 Investment Highlights
1. Stable financial position and strong profitability
2. Solid industry position and obvious competitive advantages
3. Reasonable valuation and investment value
4. Stable dividend policy and good shareholder returns
""",

        "market_report": f"""# {stock_name}({stock_symbol}) Technical analysis report

## 📈 Price trend analysis
### short term trend (5-20 day)
- **trend direction**: rise
- **support level**: ¥45.20
- **resistance level**: ¥52.80
- **Current location**: Break through the previous high

### medium term trend (20-60 day)
- **trend direction**: rise
- **main support**: ¥42.50
- **Target position**: ¥55.00
- **trend strength**: Strong

## 📊 Technical indicator analysis
### trend indicator
- **MA5**: 48.50 (Price is above the moving average)
- **MA20**: 46.80 (multi-head arrangement)
- **MA60**: 44.20 (long term uptrend)

### Momentum indicator
- **RSI(14)**: 68.5 (Strong, not overbought)
- **MACD**: golden cross upward
- **KDJ**: K=75, D=68, J=82 (Strong area)

### Volume analysis
- **Volume**: Rising on heavy volume
- **Volume price relationship**: Price increase, volume increase, healthy increase
- **turnover rate**: 3.2% (active)

## 🎯 Operation suggestions
### buy signal
- Break through the previous high
- Volume matching
- Technical indicators are improving

### key position
- **buy position**: ¥48.00-49.00
- **Stop loss level**: ¥45.00
- **Target position**: ¥55.00

## ⚠️ Risk warning
- Pay attention to the overall trend of the market
- Pay attention to changes in trading volume
- Set a reasonable stop loss level
"""
    }
    
    return analysis_results, reports

def main():
    """main function"""
    print("🎨 Create a sample analysis report...")
    
    try:
        from web.utils.mongodb_report_manager import mongodb_report_manager
        
        if not mongodb_report_manager.connected:
            print("❌ MongoDB Not connected")
            return
        
        # Create multiple sample reports
        sample_stocks = [
            ("DEMO001", "Example Technology Stocks"),
            ("DEMO002", "Example Bank Stocks"),
            ("DEMO003", "Example consumer stocks"),
            ("000001", "Ping An Bank"),
            ("000002", "Vanke A")
        ]
        
        success_count = 0
        
        for stock_symbol, stock_name in sample_stocks:
            print(f"📝 Create {stock_name}({stock_symbol}) analysis report...")
            
            analysis_results, reports = create_sample_report(stock_symbol, stock_name)
            
            success = mongodb_report_manager.save_analysis_report(
                stock_symbol=stock_symbol,
                analysis_results=analysis_results,
                reports=reports
            )
            
            if success:
                success_count += 1
                print(f"✅ {stock_name} Report created successfully")
            else:
                print(f"❌ {stock_name} Report creation failed")
        
        print(f"\n🎉 Finish! Created successfully {success_count}/{len(sample_stocks)} sample reports")
        print("💡 These reports can now be viewed in the web interface")
        
    except Exception as e:
        print(f"❌ Creating sample report failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

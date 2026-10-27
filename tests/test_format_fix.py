#!/usr/bin/env python3
"""
Test format repair
"""

import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_format_analysis_results():
    """Test analysis result formatting function"""
    
    from web.utils.analysis_runner import format_analysis_results
    
    print("🧪 Formatting test analysis results")
    print("=" * 50)
    
    # test case 1: decision is a string
    print("test case 1: decision is a string")
    results1 = {
        'stock_symbol': 'AAPL',
        'analysis_date': '2025-06-27',
        'analysts': ['market', 'fundamentals'],
        'research_depth': 3,
        'llm_model': 'qwen-plus',
        'state': {
            'market_report': 'technical analysis report...',
            'fundamentals_report': 'Fundamental Analysis Report...'
        },
        'decision': 'BUY',  # String format
        'success': True,
        'error': None
    }
    
    try:
        formatted1 = format_analysis_results(results1)
        print("✅ String decision formatted successfully")
        print(f"  decision making: {formatted1['decision']['action']}")
        print(f"  reasoning: {formatted1['decision']['reasoning']}")
    except Exception as e:
        print(f"❌ String decision formatting failed: {e}")
    
    print()
    
    # test case 2: decision is a dictionary
    print("test case 2: decision is a dictionary")
    results2 = {
        'stock_symbol': 'AAPL',
        'analysis_date': '2025-06-27',
        'analysts': ['market', 'fundamentals'],
        'research_depth': 3,
        'llm_model': 'qwen-plus',
        'state': {
            'market_report': 'technical analysis report...',
            'fundamentals_report': 'Fundamental Analysis Report...'
        },
        'decision': {  # Dictionary format
            'action': 'SELL',
            'confidence': 0.8,
            'risk_score': 0.4,
            'target_price': 180.0,
            'reasoning': 'Based on technical analysis, it is recommended to sell'
        },
        'success': True,
        'error': None
    }
    
    try:
        formatted2 = format_analysis_results(results2)
        print("✅ Dictionary decision formatting successful")
        print(f"  decision making: {formatted2['decision']['action']}")
        print(f"  Confidence: {formatted2['decision']['confidence']}")
        print(f"  reasoning: {formatted2['decision']['reasoning']}")
    except Exception as e:
        print(f"❌ Dictionary decision formatting failed: {e}")
    
    print()
    
    # test case 3: decision is other type
    print("test case 3: decision is other type")
    results3 = {
        'stock_symbol': 'AAPL',
        'analysis_date': '2025-06-27',
        'analysts': ['market', 'fundamentals'],
        'research_depth': 3,
        'llm_model': 'qwen-plus',
        'state': {
            'market_report': 'technical analysis report...',
            'fundamentals_report': 'Fundamental Analysis Report...'
        },
        'decision': 123,  # Numeric type
        'success': True,
        'error': None
    }
    
    try:
        formatted3 = format_analysis_results(results3)
        print("✅ Other types of decision formatting successful")
        print(f"  decision making: {formatted3['decision']['action']}")
        print(f"  reasoning: {formatted3['decision']['reasoning']}")
    except Exception as e:
        print(f"❌ Other types of decision formatting failed: {e}")
    
    print()
    
    # test case 4: failed result
    print("test case 4: failed result")
    results4 = {
        'stock_symbol': 'AAPL',
        'success': False,
        'error': 'Analysis failed'
    }
    
    try:
        formatted4 = format_analysis_results(results4)
        print("✅ Failure result formatting successful")
        print(f"  success: {formatted4['success']}")
        print(f"  Error: {formatted4['error']}")
    except Exception as e:
        print(f"❌ Failure result format failed: {e}")

def main():
    """Main test function"""
    print("🧪 Format repair test")
    print("=" * 60)
    
    test_format_analysis_results()
    
    print("\n🎉 Test completed!")

if __name__ == "__main__":
    main()

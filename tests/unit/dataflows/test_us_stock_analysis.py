#!/usr/bin/env python3
"""
Test the US stock analysis function
"""

import sys
import os
sys.path.append('..')

def test_us_stock_market_analysis():
    """Test US stock market analysis"""
    print("🔍 Test US stock market analysis...")
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from langchain_community.llms import Tongyi

        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config['online_tools'] = True

        # Create toolkit
        toolkit = Toolkit()
        toolkit.update_config(config)

        # Check if the toolkit has the correct method
        print(f"✅ Toolkit method checking:")
        print(f"  - get_YFin_data_online: {hasattr(toolkit, 'get_YFin_data_online')}")
        print(f"  - get_china_stock_data: {hasattr(toolkit, 'get_china_stock_data')}")
        
        # Create Tongyi LLM
        llm = Tongyi()
        llm.model_name = 'qwen-turbo'

        # Create ReAct Market Analyst
        analyst = create_market_analyst_react(llm, toolkit)

        # Test US stocks
        test_state = {
            'trade_date': '2025-06-29',
            'company_of_interest': 'AAPL',
            'messages': [('human', 'analysis AAPL')],
            'market_report': ''
        }

        print(f"\n🔄 Start analyzing the U.S. stock market...")
        result = analyst(test_state)
        
        print(f"✅ U.S. stock market analysis completed")
        print(f"Market report length: {len(result['market_report'])}")
        
        if len(result['market_report']) > 100:
            print(f"✅ Report content is normal")
            print(f"Report first 300 characters:")
            print(result['market_report'][:300])
        else:
            print(f"❌ Abnormal report content:")
            print(result['market_report'])
            
        return result
        
    except Exception as e:
        print(f"❌ U.S. stock market analysis fails: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_us_stock_fundamentals_analysis():
    """Test fundamental analysis of U.S. stocks"""
    print("\n" + "="*50)
    print("🔍 Test fundamental analysis of U.S. stocks...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst_react
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from langchain_community.llms import Tongyi

        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config['online_tools'] = True

        # Create toolkit
        toolkit = Toolkit()
        toolkit.update_config(config)

        # Check if the toolkit has the correct method
        print(f"✅ Toolkit method checking:")
        print(f"  - get_YFin_data_online: {hasattr(toolkit, 'get_YFin_data_online')}")
        print(f"  - get_fundamentals_openai: {hasattr(toolkit, 'get_fundamentals_openai')}")
        
        # Create Tongyi LLM
        llm = Tongyi()
        llm.model_name = 'qwen-turbo'

        # Create ReAct Fundamental Analyst
        analyst = create_fundamentals_analyst_react(llm, toolkit)

        # Test US stocks
        test_state = {
            'trade_date': '2025-06-29',
            'company_of_interest': 'AAPL',
            'messages': [('human', 'analysis AAPL')],
            'fundamentals_report': ''
        }

        print(f"\n🔄 Start fundamental analysis of U.S. stocks...")
        result = analyst(test_state)
        
        print(f"✅ Fundamental analysis of U.S. stocks completed")
        print(f"Fundamental report length: {len(result['fundamentals_report'])}")
        
        if len(result['fundamentals_report']) > 100:
            print(f"✅ Report content is normal")
            print(f"Report first 300 characters:")
            print(result['fundamentals_report'][:300])
        else:
            print(f"❌ Abnormal report content:")
            print(result['fundamentals_report'])
            
        return result
        
    except Exception as e:
        print(f"❌ Fundamental analysis of U.S. stocks fails: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🚀 Start U.S. stock analysis test")
    print("="*50)
    
    # Check API key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ Please set the DASHSCOPE_API_KEY environment variable")
        sys.exit(1)
    
    print(f"✅ API Key configured: {api_key[:10]}...")
    
    # Test market analysis
    result1 = test_us_stock_market_analysis()
    
    # Test fundamental analysis
    result2 = test_us_stock_fundamentals_analysis()
    
    print("\n" + "="*50)
    print("🎯 Test summary:")
    print(f"Market Analysis Test: {'✅ success' if result1 else '❌ failed'}")
    print(f"Fundamental Analysis Test: {'✅ success' if result2 else '❌ failed'}")

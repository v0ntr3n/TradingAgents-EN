#!/usr/bin/env python3
"""
LLM Technical analysis, debugging and testing
Specialized in diagnosing the differences in technical analysis between Alibaba Bailian vs DeepSeek
"""

import os
import sys
from datetime import datetime

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_dashscope_technical_analysis():
    """Test the technical analysis of Alibaba Bailian"""
    print("\n🔧 Test Alibaba Bailian technical analysis")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from langchain.schema import HumanMessage
        
        # Create Ali Bailian model
        llm = ChatDashScope(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=2000
        )
        
        print("✅ Alibaba Bailian model was created successfully")
        
        # Test a simple conversation
        print("🔄 Test a simple conversation...")
        simple_messages = [HumanMessage(content="Please briefly introduce the concept of stock technical analysis within 100 words.")]
        simple_response = llm.invoke(simple_messages)
        print(f"📊 Simple dialogue response length: {len(simple_response.content)}character")
        print(f"📋 Simple conversation content: {simple_response.content[:200]}...")
        
        # Test complex technical analysis prompt
        print("\n🔄 Test complex technical analysis prompt...")
        complex_prompt = """Please now generate a detailed technical analysis report based on the following stock data.

Requirements:
1. Reports must be analyzed based on the data provided
2. Contains specific technical indicator values and professional analysis
3. Provide clear investment advice and risk warnings
4. The report length should be no less than 800 words
5. Written in Chinese

Please analyze the technical situation of stock 600036, including:
- Price trend analysis
- Interpretation of technical indicators
- Support and resistance level analysis
- Volume analysis
- investment advice

Stock data:
Stock code: 600036
Stock name: China Merchants Bank
current price: ¥47.13
Increase or decrease: -1.03%
Volume: 61.5 Thousands of hands
"""
        
        complex_messages = [HumanMessage(content=complex_prompt)]
        complex_response = llm.invoke(complex_messages)
        print(f"📊 Complex analysis response length: {len(complex_response.content)}character")
        print(f"📋 Complex analysis content: {complex_response.content[:300]}...")
        
        if len(complex_response.content) < 100:
            print("❌ Alibaba Bailian complex analysis response is too short")
            return False
        else:
            print("✅ Alibaba Bailian complex analysis response is normal")
            return True
        
    except Exception as e:
        print(f"❌ Ali Bailian test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_deepseek_technical_analysis():
    """Technical analysis of testing DeepSeek"""
    print("\n🔧 Test DeepSeek technical analysis")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from langchain.schema import HumanMessage
        
        # Create a DeepSeek model
        llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=2000
        )
        
        print("✅ DeepSeek Model created successfully")
        
        # Test a simple conversation
        print("🔄 Test a simple conversation...")
        simple_messages = [HumanMessage(content="Please briefly introduce the concept of stock technical analysis within 100 words.")]
        simple_response = llm.invoke(simple_messages)
        print(f"📊 Simple dialogue response length: {len(simple_response.content)}character")
        print(f"📋 Simple conversation content: {simple_response.content[:200]}...")
        
        # Test complex technical analysis prompt
        print("\n🔄 Test complex technical analysis prompt...")
        complex_prompt = """Please now generate a detailed technical analysis report based on the following stock data.

Requirements:
1. Reports must be analyzed based on the data provided
2. Contains specific technical indicator values and professional analysis
3. Provide clear investment advice and risk warnings
4. The report length should be no less than 800 words
5. Written in Chinese

Please analyze the technical situation of stock 600036, including:
- Price trend analysis
- Interpretation of technical indicators
- Support and resistance level analysis
- Volume analysis
- investment advice

Stock data:
Stock code: 600036
Stock name: China Merchants Bank
current price: ¥47.13
Increase or decrease: -1.03%
Volume: 61.5 Thousands of hands
"""
        
        complex_messages = [HumanMessage(content=complex_prompt)]
        complex_response = llm.invoke(complex_messages)
        print(f"📊 Complex analysis response length: {len(complex_response.content)}character")
        print(f"📋 Complex analysis content: {complex_response.content[:300]}...")
        
        if len(complex_response.content) < 100:
            print("❌ DeepSeek Complex analysis response is too short")
            return False
        else:
            print("✅ DeepSeek Complex analysis responds normally")
            return True
        
    except Exception as e:
        print(f"❌ DeepSeek test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_sequence_handling():
    """Test complex message sequence processing"""
    print("\n🔧 Test complex message sequence processing")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from langchain.schema import HumanMessage, AIMessage, ToolMessage
        
        # Create Ali Bailian model
        llm = ChatDashScope(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=2000
        )
        
        print("✅ Alibaba Bailian model was created successfully")
        
        # Simulate complex message sequences (similar to what is the case in technical analysis)
        messages = [
            HumanMessage(content="Please analyze the technical aspects of stock 600036"),
            AIMessage(content="I need to get stock data for analysis", tool_calls=[
                {
                    "name": "get_china_stock_data",
                    "args": {"stock_code": "600036", "start_date": "2025-06-10", "end_date": "2025-07-10"},
                    "id": "call_1"
                }
            ]),
            ToolMessage(content="Stock code: 600036\n Stock name: China Merchants Bank\n current price: ¥47.13\n Increase or decrease: -1.03%\n Volume: 61.5 Thousands of hands", tool_call_id="call_1"),
            HumanMessage(content="""Now please generate a detailed technical analysis report based on the data obtained by the above tools.

Requirements:
1. Reports must be analyzed based on real data returned by the tool
2. Contains specific technical indicator values and professional analysis
3. Provide clear investment advice and risk warnings
4. The report length should be no less than 800 words
5. Written in Chinese

Please analyze the technical situation of stock 600036, including:
- Price trend analysis
- Interpretation of technical indicators
- Support and resistance level analysis
- Volume analysis
- investment advice""")
        ]
        
        print("🔄 Test complex message sequences...")
        response = llm.invoke(messages)
        print(f"📊 Complex message sequence response length: {len(response.content)}character")
        print(f"📋 Complex message sequence content: {response.content[:300]}...")
        
        if len(response.content) < 100:
            print("❌ Alibaba Bailian complex message sequence response is too short")
            return False
        else:
            print("✅ Alibaba Bailian complex message sequence response is normal")
            return True
        
    except Exception as e:
        print(f"❌ Complex message sequence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_max_tokens_impact():
    """Test the impact of the max_tokens parameter"""
    print("\n🔧 Test the impact of max_tokens parameter")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from langchain.schema import HumanMessage
        
        prompt = """Please generate a detailed stock technical analysis report, requiring no less than 800 words, including:
1. Price trend analysis
2. Interpretation of technical indicators
3. Support and resistance level analysis
4. Volume analysis
5. investment advice

Stocks: China Merchants Bank(600036)
current price: ¥47.13
"""
        
        # Test different max_tokens settings
        token_settings = [500, 1000, 2000, 4000]
        
        for max_tokens in token_settings:
            print(f"\n🔄 test max_tokens={max_tokens}...")
            
            llm = ChatDashScope(
                model="qwen-plus-latest",
                temperature=0.1,
                max_tokens=max_tokens
            )
            
            messages = [HumanMessage(content=prompt)]
            response = llm.invoke(messages)
            
            print(f"📊 max_tokens={max_tokens}, response length: {len(response.content)}character")
            
            if len(response.content) < 100:
                print(f"❌ max_tokens={max_tokens}Response is too short")
            else:
                print(f"✅ max_tokens={max_tokens}Response is normal")
        
        return True
        
    except Exception as e:
        print(f"❌ max_tokens test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔍 LLM Technical analysis, debugging and testing")
    print("=" * 70)
    print("💡 debug target:")
    print("   - Diagnosing the problem of Alibaba Bailian technical analysis report being too short")
    print("   - Compare the response differences between DeepSeek and Alibaba Bailian")
    print("   - Test complex message sequence processing")
    print("   - Analyze the impact of max_tokens parameter")
    print("=" * 70)
    
    # Run all tests
    tests = [
        ("Alibaba Bailian technical analysis", test_dashscope_technical_analysis),
        ("DeepSeek Technical analysis", test_deepseek_technical_analysis),
        ("Complex message sequence processing", test_message_sequence_handling),
        ("max_tokens Parameter influence", test_max_tokens_impact)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 LLM Technical analysis and debugging summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    print("\n💡 possible solutions:")
    print("   1. Adjust the max_tokens parameter of Ali Bailian")
    print("   2. Optimize prompt design for technical analysis")
    print("   3. Simplify complex message sequences")
    print("   4. Add model-specific processing logic")
    
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()

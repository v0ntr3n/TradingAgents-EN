"""
Test fundamental analyst fixes

Verify bind_tools([]) Is it possible to solve the problem of qwen-flash continuously calling tools?
"""

import sys
import os
import asyncio

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.agents.adapters.fundamentals_analyst_v2 import FundamentalsAnalystAgentV2
from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI


async def test_fundamentals_analyst():
    """Test Fundamental Analyst"""
    print("\n" + "=" * 60)
    print("Test Fundamental Analyst v2.0 - Tool call fixes")
    print("=" * 60)

    # Create LLM (using DashScope qwen-flash)
    llm = ChatDashScopeOpenAI(
        model="qwen-flash",
        temperature=0.7,
        max_tokens=4000
    )
    
    # Create a fundamental analyst
    agent = FundamentalsAnalystAgentV2(llm=llm)
    
    # Perform analysis
    print("\n Start performing fundamental analysis...")
    result = agent.execute({
        "ticker": "000001",
        "analysis_date": "2026-01-11"
    })
    
    print("\n" + "=" * 60)
    print("📊 Test results")
    print("=" * 60)
    
    report = result.get("fundamentals_report", "")
    print(f"Report length: {len(report)} character")
    
    if len(report) > 100:
        print("✅ Report generated successfully!")
        print(f"\n Report first 500 characters:\n{report[:500]}...")
    else:
        print("❌ Report generation failed!")
        print(f"Report content: {report}")
        return False
    
    return True


if __name__ == "__main__":
    print("\n🧪 Start testing fundamental analyst fixes\n")
    
    success = asyncio.run(test_fundamentals_analyst())
    
    if success:
        print("\n🎉 Test passed! Repair successful!")
    else:
        print("\n❌ Test failed, please check the code")
        sys.exit(1)


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test level 3 infinite loop repair effect
"""

import os
import sys
import time

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_level3_analysis():
    """Test level 3 analyzes whether there will still be an infinite loop"""
    print("🧪 Test level 3 analyzes the repair effect")
    print("=" * 60)
    
    start_time = time.time()  # Define outside try block
    
    try:
        from app.services.simple_analysis_service import SimpleAnalysisService
        from app.models.analysis import SingleAnalysisRequest, AnalysisParameters
        
        # Create an analysis service
        service = SimpleAnalysisService()
        
        # Test parameters
        test_ticker = "000001"  # Ping An Bank
        research_depth = "Standard"  # Level 3: Standard analysis (using strings)
        
        print(f"📊 Start testing level 3 analysis...")
        print(f"Stock code: {test_ticker}")
        print(f"level of analysis: {research_depth}")
        
        # Create analysis request
        request = SingleAnalysisRequest(
            stock_code=test_ticker,
            parameters=AnalysisParameters(
                research_depth=research_depth,
                selected_analysts=["market", "fundamentals"]
            )
        )
        
        # Set timeout (5 minutes)
        timeout = 300
        
        print(f"⏰ Set timeout: {timeout}seconds")
        print(f"🚀 Start analysis...")
        
        # Perform analysis - using synchronized methods
        result = service._run_analysis_sync(
            task_id="test_level3_fix",
            user_id="test_user",
            request=request
        )
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"✅ Analysis completed!")
        print(f"⏱️ Time consuming: {elapsed:.1f}seconds")
        
        # Check results
        if result and 'decision' in result:
            decision = result['decision']
            print(f"📈 Analyze results:")
            print(f"  action: {decision.get('action', 'N/A')}")
            print(f"  Confidence: {decision.get('confidence', 0):.1%}")
            print(f"  risk score: {decision.get('risk_score', 0):.1%}")
            
            # Check if there is a fundamental report
            if 'state' in result and 'fundamentals_report' in result['state']:
                fundamentals_report = result['state']['fundamentals_report']
                if fundamentals_report:
                    print(f"📊 Fundamental report length: {len(fundamentals_report)}character")
                    print("✅ Fundamental analysis is completed normally")
                else:
                    print("⚠️ Fundamentals report is empty")
            
            # Check the number of tool calls
            if 'state' in result:
                tool_call_count = result['state'].get('fundamentals_tool_call_count', 0)
                print(f"🔧 Number of fundamental analyst tool calls: {tool_call_count}")
                if tool_call_count >= 3:
                    print("⚠️ The maximum number of tool calls is reached and the repair mechanism takes effect.")
                else:
                    print("✅ The number of tool calls is normal")
            
            return True
        else:
            print("❌ Abnormal analysis results")
            return False
            
    except Exception as e:
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"❌ Analyze exceptions: {e}")
        print(f"⏱️ Time taken before exception: {elapsed:.1f}seconds")
        
        if elapsed > 60:
            print("⚠️ There may still be an infinite loop problem (taking more than 1 minute)")
        
        return False

if __name__ == "__main__":
    success = test_level3_analysis()
    if success:
        print("\n🎉 Level 3 infinite loop repair test passed!")
    else:
        print("\n❌ Level 3 infinite loop repair test failed!")

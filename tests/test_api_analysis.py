#!/usr/bin/env python3
"""
Script to test API analysis function
"""

import requests
import time
import json

def test_api_analysis():
    """Test API analysis function"""
    print("🔍 Test API analysis function")
    print("=" * 60)
    
    # API Basics URL
    base_url = "http://localhost:8000"
    
    try:
        # 1. Check API health status
        print("1. Check API health status...")
        health_response = requests.get(f"{base_url}/api/health")
        if health_response.status_code == 200:
            print("✅ API Service is running normally")
        else:
            print(f"❌ API Service exception: {health_response.status_code}")
            return False
        
        # 2. Submit an analysis request
        print("\n2. Submit an analysis request...")
        analysis_request = {
            "stock_code": "000002",
            "parameters": {
                "market_type": "A shares",
                "analysis_date": "2025-08-20",
                "research_depth": "fast",
                "selected_analysts": ["market"],  # Use only market analysts for quick testing
                "include_sentiment": False,
                "include_risk": False,
                "language": "zh-CN",
                "quick_analysis_model": "qwen-turbo",
                "deep_analysis_model": "qwen-max"
            }
        }
        
        # Add authentication header (if needed)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer admin_token"  # Use administrator token
        }
        
        response = requests.post(
            f"{base_url}/api/analysis/single",
            json=analysis_request,
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            task_id = result.get("task_id")
            print(f"✅ Analysis task has been submitted: {task_id}")
        else:
            print(f"❌ Failed to submit analysis request: {response.status_code}")
            print(f"   response: {response.text}")
            return False
        
        # 3. Monitor task status
        print(f"\n3. Monitor task status...")
        max_wait_time = 300  # Wait up to 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status_response = requests.get(
                f"{base_url}/api/analysis/tasks/{task_id}/status",
                headers=headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get("status")
                progress = status_data.get("progress", 0)
                message = status_data.get("message", "")
                
                print(f"   Status: {status}, Progress: {progress}%, news: {message}")
                
                if status == "completed":
                    print("✅ Analysis task completed!")
                    
                    # Get analysis results
                    result_response = requests.get(
                        f"{base_url}/api/analysis/tasks/{task_id}/result",
                        headers=headers
                    )
                    
                    if result_response.status_code == 200:
                        result_data = result_response.json()
                        print(f"\n📊 Analyze results:")
                        print(f"   Stock code: {result_data.get('stock_code')}")
                        print(f"   Analysis date: {result_data.get('analysis_date')}")
                        
                        # Check report content
                        reports = result_data.get('reports', {})
                        for report_type, content in reports.items():
                            if isinstance(content, str) and len(content) > 0:
                                print(f"   {report_type}: There is content (length: {len(content)})")
                            else:
                                print(f"   {report_type}: No content or empty")
                        
                        return True
                    else:
                        print(f"❌ Failed to obtain analysis results: {result_response.status_code}")
                        return False
                        
                elif status == "failed":
                    print(f"❌ Analysis task failed: {message}")
                    return False
                    
            else:
                print(f"❌ Failed to query task status: {status_response.status_code}")
                return False
            
            # Query again after waiting 5 seconds
            time.sleep(5)
        
        print(f"⏰ Task execution timeout (exceed{max_wait_time}seconds)")
        return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_api_analysis()
    if success:
        print("\n🎉 API Analysis function test successful!")
    else:
        print("\n💥 API Analysis function test failed!")

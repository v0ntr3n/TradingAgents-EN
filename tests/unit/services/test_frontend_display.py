#!/usr/bin/env python3
"""
Script to test front-end display issues
"""

import requests
import time
import json

def test_frontend_display():
    """Test front-end display issues"""
    print("🔍 Test front-end display issues")
    print("=" * 60)
    
    # API Basics URL
    base_url = "http://localhost:8000"
    
    try:
        # 1. Log in to get token
        print("1. Log in to get token...")
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        login_response = requests.post(
            f"{base_url}/api/auth/login",
            json=login_data
        )
        
        if login_response.status_code == 200:
            login_result = login_response.json()
            access_token = login_result["data"]["access_token"]
            print("✅ Log in successfully and get token")
        else:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        # 2. Submit an analysis request
        print("\n2. Submit an analysis request...")
        analysis_request = {
            "stock_code": "000004",  # Use new ticker
            "parameters": {
                "market_type": "A shares",
                "analysis_date": "2025-08-20",
                "research_depth": "fast",
                "selected_analysts": ["market"],
                "include_sentiment": False,
                "include_risk": False,
                "language": "zh-CN",
                "quick_analysis_model": "qwen-turbo",
                "deep_analysis_model": "qwen-max"
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.post(
            f"{base_url}/api/analysis/single",
            json=analysis_request,
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            task_id = result["data"]["task_id"]
            print(f"✅ Analysis task has been submitted: {task_id}")
        else:
            print(f"❌ Failed to submit analysis request: {response.status_code}")
            return False
        
        # 3. Wait for task to complete
        print(f"\n3. Wait for task to complete...")
        for i in range(60):  # Wait up to 5 minutes
            status_response = requests.get(
                f"{base_url}/api/analysis/tasks/{task_id}/status",
                headers=headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data["data"]["status"]
                
                if status == "completed":
                    print("✅ Analysis task completed!")
                    break
                elif status == "failed":
                    print(f"❌ Analysis task failed")
                    return False
            
            time.sleep(5)
        else:
            print(f"⏰ Task execution timeout")
            return False
        
        # 4. Test the new result endpoint
        print(f"\n4. Test the new result endpoint...")
        result_response = requests.get(
            f"{base_url}/api/analysis/tasks/{task_id}/result",
            headers=headers
        )
        
        if result_response.status_code == 200:
            result_data = result_response.json()
            print(f"✅ Successfully obtained analysis results")
            
            # Check data structure
            data = result_data["data"]
            print(f"\n📊 Result data structure check:")
            print(f"   stock_code: {data.get('stock_code', 'NOT_FOUND')}")
            print(f"   stock_symbol: {data.get('stock_symbol', 'NOT_FOUND')}")
            print(f"   analysis_date: {data.get('analysis_date', 'NOT_FOUND')}")
            
            # Check reports field
            reports = data.get('reports', {})
            if reports:
                print(f"✅ Find the reports field, containing {len(reports)} reports:")
                for report_type, content in reports.items():
                    if isinstance(content, str):
                        print(f"   - {report_type}: {len(content)} character")
                    else:
                        print(f"   - {report_type}: {type(content)}")
            else:
                print(f"❌ reports field not found or empty")
                
                # Check the detailed_analysis field
                detailed_analysis = data.get('detailed_analysis')
                if detailed_analysis:
                    print(f"⚠️ But find the detailed_analysis field: {type(detailed_analysis)}")
                    if isinstance(detailed_analysis, dict):
                        print(f"   detailed_analysis key: {list(detailed_analysis.keys())}")
                        for key, value in detailed_analysis.items():
                            if isinstance(value, str) and len(value) > 50:
                                print(f"   - {key}: {len(value)} character (available as report)")
                else:
                    print(f"❌ The detailed_analysis field was not found either.")
            
            return True
        else:
            print(f"❌ Failed to obtain analysis results: {result_response.status_code}")
            print(f"   response: {result_response.text}")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_frontend_display()
    if success:
        print("\n🎉 The front end shows that the test is successful!")
    else:
        print("\n💥 The front end shows that the test failed!")

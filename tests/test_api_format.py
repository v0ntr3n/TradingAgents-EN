#!/usr/bin/env python3
"""
Test the data format returned by the API
"""

import requests
import time
import json

def test_api_format():
    """Test the data format returned by the API"""
    print("🔍 Test the data format returned by the API")
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
            "stock_code": "000008",  # Use new ticker
            "parameters": {
                "market_type": "A shares",
                "analysis_date": "2025-08-20",
                "research_depth": "fast",
                "selected_analysts": ["market"],  # Select just one analyst for a quick test
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
            print(f"   response: {response.text}")
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
                progress = status_data["data"].get("progress", 0)
                message = status_data["data"].get("message", "")
                
                print(f"   Status: {status}, Progress: {progress}%, news: {message}")
                
                if status == "completed":
                    print("✅ Analysis task completed!")
                    break
                elif status == "failed":
                    print(f"❌ Analysis task failed: {message}")
                    return False
            
            time.sleep(5)
        else:
            print(f"⏰ Task execution timeout")
            return False
        
        # 4. Test the data format returned by the API
        print(f"\n4. Test the data format returned by the API...")
        result_response = requests.get(
            f"{base_url}/api/analysis/tasks/{task_id}/result",
            headers=headers
        )
        
        if result_response.status_code == 200:
            result_data = result_response.json()
            data = result_data["data"]
            
            print(f"✅ Successfully obtained analysis results")
            print(f"   stock_symbol: {data.get('stock_symbol')}")
            print(f"   analysts: {data.get('analysts', [])}")
            
            # Check the data type of the reports field
            reports = data.get('reports', {})
            if reports:
                print(f"✅ API Return contains {len(reports)} reports:")
                for report_type, content in reports.items():
                    content_type = type(content).__name__
                    if isinstance(content, str):
                        print(f"   ✅ {report_type}: {content_type} ({len(content)} character)")
                        # Check if the content contains valid text
                        if len(content.strip()) > 10:
                            print(f"      Preview: {content[:100].replace(chr(10), ' ')}...")
                        else:
                            print(f"      ⚠️ Content is too short: '{content}'")
                    else:
                        print(f"   ❌ {report_type}: {content_type} (should be str)")
                        print(f"      value: {content}")
                
                # Validate the fields expected by the front end
                expected_fields = ['market_report', 'fundamentals_report', 'investment_plan', 'final_trade_decision']
                print(f"\n🎯 Check the fields expected by the front end:")
                for field in expected_fields:
                    if field in reports:
                        content = reports[field]
                        if isinstance(content, str) and len(content.strip()) > 10:
                            print(f"   ✅ {field}: Valid string content")
                        else:
                            print(f"   ⚠️ {field}: Content is invalid or too short")
                    else:
                        print(f"   ❌ {field}: Missing")
                
                return True
            else:
                print(f"❌ API Return does not include reports field")
                return False
        else:
            print(f"❌ Failed to get API results: {result_response.status_code}")
            print(f"   response: {result_response.text}")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_api_format()
    if success:
        print("\n🎉 API Data format test successful!")
    else:
        print("\n💥 API Data format test failed!")

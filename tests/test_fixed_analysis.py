#!/usr/bin/env python3
"""
Test the repaired analysis functionality
"""

import requests
import time
import json
from pathlib import Path

def test_fixed_analysis():
    """Test the repaired analysis functionality"""
    print("🔍 Test the repaired analysis functionality")
    print("=" * 60)

    # API Basics URL
    base_url = "http://localhost:8000"

    try:
        # 1. Check API health status
        print("1. Check API health status...")
        response = requests.get(f"{base_url}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ API Service is running normally")
        else:
            print(f"❌ API Service exception: {response.status_code}")
            return False

        # 2. Log in to get token
        print("\n2. Log in to get token...")
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
            print(f"   response: {login_response.text}")
            return False
        
        # 3. Submit an analysis request
        print("\n3. Submit an analysis request...")
        analysis_request = {
            "stock_code": "000001",  # Test with different tickers
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

        # Use the obtained token
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
            task_id = result.get("task_id")
            print(f"✅ Analysis task has been submitted: {task_id}")
        else:
            print(f"❌ Failed to submit analysis request: {response.status_code}")
            print(f"   response: {response.text}")
            return False
        
        # 4. Monitor task status
        print(f"\n4. Monitor task status...")
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

                    # 5. Check file save (should use correct ticker)
                    print(f"\n5. Check file save...")
                    
                    # Check the data directory (should be 000001 not UNKNOWN)
                    data_dir = Path("data/analysis_results/000001/2025-08-20")
                    if data_dir.exists():
                        print(f"✅ Analysis results directory exists: {data_dir}")
                        
                        # Check the reports directory
                        reports_dir = data_dir / "reports"
                        if reports_dir.exists():
                            report_files = list(reports_dir.glob("*.md"))
                            if report_files:
                                print(f"✅ found {len(report_files)} report files:")
                                for file in report_files:
                                    print(f"   - {file.name}")
                                    
                                # Check the market analysis report content
                                market_report = reports_dir / "market_report.md"
                                if market_report.exists():
                                    with open(market_report, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                        if len(content) > 100:
                                            print(f"✅ The market analysis report has content (length: {len(content)})")
                                            # Check if the correct stock symbol is included
                                            if "000001" in content:
                                                print(f"✅ Report contains correct ticker symbol: 000001")
                                            else:
                                                print(f"⚠️ Stock symbol not found in report 000001")
                                        else:
                                            print(f"⚠️ Market analysis report content is too short")
                            else:
                                print(f"⚠️ reports Directory exists but no report files")
                        else:
                            print(f"❌ reports Directory does not exist")
                    else:
                        print(f"❌ The analysis results directory does not exist: {data_dir}")
                        # Check whether it is still saved to the UNKNOWN directory
                        unknown_dir = Path("data/analysis_results/UNKNOWN/2025-08-20")
                        if unknown_dir.exists():
                            print(f"⚠️ The file was saved to the UNKNOWN directory, and there was a problem with the stock code transfer.")
                    
                    # 6. Get analysis results
                    print(f"\n6. Get analysis results...")
                    result_response = requests.get(
                        f"{base_url}/api/analysis/tasks/{task_id}/result",
                        headers=headers
                    )
                    
                    if result_response.status_code == 200:
                        result_data = result_response.json()
                        print(f"✅ Successfully obtained analysis results")
                        print(f"   Stock code: {result_data.get('stock_code')}")
                        print(f"   stock symbol: {result_data.get('stock_symbol')}")
                        print(f"   Analysis date: {result_data.get('analysis_date')}")
                        
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
    success = test_fixed_analysis()
    if success:
        print("\n🎉 The repaired analysis function was successfully tested!")
    else:
        print("\n💥 Fixed analysis function test fails!")

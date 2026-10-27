#!/usr/bin/env python3
"""
Test reports and analysts field fixes
"""

import requests
import time
import json
from pymongo import MongoClient

def test_reports_and_analysts_fix():
    """Test reports and analysts field fixes"""
    print("🔍 Test reports and analysts field fixes")
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
        
        # 2. Submit an analysis request (contain multiple analysts)
        print("\n2. Submit an analysis request...")
        analysis_request = {
            "stock_code": "000006",  # Use new ticker
            "parameters": {
                "market_type": "A shares",
                "analysis_date": "2025-08-20",
                "research_depth": "Depth",  # Use deep analysis
                "selected_analysts": ["market", "fundamentals", "sentiment"],  # Select multiple analysts
                "include_sentiment": True,
                "include_risk": True,
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
            print(f"📋 Selected Analyst: {analysis_request['parameters']['selected_analysts']}")
        else:
            print(f"❌ Failed to submit analysis request: {response.status_code}")
            return False
        
        # 3. Wait for task to complete
        print(f"\n3. Wait for task to complete...")
        for i in range(120):  # Wait up to 10 minutes (longer for in-depth analysis)
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
                    print(f"❌ Analysis task failed")
                    return False
            
            time.sleep(5)
        else:
            print(f"⏰ Task execution timeout")
            return False
        
        # 4. Check the results returned by the API
        print(f"\n4. Check the results returned by the API...")
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
            print(f"   research_depth: {data.get('research_depth')}")
            
            # Check reports field
            reports = data.get('reports', {})
            if reports:
                print(f"✅ API Return contains {len(reports)} reports:")
                for report_type, content in reports.items():
                    if isinstance(content, str):
                        print(f"   - {report_type}: {len(content)} character")
                    else:
                        print(f"   - {report_type}: {type(content)}")
            else:
                print(f"❌ API Return does not include reports field")
        else:
            print(f"❌ Failed to get API results: {result_response.status_code}")
        
        # 5. Check MongoDB saved data
        print(f"\n5. Check MongoDB saved data...")
        
        try:
            client = MongoClient('mongodb://localhost:27017/')
            db = client['tradingagents']
            collection = db['analysis_reports']
            
            # Find the latest record
            latest_record = collection.find({"stock_symbol": "000006"}).sort("created_at", -1).limit(1)
            
            for record in latest_record:
                print(f"📋 MongoDB record details:")
                print(f"   analysis_id: {record.get('analysis_id')}")
                print(f"   stock_symbol: {record.get('stock_symbol')}")
                print(f"   analysts: {record.get('analysts', [])}")
                print(f"   research_depth: {record.get('research_depth')}")
                
                # Check reports field
                reports = record.get('reports', {})
                if reports:
                    print(f"✅ MongoDB contains {len(reports)} reports:")
                    for report_type, content in reports.items():
                        if isinstance(content, str):
                            print(f"   - {report_type}: {len(content)} character")
                            # Displays the first 100 characters of the report content as a preview
                            preview = content[:100].replace('\n', ' ')
                            print(f"     Preview: {preview}...")
                        else:
                            print(f"   - {report_type}: {type(content)}")
                    
                    return True
                else:
                    print(f"❌ MongoDB reports field is not included or is empty")
                    return False
            
            print(f"❌ MongoDB record not found")
            return False
            
        except Exception as e:
            print(f"❌ MongoDB Check failed: {e}")
            return False
        finally:
            if 'client' in locals():
                client.close()
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_reports_and_analysts_fix()
    if success:
        print("\n🎉 reports and analysts field repair test successful!")
    else:
        print("\n💥 reports and analysts field fix test failure!")

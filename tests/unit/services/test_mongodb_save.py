#!/usr/bin/env python3
"""
Test MongoDB save functionality
"""

import requests
import time
import json
from pymongo import MongoClient

def check_mongodb_before_after():
    """Check MongoDB data before and after saving"""
    print("🔍 Test MongoDB save functionality")
    print("=" * 60)
    
    # connect MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/')
        db = client['tradingagents']
        collection = db['analysis_reports']
        
        # Check the number of records before saving
        before_count = collection.count_documents({})
        print(f"📊 Number of analysis_reports records before saving: {before_count}")
        
    except Exception as e:
        print(f"❌ MongoDB Connection failed: {e}")
        return False
    
    # API Basics URL
    base_url = "http://localhost:8000"
    
    try:
        # 1. Log in to get token
        print("\n1. Log in to get token...")
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
            "stock_code": "000005",  # Use new ticker
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
        
        # 4. Check MongoDB save results
        print(f"\n4. Check MongoDB save results...")
        
        # Check the number of saved records
        after_count = collection.count_documents({})
        print(f"📊 Number of analysis_reports records after saving: {after_count}")
        
        if after_count > before_count:
            print(f"✅ MongoDB records added {after_count - before_count} Article")
            
            # Get the latest record
            latest_record = collection.find().sort("created_at", -1).limit(1)
            for record in latest_record:
                print(f"\n📋 Latest record details:")
                print(f"   analysis_id: {record.get('analysis_id')}")
                print(f"   stock_symbol: {record.get('stock_symbol')}")
                print(f"   analysis_date: {record.get('analysis_date')}")
                print(f"   status: {record.get('status')}")
                print(f"   source: {record.get('source')}")
                
                # Check reports field
                reports = record.get('reports', {})
                if reports:
                    print(f"✅ Find the reports field, containing {len(reports)} reports:")
                    for report_type, content in reports.items():
                        if isinstance(content, str):
                            print(f"   - {report_type}: {len(content)} character")
                        else:
                            print(f"   - {report_type}: {type(content)}")
                else:
                    print(f"❌ reports field not found or empty")
                
                return True
        else:
            print(f"❌ MongoDB The number of records has not increased")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    success = check_mongodb_before_after()
    if success:
        print("\n🎉 MongoDB Save test successful!")
    else:
        print("\n💥 MongoDB Saving test failed!")

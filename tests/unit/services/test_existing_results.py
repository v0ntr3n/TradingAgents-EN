#!/usr/bin/env python3
"""
Test existing analysis results
"""

import requests
import json
from pymongo import MongoClient
import os
from dotenv import load_dotenv

def get_existing_task_ids():
    """Get existing tasks from MongoDB ID"""
    try:
        # Load environment variables
        load_dotenv()
        
        # Get MongoDB configuration from environment variables
        mongodb_host = os.getenv("MONGODB_HOST", "localhost")
        mongodb_port = int(os.getenv("MONGODB_PORT", "27017"))
        mongodb_username = os.getenv("MONGODB_USERNAME")
        mongodb_password = os.getenv("MONGODB_PASSWORD")
        mongodb_database = os.getenv("MONGODB_DATABASE", "tradingagents")
        mongodb_auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
        
        # Build connection parameters
        connect_kwargs = {
            "host": mongodb_host,
            "port": mongodb_port,
            "serverSelectionTimeoutMS": 5000,
            "connectTimeoutMS": 5000
        }

        # If you have a username and password, add authentication information
        if mongodb_username and mongodb_password:
            connect_kwargs.update({
                "username": mongodb_username,
                "password": mongodb_password,
                "authSource": mongodb_auth_source
            })
        
        # connect MongoDB
        client = MongoClient(**connect_kwargs)
        db = client[mongodb_database]
        
        # Get the most recent tasks from the analysis_reports collection
        reports_collection = db['analysis_reports']
        recent_reports = reports_collection.find(
            {"source": "api", "task_id": {"$exists": True}},
            {"task_id": 1, "analysis_id": 1, "stock_symbol": 1, "created_at": 1}
        ).sort("created_at", -1).limit(5)
        
        task_ids = []
        for report in recent_reports:
            task_ids.append({
                "task_id": report.get("task_id"),
                "analysis_id": report.get("analysis_id"),
                "stock_symbol": report.get("stock_symbol"),
                "created_at": report.get("created_at")
            })
        
        client.close()
        return task_ids
        
    except Exception as e:
        print(f"❌ Failed to get task ID: {e}")
        return []

def test_existing_result(task_id, stock_symbol):
    """Test existing analysis results"""
    print(f"\n🔍 Test results are available: {task_id} ({stock_symbol})")
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
            print("✅ Login successful")
        else:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        # 2. Check task status
        print(f"\n2. Check task status...")
        status_response = requests.get(
            f"{base_url}/api/analysis/tasks/{task_id}/status",
            headers=headers
        )
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            status = status_data["data"]["status"]
            print(f"   Task status: {status}")
            
            if status != "completed":
                print(f"   ⚠️ Task not completed, skipped")
                return False
        else:
            print(f"   ❌ Failed to get status: {status_response.status_code}")
            return False
        
        # 3. Get analysis results
        print(f"\n3. Get analysis results...")
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
                            preview = content[:100].replace('\n', ' ').replace('\r', ' ')
                            print(f"      Preview: {preview}...")
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
                
                # Show complete data structure for debugging
                print(f"\n🔍 Complete data structure:")
                for key, value in data.items():
                    print(f"   {key}: {type(value).__name__}")
                    if isinstance(value, dict) and len(value) > 0:
                        print(f"      subfield: {list(value.keys())}")
                
                return False
        else:
            print(f"❌ Failed to get API results: {result_response.status_code}")
            print(f"   response: {result_response.text}")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def main():
    """main function"""
    print("🔍 Test existing analysis results")
    print("=" * 80)
    
    # Get existing tasks ID
    print("📋 Get existing tasks ID...")
    task_ids = get_existing_task_ids()
    
    if not task_ids:
        print("❌ No existing tasks found")
        return
    
    print(f"✅ found {len(task_ids)} tasks:")
    for i, task_info in enumerate(task_ids, 1):
        print(f"   {i}. {task_info['task_id']} - {task_info['stock_symbol']} ({task_info['created_at']})")
    
    # Test the latest tasks
    latest_task = task_ids[0]
    success = test_existing_result(latest_task['task_id'], latest_task['stock_symbol'])
    
    if success:
        print(f"\n🎉 Test successful! Task {latest_task['task_id']} The API return format is correct")
    else:
        print(f"\n💥 test failed! Task {latest_task['task_id']} There is a problem with the API return format")

if __name__ == "__main__":
    main()

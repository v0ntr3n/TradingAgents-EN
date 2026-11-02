#!/usr/bin/env python3
"""
Test whether decision data is saved and obtained correctly
"""
import requests
import json
from datetime import datetime

def test_decision_data():
    """The complete process of testing decision data"""
    base_url = "http://localhost:8000"
    
    # Log in to get token
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    response = requests.post(
        f"{base_url}/api/auth/login",
        json=login_data,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        return
    
    result = response.json()
    if not result.get("success"):
        print(f"❌ Login failed: {result.get('message')}")
        return
    
    token = result["data"]["access_token"]
    print(f"✅ Login successful")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        print(f"\n🧪 Test decision data flow")
        print("=" * 50)
        
        # 1. Start a new analysis task
        print(f"\n1. Start a new analysis task...")
        analysis_request = {
            "stock_code": "000001",
            "parameters": {
                "research_depth": "fast",
                "selected_analysts": ["market", "fundamentals"]
            }
        }
        
        start_response = requests.post(
            f"{base_url}/api/analysis/single",
            json=analysis_request,
            headers=headers
        )
        
        if start_response.status_code != 200:
            print(f"❌ Failed to start analysis: {start_response.status_code}")
            print(f"   error message: {start_response.text}")
            return
        
        start_data = start_response.json()
        if not start_data.get("success"):
            print(f"❌ Failed to start analysis: {start_data.get('message')}")
            return
        
        task_id = start_data["data"]["task_id"]
        print(f"✅ Analysis task started successfully: {task_id}")
        
        # 2. Wait for task to complete
        print(f"\n2. Wait for task to complete...")
        import time
        max_wait = 300  # Wait up to 5 minutes
        wait_time = 0
        
        while wait_time < max_wait:
            status_response = requests.get(
                f"{base_url}/api/analysis/tasks/{task_id}/status",
                headers=headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get("success"):
                    status = status_data["data"]["status"]
                    print(f"   Task status: {status}")
                    
                    if status == "completed":
                        print(f"✅ Mission accomplished!")
                        break
                    elif status == "failed":
                        print(f"❌ Task failed!")
                        return
            
            time.sleep(10)
            wait_time += 10
        
        if wait_time >= max_wait:
            print(f"❌ Task timeout!")
            return
        
        # 3. Get full results
        print(f"\n3. Get full analysis results...")
        result_response = requests.get(
            f"{base_url}/api/analysis/tasks/{task_id}/result",
            headers=headers
        )
        
        if result_response.status_code != 200:
            print(f"❌ Failed to get results: {result_response.status_code}")
            print(f"   error message: {result_response.text}")
            return
        
        result_data = result_response.json()
        if not result_data.get("success"):
            print(f"❌ Failed to get results: {result_data.get('message')}")
            return
        
        analysis_result = result_data["data"]
        
        # 4. Check the decision field
        print(f"\n4. Check decision data...")
        print(f"   There is a decision field: {bool(analysis_result.get('decision'))}")
        
        if analysis_result.get('decision'):
            decision = analysis_result['decision']
            print(f"   Decision data structure:")
            print(f"     action: {decision.get('action', 'None')}")
            print(f"     target_price: {decision.get('target_price', 'None')}")
            print(f"     confidence: {decision.get('confidence', 'None')}")
            print(f"     risk_score: {decision.get('risk_score', 'None')}")
            print(f"     reasoning: {len(str(decision.get('reasoning', '')))} character")
            
            # Save decision data for checking
            with open('decision_sample.json', 'w', encoding='utf-8') as f:
                json.dump(decision, f, ensure_ascii=False, indent=2, default=str)
            print(f"   Decision Data has been saved to decision_sample.json")
        else:
            print(f"   ❌ decision field not found!")
            print(f"   Available fields: {list(analysis_result.keys())}")
        
        # 5. Check data in MongoDB
        print(f"\n5. Check data in MongoDB...")
        reports_response = requests.get(
            f"{base_url}/api/reports/list?search_keyword={task_id}",
            headers=headers
        )
        
        if reports_response.status_code == 200:
            reports_data = reports_response.json()
            if reports_data.get("success") and reports_data["data"]["reports"]:
                report = reports_data["data"]["reports"][0]
                report_id = report["id"]
                
                # Get report details
                detail_response = requests.get(
                    f"{base_url}/api/reports/{report_id}/detail",
                    headers=headers
                )
                
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    if detail_data.get("success"):
                        report_detail = detail_data["data"]
                        print(f"   MongoDB There is a decision field in: {bool(report_detail.get('decision'))}")
                        
                        if report_detail.get('decision'):
                            mongo_decision = report_detail['decision']
                            print(f"   MongoDB Decision data:")
                            print(f"     action: {mongo_decision.get('action', 'None')}")
                            print(f"     target_price: {mongo_decision.get('target_price', 'None')}")
                            print(f"     confidence: {mongo_decision.get('confidence', 'None')}")
                        else:
                            print(f"   ❌ MongoDB There is no decision field in!")
                            print(f"   MongoDB Available fields: {list(report_detail.keys())}")
        
        print(f"\n🎉 Decision Data test completed!")
        
    except Exception as e:
        print(f"❌ An exception occurred during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print(f"start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    test_decision_data()
    print(f"\n end time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

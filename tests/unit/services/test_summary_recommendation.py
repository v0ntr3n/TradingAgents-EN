#!/usr/bin/env python3
"""
Test summary and recommendation fields
"""
import requests
import json

def test_summary_recommendation():
    """Test summary and recommendation fields"""
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
    
    # Use the latest tasks ID
    task_id = "b407e811-e593-416f-8e7f-3e75d37e8b8b"
    
    print(f"\n🔍 Check tasks {task_id} summary and recommendation fields")
    
    # Get full results
    result_response = requests.get(
        f"{base_url}/api/analysis/tasks/{task_id}/result",
        headers=headers
    )
    
    if result_response.status_code != 200:
        print(f"❌ Failed to get results: {result_response.status_code}")
        return
    
    result_data = result_response.json()
    if not result_data.get("success"):
        print(f"❌ Failed to get results: {result_data.get('message')}")
        return
    
    analysis_result = result_data["data"]
    
    print(f"\n📊 Field check:")
    print(f"   summary exist: {bool(analysis_result.get('summary'))}")
    print(f"   summary length: {len(analysis_result.get('summary', ''))}")
    print(f"   summary content: {analysis_result.get('summary', 'None')[:100]}...")
    
    print(f"\n   recommendation exist: {bool(analysis_result.get('recommendation'))}")
    print(f"   recommendation length: {len(analysis_result.get('recommendation', ''))}")
    print(f"   recommendation content: {analysis_result.get('recommendation', 'None')[:100]}...")
    
    print(f"\n   decision exist: {bool(analysis_result.get('decision'))}")
    if analysis_result.get('decision'):
        decision = analysis_result['decision']
        print(f"   decision.action: {decision.get('action')}")
        print(f"   decision.target_price: {decision.get('target_price')}")
        print(f"   decision.reasoning: {decision.get('reasoning', '')[:50]}...")
    
    print(f"\n   reports exist: {bool(analysis_result.get('reports'))}")
    if analysis_result.get('reports'):
        reports = analysis_result['reports']
        print(f"   reports key: {list(reports.keys())}")
        if 'final_trade_decision' in reports:
            final_decision = reports['final_trade_decision']
            print(f"   final_trade_decision length: {len(final_decision)}")
            print(f"   final_trade_decision first 100 characters: {final_decision[:100]}...")
    
    # Save complete data for inspection
    with open('full_analysis_result.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Complete analysis results have been saved to full_analysis_result.json")

if __name__ == "__main__":
    test_summary_recommendation()

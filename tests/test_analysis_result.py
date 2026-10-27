#!/usr/bin/env python3
"""
Test analysis result data structure
"""
import requests
import json
from datetime import datetime

def test_analysis_result():
    """Data structure of test analysis results"""
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
        # Get report list
        print("\n1. Get report list...")
        reports_response = requests.get(
            f"{base_url}/api/reports/list?page_size=1",
            headers=headers
        )
        
        if reports_response.status_code != 200:
            print(f"❌ Failed to get report list: {reports_response.status_code}")
            return
        
        reports_data = reports_response.json()
        if not reports_data.get("success") or not reports_data["data"]["reports"]:
            print("❌ Report not found")
            return
        
        # Get details of your first report
        first_report = reports_data["data"]["reports"][0]
        report_id = first_report["id"]
        
        print(f"\n2. Get report details: {report_id}")
        detail_response = requests.get(
            f"{base_url}/api/reports/{report_id}/detail",
            headers=headers
        )
        
        if detail_response.status_code != 200:
            print(f"❌ Failed to get report details: {detail_response.status_code}")
            return
        
        detail_data = detail_response.json()
        if not detail_data.get("success"):
            print(f"❌ Failed to get report details: {detail_data.get('message')}")
            return
        
        report_detail = detail_data["data"]
        
        print(f"\n📊 Report data structure analysis:")
        print(f"   report ID: {report_detail.get('id')}")
        print(f"   Stock code: {report_detail.get('stock_symbol')}")
        print(f"   Analysis date: {report_detail.get('analysis_date')}")
        print(f"   Status: {report_detail.get('status')}")
        
        # Check key fields
        print(f"\n🔍 Key field check:")
        print(f"   There is a decision field: {bool(report_detail.get('decision'))}")
        print(f"   There is a state field: {bool(report_detail.get('state'))}")
        print(f"   There is a reports field: {bool(report_detail.get('reports'))}")
        print(f"   There is a recommendation field: {bool(report_detail.get('recommendation'))}")
        
        # Show all top-level fields
        print(f"\n📋 All top-level fields:")
        for key in sorted(report_detail.keys()):
            value = report_detail[key]
            if isinstance(value, dict):
                print(f"   {key}: dict (contains {len(value)} keys)")
                if key == 'reports':
                    print(f"      reports subkey: {list(value.keys())}")
            elif isinstance(value, list):
                print(f"   {key}: list (contains {len(value)} elements)")
            else:
                print(f"   {key}: {type(value).__name__} = {str(value)[:100]}")
        
        # If there is a reports field, detailed analysis
        if report_detail.get('reports'):
            print(f"\n📄 Reports Field detailed analysis:")
            reports = report_detail['reports']
            for key, content in reports.items():
                if isinstance(content, str):
                    print(f"   {key}: string ({len(content)} character)")
                    print(f"      first 100 characters: {content[:100]}...")
                else:
                    print(f"   {key}: {type(content).__name__}")
        
        # Save complete data to file for analysis
        with open('analysis_result_sample.json', 'w', encoding='utf-8') as f:
            json.dump(report_detail, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n💾 Complete data has been saved to analysis_result_sample.json")
        
        # Simulate front-end data processing logic
        print(f"\n🎭 Simulate front-end data processing:")
        
        # Check if the results will be displayed
        has_decision = bool(report_detail.get('decision'))
        has_state = bool(report_detail.get('state'))
        has_reports = bool(report_detail.get('reports'))
        
        print(f"   showResults Conditions: analysisResults exist = True")
        print(f"   decision Partial display: {has_decision}")
        print(f"   reports Partial display (state): {has_state}")
        print(f"   reports Partial display (reports): {has_reports}")
        print(f"   reports Partial display (any): {has_state or has_reports}")
        
        # Mock getAnalysisReports function
        reports_data = None
        if report_detail.get('reports'):
            reports_data = report_detail['reports']
            print(f"   Use data.reports")
        elif report_detail.get('state'):
            reports_data = report_detail['state']
            print(f"   Use data.state")
        else:
            print(f"   Report data not found")
            return
        
        # Check report mapping
        report_mappings = [
            'market_report', 'fundamentals_report', 'news_report', 'sentiment_report',
            'investment_plan', 'trader_investment_plan', 'final_trade_decision',
            'research_team_decision', 'risk_management_decision',
            'investment_debate_state', 'risk_debate_state'
        ]
        
        found_reports = []
        for key in report_mappings:
            if key in reports_data and reports_data[key]:
                found_reports.append(key)
        
        print(f"   Report module found: {found_reports}")
        print(f"   Report quantity: {len(found_reports)}")
        
        if len(found_reports) == 0:
            print(f"   ⚠️ No reporting modules found!")
            print(f"   actual key: {list(reports_data.keys())}")
        
    except Exception as e:
        print(f"❌ An exception occurred during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print(f"start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    test_analysis_result()
    print(f"\n end time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

#!/usr/bin/env python3
"""
Test analysis report API function
"""
import requests
import json
import time
from datetime import datetime

def login_and_get_token(base_url):
    """Log in and get token"""
    login_data = {
        "username": "admin",
        "password": "admin123"
    }

    response = requests.post(
        f"{base_url}/api/auth/login",
        json=login_data,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            token = result["data"]["access_token"]
            print(f"✅ Log in successfully and get token")
            return token
        else:
            print(f"❌ Login failed: {result.get('message', 'unknown error')}")
            return None
    else:
        print(f"❌ Login request failed: {response.status_code}")
        print(f"   error message: {response.text}")
        return None

def test_reports_api():
    """Test reporting API functionality"""
    base_url = "http://localhost:8000"

    # Log in first to get token
    print("0. Log in to get token...")
    token = login_and_get_token(base_url)
    if not token:
        print("❌ Unable to obtain token, test terminated")
        return False

    # use real token
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        print("🧪 Test analysis report API function")
        print("=" * 50)
        
        # 1. Check API health status
        print("\n1. Check API health status...")
        health_response = requests.get(f"{base_url}/api/health")
        if health_response.status_code == 200:
            print("✅ API Service is running normally")
        else:
            print(f"❌ API Service exception: {health_response.status_code}")
            return False
        
        # 2. Get report list
        print("\n2. Get report list...")
        reports_response = requests.get(
            f"{base_url}/api/reports/list",
            headers=headers
        )
        
        if reports_response.status_code == 200:
            reports_data = reports_response.json()
            print(f"✅ Report list obtained successfully")
            print(f"   total: {reports_data['data']['total']}")
            print(f"   Current page: {reports_data['data']['page']}")
            print(f"   Quantity per page: {reports_data['data']['page_size']}")
            print(f"   Report quantity: {len(reports_data['data']['reports'])}")
            
            # Show previous reports
            reports = reports_data['data']['reports']
            if reports:
                print(f"\n📋 First 3 reports:")
                for i, report in enumerate(reports[:3]):
                    print(f"   {i+1}. {report['stock_code']} - {report['analysis_date']}")
                    print(f"      ID: {report['id']}")
                    print(f"      Status: {report['status']}")
                    print(f"      analyst: {', '.join(report['analysts'])}")
                    print(f"      creation time: {report['created_at']}")
                
                # 3. Test Get Report Details
                if reports:
                    test_report = reports[0]
                    print(f"\n3. Get report details...")
                    print(f"   test report ID: {test_report['id']}")
                    
                    detail_response = requests.get(
                        f"{base_url}/api/reports/{test_report['id']}/detail",
                        headers=headers
                    )
                    
                    if detail_response.status_code == 200:
                        detail_data = detail_response.json()
                        print(f"✅ Report details obtained successfully")
                        
                        report_detail = detail_data['data']
                        print(f"   Stock code: {report_detail['stock_symbol']}")
                        print(f"   Analysis date: {report_detail['analysis_date']}")
                        print(f"   Summary length: {len(report_detail.get('summary', ''))}")
                        
                        # Inspection report module
                        reports_content = report_detail.get('reports', {})
                        print(f"   Number of reporting modules: {len(reports_content)}")
                        for module_name, content in reports_content.items():
                            if isinstance(content, str):
                                print(f"     - {module_name}: {len(content)} character")
                            else:
                                print(f"     - {module_name}: {type(content)}")
                        
                        # 4. Test download report
                        print(f"\n4. Test download report...")
                        download_response = requests.get(
                            f"{base_url}/api/reports/{test_report['id']}/download?format=markdown",
                            headers=headers
                        )
                        
                        if download_response.status_code == 200:
                            print(f"✅ Report download successful")
                            print(f"   file size: {len(download_response.content)} Bytes")
                            print(f"   Content-Type: {download_response.headers.get('content-type')}")
                            
                            # Save downloaded file for inspection
                            filename = f"test_download_{test_report['stock_code']}.md"
                            with open(filename, 'wb') as f:
                                f.write(download_response.content)
                            print(f"   saved to: {filename}")
                        else:
                            print(f"❌ Report download failure: {download_response.status_code}")
                            print(f"   error message: {download_response.text}")
                        
                        # 5. Test to get specific module content
                        if reports_content:
                            module_name = list(reports_content.keys())[0]
                            print(f"\n5. Test to get module content...")
                            print(f"   test module: {module_name}")
                            
                            module_response = requests.get(
                                f"{base_url}/api/reports/{test_report['id']}/content/{module_name}",
                                headers=headers
                            )
                            
                            if module_response.status_code == 200:
                                module_data = module_response.json()
                                print(f"✅ Module content obtained successfully")
                                print(f"   module name: {module_data['data']['module']}")
                                print(f"   Content type: {module_data['data']['content_type']}")
                                print(f"   content length: {len(str(module_data['data']['content']))}")
                            else:
                                print(f"❌ Failed to obtain module content: {module_response.status_code}")
                    else:
                        print(f"❌ Failed to obtain report details: {detail_response.status_code}")
                        print(f"   error message: {detail_response.text}")
            else:
                print("⚠️ No report found, you may need to run some analysis tasks first")
        else:
            print(f"❌ Failed to obtain report list: {reports_response.status_code}")
            print(f"   error message: {reports_response.text}")
            return False
        
        # 6. Test search functionality
        print(f"\n6. Test search functionality...")
        search_response = requests.get(
            f"{base_url}/api/reports/list?search_keyword=000001",
            headers=headers
        )
        
        if search_response.status_code == 200:
            search_data = search_response.json()
            print(f"✅ Search function is normal")
            print(f"   Number of search results: {len(search_data['data']['reports'])}")
        else:
            print(f"❌ Search function failed: {search_response.status_code}")
        
        print(f"\n🎉 Report API testing completed!")
        return True
        
    except Exception as e:
        print(f"❌ An exception occurred during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reports_with_filters():
    """Test report query with filter conditions"""
    base_url = "http://localhost:8000"

    # get token
    token = login_and_get_token(base_url)
    if not token:
        print("❌ Unable to obtain token, skip screening test")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    print(f"\n🔍 Test filtering functionality...")
    
    # Test different filters
    filters = [
        {"status_filter": "completed"},
        {"start_date": "2025-08-01", "end_date": "2025-08-31"},
        {"stock_code": "000001"},
        {"page": 1, "page_size": 5}
    ]
    
    for i, filter_params in enumerate(filters):
        print(f"\n   test screening {i+1}: {filter_params}")
        
        params = "&".join([f"{k}={v}" for k, v in filter_params.items()])
        response = requests.get(
            f"{base_url}/api/reports/list?{params}",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Screening successful, number of results: {len(data['data']['reports'])}")
        else:
            print(f"   ❌ Filtering failed: {response.status_code}")

if __name__ == "__main__":
    print(f"start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = test_reports_api()
    
    if success:
        test_reports_with_filters()
    
    print(f"\n end time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

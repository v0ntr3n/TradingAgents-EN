#!/usr/bin/env python3
"""
Test new industries API
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"

def test_industries_api():
    """Testing industry API"""
    print("🧪 Testing industry API")
    print("=" * 50)
    
    # 1. Get access token
    print("\n1. Get access token...")
    auth_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })

    if auth_response.status_code != 200:
        print(f"❌ Login failed: {auth_response.status_code}")
        print(f"   Response content: {auth_response.text}")
        return False

    auth_data = auth_response.json()
    print(f"   Login response: {auth_data}")

    # Try different token field names and paths
    token = None

    # Check nested structures data.access_token
    if "data" in auth_data and isinstance(auth_data["data"], dict):
        data = auth_data["data"]
        for key in ["access_token", "token", "accessToken"]:
            if key in data:
                token = data[key]
                break

    # Check top-level fields
    if not token:
        for key in ["access_token", "token", "accessToken"]:
            if key in auth_data:
                token = auth_data[key]
                break

    if not token:
        print(f"❌ Unable to find access token, response data: {auth_data}")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful")
    
    # 2. Testing industry API
    print("\n2. Testing industry API...")
    response = requests.get(f"{BASE_URL}/api/screening/industries", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        industries = data.get("industries", [])
        total = data.get("total", 0)
        
        print(f"✅ Industry API successful, return {total} industries")
        print(f"\n📊 Top 10 industries (sorted by number of stocks):")
        
        for i, industry in enumerate(industries[:10]):
            print(f"  {i+1:2d}. {industry['label']} ({industry['count']}only stocks)")
        
        if len(industries) > 10:
            print(f"  ... Also {len(industries) - 10} industries")
        
        # Check whether banks, securities, and insurance are on the list
        print(f"\n🏦 Financial industry inspection:")
        financial_industries = ['bank', 'securities', 'insurance']
        for fin_industry in financial_industries:
            found = next((ind for ind in industries if ind['label'] == fin_industry), None)
            if found:
                print(f"  ✅ {fin_industry}: {found['count']}only stocks")
            else:
                print(f"  ❌ {fin_industry}: not found")
        
        return True
    else:
        print(f"❌ Industry API failed: {response.status_code}")
        print(f"   Response content: {response.text}")
        return False

if __name__ == "__main__":
    success = test_industries_api()
    
    if success:
        print("\n🎉 Industry API test successful!")
        print("The front end can now dynamically load real industry data.")
    else:
        print("\n❌ Industry API test failed!")
        print("Need to check the backend API implementation.")

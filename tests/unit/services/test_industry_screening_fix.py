#!/usr/bin/env python3
"""
Test industry screening fix
Verify that the front-end sends industry filter conditions and the back-end correctly processes and returns bank stocks
"""

import asyncio
import requests
import json
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"

async def test_industry_screening():
    """Test industry filtering capabilities"""
    print("🧪 Test industry screening fix")
    print("=" * 50)
    
    # 1. Get access token
    print("\n1. Get access token...")
    auth_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    
    if auth_response.status_code != 200:
        print(f"❌ Login failed: {auth_response.status_code}")
        return False
    
    token = auth_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful")
    
    # 2. Test filter with only market capitalization condition (original problem scenario)
    print("\n2. Test a filter with only market capitalization criteria...")
    market_cap_only_payload = {
        "market": "CN",
        "conditions": {
            "logic": "AND",
            "children": [
                {"field": "market_cap", "op": "between", "value": [5000000, 9007199254740991]}
            ]
        },
        "order_by": [{"field": "market_cap", "direction": "desc"}],
        "limit": 10,
        "offset": 0
    }
    
    response = requests.post(
        f"{BASE_URL}/api/screening/run",
        json=market_cap_only_payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        print(f"✅ Market value screening successful, return {len(items)} only stocks")
        
        # Show the industry distribution of the top 3 stocks
        industries = {}
        for item in items[:3]:
            industry = item.get("industry", "unknown")
            industries[industry] = industries.get(industry, 0) + 1
            print(f"   {item['code']} - {item['name']} - {industry}")
        
        print(f"   Industry distribution: {industries}")
    else:
        print(f"❌ Market value filter failed: {response.status_code}")
        return False
    
    # 3. Test adding filtering for industry conditions (should work after fix)
    print("\n3. Test the screening of conditions for joining the banking industry...")
    industry_payload = {
        "market": "CN", 
        "conditions": {
            "logic": "AND",
            "children": [
                {"field": "market_cap", "op": "between", "value": [5000000, 9007199254740991]},
                {"field": "industry", "op": "in", "value": ["bank"]}
            ]
        },
        "order_by": [{"field": "market_cap", "direction": "desc"}],
        "limit": 10,
        "offset": 0
    }
    
    response = requests.post(
        f"{BASE_URL}/api/screening/run",
        json=industry_payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        print(f"✅ Banking industry screening is successful, return {len(items)} only stocks")
        
        # Verify that all stocks returned are bank stocks
        all_banks = True
        for item in items:
            industry = item.get("industry", "")
            is_bank = "bank" in industry
            print(f"   {item['code']} - {item['name']} - {industry} {'✅' if is_bank else '❌'}")
            if not is_bank:
                all_banks = False
        
        if all_banks and len(items) > 0:
            print("🎉 Repair successful! All stocks returned are bank stocks")
            return True
        elif len(items) == 0:
            print("⚠️  No banking stocks were found. There may be no banking industry data in the database.")
            return False
        else:
            print("❌ Repair failed! Returned to non-bank stocks")
            return False
    else:
        print(f"❌ Banking industry screening failed: {response.status_code}")
        print(f"   Response content: {response.text}")
        return False

def test_frontend_payload():
    """Test the payload format that will be sent after the front-end is repaired"""
    print("\n4. Test the payload format after the front-end repair...")
    
    # Simulate requests sent after front-end repair
    frontend_payload = {
        "market": "CN",
        "conditions": {
            "logic": "AND", 
            "children": [
                {"field": "market_cap", "op": "between", "value": [500 * 10000, 9007199254740991]},  # large cap stocks
                {"field": "industry", "op": "in", "value": ["bank"]}  # banking industry
            ]
        },
        "order_by": [{"field": "market_cap", "direction": "desc"}],
        "limit": 50,
        "offset": 0
    }
    
    print("It will be sent after the front end is repaired.payload:")
    print(json.dumps(frontend_payload, indent=2, ensure_ascii=False))
    
    return frontend_payload

if __name__ == "__main__":
    # Test front-end payload format
    test_frontend_payload()
    
    # Test backend API
    success = asyncio.run(test_industry_screening())
    
    if success:
        print("\n🎉 Industry screening and repair verification successful!")
        print("Now when the user selects the banking industry, only bank stocks should be returned.")
    else:
        print("\n❌ Industry filtering repair verification failed!")
        print("Further inspection of database data or backend logic is required.")

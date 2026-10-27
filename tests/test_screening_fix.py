#!/usr/bin/env python3
"""
Test the fixed filtering functionality
"""

import asyncio
import sys
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_screening_api():
    """test screening API"""
    print("🧪 Test the fixed filtering functionality...")
    
    base_url = "http://localhost:8000"
    
    try:
        # 1. Log in to get token
        print("🔐 Logging in...")
        login_response = requests.post(f"{base_url}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        }, timeout=10)
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        login_data = login_response.json()
        token = login_data["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful")
        
        # 2. test screening API
        print("\n📊 test screening API...")
        
        # Simulate filtering requests sent by the front end
        screening_request = {
            "market": "CN",
            "conditions": {
                "logic": "AND",
                "children": [
                    {
                        "field": "market_cap",
                        "op": "between", 
                        "value": [1000000, 50000000]  # 100 billion to 500 billion (ten thousand yuan)
                    }
                ]
            },
            "order_by": [
                {
                    "field": "market_cap",
                    "direction": "desc"
                }
            ],
            "limit": 10,
            "offset": 0
        }
        
        print(f"📋 Filter criteria: {json.dumps(screening_request, indent=2, ensure_ascii=False)}")
        
        # Send filtering request
        screening_response = requests.post(
            f"{base_url}/api/screening/run",
            json=screening_request,
            headers=headers,
            timeout=30
        )
        
        if screening_response.status_code != 200:
            print(f"❌ Filtering failed: {screening_response.status_code}")
            print(f"Response content: {screening_response.text}")
            return False
        
        screening_data = screening_response.json()
        print(f"✅ Screening successful!")
        print(f"📊 Result statistics:")
        print(f"  - total quantity: {screening_data.get('total', 0)}")
        print(f"  - Return quantity: {len(screening_data.get('items', []))}")
        
        # Show first 5 results
        items = screening_data.get('items', [])
        if items:
            print(f"📋 Top 5 results:")
            for i, item in enumerate(items[:5], 1):
                print(f"  {i}. {item.get('code', 'N/A')} - Market value: {item.get('total_mv', 'N/A')}billion")
        
        # 3. Test more complex filters
        print("\n🔧 Test complex filters...")
        
        complex_request = {
            "market": "CN",
            "conditions": {
                "logic": "AND",
                "children": [
                    {
                        "field": "market_cap",
                        "op": "between",
                        "value": [500000, 20000000]  # 50 billion to 200 billion
                    }
                ]
            },
            "order_by": [
                {
                    "field": "market_cap", 
                    "direction": "desc"
                }
            ],
            "limit": 15,
            "offset": 0
        }
        
        complex_response = requests.post(
            f"{base_url}/api/screening/run",
            json=complex_request,
            headers=headers,
            timeout=30
        )
        
        if complex_response.status_code == 200:
            complex_data = complex_response.json()
            print(f"✅ Complex screening successful!")
            print(f"📊 Result statistics:")
            print(f"  - total quantity: {complex_data.get('total', 0)}")
            print(f"  - Return quantity: {len(complex_data.get('items', []))}")
        else:
            print(f"❌ Complex filter failed: {complex_response.status_code}")
        
        print("\n🎉 Filter function test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Test exception: {e}")
        return False

if __name__ == "__main__":
    test_screening_api()

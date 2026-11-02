#!/usr/bin/env python3
"""
Test real estate related API calls
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"

def test_real_estate_screening():
    """Test real estate screening"""
    print("🏠 Test real estate related filters")
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
    
    # 2. Testing industry API
    print("\n2. Get all industries...")
    response = requests.get(f"{BASE_URL}/api/screening/industries", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        industries = data.get("industries", [])
        
        print(f"✅ Get {len(industries)} industries")
        
        # Find real estate related industries
        real_estate_industries = []
        for industry in industries:
            industry_name = industry['label']
            if any(keyword in industry_name for keyword in ['room', 'real estate', 'architecture', 'decoration', 'Home']):
                real_estate_industries.append(industry)
        
        print(f"\n🏠 Real estate related industries ({len(real_estate_industries)}a):")
        for industry in real_estate_industries:
            print(f"  - {industry['label']} ({industry['count']}only stocks)")
        
        # 3. Test different real estate related filters
        test_industries = []
        if real_estate_industries:
            test_industries = [ind['label'] for ind in real_estate_industries[:3]]  # Test first 3
        else:
            # If not found, try some possible names
            test_industries = ['real estate development', 'architectural decoration', 'building materials', 'Household items']
        
        print(f"\n3. Test real estate related industry screening...")
        for industry_name in test_industries:
            print(f"\n🔍 Testing industry: {industry_name}")
            
            # Construct filter conditions - lower the market capitalization threshold to 10 billion
            screening_request = {
                "conditions": {
                    "logic": "AND",
                    "children": [
                        {"field": "industry", "op": "in", "value": [industry_name]},
                        {"field": "market_cap", "op": "between", "value": [1000000, 9007199254740991]}  # 100 More than 100 million
                    ]
                },
                "order_by": [{"field": "market_cap", "direction": "desc"}],
                "limit": 10
            }
            
            response = requests.post(f"{BASE_URL}/api/screening/run", 
                                   json=screening_request, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                total = result.get("total", 0)
                items = result.get("items", [])
                
                print(f"  ✅ found {total} only stocks")
                if items:
                    print(f"  📊 Top 3 stocks:")
                    for i, stock in enumerate(items[:3]):
                        market_cap = stock.get('total_mv', 0)
                        print(f"    {i+1}. {stock.get('code', 'N/A')} - {stock.get('name', 'N/A')} - {market_cap:.2f}billion")
                else:
                    print(f"  ⚠️ There are no stocks with a market value of more than 10 billion in this industry")
            else:
                print(f"  ❌ Filtering failed: {response.status_code}")
                print(f"     response: {response.text}")
        
        return True
    else:
        print(f"❌ Failed to obtain industry list: {response.status_code}")
        print(f"   Response content: {response.text}")
        return False

if __name__ == "__main__":
    success = test_real_estate_screening()
    
    if success:
        print("\n🎉 Real estate industry test completed!")
    else:
        print("\n❌ The real estate industry failed the test!")

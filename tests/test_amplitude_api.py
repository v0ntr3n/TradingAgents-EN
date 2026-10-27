"""Test amplitude API"""
import requests
import json

# API Configuration
BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "admin123"

def login():
    """Log in to get token"""
    url = f"{BASE_URL}/api/auth/login"
    data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    response = requests.post(url, json=data)
    if response.status_code == 200:
        result = response.json()
        return result.get("data", {}).get("access_token")
    else:
        print(f"❌ Login failed: {response.status_code}")
        print(response.text)
        return None

def get_quote(token, code):
    """Get stock quotes"""
    url = f"{BASE_URL}/api/stocks/{code}/quote"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get quotes: {response.status_code}")
        print(response.text)
        return None

def main():
    print("=" * 60)
    print("🧪 Test amplitude API")
    print("=" * 60)
    
    # 1. Login
    print("\n1️⃣ Login...")
    token = login()
    if not token:
        return
    print(f"✅ Login successful")
    
    # 2. Get 300750 Quotes
    print("\n2️⃣ Get 300750 Quotes...")
    result = get_quote(token, "300750")
    if not result:
        return
    
    print(f"✅ get success")
    print(f"\n📊 Market data:")
    data = result.get("data", {})
    
    # Print key fields
    fields = [
        ("code", "code"),
        ("Name", "name"),
        ("price", "price"),
        ("Increase or decrease", "change_percent"),
        ("Open", "open"),
        ("highest", "high"),
        ("lowest", "low"),
        ("Collected yesterday", "prev_close"),
        ("Volume", "volume"),
        ("Turnover", "amount"),
        ("turnover rate", "turnover_rate"),
        ("Amplitude", "amplitude"),  # 🔥 New
        ("Turnover date", "turnover_rate_date"),
        ("amplitude date", "amplitude_date"),  # 🔥 New
    ]
    
    for label, key in fields:
        value = data.get(key)
        if value is not None:
            if key in ["change_percent", "turnover_rate", "amplitude"]:
                print(f"  {label}: {value}%")
            elif key == "volume":
                print(f"  {label}: {value:,.0f}")
            elif key == "amount":
                print(f"  {label}: {value:,.2f}")
            else:
                print(f"  {label}: {value}")
        else:
            print(f"  {label}: -")
    
    # Verify amplitude calculation
    print("\n3️⃣ Verify amplitude calculation...")
    high = data.get("high")
    low = data.get("low")
    prev_close = data.get("prev_close")
    amplitude = data.get("amplitude")
    
    if high and low and prev_close:
        expected_amplitude = round((high - low) / prev_close * 100, 2)
        print(f"  high: {high}")
        print(f"  low: {low}")
        print(f"  Collected yesterday: {prev_close}")
        print(f"  expected amplitude: {expected_amplitude}%")
        print(f"  actual amplitude: {amplitude}%")
        
        if abs(expected_amplitude - amplitude) < 0.01:
            print(f"  ✅ The amplitude calculation is correct!")
        else:
            print(f"  ❌ Amplitude calculation error!")
    else:
        print(f"  ⚠️ Data is incomplete and cannot be verified")

if __name__ == "__main__":
    main()


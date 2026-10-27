"""Test query"""
from pymongo import MongoClient

# connect MongoDB
mongo_uri = "mongodb://admin:tradingagents123@localhost:27017/"
client = MongoClient(mongo_uri)

db = client["tradingagents"]

print("=" * 60)
print("🔍 Test query market_quotes")
print("=" * 60)

# Test different query conditions
queries = [
    {"code": "300750"},
    {"symbol": "300750"},
    {"code": "300750", "symbol": "300750"},
]

for query in queries:
    print(f"\n Query conditions: {query}")
    result = db.market_quotes.find_one(query, {"_id": 0})
    if result:
        print(f"  ✅ find data")
        print(f"  - volume: {result.get('volume')}")
        print(f"  - amount: {result.get('amount')}")
        print(f"  - volume_ratio: {result.get('volume_ratio')}")
    else:
        print(f"  ❌ No data found")

client.close()


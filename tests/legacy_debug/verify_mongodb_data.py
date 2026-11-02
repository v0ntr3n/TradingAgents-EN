#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB Data validation script
Verify whether the basic information of A-share stocks is correctly synchronized to MongoDB
"""

import os
from typing import Dict, Any, List
from datetime import datetime

try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("❌ pymongo Not installed, please run: pip install pymongo")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv Not installed, system environment variables will be used")

def get_mongodb_config() -> Dict[str, Any]:
    """Get MongoDB configuration"""
    return {
        'host': os.getenv('MONGODB_HOST', 'localhost'),
        'port': int(os.getenv('MONGODB_PORT', 27018)),
        'username': os.getenv('MONGODB_USERNAME'),
        'password': os.getenv('MONGODB_PASSWORD'),
        'database': os.getenv('MONGODB_DATABASE', 'tradingagents'),
        'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin')
    }

def connect_mongodb():
    """connect MongoDB"""
    if not MONGODB_AVAILABLE:
        return None, None
    
    config = get_mongodb_config()
    
    try:
        # Build connection string
        if config.get('username') and config.get('password'):
            connection_string = f"mongodb://{config['username']}:{config['password']}@{config['host']}:{config['port']}/{config['auth_source']}"
        else:
            connection_string = f"mongodb://{config['host']}:{config['port']}/"
        
        # Create client
        client = MongoClient(
            connection_string,
            serverSelectionTimeoutMS=5000
        )
        
        # test connection
        client.admin.command('ping')
        
        # Select database
        db = client[config['database']]
        
        print(f"✅ MongoDB Connection successful: {config['host']}:{config['port']}")
        return client, db
        
    except Exception as e:
        print(f"❌ MongoDB Connection failed: {e}")
        return None, None

def verify_stock_data(db):
    """Verify stock data"""
    if db is None:
        return
    
    collection = db['stock_basic_info']
    
    print("\n" + "="*60)
    print("📊 MongoDB A-share basic information verification in")
    print("="*60)
    
    # 1. Total number of records
    total_count = collection.count_documents({})
    print(f"📈 Total number of records: {total_count:,}")
    
    # 2. Statistics by market
    print("\n🏢 Market distribution:")
    market_pipeline = [
        {'$group': {
            '_id': '$sse',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}}
    ]
    
    for market in collection.aggregate(market_pipeline):
        market_name = 'Shanghai' if market['_id'] == 'sh' else 'Shenzhen'
        print(f"  {market_name}market ({market['_id']}): {market['count']:,} Article")
    
    # 3. Statistics by category
    print("\n📊 Classification distribution:")
    category_pipeline = [
        {'$group': {
            '_id': '$sec',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}}
    ]
    
    for category in collection.aggregate(category_pipeline):
        category_name = {
            'stock_cn': 'stocks',
            'etf_cn': 'ETF fund',
            'index_cn': 'Index',
            'bond_cn': 'bonds'
        }.get(category['_id'], category['_id'])
        print(f"  {category_name}: {category['count']:,} Article")
    
    # 4. data sample
    print("\n📋 data sample (Top 10):")
    samples = collection.find({}).limit(10)
    
    for i, stock in enumerate(samples, 1):
        market_name = 'Shanghai' if stock['sse'] == 'sh' else 'Shenzhen'
        print(f"  {i:2d}. {stock['code']} - {stock['name']} ({market_name})")
    
    # 5. last updated time
    latest = collection.find_one({}, sort=[('updated_at', -1)])
    if latest and 'updated_at' in latest:
        print(f"\n🕒 last updated time: {latest['updated_at']}")
    
    # 6. Data integrity check
    print("\n🔍 Data integrity check:")
    
    # Check required fields
    required_fields = ['code', 'name', 'sse']
    for field in required_fields:
        missing_count = collection.count_documents({field: {'$exists': False}})
        null_count = collection.count_documents({field: None})
        empty_count = collection.count_documents({field: ''})
        
        if missing_count + null_count + empty_count == 0:
            print(f"  ✅ {field}: complete")
        else:
            print(f"  ⚠️ {field}: Missing{missing_count}, null value{null_count}, empty string{empty_count}")
    
    # 7. Query example
    print("\n🔍 Query example:")
    
    # Find Ping An related stocks
    ping_an_stocks = list(collection.find(
        {'name': {'$regex': 'Peace', '$options': 'i'}}
    ).limit(5))
    
    if ping_an_stocks:
        print("  Ping An related stocks:")
        for stock in ping_an_stocks:
            market_name = 'Shanghai' if stock['sse'] == 'sh' else 'Shenzhen'
            print(f"    {stock['code']} - {stock['name']} ({market_name})")
    
    # Find ETF
    etf_count = collection.count_documents({'sec': 'etf_cn'})
    print(f"  ETF Total number of funds: {etf_count:,}")
    
    # Find index
    index_count = collection.count_documents({'sec': 'index_cn'})
    print(f"  Total number of indices: {index_count:,}")

def main():
    """main function"""
    print("🔍 Verifying basic A-share information in MongoDB...")
    
    # connect MongoDB
    client, db = connect_mongodb()
    
    if client is None or db is None:
        print("❌ Unable to connect to MongoDB, authentication failed")
        return
    
    try:
        # Validate data
        verify_stock_data(db)
        
        print("\n✅ Data verification completed")
        
    except Exception as e:
        print(f"❌ An error occurred during verification: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # close connection
        if client:
            client.close()
            print("🔒 MongoDB connection closed")

if __name__ == "__main__":
    main()
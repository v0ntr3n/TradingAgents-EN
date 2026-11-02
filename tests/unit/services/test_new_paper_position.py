"""Test whether the name field is saved correctly when creating a new simulated transaction"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def test_new_position():
    """Test the name field when creating a new position"""
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_uri)
    db = client['tradingagents']
    
    print('=== Test the name field when creating a new position ===\n')
    
    # test user ID
    test_user_id = "test_user_001"
    
    # Clean old data
    await db['paper_positions'].delete_many({'user_id': test_user_id})
    await db['paper_accounts'].delete_many({'user_id': test_user_id})
    
    print('✅ Old test data cleaned\n')
    
    # Create account
    now_iso = datetime.utcnow().isoformat()
    account = {
        'user_id': test_user_id,
        'cash': {
            'CNY': 1000000.0,
            'HKD': 1000000.0,
            'USD': 100000.0
        },
        'realized_pnl': {
            'CNY': 0.0,
            'HKD': 0.0,
            'USD': 0.0
        },
        'created_at': now_iso,
        'updated_at': now_iso
    }
    await db['paper_accounts'].insert_one(account)
    print('✅ Test account created\n')
    
    # Test cases: A shares, Hong Kong stocks, US stocks
    test_cases = [
        {'code': '300750', 'market': 'CN', 'name': 'Ningde era'},
        {'code': '00700', 'market': 'HK', 'name': 'Tencent Holdings'},
        {'code': 'AAPL', 'market': 'US', 'name': 'apple inc.'},
    ]
    
    print('=== Simulate a new position ===\n')
    
    for test_case in test_cases:
        code = test_case['code']
        market = test_case['market']
        expected_name = test_case['name']
        
        # Create a position (simulate order logic)
        position = {
            'user_id': test_user_id,
            'code': code,
            'name': expected_name,  # This is a new field
            'market': market,
            'currency': {'CN': 'CNY', 'HK': 'HKD', 'US': 'USD'}[market],
            'quantity': 100,
            'available_qty': 100 if market != 'CN' else 0,
            'frozen_qty': 0,
            'avg_cost': 100.0,
            'updated_at': now_iso
        }
        
        result = await db['paper_positions'].insert_one(position)
        print(f'✅ Create a position: {code} ({market})')
        print(f'   Name: {expected_name}')
        print(f'   ID: {result.inserted_id}\n')
    
    # Validate data
    print('=== Verify saved data ===\n')
    positions = await db['paper_positions'].find({'user_id': test_user_id}).to_list(None)
    
    for pos in positions:
        code = pos.get('code')
        name = pos.get('name', '(no name)')
        market = pos.get('market')
        print(f'code: {code:6} | Name: {name:20} | market: {market}')
    
    # statistics
    total = len(positions)
    with_name = sum(1 for p in positions if p.get('name'))
    
    print(f'\n=== statistics ===')
    print(f'Total number of records: {total}')
    print(f'has a name: {with_name}')
    print(f'name completeness: {(with_name/total*100):.1f}%' if total > 0 else 'name completeness: 0%')
    
    # Note: The data is not cleaned and remains in the database for verification.
    print('\n✅ The test data has been saved to the database and the user ID: test_user_001')
    print('   The paper_positions collection can be viewed in MongoDB')

    client.close()

if __name__ == "__main__":
    asyncio.run(test_new_position())


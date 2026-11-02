"""Test the name field in paper_positions"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def test_paper_positions_name():
    """Test the name field in paper_positions"""
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_uri)
    db = client['tradingagents']
    
    print('=== Test the name field in paper_positions ===\n')
    
    # Query several paper_positions records
    positions = await db['paper_positions'].find({}).limit(10).to_list(None)
    
    print(f'found {len(positions)} paper_positions records\n')
    
    if positions:
        print('=== Position example ===')
        for pos in positions:
            code = pos.get('code')
            name = pos.get('name', '(no name)')
            market = pos.get('market', 'CN')
            qty = pos.get('quantity', 0)
            print(f'code: {code:6} | Name: {name:20} | market: {market} | Quantity: {qty}')
    else:
        print('No position data')
    
    # Statistics of named and unnamed records
    total = await db['paper_positions'].count_documents({})
    with_name = await db['paper_positions'].count_documents({
        'name': {'$exists': True, '$ne': None, '$ne': ''}
    })
    without_name = total - with_name
    
    print(f'\n=== Statistics ===')
    print(f'Total number of records: {total}')
    print(f'has a name: {with_name}')
    print(f'no name: {without_name}')
    
    if total > 0:
        percentage = (with_name / total) * 100
        print(f'name completeness: {percentage:.1f}%')
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_paper_positions_name())


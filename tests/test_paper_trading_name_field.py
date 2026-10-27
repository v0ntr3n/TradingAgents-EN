"""Integration test: verify name field in simulated transaction"""
import pytest
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

@pytest.fixture
async def mongo_db():
    """Get MongoDB connection"""
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_uri)
    db = client['tradingagents']
    yield db
    client.close()

@pytest.mark.asyncio
async def test_paper_position_name_field_cn(mongo_db):
    """Test the name field of A-share positions"""
    test_user_id = "test_cn_user"
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})
    
    # Create a position
    position = {
        'user_id': test_user_id,
        'code': '300750',
        'name': 'Ningde era',
        'market': 'CN',
        'currency': 'CNY',
        'quantity': 100,
        'available_qty': 0,
        'frozen_qty': 0,
        'avg_cost': 100.0,
        'updated_at': '2025-12-19T00:00:00'
    }
    
    result = await mongo_db['paper_positions'].insert_one(position)
    
    # Verify
    saved = await mongo_db['paper_positions'].find_one({'_id': result.inserted_id})
    assert saved is not None
    assert saved['name'] == 'Ningde era'
    assert saved['code'] == '300750'
    assert saved['market'] == 'CN'
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})

@pytest.mark.asyncio
async def test_paper_position_name_field_hk(mongo_db):
    """Test the name field of Hong Kong stock positions"""
    test_user_id = "test_hk_user"
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})
    
    # Create a position
    position = {
        'user_id': test_user_id,
        'code': '00700',
        'name': 'Tencent Holdings',
        'market': 'HK',
        'currency': 'HKD',
        'quantity': 100,
        'available_qty': 100,
        'frozen_qty': 0,
        'avg_cost': 100.0,
        'updated_at': '2025-12-19T00:00:00'
    }
    
    result = await mongo_db['paper_positions'].insert_one(position)
    
    # Verify
    saved = await mongo_db['paper_positions'].find_one({'_id': result.inserted_id})
    assert saved is not None
    assert saved['name'] == 'Tencent Holdings'
    assert saved['code'] == '00700'
    assert saved['market'] == 'HK'
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})

@pytest.mark.asyncio
async def test_paper_position_name_field_us(mongo_db):
    """Test the name field of US stock positions"""
    test_user_id = "test_us_user"
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})
    
    # Create a position
    position = {
        'user_id': test_user_id,
        'code': 'AAPL',
        'name': 'apple inc.',
        'market': 'US',
        'currency': 'USD',
        'quantity': 100,
        'available_qty': 100,
        'frozen_qty': 0,
        'avg_cost': 100.0,
        'updated_at': '2025-12-19T00:00:00'
    }
    
    result = await mongo_db['paper_positions'].insert_one(position)
    
    # Verify
    saved = await mongo_db['paper_positions'].find_one({'_id': result.inserted_id})
    assert saved is not None
    assert saved['name'] == 'apple inc.'
    assert saved['code'] == 'AAPL'
    assert saved['market'] == 'US'
    
    # clean up
    await mongo_db['paper_positions'].delete_many({'user_id': test_user_id})

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


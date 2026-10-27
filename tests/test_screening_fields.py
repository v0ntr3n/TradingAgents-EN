#!/usr/bin/env python3
"""
Test filter field mapping
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_screening_fields():
    """Test filter field mapping"""
    print("🧪 Test filter field mapping...")
    
    try:
        # Import services
        from app.core.database import init_db
        from app.services.database_screening_service import get_database_screening_service
        from app.models.screening import ScreeningCondition, OperatorType
        
        # Initialize database
        await init_db()
        print("✅ Database connection successful")
        
        # Get service instance
        service = get_database_screening_service()
        
        # Test filters
        conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.GTE,
                value=100  # Total market capitalization >= 100 billion
            )
        ]
        
        # Perform filtering
        results, total = await service.screen_stocks(
            conditions=conditions,
            limit=3,
            order_by=[{"field": "total_mv", "direction": "desc"}]
        )
        
        print(f"✅ Screening completed: total={total}, Return={len(results)}")
        
        # Check field mapping
        if results:
            print("\n📋 Field mapping check:")
            first_result = results[0]
            
            # Check the fields expected by the front end
            expected_fields = [
                "code", "name", "industry", 
                "market_cap", "pe_ratio", "pb_ratio",
                "price", "change_percent"
            ]
            
            print("Fields expected by the front end:")
            for field in expected_fields:
                value = first_result.get(field)
                status = "✅" if field in first_result else "❌"
                print(f"  {status} {field}: {value}")
            
            print(f"\n📄 Full result example:")
            print(f"  Stock code: {first_result.get('code')}")
            print(f"  Stock name: {first_result.get('name')}")
            print(f"  Industry: {first_result.get('industry')}")
            print(f"  Market value: {first_result.get('market_cap')}billion")
            print(f"  P/E ratio: {first_result.get('pe_ratio')}")
            print(f"  price to book ratio: {first_result.get('pb_ratio')}")
            print(f"  current price: {first_result.get('price')} (The basic filter is None)")
            print(f"  Increase or decrease: {first_result.get('change_percent')} (The basic filter is None)")
        
        print("\n🎉 Field mapping test completed!")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_screening_fields())

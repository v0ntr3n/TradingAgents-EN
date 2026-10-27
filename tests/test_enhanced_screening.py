#!/usr/bin/env python3
"""
Test enhanced stock screening capabilities
"""

import asyncio
import sys
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_enhanced_screening():
    """Test enhanced filtering"""
    print("🧪 Test enhanced stock screening capabilities...")
    
    try:
        # Import services
        from app.core.database import init_db
        from app.services.enhanced_screening_service import get_enhanced_screening_service
        from app.models.screening import ScreeningCondition, OperatorType
        
        # Initialize database
        await init_db()
        print("✅ Database connection successful")
        
        # Get service instance
        service = get_enhanced_screening_service()
        
        # test 1: Get supported field information
        print("\n📋 test 1: Get supported field information")
        fields = await service.get_all_supported_fields()
        print(f"✅ Number of fields supported: {len(fields)}")
        for field in fields[:5]:  # Show first 5 fields
            print(f"  - {field['name']}: {field['display_name']} ({field['field_type']})")
        
        # test 2: Basic information screening (database optimization)
        print("\n🔍 test 2: Basic information screening (database optimization)")
        conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.GTE,
                value=100  # Total market capitalization >= 100 billion
            ),
            ScreeningCondition(
                field="pe",
                operator=OperatorType.BETWEEN,
                value=[5, 30]  # The P/E ratio is between 5-30
            ),
            ScreeningCondition(
                field="industry",
                operator=OperatorType.CONTAINS,
                value="bank"  # Industry includes"bank"
            )
        ]
        
        start_time = time.time()
        result = await service.screen_stocks(
            conditions=conditions,
            limit=10,
            use_database_optimization=True
        )
        end_time = time.time()
        
        print(f"✅ Screening completed:")
        print(f"  - total quantity: {result['total']}")
        print(f"  - Return quantity: {len(result['items'])}")
        print(f"  - Time consuming: {result.get('took_ms', 0)}ms")
        print(f"  - Optimization method: {result.get('optimization_used')}")
        print(f"  - data source: {result.get('source')}")
        
        # Show first 3 results
        if result['items']:
            print("  - Top 3 results:")
            for i, item in enumerate(result['items'][:3], 1):
                print(f"    {i}. {item.get('code')} {item.get('name')} "
                      f"Market value:{item.get('total_mv')}billion PE:{item.get('pe')} "
                      f"Industry:{item.get('industry')}")
        
        # test 3: Validate filters
        print("\n✅ test 3: Validate filters")
        validation = await service.validate_conditions(conditions)
        print(f"  - Verification results: {'Pass' if validation['valid'] else 'failed'}")
        if validation['errors']:
            print(f"  - Error: {validation['errors']}")
        if validation['warnings']:
            print(f"  - warning: {validation['warnings']}")
        
        # test 4: Field statistics
        print("\n📊 test 4: Field statistics")
        field_info = await service.get_field_info("total_mv")
        if field_info:
            stats = field_info.get('statistics', {})
            print(f"  - Total market capitalization statistics:")
            print(f"    minimum value: {stats.get('min')}billion")
            print(f"    maximum value: {stats.get('max')}billion")
            print(f"    average: {stats.get('avg')}billion")
            print(f"    Data volume: {stats.get('count')}Article")
        
        # test 5: Performance comparison (database vs traditional)
        print("\n⚡ test 5: Performance comparison")
        
        # Simple conditions (suitable for database optimization)
        simple_conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.GTE,
                value=50
            )
        ]
        
        # Database optimization methods
        start_time = time.time()
        db_result = await service.screen_stocks(
            conditions=simple_conditions,
            limit=20,
            use_database_optimization=True
        )
        db_time = time.time() - start_time
        
        # traditional way
        start_time = time.time()
        traditional_result = await service.screen_stocks(
            conditions=simple_conditions,
            limit=20,
            use_database_optimization=False
        )
        traditional_time = time.time() - start_time
        
        print(f"  - Database optimization: {db_result.get('took_ms', 0)}ms, Number of results: {len(db_result['items'])}")
        print(f"  - traditional way: {traditional_result.get('took_ms', 0)}ms, Number of results: {len(traditional_result['items'])}")
        print(f"  - Performance improvements: {traditional_time/db_time:.1f}x" if db_time > 0 else "  - Unable to calculate performance gain")
        
        # test 6: Complex filter conditions
        print("\n🔧 test 6: Complex filter conditions")
        complex_conditions = [
            ScreeningCondition(
                field="total_mv",
                operator=OperatorType.BETWEEN,
                value=[100, 1000]  # Market value 10-100 billion
            ),
            ScreeningCondition(
                field="pe",
                operator=OperatorType.LTE,
                value=20  # PE <= 20
            ),
            ScreeningCondition(
                field="pb",
                operator=OperatorType.LTE,
                value=3  # PB <= 3
            ),
            ScreeningCondition(
                field="area",
                operator=OperatorType.IN,
                value=["Beijing", "Shanghai", "Shenzhen"]  # Region in first-tier cities
            )
        ]
        
        complex_result = await service.screen_stocks(
            conditions=complex_conditions,
            limit=15,
            order_by=[{"field": "total_mv", "direction": "desc"}]
        )
        
        print(f"✅ Complex screening completed:")
        print(f"  - total quantity: {complex_result['total']}")
        print(f"  - Return quantity: {len(complex_result['items'])}")
        print(f"  - Time consuming: {complex_result.get('took_ms', 0)}ms")
        print(f"  - Optimization method: {complex_result.get('optimization_used')}")
        
        if complex_result['items']:
            print("  - Top 5 results:")
            for i, item in enumerate(complex_result['items'][:5], 1):
                print(f"    {i}. {item.get('code')} {item.get('name')} "
                      f"Market value:{item.get('total_mv')}billion PE:{item.get('pe')} "
                      f"PB:{item.get('pb')} area:{item.get('area')}")
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_enhanced_screening())

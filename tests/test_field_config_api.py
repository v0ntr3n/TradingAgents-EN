#!/usr/bin/env python3
"""
Test filter field configuration API
"""

import asyncio
import sys
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_field_config_api():
    """Test filter field configuration API"""
    print("🧪 Test filter field configuration API...")
    
    try:
        # Import necessary modules
        from app.core.database import init_db
        from app.models.screening import BASIC_FIELDS_INFO
        
        # Initialize database
        await init_db()
        print("✅ Database connection successful")
        
        # Test field configuration
        print("\n📋 Available filter fields:")
        
        # Field classification
        categories = {
            "basic": ["code", "name", "industry", "area", "market"],
            "market_value": ["total_mv", "circ_mv"],
            "financial": ["pe", "pb", "pe_ttm", "pb_mrq"],
            "trading": ["turnover_rate", "volume_ratio"],
            "price": ["close", "pct_chg", "amount"],
            "technical": ["ma20", "rsi14", "kdj_k", "kdj_d", "kdj_j", "dif", "dea", "macd_hist"]
        }
        
        for category, fields in categories.items():
            print(f"\n🏷️ {category.upper()}:")
            for field in fields:
                if field in BASIC_FIELDS_INFO:
                    field_info = BASIC_FIELDS_INFO[field]
                    print(f"  ✅ {field}: {field_info.display_name} ({field_info.data_type})")
                    print(f"     Description: {field_info.description}")
                    print(f"     Support operations: {field_info.supported_operators}")
                else:
                    print(f"  ❌ {field}: Field information is missing")
        
        # Test API response format
        response_data = {
            "fields": {name: {
                "name": info.name,
                "display_name": info.display_name,
                "field_type": info.field_type.value,
                "data_type": info.data_type,
                "description": info.description,
                "supported_operators": [op.value for op in info.supported_operators]
            } for name, info in BASIC_FIELDS_INFO.items()},
            "categories": categories
        }
        
        print(f"\n📄 API Response example:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False)[:500] + "...")
        
        print("\n🎉 Field configuration API testing completed!")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_field_config_api())

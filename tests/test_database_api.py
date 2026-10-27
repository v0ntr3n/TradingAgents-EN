#!/usr/bin/env python3
"""
Test database management API
"""

import asyncio
import sys
import os
sys.path.append('.')

from app.services.database_service import DatabaseService

async def test_database_service():
    """Test database service"""
    print('🧪 Test database management services')
    print('=' * 50)
    
    try:
        service = DatabaseService()
        
        # Test to get database status
        print('📊 Test to get database status...')
        status = await service.get_database_status()
        print(f'✅ MongoDB connect: {status["mongodb"]["connected"]}')
        print(f'✅ Redis connect: {status["redis"]["connected"]}')
        
        # Test to obtain database statistics
        print('\n📈 Test to obtain database statistics...')
        stats = await service.get_database_stats()
        print(f'📋 Collection quantity: {stats["total_collections"]}')
        print(f'📄 Number of documents: {stats["total_documents"]}')
        print(f'💾 Storage size: {stats["total_size"]} bytes')
        
        # test connection test
        print('\n🔗 Test database connection...')
        test_results = await service.test_connections()
        print(f'✅ MongoDB test: {test_results["mongodb"]["success"]}')
        print(f'✅ Redis test: {test_results["redis"]["success"]}')
        print(f'✅ overall test: {test_results["overall"]}')
        
        # Test backup list
        print('\n📋 Test to get backup list...')
        backups = await service.list_backups()
        print(f'📦 Number of backups: {len(backups)}')
        
        print('\n🎉 All tests passed!')
        
    except Exception as e:
        print(f'❌ test failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_database_service())

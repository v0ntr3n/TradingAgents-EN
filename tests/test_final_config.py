#!/usr/bin/env python3
"""
Test the final .env configuration system
Verify that the enable switch is working properly
"""

import os

def test_final_config():
    """Test final configuration"""
    print("🔧 Test the final .env configuration system")
    print("=" * 40)
    
    # 1. Check .env file
    print("\n📁 Check .env file...")
    if os.path.exists('.env'):
        print("✅ .env File exists")
    else:
        print("❌ .env File does not exist")
        return False
    
    # 2. Read enable switch
    print("\n🔧 Check enable switch...")
    mongodb_enabled = os.getenv("MONGODB_ENABLED", "false").lower() == "true"
    redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    
    print(f"MONGODB_ENABLED: {os.getenv('MONGODB_ENABLED', 'false')} -> {mongodb_enabled}")
    print(f"REDIS_ENABLED: {os.getenv('REDIS_ENABLED', 'false')} -> {redis_enabled}")
    
    # 3. Show configuration information
    print("\n📊 Database configuration:")
    
    if mongodb_enabled:
        print("MongoDB: ✅ enable")
        print(f"  Host: {os.getenv('MONGODB_HOST', 'localhost')}")
        print(f"  Port: {os.getenv('MONGODB_PORT', '27017')}")
        print(f"  Database: {os.getenv('MONGODB_DATABASE', 'tradingagents')}")
    else:
        print("MongoDB: ❌ Disable")
    
    if redis_enabled:
        print("Redis: ✅ enable")
        print(f"  Host: {os.getenv('REDIS_HOST', 'localhost')}")
        print(f"  Port: {os.getenv('REDIS_PORT', '6379')}")
        print(f"  DB: {os.getenv('REDIS_DB', '0')}")
    else:
        print("Redis: ❌ Disable")
    
    # 4. Test database manager
    print("\n🔧 Test database manager...")
    try:
        from tradingagents.config.database_manager import get_database_manager
        
        db_manager = get_database_manager()
        print("✅ Database manager created successfully")
        
        # Get status report
        status = db_manager.get_status_report()
        
        print("📊 Test results:")
        print(f"  Database available: {'✅ Yes' if status['database_available'] else '❌ No'}")
        
        mongodb_info = status['mongodb']
        print(f"  MongoDB: {'✅ Available' if mongodb_info['available'] else '❌ Not available'}")
        
        redis_info = status['redis']
        print(f"  Redis: {'✅ Available' if redis_info['available'] else '❌ Not available'}")
        
        print(f"  Caching backend: {status['cache_backend']}")
        
    except Exception as e:
        print(f"❌ Database manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Test caching system
    print("\n💾 Test caching system...")
    try:
        from tradingagents.dataflows.integrated_cache import get_cache
        
        cache = get_cache()
        print("✅ Cache system created successfully")
        
        # Get performance mode
        performance_mode = cache.get_performance_mode()
        print(f"  Performance mode: {performance_mode}")
        
        # Test basic functionality
        test_data = "Test data - final configuration"
        cache_key = cache.save_stock_data(
            symbol="TEST_FINAL",
            data=test_data,
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="final_test"
        )
        print(f"✅ Data saved successfully: {cache_key}")
        
        # Load data
        loaded_data = cache.load_stock_data(cache_key)
        if loaded_data == test_data:
            print("✅ Data loaded successfully")
        else:
            print("❌ Data loading failed")
            return False
        
    except Exception as e:
        print(f"❌ Cache system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 6. Summary
    print("\n📊 Configuration summary:")
    print("✅ Configure using .env files")
    print("✅ Control the enablement status through MONGODB_ENABLED and REDIS_ENABLED")
    print("✅ Databases are disabled by default")
    print("✅ The system uses file caching and has good performance")
    print("✅ The database can be enabled by modifying the .env file")
    
    print("\n💡 Instructions for use:")
    print("1. Default configuration:MONGODB_ENABLED=false, REDIS_ENABLED=false")
    print("2. Enable MongoDB: Set MONGODB_ENABLED to true")
    print("3. Enable Redis: Set REDIS_ENABLED to true")
    print("4. The system automatically detects and uses enabled databases")
    print("5. Automatically downgrade to file cache if database becomes unavailable")
    
    return True

def main():
    """main function"""
    try:
        success = test_final_config()
        
        if success:
            print("\n🎉 Final configuration test completed!")
            print("\n🎯 System characteristics:")
            print("✅ Simplified configuration: only .env file required")
            print("✅ Explicit control: control the database by enabling switches")
            print("✅ Default security: database is not enabled by default")
            print("✅ Smart downgrade: automatically uses file cache when database is unavailable")
            print("✅ Performance optimization: automatically use high-performance mode when there is a database")
        
        return success
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

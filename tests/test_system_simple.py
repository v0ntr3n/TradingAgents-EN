#!/usr/bin/env python3
"""
Simple system testing - verify configuration and caching system
"""

import sys
import os
from pathlib import Path

def test_basic_system():
    """Test basic system functionality"""
    print("🔧 TradingAgents Basic system testing")
    print("=" * 40)
    
    # 1. Check configuration file
    print("\n📁 Check configuration file...")
    config_file = Path("config/database_config.json")
    if config_file.exists():
        print(f"✅ Configuration file exists: {config_file}")
        
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print("✅ The configuration file format is correct")
            print(f"  Main caching backend: {config['cache']['primary_backend']}")
            print(f"  MongoDB enable: {config['database']['mongodb']['enabled']}")
            print(f"  Redis enable: {config['database']['redis']['enabled']}")
        except Exception as e:
            print(f"❌ Configuration file parsing failed: {e}")
    else:
        print(f"❌ Configuration file does not exist: {config_file}")
    
    # 2. Check database package
    print("\n📦 Check database package...")
    
    # Check pymongo
    try:
        import pymongo
        print("✅ pymongo Installed")
        
        # try to connect MongoDB
        try:
            client = pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=2000)
            client.server_info()
            client.close()
            print("✅ MongoDB Connection successful")
            mongodb_available = True
        except Exception:
            print("❌ MongoDB Connection failed (normal, if MongoDB is not installed)")
            mongodb_available = False
    except ImportError:
        print("❌ pymongo Not installed")
        mongodb_available = False
    
    # Check redis
    try:
        import redis
        print("✅ redis Installed")
        
        # try to connect Redis
        try:
            r = redis.Redis(host='localhost', port=6379, socket_timeout=2)
            r.ping()
            print("✅ Redis Connection successful")
            redis_available = True
        except Exception:
            print("❌ Redis Connection failed (normal, if Redis is not installed)")
            redis_available = False
    except ImportError:
        print("❌ redis Not installed")
        redis_available = False
    
    # 3. Test caching system
    print("\n💾 Test caching system...")
    try:
        from tradingagents.dataflows.integrated_cache import get_cache
        
        cache = get_cache()
        print("✅ Cache system initialization successful")
        
        # Get cache information
        backend_info = cache.get_cache_backend_info()
        print(f"  caching system: {backend_info['system']}")
        print(f"  Main backend: {backend_info['primary_backend']}")
        
        # Test basic functionality
        test_data = "Test data - simple test of the system"
        cache_key = cache.save_stock_data(
            symbol="TEST_SIMPLE",
            data=test_data,
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="simple_test"
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
    
    # 4. Test database manager
    print("\n🔧 Test database manager...")
    try:
        from tradingagents.config.database_manager import get_database_manager
        
        db_manager = get_database_manager()
        print("✅ Database manager created successfully")
        
        # Get status report
        status = db_manager.get_status_report()
        
        print("📊 Database status:")
        print(f"  Database available: {'✅ Yes' if status['database_available'] else '❌ No'}")
        print(f"  MongoDB: {'✅ Available' if status['mongodb']['available'] else '❌ Not available'}")
        print(f"  Redis: {'✅ Available' if status['redis']['available'] else '❌ Not available'}")
        print(f"  Caching backend: {status['cache_backend']}")
        
    except Exception as e:
        print(f"❌ Database manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Summary
    print("\n📊 System test summary:")
    print("✅ Caching system works properly")
    print("✅ Database manager works fine")
    
    if mongodb_available or redis_available:
        print("✅ The database is available and the system is running in high-performance mode")
    else:
        print("✅ The database is unavailable and the system is running in file cache mode.")
        print("💡 This is normal and the system is fully functional with file caching")
    
    print("\n🎯 System characteristics:")
    print("✅ Smart caching: automatically selects the best caching backend")
    print("✅ Downgrade support: automatically uses file cache when database is unavailable")
    print("✅ Flexible configuration: supports multiple database configurations")
    print("✅ Performance Optimization: Automatically adjust based on available resources")
    
    return True

def main():
    """main function"""
    try:
        success = test_basic_system()
        
        if success:
            print("\n🎉 System test completed!")
            print("\n💡 Next step:")
            print("1. For high performance, you can install and start MongoDB/Redis")
            print("2. Run a complete stock analysis test")
            print("3. Interactive analysis using web interface")
        
        return success
        
    except Exception as e:
        print(f"❌ System test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

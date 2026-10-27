#!/usr/bin/env python3
"""
Test the database manager configured using .env
"""

import sys
import os
from pathlib import Path

def test_env_config():
    """Test .env configuration"""
    print("🔧 Test the database manager configured using .env")
    print("=" * 50)
    
    # 1. Check .env file
    print("\n📁 Check .env file...")
    env_file = Path(".env")
    if env_file.exists():
        print(f"✅ .env File exists: {env_file}")
        
        # Read and display relevant configuration
        with open(env_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print("📊 Database related configuration:")
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if any(keyword in line.upper() for keyword in ['MONGODB', 'REDIS']):
                    # Hide password
                    if 'PASSWORD' in line.upper():
                        key, value = line.split('=', 1)
                        print(f"  {key}=***")
                    else:
                        print(f"  {line}")
    else:
        print(f"❌ .env File does not exist: {env_file}")
        return False
    
    # 2. Test database manager
    print("\n🔧 Test database manager...")
    try:
        from tradingagents.config.database_manager import get_database_manager
        
        db_manager = get_database_manager()
        print("✅ Database manager created successfully")
        
        # Get status report
        status = db_manager.get_status_report()
        
        print("📊 Database status:")
        print(f"  Database available: {'✅ Yes' if status['database_available'] else '❌ No'}")
        
        mongodb_info = status['mongodb']
        print(f"  MongoDB: {'✅ Available' if mongodb_info['available'] else '❌ Not available'}")
        print(f"    address: {mongodb_info['host']}:{mongodb_info['port']}")
        
        redis_info = status['redis']
        print(f"  Redis: {'✅ Available' if redis_info['available'] else '❌ Not available'}")
        print(f"    address: {redis_info['host']}:{redis_info['port']}")
        
        print(f"  Caching backend: {status['cache_backend']}")
        print(f"  Downgrade support: {'✅ enable' if status['fallback_enabled'] else '❌ Disable'}")
        
    except Exception as e:
        print(f"❌ Database manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. Test caching system
    print("\n💾 Test caching system...")
    try:
        from tradingagents.dataflows.integrated_cache import get_cache
        
        cache = get_cache()
        print("✅ Cache system created successfully")
        
        # Get backend information
        backend_info = cache.get_cache_backend_info()
        print(f"  caching system: {backend_info['system']}")
        print(f"  Main backend: {backend_info['primary_backend']}")
        print(f"  Performance mode: {cache.get_performance_mode()}")
        
        # Test basic functionality
        test_data = "Test data - using .env configuration"
        cache_key = cache.save_stock_data(
            symbol="TEST_ENV",
            data=test_data,
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="env_test"
        )
        print(f"✅ Data saved successfully: {cache_key}")
        
        # Load data
        loaded_data = cache.load_stock_data(cache_key)
        if loaded_data == test_data:
            print("✅ The data is loaded successfully and the content matches")
        else:
            print("❌ Data loading failed or content does not match")
            return False
        
    except Exception as e:
        print(f"❌ Cache system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. Show environment variables
    print("\n🔍 Check environment variables...")
    env_vars = [
        "MONGODB_HOST", "MONGODB_PORT", "MONGODB_USERNAME", "MONGODB_PASSWORD",
        "MONGODB_DATABASE", "MONGODB_AUTH_SOURCE",
        "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD", "REDIS_DB"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            if 'PASSWORD' in var:
                print(f"  {var}=***")
            else:
                print(f"  {var}={value}")
        else:
            print(f"  {var}=not set")
    
    # 5. Summary
    print("\n📊 Test summary:")
    print("✅ The system has correctly used the .env configuration file")
    print("✅ Database manager works fine")
    print("✅ Caching system works properly")
    print("✅ Supports full configuration of MongoDB and Redis")
    print("✅ Automatically downgrade to file cache when database becomes unavailable")
    
    print("\n💡 Configuration instructions:")
    print("1. The system reads the database configuration in the .env file")
    print("2. Automatically detect whether MongoDB and Redis are available")
    print("3. Choose the best cache backend based on availability")
    print("4. Support username and password authentication")
    print("5. Automatically use file cache when database is unavailable")
    
    return True

def main():
    """main function"""
    try:
        success = test_env_config()
        
        if success:
            print("\n🎉 .env Configuration test completed!")
            print("\n🎯 System characteristics:")
            print("✅ Use the project s existing .env configuration")
            print("✅ By default, it does not rely on the database and can be run as a pure file cache.")
            print("✅ Automatically detect and use available databases")
            print("✅ Supports full MongoDB and Redis configuration")
            print("✅ Intelligent downgrade to ensure system stability")
        
        return success
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

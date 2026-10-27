#!/usr/bin/env python3
"""
Simple .env configuration test
"""

import os

def test_env_reading():
    """Test .env file reading"""
    print("🔧 Test .env configuration reading")
    print("=" * 30)
    
    # Check .env file
    if os.path.exists('.env'):
        print("✅ .env File exists")
    else:
        print("❌ .env File does not exist")
        return False
    
    # Read environment variables
    print("\n📊 Database configuration:")
    
    # MongoDB Configuration
    mongodb_host = os.getenv("MONGODB_HOST", "localhost")
    mongodb_port = os.getenv("MONGODB_PORT", "27017")
    mongodb_username = os.getenv("MONGODB_USERNAME")
    mongodb_password = os.getenv("MONGODB_PASSWORD")
    mongodb_database = os.getenv("MONGODB_DATABASE", "tradingagents")
    
    print(f"MongoDB:")
    print(f"  Host: {mongodb_host}")
    print(f"  Port: {mongodb_port}")
    print(f"  Username: {mongodb_username or 'not set'}")
    print(f"  Password: {'***' if mongodb_password else 'not set'}")
    print(f"  Database: {mongodb_database}")
    
    # Redis Configuration
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_db = os.getenv("REDIS_DB", "0")
    
    print(f"\nRedis:")
    print(f"  Host: {redis_host}")
    print(f"  Port: {redis_port}")
    print(f"  Password: {'***' if redis_password else 'not set'}")
    print(f"  DB: {redis_db}")
    
    # Test database connection
    print("\n🧪 Test database connection...")
    
    # test MongoDB
    mongodb_available = False
    try:
        import pymongo
        client = pymongo.MongoClient(
            host=mongodb_host,
            port=int(mongodb_port),
            username=mongodb_username,
            password=mongodb_password,
            authSource="admin",
            serverSelectionTimeoutMS=2000
        )
        client.server_info()
        client.close()
        mongodb_available = True
        print("✅ MongoDB Connection successful")
    except ImportError:
        print("❌ pymongo Not installed")
    except Exception as e:
        print(f"❌ MongoDB Connection failed: {e}")
    
    # test Redis
    redis_available = False
    try:
        import redis
        r = redis.Redis(
            host=redis_host,
            port=int(redis_port),
            password=redis_password,
            db=int(redis_db),
            socket_timeout=2
        )
        r.ping()
        redis_available = True
        print("✅ Redis Connection successful")
    except ImportError:
        print("❌ redis Not installed")
    except Exception as e:
        print(f"❌ Redis Connection failed: {e}")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"MongoDB: {'✅ Available' if mongodb_available else '❌ Not available'}")
    print(f"Redis: {'✅ Available' if redis_available else '❌ Not available'}")
    
    if mongodb_available or redis_available:
        print("🚀 The database is available and the system will use high performance mode")
    else:
        print("📁 The database is unavailable, the system will use file cache mode")
        print("💡 This is normal and the system can work normally")
    
    return True

if __name__ == "__main__":
    test_env_reading()

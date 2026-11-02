#!/usr/bin/env python3
"""
Redis Quick connection test script
"""

import redis
import time
import sys

def quick_redis_test(host=None, port=None, password=None):
    """Quick Redis connection and performance testing"""
    
    # Get configuration from environment variables
    host = host or os.getenv('REDIS_HOST', 'localhost')
    port = port or int(os.getenv('REDIS_PORT', 6379))
    password = password or os.getenv('REDIS_PASSWORD')
    
    print(f"🔍 Test Redis connection: {host}:{port}")
    
    try:
        # Create a Redis connection
        start_time = time.time()
        r = redis.Redis(
            host=host, 
            port=port, 
            password=password,
            decode_responses=True,
            socket_connect_timeout=5
        )
        
        # test connection
        r.ping()
        connect_time = (time.time() - start_time) * 1000
        print(f"✅ Connection successful! connection time: {connect_time:.2f} ms")
        
        # Test basic operational delays
        print("\n📊 Basic Operation Latency Test:")
        
        # SET Operational test
        start_time = time.time()
        r.set("test_key", "test_value")
        set_time = (time.time() - start_time) * 1000
        print(f"  SET Operation: {set_time:.2f} ms")
        
        # GET Operational test
        start_time = time.time()
        value = r.get("test_key")
        get_time = (time.time() - start_time) * 1000
        print(f"  GET Operation: {get_time:.2f} ms")
        
        # PING Operational test
        ping_times = []
        for i in range(10):
            start_time = time.time()
            r.ping()
            ping_time = (time.time() - start_time) * 1000
            ping_times.append(ping_time)
        
        avg_ping = sum(ping_times) / len(ping_times)
        min_ping = min(ping_times)
        max_ping = max(ping_times)
        
        print(f"  PING Operation (10 average): {avg_ping:.2f} ms")
        print(f"  PING min/max: {min_ping:.2f} / {max_ping:.2f} ms")
        
        # Simple throughput test
        print("\n🚀 Simple throughput test (100 operations):")
        
        start_time = time.time()
        for i in range(100):
            r.set(f"throughput_test_{i}", f"value_{i}")
        set_duration = time.time() - start_time
        set_throughput = 100 / set_duration
        
        start_time = time.time()
        for i in range(100):
            r.get(f"throughput_test_{i}")
        get_duration = time.time() - start_time
        get_throughput = 100 / get_duration
        
        print(f"  SET Throughput: {set_throughput:.2f} operations/second")
        print(f"  GET Throughput: {get_throughput:.2f} operations/second")
        
        # Clean test data
        r.delete("test_key")
        for i in range(100):
            r.delete(f"throughput_test_{i}")
        
        # connection information
        print(f"\n📋 Redis Server information:")
        info = r.info()
        print(f"  Redis version: {info.get('redis_version', 'N/A')}")
        print(f"  operating mode: {info.get('redis_mode', 'N/A')}")
        print(f"  Client connected: {info.get('connected_clients', 'N/A')}")
        print(f"  memory usage: {info.get('used_memory_human', 'N/A')}")
        
        return True
        
    except redis.ConnectionError as e:
        print(f"❌ Redis Connection failed: {e}")
        return False
    except redis.TimeoutError as e:
        print(f"❌ Redis Connection timeout: {e}")
        return False
    except Exception as e:
        print(f"❌ An error occurred during testing: {e}")
        return False

def main():
    """main function"""
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = 'localhost'
    
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    else:
        port = 6379
    
    if len(sys.argv) > 3:
        password = sys.argv[3]
    else:
        password = None
    
    success = quick_redis_test(host, port, password)
    
    if success:
        print("\n✅ Redis Connection test completed!")
    else:
        print("\n❌ Redis Connection test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

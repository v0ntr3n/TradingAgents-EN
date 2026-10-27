#!/usr/bin/env python3
"""
Test MongoDB tool functions
"""

import os
import sys

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.config.mongodb_utils import (
    build_mongodb_connection_string,
    get_mongodb_database_name,
    get_mongodb_config
)


def test_build_connection_string_from_env():
    """Test building connection string from environment variables"""
    print("=" * 70)
    print("test 1: Build connection string from environment variables")
    print("=" * 70)
    
    # Set environment variables
    os.environ['MONGODB_HOST'] = 'localhost'
    os.environ['MONGODB_PORT'] = '27017'
    os.environ['MONGODB_USERNAME'] = 'admin'
    os.environ['MONGODB_PASSWORD'] = 'password123'
    os.environ['MONGODB_DATABASE'] = 'testdb'
    os.environ['MONGODB_AUTH_SOURCE'] = 'admin'
    
    # Clear MONGODB_CONNECTION_STRING (make sure to use concatenation logic)
    if 'MONGODB_CONNECTION_STRING' in os.environ:
        del os.environ['MONGODB_CONNECTION_STRING']
    
    conn_str = build_mongodb_connection_string()
    print(f"connection string: {conn_str}")
    
    expected = "mongodb://admin:password123@localhost:27017/testdb?authSource=admin"
    assert conn_str == expected, f"Expectation: {expected}, actual: {conn_str}"
    print("✅ Test passed")
    print()


def test_build_connection_string_from_env_var():
    """Tests preferentially use the MONGODB_CONNECTION_STRING environment variable"""
    print("=" * 70)
    print("test 2: Prefer using the MONGODB_CONNECTION_STRING environment variable")
    print("=" * 70)
    
    # settings MONGODB_CONNECTION_STRING
    custom_conn_str = "mongodb://custom:password@custom-host:12345/customdb?authSource=admin"
    os.environ['MONGODB_CONNECTION_STRING'] = custom_conn_str
    
    conn_str = build_mongodb_connection_string()
    print(f"connection string: {conn_str}")
    
    assert conn_str == custom_conn_str, f"Expectation: {custom_conn_str}, actual: {conn_str}"
    print("✅ Test passed")
    print()


def test_get_database_name():
    """Test to get database name"""
    print("=" * 70)
    print("test 3: Get database name")
    print("=" * 70)
    
    # Test MONGODB_DATABASE_NAME priority
    os.environ['MONGODB_DATABASE_NAME'] = 'db_from_name'
    os.environ['MONGODB_DATABASE'] = 'db_from_database'
    
    db_name = get_mongodb_database_name()
    print(f"Database name: {db_name}")
    
    assert db_name == 'db_from_name', f"Expectation: db_from_name, actual: {db_name}"
    print("✅ Test passed (MONGODB_DATABASE_NAME Priority)")
    
    # Test MONGODB_DATABASE as an alternative
    del os.environ['MONGODB_DATABASE_NAME']
    db_name = get_mongodb_database_name()
    print(f"Database name (alternative): {db_name}")
    
    assert db_name == 'db_from_database', f"Expectation: db_from_database, actual: {db_name}"
    print("✅ Test passed (MONGODB_DATABASE as an alternative)")
    print()


def test_get_mongodb_config():
    """Test to get complete configuration"""
    print("=" * 70)
    print("test 4: Get the full MongoDB configuration")
    print("=" * 70)
    
    config = get_mongodb_config()
    print(f"Configuration: {config}")
    
    assert 'connection_string' in config
    assert 'database_name' in config
    assert 'auth_source' in config
    print("✅ Test passed")
    print()


if __name__ == '__main__':
    try:
        test_build_connection_string_from_env()
        test_build_connection_string_from_env_var()
        test_get_database_name()
        test_get_mongodb_config()
        
        print("=" * 70)
        print("🎉 All tests passed!")
        print("=" * 70)
    except AssertionError as e:
        print(f"❌ test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


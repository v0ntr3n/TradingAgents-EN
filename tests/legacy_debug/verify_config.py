#!/usr/bin/env python3
"""
Verify the configuration is correct
"""

import os
import sys

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("🔧 Verify .env configuration")
print("=" * 30)

# Check enable switch
mongodb_enabled = os.getenv("MONGODB_ENABLED", "false")
redis_enabled = os.getenv("REDIS_ENABLED", "false")

print(f"MONGODB_ENABLED: {mongodb_enabled}")
print(f"REDIS_ENABLED: {redis_enabled}")

# Uses robust boolean parsing (compatible with Python 3.13+) 
try:
    from tradingagents.config.env_utils import parse_bool_env
    mongodb_bool = parse_bool_env("MONGODB_ENABLED", False)
    redis_bool = parse_bool_env("REDIS_ENABLED", False)
    print("✅ Use robust boolean parsing")
except ImportError:
    # fallback to original method
    mongodb_bool = mongodb_enabled.lower() == "true"
    redis_bool = redis_enabled.lower() == "true"
    print("⚠️ Use traditional boolean parsing")

print(f"MongoDB enable: {mongodb_bool}")
print(f"Redis enable: {redis_bool}")

if not mongodb_bool and not redis_bool:
    print("✅ Default configuration: None of the databases are enabled, the system will use file caching")
else:
    print("⚠️ If the database is enabled, the system will try to connect to the database")

print("\n💡 Configuration instructions:")
print("- MONGODB_ENABLED=false (Default)")
print("- REDIS_ENABLED=false (Default)")
print("- The system uses file caching, no database is required")
print("- If you need to enable the database, modify the corresponding value in the .env file to true")

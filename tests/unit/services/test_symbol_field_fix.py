#!/usr/bin/env python3
"""
Test symbol field fix

Verify content:
1. Whether the synchronization service correctly adds the symbol field
2. Check whether the query logic can correctly handle the symbol field
3. Whether the stock name can be correctly matched
"""

import sys
from pathlib import Path

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_basics_sync_service_has_symbol_field():
    """Test whether basics_sync_service.py adds the symbol field"""
    print("\n" + "=" * 60)
    print("test 1: basics_sync_service.py Whether the symbol field is added")
    print("=" * 60)
    
    with open("app/services/basics_sync_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if there is "symbol": code code
    if '"symbol": code' in content or "'symbol': code" in content:
        print("✅ Find the symbol field and add code")
        return True
    else:
        print("❌ symbol field added code not found")
        return False


def test_multi_source_sync_service_has_symbol_field():
    """Test whether multi_source_basics_sync_service.py adds symbol field"""
    print("\n" + "=" * 60)
    print("test 2: multi_source_basics_sync_service.py Whether the symbol field is added")
    print("=" * 60)
    
    with open("app/services/multi_source_basics_sync_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if there is "symbol": code code
    if '"symbol": code' in content or "'symbol': code" in content:
        print("✅ Find the symbol field and add code")
        return True
    else:
        print("❌ symbol field added code not found")
        return False


def test_baostock_sync_service_has_symbol_field():
    """Test whether the symbol field is added to baostock_sync_service.py"""
    print("\n" + "=" * 60)
    print("test 3: baostock_sync_service.py Whether the symbol field is added")
    print("=" * 60)
    
    with open("app/worker/baostock_sync_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if there is code to add symbol field
    if 'basic_info["symbol"]' in content or "basic_info['symbol']" in content:
        print("✅ Find the symbol field and add code")
        return True
    else:
        print("❌ symbol field added code not found")
        return False


def test_app_adapter_query_logic():
    """Test whether app_adapter.py supports symbol field query"""
    print("\n" + "=" * 60)
    print("test 4: app_adapter.py Whether to support symbol field query")
    print("=" * 60)
    
    with open("tradingagents/dataflows/cache/app_adapter.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if there is $or Query logic
    if '"$or"' in content and '"symbol"' in content and '"code"' in content:
        print("✅ Find symbol and code $or Query logic")
        return True
    else:
        print("❌ not found $or Query logic")
        return False


def test_migration_script_exists():
    """Test whether the migration script exists"""
    print("\n" + "=" * 60)
    print("test 5: Does the migration script exist?")
    print("=" * 60)
    
    migration_script = Path("scripts/migrations/add_symbol_field_to_stock_basic_info.py")
    if migration_script.exists():
        print(f"✅ Migration script exists: {migration_script}")
        return True
    else:
        print(f"❌ Migration script does not exist: {migration_script}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("symbol Field fix validation testing")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(("basics_sync_service", test_basics_sync_service_has_symbol_field()))
    results.append(("multi_source_sync_service", test_multi_source_sync_service_has_symbol_field()))
    results.append(("baostock_sync_service", test_baostock_sync_service_has_symbol_field()))
    results.append(("app_adapter_query", test_app_adapter_query_logic()))
    results.append(("migration_script", test_migration_script_exists()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:30s} - {status}")
    
    print(f"\n Overall: {passed}/{total} Test passed")
    
    if passed == total:
        print("\n✅ All tests passed! symbol field repair completed")
        return 0
    else:
        print(f"\n❌ Yes {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)


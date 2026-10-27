#!/usr/bin/env python3
"""
Clean test data
"""

import sys
import os
from pathlib import Path

# Add project path
sys.path.append(os.path.join(os.path.dirname(__file__), 'web'))

def cleanup_test_files():
    """Clean test files"""
    print("🧹 Clean test files...")
    
    # Clean up the detailed report directory
    project_root = Path(__file__).parent
    test_dir = project_root / "data" / "analysis_results" / "TEST123"
    
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print(f"✅ Test directory deleted: {test_dir}")
    else:
        print(f"⚠️ Test directory does not exist: {test_dir}")

def cleanup_mongodb_test_data():
    """Clean MongoDB test data"""
    print("🗄️ Clean MongoDB test data...")
    
    try:
        from web.utils.mongodb_report_manager import mongodb_report_manager
        
        if not mongodb_report_manager.connected:
            print("❌ MongoDB Not connected")
            return
        
        # Delete test data
        collection = mongodb_report_manager.collection
        result = collection.delete_many({"stock_symbol": "TEST123"})
        
        print(f"✅ Deleted {result.deleted_count} TEST123 related records")
        
        # Delete other test data
        result2 = collection.delete_many({"stock_symbol": "TEST001"})
        print(f"✅ Deleted {result2.deleted_count} TEST001 related records")
        
    except Exception as e:
        print(f"❌ MongoDB Cleanup failed: {e}")

def main():
    """main function"""
    print("🧹 Clean test data")
    print("=" * 30)
    
    cleanup_test_files()
    cleanup_mongodb_test_data()
    
    print("\n🎉 Cleanup completed")

if __name__ == "__main__":
    main()

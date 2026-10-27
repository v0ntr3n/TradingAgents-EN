#!/usr/bin/env python3
"""
Check analysis records in MongoDB
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import MongoDB Report Manager
try:
    from web.utils.mongodb_report_manager import mongodb_report_manager
    print(f"✅ MongoDB Report Manager imported successfully")
except ImportError as e:
    print(f"❌ MongoDB Report Manager import failed: {e}")
    sys.exit(1)

def check_mongodb_connection():
    """Check MongoDB connection status"""
    print(f"\n🔍 Check MongoDB connection status...")
    print(f"connection status: {mongodb_report_manager.connected}")
    
    if not mongodb_report_manager.connected:
        print(f"❌ MongoDB Not connected")
        return False
    
    print(f"✅ MongoDB The connection is normal")
    return True

def check_analysis_records():
    """Check analysis records"""
    print(f"\n📊 Check analysis records...")
    
    try:
        # Get all records
        all_reports = mongodb_report_manager.get_all_reports(limit=50)
        print(f"Total number of records: {len(all_reports)}")
        
        if not all_reports:
            print(f"⚠️ MongoDB There are no analysis records in")
            return
        
        # Show recent records
        print(f"\n📋 Recent analysis records:")
        for i, report in enumerate(all_reports[:5]):
            print(f"\n record {i+1}:")
            print(f"  analysis ID: {report.get('analysis_id', 'N/A')}")
            print(f"  Stock code: {report.get('stock_symbol', 'N/A')}")
            print(f"  Analysis date: {report.get('analysis_date', 'N/A')}")
            print(f"  Status: {report.get('status', 'N/A')}")
            print(f"  analyst: {report.get('analysts', [])}")
            print(f"  Research depth: {report.get('research_depth', 'N/A')}")
            
            # Check report content
            reports = report.get('reports', {})
            print(f"  Number of reporting modules: {len(reports)}")
            
            if reports:
                print(f"  reporting module:")
                for module_name, content in reports.items():
                    content_length = len(content) if isinstance(content, str) else 0
                    print(f"    - {module_name}: {content_length} character")
                    
                    # Check if the content is empty or just a placeholder
                    if content_length == 0:
                        print(f"      ⚠️ Content is empty")
                    elif isinstance(content, str) and ("No detailed analysis yet" in content or "Demo data" in content):
                        print(f"      ⚠️ Content is demo data or placeholders")
                    else:
                        print(f"      ✅ Content is normal")
            else:
                print(f"  ⚠️ No report content")
                
    except Exception as e:
        print(f"❌ Check analysis record failed: {e}")
        import traceback
        print(f"detailed error: {traceback.format_exc()}")

def check_specific_stock(stock_symbol="000001"):
    """Check records for a specific stock"""
    print(f"\n🔍 check stock {stock_symbol} records...")
    
    try:
        reports = mongodb_report_manager.get_analysis_reports(
            limit=10, 
            stock_symbol=stock_symbol
        )
        
        print(f"stocks {stock_symbol} number of records: {len(reports)}")
        
        if reports:
            latest_report = reports[0]
            print(f"\n Latest record details:")
            print(f"  analysis ID: {latest_report.get('analysis_id')}")
            print(f"  Timestamp: {latest_report.get('timestamp')}")
            print(f"  Status: {latest_report.get('status')}")
            
            reports_content = latest_report.get('reports', {})
            if reports_content:
                print(f"\n Report content details:")
                for module_name, content in reports_content.items():
                    if isinstance(content, str):
                        preview = content[:200] + "..." if len(content) > 200 else content
                        print(f"\n{module_name}:")
                        print(f"  length: {len(content)} character")
                        print(f"  Preview: {preview}")
        else:
            print(f"⚠️ No stocks found {stock_symbol} records")
            
    except Exception as e:
        print(f"❌ Checking for specific stock records failed: {e}")

def main():
    print(f"🔍 MongoDB Analytical Record Check Tool")
    print(f"=" * 50)
    
    # Check connection
    if not check_mongodb_connection():
        return
    
    # Check all records
    check_analysis_records()
    
    # Check for specific stocks
    check_specific_stock("000001")
    
    print(f"\n🎉 Check completed")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
BaoStock Data Initialization CLI Tool
Provides a command-line interface for BaoStock data initialization and management
"""
import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.worker.baostock_init_service import BaoStockInitService
from app.worker.baostock_sync_service import BaoStockSyncService

# Configure logging
os.makedirs(os.path.join('data', 'logs'), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('data', 'logs', 'baostock_init.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print banner"""
    print("🚀 BaoStock Data Initialization Tool")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)


def print_stats(stats):
    """Print statistics"""
    print("\n📊 Initialization Statistics:")
    print(f"   Completed steps: {stats.progress}")
    print(f"   Basic info: {stats.basic_info_count} records")
    print(f"   Market quotes: {stats.quotes_count} records")
    print(f"   Historical records: {stats.historical_records} records")
    print(f"   Financial records: {stats.financial_records} records")
    print(f"   Error count: {len(stats.errors)}")
    print(f"   Total duration: {stats.duration:.1f}s")
    
    if stats.errors:
        print("\n❌ Error Details:")
        for i, error in enumerate(stats.errors[:5], 1):  # Show first 5 errors only
            print(f"   {i}. {error}")
        if len(stats.errors) > 5:
            print(f"   ... and {len(stats.errors) - 5} more errors")


async def test_connection():
    """Test BaoStock connection"""
    print("🔗 Testing BaoStock connection...")
    try:
        # Database connection not required when testing BaoStock API only
        service = BaoStockSyncService(require_db=False)
        connected = await service.provider.test_connection()

        if connected:
            print("✅ BaoStock connection succeeded")
            return True
        else:
            print("❌ BaoStock connection failed")
            return False

    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False


async def check_database_status():
    """Check database status"""
    print("📋 Checking database status...")
    try:
        service = BaoStockInitService()
        status = await service.check_database_status()
        
        print(f"  📋 Stock basic info: {status.get('basic_info_count', 0)} records")
        if status.get('basic_info_latest'):
            print(f"     Latest update: {status['basic_info_latest']}")
        
        print(f"  📈 Market quotes: {status.get('quotes_count', 0)} records")
        if status.get('quotes_latest'):
            print(f"     Latest update: {status['quotes_latest']}")
        
        print(f"  ✅ Database status: {status.get('status', 'unknown')}")
        
        return status
        
    except Exception as e:
        print(f"❌ Failed to check database status: {e}")
        return None


async def run_full_initialization(historical_days: int = 365, force: bool = False):
    """Run full initialization"""
    print(f"🚀 Starting full initialization (historical days: {historical_days}, force: {force})...")
    
    try:
        service = BaoStockInitService()
        stats = await service.full_initialization(historical_days=historical_days, force=force)
        
        if stats.completed_steps == stats.total_steps:
            print("✅ Full initialization completed successfully")
        else:
            print(f"⚠️ Initialization partially completed: {stats.progress}")
        
        print_stats(stats)
        return stats.completed_steps == stats.total_steps
        
    except Exception as e:
        print(f"❌ Full initialization failed: {e}")
        return False


async def run_basic_initialization():
    """Run basic initialization"""
    print("🚀 Starting basic initialization...")
    
    try:
        service = BaoStockInitService()
        stats = await service.basic_initialization()
        
        if stats.completed_steps == stats.total_steps:
            print("✅ Basic initialization completed successfully")
        else:
            print(f"⚠️ Initialization partially completed: {stats.progress}")
        
        print_stats(stats)
        return stats.completed_steps == stats.total_steps
        
    except Exception as e:
        print(f"❌ Basic initialization failed: {e}")
        return False


def print_help_detail():
    """Print detailed help information"""
    help_text = """
🔧 BaoStock Data Initialization Tool - Detailed Guide

📋 Main Actions:
  --full              Full initialization (recommended for initial deployment)
  --basic-only        Basic initialization only (stock list and quotes)
  --check-only        Check database status only
  --test-connection   Test BaoStock connection

⚙️ Configuration Options:
  --historical-days   Number of historical days (default: 365)
  --force             Force re-initialization (ignore existing data)

📊 Usage Examples:
  # Check database status
  python cli/baostock_init.py --check-only

  # Test connection
  python cli/baostock_init.py --test-connection

  # Full initialization (recommended, default 1 year of history)
  python cli/baostock_init.py --full

  # Custom historical data range (6 months)
  python cli/baostock_init.py --full --historical-days 180

  # Full history initialization (since 1990, requires >=3650 days)
  python cli/baostock_init.py --full --historical-days 10000

  # Full history multi-period initialization (recommended for production)
  python cli/baostock_init.py --full --multi-period --historical-days 10000

  # Force re-initialization
  python cli/baostock_init.py --full --force

  # Basic initialization only
  python cli/baostock_init.py --basic-only

📝 Description:
  - Full initialization includes: basic info, historical data, financial data, real-time quotes
  - Basic initialization includes: basic info, real-time quotes
  - Full initialization is recommended for initial deployment
  - Basic initialization can be used for routine maintenance

⚠️ Notes:
  - Ensure network connectivity is stable
  - Ensure MongoDB database is accessible
  - Full initialization may take a considerable amount of time
  - Recommended to run outside trading hours
"""
    print(help_text)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="BaoStock Data Initialization Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Action arguments
    parser.add_argument('--full', action='store_true', help='Run full initialization')
    parser.add_argument('--basic-only', action='store_true', help='Run basic initialization only')
    parser.add_argument('--check-only', action='store_true', help='Check database status only')
    parser.add_argument('--test-connection', action='store_true', help='Test BaoStock connection')
    parser.add_argument('--help-detail', action='store_true', help='Show detailed help')
    
    # Configuration arguments
    parser.add_argument('--historical-days', type=int, default=365, help='Number of historical days (default: 365)')
    parser.add_argument('--force', action='store_true', help='Force re-initialization')
    
    args = parser.parse_args()
    
    # Show detailed help
    if args.help_detail:
        print_help_detail()
        return
    
    # If no action is specified, show help
    if not any([args.full, args.basic_only, args.check_only, args.test_connection]):
        parser.print_help()
        print("\n💡 Use --help-detail to view detailed instructions")
        return
    
    print_banner()
    
    try:
        success = True
        
        # Test connection
        if args.test_connection:
            success = await test_connection()
        
        # Check database status
        elif args.check_only:
            status = await check_database_status()
            success = status is not None
        
        # Full initialization
        elif args.full:
            success = await run_full_initialization(
                historical_days=args.historical_days,
                force=args.force
            )
        
        # Basic initialization
        elif args.basic_only:
            success = await run_basic_initialization()
        
        # Output result
        print("\n" + "=" * 50)
        if success:
            print("✅ Operation completed successfully")
        else:
            print("❌ Operation failed; please check the log file")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⚠️ Operation interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error occurred during operation: {e}")
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Program interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Program exited abnormally: {e}")
        sys.exit(1)

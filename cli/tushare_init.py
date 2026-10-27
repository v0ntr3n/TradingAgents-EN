#!/usr/bin/env python3
"""
Tushare Data Initialization CLI Tool
Used for data initialization during initial deployment
"""
import asyncio
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_database
from app.worker.tushare_init_service import get_tushare_init_service


def print_banner():
    """Print banner"""
    print("=" * 60)
    print("🚀 Tushare Data Initialization Tool")
    print("=" * 60)
    print()


def print_help():
    """Print help information"""
    print("📋 Usage:")
    print("  python cli/tushare_init.py [options]")
    print()
    print("🔧 Options:")
    print("  --full              Run full initialization (recommended for first-time use)")
    print("  --basic-only        Initialize basic info only")
    print("  --historical-days   Number of historical days (default: 365)")
    print("  --multi-period      Synchronize multi-period data (daily, weekly, monthly)")
    print("  --sync-items        Specify data types to sync (comma-separated)")
    print("                      Choices: basic_info,historical,weekly,monthly,financial,quotes,news")
    print("  --force             Force initialization (overwrite existing data)")
    print("  --batch-size        Batch size (default: 100)")
    print("  --check-only        Check database status only")
    print("  --help              Show this help message")
    print()
    print("📝 Examples:")
    print("  # Initial full initialization (recommended, default 1 year of history)")
    print("  python cli/tushare_init.py --full")
    print()
    print("  # Initialize historical data for the last 6 months")
    print("  python cli/tushare_init.py --full --historical-days 180")
    print()
    print("  # Initialize full historical data (since 1990, requires >=3650 days)")
    print("  python cli/tushare_init.py --full --historical-days 10000")
    print()
    print("  # Initialize and sync multi-period data (daily, weekly, monthly)")
    print("  python cli/tushare_init.py --full --multi-period")
    print()
    print("  # Full-history multi-period initialization (recommended for production)")
    print("  python cli/tushare_init.py --full --multi-period --historical-days 10000")
    print()
    print("  # Sync historical daily data only")
    print("  python cli/tushare_init.py --full --sync-items historical")
    print()
    print("  # Sync financial data and market quotes only")
    print("  python cli/tushare_init.py --full --sync-items financial,quotes")
    print()
    print("  # Sync news data only")
    print("  python cli/tushare_init.py --full --sync-items news")
    print()
    print("  # Update weekly and monthly data only")
    print("  python cli/tushare_init.py --full --sync-items weekly,monthly")
    print()
    print("  # Force re-initialization of all data")
    print("  python cli/tushare_init.py --full --force")
    print()
    print("  # Check current database status only")
    print("  python cli/tushare_init.py --check-only")
    print()


async def check_database_status():
    """Check database status"""
    print("📊 Checking database status...")
    
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        
        # Check collection counts
        basic_count = await db.stock_basic_info.count_documents({})
        quotes_count = await db.market_quotes.count_documents({})
        
        # Check extended field coverage
        extended_count = await db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        # Check latest update timestamps
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        print(f"  📋 Stock basic info: {basic_count:,} records")
        if basic_count > 0:
            coverage = extended_count / basic_count * 100
            print(f"     Extended field coverage: {extended_count:,} records ({coverage:.1f}%)")
            if latest_basic and latest_basic.get("updated_at"):
                print(f"     Latest update: {latest_basic['updated_at']}")
        
        print(f"  📈 Market quotes: {quotes_count:,} records")
        if quotes_count > 0 and latest_quotes and latest_quotes.get("updated_at"):
            print(f"     Latest update: {latest_quotes['updated_at']}")
        
        # Determine whether initialization is needed
        if basic_count == 0:
            print("  ⚠️  Database is empty; running full initialization is recommended")
            return False
        elif extended_count / basic_count < 0.5:
            print("  ⚠️  Extended field coverage is low; re-initialization is recommended")
            return False
        else:
            print("  ✅ Database status is healthy")
            return True
            
    except Exception as e:
        print(f"  ❌ Failed to check database status: {e}")
        return False


async def run_basic_initialization():
    """Run basic info initialization"""
    print("📋 Starting basic info initialization...")
    
    try:
        service = await get_tushare_init_service()
        
        # Synchronize basic info only
        result = await service.sync_service.sync_stock_basic_info(force_update=True)
        
        if result:
            success_count = result.get("success_count", 0)
            print(f"✅ Basic info initialization completed: {success_count:,} stocks")
            return True
        else:
            print("❌ Basic info initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Basic info initialization failed: {e}")
        return False


async def run_full_initialization(historical_days: int, force: bool, multi_period: bool = False, sync_items: list = None):
    """Run full initialization"""
    if sync_items:
        print(f"🚀 Starting data initialization (historical days: {historical_days})...")
        print(f"📋 Sync items: {', '.join(sync_items)}")
    else:
        period_info = "Daily, Weekly, Monthly" if multi_period else "Daily"
        print(f"🚀 Starting full data initialization (historical days: {historical_days}, periods: {period_info})...")

    try:
        service = await get_tushare_init_service()

        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force,
            enable_multi_period=multi_period,
            sync_items=sync_items
        )
        
        # Display results
        if result["success"]:
            print("🎉 Full initialization completed successfully!")
        else:
            print("⚠️ Initialization partially completed with some issues")
        
        print(f"  ⏱️  Duration: {result['duration']:.2f}s")
        print(f"  📊 Progress: {result['progress']}")

        data_summary = result["data_summary"]
        print(f"  📋 Basic info: {data_summary['basic_info_count']:,} records")
        print(f"  📊 Historical data: {data_summary['historical_records']:,} records")
        if multi_period:
            print(f"     - Daily records: {data_summary.get('daily_records', 0):,}")
            print(f"     - Weekly records: {data_summary.get('weekly_records', 0):,}")
            print(f"     - Monthly records: {data_summary.get('monthly_records', 0):,}")
        print(f"  💰 Financial records: {data_summary['financial_records']:,}")
        print(f"  📈 Market quotes: {data_summary['quotes_count']:,}")
        print(f"  📰 News items: {data_summary.get('news_count', 0):,}")
        
        if result["errors"]:
            print(f"  ⚠️  Error count: {len(result['errors'])}")
            for error in result["errors"][:3]:  # Show first 3 errors only
                print(f"     - {error['step']}: {error['error']}")
        
        return result["success"]
        
    except Exception as e:
        print(f"❌ Full initialization failed: {e}")
        return False


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Tushare Data Initialization Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--full", action="store_true", help="Run full initialization")
    parser.add_argument("--basic-only", action="store_true", help="Initialize basic info only")
    parser.add_argument("--historical-days", type=int, default=365, help="Number of historical days")
    parser.add_argument("--multi-period", action="store_true", help="Synchronize multi-period data (daily, weekly, monthly)")
    parser.add_argument("--sync-items", type=str, help="Specify data types to sync (comma-separated), choices: basic_info,historical,weekly,monthly,financial,quotes,news")
    parser.add_argument("--force", action="store_true", help="Force initialization")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--check-only", action="store_true", help="Check database status only")
    parser.add_argument("--help-detail", action="store_true", help="Show detailed help")
    
    args = parser.parse_args()
    
    # Show detailed help
    if args.help_detail:
        print_help()
        return
    
    print_banner()
    
    try:
        # Initialize database connection
        print("🔄 Initializing database connection...")
        await init_database()
        print("✅ Database connection established")
        print()
        
        # Check database status
        db_ok = await check_database_status()
        print()
        
        # Execute requested action
        if args.check_only:
            print("📋 Database status check completed")
            return
        
        elif args.basic_only:
            success = await run_basic_initialization()
            
        elif args.full:
            if not args.force and db_ok:
                print("⚠️ Database already contains data; use --force to force re-initialization")
                return

            # Parse sync_items argument
            sync_items = None
            if args.sync_items:
                sync_items = [item.strip() for item in args.sync_items.split(',')]
                # Validate sync_items
                valid_items = ['basic_info', 'historical', 'weekly', 'monthly', 'financial', 'quotes', 'news']
                invalid_items = [item for item in sync_items if item not in valid_items]
                if invalid_items:
                    print(f"❌ Invalid sync items: {', '.join(invalid_items)}")
                    print(f"   Valid choices: {', '.join(valid_items)}")
                    return

            success = await run_full_initialization(args.historical_days, args.force, args.multi_period, sync_items)
            
        else:
            print("❓ Please specify an action; use --help-detail to view detailed help")
            return
        
        if success:
            print("\n🎉 Initialization completed successfully!")
        else:
            print("\n❌ Initialization failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️ Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

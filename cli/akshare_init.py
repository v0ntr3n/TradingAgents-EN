#!/usr/bin/env python3
"""
AKShare Data Initialization CLI Tool
Used for initial deployment data initialization and management
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
import os

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import init_database, get_mongo_db, close_database
from app.worker.akshare_init_service import get_akshare_init_service
from app.worker.akshare_sync_service import get_akshare_sync_service

# Configure logging
os.makedirs(os.path.join('data', 'logs'), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('data', 'logs', 'akshare_init.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


async def check_database_status():
    """Check database status"""
    print("=" * 50)
    print("📊 Checking database status...")
    
    try:
        db = get_mongo_db()
        
        # Check basic info
        basic_count = await db.stock_basic_info.count_documents({})
        extended_count = await db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        # Get latest update timestamp
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        print(f"  📋 Stock basic info: {basic_count:,} records")
        if basic_count > 0:
            print(f"     Extended field coverage: {extended_count:,} records ({extended_count/basic_count*100:.1f}%)")
            if latest_basic and latest_basic.get("updated_at"):
                print(f"     Latest update: {latest_basic['updated_at']}")
        
        # Check market quotes
        quotes_count = await db.market_quotes.count_documents({})
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        print(f"  📈 Market quotes: {quotes_count:,} records")
        if quotes_count > 0 and latest_quotes and latest_quotes.get("updated_at"):
            print(f"     Latest update: {latest_quotes['updated_at']}")
        
        # Evaluate database status
        if basic_count == 0:
            print("  ❌ Database is empty; full initialization is required")
            return False
        elif extended_count / basic_count < 0.5:
            print("  ⚠️ Extended field coverage is low; re-initialization is recommended")
            return False
        else:
            print("  ✅ Database status is healthy")
            return True
            
    except Exception as e:
        print(f"  ❌ Failed to check database status: {e}")
        return False
    finally:
        print("📋 Database status check completed")


async def run_full_initialization(
    historical_days: int,
    force: bool = False,
    multi_period: bool = False,
    sync_items: list = None
):
    """Run full initialization"""
    print("=" * 50)
    print("🚀 Starting AKShare full data initialization...")
    print(f"📅 Historical data range: {historical_days} days")
    print(f"🔄 Force mode: {'Yes' if force else 'No'}")
    if sync_items:
        print(f"📋 Sync items: {', '.join(sync_items)}")
    elif multi_period:
        print("📊 Multi-period mode: Daily, Weekly, Monthly")

    try:
        service = await get_akshare_init_service()

        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force,
            enable_multi_period=multi_period,
            sync_items=sync_items
        )
        
        print("\n" + "=" * 50)
        print("📊 Initialization Summary:")
        print(f"  ✅ Success: {'Yes' if result['success'] else 'No'}")
        print(f"  ⏱️ Duration: {result['duration']:.2f}s")
        print(f"  📈 Progress: {result['progress']}")
        
        data_summary = result.get('data_summary', {})
        print(f"  📋 Basic info: {data_summary.get('basic_info_count', 0):,} records")
        print(f"  📊 Historical data: {data_summary.get('daily_records', 0):,} records")
        if multi_period:
            print(f"     - Daily records: {data_summary.get('daily_records', 0):,}")
            print(f"     - Weekly records: {data_summary.get('weekly_records', 0):,}")
            print(f"     - Monthly records: {data_summary.get('monthly_records', 0):,}")
        print(f"  💰 Financial records: {data_summary.get('financial_records', 0):,}")
        print(f"  📈 Market quotes: {data_summary.get('quotes_count', 0):,}")
        print(f"  📰 News items: {data_summary.get('news_count', 0):,}")
        
        if result.get('errors'):
            print(f"  ⚠️ Error count: {len(result['errors'])}")
            for error in result['errors'][:3]:  # Show first 3 errors only
                print(f"     - {error.get('step', 'Unknown')}: {error.get('error', 'Unknown error')}")
        
        return result['success']
        
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


async def run_basic_sync_only():
    """Run basic info synchronization only"""
    print("=" * 50)
    print("📋 Starting basic info synchronization...")
    
    try:
        service = await get_akshare_sync_service()
        result = await service.sync_stock_basic_info(force_update=True)
        
        print("✅ Basic info synchronization completed:")
        print(f"  📊 Total processed: {result.get('total_processed', 0):,}")
        print(f"  ✅ Succeeded: {result.get('success_count', 0):,}")
        print(f"  ❌ Errors: {result.get('error_count', 0):,}")
        print(f"  ⏱️ Duration: {result.get('duration', 0):.2f}s")
        
        return result.get('success_count', 0) > 0
        
    except Exception as e:
        print(f"❌ Basic info synchronization failed: {e}")
        return False


async def test_akshare_connection():
    """Test AKShare connection"""
    print("=" * 50)
    print("🔗 Testing AKShare connection...")
    
    try:
        service = await get_akshare_sync_service()
        connected = await service.provider.test_connection()
        
        if connected:
            print("✅ AKShare connection succeeded")
            
            # Test fetching stock list
            stock_list = await service.provider.get_stock_list()
            if stock_list:
                print(f"📋 Successfully fetched stock list: {len(stock_list)} stocks")
                
                # Show first 5 stocks
                print("  First 5 stocks:")
                for i, stock in enumerate(stock_list[:5]):
                    print(f"    {i+1}. {stock.get('code')} - {stock.get('name')}")
            else:
                print("⚠️ Failed to fetch stock list")
                
            return True
        else:
            print("❌ AKShare connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False


def print_help_detail():
    """Print detailed help information"""
    help_text = """
🔧 AKShare Data Initialization Tool - Detailed Guide

📋 Main Actions:
  --check-only        Check database status only without performing any changes
  --test-connection   Test AKShare connection status
  --basic-only        Synchronize stock basic info only
  --full              Run full data initialization workflow
  
🔄 Full Initialization Workflow Includes:
  1. Check database status
  2. Synchronize stock basic info
  3. Synchronize historical data (configurable days)
  4. Synchronize financial data
  5. Synchronize latest market quotes
  6. Verify data integrity

⚙️ Configuration Options:
  --historical-days   Number of historical days to fetch (default: 365)
  --force             Force re-initialization, ignoring existing data
  
📝 Usage Examples:
  # Check database status
  python cli/akshare_init.py --check-only

  # Test connection
  python cli/akshare_init.py --test-connection

  # Synchronize basic info only
  python cli/akshare_init.py --basic-only

  # Full initialization (recommended for initial deployment, default 1 year of history)
  python cli/akshare_init.py --full

  # Custom historical data range (6 months)
  python cli/akshare_init.py --full --historical-days 180

  # Full history initialization (since 1990, requires >=3650 days)
  python cli/akshare_init.py --full --historical-days 10000

  # Full history multi-period initialization (recommended for production)
  python cli/akshare_init.py --full --multi-period --historical-days 10000

  # Force re-initialization
  python cli/akshare_init.py --full --force

📊 Log File:
  All operation logs are saved to akshare_init.log
  
⚠️ Notes:
  - Initial run may take a considerable amount of time (30 mins - 2 hours)
  - Recommended to run under stable network conditions
  - AKShare has API rate limits; please wait patiently
  - Press Ctrl+C at any time to abort
"""
    print(help_text)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="AKShare Data Initialization Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Action arguments
    parser.add_argument("--check-only", action="store_true", help="Check database status only")
    parser.add_argument("--test-connection", action="store_true", help="Test AKShare connection")
    parser.add_argument("--basic-only", action="store_true", help="Synchronize basic info only")
    parser.add_argument("--full", action="store_true", help="Run full initialization")
    
    # Configuration arguments
    parser.add_argument("--historical-days", type=int, default=365, help="Number of historical days (default: 365)")
    parser.add_argument("--multi-period", action="store_true", help="Synchronize multi-period data (daily, weekly, monthly)")
    parser.add_argument("--sync-items", type=str, help="Specify data types to sync (comma-separated), choices: basic_info,historical,weekly,monthly,financial,quotes,news")
    parser.add_argument("--force", action="store_true", help="Force re-initialization")
    parser.add_argument("--help-detail", action="store_true", help="Show detailed help message")
    
    args = parser.parse_args()
    
    # Show detailed help
    if args.help_detail:
        print_help_detail()
        return
    
    # If no action is specified, show help
    if not any([args.check_only, args.test_connection, args.basic_only, args.full]):
        parser.print_help()
        print("\n💡 Use --help-detail to view detailed instructions")
        return
    
    print("🚀 AKShare Data Initialization Tool")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Initialize database connection
        print("🔄 Initializing database connection...")
        await init_database()
        print("✅ Database connection established")
        print()

        success = True

        # Check database status
        if args.check_only:
            await check_database_status()
        
        # Test connection
        elif args.test_connection:
            success = await test_akshare_connection()
        
        # Basic info sync only
        elif args.basic_only:
            success = await run_basic_sync_only()
        
        # Full initialization
        elif args.full:
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

            success = await run_full_initialization(
                args.historical_days,
                args.force,
                args.multi_period,
                sync_items
            )
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 Operation completed!")
        else:
            print("❌ Operation failed; please check the log file")

    except KeyboardInterrupt:
        print("\n⚠️ Operation interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error occurred: {e}")
        logger.exception("Unexpected error occurred")
    finally:
        # Close database connection
        try:
            await close_database()
        except Exception as e:
            logger.error(f"Failed to close database connection: {e}")

        # Exit with appropriate status code
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

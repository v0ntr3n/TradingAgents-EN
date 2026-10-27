"""
Migration management command line tool

Usage:
    python -m migrations.cli status              # View migration status
    python -m migrations.cli run                  # Execute all pending migrations
    python -m migrations.cli run --version 2.0.1  # Execute specified version
    python -m migrations.cli history              # View migration history
"""

import asyncio
import argparse
import sys
import os
import logging

# Make sure the project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("migrations.cli")


async def get_db():
    """Get database connection"""
    from app.core.database import init_database, get_mongo_db
    await init_database()
    return get_mongo_db()


async def cmd_status():
    """Show migration status"""
    from migrations.runner import MigrationRunner

    db = await get_db()
    runner = MigrationRunner(db)
    status = await runner.get_status()

    print("\n" + "=" * 50)
    print("📊 Database migration status")
    print("=" * 50)
    print(f"  Total migrations:   {status['total_migrations']}")
    print(f"  Executed:     {status['applied']}")
    print(f"  To be executed:     {status['pending']}")

    if status["applied_versions"]:
        print(f"\n  ✅ Executed version:")
        for v in status["applied_versions"]:
            print(f"     - {v}")

    if status["pending_versions"]:
        print(f"\n  ⏳ Version to be executed:")
        for v in status["pending_versions"]:
            print(f"     - {v}")

    print()


async def cmd_run(version: str = None):
    """Execute migration"""
    from migrations.runner import MigrationRunner

    db = await get_db()
    runner = MigrationRunner(db)

    if version:
        print(f"\n🔄 Execute specified migration: {version}")
        result = await runner.run_one(version)
        results = [result]
    else:
        print("\n🔄 Execute all pending migrations...")
        results = await runner.run_pending()

    if not results:
        print("✅ There are no migrations to perform\n")
        return

    print("\n" + "=" * 50)
    print("📋 Migration execution results")
    print("=" * 50)
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌" if r["status"] == "failed" else "⏭️"
        line = f"  {icon} {r['version']}"
        if "duration_ms" in r:
            line += f" ({r['duration_ms']}ms)"
        if r.get("error"):
            line += f" - {r['error']}"
        print(line)
    print()


async def cmd_history():
    """View migration history"""
    db = await get_db()
    cursor = db.migration_history.find().sort("applied_at", -1)
    docs = await cursor.to_list(length=50)

    print("\n" + "=" * 60)
    print("📜 Migration history")
    print("=" * 60)

    if not docs:
        print("  (No record)")
    else:
        for doc in docs:
            icon = "✅" if doc.get("status") == "success" else "❌"
            ts = doc.get("applied_at", "").strftime("%Y-%m-%d %H:%M:%S") if doc.get("applied_at") else "N/A"
            dur = doc.get("duration_ms", "?")
            print(f"  {icon} {doc['version']:10s} | {ts} | {dur}ms | {doc.get('description', '')}")
            if doc.get("error"):
                print(f"     ❌ Error: {doc['error']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="TradingAgents-CN Database migration tool")
    subparsers = parser.add_subparsers(dest="command", help="command")

    subparsers.add_parser("status", help="View migration status")

    run_parser = subparsers.add_parser("run", help="Execute migration")
    run_parser.add_argument("--version", "-v", help="Specify a version to execute")

    subparsers.add_parser("history", help="View migration history")

    args = parser.parse_args()

    if args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "run":
        asyncio.run(cmd_run(args.version))
    elif args.command == "history":
        asyncio.run(cmd_history())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


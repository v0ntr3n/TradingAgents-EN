"""
TradingAgents-CN Database migration framework

Versioned MongoDB database migration mechanism:
- Each version corresponds to a migration script
- Automatically detect and execute outstanding migrations on startup
- Record migration history to migration_history collection
- Supports idempotent execution (safe repeated runs)

How to use:
    # Automatically executed when app starts
    from migrations.runner import MigrationRunner
    runner = MigrationRunner(db)
    await runner.run_pending()
    
    # Command line tools
    python -m migrations.cli status    # View migration status
    python -m migrations.cli run       # Execute pending migration
    python -m migrations.cli run --version 2.0.1  # Execute specified version
"""


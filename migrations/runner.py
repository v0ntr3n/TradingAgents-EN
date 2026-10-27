"""
Migrate executor

Responsible for scanning migration scripts, checking execution status, and executing pending migrations in sequence.
"""

import importlib
import logging
import time
import pkgutil
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger("migrations")


class MigrationRunner:
    """Database migration executor"""

    HISTORY_COLLECTION = "migration_history"

    def __init__(self, db):
        """
        Args:
            db: AsyncIOMotorDatabase Example
        """
        self.db = db
        self._migrations: List[Dict[str, Any]] = []

    def discover_migrations(self) -> List[Dict[str, Any]]:
        """
        Scan all migrations packages v*.py Migration script
        
        Returns:
            List of migration information sorted by version number
        """
        import migrations as mig_pkg

        found = []
        for importer, modname, ispkg in pkgutil.iter_modules(mig_pkg.__path__):
            if not modname.startswith("v"):
                continue
            full_name = f"migrations.{modname}"
            try:
                mod = importlib.import_module(full_name)
                version = getattr(mod, "VERSION", None)
                description = getattr(mod, "DESCRIPTION", "")
                upgrade_fn = getattr(mod, "upgrade", None)
                downgrade_fn = getattr(mod, "downgrade", None)

                if not version or not upgrade_fn:
                    logger.warning(
                        f"⚠️ skip {modname}: Missing VERSION or upgrade function"
                    )
                    continue

                found.append({
                    "version": version,
                    "description": description,
                    "module": modname,
                    "upgrade": upgrade_fn,
                    "downgrade": downgrade_fn,
                })
            except Exception as e:
                logger.error(f"❌ Load migration script {modname} failed: {e}")

        # Sort by version number (replace "2.0.1" to a comparable tuple)
        found.sort(key=lambda m: self._version_key(m["version"]))
        self._migrations = found
        return found

    async def get_applied_versions(self) -> List[str]:
        """Get a list of successfully executed migration versions"""
        cursor = self.db[self.HISTORY_COLLECTION].find(
            {"status": "success"},
            {"version": 1, "_id": 0},
        ).sort("applied_at", 1)
        docs = await cursor.to_list(length=None)
        return [d["version"] for d in docs]

    async def get_pending(self) -> List[Dict[str, Any]]:
        """Get the list of pending migrations"""
        if not self._migrations:
            self.discover_migrations()
        applied = set(await self.get_applied_versions())
        return [m for m in self._migrations if m["version"] not in applied]

    async def run_pending(self) -> List[Dict[str, Any]]:
        """
        Execute all pending migrations
        
        Returns:
            List of performed migration results
        """
        pending = await self.get_pending()
        if not pending:
            logger.info("✅ The database is already the latest version and does not need to be migrated")
            return []

        logger.info(f"📦 discover {len(pending)} pending migrations")
        results = []

        for mig in pending:
            result = await self._execute_one(mig)
            results.append(result)
            if result["status"] == "failed":
                logger.error(
                    f"❌ Migrate {mig['version']} Failure, stop subsequent migrations"
                )
                break

        return results

    async def run_one(self, version: str) -> Dict[str, Any]:
        """Execute migration of specified version"""
        if not self._migrations:
            self.discover_migrations()
        target = next(
            (m for m in self._migrations if m["version"] == version), None
        )
        if not target:
            raise ValueError(f"version not found {version} migration script")

        applied = set(await self.get_applied_versions())
        if version in applied:
            logger.info(f"⏭️ version {version} Already executed, skip")
            return {"version": version, "status": "skipped"}

        return await self._execute_one(target)

    async def _execute_one(self, mig: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a single migration"""
        version = mig["version"]
        logger.info(f"🔄 Execute migration {version}: {mig['description']}")

        start = time.monotonic()
        try:
            await mig["upgrade"](self.db)
            duration_ms = int((time.monotonic() - start) * 1000)

            record = {
                "version": version,
                "description": mig["description"],
                "module": mig["module"],
                "applied_at": datetime.now(timezone.utc),
                "duration_ms": duration_ms,
                "status": "success",
                "error": None,
            }
            await self.db[self.HISTORY_COLLECTION].insert_one(record)
            logger.info(
                f"✅ Migrate {version} Complete ({duration_ms}ms)"
            )
            return {"version": version, "status": "success",
                    "duration_ms": duration_ms}

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            record = {
                "version": version,
                "description": mig["description"],
                "module": mig["module"],
                "applied_at": datetime.now(timezone.utc),
                "duration_ms": duration_ms,
                "status": "failed",
                "error": str(e),
            }
            await self.db[self.HISTORY_COLLECTION].insert_one(record)
            logger.error(f"❌ Migrate {version} failed: {e}")
            return {"version": version, "status": "failed",
                    "error": str(e), "duration_ms": duration_ms}

    async def get_status(self) -> Dict[str, Any]:
        """Get a summary of migration status"""
        if not self._migrations:
            self.discover_migrations()
        applied = await self.get_applied_versions()
        pending = await self.get_pending()
        return {
            "total_migrations": len(self._migrations),
            "applied": len(applied),
            "pending": len(pending),
            "applied_versions": applied,
            "pending_versions": [m["version"] for m in pending],
        }

    @staticmethod
    def _version_key(version: str):
        """Convert the version number string into a sortable tuple, such as '2.0.1' -> (2, 0, 1). 
        Non-numeric fields (such as beta.4) are retained as strings, and fallback to 0 if conversion to int fails."""
        parts = []
        for p in version.split("."):
            # Remove non-numeric prefixes (e.g. 'beta' → '') , but does not lose the semantic segment
            digits = "".join(ch for ch in p if ch.isdigit())
            if digits:
                parts.append(int(digits))
            else:
                # Assign a large value to a pure non-numeric field so that it ranks at the end
                parts.append(9999)
        return tuple(parts)


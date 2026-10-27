"""
Migration script base class

Each migration script needs to inherit this base class, or directly define module-level constants and functions.

Method 1 (recommended, simple): module level definition
    # migrations/v2_0_1.py
    VERSION = "2.0.1"
    DESCRIPTION = "Add xxx field"
    
    async def upgrade(db):
        await db.some_collection.update_many(...)
    
    async def downgrade(db):
        await db.some_collection.update_many(...)

Method 2: Class inheritance
    class Migration(BaseMigration):
        VERSION = "2.0.1"
        DESCRIPTION = "Add xxx field"
        
        async def upgrade(self, db):
            ...
"""

from abc import ABC, abstractmethod


class BaseMigration(ABC):
    """Migration script base class (optional use)"""
    
    VERSION: str = ""
    DESCRIPTION: str = ""
    
    @abstractmethod
    async def upgrade(self, db):
        """
        Forward migration - applying database changes
        
        Args:
            db: AsyncIOMotorDatabase Example
            
        Things to note:
        - Must be idempotent (repeated execution will not cause errors)
        - Use $exists Check if field already exists
        - Use find_one to check if the data has been inserted
        - Use create_index when creating an index (it will be automatically skipped if it already exists)
        """
        raise NotImplementedError
    
    async def downgrade(self, db):
        """
        Rollback migration - undo database changes (optional implementation)
        
        Args:
            db: AsyncIOMotorDatabase Example
        """
        raise NotImplementedError(
            f"Migration {self.VERSION} does not support downgrade"
        )


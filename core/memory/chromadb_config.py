"""
ChromaDB Configuration module

Provides ChromaDB configurations optimized for different operating systems
"""

import platform
import logging
import os
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


def is_windows_11() -> bool:
    """Check whether it is Windows 11"""
    if platform.system() != "Windows":
        return False
    
    try:
        version = platform.version()
        # Windows 11 build number >= 22000
        build_number = int(version.split('.')[-1])
        return build_number >= 22000
    except Exception:
        return False


def get_optimal_chromadb_client():
    """
    Get a ChromaDB client optimized for your current operating system
    
    Returns:
        chromadb.Client Example
        
    Raises:
        Exception: If all initialization methods fail
    """
    import os
    import shutil
    
    system = platform.system()
    # 🔥 Normalize paths to avoid Windows path issues
    persist_dir = os.path.normpath(os.path.join(os.getcwd(), "data", "chromadb"))
    
    # 🔥 Make sure the directory exists
    try:
        os.makedirs(persist_dir, exist_ok=True)
    except Exception as e:
        logger.warning(f"⚠️ Failed to create ChromaDB directory: {e}")
    
    # 🔥 Prioritize the use of persistence mode and add multiple persistence configuration attempts
    configs_to_try = []
    
    # 1. Try persistence mode first (optimized according to operating system)
    if system == "Windows":
        if is_windows_11():
            # Windows 11 Optimize configuration (persistence)
            configs_to_try.append({
                "name": "Windows 11 Persistence configuration",
                "settings": Settings(
                    allow_reset=True,
                    anonymized_telemetry=False,
                    is_persistent=True,
                    persist_directory=persist_dir
                )
            })
        else:
            # Windows 10 Compatible configuration (persistence)
            configs_to_try.append({
                "name": "Windows 10 Persistence configuration",
                "settings": Settings(
                    allow_reset=True,
                    anonymized_telemetry=False,
                    is_persistent=True,
                    persist_directory=persist_dir
                )
            })
    elif system == "Linux":
        configs_to_try.append({
            "name": "Linux Persistence configuration",
            "settings": Settings(
                allow_reset=True,
                anonymized_telemetry=False,
                is_persistent=True,
                persist_directory=persist_dir
            )
        })
    elif system == "Darwin":
        configs_to_try.append({
            "name": "macOS Persistence configuration",
            "settings": Settings(
                allow_reset=True,
                anonymized_telemetry=False,
                is_persistent=True,
                persist_directory=persist_dir
            )
        })
    else:
        configs_to_try.append({
            "name": f"Default persistence configuration ({system})",
            "settings": Settings(
                allow_reset=True,
                anonymized_telemetry=False,
                is_persistent=True,
                persist_directory=persist_dir
            )
        })
    
    # 🔥 Add in-memory mode as a last resort (only used if all persistence options fail)
    configs_to_try.append({
        "name": "Memory mode (last standby)",
        "settings": Settings(
            allow_reset=True,
            anonymized_telemetry=False,
            is_persistent=False
        )
    })
    
    # 🔥 Give priority to persistence mode and automatically clean up damaged databases
    last_error = None
    persistent_cleaned = False  # Mark whether the database has been cleaned
    
    for i, config in enumerate(configs_to_try):
        try:
            config_name = config['name']
            is_persistent = config['settings'].is_persistent
            
            logger.info(f"📚 try config {i+1}/{len(configs_to_try)}: {config_name}")
            
            # 🔥 If it is persistence mode and has failed before (and has not been cleaned yet), clean the database directory first.
            if is_persistent and last_error and not persistent_cleaned:
                error_msg = str(last_error)
                # Check whether it is an error related to database corruption
                if any(keyword in error_msg.lower() for keyword in [
                    "panic", "panicked", "panicException",
                    "range start index", "out of range", 
                    "corrupt", "damaged", "sqlite", "index"
                ]):
                    logger.warning(f"⚠️ Possible database corruption detected, automatic directory cleanup: {persist_dir}")
                    try:
                        # Back up old data
                        backup_dir = f"{persist_dir}.backup"
                        if os.path.exists(backup_dir):
                            shutil.rmtree(backup_dir)
                        if os.path.exists(persist_dir):
                            shutil.move(persist_dir, backup_dir)
                            logger.info(f"✅ Old database has been backed up to: {backup_dir}")
                        # Recreate directory
                        os.makedirs(persist_dir, exist_ok=True)
                        logger.info(f"✅ The database directory has been cleaned and is ready for re-initialization")
                        persistent_cleaned = True
                    except Exception as cleanup_error:
                        logger.warning(f"⚠️ Failed to clean database directory: {cleanup_error}")
                        # If cleanup fails, try force deletion and rebuild
                        try:
                            if os.path.exists(persist_dir):
                                shutil.rmtree(persist_dir)
                            os.makedirs(persist_dir, exist_ok=True)
                            logger.info(f"✅ Forced cleanup of database directory successful")
                            persistent_cleaned = True
                        except Exception as force_cleanup_error:
                            logger.error(f"❌ Forced cleanup also failed: {force_cleanup_error}")
            
            # 🔥 Create a ChromaDB client
            client = chromadb.Client(config['settings'])
            
            # 🔥 Test the connection (verify that the client is working properly)
            try:
                client.heartbeat()
            except Exception as heartbeat_error:
                # If it is in persistence mode and has not been cleaned yet, try cleaning it and try again.
                if is_persistent and not persistent_cleaned:
                    logger.warning(f"⚠️ ChromaDB Heartbeat test failed, try cleaning and trying again...")
                    try:
                        # Back up and clean
                        backup_dir = f"{persist_dir}.backup"
                        if os.path.exists(backup_dir):
                            shutil.rmtree(backup_dir)
                        if os.path.exists(persist_dir):
                            shutil.move(persist_dir, backup_dir)
                        os.makedirs(persist_dir, exist_ok=True)
                        logger.info(f"✅ Database directory cleaned")
                        persistent_cleaned = True
                        
                        # Recreate the client
                        client = chromadb.Client(config['settings'])
                        client.heartbeat()
                        logger.info(f"✅ Reinitialization successful after cleaning")
                    except Exception as retry_error:
                        logger.warning(f"⚠️ Even retrying after cleaning failed.: {retry_error}")
                        raise heartbeat_error
                else:
                    raise heartbeat_error
            
            # 🔥 Initialization successful, recording running mode
            if is_persistent:
                logger.info(f"✅ ChromaDB Client initialization successful: {config_name}")
                logger.info(f"   📁 operating mode: persistence mode")
                logger.info(f"   📂 data directory: {persist_dir}")
            else:
                logger.info(f"✅ ChromaDB Client initialization successful: {config_name}")
                logger.warning(f"   ⚠️ operating mode: Memory mode (data will not be persisted)")
            
            return client
            
        except Exception as e:
            last_error = e
            error_msg = str(e)
            logger.warning(f"⚠️ Configuration {config['name']} failed: {error_msg}")
            
            # 🔥 If it's a Rust panic error, log details
            if "PanicException" in error_msg or "panicked" in error_msg:
                logger.error(f"❌ ChromaDB Rust panic Error, possibly version incompatibility or database corruption")
                if config['settings'].is_persistent and not persistent_cleaned:
                    logger.info(f"   🔄 The database directory will be automatically cleaned the next time you try")
            
            # Continue to try the next configuration
            continue
    
    # 🔥 All configurations fail throwing the last error
    raise Exception(f"All ChromaDB configurations fail with the last error: {last_error}")


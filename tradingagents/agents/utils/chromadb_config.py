"""
ChromaDB Unified configuration module
Supports automatic adaptation of Windows 10/11 and other operating systems
"""
import os
import platform
import chromadb
from chromadb.config import Settings


def is_windows_11() -> bool:
    """
    Check whether it is Windows 11
    
    Returns:
        bool: Returns True if Windows 11, otherwise False
    """
    if platform.system() != "Windows":
        return False
    
    # Windows 11 The version number is usually 10.0.22000 or higher
    version = platform.version()
    try:
        # Extract the version number, the format is usually "10.0.26100"
        version_parts = version.split('.')
        if len(version_parts) >= 3:
            build_number = int(version_parts[2])
            # Windows 11 Build numbers start at 22000
            return build_number >= 22000
    except (ValueError, IndexError):
        pass
    
    return False


def get_win10_chromadb_client():
    """
    Get a Windows 10-compatible ChromaDB client
    
    Returns:
        chromadb.Client: ChromaDB client instance
    """
    settings = Settings(
        allow_reset=True,
        anonymized_telemetry=False,
        is_persistent=False,
        # Windows 10 specific configuration
        chroma_db_impl="duckdb+parquet",
        chroma_api_impl="chromadb.api.segment.SegmentAPI",
        # Use temporary directories to avoid permission issues
        persist_directory=None
    )
    
    try:
        client = chromadb.Client(settings)
        return client
    except Exception as e:
        # Downgrade to the most basic configuration
        basic_settings = Settings(
            allow_reset=True,
            is_persistent=False
        )
        return chromadb.Client(basic_settings)


def get_win11_chromadb_client():
    """
    Get the Windows 11 optimized ChromaDB client
    
    Returns:
        chromadb.Client: ChromaDB client instance
    """
    # Windows 11 Better support for ChromaDB, allowing for more modern configurations
    settings = Settings(
        allow_reset=True,
        anonymized_telemetry=False,  # Disable telemetry to avoid posthog errors
        is_persistent=False,
        # Windows 11 You can use the default implementation for better performance
        chroma_db_impl="duckdb+parquet",
        chroma_api_impl="chromadb.api.segment.SegmentAPI"
        # Remove persist_directory=None, Let it use the default value
    )
    
    try:
        client = chromadb.Client(settings)
        return client
    except Exception as e:
        # If you still have problems, use the simplest configuration
        minimal_settings = Settings(
            allow_reset=True,
            anonymized_telemetry=False,  # Key: Disable telemetry
            is_persistent=False
        )
        return chromadb.Client(minimal_settings)


def get_optimal_chromadb_client():
    """
    Automatically select optimal ChromaDB configuration based on operating system
    
    Returns:
        chromadb.Client: ChromaDB client instance
    """
    system = platform.system()
    
    if system == "Windows":
        # Use more accurate Windows 11 detection
        if is_windows_11():
            # Windows 11 or newer version
            return get_win11_chromadb_client()
        else:
            # Windows 10 or older, use compatible configuration
            return get_win10_chromadb_client()
    else:
        # Non-Windows systems, use standard configuration
        settings = Settings(
            allow_reset=True,
            anonymized_telemetry=False,
            is_persistent=False
        )
        return chromadb.Client(settings)


# Export configuration
__all__ = [
    'get_optimal_chromadb_client',
    'get_win10_chromadb_client',
    'get_win11_chromadb_client',
    'is_windows_11'
]


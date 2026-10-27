"""
Data source priority management module

Provide a unified data source priority acquisition function to avoid code duplication
"""
from typing import Any, Dict, Iterable, List
import logging

logger = logging.getLogger(__name__)


DEFAULT_ENABLED_SOURCES = ['local', 'tushare', 'akshare', 'baostock']


def _normalize_source_name(value: Any) -> str:
    """Normalize data source names or enumeration values to lowercase strings."""
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip().lower()


def _build_global_source_index(data_source_configs: Iterable[Any]) -> Dict[str, Any]:
    """Create name/type dual indexes for globally enabled data sources."""
    source_index: Dict[str, Any] = {}
    for ds_config in data_source_configs:
        aliases = {
            _normalize_source_name(getattr(ds_config, "name", "")),
            _normalize_source_name(getattr(ds_config, "type", "")),
        }
        for alias in aliases:
            if alias:
                source_index[alias] = ds_config
    return source_index


def _extract_grouping_field(grouping: Any, field_name: str, default: Any = None) -> Any:
    """Compatible with two group record access methods of dict / Pydantic objects."""
    if isinstance(grouping, dict):
        return grouping.get(field_name, default)
    return getattr(grouping, field_name, default)


def _merge_grouped_enabled_sources(data_source_configs: Iterable[Any], groupings: Iterable[Any]) -> List[str]:
    """
    Merge global data source configuration and market category grouping configuration.

    Rules:
    1. overall situation enabled=False The data source is never returned.
    2. Grouping under current market_category enabled=False The data source is only disabled for this category.
    3. Declared data sources within a group are sorted by group priority.
    4. Ungrouped data sources are appended according to global priority to avoid direct loss of old data when it lacks grouping.
    """
    enabled_configs = [ds for ds in data_source_configs if getattr(ds, "enabled", False)]
    enabled_configs.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    if not enabled_configs:
        return []

    source_index = _build_global_source_index(enabled_configs)
    grouped_entries = list(groupings or [])
    grouped_entries.sort(
        key=lambda item: _extract_grouping_field(item, "priority", 0),
        reverse=True,
    )

    selected_sources: List[str] = []
    handled_sources = set()

    for grouping in grouped_entries:
        grouping_name = _normalize_source_name(
            _extract_grouping_field(grouping, "data_source_name", "")
        )
        if not grouping_name:
            continue

        ds_config = source_index.get(grouping_name)
        if not ds_config:
            continue

        source_type = _normalize_source_name(getattr(ds_config, "type", ""))
        if not source_type:
            continue

        handled_sources.add(source_type)
        if not _extract_grouping_field(grouping, "enabled", False):
            continue

        if source_type not in selected_sources:
            selected_sources.append(source_type)

    for ds_config in enabled_configs:
        source_type = _normalize_source_name(getattr(ds_config, "type", ""))
        if not source_type or source_type in handled_sources:
            continue
        selected_sources.append(source_type)

    return selected_sources


async def _get_market_groupings_async(market_category: str) -> List[Dict[str, Any]]:
    """Read the data source grouping configuration of the specified market category."""
    if not market_category:
        return []

    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()
        return await db.datasource_groupings.find(
            {"market_category_id": market_category}
        ).sort("priority", -1).to_list(length=None)
    except Exception as exc:
        logger.warning(f"⚠️ [Data source priority] Failed to read group configuration({market_category}): {exc}")
        return []


def _get_market_groupings_sync(market_category: str) -> List[Dict[str, Any]]:
    """Synchronously read the data source grouping configuration of the specified market category."""
    if not market_category:
        return []

    try:
        from app.core.database import get_mongo_db_sync

        db = get_mongo_db_sync()
        cursor = db.datasource_groupings.find({"market_category_id": market_category}).sort("priority", -1)
        return list(cursor)
    except Exception as exc:
        logger.warning(f"⚠️ [Data source priority] Synchronous reading of group configuration failed({market_category}): {exc}")
        return []


async def get_enabled_data_sources_async(market_category: str = "a_shares") -> List[str]:
    """
    Get the list of enabled data sources (asynchronous version).

    Read the data source configuration from the database and sort it from high to low priority.
    No hard-coded filtering is performed, and the database configuration is completely followed.
    """
    try:
        from app.core.unified_config import UnifiedConfigManager

        config = UnifiedConfigManager()
        data_source_configs = await config.get_data_source_configs_async()

        groupings = await _get_market_groupings_async(market_category)
        enabled_sources = _merge_grouped_enabled_sources(data_source_configs, groupings)

        if enabled_sources:
            logger.info(f"✅ [Data source priority] {market_category}: {enabled_sources}")
            return enabled_sources

        default_sources = DEFAULT_ENABLED_SOURCES
        logger.warning(f"⚠️ [Data source priority] There is no enabled data source in the database, using the default configuration: {default_sources}")
        return default_sources

    except Exception as e:
        default_sources = DEFAULT_ENABLED_SOURCES
        logger.error(f"❌ [Data source priority] Failed to obtain: {e}, Use default configuration: {default_sources}")
        return default_sources


async def get_available_data_sources_async(market_category: str = "a_shares") -> List[str]:
    """
    Gets the list of enabled and currently available data sources (asynchronous version).

    The return order follows the priority configuration in the database and only retains the current adapter.is_available() A data source that is True.
    """
    enabled_sources = await get_enabled_data_sources_async(market_category)

    try:
        from app.services.data_sources.manager import DataSourceManager

        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        available_names = {_normalize_source_name(adapter.name) for adapter in available_adapters}
        available_sources = [source for source in enabled_sources if source in available_names]

        if available_sources:
            logger.info(f"✅ [Available data sources] {market_category}: {available_sources}")
            return available_sources

        logger.warning(f"⚠️ [Available data sources] {market_category}: No data source is enabled and available")
        return []

    except Exception as e:
        logger.error(f"❌ [Available data sources] Failed to obtain: {e}")
        return []


def get_available_data_sources_sync(market_category: str = "a_shares") -> List[str]:
    """
    Gets the list of enabled and currently available data sources (synchronized versions).
    """
    enabled_sources = get_enabled_data_sources_sync(market_category)

    try:
        from app.services.data_sources.manager import DataSourceManager

        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        available_names = {_normalize_source_name(adapter.name) for adapter in available_adapters}
        available_sources = [source for source in enabled_sources if source in available_names]

        if available_sources:
            logger.info(f"✅ [Available data sources] {market_category}: {available_sources}")
            return available_sources

        logger.warning(f"⚠️ [Available data sources] {market_category}: No data source is enabled and available")
        return []

    except Exception as e:
        logger.error(f"❌ [Available data sources] Failed to obtain: {e}")
        return []


def get_enabled_data_sources_sync(market_category: str = "a_shares") -> List[str]:
    """
    Get the list of enabled data sources (sync version)
    
    Read data source configuration from the database, sorted by priority from high to low
    No hard-coded filtering, completely follow the database configuration
    
    Args:
        market_category: Market classification (a_shares, us_stocks, hk_stocks)
        
    Returns:
        List of enabled data sources, sorted by priority from high to low
        For example: ['local', 'tushare', 'akshare', 'baostock']
    """
    try:
        from app.core.unified_config import UnifiedConfigManager
        
        config = UnifiedConfigManager()
        data_source_configs = config.get_data_source_configs()

        groupings = _get_market_groupings_sync(market_category)
        enabled_sources = _merge_grouped_enabled_sources(data_source_configs, groupings)
        
        if enabled_sources:
            logger.info(f"✅ [Data source priority] {market_category}: {enabled_sources}")
            return enabled_sources
        else:
            # Fall back to default configuration
            default_sources = DEFAULT_ENABLED_SOURCES
            logger.warning(f"⚠️ [Data source priority] There is no enabled data source in the database, using the default configuration: {default_sources}")
            return default_sources
            
    except Exception as e:
        # Fallback to default configuration when exception occurs
        default_sources = DEFAULT_ENABLED_SOURCES
        logger.error(f"❌ [Data source priority] Failed to obtain: {e}, Use default configuration: {default_sources}")
        return default_sources


async def get_preferred_data_source_async(market_category: str = "a_shares") -> str:
    """
    Get the highest priority data source (asynchronous version)
    
    Args:
        market_category: Market classification (a_shares, us_stocks, hk_stocks)
        
    Returns:
        The name of the data source with the highest priority, e.g.: 'local'
    """
    available_sources = await get_available_data_sources_async(market_category)
    preferred_source = available_sources[0] if available_sources else 'tushare'
    logger.info(f"📊 [Prioritize data sources] {market_category}: {preferred_source}")
    return preferred_source


def get_preferred_data_source_sync(market_category: str = "a_shares") -> str:
    """
    Get the highest priority data source (synchronized version)
    
    Args:
        market_category: Market classification (a_shares, us_stocks, hk_stocks)
        
    Returns:
        The name of the data source with the highest priority, e.g.: 'local'
    """
    available_sources = get_available_data_sources_sync(market_category)
    preferred_source = available_sources[0] if available_sources else 'tushare'
    logger.info(f"📊 [Prioritize data sources] {market_category}: {preferred_source}")
    return preferred_source


from fastapi import APIRouter, Depends
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any

router = APIRouter()
logger = logging.getLogger("webapi")


def is_jdyun_mode() -> bool:
    """Determine whether it is JD Cloud cooperation version mode"""
    return os.getenv("JDYUN_MODE", "false").lower() == "true"


def get_version() -> str:
    """Read version number from VERSION file"""
    try:
        version_file = Path(__file__).parent.parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "0.1.16"  # Default version number


@router.get("/health")
async def health():
    """Health check interface - front-end use"""
    return {
        "success": True,
        "data": {
            "status": "ok",
            "version": get_version(),
            "timestamp": int(time.time()),
            "service": "TradingAgents-CN API"
        },
        "message": "The service is running normally"
    }

@router.get("/healthz")
async def healthz():
    """Kubernetes health check"""
    return {"status": "ok"}

@router.get("/readyz")
async def readyz():
    """Kubernetes Readiness check"""
    return {"ready": True}


# Cache layer/non-real API data source type, not considered a usable data source
_CACHE_SOURCE_TYPES = {"local", "mongodb", "local_file"}


@router.get("/system/readiness", response_model=Dict[str, Any])
async def system_readiness():
    """
    System readiness check: return the readiness status of data source configuration, basic data synchronization, and LLM configuration,
    It is used as a homepage guidance card to guide users to complete the necessary configuration before first use.
    """
    readiness = {
        "datasource_configured": False,
        "basics_synced": False,
        "llm_configured": False,
        "basics_count": 0,
        "enabled_real_sources": [],
        "enabled_llm_count": 0,
        "overall_ready": False,
        "next_step": "configure_datasource",
        "next_step_message": "Please configure the data source first",
        "next_step_redirect": "/settings/config",
        "next_step_tab": "datasource",
    }

    try:
        # ── JD Cloud version specialization: environment variables have been injected into the configuration and are directly considered ready. ──
        if is_jdyun_mode():
            readiness["datasource_configured"] = True
            readiness["llm_configured"] = True
            readiness["enabled_real_sources"] = ["tushare", "akshare"]
            readiness["enabled_llm_count"] = 1
            # Still need to check underlying data sync
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            basics_count = await db["stock_basic_info"].count_documents({})
            readiness["basics_count"] = basics_count
            readiness["basics_synced"] = basics_count > 0

            # JD Cloud Edition only cares about synchronization status
            if not readiness["basics_synced"]:
                readiness["next_step"] = "sync_data"
                readiness["next_step_message"] = "Please synchronize basic stock data"
                readiness["next_step_redirect"] = "/settings/sync"
                readiness["next_step_tab"] = ""
            else:
                readiness["overall_ready"] = True
                readiness["next_step"] = "ready"
                readiness["next_step_message"] = "The system is ready to start analysis"
                readiness["next_step_redirect"] = "/analysis/single"
                readiness["next_step_tab"] = ""

            # Jingdong cloud version additional mark, front-end identifiable
            readiness["jdyun_mode"] = True
            return readiness

        # ── 1. Check data source configuration ──
        from app.services.config_service import config_service
        config = await config_service.get_system_config()

        enabled_real_sources = []
        if config and config.data_source_configs:
            for ds in config.data_source_configs:
                if ds.enabled and ds.type not in _CACHE_SOURCE_TYPES:
                    enabled_real_sources.append(ds.type)

        readiness["enabled_real_sources"] = enabled_real_sources
        readiness["datasource_configured"] = len(enabled_real_sources) > 0

        # ── 2. Check LLM configuration ──
        enabled_llms = []
        if config and config.llm_configs:
            enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
        readiness["enabled_llm_count"] = len(enabled_llms)
        readiness["llm_configured"] = len(enabled_llms) > 0

        # ── 3. Check basic data synchronization ──
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        basics_count = await db["stock_basic_info"].count_documents({})
        readiness["basics_count"] = basics_count
        readiness["basics_synced"] = basics_count > 0

        # ── 4. Calculate overall readiness and recommended next steps ──
        if not readiness["datasource_configured"]:
            readiness["next_step"] = "configure_datasource"
            readiness["next_step_message"] = "Step 1: Please configure the data source first"
            readiness["next_step_redirect"] = "/settings/config"
            readiness["next_step_tab"] = "datasource"
        elif not readiness["llm_configured"]:
            readiness["next_step"] = "configure_llm"
            readiness["next_step_message"] = "Step 2: Please configure the large language model (LLM)"
            readiness["next_step_redirect"] = "/settings/config"
            readiness["next_step_tab"] = "llm"
        elif not readiness["basics_synced"]:
            readiness["next_step"] = "sync_data"
            readiness["next_step_message"] = "Step 3: Please synchronize basic stock data"
            readiness["next_step_redirect"] = "/settings/sync"
            readiness["next_step_tab"] = ""
        else:
            readiness["overall_ready"] = True
            readiness["next_step"] = "ready"
            readiness["next_step_message"] = "The system is ready to start analysis"
            readiness["next_step_redirect"] = "/analysis/single"
            readiness["next_step_tab"] = ""

        return readiness
    except Exception as e:
        logger.error(f"❌ System readiness check failed: {e}", exc_info=True)
        # Return not ready status when an error occurs to avoid misleading users
        readiness["next_step"] = "error"
        readiness["next_step_message"] = f"Readiness check failed: {e}"
        return readiness

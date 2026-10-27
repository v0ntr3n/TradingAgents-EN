"""
Capability Index REST API (View Status + Rebuild the index)
"""
import logging
from fastapi import APIRouter, Depends

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from app.services.capability_index_service import CapabilityIndexService

router = APIRouter()
logger = logging.getLogger("webapi.capability_index")


@router.get("/capability-index/state")
async def get_capability_index_state(user: dict = Depends(get_current_user)):
    """Get the current status of the capability index"""
    svc = CapabilityIndexService(get_mongo_db())
    state = await svc.get_index_state()
    return ok(data=state, message="ok")


@router.post("/capability-index/rebuild")
async def rebuild_capability_index(user: dict = Depends(get_current_user)):
    """Forcibly rebuild the capability index (a valid Embedding API Key needs to be configured first)"""
    svc = CapabilityIndexService(get_mongo_db())
    result = await svc.rebuild_index()
    return ok(
        data={
            "sync_mode": result.sync_mode,
            "total_documents": result.total_documents,
            "indexed_documents": result.indexed_documents,
            "skipped_documents": result.skipped_documents,
            "vector_backend": result.vector_backend,
        },
        message="Capability index reconstruction completed" if result.indexed_documents > 0 else "Capability index skipped (Embedding API not available)",
    )

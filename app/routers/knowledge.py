"""
Financial knowledge base management API

Provides CRUD, semantic search, batch initialization and other interfaces for knowledge documents.
Underlying uses FinancialKnowledgeManager(Qdrant + Embedding) . 
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ============================================================
# Request/response model
# ============================================================


class KnowledgeDocRequest(BaseModel):
    """Create/update knowledge document request"""
    id: str = Field(..., description="The unique identifier of the document, such as concept_sector_system")
    category: str = Field(..., description="Classification: concept / tool_guide / methodology / pattern")
    title: str = Field(..., description="Title")
    content: str = Field(..., description="knowledge content")
    tags: List[str] = Field(default_factory=list, description="tag list")
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10, the smaller the higher")


class KnowledgeDocResponse(BaseModel):
    """Knowledge Document Response"""
    id: str
    category: str
    title: str
    content: str
    tags: List[str] = []
    priority: int = 5
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SearchRequest(BaseModel):
    """Semantic search requests"""
    query: str = Field(..., description="Search text")
    top_k: int = Field(default=3, ge=1, le=20, description="Number of results returned")
    category: Optional[str] = Field(default=None, description="Optional category filtering")


class SearchResultItem(BaseModel):
    """Search result items"""
    doc_id: str
    title: str
    content: str
    category: str
    similarity: float
    tags: List[str] = []


class StatsResponse(BaseModel):
    """Statistics response"""
    available: bool
    collection_name: str
    total_documents: int
    backend: str


class InitRequest(BaseModel):
    """Initialization request"""
    reset: bool = Field(default=False, description="Whether to clear and then refill")


# ============================================================
# Helper function
# ============================================================


def _get_km(db=None):
    """Get FinancialKnowledgeManager instance"""
    from core.knowledge import FinancialKnowledgeManager
    return FinancialKnowledgeManager(db=db)


# ============================================================
# API routing
# ============================================================


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    """Get knowledge base statistics"""
    km = _get_km(db=db)
    stats = km.get_stats()
    return StatsResponse(**stats)


@router.post("/search", response_model=List[SearchResultItem])
async def search_knowledge(
    req: SearchRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Semantic search knowledge documents"""
    km = _get_km(db=db)
    if not km.available:
        raise HTTPException(status_code=503, detail="Knowledge base is not available, please check the vector database and Embedding configuration")

    snippets = km.search(query=req.query, top_k=req.top_k, category=req.category)
    return [
        SearchResultItem(
            doc_id=s.doc_id,
            title=s.title,
            content=s.content,
            category=s.category,
            similarity=round(s.similarity, 4),
            tags=s.tags,
        )
        for s in snippets
    ]


@router.post("/documents", response_model=Dict[str, Any])
async def add_document(
    req: KnowledgeDocRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Add a single knowledge document (idempotent, the same ID will be overwritten)"""
    km = _get_km(db=db)
    if not km.available:
        raise HTTPException(status_code=503, detail="Knowledge base is unavailable")

    from core.knowledge.financial_knowledge_manager import KnowledgeDocument
    doc = KnowledgeDocument(
        id=req.id,
        category=req.category,
        title=req.title,
        content=req.content,
        tags=req.tags,
        priority=req.priority,
    )
    ok = km.add_knowledge(doc)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add knowledge document, please check Embedding service")
    return {"success": True, "id": req.id, "message": f"knowledge document '{req.title}' Added"}


@router.post("/documents/batch", response_model=Dict[str, Any])
async def add_documents_batch(
    docs: List[KnowledgeDocRequest],
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Add knowledge documents in batches"""
    km = _get_km(db=db)
    if not km.available:
        raise HTTPException(status_code=503, detail="Knowledge base is unavailable")

    from core.knowledge.financial_knowledge_manager import KnowledgeDocument
    doc_objects = [
        KnowledgeDocument(
            id=d.id, category=d.category, title=d.title,
            content=d.content, tags=d.tags, priority=d.priority,
        )
        for d in docs
    ]
    success = km.add_knowledge_batch(doc_objects)
    return {
        "success": True,
        "total": len(docs),
        "added": success,
        "failed": len(docs) - success,
    }


@router.post("/init", response_model=Dict[str, Any])
async def init_knowledge_base(
    req: InitRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Initialize the knowledge base using built-in knowledge data.

    - reset=false: Incremental mode (skip existing ones)
    - reset=true: Empty and refill
    """
    km = _get_km(db=db)
    if not km.available:
        raise HTTPException(status_code=503, detail="Knowledge base is not available, please check the vector database and Embedding configuration")

    if req.reset:
        km.clear_all()
        logger.info("🔄 [knowledge base API] Knowledge base cleared")

    from core.knowledge.knowledge_data import get_all_knowledge_documents
    from core.knowledge.financial_knowledge_manager import KnowledgeDocument

    all_docs_raw = get_all_knowledge_documents()
    docs = [KnowledgeDocument.from_dict(d) for d in all_docs_raw]
    success = km.add_knowledge_batch(docs)

    return {
        "success": True,
        "reset": req.reset,
        "total": len(docs),
        "added": success,
        "failed": len(docs) - success,
        "total_in_store": km.get_count(),
    }


@router.delete("/documents/{doc_id}", response_model=Dict[str, Any])
async def delete_document(
    doc_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Delete a single knowledge document (via doc_id).

    Note: The current Qdrant adapter does not support deleting a single document by ID.
    To delete please use /init?reset=true Reinitialize.
    """
    # Qdrant What you need to know about delete in local mode point UUID
    # Currently VectorStoreInterface does not have a delete_by_id method
    # Provide a placeholder interface that can be expanded later
    raise HTTPException(
        status_code=501,
        detail="Single deletion has not been implemented yet. Please use POST /api/knowledge/init (reset=true) Reinitialize the knowledge base."
    )


@router.delete("/all", response_model=Dict[str, Any])
async def clear_all(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Clear all knowledge documents"""
    km = _get_km(db=db)
    if not km.available:
        raise HTTPException(status_code=503, detail="Knowledge base is unavailable")

    ok = km.clear_all()
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to clear knowledge base")
    return {"success": True, "message": "Knowledge base has been cleared", "total_in_store": km.get_count()}


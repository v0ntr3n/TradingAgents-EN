import hashlib
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.capability_index import (
    CapabilityDocument,
    CapabilityIndexSyncResult,
    CapabilitySearchHit,
)
from core.agents.config import AgentMaintenanceStatus, BUILTIN_AGENTS
from core.llm.embedding_manager import EmbeddingManager
from core.memory.memory_manager import VectorStoreManager
from core.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)

CAPABILITY_INDEX_COLLECTION = "capability_registry"
CAPABILITY_INDEX_STATE_COLLECTION = "capability_index_state"
CAPABILITY_INDEX_STATE_KEY = "default"
CAPABILITY_INDEX_TOP_K = 24


class CapabilityIndexService:
    """Unified capability index service."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._embedding_manager = EmbeddingManager(db=db)
        self._vector_store_manager = VectorStoreManager()
        self._collection = None
        self._cached_documents: Dict[str, CapabilityDocument] = {}

    async def ensure_index(self, force: bool = False) -> CapabilityIndexSyncResult:
        documents, fingerprint, document_hashes = await self._collect_source_documents()
        state = await self._load_state()
        current_fingerprint = str(state.get("fingerprint") or "") if state else ""
        collection_count = int(state.get("indexed_documents") or 0) if state else 0
        previous_hashes = state.get("document_hashes") or {} if state else {}

        if not force and current_fingerprint == fingerprint and collection_count > 0:
            self._cached_documents = {doc.capability_id: doc for doc in documents}
            logger.info(
                "[CapabilityIndex] 📦 Index already exists, fingerprint matches, build skipped"
                " (%d tools / %d indexed / backends: %s) ",
                len(documents), collection_count, self._vector_store_manager.backend,
            )
            return CapabilityIndexSyncResult(
                collection_name=CAPABILITY_INDEX_COLLECTION,
                fingerprint=fingerprint,
                total_documents=len(documents),
                indexed_documents=collection_count,
                skipped_documents=max(len(documents) - collection_count, 0),
                vector_backend=self._vector_store_manager.backend,
                sync_mode="no_change",
            )

        # Check if embedding model is available
        config = self._embedding_manager.get_config()
        if not config.get("has_provider"):
            logger.warning(
                "[CapabilityIndex] ⚠️ The embedding model is not configured and index construction is skipped."
                " (%d tool will use keyword matching fallback)",
                len(documents),
            )
            self._cached_documents = {doc.capability_id: doc for doc in documents}
            return CapabilityIndexSyncResult(
                collection_name=CAPABILITY_INDEX_COLLECTION,
                fingerprint=fingerprint,
                total_documents=len(documents),
                indexed_documents=0,
                skipped_documents=len(documents),
                vector_backend=self._vector_store_manager.backend,
                sync_mode="skipped_no_embedding",
            )

        if force or not previous_hashes:
            # Pre-check: first test whether the first embedding call is successful
            # If the API Key is invalid or the network is unavailable, skip quickly to avoid long timeouts.
            test_embedding, _ = self._embedding_manager.get_embedding("test")
            if test_embedding is None:
                logger.warning(
                    "[CapabilityIndex] ⚠️ Embedding API Not available, skip index building"
                    " (%d tool will use keyword matching fallback)",
                    len(documents),
                )
                self._cached_documents = {doc.capability_id: doc for doc in documents}
                return CapabilityIndexSyncResult(
                    collection_name=CAPABILITY_INDEX_COLLECTION,
                    fingerprint=fingerprint,
                    total_documents=len(documents),
                    indexed_documents=0,
                    skipped_documents=len(documents),
                    vector_backend=self._vector_store_manager.backend,
                    sync_mode="skipped_embedding_unavailable",
                )
            logger.info(
                "[CapabilityIndex] 🔄 Starting index building (%d tools, vector dimensions: %d) ...",
                len(documents), self._embedding_manager.get_embedding_dimension(),
            )
            result = await asyncio.to_thread(self._rebuild_index, documents, fingerprint)
        else:
            logger.info(
                "[CapabilityIndex] 🔄 Incremental synchronization of indexes (%d tools, %d existing indexes)...",
                len(documents), collection_count,
            )
            result = await asyncio.to_thread(
                self._sync_index_incrementally,
                documents=documents,
                fingerprint=fingerprint,
                document_hashes=document_hashes,
                previous_hashes=previous_hashes,
                expected_count=collection_count,
            )

        await self._save_state(result, document_hashes)
        self._cached_documents = {doc.capability_id: doc for doc in documents}
        logger.info(
            "[CapabilityIndex] ✅ index ready: %d/%d Indexed, %d skipped, pattern: %s",
            result.indexed_documents, result.total_documents,
            result.skipped_documents, result.sync_mode,
        )
        return result

    async def search_capabilities(
        self,
        query: str,
        top_k: int = CAPABILITY_INDEX_TOP_K,
        bindable_only: bool = False,
        source_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> List[CapabilitySearchHit]:
        await self.ensure_index()
        documents = list(self._cached_documents.values())
        if not documents:
            return []

        allowed_sources = set(source_types or [])
        allowed_categories = set(categories or [])
        filtered_documents = [
            doc for doc in documents
            if (not bindable_only or doc.bindable)
            and (not allowed_sources or doc.source_type in allowed_sources)
            and (not allowed_categories or doc.category in allowed_categories)
        ]
        if not filtered_documents:
            return []

        hits = self._vector_search(query, top_k=max(top_k * 4, top_k))
        search_method = "vector"
        if not hits:
            hits = self._lexical_search(query, filtered_documents, top_k=max(top_k * 4, top_k))
            search_method = "lexical"

        filtered: List[CapabilitySearchHit] = []
        allowed_ids = {doc.capability_id for doc in filtered_documents}
        for hit in hits:
            capability = hit.capability
            if capability.capability_id not in allowed_ids:
                continue
            filtered.append(hit)
            if len(filtered) >= top_k:
                break

        if len(filtered) < top_k and hits:
            lexical_hits = self._lexical_search(query, filtered_documents, top_k=max(top_k * 2, top_k))
            seen_ids = {hit.capability.capability_id for hit in filtered}
            for hit in lexical_hits:
                if hit.capability.capability_id in seen_ids:
                    continue
                filtered.append(hit)
                if len(filtered) >= top_k:
                    break
        logger.debug(
            "[CapabilityIndex] search method=%s query_len=%d results=%d top3=%s",
            search_method,
            len(query),
            len(filtered),
            [(h.capability.capability_id, round(float(h.score or 0), 3)) for h in filtered[:3]],
        )
        return filtered

    async def list_capabilities(self) -> List[CapabilityDocument]:
        await self.ensure_index()
        return list(self._cached_documents.values())

    async def rebuild_index(self) -> CapabilityIndexSyncResult:
        return await self.ensure_index(force=True)

    @staticmethod
    async def refresh_after_change(db) -> None:
        """Trigger index synchronization after tool changes (delete/add/modify) to clean up ghost tools.

        Incremental synchronization automatically detects and deletes tool vectors that no longer exist.
        No exceptions are thrown, only logs are logged on failure——The allowed_ids filtering when searching will give you a clue.
        """
        try:
            service = CapabilityIndexService(db)
            result = await service.ensure_index()
            logger.info(
                "[CapabilityIndex] Synchronization completed after tool change: mode=%s, total=%d, indexed=%d",
                result.sync_mode, result.total_documents, result.indexed_documents,
            )
        except Exception as e:
            logger.warning(f"[CapabilityIndex] Synchronization failed after tool change: {e}")

    async def get_index_state(self) -> Dict[str, Any]:
        state = await self._load_state()
        return state or {}

    async def _collect_source_documents(self) -> Tuple[List[CapabilityDocument], str, Dict[str, str]]:
        registry_docs = self._build_registry_documents()
        await self._merge_skills_documents(registry_docs)
        await self._merge_external_skills_documents(registry_docs)
        await self._merge_agents_documents(registry_docs)  # 🔥 v3.0: Agent Incorporate into unified capability index (including DB customization)

        documents = sorted(registry_docs.values(), key=lambda item: (item.source_type, item.capability_id))
        payload = [
            {
                "capability_id": doc.capability_id,
                "registry_tool_id": doc.registry_tool_id,
                "source_type": doc.source_type,
                "status": doc.status,
                "bindable": doc.bindable,
                "fc_enabled": doc.fc_enabled,
                "category": doc.category,
                "name": doc.name,
                "description": doc.description,
                "when_to_use": doc.when_to_use,
                "when_not_to_use": doc.when_not_to_use,
                "returns": doc.returns,
                "related_tools": doc.related_tools,
                "coverage_terms": doc.coverage_terms,
                "retrieval_text": doc.retrieval_text,
                "data_source": doc.data_source,
                "capability_tags": doc.capability_tags,
                "tool_role_hint": doc.tool_role_hint,
                "output_shape": doc.output_shape,
                "preferred_for": doc.preferred_for,
                "not_replacement_for": doc.not_replacement_for,
            }
            for doc in documents
        ]
        fingerprint = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        document_hashes = {
            doc.capability_id: hashlib.sha1(
                json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            for doc in documents
        }
        return documents, fingerprint, document_hashes

    def _build_registry_documents(self) -> Dict[str, CapabilityDocument]:
        registry = get_tool_registry()
        documents: Dict[str, CapabilityDocument] = {}
        for tool in registry.list_all():
            tool_id = str(tool.id or "").strip()
            if not tool_id:
                continue
            source_type = "mcp_tool" if str(tool.category) == "mcp" else "builtin_tool"
            coverage_terms = self._extract_coverage_terms(self._build_searchable_text(
                tool_id,
                str(tool.name or ""),
                str(tool.description or ""),
                str(tool.when_to_use or ""),
                str(tool.when_not_to_use or ""),
                str(tool.returns or ""),
                str(tool.data_source or ""),
                " ".join(tool.related_tools or []),
            ))
            doc = CapabilityDocument(
                capability_id=tool_id,
                registry_tool_id=tool_id,
                source_type=source_type,
                status="active",
                bindable=True,
                fc_enabled=bool(tool.fc_enabled),
                category=str(tool.category or ""),
                name=str(tool.name or tool_id),
                label=f"{tool_id} | {tool.name}",
                description=str(tool.description or ""),
                when_to_use=str(tool.when_to_use or ""),
                when_not_to_use=str(tool.when_not_to_use or ""),
                returns=str(tool.returns or ""),
                related_tools=[str(item) for item in (tool.related_tools or []) if str(item).strip()],
                coverage_terms=coverage_terms,
                retrieval_text=self._build_retrieval_text(
                    tool_id=tool_id,
                    name=str(tool.name or tool_id),
                    source_type=source_type,
                    category=str(tool.category or ""),
                    description=str(tool.description or ""),
                    when_to_use=str(tool.when_to_use or ""),
                    when_not_to_use=str(tool.when_not_to_use or ""),
                    returns=str(tool.returns or ""),
                    related_tools=[str(item) for item in (tool.related_tools or []) if str(item).strip()],
                    data_source=str(tool.data_source or ""),
                    coverage_terms=coverage_terms,
                    capability_tags=[str(item) for item in (tool.capability_tags or []) if str(item).strip()],
                    tool_role_hint=str(tool.tool_role_hint or ""),
                    output_shape=str(tool.output_shape or ""),
                    preferred_for=[str(item) for item in (tool.preferred_for or []) if str(item).strip()],
                    not_replacement_for=[str(item) for item in (tool.not_replacement_for or []) if str(item).strip()],
                ),
                data_source=str(tool.data_source or ""),
                capability_tags=[str(item) for item in (tool.capability_tags or []) if str(item).strip()],
                tool_role_hint=str(tool.tool_role_hint or ""),
                output_shape=str(tool.output_shape or ""),
                preferred_for=[str(item) for item in (tool.preferred_for or []) if str(item).strip()],
                not_replacement_for=[str(item) for item in (tool.not_replacement_for or []) if str(item).strip()],
                metadata={
                    "is_online": bool(tool.is_online),
                    "timeout_tier": str(tool.timeout_tier or ""),
                    "parameters": [p.model_dump(mode="json") for p in (tool.parameters or [])],
                },
            )
            documents[tool_id] = doc
        return documents

    async def _merge_skills_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        cursor = self._db.skills.find({"enabled": True})
        async for doc in cursor:
            skill_name = str(doc.get("name") or "").strip()
            if not skill_name:
                continue
            tool_id = skill_name.replace("-", "_")
            description = str(doc.get("description") or "").strip()
            implementation = doc.get("implementation")
            parameters = doc.get("parameters") or []
            bindable = bool(implementation and parameters and tool_id in documents)

            base = documents.get(tool_id)
            merged = self._merge_capability_document(
                base=base,
                capability_id=tool_id,
                registry_tool_id=tool_id if tool_id in documents else None,
                source_type="skill",
                status="active",
                bindable=bindable,
                fc_enabled=bool(base.fc_enabled) if base else True,
                category=str(doc.get("category") or getattr(base, "category", "utility") or "utility"),
                name=skill_name,
                label=(base.label if base else f"{tool_id} | {skill_name}"),
                description=description or (base.description if base else ""),
                when_to_use=str(doc.get("when_to_use") or getattr(base, "when_to_use", "") or ""),
                when_not_to_use=str(doc.get("when_not_to_use") or getattr(base, "when_not_to_use", "") or ""),
                returns=str(doc.get("returns") or getattr(base, "returns", "") or ""),
                related_tools=list(getattr(base, "related_tools", []) or []),
                data_source=str(doc.get("data_source") or getattr(base, "data_source", "") or ""),
                capability_tags=list(getattr(base, "capability_tags", []) or []),
                tool_role_hint=str(getattr(base, "tool_role_hint", "") or ""),
                output_shape=str(getattr(base, "output_shape", "") or ""),
                preferred_for=list(getattr(base, "preferred_for", []) or []),
                not_replacement_for=list(getattr(base, "not_replacement_for", []) or []),
                metadata={
                    **(base.metadata if base else {}),
                    "skill_type": doc.get("skill_type"),
                    "source_url": doc.get("source_url"),
                },
            )
            documents[tool_id] = merged

    async def _merge_external_skills_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        cursor = self._db.external_skills.find({"status": {"$in": ["active", "draft"]}})
        async for doc in cursor:
            tool_id = str(doc.get("tool_id") or "").strip()
            if not tool_id:
                continue
            status = str(doc.get("status") or "draft")
            display_name = str(doc.get("display_name") or tool_id).strip()
            description = str(doc.get("description") or "").strip()
            base = documents.get(tool_id)
            bindable = status == "active" and tool_id in documents
            metadata = dict(doc.get("metadata") or {})
            capability_tags = self._dedupe([
                *list(getattr(base, "capability_tags", []) or []),
                *[str(item) for item in (doc.get("capability_tags") or metadata.get("capability_tags") or []) if str(item).strip()],
            ])
            tool_role_hint = str(doc.get("tool_role_hint") or metadata.get("tool_role_hint") or getattr(base, "tool_role_hint", "") or "").strip()
            output_shape = str(doc.get("output_shape") or metadata.get("output_shape") or getattr(base, "output_shape", "") or "").strip()
            preferred_for = self._dedupe([
                *list(getattr(base, "preferred_for", []) or []),
                *[str(item) for item in (doc.get("preferred_for") or metadata.get("preferred_for") or []) if str(item).strip()],
            ])
            not_replacement_for = self._dedupe([
                *list(getattr(base, "not_replacement_for", []) or []),
                *[str(item) for item in (doc.get("not_replacement_for") or metadata.get("not_replacement_for") or []) if str(item).strip()],
            ])
            merged = self._merge_capability_document(
                base=base,
                capability_id=tool_id,
                registry_tool_id=tool_id if tool_id in documents else None,
                source_type="external_skill",
                status=status,
                bindable=bindable,
                fc_enabled=bool(base.fc_enabled) if base else True,
                category=str(doc.get("category") or getattr(base, "category", "external") or "external"),
                name=display_name,
                label=(base.label if base else f"{tool_id} | {display_name}"),
                description=description or (base.description if base else ""),
                when_to_use=str(doc.get("when_to_use") or getattr(base, "when_to_use", "") or ""),
                when_not_to_use=str(doc.get("when_not_to_use") or getattr(base, "when_not_to_use", "") or ""),
                returns=str(doc.get("returns") or getattr(base, "returns", "") or ""),
                related_tools=list(getattr(base, "related_tools", []) or []),
                data_source=str(doc.get("data_source") or getattr(base, "data_source", "") or ""),
                capability_tags=capability_tags,
                tool_role_hint=tool_role_hint,
                output_shape=output_shape,
                preferred_for=preferred_for,
                not_replacement_for=not_replacement_for,
                metadata={
                    **(base.metadata if base else {}),
                    "session_id": doc.get("session_id"),
                    "source": doc.get("source"),
                },
            )
            documents[tool_id] = merged

    async def _merge_agents_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        """
        will BUILTIN_AGENTS + MongoDB Custom Agent merged into capability index

        Each Agent serves as an independent capability item,source_type="agent". 
        The built-in only collects the MAINTAINED status, and the DB only collects enabled=True of.
        """
        before_count = len(documents)
        # ── 1. Built-in Agent ──
        builtin_added = 0
        for agent_id, meta in BUILTIN_AGENTS.items():
            status = meta.maintenance_status
            if status not in (AgentMaintenanceStatus.MAINTAINED,):
                logger.debug(
                    "[CapabilityIndex] skip Agent: %s (status=%s)",
                    agent_id, status.value if hasattr(status, 'value') else status,
                )
                continue
            self._add_agent_document(
                documents, agent_id,
                name=meta.name,
                description=meta.description or "",
                category=meta.category.value if hasattr(meta.category, 'value') else str(meta.category),
                default_tools=list(meta.default_tools) if meta.default_tools else [],
                inputs=[i.name for i in meta.inputs] if meta.inputs else [],
                outputs=[o.name for o in meta.outputs] if meta.outputs else [],
                output_field=meta.output_field or "",
                source="builtin",
            )
            builtin_added += 1

        logger.info(
            "[CapabilityIndex] 📥 Agent Documentation: %d built-in, Total documents before merge %d, After merger %d",
            builtin_added, before_count, len(documents),
        )

        # ── 2. MongoDB Customize Agent ──
        if self._db is not None:
            try:
                builtin_ids = {agent_id for agent_id, _ in BUILTIN_AGENTS.items()}
                cursor = self._db.agent_configs.find({"enabled": True})
                async for doc in cursor:
                    aid = doc.get("agent_id", "").strip()
                    if not aid or aid in builtin_ids:
                        continue
                    self._add_agent_document(
                        documents, aid,
                        name=doc.get("name", aid),
                        description=doc.get("description", ""),
                        category=doc.get("category", "custom"),
                        default_tools=doc.get("default_tools", []) or [],
                        inputs=doc.get("inputs", []) or [],
                        outputs=doc.get("outputs", []) or [],
                        output_field=doc.get("output_field", doc.get("report_label", "")) or "",
                        source="database",
                    )
                    logger.info(
                        f"📥 [CapabilityIndex] Indexed custom Agent: {aid} ({doc.get('name', '')})"
                    )
            except Exception as e:
                logger.warning(f"Loading custom Agent from MongoDB to index fails: {e}")

    def _add_agent_document(
        self, documents: Dict[str, CapabilityDocument],
        agent_id: str, name: str, description: str, category: str,
        default_tools: list, inputs: list, outputs: list,
        output_field: str, source: str,
    ) -> None:
        """Build and index a CapabilityDocument for a single Agent"""
        safe_inputs = self._safe_list_to_str(inputs)
        safe_outputs = self._safe_list_to_str(outputs)
        safe_tools = self._safe_list_to_str(default_tools)

        when_to_use_parts = []
        if safe_inputs:
            when_to_use_parts.append(f"需要的输入: {', '.join(safe_inputs)}")
        if safe_outputs:
            when_to_use_parts.append(f"产生的输出: {', '.join(safe_outputs)}")
        if safe_tools:
            when_to_use_parts.append(f"默认工具: {', '.join(safe_tools)}")
        if output_field:
            when_to_use_parts.append(f"产出字段: {output_field}")

        documents[agent_id] = self._merge_capability_document(
            base=None,
            capability_id=agent_id,
            registry_tool_id=None,
            source_type="agent",
            status="active",
            bindable=True,
            fc_enabled=False,
            category=category,
            name=name,
            label=f"{agent_id} | {name}",
            description=description,
            when_to_use="; ".join(when_to_use_parts) if when_to_use_parts else "",
            when_not_to_use="",
            returns="报告文本",
            related_tools=list(safe_tools),
            data_source=source,
            capability_tags=list(safe_tools),
            tool_role_hint="agent",
            output_shape="report",
            preferred_for=[],
            not_replacement_for=[],
            metadata={
                "agent_id": agent_id,
                "source": source,
                "output_field": output_field,
                "default_tools": list(safe_tools),
                "has_inputs": len(safe_inputs) > 0,
                "has_outputs": len(safe_outputs) > 0,
            },
        )

    @staticmethod
    def _safe_list_to_str(items: list) -> List[str]:
        """Safely convert a list to a list of strings, handling dict elements and non-list input"""
        if not items:
            return []
        if not isinstance(items, list):
            return [str(items)]
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Try to get common field names, if not, then str()
                for key in ("field", "name", "desc", "key", "label"):
                    if key in item:
                        result.append(str(item[key]))
                        break
                else:
                    result.append(str(item))
            else:
                result.append(str(item))
        return result

    def _merge_capability_document(
        self,
        base: Optional[CapabilityDocument],
        capability_id: str,
        registry_tool_id: Optional[str],
        source_type: str,
        status: str,
        bindable: bool,
        fc_enabled: bool,
        category: str,
        name: str,
        label: str,
        description: str,
        when_to_use: str,
        when_not_to_use: str,
        returns: str,
        related_tools: List[str],
        data_source: str,
        metadata: Dict[str, Any],
        capability_tags: Optional[List[str]] = None,
        tool_role_hint: str = "",
        output_shape: str = "",
        preferred_for: Optional[List[str]] = None,
        not_replacement_for: Optional[List[str]] = None,
    ) -> CapabilityDocument:
        searchable = self._build_searchable_text(
            capability_id,
            name,
            description,
            when_to_use,
            when_not_to_use,
            returns,
            data_source,
            " ".join(related_tools),
        )
        coverage_terms = self._extract_coverage_terms(searchable)
        return CapabilityDocument(
            capability_id=capability_id,
            registry_tool_id=registry_tool_id,
            source_type=source_type,
            status=status,
            bindable=bindable,
            fc_enabled=fc_enabled,
            category=category,
            name=name,
            label=label,
            description=description,
            when_to_use=when_to_use,
            when_not_to_use=when_not_to_use,
            returns=returns,
            related_tools=related_tools,
            coverage_terms=coverage_terms,
            retrieval_text=self._build_retrieval_text(
                tool_id=capability_id,
                name=name,
                source_type=source_type,
                category=category,
                description=description,
                when_to_use=when_to_use,
                when_not_to_use=when_not_to_use,
                returns=returns,
                related_tools=related_tools,
                data_source=data_source,
                coverage_terms=coverage_terms,
                capability_tags=capability_tags or [],
                tool_role_hint=tool_role_hint,
                output_shape=output_shape,
                preferred_for=preferred_for or [],
                not_replacement_for=not_replacement_for or [],
            ),
            data_source=data_source,
            capability_tags=self._dedupe([str(item) for item in (capability_tags or []) if str(item).strip()]),
            tool_role_hint=str(tool_role_hint or ""),
            output_shape=str(output_shape or ""),
            preferred_for=self._dedupe([str(item) for item in (preferred_for or []) if str(item).strip()]),
            not_replacement_for=self._dedupe([str(item) for item in (not_replacement_for or []) if str(item).strip()]),
            metadata=metadata,
        )

    def _build_retrieval_text(
        self,
        tool_id: str,
        name: str,
        source_type: str,
        category: str,
        description: str,
        when_to_use: str,
        when_not_to_use: str,
        returns: str,
        related_tools: List[str],
        data_source: str,
        coverage_terms: List[str],
        capability_tags: Optional[List[str]] = None,
        tool_role_hint: str = "",
        output_shape: str = "",
        preferred_for: Optional[List[str]] = None,
        not_replacement_for: Optional[List[str]] = None,
    ) -> str:
        parts = [
            f"tool_id: {tool_id}",
            f"name: {name}",
            f"source_type: {source_type}",
            f"category: {category}",
            f"description: {description}",
            f"when_to_use: {when_to_use}",
            f"when_not_to_use: {when_not_to_use}",
            f"returns: {returns}",
            f"related_tools: {' '.join(related_tools)}",
            f"data_source: {data_source}",
            f"coverage_terms: {' '.join(coverage_terms)}",
            f"capability_tags: {' '.join(capability_tags or [])}",
            f"tool_role_hint: {tool_role_hint}",
            f"output_shape: {output_shape}",
            f"preferred_for: {' '.join(preferred_for or [])}",
            f"not_replacement_for: {' '.join(not_replacement_for or [])}",
        ]
        return "\n".join(part for part in parts if part.strip())

    def _build_searchable_text(self, *parts: str) -> str:
        return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).lower()

    def _extract_coverage_terms(self, text: str) -> List[str]:
        import re

        searchable = str(text or "").lower()
        patterns = [
            # ── Valuation class ──
            (r"(?<![a-z0-9])(valuation|valuations)(?![a-z0-9])", "valuation"),
            (r"(?<![a-z0-9])dcf(?![a-z0-9])", "dcf"),
            (r"(?<![a-z0-9])pe(?![a-z0-9])|P/E ratio|pe_ttm|p/e", "pe"),
            (r"(?<![a-z0-9])pb(?![a-z0-9])|price to book ratio|pb_mrq", "pb"),
            (r"(?<![a-z0-9])peg(?![a-z0-9])", "peg"),
            (r"(?<![a-z0-9])ps(?![a-z0-9])", "ps"),
            (r"ev/?ebitda", "ev_ebitda"),
            (r"Comparable companies|Comparison with peers|peer comparison|peer", "peer_comparison"),
            (r"Valuation|Valuation|Pricing|target price|price range|Valuation range|relative valuation", "valuation_cn"),
            (r"growth|growth|Year-on-year revenue|Net profit year-on-year|cagr", "growth"),
            (r"cash flow|cashflow|fcf|ocf|operating cash flow|free cash flow", "cashflow"),
            (r"roe|roa|roic|Gross profit margin|net profit margin|profit margin|Profitability stability|capital efficiency|piotroski|altman|beneish", "quality"),
            (r"history|many years|annual report sequence|time series|trend|series", "historical_series"),
            (r"Quantile|percentile|Valuation quantile", "percentile"),
            (r"ma20|rsi14|rsi|kdj|macd|Technical indicators|technical", "technical"),
            # ── Asset Quality/Fundamental Risk ──
            (r"Accounts receivable|receivables|(?<![a-z0-9])dso(?![a-z0-9])|Aging|bad debts|bad_debt|Refund|Collection", "asset_quality_receivables"),
            (r"Inventory|inventory|(?<![a-z0-9])dio(?![a-z0-9])|inventory turnover|Falling price", "asset_quality_inventory"),
            (r"Asset quality|asset_quality|Asset impairment", "asset_quality"),
            (r"debt repayment|solvency|debt_to_equity|Asset-liability ratio|interest coverage|Interest protection|debt_structure|Interest-bearing liabilities", "solvency"),
            (r"Liquidity|liquidity|current_ratio|quick_ratio|current ratio|quick ratio|short term debt service", "liquidity"),
            (r"goodwill|goodwill|Impairment test|impairment", "goodwill"),
            (r"Bankruptcy|bankruptcy|ohlson|z_score|zscore|altman|beneish|mscore|oscore|Fraud|fraud|financial fraud|financial fraud|risk|risk_adjusted|risk_profile|risk_event|risk_flag", "risk"),
            # ── Cost of Capital / Risk Measurement / Portfolio / Attribution Analysis / Statistical Analysis ──
            (r"wacc|capm|cost_of_equity|cost_of_debt|discount rate|capital cost|weighted average cost of capital", "cost_of_capital"),
            (r"(?<![a-z0-9])beta(?![a-z0-9])|(?<![a-z0-9])alpha(?![a-z0-9])|sharpe|sortino|treynor|calmar|jensen|information_ratio|(?<![a-z0-9])var(?![a-z0-9])|cvar|volatility|Volatility|maximum drawdown|max_drawdown|downside|risk adjustment", "risk_metrics"),
            (r"portfolio|combination|efficient_frontier|monte_carlo|Monte Carlo|Markowitz|markowitz|optimal_weight|optimal weight|scenario_analysis|Scenario analysis", "portfolio"),
            (r"attribution|attribution|brinson|factor_attribution|sector_attribution", "attribution"),
            (r"correlation|cointegration|cointegration|regression|Return|normality|normal|stationarity|Smooth|(?<![a-z0-9])adf(?![a-z0-9])|garch|ewma|statistics|statistical", "statistics"),
            # ── Screening/Macro/Dividend/Chips/Volume and Price ──
            (r"screen|Filter|filter|filter|stock picking", "screening"),
            (r"macro|Macro|economic_cycle|business cycle|monetary|monetary environment|Merrill Lynch Clock|yield_curve|yield curve|prosperity|recession|recession|recovery|recovery|overheating|overheating|stagflation|stagflation", "macro"),
            (r"dividend|dividends|dividend|Bonus shares|bonus|dividend|Send for transfer|Dividend per share", "dividend"),
            (r"chip|chips|Profit ratio|average cost|Concentration", "chip_distribution"),
            (r"vwap|obv|turnover|turnover rate|Volume|Volume and price|volume_profile|Turnover|Main net inflow|capital flow|capital_flow|fund_flow", "volume_analysis"),
            # ── Technical Analysis Extension ──
            (r"pivot|support|resistance|pressure level|fibonacci|Fibonacci|pivot point|Neckline|trend line", "support_resistance"),
            (r"candlestick|k line|k line|chart_pattern|form|Head and shoulders|double top|double bottom|triangle|flag shape|Wedge|notch|Doji|hammer head", "chart_pattern"),
            # ── Bonds/Options/Event Research ──
            (r"bond|bonds|Duration|duration|Convexity|convexity|credit_spread|credit spread|national debt|corporate bonds|Convertible bonds", "bond"),
            (r"option|options|black_scholes|greeks|greek letters|delta|gamma|theta|vega|rho|implied_volatility|Implied volatility|exercise price|strike", "option"),
            (r"event_study|event study|event day|event driven|event_driven|Announcement event|regulatory events|event_timeline", "event_study"),
            # ── Financial Statements / ETFs / Insiders / Market Breadth / Securities Master Data ──
            (r"income_analysis|income statement|Revenue|Main business|main_business|income structure|cost analysis", "income_statement"),
            (r"financial_statement|financial statements|balance_sheet|balance sheet|financial_statements|fundamentals_unified|financial data", "financial_statements"),
            (r"(?<![a-z0-9])etf(?![a-z0-9])|Fund fundamentals", "etf_fundamentals"),
            (r"insider|insider|insiders|insider_sentiment|insider_transaction", "insider"),
            (r"market_breadth|market breadth|market_overview|Market overview|market_environment|market environment|market_cycle|market cycle|Number of stocks rising and falling|breadth|index_data|index data|sector_data|Sector data|sector_analysis|Sector analysis", "market_breadth"),
            (r"security_master|Securities master data|Listing status|stock_master|Securities information|exchange|Market value", "security_master"),
        ]
        matched: List[str] = []
        for pattern, normalized in patterns:
            if re.search(pattern, searchable):
                matched.append(normalized)
        return self._dedupe(matched)

    def _rebuild_index(
        self,
        documents: List[CapabilityDocument],
        fingerprint: str,
    ) -> CapabilityIndexSyncResult:
        try:
            self._vector_store_manager.delete_collection(CAPABILITY_INDEX_COLLECTION)
        except Exception:
            pass

        self._collection = self._vector_store_manager.get_or_create_collection(
            CAPABILITY_INDEX_COLLECTION,
            vector_size=self._embedding_manager.get_embedding_dimension(),
        )

        indexed = 0
        skipped = 0
        total = len(documents)
        batch_size = max(1, total // 10)  # Output progress every 10%
        consecutive_failures = 0  # 🔥 Continuous failure counter, if the threshold is exceeded, the remaining documents will be skipped
        max_consecutive_failures = 5
        for idx, document in enumerate(documents):
            embedding, provider = self._embedding_manager.get_embedding(document.retrieval_text)
            if embedding is None:
                skipped += 1
                consecutive_failures += 1
                # 🔥 If consecutive failures exceed the threshold, the remaining documents will be skipped to avoid long-term blocking.
                if consecutive_failures >= max_consecutive_failures:
                    remaining = total - idx - 1
                    logger.warning(
                        "[CapabilityIndex] ⚠️ %d consecutive failures, skipping remaining %d documents (Embedding API unavailable)",
                        consecutive_failures, remaining,
                    )
                    skipped += remaining
                    break
                continue
            consecutive_failures = 0  # Reset if successful
            metadata = document.model_dump(mode="json")
            metadata["embedding_provider"] = provider
            self._collection.add(
                documents=[document.retrieval_text],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[str(uuid.uuid5(uuid.NAMESPACE_DNS, document.capability_id))],
            )
            indexed += 1
            if indexed % batch_size == 0 or idx == total - 1:
                logger.info(
                    "[CapabilityIndex] Under construction... %d/%d (%d skip)",
                    indexed, total, skipped,
                )

        return CapabilityIndexSyncResult(
            collection_name=CAPABILITY_INDEX_COLLECTION,
            fingerprint=fingerprint,
            total_documents=len(documents),
            indexed_documents=indexed,
            skipped_documents=skipped,
            vector_backend=self._vector_store_manager.backend,
            sync_mode="full_rebuild",
        )

    def _sync_index_incrementally(
        self,
        documents: List[CapabilityDocument],
        fingerprint: str,
        document_hashes: Dict[str, str],
        previous_hashes: Dict[str, str],
        expected_count: int,
    ) -> CapabilityIndexSyncResult:
        self._collection = self._vector_store_manager.get_or_create_collection(
            CAPABILITY_INDEX_COLLECTION,
            vector_size=self._embedding_manager.get_embedding_dimension(),
        )

        current_count = self._collection.count()
        if expected_count > 0 and current_count == 0 and documents:
            logger.warning(
                "[CapabilityIndex] It is detected that the state exists but the vector set is empty, and the fallback is to full reconstruction.: expected=%s actual=%s",
                expected_count,
                current_count,
            )
            return self._rebuild_index(documents, fingerprint)

        docs_by_id = {doc.capability_id: doc for doc in documents}
        deleted_ids = sorted(set(previous_hashes.keys()) - set(document_hashes.keys()))
        changed_ids = sorted(
            capability_id
            for capability_id, doc_hash in document_hashes.items()
            if previous_hashes.get(capability_id) != doc_hash
        )

        deleted_count = 0
        if deleted_ids:
            point_ids = [self._build_point_id(capability_id) for capability_id in deleted_ids]
            if not self._collection.delete_ids(point_ids):
                logger.warning("[CapabilityIndex] Incremental deletion failed and fell back to full reconstruction.")
                return self._rebuild_index(documents, fingerprint)
            deleted_count = len(deleted_ids)

        upserted = 0
        skipped = 0
        consecutive_failures = 0  # 🔥 Continuous failure counter
        max_consecutive_failures = 5
        if changed_ids:
            upsert_documents: List[str] = []
            upsert_embeddings: List[List[float]] = []
            upsert_metadatas: List[Dict[str, Any]] = []
            upsert_ids: List[str] = []

            for capability_id in changed_ids:
                document = docs_by_id[capability_id]
                embedding, provider = self._embedding_manager.get_embedding(document.retrieval_text)
                if embedding is None:
                    skipped += 1
                    consecutive_failures += 1
                    # 🔥 If the continuous failure exceeds the threshold, the remaining change documents will be skipped.
                    if consecutive_failures >= max_consecutive_failures:
                        remaining = len(changed_ids) - len(upsert_ids) - skipped
                        logger.warning(
                            "[CapabilityIndex] ⚠️ Incremental sync failed %d times in a row, skipping remaining %d documents",
                            consecutive_failures, remaining,
                        )
                        skipped += remaining
                        break
                    continue
                consecutive_failures = 0  # Reset if successful
                metadata = document.model_dump(mode="json")
                metadata["embedding_provider"] = provider
                upsert_documents.append(document.retrieval_text)
                upsert_embeddings.append(embedding)
                upsert_metadatas.append(metadata)
                upsert_ids.append(self._build_point_id(document.capability_id))

            if upsert_ids and not self._collection.add(
                documents=upsert_documents,
                embeddings=upsert_embeddings,
                metadatas=upsert_metadatas,
                ids=upsert_ids,
            ):
                logger.warning("[CapabilityIndex] Incremental upsert fails and falls back to full rebuild")
                return self._rebuild_index(documents, fingerprint)
            upserted = len(upsert_ids)

        indexed_documents = self._collection.count()
        return CapabilityIndexSyncResult(
            collection_name=CAPABILITY_INDEX_COLLECTION,
            fingerprint=fingerprint,
            total_documents=len(documents),
            indexed_documents=indexed_documents,
            skipped_documents=skipped,
            vector_backend=self._vector_store_manager.backend,
            sync_mode="incremental_sync",
        )

    def _build_point_id(self, capability_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, capability_id))

    def _vector_search(self, query: str, top_k: int) -> List[CapabilitySearchHit]:
        if not query.strip():
            return []
        try:
            if self._collection is None:
                self._collection = self._vector_store_manager.get_or_create_collection(
                    CAPABILITY_INDEX_COLLECTION,
                    vector_size=self._embedding_manager.get_embedding_dimension(),
                )
            query_embedding, _provider = self._embedding_manager.get_embedding(query)
            if query_embedding is None:
                return []
            result = self._collection.query(query_embeddings=[query_embedding], n_results=top_k)
            hits: List[CapabilitySearchHit] = []
            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            for _doc_text, metadata, distance in zip(documents, metadatas, distances):
                capability = CapabilityDocument.model_validate(metadata)
                hits.append(CapabilitySearchHit(capability=capability, score=round(1.0 - float(distance), 4)))
            return hits
        except Exception as exc:
            logger.warning("[CapabilityIndex] Vector retrieval failed, fallback to lexical retrieval: %s", exc)
            return []

    def _lexical_search(
        self,
        query: str,
        documents: Iterable[CapabilityDocument],
        top_k: int,
    ) -> List[CapabilitySearchHit]:
        tokens = [token for token in self._tokenize(query) if token]
        scored: List[CapabilitySearchHit] = []
        for doc in documents:
            haystack = self._build_searchable_text(
                doc.capability_id,
                doc.name,
                doc.description,
                doc.when_to_use,
                doc.returns,
                " ".join(doc.coverage_terms),
                " ".join(doc.capability_tags),
                " ".join(doc.preferred_for),
            )
            score = 0.0
            for token in tokens:
                if token in haystack:
                    score += 1.0
            if score > 0:
                scored.append(CapabilitySearchHit(capability=doc, score=score / max(len(tokens), 1)))
        scored.sort(key=lambda item: (-item.score, item.capability.label))
        return scored[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        import re

        pieces = re.split(r"[^0-9A-Za-z\u4e00-\u9fff_]+", str(text or "").lower())
        return [piece for piece in pieces if piece and len(piece) > 1]

    def _dedupe(self, items: List[str]) -> List[str]:
        seen = set()
        results = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            results.append(item)
        return results

    async def _load_state(self) -> Optional[Dict[str, Any]]:
        return await self._db[CAPABILITY_INDEX_STATE_COLLECTION].find_one({"_id": CAPABILITY_INDEX_STATE_KEY})

    async def _save_state(self, result: CapabilityIndexSyncResult, document_hashes: Dict[str, str]) -> None:
        payload = result.model_dump(mode="json")
        payload["_id"] = CAPABILITY_INDEX_STATE_KEY
        payload["document_hashes"] = document_hashes
        await self._db[CAPABILITY_INDEX_STATE_COLLECTION].update_one(
            {"_id": CAPABILITY_INDEX_STATE_KEY},
            {"$set": payload},
            upsert=True,
        )

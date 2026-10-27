"""User Manual Vector Index Manager

Based on VectorStoreManager + EmbeddingManager Implement semantic retrieval of user manuals.
Troubleshooting Using Q&A Bots"The user asked the question in natural language and the manual title could not be matched."problem.

Features:
- Reuse existing Qdrant infrastructure (isomorphic with FinancialKnowledgeManager)
- Slice by Markdown title (first/second/third level title + text)
- Automatically detect manual mtime changes at startup and rebuild indexes as needed
- Automatic indexing in JD cloud mode jdyun-user-manual-v3.0.md
- Graceful degradation: when the vector library/embedding is unavailable, empty results are returned and startup is not blocked.
"""

import hashlib
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# User manual specific vector collection name (isolated from financial knowledge base)
USER_MANUAL_COLLECTION_NAME = "user_manual_v3"

# Slicing and retrieval parameters
DEFAULT_TOP_K = 5
DEFAULT_MAX_CHARS = 4000
MAX_SECTION_CHARS = 2000  # The maximum number of characters in a single slice, if exceeded, it will be truncated.
MIN_SECTION_CHARS = 50  # Slices smaller than this length are merged into the upper header


class ManualSection:
    """Manual slice data structure"""

    def __init__(
        self,
        section_id: str,
        title: str,
        content: str,
        level: int,
        manual_type: str,  # "standard" | "jdyun"
        manual_file: str,
        parent_title: str = "",
    ):
        self.section_id = section_id
        self.title = title
        self.content = content
        self.level = level
        self.manual_type = manual_type
        self.manual_file = manual_file
        self.parent_title = parent_title

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "level": self.level,
            "manual_type": self.manual_type,
            "manual_file": self.manual_file,
            "parent_title": self.parent_title,
        }


class ManualSearchResult:
    """Search results"""

    def __init__(
        self,
        section_id: str,
        title: str,
        content: str,
        manual_type: str,
        similarity: float,
        parent_title: str = "",
    ):
        self.section_id = section_id
        self.title = title
        self.content = content
        self.manual_type = manual_type
        self.similarity = similarity
        self.parent_title = parent_title

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "manual_type": self.manual_type,
            "similarity": round(self.similarity, 4),
            "parent_title": self.parent_title,
        }


def _is_jdyun_mode() -> bool:
    """Determine whether it is JD Cloud mode"""
    return os.environ.get("JDYUN_MODE", "false").lower() == "true"


def _resolve_manual_files() -> List[Tuple[str, str]]:
    """Return [(manual path, Manual type), ...], Sort by priority.

    JD Cloud mode: jdyun takes priority; standard mode: standard takes priority.
    Both modes index both manuals simultaneously (if present), allowing LLM to answer across versions.

    Search paths (by priority):
    1. Project root directory docs/02-user-guide/ (development environment)
    2. /app/docs/02-user-guide/ (Docker container, mount or docker cp)
    3. /app/runtime/docs/02-user-guide/ (Docker Container persistence volume)
    4. current working directory docs/02-user-guide/
    """
    # Candidate search directory
    candidate_dirs = []

    # 1. Deducing the project root directory (development environment) based on __file__
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    candidate_dirs.append(os.path.join(project_root, "docs", "02-user-guide"))

    # 2. Docker Common paths within containers
    candidate_dirs.append("/app/docs/02-user-guide")
    candidate_dirs.append("/app/runtime/docs/02-user-guide")

    # 3. Relative path to current working directory
    candidate_dirs.append(os.path.join(os.getcwd(), "docs", "02-user-guide"))

    # 🔥 Compatible with older tiled docs structures (historical portable/installer packages: user-manual-v3.0.md located directly under the docs/ root)
    candidate_dirs.append(os.path.join(project_root, "docs"))
    candidate_dirs.append("/app/docs")

    # Find the first directory that exists and contains a manual file (avoid selecting empty directories)
    user_guide_dir = None
    for d in candidate_dirs:
        if os.path.isdir(d) and (
            os.path.exists(os.path.join(d, "user-manual-v3.0.md"))
            or os.path.exists(os.path.join(d, "jdyun-user-manual-v3.0.md"))
        ):
            user_guide_dir = d
            break

    if not user_guide_dir:
        logger.warning(
            f"⚠️ [UserManualManager] User manual directory not found, tried: {candidate_dirs}"
        )
        return []

    standard_path = os.path.join(user_guide_dir, "user-manual-v3.0.md")
    jdyun_path = os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md")

    manuals: List[Tuple[str, str]] = []
    if _is_jdyun_mode():
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
    else:
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
    return manuals


def _split_markdown_sections(content: str, manual_type: str, manual_file: str) -> List[ManualSection]:
    """Slice by Markdown header.

    Slicing strategy:
    - Split by headings 1-4
    - The body of each slice contains everything from the title to the next sibling or higher title.
       (That is, the H3 slice will contain the content of all H4 subtitles under it and will not be cut empty)
    - filtered short slices (< MIN_SECTION_CHARS) , Usually a placeholder or directory entry
    - Truncate slices that are too long (> MAX_SECTION_CHARS) , Avoid embeddings that are too long
    """
    sections: List[ManualSection] = []

    # 1. Use finditer to find all title positions (instead of re.split to avoid subtitles being cut away and causing the parent title body to be empty)
    heading_pattern = re.compile(r'^(#{1,4})\s+([^\n]+)$', re.MULTILINE)
    headings: List[Tuple[int, int, int, str]] = []  # [(start, end, level, title), ...]
    for m in heading_pattern.finditer(content):
        level = len(m.group(1))
        title = m.group(2).strip()
        headings.append((m.start(), m.end(), level, title))

    title_chain: List[Tuple[int, str]] = []  # [(level, title), ...]

    for i, (start, end, level, title) in enumerate(headings):
        # Maintain title chain and find parent title
        while title_chain and title_chain[-1][0] >= level:
            title_chain.pop()
        parent_title = title_chain[-1][1] if title_chain else ""
        title_chain.append((level, title))

        # Find the position of the next sibling or higher heading (body boundary)
        body_end = len(content)
        for j in range(i + 1, len(headings)):
            next_start, _, next_level, _ = headings[j]
            if next_level <= level:
                body_end = next_start
                break

        # Extract body (after the header row to body_end)
        body = content[end:body_end].strip()

        # Filter out short slices (usually placeholders or catalog items)
        if len(body) < MIN_SECTION_CHARS:
            continue

        # Truncate slices that are too long
        if len(body) > MAX_SECTION_CHARS:
            body = body[:MAX_SECTION_CHARS] + "\n\n...(Content has been truncated)"

        # Generate deterministic ID (for idempotent upsert)
        section_id_str = f"{manual_type}:{title}:{parent_title}"

        sections.append(ManualSection(
            section_id=section_id_str,  # Keep the original string as doc_id to facilitate deduplication
            title=title,
            content=body,
            level=level,
            manual_type=manual_type,
            manual_file=manual_file,
            parent_title=parent_title,
        ))

    return sections


class UserManualManager:
    """User Manual Vector Index Manager (Singleton)"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db=None):
        if self._initialized:
            return
        self._db = db
        self._embedding_manager = None
        self._collection = None
        self._available = False
        self._last_indexed_signature: Optional[str] = None  # Used for external query last index signature
        self._init_backend()
        UserManualManager._initialized = True

    # ----------------------------------------------------------
    # initialization
    # ----------------------------------------------------------

    def _init_backend(self):
        """Initialize the vector database and Embedding backend"""
        try:
            from core.llm.embedding_manager import EmbeddingManager
            from core.memory.memory_manager import VectorStoreManager

            self._embedding_manager = EmbeddingManager(db=self._db)
            vector_size = self._embedding_manager.get_embedding_dimension()

            vs_manager = VectorStoreManager()
            self._collection = vs_manager.get_or_create_collection(
                USER_MANUAL_COLLECTION_NAME, vector_size=vector_size
            )
            self._available = True
            logger.info(
                f"✅ [UserManualManager] Initialization successful "
                f"(collection: {USER_MANUAL_COLLECTION_NAME}, Dimensions: {vector_size})"
            )
        except Exception as e:
            logger.warning(f"⚠️ [UserManualManager] Initialization failed, user manual vector retrieval will not be available: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def reinit(self) -> bool:
        """Reinitialize the vector backend (embedding + vector collection).

        Applicable scenario: Embedding API Key is not configured/error causes initialization failure at startup
         (available=False) , The user can call this method after configuring the Key in the management interface.
        Resume vector retrieval without restarting the backend. EmbeddingManager will be rebuilt every time it is rebuilt
        Read latest configuration from database/environment variables.
        """
        try:
            self._embedding_manager = None
            self._collection = None
            self._init_backend()
            if self._available:
                logger.info("✅ [UserManualManager] Reinitialization successful, vector retrieval resumed")
                return True
            logger.warning("⚠️ [UserManualManager] Still unavailable after reinitialization")
            return False
        except Exception as e:
            logger.error(f"❌ [UserManualManager] Reinitialization failed: {e}", exc_info=True)
            self._available = False
            return False

    # ----------------------------------------------------------
    # Index building
    # ----------------------------------------------------------

    def _compute_manuals_signature(self, manuals: List[Tuple[str, str]]) -> str:
        """Compute manual file signatures (based on file content hashes) for change detection.

        The signature only depends on the file name + File content, independent of path and mtime,
        Ensure that different deployment environments (development/Docker/JD Cloud) generate the same signature,
        Enable pre-generated seed index data to be reused across environments.
        """
        sig_parts = []
        for path, manual_type in manuals:
            try:
                with open(path, "rb") as f:
                    content_hash = hashlib.md5(f.read()).hexdigest()
                sig_parts.append(f"{manual_type}:{os.path.basename(path)}:{content_hash}")
            except OSError:
                sig_parts.append(f"{manual_type}:{os.path.basename(path)}:missing")
        # sorted Ensure that different manual sequences produce the same signature
        return hashlib.md5("|".join(sorted(sig_parts)).encode("utf-8")).hexdigest()

    def _get_indexed_signature_from_meta(self) -> Optional[str]:
        """Read the last index signature from the Qdrant collection s metadata.

        We use a fixed point_id to store"Index meta information", Avoid traversing the entire collection.
        """
        if not self._available:
            return None
        try:
            # Try to read the signature point
            sig_point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "user_manual_index_signature"))
            results = self._collection.get(ids=[sig_point_id])
            if results and results.get("metadatas"):
                meta = results["metadatas"][0]
                if meta:
                    return meta.get("manuals_signature")
        except Exception as e:
            logger.debug(f"[UserManualManager] Failed to read index signature: {e}")
        return None

    def _save_indexed_signature(self, signature: str) -> None:
        """Write the current index signature into collection metadata"""
        if not self._available:
            return
        try:
            sig_point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "user_manual_index_signature"))
            # Qdrant It is required that the embedding is non-empty and uses an all-zero vector to occupy the position (this point does not participate in semantic retrieval)
            # But langchain's Qdrant wrapper requires embeddings, so use an empty string instead embedding
            # Here we use the metadata-only method: delete first and then add
            try:
                self._collection.delete(ids=[sig_point_id])
            except Exception:
                pass
            # Use a deterministic embedding (within the vector dimension) to allow the signature point to be stored in
            # In fact, when we use retrieve, we retrieve it by ID and will not use this embedding for similarity query.
            dim = self._embedding_manager.get_embedding_dimension()
            placeholder_embedding = [0.0] * dim
            self._collection.add(
                documents=["__INDEX_SIGNATURE__"],
                embeddings=[placeholder_embedding],
                metadatas=[{
                    "doc_id": "__INDEX_SIGNATURE__",
                    "title": "__INDEX_SIGNATURE__",
                    "manual_type": "meta",
                    "manuals_signature": signature,
                    "indexed_at": datetime.now().isoformat(),
                }],
                ids=[sig_point_id],
            )
        except Exception as e:
            logger.warning(f"⚠️ [UserManualManager] Failed to save index signature: {e}")

    def _clear_all_sections(self) -> bool:
        """Clear all manual slices (retain signature points)"""
        if not self._available:
            return False
        try:
            from core.memory.memory_manager import VectorStoreManager

            vs_manager = VectorStoreManager()
            vs_manager.delete_collection(USER_MANUAL_COLLECTION_NAME)

            vector_size = self._embedding_manager.get_embedding_dimension()
            self._collection = vs_manager.get_or_create_collection(
                USER_MANUAL_COLLECTION_NAME, vector_size=vector_size
            )
            logger.info("🗑️ [UserManualManager] Manual index collection cleared")
            return True
        except Exception as e:
            logger.error(f"❌ [UserManualManager] Failed to clear collection: {e}")
            return False

    def _index_section(self, section: ManualSection) -> bool:
        """Write a single manual slice to a vector library"""
        if not self._available:
            return False
        try:
            # Splicing embedding text: title + parent title + Text (improves semantic signals during retrieval)
            embed_text = section.title
            if section.parent_title:
                embed_text = f"{section.parent_title} > {section.title}\n\n{section.content}"
            else:
                embed_text = f"{section.title}\n\n{section.content}"

            embedding, provider = self._embedding_manager.get_embedding(embed_text)
            if embedding is None:
                logger.warning(f"⚠️ [UserManualManager] Unable to obtain embedding: {section.title}")
                return False

            metadata = {
                "doc_id": section.section_id,
                "title": section.title,
                "parent_title": section.parent_title,
                "manual_type": section.manual_type,
                "manual_file": os.path.basename(section.manual_file),
                "level": section.level,
                "provider": provider,
                "indexed_at": datetime.now().isoformat(),
            }

            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, section.section_id))
            self._collection.add(
                documents=[section.content],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[point_id],
            )
            return True
        except Exception as e:
            logger.error(f"❌ [UserManualManager] Index slicing failed ({section.title}): {e}")
            return False

    def ensure_indexed(self, force: bool = False) -> Dict[str, Any]:
        """Make sure the manual is indexed. Rebuild if the manual file changes or the collection is empty.

        Args:
            force: Force rebuild (ignore signature comparison)

        Returns:
            {
                "rebuilt": bool,         # Whether the index was rebuilt
                "skipped": bool,          # Whether to skip (signature consistent)
                "manuals_count": int,     # Number of indexed manuals
                "sections_count": int,    # Number of slices for the index
                "signature": str,         # current signature
                "error": str,             # Error message (if any)
            }
        """
        result = {
            "rebuilt": False,
            "skipped": False,
            "manuals_count": 0,
            "sections_count": 0,
            "signature": "",
            "error": "",
        }

        if not self._available:
            result["error"] = "Vector library/embedding is not available"
            return result

        manuals = _resolve_manual_files()
        if not manuals:
            result["error"] = "User manual file not found"
            return result

        current_signature = self._compute_manuals_signature(manuals)
        result["signature"] = current_signature
        result["manuals_count"] = len(manuals)

        # Signature comparison (in non-force mode)
        if not force:
            indexed_signature = self._get_indexed_signature_from_meta()
            current_count = self.get_count()
            if indexed_signature == current_signature and current_count > 1:
                logger.info(
                    f"📋 [UserManualManager] Manual unchanged, rebuild skipped "
                    f"(Signature consistent, indexed {current_count} slices)"
                )
                result["skipped"] = True
                result["sections_count"] = current_count
                self._last_indexed_signature = current_signature
                return result

        # Rebuild index
        logger.info(f"🔨 [UserManualManager] Start rebuilding manual index (force={force})")
        start_time = time.time()

        # Clear old index
        if not self._clear_all_sections():
            result["error"] = "Failed to clear old index"
            return result

        all_sections: List[ManualSection] = []
        for path, manual_type in manuals:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                sections = _split_markdown_sections(content, manual_type, path)
                all_sections.extend(sections)
                logger.info(f"📖 [UserManualManager] {manual_type} Manual slicing completed: {len(sections)} a ({os.path.basename(path)})")
            except Exception as e:
                logger.warning(f"⚠️ [UserManualManager] Failed to read manual {path}: {e}")

        if not all_sections:
            result["error"] = "slice is empty"
            return result

        # Batch index
        success_count = 0
        for section in all_sections:
            if self._index_section(section):
                success_count += 1

        # Save signature
        self._save_indexed_signature(current_signature)
        self._last_indexed_signature = current_signature

        elapsed = time.time() - start_time
        logger.info(
            f"✅ [UserManualManager] Index rebuild completed: "
            f"{success_count}/{len(all_sections)} slice, "
            f"Time consuming {elapsed:.1f}s, signature={current_signature[:8]}..."
        )

        result["rebuilt"] = True
        result["sections_count"] = success_count
        return result

    # ----------------------------------------------------------
    # Semantic retrieval
    # ----------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        manual_type: Optional[str] = None,
    ) -> List[ManualSearchResult]:
        """Semantic Search User Manual

        Args:
            query: User natural language issues
            top_k: Number of results returned
            manual_type: optional filter("standard" | "jdyun") 

        Returns:
            List of search results in descending order of similarity
        """
        if not self._available:
            return []

        try:
            query_embedding, provider = self._embedding_manager.get_embedding(query)
            if query_embedding is None:
                logger.warning("⚠️ [UserManualManager] Unable to get query embedding")
                return []

            count = self._collection.count()
            if count == 0:
                logger.debug("📭 [UserManualManager] Manual index is empty")
                return []

            top_k = min(top_k, count)

            # Build filter conditions (exclude signature points)
            where_clause = {"title": {"$ne": "__INDEX_SIGNATURE__"}}
            if manual_type:
                where_clause = {
                    "$and": [
                        {"title": {"$ne": "__INDEX_SIGNATURE__"}},
                        {"manual_type": manual_type},
                    ]
                }

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause,
            )

            search_results: List[ManualSearchResult] = []
            if results and "documents" in results and results["documents"]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for i, doc_text in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    dist = distances[i] if i < len(distances) else 1.0
                    similarity = 1.0 - dist

                    # Filter signature point (double insurance)
                    if meta.get("title") == "__INDEX_SIGNATURE__":
                        continue

                    search_results.append(ManualSearchResult(
                        section_id=meta.get("doc_id", ""),
                        title=meta.get("title", ""),
                        content=doc_text,
                        manual_type=meta.get("manual_type", ""),
                        similarity=similarity,
                        parent_title=meta.get("parent_title", ""),
                    ))

            logger.debug(
                f"🔍 [UserManualManager] Search completed: "
                f"query='{query[:30]}...', results={len(search_results)}, "
                f"top_sim={search_results[0].similarity:.3f}" if search_results else
                f"🔍 [UserManualManager] Search completed: query='{query[:30]}...', results=0"
            )
            return search_results

        except Exception as e:
            logger.error(f"❌ [UserManualManager] Retrieval failed: {e}")
            return []

    def get_count(self) -> int:
        """Get the number of indexed slices"""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.error(f"❌ [UserManualManager] Failed to get quantity: {e}")
            return 0

    def get_status(self) -> Dict[str, Any]:
        """Get index status (for use by health checks)"""
        return {
            "available": self._available,
            "collection": USER_MANUAL_COLLECTION_NAME,
            "sections_count": self.get_count(),
            "last_indexed_signature": self._last_indexed_signature,
        }

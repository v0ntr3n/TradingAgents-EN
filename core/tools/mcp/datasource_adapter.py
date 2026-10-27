"""
MCP data source adapter

Standardize the raw data returned by the data source class MCP tool and persist it to MongoDB.
Supports three-tier data processing strategy:
  1. structured + Field mapping → Write to existing/new collection
  2. No field mapping configuration   → Write the target collection as is (requires data_mapping to specify target_collection)
  3. None data_mapping  → Unstructured, written to the mcp_documents collection
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MCP_DOCUMENTS_COLLECTION = "mcp_documents"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MCPDatasourceAdapter:
    """
    MCP data source adapter

    Responsible for parsing, field mapping, and unit conversion of the original response (string) of the MCP tool.
    Then persist to MongoDB.
    """

    # ------------------------------------------------------------------
    # public interface
    # ------------------------------------------------------------------

    def adapt_and_persist(
        self,
        raw_result: str,
        tool_name: str,
        data_mapping: Optional[Dict],
        server_name: str,
    ) -> Optional[str]:
        """
        Parse raw_result, apply field mapping, write to MongoDB.

        Args:
            raw_result:   MCP call_tool The original string returned
            tool_name:    Tool name (for logging only)
            data_mapping: Entry from mcp_server_configs.data_mappings corresponding to tool_name
            server_name:  MCP Server name (write data_source identifier)

        Returns:
            The name of the target collection to be written, returned when writing fails None
        """
        if data_mapping is None:
            # No mapping configuration → unstructured processing
            self.persist_unstructured(raw_result, tool_name, server_name)
            return MCP_DOCUMENTS_COLLECTION

        target_collection = data_mapping.get("target_collection")
        if not target_collection:
            logger.warning(f"[MCP Adapter] data_mapping Missing target_collection, tools: {tool_name}")
            self.persist_unstructured(raw_result, tool_name, server_name)
            return MCP_DOCUMENTS_COLLECTION

        # Parse JSON data
        records = self._parse_result(raw_result)
        if not records:
            logger.info(f"[MCP Adapter] {tool_name} Return empty data and skip persistence")
            return target_collection

        # Apply field mapping and unit conversion (support field_mapping_list array format to achieve one source and multiple targets)
        field_mapping = data_mapping.get("field_mapping", {})
        field_mapping_list = data_mapping.get("field_mapping_list", [])
        if field_mapping_list:
            mapping_pairs = [
                (p.get("source") or p.get("key"), p.get("target") or p.get("value"))
                for p in field_mapping_list
                if (p.get("source") or p.get("key")) and (p.get("target") or p.get("value"))
            ]
        else:
            mapping_pairs = list(field_mapping.items())
        unit_conversion = data_mapping.get("unit_conversion", {})
        mapped_records = [
            self._map_record(record, mapping_pairs, unit_conversion, server_name)
            for record in records
        ]

        # write MongoDB
        self._write_to_collection(target_collection, mapped_records)
        logger.info(f"[MCP Adapter] {tool_name} → {target_collection}: {len(mapped_records)} 条记录")
        return target_collection

    def persist_unstructured(
        self,
        raw_result: str,
        tool_name: str,
        server_name: str,
        meta: Optional[Dict] = None,
    ) -> None:
        """
        Write unstructured data to the mcp_documents collection.

        Args:
            raw_result:  Original text content
            tool_name:   Tool name
            server_name: MCP Server name
            meta:        Additional metadata (such as stock_code, doc_type, etc.)
        """
        doc = {
            "server_name": server_name,
            "tool_name": tool_name,
            "content": raw_result,
            "doc_type": (meta or {}).get("doc_type", "raw"),
            "stock_code": (meta or {}).get("stock_code"),
            "tags": (meta or {}).get("tags", []),
            "created_at": _now_utc(),
        }
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            if db is not None:
                db[MCP_DOCUMENTS_COLLECTION].insert_one(doc)
                logger.info(f"[MCP Adapter] Unstructured data writing mcp_documents ({tool_name})")
        except Exception as e:
            logger.warning(f"[MCP Adapter] Writing to mcp_documents failed: {e}")

    # ------------------------------------------------------------------
    # internal tools
    # ------------------------------------------------------------------

    def _parse_result(self, raw_result: str) -> List[Dict]:
        """Try parsing raw_result into a list of records"""
        try:
            data = json.loads(raw_result)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Common structures:{"data": [...]} or {"records": [...]} Or directly a single record
                for key in ("data", "records", "result", "rows"):
                    if isinstance(data.get(key), list):
                        return data[key]
                return [data]  # single record
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def _map_record(
        self,
        record: Dict,
        mapping_pairs: List[tuple],
        unit_conversion: Dict[str, Dict],
        server_name: str,
    ) -> Dict:
        """Convert a single original record according to mapping rules. mapping_pairs is [(src, dst), ...], Support one source and multiple targets"""
        if not mapping_pairs:
            # No mapping rules, keep as is, only append data_source
            record["data_source"] = f"mcp:{server_name}"
            return record

        mapped: Dict[str, Any] = {}
        mapped_src_keys = set()
        for src_field, dst_field in mapping_pairs:
            if src_field in record:
                value = record[src_field]
                # Unit conversion
                conv = unit_conversion.get(src_field)
                if conv and isinstance(value, (int, float)):
                    factor = conv.get("factor", 1)
                    value = value * factor
                mapped[dst_field] = value
                mapped_src_keys.add(src_field)

        # Leave unmapped fields (extra_fields: preserve behavior)
        for k, v in record.items():
            if k not in mapped_src_keys:
                mapped[k] = v

        mapped["data_source"] = f"mcp:{server_name}"
        mapped["updated_at"] = _now_utc()
        return mapped

    def _write_to_collection(self, collection_name: str, records: List[Dict]) -> None:
        """Batch writing to MongoDB collections (upsert needs to be implemented by the caller through fields, here is insert_many)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            if db is not None:
                db[collection_name].insert_many(records, ordered=False)
        except Exception as e:
            logger.warning(f"[MCP Adapter] 写入集合 {collection_name} 失败: {e}")


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_adapter: Optional[MCPDatasourceAdapter] = None


def get_mcp_datasource_adapter() -> MCPDatasourceAdapter:
    """Get the MCPDatasourceAdapter global singleton"""
    global _adapter
    if _adapter is None:
        _adapter = MCPDatasourceAdapter()
    return _adapter


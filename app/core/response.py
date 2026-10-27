"""
Unified API response format tool
"""
from datetime import datetime
from typing import Any, Dict

from bson import ObjectId

from app.services.database.serialization import serialize_document
from app.utils.timezone import now_tz


def _serialize_response_data(data: Any) -> Any:
    """Convert common Mongo/Pydantic objects to JSON-safe structures."""
    if data is None or isinstance(data, (str, int, float, bool)):
        return data

    if isinstance(data, ObjectId):
        return str(data)

    if isinstance(data, datetime):
        return data.isoformat()

    if hasattr(data, "model_dump") and callable(data.model_dump):
        return _serialize_response_data(data.model_dump())

    if isinstance(data, dict):
        normalized = {
            key: _serialize_response_data(value)
            for key, value in data.items()
        }
        return serialize_document(normalized)

    if isinstance(data, (list, tuple, set)):
        return [_serialize_response_data(item) for item in data]

    return data


def ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    """Standard success response
    Return structure:{"success": True, "data": data, "message": message, "timestamp": ...}
    """
    return {
        "success": True,
        "data": _serialize_response_data(data),
        "message": message,
        "timestamp": now_tz().isoformat()
    }


def fail(message: str = "error", code: int = 500, data: Any = None) -> Dict[str, Any]:
    """Standard failure response (general errors are still recommended to be thrown with HTTPException, this function is used in business failure scenarios)"""
    return {
        "success": False,
        "data": _serialize_response_data(data),
        "message": message,
        "code": code,
        "timestamp": now_tz().isoformat()
    }


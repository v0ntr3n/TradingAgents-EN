"""
Operation log data model
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_serializer
from bson import ObjectId


class OperationLogCreate(BaseModel):
    """Create operation log request"""
    action_type: str = Field(..., description="Operation type")
    action: str = Field(..., description="Operation description")
    details: Optional[Dict[str, Any]] = Field(None, description="Details")
    success: bool = Field(True, description="Is it successful?")
    error_message: Optional[str] = Field(None, description="error message")
    duration_ms: Optional[int] = Field(None, description="Operation time consuming(milliseconds)")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="user agent")
    session_id: Optional[str] = Field(None, description="session ID")


class OperationLogResponse(BaseModel):
    """Operation log response"""
    id: str = Field(..., description="Log ID")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    action_type: str = Field(..., description="Operation type")
    action: str = Field(..., description="Operation description")
    details: Optional[Dict[str, Any]] = Field(None, description="Details")
    success: bool = Field(..., description="Is it successful?")
    error_message: Optional[str] = Field(None, description="error message")
    duration_ms: Optional[int] = Field(None, description="Operation time consuming(milliseconds)")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="user agent")
    session_id: Optional[str] = Field(None, description="session ID")
    timestamp: datetime = Field(..., description="Operating time")
    created_at: datetime = Field(..., description="creation time")

    @field_serializer('timestamp', 'created_at')
    def serialize_datetime(self, dt: datetime, _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class OperationLogQuery(BaseModel):
    """Operation log query parameters"""
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Quantity per page")
    start_date: Optional[str] = Field(None, description="start date")
    end_date: Optional[str] = Field(None, description="end date")
    action_type: Optional[str] = Field(None, description="Operation type")
    success: Optional[bool] = Field(None, description="Is it successful?")
    keyword: Optional[str] = Field(None, description="keyword search")
    user_id: Optional[str] = Field(None, description="User ID")


class OperationLogListResponse(BaseModel):
    """Operation log list response"""
    success: bool = Field(True, description="Is it successful?")
    data: Dict[str, Any] = Field(..., description="response data")
    message: str = Field("Operation successful", description="response message")


class OperationLogStats(BaseModel):
    """Operation log statistics"""
    total_logs: int = Field(..., description="Total number of logs")
    success_logs: int = Field(..., description="Number of successful logs")
    failed_logs: int = Field(..., description="Number of failed logs")
    success_rate: float = Field(..., description="success rate")
    action_type_distribution: Dict[str, int] = Field(..., description="Operation type distribution")
    hourly_distribution: List[Dict[str, Any]] = Field(..., description="Hourly distribution")


class OperationLogStatsResponse(BaseModel):
    """Operation log statistics response"""
    success: bool = Field(True, description="Is it successful?")
    data: OperationLogStats = Field(..., description="Statistics")
    message: str = Field("Obtaining statistics successfully", description="response message")


class ClearLogsRequest(BaseModel):
    """Clear log request"""
    days: Optional[int] = Field(None, description="Keep the logs of the last N days. If not uploaded, all logs will be cleared.")
    action_type: Optional[str] = Field(None, description="Only clear logs of specified types")


class ClearLogsResponse(BaseModel):
    """Clear log response"""
    success: bool = Field(True, description="Is it successful?")
    data: Dict[str, Any] = Field(..., description="Clear results")
    message: str = Field("Cleared log successfully", description="response message")


# Operation type constant
class ActionType:
    """Operation type constant"""
    STOCK_ANALYSIS = "stock_analysis"
    CONFIG_MANAGEMENT = "config_management"
    CACHE_OPERATION = "cache_operation"
    DATA_IMPORT = "data_import"
    DATA_EXPORT = "data_export"
    SYSTEM_SETTINGS = "system_settings"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_MANAGEMENT = "user_management"  # 🔧 Add user management operation type
    DATABASE_OPERATION = "database_operation"
    SCREENING = "screening"
    REPORT_GENERATION = "report_generation"


# Operation type mapping
ACTION_TYPE_NAMES = {
    ActionType.STOCK_ANALYSIS: "stock analysis",
    ActionType.CONFIG_MANAGEMENT: "Configuration management",
    ActionType.CACHE_OPERATION: "Caching operations",
    ActionType.DATA_IMPORT: "Data import",
    ActionType.DATA_EXPORT: "Data export",
    ActionType.SYSTEM_SETTINGS: "System settings",
    ActionType.USER_LOGIN: "User login",
    ActionType.USER_LOGOUT: "User logout",
    ActionType.USER_MANAGEMENT: "User management",  # 🔧 Add user management operation type name
    ActionType.DATABASE_OPERATION: "Database operations",
    ActionType.SCREENING: "stock screen",
    ActionType.REPORT_GENERATION: "Report generation",
}


def convert_objectid_to_str(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ObjectId in MongoDB document to string"""
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

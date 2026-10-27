"""
Email notification related data model
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.utils.timezone import now_tz


class EmailStatus(str, Enum):
    """Email sending status"""
    PENDING = "pending"      # To be sent
    SENDING = "sending"      # Sending
    SENT = "sent"           # Sent
    FAILED = "failed"       # Sending failed
    CANCELLED = "cancelled" # Canceled


class EmailType(str, Enum):
    """Email type"""
    SINGLE_ANALYSIS = "single_analysis"      # Single stock analysis results
    BATCH_ANALYSIS = "batch_analysis"        # Batch analysis summary
    SCHEDULED_ANALYSIS = "scheduled_analysis" # Regular analysis report
    IMPORTANT_SIGNAL = "important_signal"    # Important signal warning
    SYSTEM_NOTIFICATION = "system_notification" # System notification
    TEST_EMAIL = "test_email"                # test email


class EmailNotificationSettings(BaseModel):
    """Email notification settings"""
    enabled: bool = False                    # main switch
    email_address: Optional[str] = None      # Receiving email address (can be different from the registered email address)
    
    # Notification type switch
    single_analysis: bool = True             # Single stock analysis results
    batch_analysis: bool = True              # Batch analysis summary
    scheduled_analysis: bool = True          # Regular analysis report
    important_signals: bool = True           # Important signal warning
    system_notifications: bool = False       # System notification
    
    # Send time preference
    quiet_hours_enabled: bool = False        # Whether to enable do not disturb period
    quiet_hours_start: str = "22:00"         # Do not disturb start time
    quiet_hours_end: str = "08:00"           # Do not disturb end time
    
    # Email format preferences
    format: str = "html"                     # html / text
    include_charts: bool = False             # Whether to include charts (not supported yet)
    language: str = "zh"                     # Email language


class EmailRecord(BaseModel):
    """Email sending record"""
    id: Optional[str] = Field(default=None, alias="_id")
    
    # Basic information
    user_id: str
    to_email: str
    subject: str
    template_name: str
    
    # Email type
    email_type: EmailType
    
    # Linked data
    reference_id: Optional[str] = None   # Associated analysis report ID, etc.
    reference_type: Optional[str] = None # analysis_report/scheduled_task Wait
    
    # Send status
    status: EmailStatus = EmailStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    
    # Timestamp
    created_at: datetime = Field(default_factory=now_tz)
    sent_at: Optional[datetime] = None
    
    # error message
    error_message: Optional[str] = None
    
    # metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True


class EmailRecordCreate(BaseModel):
    """Create mail record request"""
    user_id: str
    to_email: str
    subject: str
    template_name: str
    email_type: EmailType
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmailSettingsUpdate(BaseModel):
    """Update mail settings request"""
    enabled: Optional[bool] = None
    email_address: Optional[str] = None
    single_analysis: Optional[bool] = None
    batch_analysis: Optional[bool] = None
    scheduled_analysis: Optional[bool] = None
    important_signals: Optional[bool] = None
    system_notifications: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    format: Optional[str] = None
    language: Optional[str] = None


class SMTPConfig(BaseModel):
    """SMTP Configuration"""
    host: str
    port: int = 587
    username: str
    password: str
    from_email: str
    from_name: str = "TradingAgents-CN"
    use_tls: bool = True
    use_ssl: bool = False


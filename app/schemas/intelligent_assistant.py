"""
Smart Assistant API request/response model
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Smart Assistant Conversation Request"""
    message: str = Field(..., description="User input issues")
    conversation_id: Optional[str] = Field(None, description="Session ID, reserved for multiple rounds of conversation")
    model: Optional[str] = Field(None, description="Inference model used uniformly by intelligent assistants")
    model_config_id: Optional[str] = Field(None, description="The model configuration ID used uniformly by the intelligent assistant, taking precedence over model")
    quick_model: Optional[str] = Field(None, description="Compatible with older versions: model used in quick conversation mode")
    deep_model: Optional[str] = Field(None, description="Compatible with older versions: models used in deep analysis mode")
    quick_model_config_id: Optional[str] = Field(None, description="Compatible with older versions: Quick conversation mode model configuration ID")
    deep_model_config_id: Optional[str] = Field(None, description="Compatible with older versions: Deep analysis mode model configuration ID")
    # Using Q&A bot fields (new in v3.0)
    assistant_role: str = Field("general", description="Assistant role:general=Universal Analysis Assistant (default)/ usage_helper=Use a Q&A bot")
    user_context: Optional[Dict[str, Any]] = Field(None, description="Frontend context (current route/mode tags, etc.), only used by usage_helper mode")


class ChatResponse(BaseModel):
    """Intelligent Assistant Conversation Response"""
    reply: str = Field(..., description="Assistant reply content")
    tools_used: List[str] = Field(default_factory=list, description="List of tools used in this reply")
    data_refs: Optional[List] = Field(None, description="Referenced data, reserved")
    conversation_id: Optional[str] = Field(None, description="The actual topic session used ID")


class PlannedAnalysisResponse(ChatResponse):
    """Plan analytics responses (extended from ChatResponse)"""
    plan: Optional[Dict[str, Any]] = Field(None, description="Executed analysis plan")
    step_results: Optional[List[Dict[str, Any]]] = Field(None, description="Execution results of each step")
    source: str = Field("llm_plan", description="Analysis source:seed_flow / llm_plan / react")
    supplemented: bool = Field(False, description="Whether a supplemental call was made")


class MessageItem(BaseModel):
    """Conversation message item"""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message content")
    tools_used: Optional[List[str]] = Field(None, description="List of tools used by the assistant")


class ConversationResponse(BaseModel):
    """Session history response"""
    messages: List[MessageItem] = Field(default_factory=list, description="Message list")
    conversation_id: Optional[str] = Field(None, description="Current topic session ID")


class AssistantThreadSummary(BaseModel):
    """Topic summary"""
    abstract: str = Field("", description="summary text")
    confirmed_facts: List[str] = Field(default_factory=list, description="Confirmed facts")
    open_questions: List[str] = Field(default_factory=list, description="Problems to be solved")
    next_actions: List[str] = Field(default_factory=list, description="Suggest next steps")
    focus_score: float = Field(0.0, description="focus score")


class AssistantThreadReportRef(BaseModel):
    """Topic linkage report reference"""
    ref_type: str = Field(..., description="Reference types such as stock_report / position_report / position_task")
    report_key: str = Field(..., description="Report unique key")
    source_collection: str = Field("", description="source collection")
    title: str = Field(..., description="Report title")
    symbol: Optional[str] = Field(None, description="Associated stock code")
    summary: str = Field("", description="Report Summary")
    status: Optional[str] = Field(None, description="Report status")
    task_id: Optional[str] = Field(None, description="Analysis tasks ID")
    analysis_id: Optional[str] = Field(None, description="Position analysis ID")
    created_at: Optional[str] = Field(None, description="Report creation time")
    linked_at: Optional[str] = Field(None, description="Time to mount to theme")


class AssistantThreadItem(BaseModel):
    """Assistant topic session"""
    thread_id: str = Field(..., description="topic session ID")
    title: str = Field(..., description="topic title")
    parent_thread_id: Optional[str] = Field(None, description="Parent topic ID")
    topic_type: str = Field("general", description="Topic type")
    pinned: bool = Field(False, description="Whether to pin it to the top")
    archived: bool = Field(False, description="File or not")
    message_count: int = Field(0, description="Number of messages")
    last_user_message: str = Field("", description="Last user message")
    updated_at: Optional[str] = Field(None, description="Update time")
    report_refs: List[AssistantThreadReportRef] = Field(default_factory=list, description="Associated report references")
    current_summary: Optional[AssistantThreadSummary] = Field(None, description="Current summary")


class AssistantThreadListResponse(BaseModel):
    """Topic conversation list response"""
    items: List[AssistantThreadItem] = Field(default_factory=list, description="Topic conversation list")
    total: int = Field(0, description="total")


class CreateAssistantThreadRequest(BaseModel):
    """Create topic session request"""
    title: Optional[str] = Field(None, description="topic title")
    parent_thread_id: Optional[str] = Field(None, description="Parent topic ID")


class AssistantThreadMessagesResponse(ConversationResponse):
    """Topic message list response"""
    thread: Optional[AssistantThreadItem] = Field(None, description="Topic information")


class ThreadSummarizeResponse(BaseModel):
    """Topic summary response"""
    conversation_id: str = Field(..., description="topic session ID")
    summary: AssistantThreadSummary = Field(..., description="Latest summary")


class ThreadDeleteResponse(BaseModel):
    """Topic deletion response"""
    success: bool = Field(True, description="Is deletion successful?")
    deleted_thread_ids: List[str] = Field(default_factory=list, description="List of deleted topic IDs")


class AssistantThreadReportDetail(BaseModel):
    """Topic linkage report details"""
    ref_type: str = Field(..., description="reference type")
    report_key: str = Field(..., description="Report unique key")
    title: str = Field(..., description="Report title")
    symbol: Optional[str] = Field(None, description="Stock code")
    status: Optional[str] = Field(None, description="Status")
    task_id: Optional[str] = Field(None, description="Task ID")
    analysis_id: Optional[str] = Field(None, description="analysis ID")
    created_at: Optional[str] = Field(None, description="Report creation time")
    linked_at: Optional[str] = Field(None, description="Mount time")
    content: str = Field("", description="Details text")
    content_format: str = Field("markdown", description="Text format")


class AssistantThreadReportDetailResponse(BaseModel):
    """Topic Association Report Details Response"""
    detail: AssistantThreadReportDetail = Field(..., description="Report details")


class AssistantThreadReportSearchResponse(BaseModel):
    """Topics can be associated with report search responses"""
    items: List[AssistantThreadReportRef] = Field(default_factory=list, description="List of reports that can be associated")
    total: int = Field(0, description="number of results")


class AssistantThreadAttachReportRequest(BaseModel):
    """Topic manually associates old report requests"""
    ref_type: str = Field(..., description="reference type")
    report_key: str = Field(..., description="Report unique key")


class AssistantThreadAttachReportResponse(BaseModel):
    """Topic manually associates old report responses"""
    success: bool = Field(True, description="Whether the association is successful")
    attached_ref: AssistantThreadReportRef = Field(..., description="Linked report references")

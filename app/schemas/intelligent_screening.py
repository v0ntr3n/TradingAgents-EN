"""
Smart filtering API response model

Request model reuse app.schemas.intelligent_assistant.ChatRequest
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class StockRecommendation(BaseModel):
    """Single recommended stocks"""
    code: str = Field(..., description="Stock code")
    name: str = Field("", description="Stock name")
    industry: str = Field("", description="Industry")
    price: Optional[float] = Field(None, description="current price")
    pe: Optional[float] = Field(None, description="P/E ratio")
    pe_display_label: Optional[str] = Field(None, description="PE Display labels such as PE / PE(TTM)")
    pb: Optional[float] = Field(None, description="price to book ratio")
    pb_display_label: Optional[str] = Field(None, description="PB Display labels such as PB / PB(MRQ)")
    roe: Optional[float] = Field(None, description="ROE(%)")
    roa: Optional[float] = Field(None, description="return on total assets(%)")
    gross_margin: Optional[float] = Field(None, description="Gross profit margin(%)")
    netprofit_margin: Optional[float] = Field(None, description="net profit margin(%)")
    dividend_yield: Optional[float] = Field(None, description="dividend yield(%)")
    debt_to_assets: Optional[float] = Field(None, description="Asset-liability ratio(%)")
    assets_to_eqt: Optional[float] = Field(None, description="equity multiplier")
    current_ratio: Optional[float] = Field(None, description="current ratio")
    quick_ratio: Optional[float] = Field(None, description="quick ratio")
    cash_ratio: Optional[float] = Field(None, description="cash ratio")
    revenue_ttm: Optional[float] = Field(None, description="Rolling 12-month revenue")
    net_profit_ttm: Optional[float] = Field(None, description="Rolling 12-month net profit")
    n_cashflow_act: Optional[float] = Field(None, description="Net operating cash flow")
    report_period: Optional[str] = Field(None, description="financial reporting period")
    pct_change: Optional[float] = Field(None, description="Increase or decrease(%)")
    reason: str = Field("", description="Reasons for recommendation")


class ScreeningChatResponse(BaseModel):
    """Intelligent filtering of conversation responses"""
    reply: str = Field(..., description="Assistant reply content (Markdown)")
    tools_used: List[str] = Field(default_factory=list, description="List of tools used")
    stocks: List[StockRecommendation] = Field(default_factory=list, description="Recommended stock list")
    phase: str = Field("result", description="current stage: confirmation=Requirements confirmation, planning=execution plan, result=Filter results")
    conversation_id: Optional[str] = Field(None, description="current session ID")
    is_fallback: bool = Field(False, description="Whether it is a downgrade candidate result (the result will be roughly screened by the database after LLM times out)")


class ScreeningMessageItem(BaseModel):
    """Filter conversation message items"""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message content")
    tools_used: Optional[List[str]] = Field(None, description="Tool list")
    stocks: Optional[List[StockRecommendation]] = Field(None, description="Recommended stocks")
    phase: Optional[str] = Field(None, description="stage mark: confirmation / planning / result")
    is_fallback: Optional[bool] = Field(None, description="Whether it is a downgrade candidate result")


class ScreeningConversationResponse(BaseModel):
    """Filter conversation history responses"""
    conversation_id: Optional[str] = Field(None, description="current session ID")
    messages: List[ScreeningMessageItem] = Field(default_factory=list)


class ScreeningConversationSummary(BaseModel):
    """Filter session summaries"""
    conversation_id: str = Field(..., description="session ID")
    title: str = Field("", description="Session title")
    preview: str = Field("", description="Summary of the latest message")
    message_count: int = Field(0, description="Number of messages")
    created_at: Optional[str] = Field(None, description="creation time")
    updated_at: Optional[str] = Field(None, description="Update time")


class ScreeningConversationListResponse(BaseModel):
    """Filter session list responses"""
    items: List[ScreeningConversationSummary] = Field(default_factory=list)


"""
Report saving tool module

Provides unified report saving logic for single stock analysis and workflow execution.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


def extract_reports_from_state(state: Any) -> Dict[str, str]:
    """
    Pull all reports from analysis status
    
    Args:
        state: Analysis state object (can be an AgentState object or dictionary)
        
    Returns:
        Report dictionary, the key is the report field name, the value is the report content
    """
    reports = {}
    
    # Define all possible report fields (preferred from structured_reports output by the engine)
    report_fields = []
    if isinstance(state, dict):
        structured_reports = state.get('structured_reports', {})
        if isinstance(structured_reports, dict) and structured_reports:
            report_fields = [
                field for field, entry in structured_reports.items()
                if isinstance(entry, dict) and entry.get("success") and entry.get("content")
            ]
    if not report_fields:
        # Fallback: Legacy hardcoded lists
        report_fields = [
            'index_report',
            'sector_report',
            'market_report',
            'sentiment_report',
            'news_report',
            'fundamentals_report',
            'chip_report',
            'investment_plan',
            'trader_investment_plan',
            'final_trade_decision'
        ]
    
    # Extract report content from state
    for field in report_fields:
        value = ""
        if hasattr(state, field):
            value = getattr(state, field, "")
        elif isinstance(state, dict) and field in state:
            value = state[field]
        
        if isinstance(value, str) and len(value.strip()) > 10:
            reports[field] = value.strip()
    
    # Handle research team debate status report
    debate_state = None
    if hasattr(state, 'investment_debate_state'):
        debate_state = getattr(state, 'investment_debate_state', None)
    elif isinstance(state, dict) and 'investment_debate_state' in state:
        debate_state = state.get('investment_debate_state')
    
    if debate_state:
        # Extract long researcher history
        bull_content = _extract_field(debate_state, 'bull_history')
        if bull_content and len(bull_content.strip()) > 10:
            reports['bull_researcher'] = bull_content.strip()
        
        # Extract short researcher history
        bear_content = _extract_field(debate_state, 'bear_history')
        if bear_content and len(bear_content.strip()) > 10:
            reports['bear_researcher'] = bear_content.strip()
        
        # Extract Research Manager Analysis
        decision_content = _extract_field(debate_state, 'judge_decision')
        if not decision_content:
            decision_content = str(debate_state) if debate_state else ""
        if decision_content and len(decision_content.strip()) > 10:
            reports['research_team_decision'] = decision_content.strip()
    
    # Handle risk management team debate status report
    risk_state = None
    if hasattr(state, 'risk_debate_state'):
        risk_state = getattr(state, 'risk_debate_state', None)
    elif isinstance(state, dict) and 'risk_debate_state' in state:
        risk_state = state.get('risk_debate_state')
    
    if risk_state:
        # Extract activist analyst history
        risky_content = _extract_field(risk_state, 'risky_history')
        if risky_content and len(risky_content.strip()) > 10:
            reports['risky_analyst'] = risky_content.strip()
        
        # Extract conservative analyst history
        safe_content = _extract_field(risk_state, 'safe_history')
        if safe_content and len(safe_content.strip()) > 10:
            reports['safe_analyst'] = safe_content.strip()
        
        # Extract neutral analyst history
        neutral_content = _extract_field(risk_state, 'neutral_history')
        if neutral_content and len(neutral_content.strip()) > 10:
            reports['neutral_analyst'] = neutral_content.strip()
        
        # Extract risk assessor decisions
        risk_decision = _extract_field(risk_state, 'judge_decision')
        if not risk_decision:
            risk_decision = str(risk_state) if risk_state else ""
        if risk_decision and len(risk_decision.strip()) > 10:
            reports['risk_management_decision'] = risk_decision.strip()
    
    logger.info(f"📊 Extracted from state {len(reports)} reports: {list(reports.keys())}")
    return reports


def _extract_field(obj: Any, field_name: str) -> str:
    """
    Extract field value from object
    
    Args:
        obj: Object (can be a class instance or dictionary)
        field_name: Field name
        
    Returns:
        field value (string)
    """
    if hasattr(obj, field_name):
        return getattr(obj, field_name, "")
    elif isinstance(obj, dict) and field_name in obj:
        return obj[field_name]
    return ""


async def save_analysis_report(
    db,
    stock_symbol: str,
    stock_name: str,
    market_type: str,
    model_info: str,
    reports: Dict[str, str],
    decision: Dict[str, Any],
    recommendation: str,
    confidence_score: float,
    risk_level: str,
    summary: str = "",
    key_points: list = None,
    task_id: str = "",
    execution_time: float = 0.0,
    tokens_used: int = 0,
    analysts: list = None,
    research_depth: str = "Standard",
    analysis_date: Optional[str] = None,
    source: str = "api",
    engine: str = "v2",
    user_id: Optional[str] = None,
    performance_metrics: Dict[str, Any] = None,
    task_type: Optional[str] = None
) -> str:
    """
    Save analysis reports to the analysis_reports collection (unified method)
    
    Args:
        db: MongoDB Database connection
        stock_symbol: Stock code
        stock_name: Stock name
        market_type: Market type (A shares/Hong Kong stocks/US stocks)
        model_info: Model information
        reports: Report dictionary (duplicate fields will be cleaned)
        decision: decision dictionary
        recommendation: Research conclusion
        confidence_score: Confidence
        risk_level: risk level
        ... (Other parameters)
        
    Returns:
        analysis_id: analysis report ID
    """
    # 🔥 Generate analysis ID - use UTC time to keep consistent with old versions
    timestamp = datetime.utcnow()
    analysis_id = f"{stock_symbol}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
    
    # 🔥 Clean up duplicate fields in reports (avoid saving duplicate data)
    cleaned_reports = {}
    if isinstance(reports, dict):
        for key, value in reports.items():
            # Skip structured_reports (if present to avoid duplication)
            if key != "structured_reports":
                cleaned_reports[key] = value
    
    # Build documentation (completely consistent with single-strand analysis and workflow execution)
    document = {
        "analysis_id": analysis_id,
        "stock_symbol": stock_symbol,
        "stock_code": stock_symbol,
        "stock_name": stock_name,
        "market_type": market_type,
        "model_info": model_info,
        "analysis_date": analysis_date or timestamp.strftime('%Y-%m-%d'),
        "timestamp": timestamp,
        "status": "completed",
        "source": source,
        "engine": engine,
        "task_type": task_type,

        # Summary of analysis results
        "summary": summary or "Research completed",
        "analysts": analysts or [],
        "research_depth": research_depth,

        # Report content (use cleaned reports to avoid duplicate data)
        "reports": cleaned_reports,

        # 🔥 Key fields:decision
        "decision": decision,

        # metadata
        "created_at": timestamp,
        "updated_at": timestamp,

        # API Unique fields
        "task_id": task_id,
        "recommendation": recommendation,
        "confidence_score": confidence_score,
        "risk_level": risk_level,
        "key_points": key_points or [],
        "execution_time": execution_time,
        "tokens_used": tokens_used,

        # 🆕 Performance index data
        "performance_metrics": performance_metrics or {}
    }

    # If user_id exists, add to document
    if user_id:
        document["user_id"] = user_id

    # save to MongoDB
    result = await db.analysis_reports.insert_one(document)

    if result.inserted_id:
        logger.info(f"✅ Analysis report has been saved to MongoDB: {analysis_id}, total {len(reports)} reporting modules")
    else:
        logger.error("❌ MongoDB Insertion failed")

    return analysis_id


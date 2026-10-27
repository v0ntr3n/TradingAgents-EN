"""
Weight calculation tool

Automatically calculate the weight of each report based on the analyst selected by the user
"""

from typing import Dict, List, Optional, Tuple


def calculate_report_weights(
    reports: Dict[str, str],
    trading_style: Optional[str] = None
) -> Dict[str, float]:
    """
    Calculate the weight of each report based on the analyst reports selected by the user
    
    Args:
        reports: Report dictionary, key is the report field name, value is the report content (if it is an empty string or None, it means not selected)
        trading_style: trading style,"short" (short line) or"long" (medium and long term), if it is None, it will be automatically determined
    
    Returns:
        Weight dictionary, key is the report field name, value is the weight (a floating point number between 0-1)
    """
    # Mapping of report field names to analyst types
    REPORT_TO_ANALYST_TYPE = {
        "market_report": "technical",      # Market Analyst (Technical Analysis)
        "news_report": "news",             # news analyst
        "sentiment_report": "social",       # Social Media Analyst (Sentiment Analysis)
        "fundamentals_report": "fundamental",  # fundamental analyst
        "sector_report": "sector",         # Sector Analyst (Industry Analysis)
        "index_report": "index",           # Market Analyst
    }
    
    # Filter out non-empty reports (indicating that the user selected these analysts)
    selected_reports = {
        report_key: report_content
        for report_key, report_content in reports.items()
        if report_content and isinstance(report_content, str) and len(report_content.strip()) > 0
    }
    
    if not selected_reports:
        # If no report is selected, an empty weights dictionary is returned
        return {}
    
    # If no trading style is specified, it will be automatically determined
    if trading_style is None:
        trading_style = _infer_trading_style(selected_reports)
    
    # Set weights based on trading style
    if trading_style == "short":
        # Short-term weight configuration
        weights = _calculate_short_term_weights(selected_reports)
    elif trading_style == "long":
        # Medium and long-term weight allocation
        weights = _calculate_long_term_weights(selected_reports)
    else:
        # Default: average weight
        weights = _calculate_equal_weights(selected_reports)
    
    return weights


def _infer_trading_style(reports: Dict[str, str]) -> str:
    """
    Infer trading style based on selected reports
    
    Args:
        reports: Selected report dictionary
    
    Returns:
        "short" or "long"
    """
    # If you choose a fundamental analyst, it is more likely to be a medium- to long-term analyst.
    if "fundamentals_report" in reports:
        return "long"
    
    # If you choose technology, news, or social media analysts, you are more likely to be short-term
    if "market_report" in reports and "news_report" in reports and "sentiment_report" in reports:
        return "short"
    
    # If you choose a sector analyst, he is more likely to be a medium to long-term analyst.
    if "sector_report" in reports:
        return "long"
    
    # Default returns short line
    return "short"


def _calculate_short_term_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the weight of short-term transactions
    
    Short-term weight configuration:
    - Technical analysis (market_report):40%
    - News analysis (news_report):30%
    - Social media analysis (sentiment_report):30%
    - Other reports: 10% or less
    """
    weights = {}
    total_weight = 0.0
    
    # Core reporting weight
    core_reports = {
        "market_report": 0.40,      # technical analysis 40%
        "news_report": 0.30,        # news analysis 30%
        "sentiment_report": 0.30,   # social media analysis 30%
    }
    
    # Check if the core report exists
    selected_core_reports = {
        k: v for k, v in core_reports.items() if k in reports
    }
    
    if selected_core_reports:
        # If core reports are present, use default weights
        for report_key, weight in selected_core_reports.items():
            weights[report_key] = weight
            total_weight += weight
        
        # Other reports (fundamentals, sectors, market) have lower weights
        other_reports = {
            "fundamentals_report": 0.05,  # Fundamentals 5%
            "sector_report": 0.05,        # plate 5%
            "index_report": 0.10,         # Market 10%
        }
        
        for report_key, weight in other_reports.items():
            if report_key in reports:
                weights[report_key] = weight
                total_weight += weight
        
        # Normalized weights (make sure the sum is 1.0)
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
    else:
        # If core reporting is incomplete, use average weight
        weights = _calculate_equal_weights(reports)
    
    return weights


def _calculate_long_term_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the weight of medium and long-term investments
    
    Medium and long-term weight configuration:
    - Fundamental analysis (fundamentals_report):50%
    - Sector analysis (sector_report):30%
    - Risk analysis (reflected through risk multi-scenario research):20%
    - Other reports: 10% or less
    """
    weights = {}
    total_weight = 0.0
    
    # Core reporting weight
    core_reports = {
        "fundamentals_report": 0.50,  # fundamental analysis 50%
        "sector_report": 0.30,        # Sector analysis 30%
    }
    
    # Check if the core report exists
    selected_core_reports = {
        k: v for k, v in core_reports.items() if k in reports
    }
    
    if selected_core_reports:
        # If core reports are present, use default weights
        for report_key, weight in selected_core_reports.items():
            weights[report_key] = weight
            total_weight += weight
        
        # Other reports have lower weight
        other_reports = {
            "market_report": 0.10,        # Technical analysis 10% (only used to determine whether the technical situation is in a downtrend)
            "news_report": 0.05,          # news analysis 5%
            "sentiment_report": 0.05,     # social media analysis 5%
            "index_report": 0.00,         # Market analysis 0% (not paying much attention to the market in the medium and long term)
        }
        
        for report_key, weight in other_reports.items():
            if report_key in reports:
                weights[report_key] = weight
                total_weight += weight
        
        # Normalized weights (make sure the sum is 1.0)
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
    else:
        # If core reporting is incomplete, use average weight
        weights = _calculate_equal_weights(reports)
    
    return weights


def _calculate_equal_weights(reports: Dict[str, str]) -> Dict[str, float]:
    """
    Calculate the average weight (used when the trading style cannot be determined)
    
    Args:
        reports: Selected report dictionary
    
    Returns:
        A dictionary of weights with equal weights for all reports
    """
    if not reports:
        return {}
    
    weight = 1.0 / len(reports)
    return {report_key: weight for report_key in reports.keys()}


def format_weighted_reports_prompt(
    reports: Dict[str, str],
    weights: Dict[str, float],
    report_labels: Optional[Dict[str, str]] = None
) -> str:
    """
    Format weighted report prompt words
    
    Args:
        reports: report dictionary
        weights: weight dictionary
        report_labels: Report label dictionary (optional) to display Chinese names
    
    Returns:
        Formatted prompt text
    """
    if not report_labels:
        report_labels = {
            "market_report": "Market Analysis (Technical Analysis)",
            "news_report": "news analysis",
            "sentiment_report": "Social media analysis (market sentiment)",
            "fundamentals_report": "fundamental analysis",
            "sector_report": "Sector analysis (industry analysis)",
            "index_report": "Market analysis",
        }
    
    # Sort by weight (high to low)
    sorted_reports = sorted(
        weights.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    prompt_parts = []
    
    # High weight report (weight >= 20%) 
    high_weight_reports = [
        (report_key, weight) for report_key, weight in sorted_reports
        if weight >= 0.20 and report_key in reports
    ]
    
    if high_weight_reports:
        prompt_parts.append(" [Important report] (high weight, please pay attention)")
        for report_key, weight in high_weight_reports:
            label = report_labels.get(report_key, report_key)
            weight_pct = int(weight * 100)
            prompt_parts.append(f"- {label} (weight{weight_pct}%) : \n{reports[report_key]}\n")
    
    # Low weight report (weight < 20%) 
    low_weight_reports = [
        (report_key, weight) for report_key, weight in sorted_reports
        if weight < 0.20 and report_key in reports
    ]
    
    if low_weight_reports:
        prompt_parts.append("\n [Secondary report] (low weight, for reference only)")
        for report_key, weight in low_weight_reports:
            label = report_labels.get(report_key, report_key)
            weight_pct = int(weight * 100)
            prompt_parts.append(f"- {label} (weight{weight_pct}%, For reference only):\n{reports[report_key]}\n")
    
    # Add weight description
    if prompt_parts:
        prompt_parts.append(
            "\n**Weight description**: "
            "\n- Please focus on high-weighted reports, which are more important for investment decisions"
            "\n- Low-weighted reports are only for supplementary reference and should not be overly relied upon."
            "\n- When making a comprehensive judgment, please give appropriate attention based on the weight."
        )
    
    return "\n".join(prompt_parts)



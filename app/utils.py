from __future__ import annotations
import sys as _sys
__path__ = []
_self_mod = _sys.modules[__name__]
for _sub in ['api_key_utils', 'compliance', 'error_formatter', 'report_exporter', 'report_formatter', 'report_saver', 'thread_safe_db', 'timezone', 'trading_time']:
    _sys.modules[f"app.utils.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === api_key_utils.py ===
"""
API Key Processing utility functions

Provides unified API Key verification, abbreviation, environment variable reading and other functions
"""

import os
from typing import Optional


def is_valid_api_key(api_key: Optional[str]) -> bool:
    """
    Determine whether the API Key is valid
    
    A valid API Key must satisfy:
    1. cannot be empty
    2. The length must be >= 5
    3. Cannot be a placeholder (prefix:your_, your-) 
    4. Cannot be a placeholder (suffix:_here, -here) 
    5. Cannot be a truncated key (containing '...') 
    
    Args:
        api_key: To be verified API Key
        
    Returns:
        bool: Is it valid?
    """
    if not api_key:
        return False
    
    api_key = api_key.strip()
    
    # 1. cannot be empty
    if not api_key:
        return False
    
    # 2. The length must be >= 5
    if len(api_key) < 5:
        return False
    
    # 3. Cannot be a placeholder (prefix)
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return False
    
    # 4. Cannot be a placeholder (suffix)
    if api_key.endswith('_here') or api_key.endswith('-here'):
        return False
    
    # 5. Cannot be a truncated key (containing '...') 
    if '...' in api_key:
        return False
    
    return True


def truncate_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    Abbreviated API Key, showing the first 6 digits and the last 6 digits
    
    Example:
        Input:'d1el869r01qghj41hahgd1el869r01qghj41hai0'
        Output:'d1el86...j41hai0'
    
    Args:
        api_key: To be abbreviated API Key
        
    Returns:
        str: Abbreviated API Key, if input is empty or length <= 12 then return the original value
    """
    if not api_key or len(api_key) <= 12:
        return api_key
    
    return f"{api_key[:6]}...{api_key[-6:]}"


def get_env_api_key_for_provider(provider_name: str) -> Optional[str]:
    """
    Obtain the large model manufacturer s information from environment variables API Key
    
    Environment variable name format:{PROVIDER_NAME}_API_KEY
    
    Args:
        provider_name: Manufacturer name (such as 'deepseek', 'dashscope') 
        
    Returns:
        str: API Key in environment variables, returned if it does not exist or is invalid None
    """
    env_key_name = f"{provider_name.upper()}_API_KEY"
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def get_env_api_key_for_datasource(ds_type: str) -> Optional[str]:
    """
    Get the data source from environment variables API Key
    
    Mapping of data source types to environment variable names:
    - tushare → TUSHARE_TOKEN
    - finnhub → FINNHUB_API_KEY
    - polygon → POLYGON_API_KEY
    - iex → IEX_API_KEY
    - quandl → QUANDL_API_KEY
    - alphavantage → ALPHAVANTAGE_API_KEY
    
    Args:
        ds_type: Data source type (e.g. 'tushare', 'finnhub') 
        
    Returns:
        str: API Key in environment variables, returned if it does not exist or is invalid None
    """
    # Mapping of data source types to environment variable names
    env_key_map = {
        "tushare": "TUSHARE_TOKEN",
        "qmt": "QMT_TOKEN",
        "finnhub": "FINNHUB_API_KEY",
        "polygon": "POLYGON_API_KEY",
        "iex": "IEX_API_KEY",
        "quandl": "QUANDL_API_KEY",
        "alphavantage": "ALPHAVANTAGE_API_KEY",
    }
    
    env_key_name = env_key_map.get(ds_type.lower())
    if not env_key_name:
        return None
    
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def should_skip_api_key_update(api_key: Optional[str]) -> bool:
    """
    Determine whether API Key update should be skipped

    Updates should be skipped (original values retained) in the following cases:
    1. API Key is the truncated key (containing '...') 
    2. API Key is a placeholder (your_*, your-*) 

    Args:
        api_key: To be checked API Key

    Returns:
        bool: Should updates be skipped?
    """
    if not api_key:
        return False

    api_key = api_key.strip()

    # 1. Truncated key (contains '...') 
    if '...' in api_key:
        return True

    # 2. placeholder
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return True

    return False


def has_valid_api_key(llm_config, providers_dict: Optional[dict] = None) -> bool:
    """
    Determine whether the LLM configuration has a valid API Key

    Checking sequence (consistent with /api/config/llm/providers interface logic):
    1. Check whether it is a local model (ollama, localai), local models are not required API Key
    2. Check the model configuration for api_key
    3. Check api_key in manufacturer configuration (if providers_dict is provided)
    4. Check the environment variables for api_key

    Args:
        llm_config: LLM Configuration object (LLMConfig or dictionary)
        providers_dict: Manufacturer configuration dictionary {provider_name: LLMProvider}, Optional

    Returns:
        bool: Whether there is a valid API Key (logically consistent with the has_api_key field)
    """
    # Get provider and api_key
    if hasattr(llm_config, 'provider'):
        provider = llm_config.provider
        model_api_key = llm_config.api_key
    else:
        provider = llm_config.get('provider', '')
        model_api_key = llm_config.get('api_key', '')

    # 🔥 Not required for local models API Key
    local_models = ["ollama", "localai"]
    if provider.lower() in local_models:
        return True

    # 1. Check the model configuration for api_key
    if is_valid_api_key(model_api_key):
        return True

    # 2. Check the api_key in the manufacturer configuration (use database configuration first)
    if providers_dict and provider in providers_dict:
        provider_obj = providers_dict[provider]
        # 🔥 Check if the manufacturer is a local model
        provider_name = provider_obj.name if hasattr(provider_obj, 'name') else provider_obj.get('name', '')
        if provider_name.lower() in local_models:
            return True
        
        provider_api_key = provider_obj.api_key if hasattr(provider_obj, 'api_key') else provider_obj.get('api_key', '')
        if is_valid_api_key(provider_api_key):
            return True

    # 3. Check the api_key in the environment variable (logically consistent with /api/config/llm/providers)
    env_api_key = get_env_api_key_for_provider(provider)
    if env_api_key:
        return True

    return False


# === compliance.py ===
"""Compliance output tool.

Unify transaction recommendation fields in closing analysis results, retaining summaries, risk factors, and public information observations required for research assistance.
"""


import re
from typing import Any, Dict, Iterable, List, Tuple


SAFE_REPORT_KEYS = (
    "index_report",
    "sector_report",
    "market_report",
    "fundamentals_report",
    "sentiment_report",
    "news_report",
)

GENERIC_RESEARCH_RECOMMENDATION = "Please refer to the detailed research report, focusing on fundamental changes, market environment and risk factors."
GENERIC_POSITION_RECOMMENDATION = "This position research only provides research observations and risk tips. Please make independent judgments based on your own strategies."
GENERIC_REVIEW_SUMMARY = "This review only retains the review conclusions, disciplinary issues and research and improvement directions, and does not provide suggestions for future trading actions."
GENERIC_REVIEW_IMPROVEMENTS = (
    "Improve pre-transaction evidence verification and recording to avoid insufficient basis for pre-transaction transactions.",
    "Organize the triggering conditions of the trading plan into a verifiable list to improve execution consistency.",
    "During the review, the focus will be on discipline enforcement, risk exposure and research blind spots.",
)

_ACTIONABLE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"buy|sell|hold|Add to position|Reduce positions|Clearance|Open a position|Close position|Adjust positions",
        r"stop loss|Take profit|position|target price|target price|target range|price analysis range|reference price",
        r"Target position|target point|support level|resistance level|pressure level|Configuration recommendations|defensive configuration|offensive configuration|margin of safety|Sector opportunities",
        r"investment advice|trading advice|Operation suggestions|Simulate an order with one click|Place an order|simulated trading",
        r"BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
        r"target_price|stop_loss|take_profit|position_ratio|suggested_quantity|suggested_amount",
    )
]
_REVIEW_EXECUTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(Suggestions|OK|Can be considered|should|should|need|appropriate|Not suitable).{0,12}(buy|sell|continue to hold|hold|Add to position|Reduce positions|cover position|Clearance|Open a position|Close position|Adjust positions)",
        r"(next time|Follow-up|future).{0,16}(buy|sell|continue to hold|hold|Add to position|Reduce positions|cover position|Clearance|Open a position|Close position|Adjust positions|stop loss|Take profit)",
        r"continue to hold|buy on dips|sell on rallies|Buy in batches|Sell in batches",
        r"Stop loss price|Take profit price|target price|target price|target range|reference price|reference price",
        r"(fell below|breakthrough|call back to|rebound to|fall to|rise to|return to).{0,12}(buy|sell|Add to position|Reduce positions|stop loss|Take profit)",
        r"position.{0,8}(\d+%|percent|\d+into|controlled in|promoted to|down to|raised to|Adjusted down to)",
        r"\b(BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL)\b",
        r"Simulate an order with one click|Place an order|simulated trading",
    )
]
_POSITION_TRIGGER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:technical aspect|Fundamentals|risk|Comprehensive)?Rating\s*[:: ]?\s*\d+(?:\.\d+)?\s*points",
        r"continuous.{0,8}(?:day|day|week).{0,10}(stand firm|Stand firm at the close|Increase the volume|shrink|breakthrough|fell below)",
        r"Right intervention|left intervention|Basis for intervention|Admission basis|Exit basis|Transaction trigger|rebound kinetic energy",
        r"\bMA\d+\b|\bRSI\d*\b|\bMACD\b|\bKDJ\b|Brin(?:middle track|On track|Lower track)?",
        r"support strap|support level|resistance level|pressure level|Increase the volume|shrink|stand firm|breakthrough|fell below",
    )
]
_POSITION_LABEL_ONLY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(Research conclusion|core basis|research judgment|Risk warning|Observation points|Supplementary perspective|research observation|risk assessment|Catalysis and improving conditions)$",
    )
]
_POSITION_PLAIN_LANGUAGE_REPLACEMENTS = (
    ("Technically highly secure", "The short-term trend has not weakened significantly"),
    ("Neutral to strong state", "The current status is relatively stable, but further verification is needed."),
    ("Technical structure is critically stable", "There is no further deterioration in the short term"),
    ("Solid fundamentals but differentiated valuation structure", "The company s operating foundation is acceptable, but the market is still divided on valuation restoration"),
    ("neutral observation stage", "For the time being, we can only continue to observe"),
    ("Prices cling to medium-term support", "The stock price is still near a periodic low"),
    ("No trend reversal signal has occurred yet", "No clear signal of repair has been seen yet"),
    ("Nor did it trigger conditions for systemic deterioration.", "There is no clear evidence of deterioration"),
    ("The cost price is significantly higher than the current price", "The current price is still significantly lower than the holding cost"),
    ("Cost price is buried deep below all key moving averages", "The current price is significantly higher than the holding cost"),
    ("Stable financial indicators and excellent earnings quality", "Overall operational and financial performance is stable"),
    ("Operating cash flow continues to cover net profit at a high multiple", "Cash flow performance is relatively stable"),
    ("Solid margin of financial safety", "Financial buffers remain solid"),
    ("Growth logic needs to be verified", "Whether subsequent growth will continue remains to be verified."),
    ("ROE staged decline", "Profit efficiency drops in stages"),
    ("Gross profit margin data is missing", "Margin data is incomplete"),
    ("High PB valuation", "current valuation level"),
    ("barrier premium", "competitive advantage premium"),
    ("growth premium", "growth expected premium"),
    ("Valuation center rises", "The market is willing to give a higher valuation"),
    ("second curve", "new business growth"),
    ("Customer designated announcement", "Announcement of new customers and project progress"),
    ("bargaining power", "pricing power"),
    ("Repair requires time and multiple conditions.", "Subsequent repairs usually take time and require improvements in many aspects."),
)
_POSITION_GENERIC_ITEM_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"The current judgment is mainly based on the disclosure of operating information and risk signals.",
        r"Current conclusions are primarily based on disclosed information",
        r"Please focus on",
        r"Please keep following",
        r"Follow-up key observations",
    )
]
_POSITION_APPENDIX_SECTION_ORDER = (
    ("technical_analysis", "Technical analysis"),
    ("fundamental_analysis", "fundamental analysis"),
    ("risk_analysis", "risk assessment"),
)
_POSITION_APPENDIX_TITLE_TO_KEY = {
    title: key for key, title in _POSITION_APPENDIX_SECTION_ORDER
}
_POSITION_APPENDIX_HEADING_PATTERN = re.compile(r"^ [(Technical analysis|fundamental analysis|risk assessment)] $")
_JSON_FIELD_PATTERN = re.compile(r'^[\[\]{}":,0-9._%\-\s]+$')
_SENTENCE_SPLIT_PATTERN = re.compile(r"[\n。！？；]+")
_LOW_SIGNAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^Basic stock information$",
        r"^Company name[:: ]",
        r"^Stock code[:: ]",
        r"^Market[:: ]",
        r"^current price[:: ]",
        r"^Increase or decrease[:: ]",
        r"^Analysis date[:: ]",
        r"^Data source[:: ]",
        r"^Basic information[:: ]",
        r"^financial data[:: ]$",
        r"^1. Company Profile$",
        r"^2. Financial data analysis$",
        r"^Three.",
        r"^Four.",
        r"analysis report",
    )
]
_DISPLAY_REPORT_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"target price|target price|price range|key price|key price|key verification bit|Observation interval|reference price|reference price|Risk Control Reference",
        r"support level|resistance level|breakthrough|fell below|stand firm|fall|stop loss|Take profit|position|risk exposure|Position period",
        r"Room for upside|Downside|Upside|Downside|Profit space|Earnings expectations|maximum benefit|Potential earnings|retracement|maximum possible loss",
        r"Risk-benefit ratio|expected return|margin of safety|configuration value|Contrarian investment opportunities|buy signal|sell signal|Admission|Exit conditions|Operational strategy",
        r"Overweight view|Underweight view|Open a position|Close position|Adjust positions|Heavy warehouse|Qingcang|Buy in batches|Sell in batches|bullish price|bearish price",
        r"(?:¥|￥|\$)\s*\d|\d+(?:\.\d+)?\s*(?:Yuan|US dollars|Hong Kong dollar)",
    )
]
_INFERENTIAL_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"inference|inferred|infer|Speculate|Presumption|Estimate|Calculate|estimate|hypothesis|Assume|Guess|conjecture|suspected",
        r"possible|or will|hopefully|expected|tend to|High probability|maybe|Maybe",
        r"To be verified|Need to verify|yet to be verified|Still to be verified|Not verifiable|Difficult to verify",
    )
]

_DISPLAY_TITLE_REPLACEMENTS = [
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?News Analyst Research Report$', re.IGNORECASE), 'Journalism Research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?news research report$', re.IGNORECASE), 'Journalism Research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Social Media Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Social Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Sentiment Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Sector Analyst Research Observation Report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Industry Analyst Research Observation Report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Industry sector research observation report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Market Analyst Research Observation Report$', re.IGNORECASE), 'market environment research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Market Environment Research Observation Report$', re.IGNORECASE), 'market environment research'),
]

_DISPLAY_PHRASE_REPLACEMENTS = (
    ('buy logic', 'research logic'),
    ('investment opportunities', 'research leads'),
    ('allocation investor', 'research users'),
    ('configuration value', 'Research tracking value'),
    ('margin of safety', 'risk buffer'),
    ('have certain appeal', 'Worth continuing to follow'),
    ('The starting point of value restoration', 'Early signs of valuation and expected repairs'),
)

RESEARCH_ONLY_DISCLAIMER = "This report is for research reference only and does not constitute individual stock recommendation, investment advice or operation basis. Please make independent judgments based on public information disclosure and your own research."
_LEGACY_DISCLAIMER_BLOCK_PATTERN = re.compile(
    r"(?is)(?:\*\*)?Disclaimer(?:\*\*)?[: :]\s*"
    r"(?:Ben(?:analysis)?The report is for reference only and does not constitute investment advice..*?Make investment decisions independently."
    r"|Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary.)"
)
_LEGACY_DISCLAIMER_LINE_PATTERN = re.compile(
    r"(?is)Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary."
)
_TOOL_CALL_ARTIFACT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^</?tool_call>$",
        r'^\{"name"\s*:\s*"get_[^\"]+".*"arguments"\s*:\s*\{.*\}\s*\}$',
        r'^"name"\s*:\s*"get_[^\"]+"',
        r'^"arguments"\s*:\s*\{',
    )
]
_STABLE_DATA_REQUEST_DATE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"There are currently no analysis days[ ((](\d{4}-\d{2}-\d{2})[) )]Corresponding stable post-closing daily frequency data",
        r"None currently\s*(\d{4}-\d{2}-\d{2})\s*Corresponding stable post-closing daily frequency data",
        r"None currently\s*(\d{4}-\d{2}-\d{2})\s*of[^. \n]*Daily frequency data after stable closing",
    )
]
_STABLE_DATA_SNAPSHOT_LINE_PATTERN = re.compile(
    r"The snapshot date of all valuation indicators is unified to\s*(?:\*\*)?(\d{4}-\d{2}-\d{2})(?:\*\*)?[. .]?"
)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "markdown", "text", "message", "report"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        return ""
    return "" if value is None else str(value)


def contains_actionable_content(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _ACTIONABLE_PATTERNS)


def contains_review_execution_guidance(text: str) -> bool:
    if not text:
        return False
    normalized = _plain_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _REVIEW_EXECUTION_PATTERNS)


def _plain_text(text: Any) -> str:
    if text is None:
        return ""

    if isinstance(text, (list, tuple, set)):
        joined = " ".join(
            fragment
            for item in text
            for fragment in [_plain_text(item)]
            if fragment
        )
        if not joined:
            return ""
        text = joined
    elif isinstance(text, dict):
        text = _as_text(text)
    elif not isinstance(text, str):
        text = str(text)

    normalized = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    normalized = re.sub(r"`+", "", normalized)
    normalized = normalized.replace("#", " ").replace("*", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_display_line(line: str) -> str:
    normalized_line = line

    for pattern, replacement in _DISPLAY_TITLE_REPLACEMENTS:
        match = pattern.match(normalized_line.strip())
        if match:
            prefix = match.groupdict().get('prefix') or ''
            return f"{prefix}{replacement}".rstrip()

    for old_text, new_text in _DISPLAY_PHRASE_REPLACEMENTS:
        normalized_line = normalized_line.replace(old_text, new_text)

    return normalized_line


def _normalize_research_disclaimer(text: str) -> str:
    normalized = _LEGACY_DISCLAIMER_BLOCK_PATTERN.sub(
        f"**Disclaimer**: {RESEARCH_ONLY_DISCLAIMER}",
        text,
    )
    normalized = _LEGACY_DISCLAIMER_LINE_PATTERN.sub(RESEARCH_ONLY_DISCLAIMER, normalized)
    return normalized


def _strip_tool_call_artifacts(text: str) -> Tuple[str, bool]:
    cleaned_lines: List[str] = []
    removed_any = False

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        normalized = _plain_text(raw_line)

        if any(pattern.search(stripped) or pattern.search(normalized) for pattern in _TOOL_CALL_ARTIFACT_PATTERNS):
            removed_any = True
            continue

        if stripped.startswith("{") and '"name"' in stripped and '"arguments"' in stripped and '"get_' in stripped:
            removed_any = True
            continue

        cleaned_lines.append(raw_line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"```(?:json)?\s*```", "", cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    return cleaned_text, removed_any


def _normalize_stable_data_snapshot_conflicts(text: str) -> str:
    requested_date = ""
    for pattern in _STABLE_DATA_REQUEST_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            requested_date = match.group(1)
            break

    if not requested_date:
        return text

    def _replace_snapshot_line(match: re.Match[str]) -> str:
        snapshot_date = match.group(1)
        if snapshot_date == requested_date:
            return "The snapshot date of all valuation indicators should be based on the latest available trading day returned by the tool, and the current text date caliber still needs to be verified."
        return match.group(0)

    return _STABLE_DATA_SNAPSHOT_LINE_PATTERN.sub(_replace_snapshot_line, text)


def sanitize_report_artifacts(text: Any) -> str:
    raw_text = _as_text(text)
    if not raw_text:
        return ""

    normalized = _normalize_research_disclaimer(raw_text)
    normalized, _ = _strip_tool_call_artifacts(normalized)
    normalized = _normalize_stable_data_snapshot_conflicts(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized


def is_low_signal_text(text: str) -> bool:
    normalized = _plain_text(text)
    if not normalized:
        return True
    if any(pattern.search(normalized) for pattern in _LOW_SIGNAL_PATTERNS):
        return True
    if normalized.startswith("-") and len(normalized) <= 14:
        return True
    return False


def _fragment_score(text: str) -> int:
    normalized = _plain_text(text)
    if not normalized:
        return -1

    score = min(len(normalized), 160)
    if is_low_signal_text(normalized):
        score -= 120
    if any(keyword in normalized for keyword in ("risk", "Profit", "growth", "pressure", "competition", "Valuation", "assets", "Liabilities", "catalysis", "Industry", "Macro", "demand", "income", "profit")):
        score += 60
    if normalized.startswith("-"):
        score -= 10
    return score


def sanitize_text_block(text: Any, fallback: str = "") -> str:
    raw_text = sanitize_report_artifacts(text)
    if not raw_text:
        return fallback

    lines: List[str] = []
    for chunk in re.split(r"\r?\n", raw_text):
        line = _plain_text(chunk)
        if not line or len(line) < 6:
            continue
        if _JSON_FIELD_PATTERN.match(line):
            continue
        if contains_actionable_content(line):
            continue
        if is_low_signal_text(line):
            continue
        lines.append(line)

    deduped: List[str] = []
    for line in lines:
        if line not in deduped:
            deduped.append(line)

    if not deduped:
        return fallback
    return "\n".join(deduped[:12])[:2500]


def contains_position_trigger_language(text: str) -> bool:
    if not text:
        return False
    normalized = _plain_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _POSITION_TRIGGER_PATTERNS)


def _iter_position_review_fragments(text: Any) -> Iterable[str]:
    for fragment in _iter_review_fragments(text):
        yield fragment

    raw_text = _as_text(text)
    if not raw_text:
        return

    for chunk in re.split(r"\r?\n", raw_text):
        normalized = _plain_text(chunk)
        if not normalized:
            continue

        fragments = [
            fragment.strip()
            for fragment in _SENTENCE_SPLIT_PATTERN.split(normalized)
            if fragment.strip()
        ]
        if not fragments:
            fragments = [normalized]

        for fragment in fragments:
            if len(fragment) < 4:
                continue
            if _JSON_FIELD_PATTERN.match(fragment):
                continue
            if is_low_signal_text(fragment):
                continue
            if not contains_review_execution_guidance(fragment):
                continue

            simplified = _simplify_position_user_language(fragment)
            if not simplified or contains_review_execution_guidance(simplified):
                continue
            yield simplified


def sanitize_position_text_block(text: Any, fallback: str = "") -> str:
    deduped: List[str] = []
    for fragment in _iter_position_review_fragments(text):
        if contains_position_trigger_language(fragment):
            continue
        if any(pattern.match(fragment) for pattern in _POSITION_LABEL_ONLY_PATTERNS):
            continue
        if fragment not in deduped:
            deduped.append(fragment)

    if not deduped:
        return fallback
    return "；".join(deduped[:5])[:600]


def _normalize_position_list_items(value: Any, fallback: List[str], limit: int = 3) -> List[str]:
    raw_items: List[str] = []
    if isinstance(value, list):
        for item in value:
            text = _plain_text(item)
            if text:
                raw_items.append(text)
    elif value:
        raw_items.extend(_iter_position_review_fragments(value))

    cleaned_items: List[str] = []
    for item in raw_items:
        for fragment in _iter_position_clauses(item):
            cleaned = _clip_position_user_text(_simplify_position_user_language(fragment), 56)
            if not cleaned or contains_position_trigger_language(cleaned):
                continue
            if _is_low_signal_position_item(cleaned) or _looks_truncated_position_text(cleaned):
                continue
            if cleaned not in cleaned_items:
                cleaned_items.append(cleaned)
            if len(cleaned_items) >= limit:
                break
        if len(cleaned_items) >= limit:
            break

    if cleaned_items:
        return cleaned_items
    return fallback[:limit]


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_int(value: Any) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(number)


def _extract_position_snapshot(result_data: Dict[str, Any], position_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(position_snapshot, dict) and position_snapshot:
        return position_snapshot
    summary = result_data.get("summary")
    if isinstance(summary, dict):
        return summary
    return {}


def _simplify_position_user_language(text: str) -> str:
    normalized = _plain_text(text)
    if not normalized:
        return ""

    for old, new in _POSITION_PLAIN_LANGUAGE_REPLACEMENTS:
        normalized = normalized.replace(old, new)

    normalized = re.sub(
        r"Missing short-term goals(?:also)?untouched(?:and)?stop loss",
        "Short-term performance fell short of expectations, but there are currently no signs of further deterioration.",
        normalized,
    )
    normalized = re.sub(r"Missed target", "Performance fell short of expectations", normalized)
    normalized = re.sub(r"untouched(?:and)?stop loss", "There are no signs of further deterioration yet", normalized)

    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("At this stage, there is no further deterioration in the short term,", "A more appropriate conclusion at this stage is to continue to observe: there will be no further deterioration in the short term;")
    normalized = normalized.replace("If there are still differences, we can only continue to observe for the time being.", "There are still differences, and we can only continue to observe for the time being.")
    normalized = normalized.replace("; price", "; stock price")
    normalized = normalized.replace("The current position is at", "At this stage")
    normalized = normalized.replace("；-", "；")
    normalized = normalized.replace("- ", "")
    return normalized.strip(" ；，。")


def _iter_position_clauses(text: Any) -> Iterable[str]:
    normalized = _plain_text(text)
    if not normalized:
        return

    for sentence in re.split(r"[。！？；]+", normalized):
        sentence = sentence.strip(" ；，。")
        if not sentence:
            continue

        comma_fragments = [
            fragment.strip(" ；，。")
            for fragment in re.split(r"[，、]+", sentence)
            if fragment.strip(" ；，。")
        ]
        if len(comma_fragments) >= 2:
            for fragment in comma_fragments:
                if len(fragment) >= 6:
                    yield fragment
            continue

        yield sentence


def _clip_position_user_text(text: str, max_len: int) -> str:
    normalized = _plain_text(text).strip(" ；，。:-")
    if not normalized:
        return ""
    if len(normalized) <= max_len:
        return normalized

    window = normalized[: max_len + 1]
    cut_at = max(window.rfind(marker) for marker in ("；", "。", "，", "、", "：", " "))
    if cut_at >= max(10, max_len // 2):
        clipped = window[:cut_at]
    else:
        clipped = window[:max_len]

    clipped = re.sub(r"(?:will|let|get|and|But|and|and|with|or|rule|Need|Wait|Yes)+$", "", clipped)
    return clipped.strip(" ；，。:-")


def _looks_truncated_position_text(text: str) -> bool:
    normalized = _plain_text(text).strip()
    if len(normalized) < 12:
        return False
    if re.search(r"[；，,:：\-/]$", normalized):
        return True
    return bool(re.search(r"(?:will|let|get|and|But|and|and|with|or|rule|Need|Wait|Yes)$", normalized))


def _is_low_signal_position_item(text: str) -> bool:
    normalized = _plain_text(text)
    return any(pattern.search(normalized) for pattern in _POSITION_GENERIC_ITEM_PATTERNS)


def _build_position_candidate_items(*sources: Any, limit: int = 3, max_len: int = 40) -> List[str]:
    items: List[str] = []
    for source in sources:
        for fragment in _iter_position_clauses(source):
            cleaned = _clip_position_user_text(_simplify_position_user_language(fragment), max_len)
            if len(cleaned) < 6:
                continue
            if contains_position_trigger_language(cleaned):
                continue
            if _is_low_signal_position_item(cleaned) or _looks_truncated_position_text(cleaned):
                continue
            if cleaned not in items:
                items.append(cleaned)
            if len(items) >= limit:
                return items
    return items


def _build_position_conclusion(*sources: Any) -> str:
    for source in sources:
        normalized = _clip_position_user_text(_simplify_position_user_language(source), 72)
        if normalized and not _looks_truncated_position_text(normalized) and (
            "Continue to observe" in normalized
            or "Performance fell short of expectations" in normalized
            or "further worsening the signal" in normalized
        ):
            return normalized

    clauses = _build_position_candidate_items(*sources, limit=2, max_len=32)
    if clauses:
        return _clip_position_user_text("；".join(clauses), 72)
    return "At this stage, it is more suitable to continue to observe and focus on confirming whether the original research logic still holds."


def _build_position_user_action_reason(
    result_data: Dict[str, Any],
    position_snapshot: Dict[str, Any] | None = None,
) -> tuple[str, str, Dict[str, Any]]:
    snapshot = _extract_position_snapshot(result_data, position_snapshot)
    raw_user_view = result_data.get("user_view") if isinstance(result_data.get("user_view"), dict) else {}
    analysis_summary = result_data.get("analysis_summary") if isinstance(result_data.get("analysis_summary"), dict) else {}
    neutral_advice = result_data.get("neutral_operation_advice") if isinstance(result_data.get("neutral_operation_advice"), dict) else {}
    if not neutral_advice and isinstance(result_data.get("neutral_operation_suggestion"), dict):
        neutral_advice = result_data.get("neutral_operation_suggestion")
    specific_plan = result_data.get("specific_plan") if isinstance(result_data.get("specific_plan"), dict) else {}
    cleaned_observation = _simplify_position_user_language(
        sanitize_position_text_block(
            raw_user_view.get("conclusion") or result_data.get("action_reason"),
            fallback="",
        )
    )
    cleaned_risk = sanitize_text_block(result_data.get("risk_assessment"), fallback="")
    cleaned_opportunity = sanitize_text_block(result_data.get("opportunity_assessment"), fallback="")

    current_price = _coerce_float(snapshot.get("current_price"))
    cost_price = _coerce_float(snapshot.get("cost_price"))
    unrealized_pnl_pct = _coerce_float(snapshot.get("unrealized_pnl_pct"))
    holding_days = _coerce_int(snapshot.get("holding_days"))

    snapshot_context_parts: List[str] = []
    if unrealized_pnl_pct is not None:
        abs_loss = abs(unrealized_pnl_pct)
        if unrealized_pnl_pct <= -30:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, It is already in a deep floating loss range.")
        elif unrealized_pnl_pct <= -15:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, It has deviated significantly from the original cost range.")
        elif unrealized_pnl_pct < 0:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, Still operating below costs.")
        elif unrealized_pnl_pct > 0:
            snapshot_context_parts.append(f"The current floating profit of this position is about{unrealized_pnl_pct:.2f}%, However, subsequent judgments still need to pay attention to whether the evidence continues.")

    if cost_price is not None and current_price is not None:
        snapshot_context_parts.append(f"Approximate cost price¥{cost_price:.2f}, Current price¥{current_price:.2f}. ")

    if holding_days is not None and holding_days >= 60:
        snapshot_context_parts.append(f"Holding time approx.{holding_days}Days later, priority should be given to confirming whether operations and risks have improved, rather than relying on short-term technical signals.")

    opening_parts = list(snapshot_context_parts)

    if cleaned_observation:
        opening_parts.append(cleaned_observation)
    else:
        opening_parts.append("At this stage, it is more appropriate to focus on confirming whether the research logic still holds, rather than directly interpreting short-term price fluctuations as the beginning of repair.")

    raw_position_context = _clip_position_user_text(
        _simplify_position_user_language(raw_user_view.get("position_context", "")),
        88,
    )
    if raw_position_context and not _looks_truncated_position_text(raw_position_context):
        position_context = raw_position_context
    else:
        position_context = _clip_position_user_text(" ".join(snapshot_context_parts[:3]).strip(), 96)

    conclusion = _build_position_conclusion(
        raw_user_view.get("conclusion"),
        cleaned_observation,
        analysis_summary.get("overall_view"),
        neutral_advice.get("core_judgment"),
    )

    key_points_fallback = _build_position_candidate_items(
        raw_user_view.get("conclusion"),
        cleaned_observation,
        analysis_summary.get("overall_view"),
        neutral_advice.get("core_judgment"),
        limit=3,
        max_len=38,
    ) or ["Current judgments still need to continue to check operating performance, risk changes and subsequent disclosures."]
    key_points = _normalize_position_list_items(
        raw_user_view.get("key_points") or analysis_summary.get("key_points") or neutral_advice.get("reasoning"),
        fallback=key_points_fallback,
    )
    risk_focus_fallback = _build_position_candidate_items(
        raw_user_view.get("risk_focus"),
        cleaned_risk,
        limit=3,
        max_len=42,
    ) or ["Please prioritize whether industry changes, company announcements, and position fluctuations continue to worsen."]
    risk_focus = _normalize_position_list_items(
        raw_user_view.get("risk_focus") or cleaned_risk,
        fallback=risk_focus_fallback,
    )
    watch_items_fallback = _build_position_candidate_items(
        raw_user_view.get("watch_items"),
        specific_plan.get("observation_factors"),
        neutral_advice.get("analysis_points"),
        cleaned_opportunity,
        limit=3,
        max_len=42,
    ) or ["The follow-up focus will be on operating quality, valuation changes and public catalysts that can change current judgments."]
    watch_items = _normalize_position_list_items(
        raw_user_view.get("watch_items") or specific_plan.get("observation_factors") or neutral_advice.get("analysis_points") or cleaned_opportunity,
        fallback=watch_items_fallback,
    )
    uncertainty_note = _clip_position_user_text(
        _simplify_position_user_language(raw_user_view.get("uncertainty_note", ""))
        or "The current conclusion is mainly based on disclosed information and needs to be verified in the future based on financial reports, announcements and industry changes.",
        72,
    )

    detailed_sections = [
        "### Current status",
        f"- {position_context}",
        f"- {conclusion}",
        "",
        "### core basis",
        *[f"- {item}" for item in key_points],
        "",
        "### Risk warning",
        *[f"- {item}" for item in risk_focus],
        "",
        "### Follow-up observation points",
        *[f"- {item}" for item in watch_items],
        "",
        "### uncertainty statement",
        f"- {uncertainty_note[:180]}",
    ]
    user_view = {
        "conclusion": conclusion[:80],
        "position_context": position_context[:96],
        "key_points": key_points,
        "risk_focus": risk_focus,
        "watch_items": watch_items,
        "uncertainty_note": uncertainty_note[:72],
    }
    compatibility_reason = _clip_position_user_text(f"{position_context} {conclusion}".strip(), 220)
    return compatibility_reason, "\n".join(detailed_sections).strip(), user_view


def _iter_review_fragments(text: Any) -> Iterable[str]:
    raw_text = _as_text(text)
    if not raw_text:
        return

    for chunk in re.split(r"\r?\n", raw_text):
        normalized = _plain_text(chunk)
        if not normalized:
            continue

        fragments = [
            fragment.strip()
            for fragment in _SENTENCE_SPLIT_PATTERN.split(normalized)
            if fragment.strip()
        ]
        if not fragments:
            fragments = [normalized]

        for fragment in fragments:
            if len(fragment) < 4:
                continue
            if _JSON_FIELD_PATTERN.match(fragment):
                continue
            if contains_review_execution_guidance(fragment):
                continue
            if is_low_signal_text(fragment):
                continue
            yield fragment


def sanitize_review_text_block(text: Any, fallback: str = "") -> str:
    deduped: List[str] = []
    for fragment in _iter_review_fragments(text):
        if fragment not in deduped:
            deduped.append(fragment)

    if not deduped:
        return fallback
    return "；".join(deduped[:6])[:1200]


def sanitize_review_detail_block(text: Any, fallback: str = "") -> str:
    raw_text = _as_text(text)
    if not raw_text:
        return fallback

    normalized = sanitize_report_artifacts(raw_text)
    if not normalized:
        return fallback

    cleaned_lines: List[str] = []

    for raw_line in normalized.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        plain = _plain_text(raw_line)
        if not plain:
            continue
        if _JSON_FIELD_PATTERN.match(plain):
            continue
        if contains_review_execution_guidance(plain):
            continue
        if is_low_signal_text(plain) and not stripped.startswith(("#", "-", "*")):
            continue

        cleaned_lines.append(raw_line.rstrip())

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

    if cleaned_text:
        return cleaned_text[:4000]

    return fallback


def sanitize_review_points(points: Any, fallback: Iterable[str] = ()) -> List[str]:
    cleaned_points: List[str] = []

    if isinstance(points, list):
        source_items = points
    elif points in (None, ""):
        source_items = []
    else:
        source_items = [points]

    for item in source_items:
        for fragment in _iter_review_fragments(item):
            if fragment not in cleaned_points:
                cleaned_points.append(fragment)
            if len(cleaned_points) >= 5:
                return cleaned_points

    for item in fallback:
        normalized = _plain_text(item)
        if normalized and normalized not in cleaned_points:
            cleaned_points.append(normalized)
        if len(cleaned_points) >= 5:
            break

    return cleaned_points[:5]


def sanitize_brief_points(points: Any) -> List[str]:
    cleaned_points: List[str] = []

    if not isinstance(points, list):
        return cleaned_points

    for item in points:
        normalized = _plain_text(_as_text(item))
        if len(normalized) < 2:
            continue
        if _JSON_FIELD_PATTERN.match(normalized):
            continue
        if contains_actionable_content(normalized):
            continue
        if is_low_signal_text(normalized):
            continue
        if normalized not in cleaned_points:
            cleaned_points.append(normalized[:120])
        if len(cleaned_points) >= 5:
            break

    return cleaned_points


def contains_inferential_evidence(text: str) -> bool:
    normalized = _plain_text(_as_text(text))
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _INFERENTIAL_EVIDENCE_PATTERNS)


def normalize_research_brief_lists(
    core_evidence: Any,
    uncertainties: Any,
    invalidation_conditions: Any,
    watch_items: Any,
) -> Dict[str, List[str]]:
    cleaned_core_evidence = sanitize_brief_points(core_evidence)
    cleaned_uncertainties = sanitize_brief_points(uncertainties)
    cleaned_invalidation_conditions = sanitize_brief_points(invalidation_conditions)
    cleaned_watch_items = sanitize_brief_points(watch_items)

    normalized_core_evidence: List[str] = []
    demoted_inferential_items: List[str] = []

    for item in cleaned_core_evidence:
        if contains_inferential_evidence(item):
            demoted_inferential_items.append(item)
            continue
        normalized_core_evidence.append(item)

    for item in demoted_inferential_items:
        if item not in cleaned_uncertainties and len(cleaned_uncertainties) < 5:
            cleaned_uncertainties.append(item)
            continue
        if item not in cleaned_watch_items and len(cleaned_watch_items) < 5:
            cleaned_watch_items.append(item)

    return {
        "core_evidence": normalized_core_evidence[:5],
        "uncertainties": cleaned_uncertainties[:5],
        "invalidation_conditions": cleaned_invalidation_conditions[:5],
        "watch_items": cleaned_watch_items[:5],
    }


def sanitize_display_report_text(text: Any, fallback: str = "") -> str:
    raw_text = sanitize_report_artifacts(text)
    if not raw_text:
        return fallback

    cleaned_lines: List[str] = []
    in_disclaimer_block = False

    for raw_line in raw_text.splitlines():
        line = _normalize_display_line(raw_line.rstrip())
        normalized = _plain_text(line)

        if not normalized:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        if "Disclaimer" in normalized or normalized == RESEARCH_ONLY_DISCLAIMER:
            cleaned_lines.append(line)
            # Disclaimer text is retained in its entirety: actionable content filtering is skipped until the next markdown header
            in_disclaimer_block = True
            continue

        if in_disclaimer_block:
            if line.strip().startswith("#"):
                in_disclaimer_block = False
            else:
                cleaned_lines.append(line)
                continue

        if contains_actionable_content(normalized):
            continue
        if any(pattern.search(normalized) for pattern in _DISPLAY_REPORT_RISK_PATTERNS):
            continue

        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    cleaned_text = _normalize_research_disclaimer(cleaned_text)

    if cleaned_text:
        return cleaned_text[:4000]

    return sanitize_text_block(raw_text, fallback=fallback)


def _build_position_appendix_sections(result_data: Dict[str, Any]) -> List[Dict[str, str]]:
    normalized_sections: List[Dict[str, str]] = []
    seen_keys: set[str] = set()

    raw_sections = result_data.get("appendix_sections")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            raw_title = str(item.get("title") or "").strip()
            key = str(item.get("key") or _POSITION_APPENDIX_TITLE_TO_KEY.get(raw_title) or "").strip()
            title = raw_title or dict(_POSITION_APPENDIX_SECTION_ORDER).get(key, "")
            content = sanitize_display_report_text(item.get("content"))
            if key and title and content and key not in seen_keys:
                normalized_sections.append({"key": key, "title": title, "content": content[:4000]})
                seen_keys.add(key)

    if normalized_sections:
        return normalized_sections

    section_content_by_key: Dict[str, str] = {}
    for key, _title in _POSITION_APPENDIX_SECTION_ORDER:
        cleaned_direct = sanitize_display_report_text(result_data.get(key))
        if cleaned_direct:
            section_content_by_key[key] = cleaned_direct

    raw_detailed_analysis = sanitize_report_artifacts(result_data.get("detailed_analysis"))
    if raw_detailed_analysis:
        current_key: str | None = None
        current_lines: List[str] = []

        def flush_current_section() -> None:
            nonlocal current_key, current_lines
            if not current_key:
                current_lines = []
                return
            cleaned = sanitize_display_report_text("\n".join(current_lines).strip())
            if cleaned and current_key not in section_content_by_key:
                section_content_by_key[current_key] = cleaned
            current_key = None
            current_lines = []

        for raw_line in raw_detailed_analysis.splitlines():
            stripped = raw_line.strip()
            heading_match = _POSITION_APPENDIX_HEADING_PATTERN.match(stripped)
            if heading_match:
                flush_current_section()
                current_key = _POSITION_APPENDIX_TITLE_TO_KEY.get(heading_match.group(1))
                continue
            if current_key:
                current_lines.append(raw_line)

        flush_current_section()

    for key, title in _POSITION_APPENDIX_SECTION_ORDER:
        content = section_content_by_key.get(key)
        if content:
            normalized_sections.append({"key": key, "title": title, "content": content[:4000]})

    return normalized_sections


def filter_analysis_reports(reports: Any) -> Dict[str, str]:
    if not isinstance(reports, dict):
        return {}

    filtered: Dict[str, str] = {}
    for key in SAFE_REPORT_KEYS:
        cleaned = sanitize_text_block(reports.get(key))
        if cleaned:
            filtered[key] = cleaned
    return filtered


def _iter_safe_fragments(reports: Dict[str, str], fallback_summary: str = "") -> Iterable[str]:
    if fallback_summary:
        cleaned_summary = sanitize_text_block(fallback_summary)
        if cleaned_summary:
            for fragment in _SENTENCE_SPLIT_PATTERN.split(cleaned_summary):
                sentence = fragment.strip()
                if sentence and not contains_actionable_content(sentence) and not is_low_signal_text(sentence):
                    yield sentence

    summary_priority = (
        "fundamentals_report",
        "market_report",
        "sector_report",
        "news_report",
        "sentiment_report",
        "index_report",
    )

    for key in summary_priority:
        content = sanitize_text_block(reports.get(key, ""))
        if not content:
            continue
        for fragment in _SENTENCE_SPLIT_PATTERN.split(content):
            sentence = fragment.strip()
            if sentence and not contains_actionable_content(sentence) and not is_low_signal_text(sentence):
                yield sentence


def build_research_summary(reports: Dict[str, str], fallback_summary: str = "") -> str:
    candidate_fragments: List[str] = []
    for fragment in _iter_safe_fragments(reports, fallback_summary):
        normalized = _plain_text(fragment)
        if normalized and normalized not in candidate_fragments:
            candidate_fragments.append(normalized)

    summary_parts = sorted(candidate_fragments, key=_fragment_score, reverse=True)[:3]

    if summary_parts:
        return "；".join(summary_parts)[:800]

    return "This result has been output in research-assisted mode. Please focus on basic data, risk factors and subsequent disclosure information."


def build_key_points(reports: Dict[str, str], key_points: Any, summary: str) -> List[str]:
    cleaned_points: List[str] = []
    if isinstance(key_points, list):
        for item in key_points:
            point = sanitize_text_block(item)
            if point and point not in cleaned_points and not is_low_signal_text(point):
                cleaned_points.append(point)

    if len(cleaned_points) >= 3:
        return cleaned_points[:5]

    for fragment in _iter_safe_fragments(reports, summary):
        if fragment not in cleaned_points and not is_low_signal_text(fragment):
            cleaned_points.append(fragment)
        if len(cleaned_points) >= 5:
            break

    return cleaned_points[:5]


def sanitize_analysis_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    reports = filter_analysis_reports(sanitized.get("reports") or {})
    summary = build_research_summary(reports, sanitized.get("summary", ""))

    sanitized["reports"] = reports
    sanitized["summary"] = summary
    sanitized["key_points"] = build_key_points(reports, sanitized.get("key_points"), summary)

    decision = sanitized.get("decision")
    normalized_action = ""
    if isinstance(decision, dict):
        sanitized_decision: Dict[str, Any] = {}
        action = decision.get("analysis_view") or decision.get("action")
        if isinstance(action, str) and action.strip():
            action_mapping = {
                "BUY": "optimistic",
                "SELL": "Prudence",
                "HOLD": "Neutral",
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "bullish": "optimistic",
                "Bearish": "Prudence",
                "optimistic": "optimistic",
                "Prudence": "Prudence",
                "Neutral": "Neutral",
            }
            normalized_action = action_mapping.get(action.strip(), action.strip())
            sanitized_decision["action"] = normalized_action
            sanitized_decision["analysis_view"] = normalized_action
        confidence = decision.get("confidence")
        if isinstance(confidence, (int, float)):
            sanitized_decision["confidence"] = confidence / 100 if confidence > 1 else confidence
        risk_score = decision.get("risk_score")
        if isinstance(risk_score, (int, float)):
            sanitized_decision["risk_score"] = risk_score / 100 if risk_score > 1 else risk_score
        reasoning = sanitize_text_block(decision.get("reasoning"), fallback=summary)
        if reasoning:
            sanitized_decision["reasoning"] = reasoning[:400]
        decision_summary = sanitize_text_block(decision.get("summary"))
        if decision_summary:
            sanitized_decision["summary"] = decision_summary[:240]
        risk_warning = sanitize_text_block(decision.get("risk_warning"))
        if risk_warning:
            sanitized_decision["risk_warning"] = risk_warning[:200]
        normalized_lists = normalize_research_brief_lists(
            decision.get("core_evidence"),
            decision.get("uncertainties"),
            decision.get("invalidation_conditions"),
            decision.get("watch_items"),
        )
        for field_name in ("core_evidence", "uncertainties", "invalidation_conditions", "watch_items"):
            cleaned_items = normalized_lists.get(field_name, [])
            if cleaned_items:
                sanitized_decision[field_name] = cleaned_items
        sanitized["decision"] = sanitized_decision

    recommendation_parts: List[str] = []
    if normalized_action:
        recommendation_parts.append(f"Research judgment:{normalized_action}")
    if summary:
        recommendation_parts.append(summary[:120])
    recommendation_parts.append("Please continue to pay attention to changes in evidence, risk factors and subsequent disclosures in conjunction with the detailed report.")
    sanitized["recommendation"] = "；".join(part for part in recommendation_parts if part)[:240] or GENERIC_RESEARCH_RECOMMENDATION

    return sanitized


def sanitize_position_analysis_payload(
    result_data: Dict[str, Any],
    position_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    appendix_sections = _build_position_appendix_sections(sanitized)
    action_reason, user_detailed_analysis, user_view = _build_position_user_action_reason(sanitized, position_snapshot)
    summary = action_reason or sanitize_position_text_block(
        sanitized.get("summary") or sanitized.get("action_reason") or sanitized.get("detailed_analysis"),
        fallback="This position research has been converted into research observation, please make independent judgment based on your own strategy.",
    )

    sanitized["action"] = "hold"
    sanitized["action_reason"] = action_reason or "Currently, only research conclusions, risk warnings and observation points are retained, and no execution trading suggestions are provided."
    sanitized["price_targets"] = {}
    sanitized["suggested_quantity"] = None
    sanitized["suggested_amount"] = None
    sanitized["risk_assessment"] = sanitize_text_block(
        sanitized.get("risk_assessment"),
        fallback="Please focus on position fluctuations, industry changes and announcement risks.",
    )
    sanitized["opportunity_assessment"] = sanitize_text_block(
        sanitized.get("opportunity_assessment"),
        fallback="Please continue to track operating quality, valuation changes and potential catalytic events.",
    )
    sanitized["detailed_analysis"] = user_detailed_analysis
    sanitized["user_view"] = user_view
    sanitized["appendix_sections"] = appendix_sections
    sanitized["summary"] = summary
    sanitized["recommendation"] = GENERIC_POSITION_RECOMMENDATION

    confidence = sanitized.get("confidence")
    if isinstance(confidence, (int, float)):
        sanitized["confidence"] = max(0.0, min(100.0, float(confidence)))

    return sanitized


def sanitize_trade_review_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    sanitized["summary"] = sanitize_review_text_block(
        sanitized.get("summary"),
        fallback=GENERIC_REVIEW_SUMMARY,
    )
    sanitized["strengths"] = sanitize_review_points(sanitized.get("strengths"))
    sanitized["weaknesses"] = sanitize_review_points(sanitized.get("weaknesses"))
    sanitized["suggestions"] = sanitize_review_points(
        sanitized.get("suggestions"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["timing_analysis"] = sanitize_review_detail_block(
        sanitized.get("timing_analysis"),
        fallback="Please focus on reviewing whether the basis for entry and exit is sufficient, rather than giving new trading instructions.",
    )
    sanitized["position_analysis"] = sanitize_review_detail_block(
        sanitized.get("position_analysis"),
        fallback="Please focus on reviewing the basis for position management and risk exposure, and do not provide specific position adjustment plans.",
    )
    sanitized["emotion_analysis"] = sanitize_review_detail_block(
        sanitized.get("emotion_analysis"),
        fallback="Please focus on reviewing the issues of emotional control and discipline enforcement.",
    )
    sanitized["attribution_analysis"] = sanitize_review_detail_block(
        sanitized.get("attribution_analysis"),
        fallback="Please focus on reviewing the evidence attribution of the sources of gains and losses.",
    )
    sanitized["plan_adherence"] = sanitize_review_text_block(sanitized.get("plan_adherence"))
    sanitized["plan_deviation"] = sanitize_review_text_block(sanitized.get("plan_deviation"))
    sanitized.pop("optimal_pnl", None)
    sanitized.pop("missed_profit", None)
    sanitized.pop("avoided_loss", None)

    return sanitized


def sanitize_periodic_review_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    sanitized["summary"] = sanitize_review_text_block(
        sanitized.get("summary"),
        fallback=GENERIC_REVIEW_SUMMARY,
    )
    sanitized["trading_style"] = sanitize_review_text_block(
        sanitized.get("trading_style"),
        fallback="Please conduct a phased review from the perspective of style stability, discipline execution and research preparation adequacy.",
    )
    sanitized["common_mistakes"] = sanitize_review_points(sanitized.get("common_mistakes"))
    sanitized["improvement_areas"] = sanitize_review_points(
        sanitized.get("improvement_areas"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["action_plan"] = sanitize_review_points(
        sanitized.get("action_plan"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["best_trade"] = sanitize_review_text_block(sanitized.get("best_trade"))
    sanitized["worst_trade"] = sanitize_review_text_block(sanitized.get("worst_trade"))

    return sanitized

# === error_formatter.py ===
"""
Error message formatting tool

Convert technical errors into user-friendly error messages that clearly indicate the problem (data source, large model, configuration, etc.)
"""

import re
from typing import Dict, Optional, Tuple
from enum import Enum


class ErrorCategory(str, Enum):
    """Error category"""
    LLM_API_KEY = "llm_api_key"  # Large model API Key error
    LLM_NETWORK = "llm_network"  # Large model network errors
    LLM_QUOTA = "llm_quota"  # Large model quota/limiting error
    LLM_CONTENT_FILTER = "llm_content_filter"  # Large model content review failed
    LLM_OTHER = "llm_other"  # Other errors in large models

    DATA_SOURCE_API_KEY = "data_source_api_key"  # Data source API Key error
    DATA_SOURCE_NETWORK = "data_source_network"  # Data source network error
    DATA_SOURCE_NOT_FOUND = "data_source_not_found"  # Data source cannot find data
    DATA_SOURCE_OTHER = "data_source_other"  # Other data source errors

    STOCK_CODE_INVALID = "stock_code_invalid"  # Invalid stock code
    NETWORK = "network"  # Network connection error
    SYSTEM = "system"  # System error
    UNKNOWN = "unknown"  # unknown error


class ErrorFormatter:
    """Error message formatter"""
    
    # LLM Vendor name mapping
    LLM_PROVIDERS = {
        "google": "Google Gemini",
        "dashscope": "Ali Bailian (Tongyi Qianwen)",
        "qianfan": "Baidu Qianfan",
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "openrouter": "OpenRouter",
        "aihubmix": "AIHubMix",
        "anthropic": "Anthropic Claude",
        "zhipu": "Wisdom spectrum AI",
        "moonshot": "Dark Side of the Moon (Kimi)",
    }
    
    # Data source name mapping
    DATA_SOURCES = {
        "tushare": "Tushare",
        "akshare": "AKShare",
        "baostock": "BaoStock",
        "finnhub": "Finnhub",
        "mongodb": "MongoDB cache",
    }
    
    @classmethod
    def format_error(cls, error_message: str, context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Format error message
        
        Args:
            error_message: Original error message
            context: Context information (optional), including llm_provider, model, data_source Wait
            
        Returns:
            {
                "category": "Error category",
                "title": "error title",
                "message": "User-friendly error description",
                "suggestion": "Solution suggestions",
                "technical_detail": "Technical details (optional)"
            }
        """
        context = context or {}
        
        # Classification error
        category, provider_or_source = cls._categorize_error(error_message, context)
        
        # Generate friendly reminders
        return cls._generate_friendly_message(category, provider_or_source, error_message, context)

    @classmethod
    def format_user_message(
        cls,
        error_message: str,
        context: Optional[Dict] = None,
        include_suggestion: bool = True,
    ) -> str:
        """Generate Chinese messages that can be returned directly to the front end or displayed to the user."""
        formatted = cls.format_error(error_message, context)
        message = formatted.get("message", "Operation failed")
        suggestion = formatted.get("suggestion", "")

        if include_suggestion and suggestion:
            return f"{message}\n\n Recommended treatment:\n{suggestion}"
        return message
    
    @classmethod
    def _categorize_error(cls, error_message: str, context: Dict) -> Tuple[ErrorCategory, Optional[str]]:
        """
        Classification error
        
        Returns:
            (Error category, Related vendor/data source name)
        """
        error_lower = error_message.lower()
        
        # 1. Check if it is an LLM related error
        llm_provider = context.get("llm_provider") or cls._extract_llm_provider(error_message)
        
        if llm_provider or any(keyword in error_lower for keyword in [
            "api key", "api_key", "apikey", "invalid_api_key", "authentication", 
            "unauthorized", "401", "402", "403", "payment required", "billing",
            "quota", "insufficient_quota", "balance", "Balance", "Account balance",
            "gemini", "openai", "dashscope", "qianfan", "deepseek", "openrouter", "aihubmix"
        ]):
            # LLM API Key Error
            if any(keyword in error_lower for keyword in [
                "api key", "api_key", "apikey", "invalid", "authentication", 
                "unauthorized", "401", "invalid_api_key", "api key not valid"
            ]):
                return ErrorCategory.LLM_API_KEY, llm_provider
            
            # LLM Quota/limiting error
            if any(keyword in error_lower for keyword in [
                "quota", "rate limit", "too many requests", "429", "resource exhausted",
                "insufficient_quota", "billing", "402", "payment required",
                "insufficient balance", "balance", "credit", "recharge", "Balance", "Recharge"
            ]):
                return ErrorCategory.LLM_QUOTA, llm_provider

            # LLM Content review failed
            if any(keyword in error_lower for keyword in [
                "data_inspection_failed", "inappropriate content", "content filter",
                "Content moderation", "Sensitive content", "Illegal content", "content policy"
            ]):
                return ErrorCategory.LLM_CONTENT_FILTER, llm_provider

            # LLM network error
            if any(keyword in error_lower for keyword in [
                "connection", "network", "timeout", "unreachable", "dns", "ssl"
            ]):
                return ErrorCategory.LLM_NETWORK, llm_provider

            # LLM Other errors
            return ErrorCategory.LLM_OTHER, llm_provider
        
        # 2. Check whether it is a data source related error
        data_source = context.get("data_source") or cls._extract_data_source(error_message)
        
        if data_source or any(keyword in error_lower for keyword in [
            "tushare", "akshare", "baostock", "finnhub", "data source", "data source"
        ]):
            # Data source API Key error
            if any(keyword in error_lower for keyword in [
                "token", "api key", "authentication", "unauthorized"
            ]):
                return ErrorCategory.DATA_SOURCE_API_KEY, data_source
            
            # Data source cannot find data
            if any(keyword in error_lower for keyword in [
                "not found", "no data", "empty", "No data", "not found"
            ]):
                return ErrorCategory.DATA_SOURCE_NOT_FOUND, data_source
            
            # Data source network error
            if any(keyword in error_lower for keyword in [
                "connection", "network", "timeout"
            ]):
                return ErrorCategory.DATA_SOURCE_NETWORK, data_source
            
            # Other data source errors
            return ErrorCategory.DATA_SOURCE_OTHER, data_source
        
        # 3. Check if it is a stock code error
        if any(keyword in error_lower for keyword in [
            "Stock code", "stock code", "symbol", "invalid code", "Invalid code"
        ]):
            return ErrorCategory.STOCK_CODE_INVALID, None
        
        # 4. Check if it is a network error
        if any(keyword in error_lower for keyword in [
            "connection", "network", "timeout", "unreachable", "dns"
        ]):
            return ErrorCategory.NETWORK, None
        
        # 5. System error
        if any(keyword in error_lower for keyword in [
            "internal error", "server error", "500", "System error"
        ]):
            return ErrorCategory.SYSTEM, None
        
        # 6. unknown error
        return ErrorCategory.UNKNOWN, None
    
    @classmethod
    def _extract_llm_provider(cls, error_message: str) -> Optional[str]:
        """Extract LLM vendor from error message"""
        error_lower = error_message.lower()
        for key, name in cls.LLM_PROVIDERS.items():
            if key in error_lower or name.lower() in error_lower:
                return key
        return None
    
    @classmethod
    def _extract_data_source(cls, error_message: str) -> Optional[str]:
        """Extract data source from error message"""
        error_lower = error_message.lower()
        for key, name in cls.DATA_SOURCES.items():
            if key in error_lower or name.lower() in error_lower:
                return key
        return None
    
    @classmethod
    def _generate_friendly_message(
        cls, 
        category: ErrorCategory, 
        provider_or_source: Optional[str],
        original_error: str,
        context: Dict
    ) -> Dict[str, str]:
        """Generate user-friendly error messages"""
        
        # Get friendly vendor/data source names
        friendly_name = None
        if provider_or_source:
            friendly_name = cls.LLM_PROVIDERS.get(provider_or_source) or \
                           cls.DATA_SOURCES.get(provider_or_source) or \
                           provider_or_source
        
        # Generate messages based on categories
        if category == ErrorCategory.LLM_API_KEY:
            return {
                "category": "Large model account authentication error",
                "title": f"❌ {friendly_name or 'large model'} Account authentication failed",
                "message": f"{friendly_name or 'large model'} If the call fails, there is usually a problem with the account, API Key or model authorization configuration.",
                "suggestion": (
                    "Please check the following points:\n"
                    f"1. In System Settings → Check in Large Model Configuration  {friendly_name or 'The model'} Is the API Key correct?\n"
                    "2. Confirm that the account is not in arrears or deactivated, and the API Key is activated and has not expired.\n"
                    "3. Confirm that the current account has permission to access the selected model\n"
                    "4. If you have just updated the key, save it and re-initiate the request.\n"
                    "5. If you still have problems, switch to other available large models"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.LLM_QUOTA:
            return {
                "category": "Large model account limit error",
                "title": f"⚠️ {friendly_name or 'large model'} Account quota is insufficient or limited",
                "message": f"{friendly_name or 'large model'} The call failure is usually caused by account balance, package quota, call quota or current limit.",
                "suggestion": (
                    "Please try the following solutions:\n"
                    f"1. Check {friendly_name or 'The model'} Account balance, packages and remaining call limit\n"
                    "2. Confirm whether the current model requires separate paid permissions\n"
                    "3. If it is current limiting, wait for a while and try again.\n"
                    "4. Recharge, upgrade your plan or switch to other available large models when necessary"
                ),
                "technical_detail": original_error
            }

        elif category == ErrorCategory.LLM_CONTENT_FILTER:
            return {
                "category": "Content review failed",
                "title": f"🚫 {friendly_name or 'large model'} Content review failed",
                "message": f"{friendly_name or 'large model'} It was detected that the input content may contain inappropriate content and the request was refused to be processed.",
                "suggestion": (
                    "This is usually due to sensitive words or inappropriate expressions in the analysis. Suggestions:\n"
                    "1. This may be because stock news or financial reports contain sensitive words (such as politics, violence, etc.)\n"
                    "2. Try switching to other large models (e.g. DeepSeek, Google Gemini)\n"
                    "3. If it is Alibaba Bailian, you can try to use the qwen-max or qwen-plus model\n"
                    "4. Contact technical support to report this issue and we will optimize the content filtering logic\n"
                    "\n"
                    "💡 Tip: Different large models have different content moderation policies. Switching models can usually solve this problem."
                ),
                "technical_detail": original_error
            }

        elif category == ErrorCategory.LLM_NETWORK:
            return {
                "category": "Large model network errors",
                "title": f"🌐 Unable to connect to {friendly_name or 'large model'}",
                "message": f"connect {friendly_name or 'large model'} The network timed out or the connection failed during service.",
                "suggestion": (
                    "Please check the following points:\n"
                    "1. Check whether the network connection is normal\n"
                    f"2. {friendly_name or 'The service'} May require scientific Internet access (such as Google Gemini)\n"
                    "3. Check firewall or proxy settings\n"
                    "4. Try again later or switch to another larger model"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.LLM_OTHER:
            return {
                "category": "Large model call error",
                "title": f"❌ {friendly_name or 'large model'} call failed",
                "message": f"call {friendly_name or 'large model'} An error occurred.",
                "suggestion": (
                    "Suggestions:\n"
                    "1. Check if the model configuration is correct\n"
                    "2. See the technical details for specific errors\n"
                    "3. Try switching to other large models\n"
                    "4. If the problem persists, please contact technical support"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.DATA_SOURCE_API_KEY:
            return {
                "category": "Data source configuration error",
                "title": f"❌ {friendly_name or 'data source'} Token/API Key Invalid",
                "message": f"{friendly_name or 'data source'} The Token or API Key is invalid or not configured.",
                "suggestion": (
                    "Please check the following points:\n"
                    f"1. In System Settings → Check in Data Source Configuration {friendly_name or 'The data source'} configuration\n"
                    "2. Confirm whether the Token/API Key is correct and valid\n"
                    "3. Check if the account is activated\n"
                    "4. The system will automatically try to use an alternate data source"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.DATA_SOURCE_NOT_FOUND:
            return {
                "category": "Data acquisition failed",
                "title": f"📊 {friendly_name or 'data source'} No data found",
                "message": f"from {friendly_name or 'data source'} Failed to obtain stock data. It may be that the stock code does not exist or the data has not been updated yet.",
                "suggestion": (
                    "Suggestions:\n"
                    "1. Check if the stock code is correct\n"
                    "2. Confirm whether the stock is listed\n"
                    "3. The system will automatically try to use other data sources\n"
                    "4. If it is a new stock, you may need to wait for data updates"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.DATA_SOURCE_NETWORK:
            return {
                "category": "Data source network error",
                "title": f"🌐 Unable to connect to {friendly_name or 'data source'}",
                "message": f"connect {friendly_name or 'data source'} The network times out or the connection fails.",
                "suggestion": (
                    "Please check:\n"
                    "1. Is the network connection normal?\n"
                    "2. Is the data source service available?\n"
                    "3. The system will automatically try to use an alternate data source\n"
                    "4. Try again later"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.DATA_SOURCE_OTHER:
            return {
                "category": "Data source error",
                "title": f"❌ {friendly_name or 'data source'} call failed",
                "message": f"from {friendly_name or 'data source'} An error occurred while retrieving data.",
                "suggestion": (
                    "Suggestions:\n"
                    "1. The system will automatically try to use an alternate data source\n"
                    "2. See the technical details for specific errors\n"
                    "3. Try again later\n"
                    "4. If the problem persists, please contact technical support"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.STOCK_CODE_INVALID:
            return {
                "category": "Stock code error",
                "title": "❌ Invalid stock code",
                "message": "The entered stock symbol format is incorrect or does not exist.",
                "suggestion": (
                    "Please check:\n"
                    "1. A Stock code format: 6 digits (such as 000001, 600000)\n"
                    "2. Hong Kong stock code format: 5 digits (such as 00700)\n"
                    "3. U.S. stock code format: stock code (such as AAPL, TSLA)\n"
                    "4. Confirm whether the stock is listed"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.NETWORK:
            return {
                "category": "Network connection error",
                "title": "🌐 Network connection failed",
                "message": "The network connection has timed out or the service cannot be accessed.",
                "suggestion": (
                    "Please check:\n"
                    "1. Is the network connection normal?\n"
                    "2. Is the server accessible?\n"
                    "3. Firewall or proxy settings\n"
                    "4. Try again later"
                ),
                "technical_detail": original_error
            }
        
        elif category == ErrorCategory.SYSTEM:
            return {
                "category": "System error",
                "title": "⚠️ System internal error",
                "message": "An internal error occurred while the system was processing the request.",
                "suggestion": (
                    "Suggestions:\n"
                    "1. Try again later\n"
                    "2. If the problem persists, please contact technical support\n"
                    "3. Provide technical details for troubleshooting"
                ),
                "technical_detail": original_error
            }
        
        else:  # UNKNOWN
            return {
                "category": "unknown error",
                "title": "❌ Analysis failed",
                "message": "An error occurred during analysis.",
                "suggestion": (
                    "Suggestions:\n"
                    "1. Check whether the input parameters are correct\n"
                    "2. See the technical details for specific errors\n"
                    "3. Try again later\n"
                    "4. If the problem persists, please contact technical support"
                ),
                "technical_detail": original_error
            }


# === report_exporter.py ===
"""
Report export tool - supports Markdown, Word, PDF formats

Depends on installation:
    pip install pypandoc markdown

PDF Export requires additional tools:
    - wkhtmltopdf (Recommended): https://wkhtmltopdf.org/downloads.html
    - or LaTeX: https://www.latex-project.org/get/
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Analyst English ID to Chinese name mapping (for report display)
ANALYST_ID_TO_CHINESE: dict = {
    # Macro Analyst
    "index_analyst": "Market environment analyst",
    "index_analyst_v2": "Market environment analyst",
    "sector_analyst": "Industry sector research analyst",
    "sector_analyst_v2": "Industry sector research analyst",
    # Analyst Team
    "market_analyst": "Market Technical Analyst",
    "market_analyst_v2": "Market Technical Analyst",
    "sentiment_analyst": "Sentiment Research Analyst",
    "emotion_analyst": "Sentiment Research Analyst",
    "emotion_analyst_v2": "Sentiment Research Analyst",
    "news_analyst": "News Research Analyst",
    "news_analyst_v2": "News Research Analyst",
    "fundamentals_analyst": "fundamental analyst",
    "fundamentals_analyst_v2": "fundamental analyst",
    "social_media_analyst": "social media research analyst",
    "social_analyst_v2": "social media research analyst",
    # research team
    "bull_researcher": "optimistic scenario argument",
    "bull_researcher_v2": "optimistic scenario argument",
    "bear_researcher": "Prudential Scenario Argument",
    "bear_researcher_v2": "Prudential Scenario Argument",
    "research_manager": "Summary of research conclusions",
    "research_manager_v2": "Summary of research conclusions",
    # risk management team
    "risky_analyst": "Highly resilient scenario assessment",
    "risky_analyst_v2": "Highly resilient scenario assessment",
    "safe_analyst": "Defense Scenario Assessment",
    "safe_analyst_v2": "Defense Scenario Assessment",
    "neutral_analyst": "Baseline Scenario Assessment",
    "neutral_analyst_v2": "Baseline Scenario Assessment",
    "risk_manager": "Risk review summary",
    "risk_manager_v2": "Risk review summary",
    # Research integration and review
    "trader": "User version research briefing",
    "trader_v2": "User version research briefing",
    "timing_analyst": "timing analyst",
    "timing_analyst_v2": "timing analyst",
    "position_analyst": "Position Analyst",
    "position_analyst_v2": "Position Analyst",
    "attribution_analyst": "attribution analyst",
    "attribution_analyst_v2": "attribution analyst",
    "review_manager": "Review summary expert",
    "review_manager_v2": "Review summary expert",
    # Position research
    "position_advisor": "Position consultant",
    "pa_technical": "technical researcher",
    "pa_fundamental": "Fundamental Researcher",
    "pa_risk": "risk assessor",
    "pa_advisor": "conclusion integrator",
}

EXPORT_SANITIZED_MODULE_KEYS = {
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
    "bull_researcher",
    "bull_researcher_v2",
    "bear_researcher",
    "bear_researcher_v2",
    "risky_analyst",
    "risky_analyst_v2",
    "safe_analyst",
    "safe_analyst_v2",
    "neutral_analyst",
    "neutral_analyst_v2",
    "research_team_decision",
    "risk_management_decision",
}

MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
CHINESE_SECTION_PREFIX_PATTERN = re.compile(r"^[One, two, three, four, five, six, seven, eight, nine hundred]+[, \.]\s*")

# Check if dependencies are available
try:
    import markdown
    import pypandoc

    # Check if pandoc is available
    try:
        pypandoc.get_pandoc_version()
        PANDOC_AVAILABLE = True
        logger.info("✅ Pandoc Available")
    except OSError:
        PANDOC_AVAILABLE = False
        logger.warning("⚠️ Pandoc Not available, Word and PDF export functionality will not be available")

    EXPORT_AVAILABLE = True
except ImportError as e:
    EXPORT_AVAILABLE = False
    PANDOC_AVAILABLE = False
    logger.warning(f"⚠️ Export function dependency package is missing: {e}")
    logger.info("💡 Please install: pip install pypandoc markdown")

# Check out WeasyPrint (recommended, pure Python, no external tools required)
WEASYPRINT_AVAILABLE = False
WEASYPRINT_ERROR = None

try:
    import weasyprint
    WEASYPRINT_AVAILABLE = True
    logger.info("✅ WeasyPrint Available (PDF generation tool, recommended)")
except ImportError:
    logger.warning("⚠️ WeasyPrint Not installed, PDF export functionality will use pdfkit")
    logger.info("💡 Installation method: pip install weasyprint")
except Exception as e:
    WEASYPRINT_ERROR = str(e)
    logger.warning(f"⚠️ WeasyPrint Detection failed: {e}")

# Check pdfkit (alternative, requires wkhtmltopdf)
PDFKIT_AVAILABLE = False
PDFKIT_ERROR = None

try:
    import pdfkit
    # Check if wkhtmltopdf is installed
    try:
        pdfkit.configuration()
        PDFKIT_AVAILABLE = True
        logger.info("✅ pdfkit + wkhtmltopdf Available (PDF generation tool, optional)")
    except Exception as e:
        PDFKIT_ERROR = str(e)
        logger.warning("⚠️ wkhtmltopdf Not installed, pdfkit is not available")
        logger.info("💡 Installation method: https://wkhtmltopdf.org/downloads.html")
except ImportError:
    logger.warning("⚠️ pdfkit Not installed")
    logger.info("💡 Installation method: pip install pdfkit")
except Exception as e:
    PDFKIT_ERROR = str(e)
    logger.warning(f"⚠️ pdfkit Detection failed: {e}")


class ReportExporter:
    """Report exporter - supports Markdown, Word, PDF formats"""

    def __init__(self):
        self.export_available = EXPORT_AVAILABLE
        self.pandoc_available = PANDOC_AVAILABLE
        self.weasyprint_available = WEASYPRINT_AVAILABLE
        self.pdfkit_available = PDFKIT_AVAILABLE

        logger.info("📋 ReportExporter initialization:")
        logger.info(f"  - export_available: {self.export_available}")
        logger.info(f"  - pandoc_available: {self.pandoc_available}")
        logger.info(f"  - pdfkit_available: {self.pdfkit_available}")

    @staticmethod
    def _normalize_heading_text(text: str) -> str:
        normalized = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
        return normalized.casefold()

    def _strip_duplicate_leading_heading(self, content: str, title: str) -> str:
        lines = content.splitlines()
        normalized_title = self._normalize_heading_text(title)

        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            heading_match = MARKDOWN_HEADING_PATTERN.match(stripped)
            if not heading_match:
                break

            if self._normalize_heading_text(heading_match.group(2)) == normalized_title:
                remaining = lines[index + 1 :]
                while remaining and not remaining[0].strip():
                    remaining.pop(0)
                return "\n".join(remaining)

            break

        return content

    @staticmethod
    def _demote_markdown_headings(content: str) -> str:
        demoted_lines = []
        in_code_block = False

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                demoted_lines.append(line)
                continue

            if not in_code_block:
                heading_match = MARKDOWN_HEADING_PATTERN.match(line)
                if heading_match:
                    heading_level = min(len(heading_match.group(1)) + 1, 6)
                    demoted_lines.append(f"{'#' * heading_level} {heading_match.group(2)}")
                    continue

            demoted_lines.append(line)

        return "\n".join(demoted_lines)

    @staticmethod
    def _normalize_section_title(text: str) -> str:
        normalized = text.strip()
        if normalized.startswith("**") and normalized.endswith("**") and len(normalized) > 4:
            normalized = normalized[2:-2].strip()
        return CHINESE_SECTION_PREFIX_PATTERN.sub("", normalized).strip()

    @staticmethod
    def _strip_emphasis_markers(text: str) -> str:
        normalized = text.strip()
        if normalized.startswith("**") and normalized.endswith("**") and len(normalized) > 4:
            return normalized[2:-2].strip()
        return normalized

    def _normalize_intra_module_headings(self, content: str) -> str:
        normalized_lines = []
        in_code_block = False

        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                normalized_lines.append(line)
                continue

            if in_code_block or not stripped:
                normalized_lines.append(line)
                continue

            heading_match = MARKDOWN_HEADING_PATTERN.match(line)
            if heading_match:
                heading_text = self._normalize_section_title(heading_match.group(2))
                normalized_lines.append(f"{heading_match.group(1)} {heading_text}")
                continue

            plain_line = self._strip_emphasis_markers(stripped)
            if CHINESE_SECTION_PREFIX_PATTERN.match(plain_line):
                section_title = self._normalize_section_title(stripped)
                if section_title and len(section_title) <= 30 and not re.search(r"[，,。！？；：:]", section_title):
                    normalized_lines.append(f"## {section_title}")
                    continue

            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    @staticmethod
    def _normalize_disclaimer(content: str) -> str:
        return re.sub(
            r"(?is)(?:\*\*)?Disclaimer(?:\*\*)?[: :].*?(?:Make investment decisions independently.|Please consult professional advisors if necessary.)",
            f"**Disclaimer**: {RESEARCH_ONLY_DISCLAIMER}",
            content,
        )

    def _normalize_module_content(self, module_key: str, title: str, module_content: str) -> str:
        normalized_content = sanitize_report_artifacts(module_content.strip()) or module_content.strip()
        if module_key in EXPORT_SANITIZED_MODULE_KEYS:
            normalized_content = sanitize_display_report_text(normalized_content, fallback=normalized_content)

        if not normalized_content and module_key == "news_report":
            normalized_content = "The tool results were not successfully expanded into news reports, and the current news conclusions still need to be verified."

        normalized_content = self._normalize_intra_module_headings(normalized_content)
        normalized_content = self._normalize_disclaimer(normalized_content)
        normalized_content = self._strip_duplicate_leading_heading(normalized_content, title)
        normalized_content = self._demote_markdown_headings(normalized_content)
        return normalized_content.strip()
    
    def generate_markdown_report(self, report_doc: Dict[str, Any]) -> str:
        """Generate Markdown format report"""
        logger.info("📝 Generate Markdown report...")
        
        stock_symbol = report_doc.get("stock_symbol", "unknown")
        analysis_date = report_doc.get("analysis_date", "")
        analysts = report_doc.get("analysts", [])
        research_depth = report_doc.get("research_depth", 1)
        reports = report_doc.get("reports", {})
        summary = report_doc.get("summary", "")
        
        content_parts = []
        
        # Title and meta information
        content_parts.append(f"# {stock_symbol} Stock research reports")
        content_parts.append("")
        content_parts.append(f"**Study date**: {analysis_date}")
        if analysts:
            analyst_names = [
                ANALYST_ID_TO_CHINESE.get(a, a) for a in analysts
            ]
            content_parts.append(f"**analyst**: {', '.join(analyst_names)}")
        content_parts.append(f"**Research depth**: {research_depth}")
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")
        
        # Research summary
        if summary:
            content_parts.append("## 📊 Research summary")
            content_parts.append("")
            content_parts.append(summary)
            content_parts.append("")
            content_parts.append("---")
            content_parts.append("")
        
        # Contents of each module (in order of presentation)
        module_order = [
            # end user output
            "trader_investment_plan",
            "final_trade_decision",

            # Macro analysis (priority for display)
            "index_report",
            "sector_report",

            # Basic analysis module
            "company_overview",
            "financial_analysis",
            "technical_analysis",
            "market_analysis",
            "risk_analysis",
            "valuation_analysis",
            "investment_recommendation",

            # individual stock analysis report
            "market_report",
            "fundamentals_report",
            "sentiment_report",
            "news_report",

            # Research team conclusion
            "bull_researcher",
            "bear_researcher",
            "neutral_analyst",
            "research_team_decision",

            # Risk team analysis
            "risky_analyst",
            "safe_analyst",
            "risk_management_decision",

            # decision report
        ]
        
        module_titles = {
            # Basic analysis module
            "company_overview": "🏢 Company Profile",
            "financial_analysis": "💰 financial analysis",
            "technical_analysis": "📈 technical analysis",
            "market_analysis": "🌍 market analysis",
            "risk_analysis": "⚠️ risk analysis",
            "valuation_analysis": "💎 Valuation analysis",
            "investment_recommendation": "🎯 Summary of research conclusions",

            # decision report
            "final_trade_decision": "📝 Comprehensive research conclusion",
            "investment_plan": "📋 Research Manager Briefing",
            "trader_investment_plan": "🧩 User version research briefing",
            "research_team_decision": "🤝 Summary of research conclusions",
            "risk_management_decision": "🛡️ Risk review conclusion",

            # research team researcher
            "bull_researcher": "🌤️ optimistic scenario argument",
            "bear_researcher": "🌧️ Prudential Scenario Argument",

            # Risk Team Analyst
            "risky_analyst": "⚡ Highly resilient scenario assessment",
            "safe_analyst": "🛡️ Defense Scenario Assessment",
            "neutral_analyst": "⚖️ Baseline Scenario Assessment",

            # individual stock analysis report
            "market_report": "📈 Market Technology Research Report",
            "fundamentals_report": "💰 Fundamental Research Report",
            "sentiment_report": "💭 Emotion research report",
            "news_report": "📰 news research report",

            # Macro analysis report
            "sector_report": "🏭 Industry sector research report",
            "index_report": "📊 Market Environment Research Report",
        }
        
        # Add modules in order
        for module_key in module_order:
            if module_key in reports:
                module_content = reports[module_key]
                # 🔥 Handle content in dictionary format (e.g. final_trade_decision may be a dictionary)
                if isinstance(module_content, dict):
                    # If there is a content field, use it
                    if "content" in module_content:
                        module_content = module_content["content"]
                    else:
                        # Otherwise convert to formatted string
                        import json
                        module_content = json.dumps(module_content, ensure_ascii=False, indent=2)
                
                if isinstance(module_content, str) and module_content.strip():
                    title = module_titles.get(module_key, module_key)
                    module_content = self._normalize_module_content(module_key, title, module_content)
                    content_parts.append(f"## {title}")
                    content_parts.append("")
                    content_parts.append(module_content)
                    content_parts.append("")
                    content_parts.append("---")
                    content_parts.append("")
        
        # Add other modules not listed
        # 🔥 Blacklist: Explicitly excluded fields (to avoid confusion with other fields)
        excluded_fields = {
            "investment_plan",  # Replaced by trader_investment_plan
        }

        for module_key, module_content in reports.items():
            if module_key not in module_order and module_key not in excluded_fields:
                # 🔥 Processing content in dictionary format
                if isinstance(module_content, dict):
                    if "content" in module_content:
                        module_content = module_content["content"]
                    else:
                        import json
                        module_content = json.dumps(module_content, ensure_ascii=False, indent=2)

                if isinstance(module_content, str) and module_content.strip():
                    # 🔥 Use a friendly title if one exists
                    title = module_titles.get(module_key, module_key.replace("_", " ").title())
                    module_content = self._normalize_module_content(module_key, title, module_content)
                    content_parts.append(f"## {title}")
                    content_parts.append("")
                    content_parts.append(module_content)
                    content_parts.append("")
                    content_parts.append("---")
                    content_parts.append("")
        
        # footer
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")
        content_parts.append("*This report is automatically generated by TradingAgents-CN*")
        content_parts.append("")
        
        markdown_content = "\n".join(content_parts)
        logger.info(f"✅ Markdown Report generation completed, length: {len(markdown_content)} character")
        
        return markdown_content
    
    def _clean_markdown_for_pandoc(self, md_content: str) -> str:
        """Clean up Markdown content to avoid pandoc parsing issues"""
        import re

        # Remove content that may cause YAML parsing issues
        # If there is at the beginning "---", Add a blank line in front
        if md_content.strip().startswith("---"):
            md_content = "\n" + md_content

        # 🔥 Remove HTML tags and styles that may cause vertical alignment
        # Remove writing-mode related styles
        md_content = re.sub(r'<[^>]*writing-mode[^>]*>', '', md_content, flags=re.IGNORECASE)
        md_content = re.sub(r'<[^>]*text-orientation[^>]*>', '', md_content, flags=re.IGNORECASE)

        # Remove <div> The style attribute in the tag (may include vertical style)
        md_content = re.sub(r'<div\s+style="[^"]*">', '<div>', md_content, flags=re.IGNORECASE)
        md_content = re.sub(r'<span\s+style="[^"]*">', '<span>', md_content, flags=re.IGNORECASE)

        # 🔥 Remove HTML tags that may be causing problems
        # Keep the basic Markdown format and remove complex HTML
        md_content = re.sub(r'<style[^>]*>.*?</style>', '', md_content, flags=re.DOTALL | re.IGNORECASE)

        # 🔥 Make sure all paragraphs are normal horizontal text
        # Add clear line breaks before and after each paragraph to avoid Pandoc misjudgments
        lines = md_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip empty lines
            if not line.strip():
                cleaned_lines.append(line)
                continue

            # If it is Markdown syntax such as titles, lists, tables, etc., keep it as is
            if line.strip().startswith(('#', '-', '*', '|', '>', '```', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                cleaned_lines.append(line)
            else:
                # Ordinary paragraphs: Make sure there are no special characters that cause vertical alignment
                cleaned_lines.append(line)

        md_content = '\n'.join(cleaned_lines)

        return md_content

    def _create_pdf_css(self) -> str:
        """Create PDF stylesheets to control table pagination and text direction"""
        return """
<style>
/* 🔥 Force all text to be displayed horizontally (fix Chinese vertical display problem) */
* {
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

body {
    writing-mode: horizontal-tb !important;
    direction: ltr !important;
}

/* paragraphs and text */
p, div, span, td, th, li {
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* Table style - allow cross-page */
table {
    width: 100%;
    border-collapse: collapse;
    page-break-inside: auto;
    writing-mode: horizontal-tb !important;
}

/* Table rows - avoid page breaks in the middle of rows */
tr {
    page-break-inside: avoid;
    page-break-after: auto;
}

/* Header - Repeat on every page */
thead {
    display: table-header-group;
}

/* table cell */
td, th {
    padding: 8px;
    border: 1px solid #ddd;
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* Header style */
th {
    background-color: #f2f2f2;
    font-weight: bold;
}

/* Avoid pagination immediately after title */
h1, h2, h3, h4, h5, h6 {
    page-break-after: avoid;
    writing-mode: horizontal-tb !important;
}

/* Avoid pagination in the middle of list items */
li {
    page-break-inside: avoid;
}

/* code block */
pre, code {
    writing-mode: horizontal-tb !important;
    white-space: pre-wrap;
    word-wrap: break-word;
}
</style>
"""
    
    def generate_docx_report(self, report_doc: Dict[str, Any]) -> bytes:
        """Generate reports in Word document format"""
        logger.info("📄 Start generating a Word document...")

        if not self.pandoc_available:
            raise Exception("Pandoc Unavailable, unable to generate Word document. Please install pandoc or use Markdown format to export.")

        # Generate Markdown content
        md_content = self.generate_markdown_report(report_doc)
        # Replace emoji with plain text to avoid appearing as squares in Word (compatible with older versions/cross-platform)
        md_content = self._replace_emoji_for_pdf(md_content)

        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
                output_file = tmp_file.name

            logger.info(f"📁 Temporary file path: {output_file}")

            # Pandoc parameters
            extra_args = [
                '--from=markdown-yaml_metadata_block',  # Disable YAML metadata block parsing
                '--standalone',  # Generate standalone documentation
                '--wrap=preserve',  # Keep line breaks
                '--columns=120',  # Set column width
                '-M', 'lang=zh-CN',  # 🔥 Explicitly specify the language as Simplified Chinese
                '-M', 'dir=ltr',  # 🔥 Explicitly specify text direction as left to right
            ]

            # Clean content
            cleaned_content = self._clean_markdown_for_pandoc(md_content)

            # Convert to Word
            pypandoc.convert_text(
                cleaned_content,
                'docx',
                format='markdown',
                outputfile=output_file,
                extra_args=extra_args
            )

            logger.info("✅ pypandoc Conversion completed")

            # 🔥 Post-processing: Fix text orientation in Word documents
            try:
                from docx import Document
                doc = Document(output_file)

                # Fix text direction for all paragraphs
                for paragraph in doc.paragraphs:
                    # Set paragraphs from left to right
                    if paragraph._element.pPr is not None:
                        # Remove possible vertical setting
                        for child in list(paragraph._element.pPr):
                            if 'textDirection' in child.tag or 'bidi' in child.tag:
                                paragraph._element.pPr.remove(child)

                # Fix text direction in tables
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for paragraph in cell.paragraphs:
                                if paragraph._element.pPr is not None:
                                    for child in list(paragraph._element.pPr):
                                        if 'textDirection' in child.tag or 'bidi' in child.tag:
                                            paragraph._element.pPr.remove(child)

                # Save the repaired document
                doc.save(output_file)
                logger.info("✅ Word Document text direction repair completed")
            except ImportError:
                logger.warning("⚠️ python-docx Not installed, skipping text orientation fix")
            except Exception as e:
                logger.warning(f"⚠️ Word Document text orientation fix failed: {e}")

            # Read the generated file
            with open(output_file, 'rb') as f:
                docx_content = f.read()

            logger.info(f"✅ Word Document generation successful, size: {len(docx_content)} Bytes")

            # Clean temporary files
            os.unlink(output_file)

            return docx_content
            
        except Exception as e:
            logger.error(f"❌ Word Document generation failed: {e}", exc_info=True)
            # Clean temporary files
            try:
                if 'output_file' in locals() and os.path.exists(output_file):
                    os.unlink(output_file)
            except Exception:
                pass
            raise Exception(f"Failed to generate Word document: {e}")
    
    def _replace_emoji_for_pdf(self, text: str) -> str:
        """
        Replace emojis with PDF-friendly plain text to avoid appearing as squares when generating PDFs.
        PDF Engine (WeasyPrint/pdfkit) default fonts usually do not support emoji characters.
        """
        import re
        # Risk level/action icon -> text markup
        replacements = [
            ("🟢", "[low]"),
            ("🟡", "[in]"),
            ("🔴", "[high]"),
            ("⚪", "[ ]"),
            # Common emoji are removed directly (the title already has a text description)
            ("📊", ""),
            ("⚠️", ""),
            ("⚠", ""),
            ("💡", ""),
            ("📋", ""),
            ("💼", ""),
            ("🎯", ""),
            ("🔍", ""),
            ("🛡️", ""),
            ("🛡", ""),
            ("📈", ""),
            ("📉", ""),
            ("🏢", ""),
            ("💰", ""),
            ("🌍", ""),
            ("💎", ""),
            ("⚖️", ""),
            ("⚖", ""),
            ("👔", ""),
            ("💭", ""),
            ("📰", ""),
            ("🏭", ""),
        ]
        result = text
        for emoji, replacement in replacements:
            result = result.replace(emoji, replacement)
        # Remove zero-width characters and common invisible characters
        result = re.sub(r"[\u200b-\u200d\ufeff]", "", result)
        # 🔥 Fix: Only compress the extra spaces in the title, without affecting the table format
        # Only handles Markdown header lines (starting with # extra spaces at the beginning)
        lines = result.split('\n')
        processed_lines = []
        for line in lines:
            # Only the title row (starting with # beginning) to compress excess spaces
            if line.strip().startswith('#'):
                # Compress extra spaces in titles (e.g. "##  risk assessment" -> "## risk assessment") 
                line = re.sub(r'(#{1,6})\s{2,}', r'\1 ', line)
            processed_lines.append(line)
        result = '\n'.join(processed_lines)
        return result

    def _markdown_to_html(self, md_content: str) -> str:
        """Convert Markdown to HTML"""
        import markdown

        # Configure Markdown extension
        extensions = [
            'markdown.extensions.tables',  # Table support
            'markdown.extensions.fenced_code',  # Code block support
            'markdown.extensions.nl2br',  # Newline support
        ]

        # Convert to HTML
        html_content = markdown.markdown(md_content, extensions=extensions)

        # Add HTML templates and styles
        # WeasyPrint Optimized CSS (removes unsupported properties)
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN" dir="ltr">
<head>
    <meta charset="UTF-8">
    <title>research report</title>
    <style>
        /* Basic styling - ensuring text is oriented correctly */
        html {{
            direction: ltr;
        }}

        body {{
            font-family: "Noto Sans CJK SC", "Microsoft YaHei", "SimHei", "Arial", sans-serif;
            line-height: 1.8;
            color: #333;
            margin: 20mm;
            padding: 0;
            background: white;
            direction: ltr;
        }}

        /* Title style */
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.8em;
            font-weight: 600;
            page-break-after: avoid;
            direction: ltr;
        }}

        h1 {{
            font-size: 2em;
            border-bottom: 3px solid #3498db;
            padding-bottom: 0.3em;
            page-break-before: always;
        }}

        h1:first-child {{
            page-break-before: avoid;
        }}

        h2 {{
            font-size: 1.6em;
            border-bottom: 2px solid #bdc3c7;
            padding-bottom: 0.25em;
        }}

        h3 {{
            font-size: 1.3em;
            color: #34495e;
        }}

        /* paragraph style */
        p {{
            margin: 0.8em 0;
            text-align: left;
            direction: ltr;
        }}

        /* Table style - optimized paging */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5em 0;
            font-size: 0.9em;
            direction: ltr;
        }}

        /* Header repeats on every page */
        thead {{
            display: table-header-group;
        }}

        tbody {{
            display: table-row-group;
        }}

        /* Table rows avoid breaking across pages */
        tr {{
            page-break-inside: avoid;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 10px 12px;
            text-align: left;
            direction: ltr;
        }}

        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}

        tbody tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}

        tbody tr:hover {{
            background-color: #e9ecef;
        }}

        /* code block style */
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", "Monaco", "Courier New", monospace;
            font-size: 0.9em;
            direction: ltr;
        }}

        pre {{
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #3498db;
            page-break-inside: avoid;
            direction: ltr;
        }}

        pre code {{
            background-color: transparent;
            padding: 0;
        }}

        /* list style */
        ul, ol {{
            margin: 0.8em 0;
            padding-left: 2em;
            direction: ltr;
        }}

        li {{
            margin: 0.4em 0;
            direction: ltr;
        }}

        /* emphasize text */
        strong, b {{
            font-weight: 700;
            color: #2c3e50;
        }}

        em, i {{
            font-style: italic;
            color: #555;
        }}

        /* horizontal line */
        hr {{
            border: none;
            border-top: 2px solid #ecf0f1;
            margin: 2em 0;
        }}

        /* link style */
        a {{
            color: #3498db;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        /* Paging control */
        @page {{
            size: A4;
            margin: 20mm;

            @top-center {{
                content: "research report";
                font-size: 10pt;
                color: #999;
            }}

            @bottom-right {{
                content: "No. " counter(page) " page";
                font-size: 10pt;
                color: #999;
            }}
        }}

        /* Avoid being alone and alone */
        p, li {{
            orphans: 3;
            widows: 3;
        }}

        /* Picture style */
        img {{
            max-width: 100%;
            height: auto;
            page-break-inside: avoid;
        }}

        /* quote block style */
        blockquote {{
            margin: 1em 0;
            padding: 0.5em 1em;
            border-left: 4px solid #3498db;
            background-color: #f8f9fa;
            font-style: italic;
            page-break-inside: avoid;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>
"""
        return html_template

    def _generate_pdf_with_pdfkit(self, html_content: str) -> bytes:
        """Generated using pdfkit PDF"""
        import pdfkit

        logger.info("🔧 Use pdfkit + wkhtmltopdf generate PDF...")

        # Configuration options
        options = {
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'page-size': 'A4',
            'margin-top': '20mm',
            'margin-right': '20mm',
            'margin-bottom': '20mm',
            'margin-left': '20mm',
        }

        # generate PDF
        pdf_bytes = pdfkit.from_string(html_content, False, options=options)

        logger.info(f"✅ pdfkit PDF Generated successfully, size: {len(pdf_bytes)} Bytes")
        return pdf_bytes

    def _generate_pdf_with_weasyprint(self, html_content: str) -> bytes:
        """Generate PDF using WeasyPrint (recommended, pure Python, no external tools required)"""
        import weasyprint
        
        logger.info("🔧 Generate using WeasyPrint PDF...")
        
        # generate PDF
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        
        logger.info(f"✅ PDF Generated successfully, size: {len(pdf_bytes)} Bytes")
        return pdf_bytes

    def generate_pdf_report(self, report_doc: Dict[str, Any]) -> bytes:
        """Generate reports in PDF format (preferably use WeasyPrint, otherwise use pdfkit)"""
        logger.info("📊 Start generating PDF documents...")

        # Generate Markdown content
        md_content = self.generate_markdown_report(report_doc)
        # Replace emoji with PDF-friendly text to avoid appearing as squares when exporting
        md_content = self._replace_emoji_for_pdf(md_content)
        html_content = self._markdown_to_html(md_content)

        # Prefer using WeasyPrint (recommended, pure Python, no external tools required)
        if self.weasyprint_available:
            try:
                logger.info("🎯 Use WeasyPrint to generate PDF (recommended)")
                return self._generate_pdf_with_weasyprint(html_content)
            except Exception as e:
                logger.warning(f"⚠️ WeasyPrint Build failed: {e}, Try using pdfkit...")
                # If WeasyPrint fails, try pdfkit

        # Alternative: Use pdfkit
        if self.pdfkit_available:
            try:
                logger.info("🎯 Use pdfkit + wkhtmltopdf Generate PDF (optional)")
                return self._generate_pdf_with_pdfkit(html_content)
            except Exception as e:
                logger.error(f"❌ pdfkit Build failed: {e}")
                raise Exception(f"PDF Build failed: {e}")

        # If neither is available, throw an error
        error_msg = (
            "PDF The generation tool is unavailable and cannot generate the PDF.\n\n"
            "Recommended installation method (choose one):\n"
            "1. WeasyPrint (Recommended, pure Python, no external tools required): pip install weasyprint\n"
            "2. pdfkit + wkhtmltopdf: pip install pdfkit, then install https://wkhtmltopdf.org/downloads.html\n"
        )
        if WEASYPRINT_ERROR:
            error_msg += f"\nWeasyPrint Error: {WEASYPRINT_ERROR}\n"
        if PDFKIT_ERROR:
            error_msg += f"\npdfkit Error: {PDFKIT_ERROR}"

        logger.error(f"❌ {error_msg}")
        raise Exception(error_msg)


# Create a global exporter instance
report_exporter = ReportExporter()


# === report_formatter.py ===
"""
Unified research report formatting tool

Provides unified report extraction and formatting functions for use by SimpleAnalysisService and UnifiedAnalysisService.
Make sure the report format is consistent and contains all necessary fields:
- Macro report: index_report (market research), sector_report (Industry sector research)
- Basic report:market_report, sentiment_report, news_report, fundamentals_report
- Research conclusion:investment_plan, trader_investment_plan, final_trade_decision
- Research team:bull_researcher, bear_researcher, research_team_decision
- Risk Team:risky_analyst, safe_analyst, neutral_analyst, risk_management_decision
"""

import logging
import uuid
import json
import re
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)
_ERROR_RESULT_PATTERNS = (
    re.compile(r'^\{[\s\S]*["\']error["\']\s*:\s*["\'][\s\S]*["\']\s*,\s*["\']success["\']\s*:\s*False[\s\S]*\}$'),
    re.compile(r'^Execution failed[:: ].*$', re.IGNORECASE),
)

def _build_report_failure_fallback(report_type: str) -> str:
    fallback_map = {
        "risk": "The execution of the risk review module has not been completed, and the current risk conclusions still need to be verified.",
        "investment": "The implementation of the comprehensive research conclusion module has not been completed, and the current conclusions still need to be verified.",
        "final_decision": "The implementation of the comprehensive research conclusion module has not been completed, and the current conclusions still need to be verified.",
    }
    return fallback_map.get(report_type, "Tool execution or model generation has not been completed, and the current conclusions still need to be verified.")


def _is_error_payload_text(content: str) -> bool:
    stripped = (content or "").strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in _ERROR_RESULT_PATTERNS)
    logger.info(f"🔄 [JSON Convert] Start conversion, report type: {report_type}, content length: {len(content) if content else 0}")

    if _is_error_payload_text(content):
        logger.warning(f"⚠️ [JSON Convert] Error payload text detected, returned by downgrade copy, report type: {report_type}")
        return _build_report_failure_fallback(report_type)


DISPLAY_SANITIZED_REPORT_KEYS = {
    'bull_researcher',
    'bull_report',
    'bear_researcher',
    'bear_report',
    'research_team_decision',
    'investment_plan',
    'trader_investment_plan',
    'risky_analyst',
    'risky_opinion',
    'safe_analyst',
    'safe_opinion',
    'neutral_analyst',
    'neutral_opinion',
    'risk_management_decision',
}


# All standard reporting fields
STANDARD_REPORT_FIELDS = [
    # 🆕 Macro research reports (priority for display)
    'index_report',           # Market/index analysis
    'sector_report',          # Industry/sector analysis
    # Individual stock research reports
    'market_report',          # Market technical analysis
    'sentiment_report',       # Social media sentiment analysis
    'news_report',            # Journalism Research
    'fundamentals_report',    # fundamental analysis
    'chip_report',            # Chip distribution analysis
    # research conclusion report
    # 'investment_plan',        # Research Manager Conclusion (as an alternative to research_team_decision)
    'trader_investment_plan', # Research and integrate opinions
    'research_team_decision', # Research team conclusion
    'risk_management_decision', # Risk review conclusion
    'final_trade_decision'    # Comprehensive research conclusion
]


def _failure_shape_message(value: dict) -> Optional[str]:
    """🛡️ Q1: Identifies a failed/empty response wrapper dict and returns a user-friendly prompt (returns None for non-failure forms).

    Cover {'success': False, 'error': ...} (Node exception) and
    {'content': '', 'success': True} (Empty response is packaged as success) two categories.
    """
    if not isinstance(value, dict):
        return None
    content_val = value.get("content")
    if value.get("success") is False or (
        value.get("success") is True
        and not (isinstance(content_val, str) and content_val.strip())
    ):
        err = value.get("error") or "Model response exception (empty content)"
        return f"> ⚠️ **Generation of this section failed**: {err}. It is recommended to reanalyze to get the full report."
    return None


def _extract_report_text(report_key: str, value: Any) -> Optional[str]:
    text_value = None

    if isinstance(value, str):
        text_value = value.strip()
    elif isinstance(value, dict):
        # 🛡️ Q1: Failure/empty response form → Render friendly prompt instead of skipping (naked dict is strictly prohibited from reporting)
        _failure_msg = _failure_shape_message(value)
        if _failure_msg:
            logger.warning(f"⚠️ [ReportFormatter] {report_key} For failure/empty response form, render prompt")
            return _failure_msg
        for key in ("content", "markdown", "text", "message", "report"):
            nested_value = value.get(key)
            if isinstance(nested_value, str) and nested_value.strip():
                text_value = nested_value.strip()
                break
    elif value is not None:
        raw_text = str(value).strip()
        if raw_text:
            text_value = raw_text

    if not text_value or len(text_value) <= 10:
        return None

    if report_key == 'final_trade_decision':
        return _convert_json_to_markdown(text_value, "final_decision")
    if report_key == 'research_team_decision':
        return _convert_json_to_markdown(text_value, "final_decision")
    if report_key == 'risk_management_decision':
        return _convert_json_to_markdown(text_value, "risk")
    return _clean_report_for_display(report_key, text_value)


def _extract_reports_from_mapping(mapping: Dict[str, Any], reports: Dict[str, str], source_name: str) -> None:
    if not isinstance(mapping, dict):
        return

    logger.info(f"🔍 [ReportFormatter] {source_name} Field: {list(mapping.keys())}")

    for field in STANDARD_REPORT_FIELDS:
        if field in reports:
            continue
        extracted = _extract_report_text(field, mapping.get(field))
        if extracted:
            reports[field] = extracted
            logger.info(f"📊 [ReportFormatter] Extract report: {field} <- {source_name} - length: {len(extracted)}")

    for report_key in DISPLAY_SANITIZED_REPORT_KEYS:
        if report_key in reports:
            continue
        extracted = _extract_report_text(report_key, mapping.get(report_key))
        if extracted:
            reports[report_key] = extracted
            logger.info(f"📊 [ReportFormatter] Extract report: {report_key} <- {source_name} - length: {len(extracted)}")


def extract_reports_from_state(state: Any) -> Dict[str, str]:
    """
    Extract all report content from state

    Args:
        state: Parse state object (can be a dictionary or object)

    Returns:
        Dictionary containing all reports
    """
    reports = {}

    if state is None:
        return reports

    nested_reports = _get_field_value(state, 'reports')
    has_nested_reports = isinstance(nested_reports, dict) and bool(nested_reports)

    if has_nested_reports:
        _extract_reports_from_mapping(nested_reports, reports, 'state.reports')

    # 🔥 Debug log: display top-level fields of state
    if isinstance(state, dict):
        logger.info(f"🔍 [ReportFormatter] state Top level fields: {list(state.keys())}")
        # 🔥 Check whether index_report and sector_report exist
        if "index_report" in state:
            logger.info(f"🔍 [ReportFormatter] index_report existence, length: {len(str(state.get('index_report', '')))}")
        elif not has_nested_reports:
            logger.warning("⚠️ [ReportFormatter] index_report Field does not exist in state")
        if "sector_report" in state:
            logger.info(f"🔍 [ReportFormatter] sector_report existence, length: {len(str(state.get('sector_report', '')))}")
        elif not has_nested_reports:
            logger.warning("⚠️ [ReportFormatter] sector_report Field does not exist in state")

    # 1. Extract report fields (first read from structured_reports output by the engine, automatically include new agent output)
    structured_reports = _get_field_value(state, 'structured_reports')
    if isinstance(structured_reports, dict) and structured_reports:
        for field, entry in structured_reports.items():
            if field in reports:
                continue
            if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                content = entry["content"]
                if isinstance(content, str) and len(content.strip()) > 10:
                    reports[field] = content.strip()
                    logger.info(f"📊 [ReportFormatter] Extracted from structured_reports: {field} - length: {len(content.strip())}")
    else:
        # Fallback: derivation from report_manifest
        manifest = _get_field_value(state, 'report_manifest')
        if isinstance(manifest, list) and manifest:
            for m in manifest:
                field = m.get("field")
                if field and field not in reports:
                    value = _get_field_value(state, field)
                    extracted = _extract_report_text(field, value)
                    if extracted:
                        reports[field] = extracted
                        logger.info(f"📊 [ReportFormatter] Extract from manifest: {field} - length: {len(extracted)}")
        else:
            # Final fallback: legacy hardcoded lists
            for field in STANDARD_REPORT_FIELDS:
                if field in reports:
                    continue
                value = _get_field_value(state, field)
                extracted = _extract_report_text(field, value)
                if extracted:
                    reports[field] = extracted
                    logger.info(f"📊 [ReportFormatter] Extract from hardcoded list: {field} - length: {len(extracted)}")

    # 2. Extract the research team debate status report (investment_debate_state)
    debate_state = _get_field_value(state, 'investment_debate_state')
    if debate_state:
        _extract_investment_debate_reports(debate_state, reports)
    else:
        logger.warning("⚠️ [ReportFormatter] investment_debate_state Does not exist or is empty")

    # 3. Extract the risk management team debate status report (risk_debate_state)
    risk_state = _get_field_value(state, 'risk_debate_state')
    if risk_state:
        _extract_risk_debate_reports(risk_state, reports)
    else:
        logger.warning("⚠️ [ReportFormatter] risk_debate_state Does not exist or is empty")

    # 🔥 Alternative: Find directly from top-level state bull_report, bear_report etc fields
    # New workflows may store reports in different locations
    _extract_alternative_reports(state, reports)

    logger.info(f"📊 [ReportFormatter] Extract to {len(reports)} reports: {list(reports.keys())}")
    return reports


def _clean_report_for_display(report_key: str, text: str) -> str:
    cleaned_text = _remove_author_signature(text.strip())
    artifact_cleaned_text = sanitize_report_artifacts(cleaned_text)
    if artifact_cleaned_text:
        cleaned_text = artifact_cleaned_text
    elif any(token in cleaned_text for token in ("</tool_call>", "<tool_call", '"name": "get_')):
        if report_key == 'news_report':
            return "The tool results were not successfully expanded into news reports, and the current news conclusions still need to be verified."
        return "The tool results were not successfully expanded into text, and the current conclusions still need to be verified."

    if report_key in DISPLAY_SANITIZED_REPORT_KEYS:
        cleaned_text = sanitize_display_report_text(cleaned_text, fallback=cleaned_text)
    return cleaned_text


def _extract_alternative_reports(state: Any, reports: Dict[str, str]):
    """
    Alternative: Pull the report from the state top level or elsewhere

    New workflows may store reports in different locations, such as:
    - bull_report (instead of investment_debate_state.bull_history)
    - bear_report (instead of investment_debate_state.bear_history)
    """
    # Alternative field mapping (including v2.0 agent field)
    alternative_mappings = {
        'bull_researcher': ['bull_report', 'bull_history', 'bull_analysis'],
        'bear_researcher': ['bear_report', 'bear_history', 'bear_analysis'],
        'neutral_analyst': ['neutral_report', 'neutral_history', 'neutral_analysis'],
        'trader_investment_plan': ['trader_investment_plan', 'trading_plan', 'trade_plan'],
        # 🔥 research_team_decision Can be read from the investment_plan field (some workflows are stored here)
        'research_team_decision': ['research_team_decision', 'investment_plan', 'investment_advice', 'judge_decision'],
        'risk_management_decision': ['risk_management_decision', 'risk_assessment', 'judge_decision'],
        'final_trade_decision': ['final_trade_decision'],
        # 🔥 Remove investment_plan as a separate field (to avoid confusion with trader_investment_plan)
        # 'investment_plan': ['investment_plan', 'investment_advice'],
        # v2.0 Risk Analyst Field Mapping
        'risky_analyst': ['risky_analyst', 'risky_opinion', 'risky_history'],
        'safe_analyst': ['safe_analyst', 'safe_opinion', 'safe_history'],
        'neutral_analyst': ['neutral_analyst', 'neutral_opinion', 'neutral_history'],
    }

    for report_key, alt_fields in alternative_mappings.items():
        if report_key in reports:
            continue  # Already extracted

        for alt_field in alt_fields:
            value = _get_field_value(state, alt_field)
            text_value = None
            if isinstance(value, str):
                text_value = value.strip()
            elif isinstance(value, dict):
                # 🛡️ Q1: Failure/empty response form → Rendering-friendly tips (naked dict is strictly prohibited from entering reports)
                _failure_msg = _failure_shape_message(value)
                if _failure_msg:
                    logger.warning(
                        f"⚠️ [ReportFormatter] alternative extraction {report_key} <- {alt_field} For failure/empty response form, render prompt"
                    )
                    reports[report_key] = _failure_msg
                    break
                for k in ("content", "markdown", "text", "message", "report"):
                    v = value.get(k)
                    if isinstance(v, str) and v.strip():
                        text_value = v.strip()
                        break
            if text_value and len(text_value) > 10:
                # 🔥 For fields that may contain JSON, convert to Markdown
                if report_key == 'final_trade_decision':
                    markdown_value = _convert_json_to_markdown(text_value, "final_decision")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                elif report_key == 'research_team_decision':
                    # Research team conclusions may also be in JSON format
                    logger.info("🔍 [ReportFormatter] Alternative extraction detected research_team_decision, ready for conversion JSON")
                    logger.info(f"🔍 [ReportFormatter] First 500 characters of original content: {text_value[:500]}")
                    markdown_value = _convert_json_to_markdown(text_value, "final_decision")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                    logger.info(f"📊 [ReportFormatter] The first 500 characters of the converted content: {markdown_value[:500]}")
                elif report_key == 'risk_management_decision':
                    # Risk management decisions may also be in JSON format
                    markdown_value = _convert_json_to_markdown(text_value, "risk")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                else:
                    # 🔥 Clean up signature information generated by AI
                    cleaned_value = _clean_report_for_display(report_key, text_value)
                    reports[report_key] = cleaned_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Signature cleared)")
                break


def _get_field_value(obj: Any, field: str) -> Any:
    """Safely get field values"""
    if obj is None:
        return None
    if hasattr(obj, field):
        return getattr(obj, field, None)
    elif isinstance(obj, dict) and field in obj:
        return obj[field]
    return None


def _convert_json_to_markdown(content: str, report_type: str = "investment") -> str:
    """
    Convert JSON formatted report to Markdown format

    Args:
        content: Report content (may be a JSON string or plain text)
        report_type: Report Type ("investment", "risk" or "final_decision") 

    Returns:
        Markdown Format report content
    """
    logger.info("🔄 [JSON Convert] ========== Start converting ==========")
    logger.info(f"🔄 [JSON Convert] report type: {report_type}")
    logger.info(f"🔄 [JSON Convert] content length: {len(content) if content else 0}")
    logger.info(f"🔄 [JSON Convert] Content type: {type(content)}")

    if not content or not isinstance(content, str):
        logger.warning("⚠️ [JSON Convert] If the content is empty or not a string, it will be returned directly.")
        return content

    content = content.strip()
    logger.info(f"🔄 [JSON Convert] The first 500 characters of the content: {content[:500]}")
    logger.info(f"🔄 [JSON Convert] Does it contain '```json': {'```json' in content}")
    logger.info(f"🔄 [JSON Convert] Whether to {{ Beginning: {content.startswith('{')}")

    if _is_error_payload_text(content):
        logger.warning(f"⚠️ [JSON Convert] Error payload text detected, returned by downgrade copy, report type: {report_type}")
        return _build_report_failure_fallback(report_type)

    # Check if it is in JSON format
    json_obj = None

    # 1. Try to extract JSON code block
    if "```json" in content:
        logger.info("🔄 [JSON Convert] JSON code block detected")
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            logger.info(f"🔄 [JSON Convert] Extracted JSON string length: {len(json_str)}, first 200 characters: {json_str[:200]}")
            
            # 🔥 Fix common JSON format issues
            # 1. Repair price_analysis_range: 295.29-442.93 -> [295.29, 442.93]
            # match pattern: "price_analysis_range": numbers - numbers
            json_str = re.sub(
                r'"price_analysis_range"\s*:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',
                r'"price_analysis_range": [\1, \2]',
                json_str
            )
            
            try:
                json_obj = json.loads(json_str)
                logger.info(f"✅ [JSON Convert] JSON Code block parsed successfully, field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [JSON Convert] JSON Code block parsing failed: {e}")
                # If it still fails after repairing, record the repaired content for debugging
                logger.debug(f"🔍 [JSON Convert] The first 500 characters of the repaired JSON string: {json_str[:500]}")

    # 2. Try to parse directly JSON
    if json_obj is None and content.startswith("{"):
        logger.info("🔄 [JSON Convert] Detected with { At the beginning, try to parse directly JSON")
        # 🔥 Fix common JSON format issues
        fixed_content = re.sub(
            r'"price_analysis_range"\s*:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',
            r'"price_analysis_range": [\1, \2]',
            content
        )
        try:
            json_obj = json.loads(fixed_content)
            logger.info(f"✅ [JSON Convert] Direct JSON parsing successful, field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [JSON Convert] Direct JSON parsing failed: {e}")

    # If it is not JSON, return the original content directly.
    if json_obj is None:
        logger.warning("⚠️ [JSON Convert] It is not in JSON format and returns the original content directly.")
        logger.warning(f"⚠️ [JSON Convert] The first 1000 characters of the original content: {content[:1000]}")
        return content

    # Convert to Markdown
    logger.info(f"🔄 [JSON Convert] Start converting to Markdown, report type: {report_type}")
    logger.info(f"🔄 [JSON Convert] JSON object field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")

    if report_type == "investment":
        result = _convert_investment_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] Research conclusion conversion completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    elif report_type == "risk":
        result = _convert_risk_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] Risk assessment conversion completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    elif report_type == "final_decision":
        result = _convert_final_decision_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] The final research conclusion conversion is completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    else:
        logger.warning(f"⚠️ [JSON Convert] Unknown report type: {report_type}, Return directly to the original content")
        return content


def _convert_investment_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """Convert research conclusion JSON to Markdown"""
    logger.info(f"🔄 [Conversion of research conclusions] JSON Field: {list(json_obj.keys())}")
    lines = []
    
    # Summary of Research Perspectives
    action = json_obj.get("analysis_view") or json_obj.get("action", "")
    logger.info(f"🔄 [Conversion of research conclusions] action: {action}")
    if action:
        action_map = {
            # New compliance terms (optimistic/cautious/neutral) take precedence
            "optimistic": "🟢 optimistic",
            "Prudence": "🟡 Prudence",
            "Neutral": "⚪ Neutral",
            # old market view terminology + Old transaction instructions (compatible with existing data, mapped to new compliance expressions)
            "buy": "🟢 optimistic",
            "hold": "⚪ Neutral",
            "sell": "🟡 Prudence",
            "bullish": "🟢 optimistic",
            "Bearish": "🟡 Prudence",
        }
        action_display = action_map.get(action, action)
        lines.append(f"## 💡 research perspective\n\n**point of view**: {action_display}\n\n")
    
    # Confidence
    confidence = json_obj.get("confidence")
    logger.info(f"🔄 [Conversion of research conclusions] confidence: {confidence}")
    if confidence is not None:
        # 🔥 Fix: handle both 0-1 decimal and 0-100 integer situations
        try:
            conf_value = float(confidence)
            # If it is a decimal between 0 and 1, convert it to a percentage
            if conf_value <= 1:
                conf_display = int(conf_value * 100)
            else:
                conf_display = int(conf_value)
            lines.append(f"**Confidence**: {conf_display}/100\n\n")
        except (ValueError, TypeError):
            lines.append(f"**Confidence**: {confidence}/100\n\n")
    
    # risk score
    risk_score = json_obj.get("risk_score")
    logger.info(f"🔄 [Conversion of research conclusions] risk_score: {risk_score}")
    if risk_score is not None:
        risk_level = "low" if risk_score < 0.3 else "in" if risk_score < 0.7 else "high"
        lines.append(f"**risk score**: {risk_score:.2f} ({risk_level}risk)\n\n")
    
    # Research basis (core content)
    reasoning = json_obj.get("reasoning", "")
    logger.info(f"🔄 [Conversion of research conclusions] reasoning length: {len(reasoning) if reasoning else 0}")
    if reasoning:
        lines.append(f"## 📊 Research basis\n\n{reasoning}\n\n")
    
    # Investment plan summary
    summary = json_obj.get("summary", "")
    logger.info(f"🔄 [Conversion of research conclusions] summary length: {len(summary) if summary else 0}")
    if summary:
        lines.append(f"## 📋 Research summary\n\n{summary}\n\n")
    
    # Risk warning
    risk_warning = json_obj.get("risk_warning", "")
    logger.info(f"🔄 [Conversion of research conclusions] risk_warning length: {len(risk_warning) if risk_warning else 0}")
    if risk_warning:
        lines.append(f"## ⚠️ Risk warning\n\n{risk_warning}\n\n")

    for title, field_name in (
        ("## 🔍 core basis", "core_evidence"),
        ("## ❓ key uncertainties", "uncertainties"),
        ("## 🔄 Determine adjustment conditions", "invalidation_conditions"),
        ("## 👀 Follow-up observations", "watch_items"),
    ):
        items = [item for item in json_obj.get(field_name, []) if item] if isinstance(json_obj.get(field_name, []), list) else []
        if items:
            lines.append(f"{title}\n\n")
            for idx, item in enumerate(items, 1):
                lines.append(f"{idx}. {item}\n")
            lines.append("\n")
    
    result = "\n".join(lines).strip()
    logger.info(f"✅ [Conversion of research conclusions] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _convert_risk_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """Convert risk assessment JSON to Markdown"""
    logger.info(f"🔄 [risk assessment transformation] JSON Field: {list(json_obj.keys())}")
    lines = []

    # risk level
    risk_level = json_obj.get("risk_level", "")
    logger.info(f"🔄 [risk assessment transformation] risk_level: {risk_level}")
    if risk_level:
        level_map = {"low": "🟢", "in": "🟡", "high": "🔴"}
        level_icon = level_map.get(risk_level, "⚪")
        lines.append(f"## ⚠️ risk level\n\n{level_icon} **{risk_level}risk**\n\n")

    # risk score
    risk_score = json_obj.get("risk_score")
    logger.info(f"🔄 [risk assessment transformation] risk_score: {risk_score}")
    if risk_score is not None:
        lines.append(f"**risk score**: {risk_score:.2f}\n\n")

    # Reasons for risk assessment (core content)
    reasoning = json_obj.get("reasoning", "")
    logger.info(f"🔄 [risk assessment transformation] reasoning length: {len(reasoning) if reasoning else 0}")
    if reasoning:
        lines.append(f"## 📊 Risk assessment rationale\n\n{reasoning}\n\n")

    # Main risk points
    key_risks = json_obj.get("key_risks", [])
    logger.info(f"🔄 [risk assessment transformation] key_risks Quantity: {len(key_risks) if isinstance(key_risks, list) else 0}")
    if isinstance(key_risks, list) and key_risks:
        lines.append("## 🔍 Main risk points\n\n")
        for idx, risk in enumerate(key_risks, 1):
            if risk:
                lines.append(f"{idx}. {risk}\n")
        lines.append("\n")

    # Research use boundaries
    risk_control = json_obj.get("risk_control", "")
    logger.info(f"🔄 [risk assessment transformation] risk_control length: {len(risk_control) if risk_control else 0}")
    if risk_control:
        lines.append(f"## 🛡️ Research use boundaries\n\n{risk_control}\n\n")

    # Research Tracking Recommendations Adjustments
    investment_adjustment = json_obj.get("investment_adjustment", "")
    logger.info(f"🔄 [risk assessment transformation] investment_adjustment length: {len(investment_adjustment) if investment_adjustment else 0}")
    if investment_adjustment:
        lines.append(f"## 📈 Research Tracking Advice\n\n{investment_adjustment}\n\n")

    result = "\n".join(lines).strip()
    logger.info(f"✅ [risk assessment transformation] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _convert_final_decision_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """
    Convert JSON containing final_trade_decision to Markdown

    This function handles the full JSON output by RiskManager, including:
    - Risk Assessment Section (risk_level, risk_score, reasoning, key_risks, risk_control, investment_adjustment) 
    - Final research conclusion part (final_trade_decision nested object)
    """
    logger.info(f"🔄 [Conversion of final research conclusions] JSON Field: {list(json_obj.keys())}")
    lines = []

    # 🔥 Key: Extract final_trade_decision nested object
    final_trade_decision = json_obj.get("final_trade_decision", {})
    logger.info(f"🔄 [Conversion of final research conclusions] final_trade_decision Type: {type(final_trade_decision)}")

    if isinstance(final_trade_decision, dict) and final_trade_decision:
        logger.info(f"🔄 [Conversion of final research conclusions] final_trade_decision Field: {list(final_trade_decision.keys())}")

        # decision summary
        lines.append("# 🎯 Comprehensive research conclusion\n\n")
        lines.append("## current judgment\n\n")

        # research judgment
        action = final_trade_decision.get("analysis_view") or final_trade_decision.get("action", "")
        logger.info(f"🔄 [Conversion of final research conclusions] action: {action}")
        if action:
            action_map = {
                # New compliance terms (optimistic/cautious/neutral) take precedence
                "optimistic": "🟢 optimistic",
                "Prudence": "🟡 Prudence",
                "Neutral": "⚪ Neutral",
                # old market view terminology + Old transaction instructions (compatible with existing data, mapped to new compliance expressions)
                "buy": "🟢 optimistic",
                "hold": "⚪ Neutral",
                "sell": "🟡 Prudence",
                "bullish": "🟢 optimistic",
                "Bearish": "🟡 Prudence",
            }
            action_display = action_map.get(action, action)
            lines.append(f"- **research perspective**: {action_display}\n")

        # Confidence
        confidence = final_trade_decision.get("confidence")
        logger.info(f"🔄 [Conversion of final research conclusions] confidence: {confidence}")
        if confidence is not None:
            # 🔥 Fix: handle both 0-1 decimal and 0-100 integer situations
            try:
                conf_value = float(confidence)
                # If it is a decimal between 0 and 1, convert it to a percentage
                if conf_value <= 1:
                    conf_display = int(conf_value * 100)
                else:
                    conf_display = int(conf_value)
                lines.append(f"- **Confidence**: {conf_display}%\n")
            except (ValueError, TypeError):
                lines.append(f"- **Confidence**: {confidence}%\n")

        lines.append("\n")

        # Research basis (core content)
        reasoning = final_trade_decision.get("reasoning", "")
        logger.info(f"🔄 [Conversion of final research conclusions] reasoning length: {len(reasoning) if reasoning else 0}")
        if reasoning:
            lines.append(f"## 📊 Research basis\n\n{reasoning}\n\n")

        # One sentence summary
        summary = final_trade_decision.get("summary", "")
        logger.info(f"🔄 [Conversion of final research conclusions] summary length: {len(summary) if summary else 0}")
        if summary:
            lines.append(f"## 💡 Research summary\n\n{summary}\n\n")

        # Risk warning
        risk_warning = final_trade_decision.get("risk_warning", "")
        logger.info(f"🔄 [Conversion of final research conclusions] risk_warning length: {len(risk_warning) if risk_warning else 0}")
        if risk_warning:
            lines.append(f"## ⚠️ Risk warning\n\n{risk_warning}\n\n")

        for title, field_name in (
            ("## 🔍 core basis", "core_evidence"),
            ("## ❓ key uncertainties", "uncertainties"),
            ("## 🔄 Determine adjustment conditions", "invalidation_conditions"),
            ("## 👀 Follow-up observations", "watch_items"),
        ):
            items = [item for item in final_trade_decision.get(field_name, []) if item] if isinstance(final_trade_decision.get(field_name, []), list) else []
            if items:
                lines.append(f"{title}\n\n")
                for idx, item in enumerate(items, 1):
                    lines.append(f"{idx}. {item}\n")
                lines.append("\n")
    else:
        logger.warning("⚠️ [Conversion of final research conclusions] final_trade_decision Does not exist or is empty, falls back to risk assessment format")
        # If there is no final_trade_decision, fall back to the risk assessment format
        return _convert_risk_json_to_markdown(json_obj)

    result = "\n".join(lines).strip()
    logger.info(f"✅ [Conversion of final research conclusions] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _extract_investment_debate_reports(debate_state: Any, reports: Dict[str, str]):
    """Extract research team debate reports"""
    # 🔥 Debug log: display the contents of investment_debate_state
    logger.info(f"🔍 [ReportFormatter] investment_debate_state Type: {type(debate_state)}")
    if isinstance(debate_state, dict):
        logger.info(f"🔍 [ReportFormatter] investment_debate_state Field: {list(debate_state.keys())}")

    # multi-investigator
    bull_content = _get_field_value(debate_state, 'bull_history')
    logger.info(f"🔍 [ReportFormatter] bull_history Type: {type(bull_content)}, value: {str(bull_content)[:100] if bull_content else None}")
    if bull_content and isinstance(bull_content, str) and len(bull_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('bull_researcher', bull_content.strip())
        reports['bull_researcher'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: bull_researcher - length: {len(cleaned_content)} (Signature cleared)")

    # short researcher
    bear_content = _get_field_value(debate_state, 'bear_history')
    logger.info(f"🔍 [ReportFormatter] bear_history Type: {type(bear_content)}, value: {str(bear_content)[:100] if bear_content else None}")
    if bear_content and isinstance(bear_content, str) and len(bear_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('bear_researcher', bear_content.strip())
        reports['bear_researcher'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: bear_researcher - length: {len(cleaned_content)} (Signature cleared)")

    # Research Manager Analysis
    decision_content = _get_field_value(debate_state, 'judge_decision')
    logger.info(f"🔍 [ReportFormatter] judge_decision Type: {type(decision_content)}, value: {str(decision_content)[:100] if decision_content else None}")

    # ✅ Fix: only use judge_decision if it has actual content
    # Don't use with empty string str(debate_state) as an alternative
    if decision_content and isinstance(decision_content, str) and len(decision_content.strip()) > 10:
        # 🔥 New: If in JSON format, convert to Markdown
        markdown_content = _clean_report_for_display(
            'research_team_decision',
            _convert_json_to_markdown(decision_content.strip(), "investment"),
        )
        reports['research_team_decision'] = markdown_content
        logger.info(f"📊 [ReportFormatter] Extract: research_team_decision - length: {len(markdown_content)}")
    else:
        logger.warning("⚠️ [ReportFormatter] research_team_decision Empty or too short, skip")


def _extract_risk_debate_reports(risk_state: Any, reports: Dict[str, str]):
    """Extract risk management team debate report"""
    # 🔥 Debug log: display the contents of risk_debate_state
    logger.info(f"🔍 [ReportFormatter] risk_debate_state Type: {type(risk_state)}")
    if isinstance(risk_state, dict):
        logger.info(f"🔍 [ReportFormatter] risk_debate_state Field: {list(risk_state.keys())}")

    # activist analyst
    risky_content = _get_field_value(risk_state, 'risky_history')
    logger.info(f"🔍 [ReportFormatter] risky_history: {str(risky_content)[:100] if risky_content else None}")
    if risky_content and isinstance(risky_content, str) and len(risky_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('risky_analyst', risky_content.strip())
        reports['risky_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: risky_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # conservative analyst
    safe_content = _get_field_value(risk_state, 'safe_history')
    logger.info(f"🔍 [ReportFormatter] safe_history: {str(safe_content)[:100] if safe_content else None}")
    if safe_content and isinstance(safe_content, str) and len(safe_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('safe_analyst', safe_content.strip())
        reports['safe_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: safe_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # neutral analyst
    neutral_content = _get_field_value(risk_state, 'neutral_history')
    logger.info(f"🔍 [ReportFormatter] neutral_history: {str(neutral_content)[:100] if neutral_content else None}")
    if neutral_content and isinstance(neutral_content, str) and len(neutral_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('neutral_analyst', neutral_content.strip())
        reports['neutral_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: neutral_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # risk management decisions
    risk_decision = _get_field_value(risk_state, 'judge_decision')
    logger.info(f"🔍 [ReportFormatter] risk judge_decision Type: {type(risk_decision)}, value: {str(risk_decision)[:100] if risk_decision else None}")

    # ✅ Fix: only use judge_decision if it has actual content
    # Don't use with empty string str(risk_state) as an alternative
    if risk_decision and isinstance(risk_decision, str) and len(risk_decision.strip()) > 10:
        # 🔥 New: If in JSON format, convert to Markdown
        markdown_content = _clean_report_for_display(
            'risk_management_decision',
            _convert_json_to_markdown(risk_decision.strip(), "risk"),
        )
        reports['risk_management_decision'] = markdown_content
        logger.info(f"📊 [ReportFormatter] Extract: risk_management_decision - length: {len(markdown_content)}")
    else:
        logger.warning("⚠️ [ReportFormatter] risk_management_decision Empty or too short, skip")


# 🔥 Compliance Modification: Research Conclusion Mapping (English -> Chinese Compliance Terminology)
ACTION_TRANSLATION = {
    'BUY': 'optimistic', 'SELL': 'Prudence', 'HOLD': 'Neutral',
    'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',
    'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',  # Compatible with old data
    'bullish': 'optimistic', 'Bearish': 'Prudence', 'Neutral': 'Neutral',  # Compatible with old data
}


def format_decision(
    decision_raw: Dict[str, Any],
    fallback_text: str = "",
    quick_model: str = None,
    stock_code: str = None
) -> Dict[str, Any]:
    """
    Formatting decisions into standard formats

    🔥 Core fix: if decision_raw is missing a key field (reasoning),
    Use SignalProcessor to extract structured information from fallback_text.

    Args:
        decision_raw: original decision dictionary
        fallback_text: Alternate text (usually final_trade_decision or risk_management_decision)
        quick_model: User-selected quick analysis model name
        stock_code: Stock code (used by SignalProcessor to determine currency type)

    Returns:
        Formatted decision dictionary, including action, confidence, risk_score, reasoning
    """
    import re

    if not decision_raw:
        decision_raw = {}

    # 🔥 If decision_raw lacks key fields and has fallback_text, use SignalProcessor to process
    needs_signal_processing = (
        fallback_text and
        len(fallback_text) > 50 and
        (not decision_raw.get('reasoning') and not decision_raw.get('rationale'))
    )

    if needs_signal_processing:
        try:
            from tradingagents.graph.signal_processing import SignalProcessor
            from tradingagents.graph.trading_graph import create_llm_by_provider

            # Find the corresponding configuration from the database according to the incoming quick_model
            quick_llm = None
            target_model = quick_model  # Use user-selected model

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    selected_cfg = None

                    # 🔥 Prioritize to find the corresponding configuration based on the incoming quick_model
                    if target_model and target_model != "Unknown":
                        for cfg in doc["llm_configs"]:
                            if cfg.get("model_name") == target_model:
                                selected_cfg = cfg
                                logger.info(f"📊 [ReportFormatter] Find user-specified model configuration: {target_model}")
                                break

                    # If the specified model is not found, use the domestic LLM alternative.
                    if not selected_cfg:
                        preferred_providers = ["dashscope", "deepseek", "zhipu", "siliconflow"]
                        for cfg in doc["llm_configs"]:
                            if cfg.get("enabled", True):
                                provider = cfg.get("provider", "").lower()
                                if provider in preferred_providers:
                                    selected_cfg = cfg
                                    logger.info(f"📊 [ReportFormatter] Use alternative domestic models: {cfg.get('model_name')}")
                                    break

                    if selected_cfg:
                        quick_llm = create_llm_by_provider(
                            provider=selected_cfg.get("provider", "dashscope"),
                            model=selected_cfg.get("model_name", "qwen-turbo"),
                            backend_url=selected_cfg.get("default_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                            temperature=0.1,
                            max_tokens=2000,
                            timeout=60,
                            api_key=selected_cfg.get("api_key")
                        )
                        logger.info(f"📊 [ReportFormatter] Create using model LLM: {selected_cfg.get('model_name')}")
                client.close()
            except Exception as db_err:
                logger.warning(f"⚠️ [ReportFormatter] Failed to get LLM configuration from database: {db_err}")

            # If database configuration fails, use default configuration
            if quick_llm is None:
                quick_llm = create_llm_by_provider(
                    provider="dashscope",
                    model="qwen-turbo",
                    backend_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    temperature=0.1,
                    max_tokens=2000,
                    timeout=60
                )
                logger.info("📊 [ReportFormatter] Created with default configuration LLM: qwen-turbo")

            signal_processor = SignalProcessor(quick_llm)
            processed = signal_processor.process_signal(fallback_text, stock_code)
            logger.info(f"📊 [ReportFormatter] Use SignalProcessor to process text, the result: action={processed.get('action')}")

            # Merge processing results (preferring the value in decision_raw, if any)
            if not decision_raw.get('reasoning') and processed.get('reasoning'):
                decision_raw['reasoning'] = processed['reasoning']
            if not decision_raw.get('action') and processed.get('action'):
                decision_raw['action'] = processed['action']
            if not decision_raw.get('confidence') and processed.get('confidence'):
                decision_raw['confidence'] = processed['confidence']
            if not decision_raw.get('risk_score') and processed.get('risk_score'):
                decision_raw['risk_score'] = processed['risk_score']

        except Exception as e:
            logger.warning(f"⚠️ [ReportFormatter] SignalProcessor Processing failed: {e}")

    # get action
    action = decision_raw.get('action', 'Neutral')
    chinese_action = ACTION_TRANSLATION.get(action, action) if action else 'Neutral'

    # Get reasoning - clean Markdown format
    # 🔥 Compatible with old and new versions: reasoning or rationale
    # 🔥 Important: reasoning should be extracted from decision_raw, if decision_raw does not have reasoning, use the default value
    # Should not be extracted from fallback_text (usually final_trade_decision) as final_trade_decision will be used to generate summary
    # This is consistent with the way the old engine handles it: in the old engine, if the decision has no reasoning, the default value is used 'No analytical reasoning yet'
    logger.info("🔍 [format_decision] ========== Extract reasoning ==========")
    logger.info(f"🔍 [format_decision] decision_raw Type: {type(decision_raw)}")
    if isinstance(decision_raw, dict):
        logger.info(f"🔍 [format_decision] decision_raw Field: {list(decision_raw.keys())}")
        logger.info(f"🔍 [format_decision] decision_raw.get('reasoning'): {decision_raw.get('reasoning', 'None')}")
        logger.info(f"🔍 [format_decision] decision_raw.get('rationale'): {decision_raw.get('rationale', 'None')}")
    
    reasoning = decision_raw.get('reasoning', '') or decision_raw.get('rationale', '')
    logger.info(f"🔍 [format_decision] initial reasoning value: {reasoning[:200] if reasoning else 'None'}")
    
    if reasoning:
        # Clean up the Markdown format in existing reasoning
        reasoning = _clean_markdown(reasoning)
        logger.info(f"🔍 [format_decision] ✅ Extract from decision_raw to reasoning, cleaned length: {len(reasoning)}")
        logger.info(f"🔍 [format_decision] reasoning Cleaned content: {reasoning[:300]}")
    else:
        # 🔥 If there is no reasoning in decision_raw, use the default value (consistent with old engines)
        # Note: should not be extracted from fallback_text to avoid duplication with summary
        reasoning = 'No analytical reasoning yet'
        logger.info(f"🔍 [format_decision] ⚠️ decision_raw There is no reasoning in , use the default value: {reasoning}")
        logger.info(f"🔍 [format_decision] fallback_text length: {len(fallback_text) if fallback_text else 0}")
        if fallback_text:
            logger.info(f"🔍 [format_decision] fallback_text first 200 characters: {fallback_text[:200]}")
            logger.info("🔍 [format_decision] ⚠️ Note: reasoning will not be extracted from fallback_text to avoid duplication with summary")

    normalized_lists = normalize_research_brief_lists(
        decision_raw.get('core_evidence'),
        decision_raw.get('uncertainties'),
        decision_raw.get('invalidation_conditions'),
        decision_raw.get('watch_items'),
    )

    return {
        'action': chinese_action,
        'analysis_view': chinese_action,
        'confidence': float(decision_raw.get('confidence', 0.5)),
        'risk_score': float(decision_raw.get('risk_score', 0.3)),
        'reasoning': reasoning or 'No analytical reasoning yet',
        'summary': decision_raw.get('summary', '') or '',
        'risk_warning': decision_raw.get('risk_warning', '') or '',
        'core_evidence': normalized_lists['core_evidence'],
        'uncertainties': normalized_lists['uncertainties'],
        'invalidation_conditions': normalized_lists['invalidation_conditions'],
        'watch_items': normalized_lists['watch_items'],
    }


def _remove_author_signature(text: str) -> str:
    """
    Remove AI-generated signature information (author, date, statement, etc.)
    
    Args:
        text: original text
        
    Returns:
        Cleaned text
    """
    import re
    
    if not text:
        return text
    
    # Remove"Written by:XXX"Format of signature
    text = re.sub(r'Written by[: :]\s*[^\n]+\n?', '', text, flags=re.MULTILINE)
    # Remove"Date:XXX"format date signature
    text = re.sub(r'Date[: :]\s*\d{4}year\d{1,2}month\d{1,2}day\s*\n?', '', text, flags=re.MULTILINE)
    # Remove"Statement:XXX"A statement of format (usually near the signature)
    text = re.sub(r'Statement[: :]\s*[^\n]+this report[^\n]+\n?', '', text, flags=re.MULTILINE)
    # remove contains"Written by", "Date", "Statement"Full signature block (multiple lines)
    text = re.sub(
        r'Written by[: :][^\n]+\n Date[: :][^\n]+\n Statement[: :][^\n]+',
        '',
        text,
        flags=re.MULTILINE | re.DOTALL
    )
    # Remove common signature formats (such as"Written by:XXX·YYY") 
    text = re.sub(r'Written by[: :]\s*[^·\n]+[··][^\n]+\n?', '', text, flags=re.MULTILINE)
    # Remove"analyst·XXX"Format signature (e.g."Bearish Analyst·Li Yan") 
    text = re.sub(r'[^: :\n]+analyst[··][^\n]+\n?', '', text, flags=re.MULTILINE)
    
    # Remove extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _clean_markdown(text: str) -> str:
    """
    Clean up Markdown formatting tags

    Args:
        text: original text

    Returns:
        Cleaned text
    """
    import re

    if not text:
        return text

    # 🔥 Process escape characters first (process \\n etc.)
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', ' ')
    text = text.replace('\\r', '')

    # Remove Markdown separators (--- or ___ or ***)
    text = re.sub(r'^[\-_\*]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Remove Markdown title tag (###, ##, #)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove reference mark (>)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

    # Remove bold mark (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic mark (*text* or _text_)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove code block tags (```code```)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    # Remove inline tags (`code`)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove link tag ([text](url))
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # Remove list mark (-, *, +, numbers.)
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove Chinese number list markers (one, two, three,)
    text = re.sub(r'^[One, two, three, four, five, six, seven, eight, ninety]+[, \.]\s*', '', text, flags=re.MULTILINE)

    # 🔥 Remove AI-generated signature information
    text = _remove_author_signature(text)

    # Remove extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove leading whitespace
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)

    return text.strip()


def generate_summary_recommendation(
    reports: Dict[str, str],
    decision: Dict[str, Any],
    stock_code: str
) -> Tuple[str, str]:
    """
    Generate summary and recommendation

    🔥 Important: summary and decision.reasoning should have different sources and content
    - summary: Extract analysis summary (first 200 characters) from final_trade_decision or other reports
    - decision.reasoning: Extract reasoning process from final_decision.reasoning (short summary, first 150 characters)
    - recommendation: The unified closing is a research auxiliary prompt and no trading advice is generated.

    Args:
        reports: report dictionary
        decision: Formatted decision making
        stock_code: Stock code

    Returns:
        (summary, recommendation) tuple
    """
    summary = ""
    recommendation = ""

    logger.info("🔍 [generate_summary_recommendation] ========== generate summary ==========")
    logger.info(f"🔍 [generate_summary_recommendation] reports fields in: {list(reports.keys())}")
    for report_name in reports.keys():
        if isinstance(reports[report_name], str):
            logger.info(f"🔍 [generate_summary_recommendation] reports['{report_name}'] length: {len(reports[report_name])}, first 100 characters: {reports[report_name][:100]}")

    # 🔥 Important: Consistent with the old engine, summary (analysis summary) is extracted from final_trade_decision first
    # How the old engine handles it: extract summary (first 200 characters) from final_trade_decision in reports first
    # 1. Prefer extracting summary from final_trade_decision (consistent with old engine)
    logger.info(f"🔍 [generate_summary_recommendation] Check 'final_trade_decision' Is it in reports: {'final_trade_decision' in reports}")
    if 'final_trade_decision' in reports:
        content = reports['final_trade_decision']
        logger.info(f"🔍 [generate_summary_recommendation] final_trade_decision content length: {len(content)}")
        logger.info(f"🔍 [generate_summary_recommendation] final_trade_decision first 300 characters: {content[:300]}")
        if len(content) > 50:
            # Clean up Markdown format, extract first 200 characters as summary (consistent with old engine)
            cleaned_content = _clean_markdown(content)
            summary = cleaned_content[:200].strip()
            if len(cleaned_content) > 200:
                summary += "..."
            logger.info(f"🔍 [generate_summary_recommendation] ✅ Extract summary from final_trade_decision: {len(summary)}character")
            logger.info(f"🔍 [generate_summary_recommendation] summary content: {summary[:300]}")

    # 2. Without final_trade_decision, extract summary from other reports
    if not summary:
        logger.info("🔍 [generate_summary_recommendation] final_trade_decision Does not exist or is empty, try to extract from other reports")
        for report_name in ['investment_plan', 'trader_investment_plan', 'research_team_decision', 'market_report']:
            logger.info(f"🔍 [generate_summary_recommendation] Check '{report_name}': {'exist' if report_name in reports else 'does not exist'}")
            if report_name in reports:
                content = reports[report_name]
                logger.info(f"🔍 [generate_summary_recommendation] {report_name} content length: {len(content)}")
                if len(content) > 100:
                    cleaned_content = _clean_markdown(content)
                    summary = cleaned_content[:200].strip()
                    if len(cleaned_content) > 200:
                        summary += "..."
                    logger.info(f"🔍 [generate_summary_recommendation] ✅ from {report_name} Extract summary: {len(summary)}character")
                    logger.info(f"🔍 [generate_summary_recommendation] summary content: {summary[:300]}")
                    break

    # 3. Last resort
    if not summary:
        summary = f"Yes{stock_code}The analysis has been completed, please view the detailed report."
        logger.warning("⚠️ [Summary] Use alternate summaries")

    # 4. Generate recommendations (unified research auxiliary tips)
    logger.info("🔍 [generate_summary_recommendation] ========== generate recommendation ==========")
    logger.info(f"🔍 [generate_summary_recommendation] decision Field: {list(decision.keys())}")
    # 🔥 recommendation Should be based on the decision's action, target_price, and a short summary of the reasoning
    # Note: Complete reasoning is not used here to avoid confusion with"Research basis"Repeat
    action = decision.get('action') or decision.get('analysis_view') or 'Neutral'
    reasoning = decision.get('reasoning', '')
    
    logger.info(f"🔍 [generate_summary_recommendation] decision.action: {action}")
    logger.info(f"🔍 [generate_summary_recommendation] decision.reasoning length: {len(reasoning)}, content: {reasoning[:200]}")

    recommendation = f"Research perspective:{action}. Please use detailed reporting to focus on changes in evidence, risk factors and subsequent disclosures."
    if reasoning:
        short_reasoning = reasoning[:60] + "..." if len(reasoning) > 60 else reasoning
        recommendation += f" Core basis:{short_reasoning}"

    if not recommendation:
        recommendation = "Please refer to the detailed research report, focusing on fundamental changes, market environment and risk factors."
        logger.warning("⚠️ [Recommendation] Use backup research tips")
    
    logger.info(f"🔍 [generate_summary_recommendation] recommendation final content: {recommendation[:300]}")

    logger.info(f"✅ [Summary/Recommendation] summary={len(summary)}character, recommendation={len(recommendation)}character")
    return summary, recommendation


def calculate_risk_level(risk_score: float) -> str:
    """
    Calculate risk level based on risk score

    Args:
        risk_score: risk score (0-1)

    Returns:
        Risk level string
    """
    if risk_score >= 0.7:
        return "high"
    elif risk_score >= 0.4:
        return "medium"
    else:
        return "low"


def format_analysis_result(
    raw_result: Dict[str, Any],
    stock_code: str,
    stock_name: str,
    analysis_date: str,
    task_id: str,
    analysts: list = None,
    research_depth: str = "Standard",
    quick_model: str = "Unknown",
    deep_model: str = "Unknown",
    execution_time: float = 0,
) -> Dict[str, Any]:
    """
    Unified analysis result formatting function

    Args:
        raw_result: Raw analysis results (usually LangGraph state)
        stock_code: Stock code
        stock_name: Stock name
        analysis_date: Analysis date
        task_id: Task ID
        analysts: List of selected analysts
        research_depth: Research depth
        quick_model: Quickly analyze models
        deep_model: Deep analysis model
        execution_time: Execution time (seconds)

    Returns:
        Complete analysis results after formatting
    """
    # 1. Extract report from raw_result
    logger.info("🔍 [ReportFormatter] ========== Start formatting analysis results ==========")
    logger.info(f"🔍 [ReportFormatter] stock_code={stock_code}, stock_name={stock_name}")
    
    reports = extract_reports_from_state(raw_result)
    logger.info(f"🔍 [ReportFormatter] Extract to {len(reports)} reports: {list(reports.keys())}")
    for report_name, report_content in reports.items():
        if isinstance(report_content, str):
            logger.info(f"🔍 [ReportFormatter] reports['{report_name}'] length: {len(report_content)}, first 100 characters: {report_content[:100]}")

    # 2. Parse and format decisions
    # 🔥 v2.0 Special handling of the engine:
    # - final_decision: May not exist or be empty
    # - action_advice: ActionAdvisorV2 The output of contains research observations and reasoning
    # - final_trade_decision: RiskManagerV2 The output of , containing the full risk assessment report (should not be used for reasoning)
    final_decision = raw_result.get("final_decision", {})
    action_advice = raw_result.get("action_advice", "")
    final_trade_decision = raw_result.get("final_trade_decision", "")

    # 🔥 Detailed log: check the contents of each field
    logger.info("🔍 [ReportFormatter] ========== Check raw data fields ==========")
    logger.info(f"🔍 [ReportFormatter] final_decision Type: {type(final_decision)}")
    if isinstance(final_decision, dict):
        logger.info(f"🔍 [ReportFormatter] final_decision Field: {list(final_decision.keys())}")
        logger.info(f"🔍 [ReportFormatter] final_decision.target_price: {final_decision.get('target_price')}")
        logger.info(f"🔍 [ReportFormatter] final_decision.reasoning: {str(final_decision.get('reasoning', ''))[:200] if final_decision.get('reasoning') else 'None'}")
    else:
        logger.info(f"🔍 [ReportFormatter] final_decision value: {str(final_decision)[:200]}")
    
    # 🔥 Check action_advice (research observation for v2.0 engine)
    logger.info(f"🔍 [ReportFormatter] action_advice Type: {type(action_advice)}")
    if action_advice:
        if isinstance(action_advice, dict):
            action_advice_content = action_advice.get("content", str(action_advice))
            logger.info(f"🔍 [ReportFormatter] action_advice is a dictionary, field: {list(action_advice.keys())}")
        else:
            action_advice_content = str(action_advice)
        logger.info(f"🔍 [ReportFormatter] action_advice existence, length: {len(action_advice_content)}")
        logger.info(f"🔍 [ReportFormatter] action_advice first 300 characters: {action_advice_content[:300]}")
    else:
        logger.info("🔍 [ReportFormatter] action_advice Does not exist or is empty")
    
    logger.info(f"🔍 [ReportFormatter] final_trade_decision Type: {type(final_trade_decision)}")
    logger.info(f"🔍 [ReportFormatter] final_trade_decision length: {len(final_trade_decision) if final_trade_decision else 0}")
    if final_trade_decision:
        final_trade_decision_str = str(final_trade_decision)
        logger.info(f"🔍 [ReportFormatter] final_trade_decision first 300 characters: {final_trade_decision_str[:300]}")
        logger.info(f"🔍 [ReportFormatter] final_trade_decision Is it in reports: {'final_trade_decision' in reports}")
        if 'final_trade_decision' in reports:
            logger.info(f"🔍 [ReportFormatter] reports['final_trade_decision'] length: {len(reports['final_trade_decision'])}, first 300 characters: {reports['final_trade_decision'][:300]}")

    # 🔥 v2.0 Special processing of the engine: priority is extracted from action_advice reasoning
    # If final_decision has no reasoning and action_advice exists, try to extract it from action_advice
    if isinstance(final_decision, dict) and not final_decision.get('reasoning'):
        if action_advice:
            # Try to extract from action_advice reasoning
            if isinstance(action_advice, dict):
                action_advice_content = action_advice.get("content", str(action_advice))
            else:
                action_advice_content = str(action_advice)
            
            # Try to parse JSON format action_advice
            import json
            try:
                if isinstance(action_advice_content, str) and ("{" in action_advice_content or "```json" in action_advice_content):
                    # Extract JSON part
                    json_str = action_advice_content
                    if "```json" in json_str:
                        json_start = json_str.find("```json") + 7
                        json_end = json_str.find("```", json_start)
                        if json_end > json_start:
                            json_str = json_str[json_start:json_end].strip()
                    
                    if json_str.strip().startswith("{"):
                        action_advice_json = json.loads(json_str)
                        # Extract from JSON reasoning
                        if isinstance(action_advice_json, dict):
                            reasoning_from_advice = action_advice_json.get("reasoning") or action_advice_json.get("detailed_analysis", "")
                            if reasoning_from_advice:
                                final_decision['reasoning'] = reasoning_from_advice
                                logger.info(f"✅ [ReportFormatter] Extracted from action_advice reasoning: {len(reasoning_from_advice)}character")
            except Exception as e:
                logger.warning(f"⚠️ [ReportFormatter] Parsing action_advice JSON failed: {e}")

    # 🔥 Pass in quick_model and stock_code to use the model selected by the user
    # 🔥 Important: For the v2.0 engine, if final_decision has no reasoning, try to extract it from action_advice
    # If action_advice is not available, format_decision will use the default value 'No analytical reasoning yet' (consistent with the old engine)
    # final_trade_decision should not be used as a fallback for reasoning because final_trade_decision will be used to generate summary
    fallback_for_reasoning = ""
    if action_advice:
        # Prefer using action_advice as a fallback for reasoning (try to extract reasoning from action_advice)
        if isinstance(action_advice, dict):
            fallback_for_reasoning = action_advice.get("content", str(action_advice))
        else:
            fallback_for_reasoning = str(action_advice)
    
    formatted_decision = format_decision(
        final_decision,
        fallback_for_reasoning,  # Use action_advice if present, otherwise format_decision will use the default value
        quick_model=quick_model,
        stock_code=stock_code
    )
    logger.info(f"🔍 [ReportFormatter] formatted_decision: action={formatted_decision.get('action')}, target_price={formatted_decision.get('target_price')}, reasoning length={len(formatted_decision.get('reasoning', ''))}")

    # 3. Generate summary and recommendation
    # 🔥 Important: summary should be extracted from investment_plan or other comprehensive reports, not from final_trade_decision
    # final_trade_decision is a risk assessment report and should not be used as summary
    summary, recommendation = generate_summary_recommendation(
        reports, formatted_decision, stock_code
    )

    # 4. Calculate risk level
    risk_level = calculate_risk_level(formatted_decision.get('risk_score', 0.3))

    # 5. Build the complete result
    result = {
        "success": True,
        "analysis_id": str(uuid.uuid4()),
        "task_id": task_id,
        "stock_code": stock_code,
        "stock_symbol": stock_code,
        "stock_name": stock_name,
        "analysis_date": analysis_date,

        # Core fields - the front end depends on these
        "summary": summary,
        "recommendation": recommendation,
        "confidence_score": formatted_decision.get("confidence", 0.5),
        "risk_level": risk_level,
        "key_points": [],

        # decision Field - the front end displays research tendencies, research basis, etc.
        "decision": formatted_decision,

        # Report content - including long, short, aggressive, conservative, neutral, etc.
        "reports": reports,

        # Original state (for debugging)
        "state": raw_result,
        "detailed_analysis": final_decision,

        # Analyst and model information
        "analysts": analysts or [],
        "research_depth": research_depth,
        "model_info": f"{quick_model}/{deep_model}",
        "quick_model": quick_model,
        "deep_model": deep_model,

        # Performance indicators
        "execution_time": execution_time,
        "tokens_used": raw_result.get("tokens_used", 0),
        "performance_metrics": raw_result.get("performance_metrics", {}),
    }

    # 🔥 final result log
    logger.info("🔍 [ReportFormatter] ========== Final formatting result ==========")
    logger.info(f"🔍 [ReportFormatter] result.decision.reasoning length: {len(formatted_decision.get('reasoning', ''))}, content: {formatted_decision.get('reasoning', '')[:300]}")
    logger.info(f"🔍 [ReportFormatter] result.summary length: {len(summary)}, content: {summary[:300]}")
    logger.info(f"🔍 [ReportFormatter] result.recommendation length: {len(recommendation)}, content: {recommendation[:300]}")
    logger.info("🔍 [ReportFormatter] ========== Formatting completed ==========")
    logger.info(f"✅ [ReportFormatter] Formatting completed: decision.action={formatted_decision.get('action')}, reports={len(reports)}a")
    return result

# === report_saver.py ===
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


# === thread_safe_db.py ===
"""
Thread-safe database operation tools

Used to safely perform MongoDB operations in the thread pool to avoid event loop conflicts
"""
import threading
import asyncio
import logging
from typing import List, Any
try:
    from pymongo.results import BulkWriteResult
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

logger = logging.getLogger(__name__)


def is_in_thread_pool() -> bool:
    """
    Detect whether it is currently running in the thread pool
    
    Returns:
        True False if in the thread pool, False if in the main thread
    """
    current_thread = threading.current_thread()
    return not isinstance(current_thread, threading._MainThread)


async def safe_bulk_write(
    collection_name: str,
    operations: List,
    ordered: bool = False,
    async_db=None,
    max_retries: int = 3
) -> BulkWriteResult:
    """
    Thread-safe bulk_write operations
    
    Automatically detect the running environment:
    - In the main thread: Using an asynchronous MongoDB client
    - In a thread pool: Using a synchronous MongoDB client
    
    Args:
        collection_name: Collection name
        operations: Bulk operation list
        ordered: Whether to execute in order
        async_db: Asynchronous database instance (used in the main thread)
        max_retries: Maximum number of retries
        
    Returns:
        BulkWriteResult object
        
    Raises:
        Exception: If all retries fail
    """
    in_thread_pool = is_in_thread_pool()
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if in_thread_pool:
                # 🔥 In a thread pool: Using a synchronous MongoDB client
                logger.debug(f"🔍 [thread pool] Use sync bulk_write: collection={collection_name}, operand={len(operations)}, ordered={ordered}")
                from app.core.database import get_mongo_db_sync
                sync_db = get_mongo_db_sync()
                sync_collection = sync_db[collection_name]
                result = sync_collection.bulk_write(operations, ordered=ordered)
                return result
            else:
                # 🔥 In the main thread: Using an asynchronous MongoDB client
                if async_db is None:
                    from app.core.database import get_mongo_db
                    async_db = get_mongo_db()
                
                logger.debug(f"🔍 [main thread] Use async bulk_write: collection={collection_name}, operand={len(operations)}, ordered={ordered}")
                async_collection = async_db[collection_name]
                result = await async_collection.bulk_write(operations, ordered=ordered)
                return result
                
        except asyncio.TimeoutError as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff: 2 seconds, 4 seconds, 8 seconds
                logger.warning(f"⚠️ Batch write timeout (No.{retry_count}/{max_retries}retries), wait{wait_time}Try again in seconds...")
                
                # 🔥 Choose the sleep mode according to the operating environment
                if in_thread_pool:
                    import time
                    time.sleep(wait_time)
                else:
                    await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Batch write failed, retried{max_retries}times: {e}")
                raise
                
        except Exception as e:
            # Check if it is a timeout related error
            error_msg = str(e).lower()
            if 'timeout' in error_msg or 'timed out' in error_msg:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"⚠️ Batch write timeout (No.{retry_count}/{max_retries}retries), wait{wait_time}Try again in seconds... Error: {e}")
                    
                    # 🔥 Choose the sleep mode according to the operating environment
                    if in_thread_pool:
                        import time
                        time.sleep(wait_time)
                    else:
                        await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Batch write failed, retried{max_retries}times: {e}")
                    raise
            else:
                logger.error(f"❌ Batch write failed: {e}")
                raise
    
    raise Exception(f"Batch write failed, retried{max_retries}times")


async def safe_sleep(seconds: float):
    """
    Thread-safe sleep operation
    
    Automatically detect the running environment:
    - In the main thread: use asyncio.sleep
    - In the thread pool: use time.sleep
    
    Args:
        seconds: sleep seconds
    """
    if is_in_thread_pool():
        import time
        time.sleep(seconds)
    else:
        await asyncio.sleep(seconds)


# === timezone.py ===

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from app.core.config import settings


def get_tz_name() -> str:
    """Return configured timezone name, preferring DB system_settings.app_timezone if cached.
    Fallback order: DB (cached) > env (settings.TIMEZONE) > Asia/Shanghai.
    This function is sync and must not await; it relies on provider cache populated elsewhere.
    """
    try:
        # Lazy import to avoid circular imports
        from app.services.config_provider import provider as cfgprov  # type: ignore
        cached = getattr(cfgprov, "_cache_settings", None)
        if isinstance(cached, dict):
            tz = cached.get("app_timezone") or cached.get("APP_TIMEZONE")
            if isinstance(tz, str) and tz.strip():
                return tz.strip()
    except Exception:
        pass
    return settings.TIMEZONE or "Asia/Shanghai"


def get_tz() -> ZoneInfo:
    return ZoneInfo(get_tz_name())


def now_tz() -> datetime:
    """Current time in configured timezone (tz-aware)."""
    return datetime.now(get_tz())


def to_config_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive as UTC by default, then convert to configured tz
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(get_tz())
    return dt.astimezone(get_tz())


def ensure_timezone(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Make sure the datetime object contains time zone information
    If there is no time zone information, the configured time zone is assumed (default Asia/Shanghai)
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # If no time zone information is available, the configured time zone is assumed
        return dt.replace(tzinfo=get_tz())
    return dt


# === trading_time.py ===
"""
Trading time judgment tool module

Provides unified trading time judgment logic to determine whether it is currently within the A-share trading hours.
"""

from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

from app.core.config import settings


def is_trading_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is during A-share trading hours or the post-closing buffer period

    Trading hours:
    - Morning:9:30-11:30
    - Afternoon:13:00-15:00
    - Post-closing buffer period:15:00-15:30 (Make sure to get the closing price)

    Description of the post-closing buffer period:
    - Continue to obtain for 30 minutes after the trading time ends
    - Assuming once every 6 minutes, 5 more synchronization opportunities can be added
    - Greatly reduces the risk of missing the closing price

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it within trading hours?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    
    # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
    morning = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    # Post-closing buffer period (extended by 30 minutes to 15:30) 
    buffer_end = dtime(15, 30)
    
    return (morning <= t <= noon) or (afternoon_start <= t <= buffer_end)


def is_strict_trading_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is within strict A-share trading hours (excluding the buffer period)

    Trading hours:
    - Morning:9:30-11:30
    - Afternoon:13:00-15:00

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Whether it is within strict trading hours
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    
    # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
    morning = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    afternoon_end = dtime(15, 0)
    
    return (morning <= t <= noon) or (afternoon_start <= t <= afternoon_end)


def is_pre_market_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is before the market time (9:00-9:30) 

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it during pre-market time?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    pre_market_start = dtime(9, 0)
    pre_market_end = dtime(9, 30)
    
    return pre_market_start <= t < pre_market_end


def is_after_market_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is after-hours time (15:00-15:30) 

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it after hours?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    after_market_start = dtime(15, 0)
    after_market_end = dtime(15, 30)
    
    return after_market_start <= t <= after_market_end


def get_trading_status(now: Optional[datetime] = None) -> str:
    """
    Get current transaction status

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        str: transaction status
            - "pre_market": Before the market
            - "morning_session": morning trading session
            - "noon_break": Market closed at noon
            - "afternoon_session": Afternoon trading session
            - "after_market": After-hours buffer period
            - "closed": Market closed
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # weekend
    if now.weekday() > 4:
        return "closed"
    
    t = now.time()
    
    # Define time point
    pre_market_start = dtime(9, 0)
    morning_start = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    afternoon_end = dtime(15, 0)
    after_market_end = dtime(15, 30)
    
    # Judgment status
    if pre_market_start <= t < morning_start:
        return "pre_market"
    elif morning_start <= t <= noon:
        return "morning_session"
    elif noon < t < afternoon_start:
        return "noon_break"
    elif afternoon_start <= t <= afternoon_end:
        return "afternoon_session"
    elif afternoon_end < t <= after_market_end:
        return "after_market"
    else:
        return "closed"


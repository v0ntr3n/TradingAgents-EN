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


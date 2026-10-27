"""
Test data export desensitization function
"""
import pytest
from app.services.database.backups import _sanitize_document


def test_sanitize_simple_fields():
    """Test simple field desensitization"""
    doc = {
        "name": "test",
        "api_key": "secret123",
        "api_secret": "secret456",
        "password": "pass123",
        "token": "token123",
        "normal_field": "keep_this"
    }

    result = _sanitize_document(doc)

    assert result["name"] == "test"
    assert result["api_key"] == ""
    assert result["api_secret"] == ""
    assert result["password"] == ""
    assert result["token"] == ""
    assert result["normal_field"] == "keep_this"


def test_sanitize_max_tokens_preserved():
    """Test that the max_tokens field is not desensitized"""
    doc = {
        "provider": "openai",
        "model_name": "gpt-4",
        "api_key": "secret123",
        "max_tokens": 8000,
        "timeout": 180,
        "retry_times": 3,
        "context_length": 32768
    }

    result = _sanitize_document(doc)

    assert result["api_key"] == ""  # Sensitive fields are cleared
    assert result["max_tokens"] == 8000  # max_tokens Reserve
    assert result["timeout"] == 180  # timeout Reserve
    assert result["retry_times"] == 3  # retry_times Reserve
    assert result["context_length"] == 32768  # context_length Reserve


def test_sanitize_nested_dict():
    """Test nested dictionary desensitization"""
    doc = {
        "config": {
            "llm": {
                "api_key": "secret123",
                "model": "gpt-4"
            },
            "database": {
                "password": "dbpass",
                "host": "localhost"
            }
        },
        "name": "test"
    }
    
    result = _sanitize_document(doc)
    
    assert result["config"]["llm"]["api_key"] == ""
    assert result["config"]["llm"]["model"] == "gpt-4"
    assert result["config"]["database"]["password"] == ""
    assert result["config"]["database"]["host"] == "localhost"
    assert result["name"] == "test"


def test_sanitize_list():
    """Test List Desensitization"""
    doc = {
        "providers": [
            {"name": "provider1", "api_key": "key1"},
            {"name": "provider2", "client_secret": "secret2"}
        ]
    }
    
    result = _sanitize_document(doc)
    
    assert result["providers"][0]["name"] == "provider1"
    assert result["providers"][0]["api_key"] == ""
    assert result["providers"][1]["name"] == "provider2"
    assert result["providers"][1]["client_secret"] == ""


def test_sanitize_case_insensitive():
    """Test case insensitivity"""
    doc = {
        "API_KEY": "secret1",
        "Api_Secret": "secret2",
        "PASSWORD": "pass1",
        "Token": "token1"
    }
    
    result = _sanitize_document(doc)
    
    assert result["API_KEY"] == ""
    assert result["Api_Secret"] == ""
    assert result["PASSWORD"] == ""
    assert result["Token"] == ""


def test_sanitize_all_keywords():
    """Test all sensitive keywords"""
    doc = {
        "api_key": "1",
        "api_secret": "2",
        "secret": "3",
        "token": "4",
        "password": "5",
        "client_secret": "6",
        "webhook_secret": "7",
        "private_key": "8",
        "safe_field": "keep"
    }
    
    result = _sanitize_document(doc)
    
    assert result["api_key"] == ""
    assert result["api_secret"] == ""
    assert result["secret"] == ""
    assert result["token"] == ""
    assert result["password"] == ""
    assert result["client_secret"] == ""
    assert result["webhook_secret"] == ""
    assert result["private_key"] == ""
    assert result["safe_field"] == "keep"


def test_sanitize_complex_structure():
    """Test complex structure desensitization (simulate real export data)"""
    doc = {
        "system_configs": [
            {
                "llm_configs": [
                    {
                        "provider": "openai",
                        "api_key": "sk-xxx",
                        "model": "gpt-4"
                    }
                ],
                "system_settings": {
                    "finnhub_api_key": "xxx",
                    "tushare_token": "yyy",
                    "reddit_client_secret": "zzz",
                    "app_name": "TradingAgents"
                }
            }
        ],
        "llm_providers": [
            {
                "name": "OpenAI",
                "api_key": "sk-xxx",
                "base_url": "https://api.openai.com"
            }
        ]
    }
    
    result = _sanitize_document(doc)
    
    # Check that api_key in llm_configs is cleared
    assert result["system_configs"][0]["llm_configs"][0]["api_key"] == ""
    assert result["system_configs"][0]["llm_configs"][0]["model"] == "gpt-4"
    
    # Check that sensitive fields in system_settings are cleared
    assert result["system_configs"][0]["system_settings"]["finnhub_api_key"] == ""
    assert result["system_configs"][0]["system_settings"]["tushare_token"] == ""
    assert result["system_configs"][0]["system_settings"]["reddit_client_secret"] == ""
    assert result["system_configs"][0]["system_settings"]["app_name"] == "TradingAgents"
    
    # Check that api_key in llm_providers is cleared
    assert result["llm_providers"][0]["api_key"] == ""
    assert result["llm_providers"][0]["base_url"] == "https://api.openai.com"


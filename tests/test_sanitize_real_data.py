"""
Test the desensitization function of real exported data
"""
import json
from app.services.database.backups import _sanitize_document


def test_sanitize_real_export_file():
    """Test desensitization on real exported files"""
    # Read real export file
    with open("install/database_export_config_2025-10-25.json", "r", encoding="utf-8") as f:
        export_data = json.load(f)
    
    # Desensitize the data part
    sanitized_data = _sanitize_document(export_data["data"])
    
    # Verify that api_key in system_configs is cleared
    for config in sanitized_data.get("system_configs", []):
        for llm_config in config.get("llm_configs", []):
            assert llm_config.get("api_key") == "", f"api_key should be cleared, but the actual value is: {llm_config.get('api_key')}"
        
        # Verify that sensitive fields in system_settings are cleared
        system_settings = config.get("system_settings", {})
        for key in ["finnhub_api_key", "tushare_token", "reddit_client_secret"]:
            if key in system_settings:
                assert system_settings[key] == "", f"{key} should be cleared, but the actual value is: {system_settings[key]}"
    
    # Verify that api_key in llm_providers is cleared
    for provider in sanitized_data.get("llm_providers", []):
        assert provider.get("api_key") == "", f"llm_providers The api_key should be cleared, but the actual value is: {provider.get('api_key')}"
    
    # Output statistics
    print("\n✅ Desensitization test passed!")
    print(f"- system_configs Quantity: {len(sanitized_data.get('system_configs', []))}")
    print(f"- llm_providers Quantity: {len(sanitized_data.get('llm_providers', []))}")
    print(f"- users Quantity: {len(sanitized_data.get('users', []))}")
    
    # Save desensitized files for comparison
    sanitized_export = {
        "export_info": export_data["export_info"],
        "data": sanitized_data
    }
    
    with open("install/database_export_config_2025-10-25_SANITIZED.json", "w", encoding="utf-8") as f:
        json.dump(sanitized_export, f, ensure_ascii=False, indent=2)
    
    print("✅ The desensitized file has been saved to: install/database_export_config_2025-10-25_SANITIZED.json")


if __name__ == "__main__":
    test_sanitize_real_export_file()


# Duplicate Logger definition repair report

## Summary

- Total number of scanned files: 321
- Number of duplicate definition files found: 98
- Number of files successfully repaired: 98
- Remove duplicate definitions altogether: 108
- Number of files that failed to be repaired: 0

## Repair details

### fix_stock_code_issue.py

- Number of original logger definitions: 3
  - Line 12: `logger = get_logger('default')`
  - Line 106: `logger = get_logger("default")`
  - Line 139: `logger = get_logger('default')`

### main.py

- Number of original logger definitions: 2
  - Line 6: `logger = get_logger('default')`
  - Line 8: `logger = get_logger('default')`

### quick_syntax_check.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('default')`
  - Line 18: `logger = get_logger('default')`

### stock_code_validator.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('default')`
  - Line 19: `logger = get_logger('default')`

### syntax_checker.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('default')`
  - Line 18: `logger = get_logger('default')`

### test_fundamentals_tracking.py

- Number of original logger definitions: 2
  - Line 25: `logger = get_logger("default")`
  - Line 97: `logger = get_logger("default")`

### test_simple_tracking.py

- Number of original logger definitions: 3
  - Line 25: `logger = get_logger("default")`
  - Line 75: `logger = get_logger("default")`
  - Line 125: `logger = get_logger("default")`

### data\scripts\sync_stock_info_to_mongodb.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('scripts')`
  - Line 397: `logger = get_logger('scripts')`

### examples\batch_analysis.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('default')`
  - Line 24: `logger = get_logger('default')`

### examples\cli_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('cli')`
  - Line 15: `logger = get_logger('cli')`

### examples\config_management_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 253: `logger = get_logger('default')`

### examples\custom_analysis_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 277: `logger = get_logger('default')`

### examples\data_dir_config_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 243: `logger = get_logger('default')`

### examples\demo_deepseek_analysis.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('default')`
  - Line 208: `logger = get_logger('default')`

### examples\my_stock_analysis.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 123: `logger = get_logger('default')`

### examples\simple_analysis_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 202: `logger = get_logger('default')`

### examples\stock_list_example.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('default')`
  - Line 16: `logger = get_logger('default')`

### examples\stock_query_examples.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 249: `logger = get_logger('default')`

### examples\token_tracking_demo.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('default')`
  - Line 33: `logger = get_logger('default')`

### examples\tushare_demo.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 258: `logger = get_logger('default')`

### examples\dashscope_examples\demo_dashscope.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 124: `logger = get_logger('default')`

### examples\dashscope_examples\demo_dashscope_chinese.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 146: `logger = get_logger('default')`

### examples\dashscope_examples\demo_dashscope_no_memory.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 115: `logger = get_logger('default')`

### examples\dashscope_examples\demo_dashscope_simple.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 111: `logger = get_logger('default')`

### examples\openai\demo_openai.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 22: `logger = get_logger('default')`

### scripts\analyze_data_calls.py

- Number of original logger definitions: 2
  - Line 18: `logger = get_logger('scripts')`
  - Line 20: `logger = get_logger('scripts')`

### scripts\build_docker_with_pdf.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 15: `logger = get_logger('scripts')`

### scripts\install_pandoc.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('scripts')`
  - Line 37: `logger = get_logger('scripts')`

### scripts\install_pdf_tools.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('scripts')`
  - Line 178: `logger = get_logger('scripts')`

### scripts\log_analyzer.py

- Number of original logger definitions: 2
  - Line 18: `logger = get_logger('scripts')`
  - Line 20: `logger = get_logger('scripts')`

### scripts\migrate_to_unified_logging.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('scripts')`
  - Line 18: `logger = get_logger('scripts')`

### scripts\setup-docker.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 121: `logger = get_logger('scripts')`

### scripts\deployment\create_github_release.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 16: `logger = get_logger('scripts')`

### scripts\deployment\release_v0.1.2.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 16: `logger = get_logger('scripts')`

### scripts\deployment\release_v0.1.3.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 16: `logger = get_logger('scripts')`

### scripts\development\adaptive_cache_manager.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('scripts')`
  - Line 114: `logger = get_logger('scripts')`

### scripts\development\download_finnhub_sample_data.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('scripts')`
  - Line 232: `logger = get_logger('scripts')`

### scripts\development\fix_streamlit_watcher.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('scripts')`
  - Line 21: `logger = get_logger('scripts')`

### scripts\development\organize_scripts.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 15: `logger = get_logger('scripts')`

### scripts\development\prepare_upstream_contribution.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('scripts')`
  - Line 19: `logger = get_logger('scripts')`

### scripts\git\branch_manager.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 16: `logger = get_logger('scripts')`

### scripts\git\check_branch_overlap.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 15: `logger = get_logger('scripts')`

### scripts\maintenance\branch_manager.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 139: `logger = get_logger('scripts')`

### scripts\maintenance\cleanup_cache.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 146: `logger = get_logger('scripts')`

### scripts\maintenance\finalize_script_organization.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 338: `logger = get_logger('scripts')`

### scripts\maintenance\organize_root_scripts.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 233: `logger = get_logger('scripts')`

### scripts\maintenance\sync_upstream.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('scripts')`
  - Line 254: `logger = get_logger('scripts')`

### scripts\maintenance\version_manager.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('scripts')`
  - Line 18: `logger = get_logger('scripts')`

### scripts\setup\configure_pip_source.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 224: `logger = get_logger('scripts')`

### scripts\setup\initialize_system.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 323: `logger = get_logger('scripts')`

### scripts\setup\init_database.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 221: `logger = get_logger('scripts')`

### scripts\setup\manual_pip_config.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 214: `logger = get_logger('scripts')`

### scripts\setup\migrate_env_to_config.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 172: `logger = get_logger('scripts')`

### scripts\setup\setup_databases.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('scripts')`
  - Line 198: `logger = get_logger('scripts')`

### scripts\validation\check_dependencies.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('scripts')`
  - Line 135: `logger = get_logger('scripts')`

### scripts\validation\check_system_status.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 251: `logger = get_logger('scripts')`

### scripts\validation\smart_config.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('scripts')`
  - Line 63: `logger = get_logger('scripts')`

### scripts\validation\verify_gitignore.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('scripts')`
  - Line 15: `logger = get_logger('scripts')`

### tradingagents\agents\utils\agent_utils.py

- Number of original logger definitions: 3
  - Line 23: `logger = get_logger('agents')`
  - Line 24: `logger = get_logger("agents.utils")`
  - Line 1133: `logger = get_logger('agents')`

### tradingagents\api\stock_api.py

- Number of original logger definitions: 3
  - Line 15: `logger = get_logger('agents')`
  - Line 24: `logger = get_logger("default")`
  - Line 29: `logger = get_logger('agents')`

### tradingagents\config\config_manager.py

- Number of original logger definitions: 3
  - Line 20: `logger = get_logger('agents')`
  - Line 21: `logger = get_logger("config")`
  - Line 455: `logger = get_logger('agents')`

### tradingagents\config\mongodb_storage.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('agents')`
  - Line 269: `logger = get_logger('agents')`

### tradingagents\dataflows\akshare_utils.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('agents')`
  - Line 240: `logger = get_logger('agents')`

### tradingagents\dataflows\cache_manager.py

- Number of original logger definitions: 2
  - Line 18: `logger = get_logger('agents')`
  - Line 97: `logger = get_logger('agents')`

### tradingagents\dataflows\data_source_manager.py

- Number of original logger definitions: 3
  - Line 15: `logger = get_logger('agents')`
  - Line 444: `logger = get_logger('agents')`
  - Line 445: `logger = get_logger("default")`

### tradingagents\dataflows\db_cache_manager.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('agents')`
  - Line 200: `logger = get_logger('agents')`

### tradingagents\dataflows\finnhub_utils.py

- Number of original logger definitions: 2
  - Line 6: `logger = get_logger('agents')`
  - Line 8: `logger = get_logger('agents')`

### tradingagents\dataflows\googlenews_utils.py

- Number of original logger definitions: 2
  - Line 11: `logger = get_logger('agents')`
  - Line 13: `logger = get_logger('agents')`

### tradingagents\dataflows\hk_stock_utils.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('agents')`
  - Line 17: `logger = get_logger('agents')`

### tradingagents\dataflows\interface.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('agents')`
  - Line 1594: `logger = get_logger('agents')`

### tradingagents\dataflows\optimized_china_data.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('agents')`
  - Line 549: `logger = get_logger('agents')`

### tradingagents\dataflows\optimized_us_data.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('agents')`
  - Line 275: `logger = get_logger('agents')`

### tradingagents\dataflows\realtime_news_utils.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('agents')`
  - Line 19: `logger = get_logger('agents')`

### tradingagents\dataflows\stock_api.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('agents')`
  - Line 93: `logger = get_logger('agents')`

### tradingagents\dataflows\stock_data_service.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('agents')`
  - Line 272: `logger = get_logger('agents')`

### tradingagents\dataflows\tdx_utils.py

- Number of original logger definitions: 2
  - Line 15: `logger = get_logger('agents')`
  - Line 852: `logger = get_logger('agents')`

### tradingagents\dataflows\tushare_utils.py

- Number of original logger definitions: 3
  - Line 17: `logger = get_logger('agents')`
  - Line 22: `logger = get_logger("default")`
  - Line 62: `logger = get_logger('agents')`

### tradingagents\dataflows\utils.py

- Number of original logger definitions: 2
  - Line 9: `logger = get_logger('agents')`
  - Line 11: `logger = get_logger('agents')`

### tradingagents\dataflows\yfin_utils.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('agents')`
  - Line 19: `logger = get_logger('agents')`

### tradingagents\dataflows\__init__.py

- Number of original logger definitions: 2
  - Line 8: `logger = get_logger('agents')`
  - Line 29: `logger = get_logger('agents')`

### tradingagents\graph\trading_graph.py

- Number of original logger definitions: 3
  - Line 25: `logger = get_logger('agents')`
  - Line 26: `logger = get_logger("graph.trading_graph")`
  - Line 111: `logger = get_logger('agents')`

### tradingagents\llm_adapters\dashscope_adapter.py

- Number of original logger definitions: 2
  - Line 22: `logger = get_logger('agents')`
  - Line 24: `logger = get_logger('agents')`

### tradingagents\llm_adapters\dashscope_openai_adapter.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('agents')`
  - Line 228: `logger = get_logger('agents')`

### tradingagents\utils\logging_init.py

- Number of original logger definitions: 4
  - Line 30: `logger = get_logger('tradingagents.init')`
  - Line 59: `logger = get_logger(logger_name)`
  - Line 92: `logger = get_logger('tradingagents.startup')`
  - Line 118: `logger = get_logger('tradingagents.shutdown')`

### tradingagents\utils\logging_manager.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('agents')`
  - Line 21: `logger = get_logger('agents')`

### upstream_contribution\batch1_caching\tradingagents\dataflows\cache_manager.py

- Number of original logger definitions: 2
  - Line 18: `logger = get_logger('agents')`
  - Line 97: `logger = get_logger('agents')`

### upstream_contribution\batch1_caching\tradingagents\dataflows\optimized_us_data.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('agents')`
  - Line 240: `logger = get_logger('agents')`

### upstream_contribution\batch2_error_handling\tradingagents\agents\analysts\fundamentals_analyst.py

- Number of original logger definitions: 2
  - Line 9: `logger = get_logger('agents')`
  - Line 258: `logger = get_logger('agents')`

### upstream_contribution\batch2_error_handling\tradingagents\agents\analysts\market_analyst.py

- Number of original logger definitions: 2
  - Line 9: `logger = get_logger('agents')`
  - Line 212: `logger = get_logger('agents')`

### upstream_contribution\batch2_error_handling\tradingagents\dataflows\db_cache_manager.py

- Number of original logger definitions: 2
  - Line 17: `logger = get_logger('agents')`
  - Line 200: `logger = get_logger('agents')`

### upstream_contribution\batch3_data_sources\tradingagents\dataflows\optimized_us_data.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('agents')`
  - Line 240: `logger = get_logger('agents')`

### utils\check_version_consistency.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 15: `logger = get_logger('default')`

### utils\cleanup_unnecessary_dirs.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 15: `logger = get_logger('default')`

### utils\update_data_source_references.py

- Number of original logger definitions: 2
  - Line 13: `logger = get_logger('default')`
  - Line 15: `logger = get_logger('default')`

### web\components\analysis_form.py

- Number of original logger definitions: 2
  - Line 10: `logger = get_logger('web')`
  - Line 12: `logger = get_logger('web')`

### web\components\results_display.py

- Number of original logger definitions: 2
  - Line 16: `logger = get_logger('web')`
  - Line 219: `logger = get_logger('web')`

### web\utils\docker_pdf_adapter.py

- Number of original logger definitions: 2
  - Line 14: `logger = get_logger('web')`
  - Line 90: `logger = get_logger('web')`

### web\utils\report_exporter.py

- Number of original logger definitions: 2
  - Line 19: `logger = get_logger('web')`
  - Line 533: `logger = get_logger('web')`


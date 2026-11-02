"""
TradingAgents-CN Backend Application Package

Provides lazy module alias resolution for consolidated domain modules across
app.models, app.schemas, app.middleware, app.constants, app.utils,
app.services, app.routers, and app.worker.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

# Map consolidated module prefixes and submodule aliases to their canonical domain module
_SINGLE_MODULE_PREFIXES = (
    "app.models.",
    "app.schemas.",
    "app.middleware.",
    "app.constants.",
    "app.utils.",
    "app.services.data_sources.",
    "app.core.lifecycle.",
)

_EXACT_MODULE_ALIASES = {
    # app.services -> analysis_services
    "app.services.analysis": "app.services.analysis_services",
    "app.services.analysis.execution_runner": "app.services.analysis_services",
    "app.services.analysis.provider_resolver": "app.services.analysis_services",
    "app.services.analysis.result_formatter": "app.services.analysis_services",
    "app.services.analysis.status_update_utils": "app.services.analysis_services",
    "app.services.progress": "app.services.analysis_services",
    "app.services.progress.tracker": "app.services.analysis_services",
    "app.services.progress.log_handler": "app.services.analysis_services",
    "app.services.progress_log_handler": "app.services.analysis_services",
    "app.services.redis_progress_tracker": "app.services.analysis_services",
    "app.services.analysis_service": "app.services.analysis_services",
    "app.services.simple_analysis_service": "app.services.analysis_services",
    "app.services.unified_analysis_engine": "app.services.analysis_services",
    "app.services.unified_analysis_service": "app.services.analysis_services",
    "app.services.task_analysis_service": "app.services.analysis_services",
    "app.services.planned_analysis_service": "app.services.analysis_services",
    "app.services.analysis_preference_service": "app.services.analysis_services",
    "app.services.analysis_profile_service": "app.services.analysis_services",
    # app.services -> screening_services
    "app.services.screening_service": "app.services.screening_services",
    "app.services.enhanced_screening_service": "app.services.screening_services",
    "app.services.database_screening_service": "app.services.screening_services",
    "app.services.intelligent_screening_service": "app.services.screening_services",
    "app.services.intelligent_screening_v2": "app.services.screening_services",
    "app.services.screening_metric_display": "app.services.screening_services",
    "app.services.factor_registry_service": "app.services.screening_services",
    # app.services -> market_data_services
    "app.services.basics_sync": "app.services.market_data_services",
    "app.services.basics_sync.utils": "app.services.market_data_services",
    "app.services.basics_sync.processing": "app.services.market_data_services",
    "app.services.stock_data_service": "app.services.market_data_services",
    "app.services.unified_stock_service": "app.services.market_data_services",
    "app.services.foreign_stock_service": "app.services.market_data_services",
    "app.services.historical_data_service": "app.services.market_data_services",
    "app.services.financial_data_service": "app.services.market_data_services",
    "app.services.news_data_service": "app.services.market_data_services",
    "app.services.quotes_service": "app.services.market_data_services",
    "app.services.quotes_ingestion_service": "app.services.market_data_services",
    "app.services.basics_sync_service": "app.services.market_data_services",
    "app.services.multi_source_basics_sync_service": "app.services.market_data_services",
    "app.services.official_industry_service": "app.services.market_data_services",
    "app.services.technical_indicator_materialization_service": "app.services.market_data_services",
    "app.services.trade_date_cache_service": "app.services.market_data_services",
    "app.services.trading_calendar_service": "app.services.market_data_services",
    "app.services.data_consistency_checker": "app.services.market_data_services",
    "app.services.data_validation_service": "app.services.market_data_services",
    # app.services -> portfolio_services
    "app.services.portfolio_service": "app.services.portfolio_services",
    "app.services.favorites_service": "app.services.portfolio_services",
    "app.services.tags_service": "app.services.portfolio_services",
    "app.services.stop_gain_alert_service": "app.services.portfolio_services",
    "app.services.stop_loss_alert_service": "app.services.portfolio_services",
    "app.services.trade_review_service": "app.services.portfolio_services",
    # app.services -> skill_services
    "app.services.skillhub_service": "app.services.skill_services",
    "app.services.clawhub_skill_service": "app.services.skill_services",
    "app.services.skill_credential_service": "app.services.skill_services",
    "app.services.skill_gap_service": "app.services.skill_services",
    "app.services.skill_generation_service": "app.services.skill_services",
    "app.services.capability_index_service": "app.services.skill_services",
    # app.services -> assistant_and_memory_services
    "app.services.intelligent_assistant_service": "app.services.assistant_and_memory_services",
    "app.services.embedded_nanobot_service": "app.services.assistant_and_memory_services",
    "app.services.session_service": "app.services.assistant_and_memory_services",
    "app.services.memory_state_manager": "app.services.assistant_and_memory_services",
    "app.services.project_memory_defaults": "app.services.assistant_and_memory_services",
    "app.services.project_memory_service": "app.services.assistant_and_memory_services",
    # app.services -> config_and_prompt_services
    "app.services.config_provider": "app.services.config_and_prompt_services",
    "app.services.config_service": "app.services.config_and_prompt_services",
    "app.services.model_capability_service": "app.services.config_and_prompt_services",
    "app.services.prompt_assembly_service": "app.services.config_and_prompt_services",
    "app.services.prompt_injection_policy_service": "app.services.config_and_prompt_services",
    "app.services.system_prompt_seed_service": "app.services.config_and_prompt_services",
    "app.services.etf_workflow_prompt_template_service": "app.services.config_and_prompt_services",
    "app.services.report_template_service": "app.services.config_and_prompt_services",
    "app.services.schema_bundle_service": "app.services.config_and_prompt_services",
    # app.services -> workflow_services
    "app.services.workflow_registry": "app.services.workflow_services",
    "app.services.workflow_growth_service": "app.services.workflow_services",
    # app.services -> notification_services
    "app.services.channel_senders": "app.services.notification_services",
    "app.services.channel_senders.webhook_sender": "app.services.notification_services",
    "app.services.channel_notifier": "app.services.notification_services",
    "app.services.notifications_service": "app.services.notification_services",
    "app.services.internal_message_service": "app.services.notification_services",
    "app.services.email_service": "app.services.notification_services",
    "app.services.im_topic_digest_service": "app.services.notification_services",
    "app.services.websocket_manager": "app.services.notification_services",
    # app.services -> system_services
    "app.services.database": "app.services.system_services",
    "app.services.database.serialization": "app.services.system_services",
    "app.services.database.status_checks": "app.services.system_services",
    "app.services.database.cleanup": "app.services.system_services",
    "app.services.database.backups": "app.services.system_services",
    "app.services.queue": "app.services.system_services",
    "app.services.queue.keys": "app.services.system_services",
    "app.services.queue.helpers": "app.services.system_services",
    "app.services.auth_service": "app.services.system_services",
    "app.services.user_service": "app.services.system_services",
    "app.services.license_service": "app.services.system_services",
    "app.services.jdyun_init": "app.services.system_services",
    "app.services.community_bootstrap_service": "app.services.system_services",
    "app.services.database_service": "app.services.system_services",
    "app.services.queue_service": "app.services.system_services",
    "app.services.scheduler_service": "app.services.system_services",
    "app.services.thread_worker": "app.services.system_services",
    "app.services.operation_log_service": "app.services.system_services",
    "app.services.log_export_service": "app.services.system_services",
    "app.services.mcp_audit_service": "app.services.system_services",
    "app.services.quality_metrics_service": "app.services.system_services",
    "app.services.usage_statistics_service": "app.services.system_services",
    "app.services.update_service": "app.services.system_services",
    # app.worker aliases
    "app.worker.base_market_sync": "app.worker.global_market_sync_service",
    "app.worker.akshare_sync_service": "app.worker.global_market_sync_service",
    "app.worker.tushare_sync_service": "app.worker.global_market_sync_service",
    "app.worker.baostock_sync_service": "app.worker.global_market_sync_service",
    "app.worker.akshare_init_service": "app.worker.global_market_sync_service",
    "app.worker.tushare_init_service": "app.worker.global_market_sync_service",
    "app.worker.baostock_init_service": "app.worker.global_market_sync_service",
    "app.worker.hk_data_service": "app.worker.global_market_sync_service",
    "app.worker.hk_sync_service": "app.worker.global_market_sync_service",
    "app.worker.us_data_service": "app.worker.global_market_sync_service",
    "app.worker.us_sync_service": "app.worker.global_market_sync_service",
    "app.worker.qmt_sync_service": "app.worker.global_market_sync_service",
    "app.worker.example_sdk_sync_service": "app.worker.global_market_sync_service",
    "app.worker.etf_sync_service": "app.worker.data_and_etf_sync_service",
    "app.worker.financial_data_sync_service": "app.worker.data_and_etf_sync_service",
    "app.worker.financial_data_sync_task": "app.worker.data_and_etf_sync_service",
    "app.worker.news_data_sync_service": "app.worker.data_and_etf_sync_service",
    "app.worker.favorites_sync_task": "app.worker.data_and_etf_sync_service",
    "app.worker.watchlist_analysis_task": "app.worker.data_and_etf_sync_service",
    "app.worker.thread_pool_sync_service": "app.worker.multi_period_sync_service",
    "app.worker.unified_thread_pool_sync_service": "app.worker.multi_period_sync_service",
    "app.worker.unified_historical_sync_service": "app.worker.multi_period_sync_service",
    "app.worker.launcher": "app.worker.__main__",
    "app.worker.worker_app": "app.worker.__main__",
    # app.routers aliases
    "app.routers.analysis": "app.routers.analysis_routers",
    "app.routers.analysis_profiles": "app.routers.analysis_routers",
    "app.routers.analysis_preferences": "app.routers.analysis_routers",
    "app.routers.reports": "app.routers.analysis_routers",
    "app.routers.unified_tasks": "app.routers.analysis_routers",
    "app.routers.stocks": "app.routers.market_and_stock_routers",
    "app.routers.multi_market_stocks": "app.routers.market_and_stock_routers",
    "app.routers.stock_data": "app.routers.market_and_stock_routers",
    "app.routers.financial_data": "app.routers.market_and_stock_routers",
    "app.routers.news_data": "app.routers.market_and_stock_routers",
    "app.routers.sync": "app.routers.sync_routers",
    "app.routers.stock_sync": "app.routers.sync_routers",
    "app.routers.multi_source_sync": "app.routers.sync_routers",
    "app.routers.multi_period_sync": "app.routers.sync_routers",
    "app.routers.tushare_init": "app.routers.sync_routers",
    "app.routers.akshare_init": "app.routers.sync_routers",
    "app.routers.baostock_init": "app.routers.sync_routers",
    "app.routers.portfolio": "app.routers.portfolio_and_review_routers",
    "app.routers.paper": "app.routers.portfolio_and_review_routers",
    "app.routers.review": "app.routers.portfolio_and_review_routers",
    "app.routers.favorites": "app.routers.portfolio_and_review_routers",
    "app.routers.tags": "app.routers.portfolio_and_review_routers",
    "app.routers.screening": "app.routers.screening_routers",
    "app.routers.intelligent_screening": "app.routers.screening_routers",
    "app.routers.skills": "app.routers.skill_routers",
    "app.routers.skill_center": "app.routers.skill_routers",
    "app.routers.skill_gaps": "app.routers.skill_routers",
    "app.routers.skill_generation": "app.routers.skill_routers",
    "app.routers.capability_index": "app.routers.skill_routers",
    "app.routers.workflows": "app.routers.workflow_routers",
    "app.routers.workflow_growth": "app.routers.workflow_routers",
    "app.routers.intelligent_assistant": "app.routers.assistant_and_memory_routers",
    "app.routers.embedded_nanobot": "app.routers.assistant_and_memory_routers",
    "app.routers.memory": "app.routers.assistant_and_memory_routers",
    "app.routers.knowledge": "app.routers.assistant_and_memory_routers",
    "app.routers.advanced_courses": "app.routers.assistant_and_memory_routers",
    "app.routers.config": "app.routers.config_routers",
    "app.routers.model_capabilities": "app.routers.config_routers",
    "app.routers.system_config": "app.routers.config_routers",
    "app.routers.notifications": "app.routers.notification_and_stream_routers",
    "app.routers.internal_messages": "app.routers.notification_and_stream_routers",
    "app.routers.websocket_notifications": "app.routers.notification_and_stream_routers",
    "app.routers.sse": "app.routers.notification_and_stream_routers",
    "app.routers.auth": "app.routers.system_and_auth_routers",
    "app.routers.auth_db": "app.routers.system_and_auth_routers",
    "app.routers.health": "app.routers.system_and_auth_routers",
    "app.routers.queue": "app.routers.system_and_auth_routers",
    "app.routers.database": "app.routers.system_and_auth_routers",
    "app.routers.cache": "app.routers.system_and_auth_routers",
    "app.routers.logs": "app.routers.system_and_auth_routers",
    "app.routers.operation_logs": "app.routers.system_and_auth_routers",
    "app.routers.usage_statistics": "app.routers.system_and_auth_routers",
    "app.routers.scheduler": "app.routers.system_and_auth_routers",
    "app.routers.update": "app.routers.system_and_auth_routers",
    "app.routers.quality_metrics": "app.routers.system_and_auth_routers",
}


def resolve_consolidated_target(fullname: str) -> str | None:
    if fullname in _EXACT_MODULE_ALIASES:
        return _EXACT_MODULE_ALIASES[fullname]
    for prefix in _SINGLE_MODULE_PREFIXES:
        if fullname.startswith(prefix):
            return prefix[:-1]
    return None


class _ConsolidatedAliasLoader(importlib.abc.Loader):
    def __init__(self, target_name: str):
        self.target_name = target_name

    def create_module(self, spec):
        target_mod = importlib.import_module(self.target_name)
        # If target_mod populated sys.modules[spec.name] (e.g., virtual router module), return that!
        if spec.name in sys.modules:
            return sys.modules[spec.name]
        sys.modules[spec.name] = target_mod
        return target_mod

    def exec_module(self, module):
        pass


class _ConsolidatedAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        target_name = resolve_consolidated_target(fullname)
        if target_name is not None:
            return importlib.machinery.ModuleSpec(fullname, _ConsolidatedAliasLoader(target_name))
        return None


if not any(isinstance(f, _ConsolidatedAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _ConsolidatedAliasFinder())

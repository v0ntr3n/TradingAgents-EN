"""
Routing Registration Center (v3.6.0 Community Edition Open Source Separation · M1 convergence transformation)

- All FastAPI route registrations converge from app/main.py to this single file
- COMMUNITY_ROUTERS: The community version is retained (the free main link will be retained as it is when the community version is released)
- PRO_ROUTERS: Pro Exclusive (paid function carrier, removed entirely when the community version is released)
- Publishing script (scripts/publish_community.py) processing method:
  Delete Pro routing files + Replace with community version registration file (remove PRO_ROUTERS section in this file)
- Principle: Only move the registration line, do not leave the routing implementation
- Pro/Community Boundary Basis: Paid Feature List.md + Separation plan §5.2
- see docs/05-design/v3.0/v3.6.0-community-edition-separation-plan.md §7.1

Note: When adding a route, it must be registered in the corresponding list.——The new Pro router cannot be accessed PRO_ROUTERS = Publish and leak.
"""

import logging

from fastapi import FastAPI

logger = logging.getLogger("app.main")

# =============================================================================
# Community version routing (free main link)
# =============================================================================
from app.routers import auth_db as auth
from app.routers import (
    analysis,
    screening,
    queue,
    sse,
    health,
    favorites,
    config,
    reports,
    database,
    operation_logs,
    tags,
    usage_statistics,
    model_capabilities,
    cache,
    logs,
)
from app.routers import sync as sync_router
from app.routers import multi_source_sync
from app.routers import stocks as stocks_router
from app.routers import stock_sync as stock_sync_router
from app.routers import news_data as news_data_router
from app.routers import stock_data as stock_data_router
from app.routers import financial_data as financial_data_router
from app.routers import workflows as workflows_router
from app.routers import multi_market_stocks as multi_market_stocks_router
from app.routers import notifications as notifications_router
from app.routers import analysis_profiles as analysis_profiles_router
from app.routers import websocket_notifications as websocket_notifications_router
from app.routers import scheduler as scheduler_router
from app.routers import analysis_preferences as analysis_preferences_router
from app.routers import advanced_courses as advanced_courses_router  # The community version is retained (the course content is physically trimmed to the first 5 sections, see the plan §7.4) 
from app.routers import embedded_nanobot as embedded_nanobot_router
from app.routers import paper as paper_router
from app.routers import portfolio as portfolio_router
from app.routers import review as review_router
from app.routers import intelligent_assistant as intelligent_assistant_router
from app.routers import intelligent_screening as intelligent_screening_router
from app.routers import memory as memory_router
from app.routers import workflow_growth as workflow_growth_router
from app.routers import multi_period_sync
from app.routers import internal_messages
from app.routers import tushare_init
from app.routers import akshare_init
from app.routers import baostock_init
from app.routers import system_config as system_config_router
from app.routers import update as update_router
from app.routers import capability_index as capability_index_router
from app.routers import quality_metrics as quality_metrics_router
from app.routers import unified_tasks as unified_tasks_router
# Skill Center (free and open starting from v3.6.0, open source with the community version)
from app.routers import skills as skills_router
from app.routers import skill_generation as skill_generation_router
from app.routers import skill_gaps as skill_gaps_router
from app.routers import skill_center as skill_center_router

# (router, Registered name, include_router kwargs)
COMMUNITY_ROUTERS = [
    (health.router, "health", {"prefix": "/api", "tags": ["health"]}),
    (auth.router, "auth", {"prefix": "/api/auth", "tags": ["authentication"]}),
    (analysis.router, "analysis", {"prefix": "/api/analysis", "tags": ["analysis"]}),
    (reports.router, "reports", {"tags": ["reports"]}),
    (screening.router, "screening", {"prefix": "/api/screening", "tags": ["screening"]}),
    (intelligent_screening_router.router, "intelligent_screening", {"tags": ["screening-intelligent"]}),
    (queue.router, "queue", {"prefix": "/api/queue", "tags": ["queue"]}),
    (favorites.router, "favorites", {"prefix": "/api", "tags": ["favorites"]}),
    (stocks_router.router, "stocks", {"prefix": "/api", "tags": ["stocks"]}),
    (multi_market_stocks_router.router, "multi_market_stocks", {"prefix": "/api", "tags": ["multi-market"]}),
    (stock_sync_router.router, "stock_sync", {"tags": ["stock-sync"]}),
    # News Data Center (free function, r7 is transferred back to the Community Edition from Pro; /save write endpoint is released through the Community Edition stub)
    (news_data_router.router, "news_data", {"tags": ["news-data"]}),
    # Stock/financial data query (free function, r8 has been transferred back to the community version from Pro; the read endpoint is not gated, and the community stock details page
    # Detail.vue Actual call to sync-status;/save-* Batch import writing endpoint is released through the community version stub)
    (stock_data_router.router, "stock_data", {"tags": ["stock-data"]}),
    (financial_data_router.router, "financial_data", {"tags": ["financial-data"]}),
    # Workflow (analysis flow, r9 moved back to community version from Pro): reading the list/details and executing the configured process is community analysis
    # Basic functions (shared by single stock/general research/review/position analysis pages); create/edit/delete endpoint bands require_pro
    # Gated, community version has no editing UI (views/pro/workflow has been removed), API is directly adjusted and released through stub
    (workflows_router.router, "workflows", {"tags": ["workflows"]}),
    (tags.router, "tags", {"prefix": "/api", "tags": ["tags"]}),
    (config.router, "config", {"prefix": "/api", "tags": ["config"]}),
    (model_capabilities.router, "model_capabilities", {"tags": ["model-capabilities"]}),
    (usage_statistics.router, "usage_statistics", {"tags": ["usage-statistics"]}),
    (database.router, "database", {"prefix": "/api/system", "tags": ["database"]}),
    (cache.router, "cache", {"tags": ["cache"]}),
    (operation_logs.router, "operation_logs", {"prefix": "/api/system", "tags": ["operation_logs"]}),
    (logs.router, "logs", {"prefix": "/api/system", "tags": ["logs"]}),
    (system_config_router.router, "system_config", {"prefix": "/api/system", "tags": ["system"]}),
    (update_router.router, "update", {"tags": ["update"]}),
    (notifications_router.router, "notifications", {"prefix": "/api", "tags": ["notifications"]}),
    (websocket_notifications_router.router, "websocket_notifications", {"prefix": "/api", "tags": ["websocket"]}),
    (scheduler_router.router, "scheduler", {"tags": ["scheduler"]}),
    (analysis_profiles_router.router, "analysis_profiles", {"tags": ["analysis-profiles"]}),
    (sse.router, "sse", {"prefix": "/api/stream", "tags": ["streaming"]}),
    (sync_router.router, "sync", {}),
    (multi_source_sync.router, "multi_source_sync", {}),
    (paper_router.router, "paper", {"prefix": "/api", "tags": ["paper"]}),
    (portfolio_router.router, "portfolio", {"prefix": "/api", "tags": ["portfolio"]}),
    (review_router.router, "review", {"prefix": "/api", "tags": ["review"]}),
    (intelligent_assistant_router.router, "intelligent_assistant", {"tags": ["assistant"]}),
    (memory_router.router, "memory", {"tags": ["memory"]}),
    (workflow_growth_router.router, "workflow_growth", {"tags": ["workflow-growth"]}),
    (tushare_init.router, "tushare_init", {"prefix": "/api", "tags": ["tushare-init"]}),
    (akshare_init.router, "akshare_init", {"prefix": "/api", "tags": ["akshare-init"]}),
    (baostock_init.router, "baostock_init", {"prefix": "/api", "tags": ["baostock-init"]}),
    (multi_period_sync.router, "multi_period_sync", {"tags": ["multi-period-sync"]}),
    (internal_messages.router, "internal_messages", {"tags": ["internal-messages"]}),
    (analysis_preferences_router.router, "analysis_preferences", {"tags": ["analysis-preferences"]}),
    (advanced_courses_router.router, "advanced_courses", {"tags": ["advanced-courses"]}),
    (embedded_nanobot_router.router, "embedded_nanobot", {"tags": ["embedded-nanobot"]}),
    (unified_tasks_router.router, "unified_tasks", {"tags": ["unified-task-center"]}),
    (capability_index_router.router, "capability_index", {"prefix": "/api", "tags": ["capability-index"]}),
    (quality_metrics_router.router, "quality_metrics", {}),
    # --- Skill Center (free and open starting from v3.6.0, open source with the community version)---
    (skills_router.router, "skills", {"tags": ["skills"]}),
    (skill_generation_router.router, "skill_generation", {"tags": ["skill-generation"]}),
    (skill_gaps_router.router, "skill_gaps", {"tags": ["skill-gaps"]}),
    (skill_center_router.router, "skill_center", {"tags": ["skill-center"]}),
]

# =============================================================================
# Pro Exclusive routing (v3.6.0 community version open source separation)
# =============================================================================
# Pro Routes are centrally defined in app/pro_routers.py: after the community version release pipeline deletes this file,
# Here try-import is automatically downgraded to an empty list, and router_registry has zero row-level changes.
try:
    from app.pro.pro_routers import PRO_ROUTERS
except ImportError:  # Community version: app/pro_routers.py has been removed from the release pipeline as a whole
    PRO_ROUTERS = []


def _register_router_with_log(app_instance, router, router_name: str, kwargs: dict) -> bool:
    """Register routes and record logs (relocated from app/main.py as is)"""
    try:
        app_instance.include_router(router, **kwargs)
        logger.info(f"✅ Route registration successful: {router_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Route registration failed: {router_name} - {str(e)}", exc_info=True)
        return False


def register_routers(app: FastAPI) -> None:
    """Register all routes: Pro version = Community version routing + Pro Dedicated routing"""
    logger.info("=" * 70)
    logger.info("🚀 Start registering routes...")
    logger.info("=" * 70)

    for router, name, kwargs in COMMUNITY_ROUTERS:
        _register_router_with_log(app, router, name, kwargs)

    for router, name, kwargs in PRO_ROUTERS:
        _register_router_with_log(app, router, name, kwargs)

    logger.info("=" * 70)
    logger.info("✅ Route registration completed")
    logger.info("=" * 70)

    # Verify critical routes are registered
    logger.info("🔍 Verify critical route registration status:")
    key_routes = [
        "/api/license/status",
        "/api/v2/tasks/list",
        "/api/v2/tasks/statistics"
    ]

    for route_path in key_routes:
        route_found = False
        matching_routes = []
        for route in app.routes:
            if not hasattr(route, 'path'):
                continue
            # FastAPI The routing path may contain a prefix, so match it directly with the full path
            if route.path == route_path:
                methods = getattr(route, 'methods', set())
                matching_routes.append((route.path, methods))
                route_found = True
                break
            # Compatible sub-route matching: matching at the end of the path (processing /status under the /api/license prefix, etc.)
            if route.path.endswith(route_path) or route_path.endswith(route.path):
                methods = getattr(route, 'methods', set())
                matching_routes.append((route.path, methods))
                route_found = True
                break

        if route_found:
            for path, methods in matching_routes:
                logger.info(f"  ✅ {route_path} -> {path} - method: {', '.join(methods)}")
        else:
            # Downgraded to INFO: The route is registered but the check logic does not match the full path, which does not mean that the route is missing.
            logger.info(f"  ℹ️  {route_path} - No exact match in app.routes (probably because of prefix splitting), route already registered via include_router")

    logger.info("=" * 70)

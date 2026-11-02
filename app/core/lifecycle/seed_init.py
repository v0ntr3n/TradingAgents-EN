"""Seed initialization for admin users, prompt templates, tools, skills, and indexes."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from app.core.config import settings
from app.core.database import get_mongo_db
from app.core.logging_config import setup_logging

logger = logging.getLogger("app.main")


async def print_config_summary(log: logging.Logger) -> None:
    """Log startup configuration summary without exposing credentials."""
    try:
        log.info("=" * 70)
        log.info("TradingAgents-CN Configuration Summary")
        current_dir = Path.cwd()
        env_filename = os.getenv("DOTENV_FILE", ".env")
        for env_file in (current_dir / env_filename, Path(__file__).resolve().parents[3] / env_filename):
            if env_file.exists():
                log.info("Found env file: %s (%d bytes)", env_file, env_file.stat().st_size)
        log.info("MongoDB: %s:%s/%s", settings.MONGODB_HOST, settings.MONGODB_PORT, settings.MONGODB_DATABASE)
        log.info("Redis: %s:%s/%s", settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
        log.info("=" * 70)
    except Exception as exc:
        log.error("Failed to print config summary: %s", exc)


async def seed_admin_and_bootstrap() -> None:
    """Bootstrap initial administrator and community configuration."""
    try:
        from app.services.user_service import bootstrap_first_admin

        await bootstrap_first_admin()
    except Exception as exc:
        logger.error("Initial admin bootstrap error: %s", exc)

    try:
        from app.services.community_bootstrap_service import import_bootstrap_config

        await import_bootstrap_config()
    except Exception as exc:
        logger.error("Community bootstrap import error: %s", exc)


async def register_tools_skills_and_mcp() -> None:
    """Load custom tools, active skills, and MCP server tools into ToolRegistry."""
    db = get_mongo_db()
    try:
        from core.tools.custom_tool import CustomToolDefinition, register_custom_tool

        async for doc in db.custom_tools.find():
            doc.pop("_id", None)
            await register_custom_tool(CustomToolDefinition(**doc))
    except Exception as exc:
        logger.error("Custom tools initialization failed: %s", exc)

    try:
        from core.tools import get_tool_registry
        from core.tools.external_skill_loader import load_external_skills_to_registry
        from core.tools.execution_logger import get_tool_execution_logger
        from app.routers.skills import _register_skill_to_registry

        async for doc in db.skills.find({"enabled": True}):
            await _register_skill_to_registry(doc)
        await load_external_skills_to_registry(db, get_tool_registry())
        get_tool_execution_logger().set_db(db)
    except Exception as exc:
        logger.error("Skill initialization failed: %s", exc)

    try:
        from app.pro.services.mcp_service import MCPService

        await MCPService(db).restore_enabled_servers()
    except Exception as exc:
        logger.error("MCP server restoration failed: %s", exc)


async def sync_prompts_and_runtime_settings() -> None:
    """Bridge config to env, seed system prompt templates, and start worker pool."""
    try:
        from app.core.config_bridge import bridge_config_to_env

        bridge_config_to_env()
    except Exception as exc:
        logger.warning("Config bridge warning: %s", exc)

    try:
        from app.services.system_prompt_seed_service import ensure_system_prompt_templates

        await ensure_system_prompt_templates()
    except Exception as exc:
        logger.error("System prompt seed failed: %s", exc)

    try:
        from app.services.config_provider import provider as config_provider

        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
    except Exception as exc:
        logger.warning("Dynamic settings warning: %s", exc)

    try:
        from app.services.workflow_registry import initialize_builtin_workflows

        initialize_builtin_workflows()
    except Exception as exc:
        logger.error("Workflow registry init failed: %s", exc)

    await print_config_summary(logger)

    try:
        from app.services.thread_worker import start_thread_worker

        max_workers = getattr(settings, "WORKER_MAX_CONCURRENT", 3)
        await asyncio.wait_for(start_thread_worker(max_workers=max_workers), timeout=20.0)
    except Exception as exc:
        logger.error("Thread worker startup error: %s", exc)

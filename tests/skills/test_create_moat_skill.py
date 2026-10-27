"""Test to create a moat strength quantitative score skill"""

import asyncio
import logging
import sys
import os

# Make sure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _wait_for_completion(db, session_id: str, timeout: int = 600):
    """Poll the database and wait for skill generation to complete (status changes to completed/failed)"""
    collection = db["skill_creation_sessions"]
    start = asyncio.get_event_loop().time()
    last_stage = ""
    last_progress = 0.0
    while True:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > timeout:
            logger.warning("⏰ Wait timeout (%ss), Exit polling", timeout)
            return None
        doc = await collection.find_one({"session_id": session_id})
        if not doc:
            logger.warning("Session document does not exist: %s", session_id)
            return None
        status = doc.get("status", "")
        stage = doc.get("pipeline_stage", "")
        message = doc.get("pipeline_message", "")
        progress = doc.get("pipeline_progress", 0.0)
        iteration = doc.get("pipeline_iteration", 0)
        if stage != last_stage or abs(progress - last_progress) > 0.01:
            logger.info(
                "⏳ status=%s stage=%s progress=%.0f%% iter=%s msg=%s",
                status, stage, progress * 100, iteration, message[:80],
            )
            last_stage = stage
            last_progress = progress
        if status in ("completed", "failed"):
            logger.info("✅ End of generation status=%s Time consuming=%.1fs", status, elapsed)
            return doc
        await asyncio.sleep(3)


async def main():
    # Initialize database
    from app.core.database import init_database, get_mongo_db
    await init_database()
    db = get_mongo_db()

    # Initialize LLM configuration
    from app.services.intelligent_assistant_service import (
        get_coding_llm_config,
        get_reasoning_llm_config,
    )
    from core.llm import UnifiedLLMClient

    reasoning_config = await get_reasoning_llm_config(db)
    reasoning_client = UnifiedLLMClient.from_config(reasoning_config) if reasoning_config else None

    coding_config = await get_coding_llm_config(db)
    coding_client = UnifiedLLMClient.from_config(coding_config) if coding_config else None

    logger.info("reasoning_client=%s, coding_client=%s", bool(reasoning_client), bool(coding_client))

    # Create SkillGenerationService
    from app.services.skill_generation_service import SkillGenerationService
    service = SkillGenerationService(
        db=db,
        reasoning_llm_client=reasoning_client,
        coding_llm_client=coding_client,
    )

    # Step 1: Start session
    description = (
        "Create a moat strength quantitative scoring tool (Integrated Moat Scorer).\n"
        "Function: From the dimensions of profitability sustainability (ROIC trend), profit margin stability, growth quality, cash flow trend, dividend history, etc.,"
        "Conduct a quantitative moat strength score (0-100 points) for A-share listed companies, and output the moat grade (wide/narrow/none) and key driving factors.\n"
        "Input: symbol (ticker symbol)\n"
        "Output: JSON, contains moat_score(0-100), moat_grade(wide/narrow/none), key_drivers(array), dimension_scores(object)\n"
        "Data source: Use the existing get_historical_financial_annual_series, get_margin_stability_metrics,"
        "get_growth_quality_metrics, get_financial_cashflow_quality_trend, dividend_history_reliability Data from other tools.\n"
        "Note: The scoring dimensions refer to the Morningstar moat methodology, but simplified into calculable quantitative indicators."
    )

    logger.info("=" * 60)
    logger.info("Step 1: Start a skill to create a session")
    logger.info("Requirement description: %s", description[:100])
    logger.info("=" * 60)

    result = await service.start_session(
        description=description,
        user_id="test_user",
    )

    session_id = result["session_id"]
    logger.info("session ID: %s", session_id)
    logger.info("AI news: %s", result["ai_message"])
    logger.info("clarity: %s", result["clarity_level"])
    logger.info("current round: %s/%s", result["current_round"], result["expected_rounds"])

    # Step 2: Respond to AI questions if multiple rounds of dialogue are required
    current_round = result["current_round"]
    expected_rounds = result["expected_rounds"]

    if current_round < expected_rounds and result.get("clarity_level") != "high":
        logger.info("=" * 60)
        logger.info("Step 2: Respond to AI clarification questions")
        logger.info("=" * 60)

        respond_result = await service.respond_to_session(
            session_id=session_id,
            user_message=(
                "The scoring dimensions are as follows:\n"
                "1. ROIC Sustainability (25 points): Is the ROIC sustainable in the past five years?>15%\n"
                "2. Profit rate stability (20 points): standard deviation of gross profit rate and net profit rate\n"
                "3. Revenue growth quality (20 points): Matching degree of revenue compound growth rate and cash flow growth\n"
                "4. Cash flow trends (15 points): Operating cash flow/net profit ratio trends\n"
                "5. Dividend continuity (10 points): number of dividends and dividend payout rate in the past five years\n"
                "6. Asset severity (10 points): Trend of total asset turnover rate\n"
                "Classification:>70=wide(wide), 40-70=narrow(narrow), <40=None(none)\n"
                "There is no need to output buying and selling recommendations, only quantitative scores and driving factors."
            ),
        )
        logger.info("AI Reply: %s", respond_result["ai_message"])
        logger.info("current round: %s/%s", respond_result["current_round"], respond_result["expected_rounds"])
        current_round = respond_result["current_round"]

    # Step 3: Confirm specs and trigger code generation (asynchronous)
    logger.info("=" * 60)
    logger.info("Step 3: Confirm specs and trigger code generation")
    logger.info("=" * 60)

    confirm_result = await service.confirm_spec(
        session_id=session_id,
        user_message="Confirm",
    )

    logger.info("Confirm result status: %s", confirm_result.get("status"))
    if confirm_result.get("spec"):
        spec = confirm_result["spec"]
        logger.info("Skill Name: %s", spec.get("name"))
        logger.info("Tool ID: %s", spec.get("tool_id"))
        logger.info("Description: %s", spec.get("description"))
        logger.info("parameters: %s", spec.get("parameters"))
    else:
        logger.error("Spec generation failed: %s", confirm_result.get("message"))
        return

    # confirm_spec It is asynchronous and returns status=generating, Need to poll and wait for completion
    logger.info("=" * 60)
    logger.info("Step 4: Wait for asynchronous code generation to complete (up to 10 minutes)")
    logger.info("=" * 60)

    final_doc = await _wait_for_completion(db, session_id, timeout=600)
    if not final_doc:
        logger.error("Generation timeout or session does not exist")
        return

    status = final_doc.get("status")
    pipeline_result = final_doc.get("pipeline_result") or {}

    logger.info("=" * 60)
    logger.info("Code generation results:")
    logger.info("  session state: %s", status)
    logger.info("  success: %s", pipeline_result.get("success"))
    logger.info("  total_rounds: %s", pipeline_result.get("total_rounds"))
    logger.info("  total_time: %s", pipeline_result.get("total_time"))
    logger.info("  error: %s", pipeline_result.get("error", "None"))
    if pipeline_result.get("final_metadata"):
        meta = pipeline_result["final_metadata"]
        logger.info("  generation_engine: %s", meta.get("generation_engine"))
        logger.info("  verified_facts: %s", len(meta.get("verified_facts") or []))
    logger.info("=" * 60)

    if status != "completed" or not pipeline_result.get("success"):
        logger.error("❌ Skill Build failed")
        # Print iteration history to aid diagnosis
        iterations = pipeline_result.get("iterations") or []
        for i, it in enumerate(iterations, 1):
            logger.info("  Iterate %d: decision=%s", i, it.get("decision"))
            if it.get("feedback"):
                logger.info("    feedback: %s", str(it.get("feedback"))[:200])
        return

    # Step 5: Generated by test skill
    logger.info("=" * 60)
    logger.info("Step 5: Test the generated skill (tested with 600519 Maotai)")
    logger.info("=" * 60)

    await asyncio.sleep(2)

    # Load from database skill
    tool_id = confirm_result["spec"].get("tool_id")
    skill_doc = await db["external_skills"].find_one({"tool_id": tool_id})
    if skill_doc:
        logger.info("Skill Saved to database: %s", skill_doc.get("tool_id"))
        logger.info("Status: %s", skill_doc.get("status"))
        logger.info("code length: %d character", len(skill_doc.get("code", "")))

        if skill_doc.get("status") == "active":
            from core.tools.external_skill_loader import register_single_external_skill
            from app.core.database import get_mongo_db_sync
            from core.tools.registry import get_tool_registry

            sync_db = get_mongo_db_sync()
            registry = get_tool_registry()
            register_single_external_skill(sync_db, registry, skill_doc)

            func = registry.get_function(tool_id)
            if func:
                logger.info("Skill Registered to ToolRegistry, start calling...")
                try:
                    result_str = func(symbol="600519")
                    logger.info("Call result: %s", str(result_str)[:800])
                except Exception as e:
                    logger.error("call failed: %s", e, exc_info=True)
            else:
                logger.error("Skill Not registered to ToolRegistry")
        else:
            logger.warning("Skill status is not active: %s, Skip calling test", skill_doc.get("status"))
    else:
        logger.error("Skill Not saved to database")

    logger.info("=" * 60)
    logger.info("Test completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

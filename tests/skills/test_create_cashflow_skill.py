"""
test generation"Cash flow quality analysis"skill
Validation vector search + reconnaissance + code generation + Tested complete link
"""
import asyncio
import time
import sys

async def main():
    from app.core.database import init_database, get_mongo_db
    from app.services.skill_generation_service import SkillGenerationService
    from app.services.intelligent_assistant_service import (
        get_coding_llm_config,
        get_reasoning_llm_config,
    )
    from core.llm import UnifiedLLMClient

    await init_database()
    db = get_mongo_db()

    # Configuration LLM
    reasoning_config = await get_reasoning_llm_config(db)
    coding_config = await get_coding_llm_config(db)
    reasoning_client = UnifiedLLMClient.from_config(reasoning_config) if reasoning_config else None
    coding_client = UnifiedLLMClient.from_config(coding_config) if coding_config else None

    svc = SkillGenerationService(
        db=db,
        reasoning_llm_client=reasoning_client,
        coding_llm_client=coding_client,
        provider="deepseek",
    )

    # ===== steps 1: Submit requirements =====
    print("=" * 60)
    print("steps 1: Submit requirements")
    print("=" * 60)
    description = (
        "Cash Flow Quality Analysis Tool: Assess the authenticity and sustainability of a company s cash flow."
        "Analyze operating net cash flow/net profit ratio (profit content), free cash flow trends,"
        "Indicators such as cash flow volatility and cash-to-cash ratio identify profit manipulation risks."
    )
    result = await svc.start_session(description=description, user_id="test")
    session_id = result.get("session_id")
    print(f"session_id: {session_id}")
    print(f"AI Reply: {result.get('ai_message', '')[:200]}...")

    # ===== steps 2: Additional details =====
    print("\n" + "=" * 60)
    print("steps 2: Additional details")
    print("=" * 60)
    detail = (
        "Dimensions to be analyzed:\n"
        "1. Profit content: net operating cash flow/net profit ratio (>1 For excellence,<0.5 as difference)\n"
        "2. Free cash flow trend: FCF trend and stability in the past 5 years\n"
        "3. Cash flow volatility: coefficient of variation of operating cash flow\n"
        "4. Cash-to-cash ratio: cash received from sales of goods/operating income\n"
        "5. Abnormal signals: positive net profit but negative operating cash flow, large capitalized expenditures, etc.\n"
        "Input parameters: stock code, analysis years (default 5 years)"
    )
    result2 = await svc.respond_to_session(session_id, detail)
    print(f"AI Reply: {result2.get('ai_message', '')[:200]}...")

    # ===== steps 3: Confirm specifications and trigger generation =====
    print("\n" + "=" * 60)
    print("steps 3: Confirm specifications and trigger generation")
    print("=" * 60)
    confirm_result = await svc.confirm_spec(session_id, "Confirm")
    print(f"status: {confirm_result.get('status')}")
    print(f"session_id: {confirm_result.get('session_id')}")

    # ===== steps 4: Polling for build completion =====
    print("\n" + "=" * 60)
    print("steps 4: Wait for the build to complete")
    print("=" * 60)
    max_wait = 900  # Wait up to 15 minutes (10 iterations may take longer)
    start_time = time.time()
    final_status = None
    while time.time() - start_time < max_wait:
        session = await svc.get_session(session_id)
        status = session.get("status")
        elapsed = int(time.time() - start_time)
        print(f"  [{elapsed}s] Status: {status}")
        if status in ("completed", "failed"):
            final_status = status
            break
        await asyncio.sleep(10)

    if final_status != "completed":
        print(f"\n❌ Build failed: status={final_status}")
        session = await svc.get_session(session_id)
        pipeline_result = session.get("pipeline_result") or {}
        print(f"Error: {pipeline_result.get('error', 'unknown')}")
        # Print failure summary for each round
        for r in pipeline_result.get("iterations", []):
            print(f"  rounds {r.get('round_number')}: decision={r.get('decision')}, feedback={r.get('feedback', '')[:150]}")
        return

    print(f"\n✅ Generation completed (Time consuming {int(time.time() - start_time)}s)")

    # ===== steps 5: View generated results =====
    print("\n" + "=" * 60)
    print("steps 5: View generated results")
    print("=" * 60)
    session = await svc.get_session(session_id)
    pipeline_result = session.get("pipeline_result") or {}
    print(f"success: {pipeline_result.get('success')}")
    print(f"total_rounds: {pipeline_result.get('total_rounds')}")
    total_time = pipeline_result.get('total_time') or 0
    print(f"total_time: {total_time:.1f}s")
    # final_score It does not exist at the top level of pipeline_result and needs to be obtained from iterations.
    iterations = pipeline_result.get("iterations") or []
    final_score = None
    if iterations:
        last_iter = iterations[-1]
        eval_score = last_iter.get("eval_score") or {}
        final_score = eval_score.get("total")
    print(f"final_score: {final_score}")

    # View spec
    spec = session.get("spec", {})
    tool_id = spec.get("tool_id")
    print(f"tool_id: {tool_id}")
    print(f"display_name: {spec.get('display_name')}")

    # View the generated skill code (external_skills is the actual storage collection)
    skill_doc = await db["external_skills"].find_one({"tool_id": tool_id})
    if skill_doc:
        code = skill_doc.get("code", "")
        print(f"Lines of code: {len(code.split(chr(10)))}")
        print(f"\n The first 30 lines of code:")
        for i, line in enumerate(code.split("\n")[:30], 1):
            print(f"  {i:3d} | {line}")

        # ===== steps 6: test skill =====
        print("\n" + "=" * 60)
        print("steps 6: Test skill (Kweichow Moutai 600519)")
        print("=" * 60)
        test_result = await svc.test_skill(tool_id, {"symbol": "600519"})
        print(f"success: {test_result.get('success')}")
        if test_result.get("success"):
            output = test_result.get("output")
            if output:
                import json
                try:
                    if isinstance(output, str):
                        output = json.loads(output)
                    print(f"Output (formatting):")
                    print(json.dumps(output, ensure_ascii=False, indent=2)[:2000])
                except Exception:
                    print(f"output(raw): {str(output)[:1500]}")
            print(f"\n Execution time: {test_result.get('execution_time')}s")
        else:
            print(f"Error: {test_result.get('error')}")
            print(f"stderr: {test_result.get('stderr', '')[:500]}")
    else:
        print(f"❌ Skill document not found (tool_id={tool_id})")

if __name__ == "__main__":
    asyncio.run(main())

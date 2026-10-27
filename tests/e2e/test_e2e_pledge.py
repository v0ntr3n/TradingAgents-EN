"""End-to-end testing: pledge skill generation process (agentic mode)"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.tools.external.skill_spec import (
    SkillSpec,
    SkillParameter,
    ExpectedOutput,
    ValidationCheck,
)
from core.tools.external.iteration_controller import IterationController


def build_pledge_spec() -> SkillSpec:
    return SkillSpec(
        tool_id="test_pledge_e2e",
        display_name="Stock Equity Pledge Trend and Risk Report",
        description=(
            "Obtain the historical trend of equity pledges for the specified stocks in the past three years, and support statistics by annual/quarterly/monthly frequency."
            "Automatically evaluate the trend direction of the pledge ratio; at the same time, it outputs the risk level and the top pledged shareholders based on the current risk snapshot."
            "For blue chip stocks that do not have pledge data, an empty trend sequence and a risk level of none are returned normally."
        ),
        category="fundamentals",
        data_source="local_db",
        parameters=[
            SkillParameter(name="symbol", param_type="string", description="6 A-share stock code, such as 000002", required=True),
            SkillParameter(name="freq", param_type="string", description="Statistical frequency, optional year, quarter, month, default year", required=False, default="year"),
        ],
        expected_output=ExpectedOutput(
            type="dict",
            fields=["symbol", "name", "historical_trend", "trend_assessment", "risk_level", "top_pledge_shareholders"],
        ),
        validation_checks=[
            ValidationCheck(check_type="output", name="status_success", description="Output status must be successful", blocking=True),
            ValidationCheck(check_type="data", name="required_field", field="symbol", description="symbol cannot be missing in the returned result", blocking=True),
            ValidationCheck(check_type="data", name="required_field", field="risk_level", description="The risk level field cannot be missing, at least return none", blocking=True),
        ],
        constraints=[
            "An empty trend or no-pledge conclusion must not be returned when pledge data actually exists.",
            "It must be obtained through the two helpers get_pledge_historical_series and get_pledge_risk_profile in series",
            "freq Parameters map directly to the period parameter (year/quarter/month) of the underlying helper",
            "When there is indeed no pledge data, historical_trend returns an empty list and risk_level returns none",
        ],
        test_input={"symbol": "000002", "freq": "year"},
    )


def main():
    print("=" * 60)
    print("End-to-end testing: pledge skill generation process (agentic mode)")
    print("=" * 60)

    spec = build_pledge_spec()
    print(f"\n📋 SkillSpec Build completed: tool_id={spec.tool_id}")
    print(f"   test input: {spec.test_input}")

    print("\n🔧 initialization IterationController (provider=deepseek)...")
    controller = IterationController(provider="deepseek", max_iterations=10)

    print("\n🚀 start run_agentic...")
    start_time = time.time()

    try:
        result = controller.run_agentic(spec)
        elapsed = time.time() - start_time
        print(f"\n✅ run_agentic completed, time consuming {elapsed:.1f}s")
        print(f"   success: {result.success}")
        print(f"   stages: {len(getattr(result, 'stages', result.iterations) if hasattr(result, 'iterations') else [])}")
        if hasattr(result, 'final_score'):
            print(f"   final_score: {result.final_score}")
        elif hasattr(result, 'quality_score'):
            print(f"   quality_score: {result.quality_score}")
        failure_summary = getattr(result, 'failure_summary', '') or ''
        print(f"   failure_summary: {failure_summary[:300] if failure_summary else '(None)'}")

        iterations = getattr(result, 'iterations', getattr(result, 'stages', []))
        for i, iteration in enumerate(iterations):
            print(f"\n--- No. {i+1} wheel ---")
            if hasattr(iteration, "eval_score") and iteration.eval_score:
                print(f"   Rating: total={iteration.eval_score.total:.2f} (exec={iteration.eval_score.executability} auth={iteration.eval_score.authenticity} compl={iteration.eval_score.completeness} rel={iteration.eval_score.relevance} fmt={iteration.eval_score.format_quality})")
            if hasattr(iteration, "reflection") and iteration.reflection:
                print(f"   root cause: {iteration.reflection.root_cause[:150]}")
                print(f"   should_retry: {iteration.reflection.should_retry}")
            if hasattr(iteration, "decision"):
                print(f"   decision making: {iteration.decision}")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ run_agentic Exception, time consuming {elapsed:.1f}s")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test completed. Please check logs/skill_workshop.log for troubleshooting details")
    print("=" * 60)


if __name__ == "__main__":
    main()

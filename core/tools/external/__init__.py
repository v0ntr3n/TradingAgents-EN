"""
External Skill Generation System

Provides a complete pipeline of Skill requirement analysis, code generation, verification, evaluation and iteration control.

How to use::

    from core.tools.external import RequirementAnalyzer, IterationController

    # 1. Requirements communication
    analyzer = RequirementAnalyzer(provider="deepseek")
    session = analyzer.create_session(user_id="u1")
    session, reply = analyzer.process_user_input(session, "I need to get individual stock news")

    # 2. After confirming the specifications, generate the code
    session, spec = analyzer.confirm_spec(session, "Confirm")

    # 3. iterative generation
    controller = IterationController(provider="deepseek")
    result = controller.run(spec)
"""

from importlib import import_module
from typing import Dict


_EXPORT_MAP: Dict[str, str] = {
    # data model
    "BoundaryCheck": ".skill_spec",
    "BusinessRuleFailure": ".skill_spec",
    "BusinessVerificationResult": ".skill_spec",
    "ClarityLevel": ".skill_spec",
    "ConversationRound": ".skill_spec",
    "EvalScore": ".skill_spec",
    "ExpectedOutput": ".skill_spec",
    "GeneratedCode": ".skill_spec",
    "ImplementationFact": ".skill_spec",
    "ImplementationFactReport": ".skill_spec",
    "ImplementationHelper": ".skill_spec",
    "ImplementationIssue": ".skill_spec",
    "IterationRound": ".skill_spec",
    "PipelineResult": ".skill_spec",
    "ReflectionResult": ".skill_spec",
    "SandboxResult": ".skill_spec",
    "SessionStatus": ".skill_spec",
    "SkillCreationSession": ".skill_spec",
    "SkillHandoffContext": ".skill_spec",
    "SkillParameter": ".skill_spec",
    "SkillSource": ".skill_spec",
    "SkillSpec": ".skill_spec",
    "SkillStatus": ".skill_spec",
    "TestCase": ".skill_spec",
    "ValidationResult": ".skill_spec",
    "ValidationCheck": ".skill_spec",
    # pipeline module
    "BusinessVerifier": ".business_verifier",
    "BusinessVerifierRegistry": ".business_verifier",
    "CodeGenerator": ".code_generator",
    "DefaultBusinessVerifier": ".business_verifier",
    "DefaultReconnaissanceController": ".reconnaissance_controller",
    "IterationController": ".iteration_controller",
    "OutputEvaluator": ".output_evaluator",
    "ReconnaissanceController": ".reconnaissance_controller",
    "RequirementAnalyzer": ".requirement_analyzer",
    "SandboxRunner": ".sandbox_runner",
    "StaticValidator": ".static_validator",
    "ValuationBusinessVerifier": ".business_verifier",
}


def __getattr__(name: str):
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(list(globals().keys()) + list(__all__))

__all__ = [
    # data model
    "BoundaryCheck",
    "BusinessRuleFailure",
    "BusinessVerificationResult",
    "ClarityLevel",
    "ConversationRound",
    "EvalScore",
    "ExpectedOutput",
    "GeneratedCode",
    "ImplementationFact",
    "ImplementationFactReport",
    "ImplementationHelper",
    "ImplementationIssue",
    "IterationRound",
    "PipelineResult",
    "ReflectionResult",
    "SandboxResult",
    "SessionStatus",
    "SkillCreationSession",
    "SkillHandoffContext",
    "SkillParameter",
    "SkillSource",
    "SkillSpec",
    "SkillStatus",
    "TestCase",
    "ValidationResult",
    "ValidationCheck",
    # pipeline module
    "BusinessVerifier",
    "BusinessVerifierRegistry",
    "CodeGenerator",
    "DefaultBusinessVerifier",
    "DefaultReconnaissanceController",
    "IterationController",
    "OutputEvaluator",
    "ReconnaissanceController",
    "RequirementAnalyzer",
    "SandboxRunner",
    "StaticValidator",
    "ValuationBusinessVerifier",
]

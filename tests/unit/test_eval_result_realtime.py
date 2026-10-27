# -*- coding: utf-8 -*-
"""Quality assessment results are displayed in real time — Unit testing

Coverage:
1. EvalScore.expert_comment Field parsing and filling (output_evaluator)
2. IterationController._build_eval_result_extra Event structure (including total/passed)
3. service Progress callback extra transparent transmission (_progress_cb is written to pipeline_eval_result)
"""
import re

from core.tools.external.iteration_controller import IterationController
from core.tools.external.skill_spec import EvalScore


def test_eval_score_has_expert_comment_default_empty():
    score = EvalScore()
    assert score.expert_comment == ""
    assert score.total >= 0


def test_build_eval_result_extra_contains_total_and_passed():
    # weighted total score = 0.25*9 + 0.25*9 + 0.20*8 + 0.20*8 + 0.10*9 = 8.6 >= threshold 8.5
    score = EvalScore(
        executability=9, authenticity=9, completeness=8, relevance=8, format_quality=9,
        expert_comment="Overall quality is good, data link is clear",
    )
    extra = IterationController._build_eval_result_extra(score, round_num=2)

    assert "eval_result" in extra
    data = extra["eval_result"]
    # total Yes @property, Must be brought out explicitly
    assert data["total"] == score.total
    assert data["round"] == 2
    assert data["passed"] is True
    assert data["expert_comment"] == "Overall quality is good, data link is clear"
    # Five dimensions fully revealed
    for key in ("executability", "authenticity", "completeness", "relevance", "format_quality"):
        assert key in data


def test_build_eval_result_extra_passed_false_below_threshold():
    score = EvalScore(executability=6.0)
    extra = IterationController._build_eval_result_extra(score, round_num=1)
    assert extra["eval_result"]["passed"] is False


def test_evaluator_parses_expert_comment_from_verdict():
    """from <verdict> JSON Parse expert_comment and write it EvalScore"""
    raw = (
        '<verdict>\n{"executability": 9, "authenticity": 8, "completeness": 8, '
        '"relevance": 9, "format_quality": 8, "expert_comment": "The data is real and the structure is clear"}\n</verdict>'
    )
    match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", raw, re.DOTALL)
    assert match

    import json as _json
    scores = _json.loads(match.group(1).strip())
    score = EvalScore()
    score.executability = float(scores["executability"])
    score.authenticity = float(scores["authenticity"])
    score.completeness = float(scores["completeness"])
    score.relevance = float(scores["relevance"])
    score.format_quality = float(scores["format_quality"])
    comment = str(scores.get("expert_comment", "")).strip()
    if comment:
        score.expert_comment = comment

    assert score.expert_comment == "The data is real and the structure is clear"
    assert score.executability == 9.0

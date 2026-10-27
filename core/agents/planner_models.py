"""
Planning and analyzing data models

Define all Pydantic models used in the Plan-then-Execute pattern:
- PlanStep: individual steps in the plan
- AnalysisPlan: Complete analysis plan
- StepResult: Step execution result
- SupplementRequest: Supplementary call request
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlanSource(str, Enum):
    """Plan source"""
    SEED_FLOW = "seed_flow"       # Level 1: Seed Process Matching
    LLM_PLAN = "llm_plan"         # Level 2: LLM independent planning
    REACT_FALLBACK = "react"      # Level 3: ReAct rollback


class PlanStep(BaseModel):
    """individual steps in the plan"""
    id: int = Field(..., description="Step number, starting from 1")
    tool: str = Field(..., description="Tool ID (must exist in ToolRegistry)")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool call parameters")
    intent: str = Field("", description="The intention description of this step helps the synthesis stage understand the semantics")
    depends_on: List[int] = Field(default_factory=list, description="A list of dependent step IDs. An empty list indicates that there are no dependencies and can be parallelized.")


class AnalysisPlan(BaseModel):
    """Complete analysis plan"""
    question: str = Field(..., description="Original user question")
    template_id: Optional[str] = Field(None, description="Seed process ID (not empty when matching at the first level, null at the second level)")
    source: PlanSource = Field(PlanSource.LLM_PLAN, description="Plan source")
    steps: List[PlanStep] = Field(default_factory=list, description="List of planning steps")

    @property
    def parallel_groups(self) -> List[List[PlanStep]]:
        """
        Grouped by dependencies, the same group can be executed in parallel.
        Returns an ordered list of step groups (topological sort).
        """
        if not self.steps:
            return []

        completed: set = set()
        groups: List[List[PlanStep]] = []
        remaining = list(self.steps)

        while remaining:
            # Find all dependent steps completed
            ready = [s for s in remaining if all(d in completed for d in s.depends_on)]
            if not ready:
                # There are circular dependencies, put all remaining steps into a set of serial executions
                groups.append(remaining)
                break
            groups.append(ready)
            for s in ready:
                completed.add(s.id)
                remaining.remove(s)

        return groups


class StepResult(BaseModel):
    """Step execution result"""
    step_id: int = Field(..., description="Corresponding steps ID")
    tool: str = Field(..., description="Tools for execution ID")
    intent: str = Field("", description="step intention")
    success: bool = Field(True, description="Whether the execution was successful")
    result: Any = Field(None, description="Tool returns results")
    error: Optional[str] = Field(None, description="Error message (on failure)")
    duration_ms: int = Field(0, description="Execution time (milliseconds)")


class SupplementRequest(BaseModel):
    """Supplementary call request (generated when LLM determines that there is insufficient data in the synthesis phase)"""
    reason: str = Field(..., description="Reasons for supplementation")
    steps: List[PlanStep] = Field(default_factory=list, description="Additional steps (max 2)")


class PlannedAnalysisResult(BaseModel):
    """Plan and analyze final results"""
    reply: str = Field(..., description="final answer")
    plan: Optional[AnalysisPlan] = Field(None, description="Executed analysis plan")
    tools_used: List[str] = Field(default_factory=list, description="List of tools used")
    step_results: List[StepResult] = Field(default_factory=list, description="Execution results of each step")
    source: PlanSource = Field(PlanSource.LLM_PLAN, description="Analytical sources actually used")
    supplemented: bool = Field(False, description="Whether a supplemental call was made")
    data_refs: Optional[List] = Field(None, description="Referenced data, reserved")


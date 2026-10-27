"""
Iterative Optimizer - implements OpenClaw-style policy iterative optimization
Perform backtesting → Assessment results → Optimization strategy → Backtest again → until satisfied
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from .engine_client import BacktestEngineClient
from .result_evaluator import (
    evaluate_backtest_result,
    optimize_strategy_based_on_evaluation,
    should_optimize_strategy,
)
from .dsl_evaluator import evaluate_strategy_python_full

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3  # Maximum number of iterations to avoid infinite loops


class IterationResult:
    """Single iteration result"""
    def __init__(
        self,
        iteration: int,
        strategy: Dict[str, Any],
        backtest_result: Dict[str, Any],
        evaluation: Dict[str, Any],
        optimization_applied: bool = False,
    ):
        self.iteration = iteration
        self.strategy = strategy
        self.backtest_result = backtest_result
        self.evaluation = evaluation
        self.optimization_applied = optimization_applied


class IterativeOptimizer:
    """iterative optimizer"""
    
    def __init__(self, engine_client: Optional[BacktestEngineClient] = None):
        self.engine_client = engine_client or BacktestEngineClient()
        self.iterations: List[IterationResult] = []
    
    async def optimize_strategy(
        self,
        user_description: str,
        initial_strategy: Dict[str, Any],
        max_iterations: int = MAX_ITERATIONS,
    ) -> Dict[str, Any]:
        """
        Iterate the optimization strategy until it is satisfied or reaches the maximum number of iterations
        
        Args:
            user_description: Description of original user needs
            initial_strategy: Initial strategy (code + config) 
            max_iterations: Maximum number of iterations
            
        Returns:
            {
                "final_strategy": {...},
                "final_result": {...},
                "final_evaluation": {...},
                "iterations": [...],
                "optimization_summary": "Summary of optimization process"
            }
        """
        self.iterations = []
        current_strategy = initial_strategy
        
        logger.info("Start iterative optimization, maximum number of iterations: %d", max_iterations)
        
        for iteration in range(1, max_iterations + 1):
            logger.info("=== Iteration %d ===", iteration)
            
            # 1. Perform backtesting
            logger.info("Perform backtesting...")
            backtest_result = await self._run_backtest(current_strategy)
            
            if not backtest_result.get("success"):
                error_msg = backtest_result.get("error", "Backtest execution failed")
                logger.error("Backtest failed: %s", error_msg)
                # If the first iteration fails, an error is returned directly.
                if iteration == 1:
                    return {
                        "final_strategy": current_strategy,
                        "final_result": backtest_result,
                        "final_evaluation": {"overall_score": 0, "is_satisfactory": False},
                        "iterations": [],
                        "optimization_summary": f"Initial strategy backtest failed: {error_msg}",
                        "error": error_msg
                    }
                # If it's not the first time, use the last result
                break
            
            # 2. Assessment results
            logger.info("Evaluate backtest results...")
            evaluation = await evaluate_backtest_result(
                user_description, current_strategy, backtest_result
            )
            
            # Record this iteration
            iteration_result = IterationResult(
                iteration=iteration,
                strategy=current_strategy,
                backtest_result=backtest_result,
                evaluation=evaluation,
                optimization_applied=False,
            )
            self.iterations.append(iteration_result)
            
            logger.info(
                "Assessment Complete - Score: %d/100, Satisfaction: %s, Optimization priority: %s",
                evaluation.get("overall_score", 0),
                "Satisfied" if evaluation.get("is_satisfactory") else "Not satisfied",
                evaluation.get("optimization_priority", "unknown")
            )
            
            # 3. Determine whether further optimization is needed
            if not should_optimize_strategy(evaluation):
                logger.info("The strategy has met the requirements and optimization has been stopped.")
                break
            
            if iteration >= max_iterations:
                logger.info("The maximum number of iterations is reached and optimization is stopped.")
                break
            
            # 4. Generate optimized version
            logger.info("Generate optimization strategy...")
            try:
                optimized_strategy = await optimize_strategy_based_on_evaluation(
                    user_description, current_strategy, evaluation, backtest_result
                )
                
                # 5. Verify the optimized strategy
                logger.info("Validate optimization strategy...")
                passed, errors = await evaluate_strategy_python_full(
                    optimized_strategy["code"], 
                    optimized_strategy["config"],
                    run_execution_check=True
                )
                
                if not passed:
                    logger.warning("Optimization strategy verification failed: %s", "; ".join(errors))
                    # If optimization fails, stop iteration
                    break
                
                current_strategy = optimized_strategy
                iteration_result.optimization_applied = True
                
                logger.info("Strategy optimization is completed and ready for the next iteration")
                
            except Exception as e:
                logger.exception("Strategy optimization failed: %s", e)
                break
        
        # generate final result
        final_iteration = self.iterations[-1] if self.iterations else None
        if not final_iteration:
            return {
                "final_strategy": initial_strategy,
                "final_result": {"success": False, "error": "No valid iteration result"},
                "final_evaluation": {"overall_score": 0, "is_satisfactory": False},
                "iterations": [],
                "optimization_summary": "Optimization process terminated abnormally",
                "error": "No valid iteration result"
            }
        
        optimization_summary = self._generate_optimization_summary()
        
        return {
            "final_strategy": final_iteration.strategy,
            "final_result": final_iteration.backtest_result,
            "final_evaluation": final_iteration.evaluation,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "score": it.evaluation.get("overall_score", 0),
                    "is_satisfactory": it.evaluation.get("is_satisfactory", False),
                    "optimization_applied": it.optimization_applied,
                    "summary": it.backtest_result.get("summary", {}),
                }
                for it in self.iterations
            ],
            "optimization_summary": optimization_summary,
        }
    
    async def _run_backtest(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Perform backtesting"""
        try:
            if "code" in strategy and "config" in strategy:
                # Python Strategy
                return await self.engine_client.run_python(
                    strategy["code"], strategy["config"]
                )
            else:
                # DSL Strategy
                return await self.engine_client.run(strategy)
        except Exception as e:
            logger.exception("Backtest execution exception")
            return {"success": False, "error": str(e)}
    
    def _generate_optimization_summary(self) -> str:
        """Generate optimization process summary"""
        if not self.iterations:
            return "No iteration record"
        
        first_score = self.iterations[0].evaluation.get("overall_score", 0)
        final_score = self.iterations[-1].evaluation.get("overall_score", 0)
        total_iterations = len(self.iterations)
        
        summary = f"passed {total_iterations} rounds of iterative optimization,"
        summary += f"Strategy score from {first_score} promoted to {final_score}. "
        
        if final_score >= 70:
            summary += "The strategy has reached a satisfactory level."
        else:
            summary += "There is still room for improvement in the strategy, and further manual adjustments are recommended."
        
        return summary

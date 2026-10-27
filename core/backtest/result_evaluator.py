"""
Backtest results evaluator
Analyze whether the backtest results meet user expectations, identify problems and make optimization suggestions
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

EVALUATE_SYSTEM = """You are a professional quantitative strategy evaluator. Your task is to analyze the backtest results, determine whether the strategy meets the original needs of users, identify problems and make optimization suggestions.

 [Evaluation Dimensions]
1. **Demand matching**: Whether the strategy logic conforms to the investment ideas described by the user
2. **Reasonableness of results**: Are indicators such as income, winning rate, retracement, etc. within a reasonable range?
3. **trading behavior**: Whether the timing of buying and selling and the distribution of positions are in line with expectations
4. **Data quality**: Are there any issues such as missing data, outliers, etc.
5. **Code logic**: Are there any obvious flaws in the implementation of the strategy?

 [Output format]
Please output the evaluation results in the following JSON format:
{
  "overall_score": 85,  // Overall rating 0-100
  "is_satisfactory": true,  // Are you satisfied (>= 70 Divided into satisfied)
  "issues": [
    {
      "type": "logic_error",  // Question type:logic_error/data_issue/performance_poor/requirement_mismatch
      "severity": "high",     // Severity:high/medium/low
      "description": "Specific problem description",
      "suggestion": "Optimization suggestions"
    }
  ],
  "strengths": ["Strategic advantages 1", "Strategic advantages 2"],
  "optimization_priority": "high",  // Optimization priority:high/medium/low/none
  "next_steps": "Specific suggestions for next-step optimization directions"
}

 [Evaluation criteria]
- Overall score: Comprehensive consideration of demand matching, rationality of results, transaction behavior, etc.
- Satisfaction threshold:>= 70 I think I am basically satisfied.< 70 Needs optimization
- Problem severity:
  * high: Seriously affects the effectiveness of the strategy and must be repaired
  * medium: Affects strategy performance, it is recommended to fix it  
  * low: Minor issue, optional fix

 [Frequently Asked Question Types]
- logic_error: Strategy logic errors (such as wrong buying and selling conditions, position management problems)
- data_issue: Data problems (such as empty stock pool, missing data)
- performance_poor: Poor performance (such as too low returns, too large drawdowns)
- requirement_mismatch: Not in line with user needs (such as expecting high dividends but choosing growth stocks)
"""

OPTIMIZE_SYSTEM = """You are a strategy optimization expert. Conduct targeted optimization of existing strategies based on the backtest result evaluation report.

 [Optimization principles]
1. **Targeted fixes**: Focus on addressing high-priority issues identified in the assessment report
2. **Keep core logic**: Optimize within the framework of users original needs without changing the basic investment ideas
3. **incremental improvements**: Only solve 1-2 major problems at a time to avoid major revisions
4. **data driven**: Optimize based on backtest data and transaction details

 [Important: Avoid Survivor Bias]
⚠️ Don t use current leading stocks to backtest the past 10-20 years! This can lead to serious survivor bias.

**Correct approach (priority from high to low)**: 

1. **🆕 Use industry classification + Historical market capitalization**: universe.type = "industry"
   - The system will automatically obtain the stock with the largest market capitalization in the industry on the start date of the backtest
   - For example, to backtest the liquor strategy from 2010 to 2020, the liquor faucet from 2010 will be used.
   - This is the best choice and can truly avoid survivor bias

2. **Use industry indices**: universe.type = "index"
   - Use index historical constituent stocks (some index historical data are limited)

3. **Shorten the backtest cycle**: Static stock pool is only used for backtesting in the past 3-5 years

 [Industry classification configuration]⭐ Recommended
Supported industries: liquor, food, home appliances, consumption, banking, insurance, securities firms, finance, semiconductors, software, technology, photovoltaics, lithium batteries, new energy, medicine, etc.

Example:
"universe": {"type": "industry", "industry": "Liquor", "max_symbols": 10}
"universe": {"type": "industry", "industry": "consumption", "max_symbols": 15}
"universe": {"type": "industry", "industry": "Finance", "max_symbols": 12}

 [Industry index code reference] (optional)
- Consumer category: 000932.SH (CSI Consumer), 399997.SZ (CSI Liquor)
- Financial: 399986.SZ (China Securities Bank), 000914.SH (300 Finance)
- Technology: 000993.SH (full index), 399006.SZ (GEM index)

 [Static stock pool configuration] (only recommended for backtesting in the past 3-5 years, long-term backtesting is not recommended)
Consumer category: 600519, 000858, 000568, 603288, 000651, 000333,600887

 [Output format]
Pure JSON must be output, in the following format:
{
  "code": "Optimized complete Python code string",
  "config": {
    "start_year": 2016,
    "end_year": 2025,
    "initial_capital": 1000000,
    "max_positions": 10,
    "benchmark": "000300",
    "market": "CN",
    "data_source": "tushare",
    "universe": {"type": "static", "symbols": ["600519", "000858", "000568", "002304", "000596", "603288", "000651", "000333", "600887", "601888"]}
  },
  "optimization_summary": "Description of the main improvements in this optimization"
}

 [Optimization strategy]
- Logic error: Correct buying and selling conditions, position management logic
- Data issues: Adjust the stock pool (increase the number of stocks, select more appropriate targets)
- Performance issues: optimize parameters and adjust position management
- Inconsistent needs: re-understand user intentions and adjust strategic direction
- Insufficient number of transactions: expand stock pool, relax entry conditions, shorten position holding period

 [Technical requirements]
- code Only import backtrader (as bt)
- datetime, date, timedelta Already injected and can be used directly
- Must output pure JSON, do not wrap markdown code blocks
- config Must contain complete configuration parameters
- Stock pool symbols are recommended to contain 8-15 stocks to ensure sufficient trading opportunities
"""


async def evaluate_backtest_result(
    user_description: str,
    strategy: Dict[str, Any],
    backtest_result: Dict[str, Any],
    llm_client: Optional[UnifiedLLMClient] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether the backtest results meet user expectations
    
    Args:
        user_description: Description of original user needs
        strategy: policy definition (code + config) 
        backtest_result: Backtest results (summary + trades etc.)
        llm_client: LLM client
        
    Returns:
        Assessment results JSON
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config
        
        cfg = await get_coding_llm_config()
        if not cfg:
            raise ValueError("LLM is not configured and result evaluation is not possible")
        client = UnifiedLLMClient.from_config(cfg)
    
    # Build an evaluation context
    context = _build_evaluation_context(user_description, strategy, backtest_result)
    
    messages = [
        Message(role=MessageRole.SYSTEM, content=EVALUATE_SYSTEM),
        Message(role=MessageRole.USER, content=context),
    ]
    
    try:
        response = await client.achat(messages)
        result_text = (response.content or "").strip()
        
        # Parse JSON results
        import json
        evaluation = json.loads(result_text)
        
        # Validate required fields
        required_fields = ["overall_score", "is_satisfactory", "issues", "optimization_priority"]
        for field in required_fields:
            if field not in evaluation:
                raise ValueError(f"Assessment results are missing required fields: {field}")
                
        return evaluation
        
    except json.JSONDecodeError as e:
        logger.warning("Evaluation result JSON parsing failed: %s", e)
        # Returns the default evaluation result
        return {
            "overall_score": 50,
            "is_satisfactory": False,
            "issues": [{"type": "logic_error", "severity": "high", 
                       "description": "Error in evaluation process", "suggestion": "Please check the policy logic"}],
            "optimization_priority": "high",
            "next_steps": "Requires manual inspection of policy implementation"
        }
    except Exception as e:
        logger.exception("Backtest result evaluation failed")
        raise ValueError(f"Evaluation failed: {e}")


def _build_evaluation_context(
    user_description: str,
    strategy: Dict[str, Any],
    backtest_result: Dict[str, Any]
) -> str:
    """Build an evaluation context"""

    # debug log
    logger.info(
        "[_build_evaluation_context] received backtest_result keys=%s",
        list(backtest_result.keys()) if backtest_result else "None"
    )

    # Extract key information
    # Two data structures are supported:1) direct summary 2) Nested under result
    if "summary" in backtest_result:
        summary = backtest_result.get("summary", {})
    else:
        summary = backtest_result  # Directly summary

    logger.info(
        "[_build_evaluation_context] summary: total_return=%s, win_rate=%s, trade_count=%s, final_value=%s",
        summary.get("total_return"),
        summary.get("win_rate"),
        summary.get("trade_count"),
        summary.get("final_value"),
    )

    # Extract run logs and warnings
    logs = backtest_result.get("logs", [])
    warnings = backtest_result.get("warnings", [])
    trades = backtest_result.get("trades", [])
    
    # Formatted backtest results summary
    result_summary = f"""
 [Summary of backtest results]
- total revenue: {summary.get('total_return', 0):.1f}%
- winning rate: {summary.get('win_rate', 0):.1f}%
- maximum drawdown: {summary.get('max_drawdown_pct', 0):.1f}%
- Number of transactions: {summary.get('trade_count', 0)}
- final value: {summary.get('final_value', 0):,.0f}
"""
    
    # Summary of transaction details (take the first 5 transactions)
    trade_summary = ""
    if trades:
        trade_summary = "\n [Transaction details sample]\n"
        for i, trade in enumerate(trades[:5]):
            trade_summary += f"- transaction{i+1}: {trade.get('symbol', 'N/A')} "
            trade_summary += f"{trade.get('entry_date', 'N/A')} -> {trade.get('exit_date', 'N/A')} "
            trade_summary += f"income: {trade.get('return_pct', 0):.1f}%\n"

    # Running logs and warning messages (important! Help identify the source of the problem)
    logs_section = ""
    if logs:
        logs_section = "\n [Backtest running log]\n"
        for log in logs:
            logs_section += f"- {log}\n"

    warnings_section = ""
    if warnings:
        warnings_section = "\n [⚠️ System warning (focus)]\n"
        for warn in warnings:
            warnings_section += f"- {warn}\n"

    # Strategy code summary (intercept key parts)
    code = strategy.get("code", "")
    code_summary = code[:500] + "..." if len(code) > 500 else code

    context = f"""
 [User original needs]
{user_description}

 [Strategy implementation]
```python
{code_summary}
```

 [Policy configuration]
{strategy.get('config', {})}

{result_summary}
{trade_summary}
{logs_section}
{warnings_section}

Based on the above information, please evaluate whether the strategy meets user needs, identify existing problems, and give optimization suggestions.
Pay special attention to the [System Warnings] section, these are potential problems automatically detected by the backtesting engine.
"""
    
    return context


async def optimize_strategy_based_on_evaluation(
    user_description: str,
    current_strategy: Dict[str, Any],
    evaluation_result: Dict[str, Any],
    backtest_result: Dict[str, Any],
    llm_client: Optional[UnifiedLLMClient] = None,
) -> Dict[str, Any]:
    """
    Optimize strategies based on evaluation results

    Args:
        user_description: User original needs
        current_strategy: current strategy (code + config) 
        evaluation_result: Assessment results
        backtest_result: Backtest results
        llm_client: LLM client

    Returns:
        Optimized strategy (code + config + optimization_summary) 
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config

        cfg = await get_coding_llm_config()
        if not cfg:
            raise ValueError("LLM is not configured and policy optimization cannot be performed")
        client = UnifiedLLMClient.from_config(cfg)

    # Build optimization context
    context = _build_optimization_context(
        user_description, current_strategy, evaluation_result, backtest_result
    )

    messages = [
        Message(role=MessageRole.SYSTEM, content=OPTIMIZE_SYSTEM),
        Message(role=MessageRole.USER, content=context),
    ]

    try:
        response = await client.achat(messages)
        result_text = (response.content or "").strip()

        # Parse JSON results
        import json
        optimized = json.loads(result_text)

        # Validate required fields
        required_fields = ["code", "config"]
        for field in required_fields:
            if field not in optimized:
                raise ValueError(f"Optimization results are missing required fields: {field}")

        return optimized

    except json.JSONDecodeError as e:
        logger.warning("Optimization result JSON parsing failed: %s", e)
        raise ValueError(f"Optimization result format error: {e}")
    except Exception as e:
        logger.exception("Strategy optimization failed")
        raise ValueError(f"Optimization failed: {e}")


def _build_optimization_context(
    user_description: str,
    current_strategy: Dict[str, Any],
    evaluation_result: Dict[str, Any],
    backtest_result: Dict[str, Any]
) -> str:
    """Build optimization context"""

    # Extract issues from assessment results
    issues = evaluation_result.get("issues", [])
    high_priority_issues = [issue for issue in issues if issue.get("severity") == "high"]

    issues_summary = ""
    if high_priority_issues:
        issues_summary = "\n [Issues that need to be resolved with priority]\n"
        for i, issue in enumerate(high_priority_issues):
            issues_summary += f"{i+1}. {issue.get('description', '')}\n"
            issues_summary += f"   Suggestions: {issue.get('suggestion', '')}\n"

    # Key indicators of backtest results
    summary = backtest_result.get("summary", {}) if "summary" in backtest_result else backtest_result
    performance_summary = f"""
 [Current performance]
- total revenue: {summary.get('total_return', 0):.1f}%
- winning rate: {summary.get('win_rate', 0):.1f}%
- maximum drawdown: {summary.get('max_drawdown_pct', 0):.1f}%
- Number of transactions: {summary.get('trade_count', 0)}
"""

    # Extract system warnings (important problem diagnostic information)
    warnings = backtest_result.get("warnings", [])
    warnings_section = ""
    if warnings:
        warnings_section = "\n [⚠️ Backtest engine warning (focus)]\n"
        for warn in warnings:
            warnings_section += f"- {warn}\n"

    context = f"""
 [User original needs]
{user_description}

 [Current strategy code]
```python
{current_strategy.get('code', '')}
```

 [Current policy configuration]
{current_strategy.get('config', {})}

{performance_summary}
{warnings_section}

 [Evaluation results]
- Overall rating: {evaluation_result.get('overall_score', 0)}/100
- Are you satisfied?: {'Yes' if evaluation_result.get('is_satisfactory') else 'No'}
- Optimization priority: {evaluation_result.get('optimization_priority', 'medium')}

{issues_summary}

 [Optimization goal]
{evaluation_result.get('next_steps', 'Improve strategy performance')}

Based on the above analysis, please optimize the strategy in a targeted manner, focusing on solving high-priority issues and system warnings.
"""

    return context


def should_optimize_strategy(evaluation_result: Dict[str, Any]) -> bool:
    """
    Determine whether an optimization strategy is needed

    Args:
        evaluation_result: Assessment results

    Returns:
        Does it need to be optimized?
    """
    # Optimization is required when the score is lower than 70 or there are high-priority issues
    score = evaluation_result.get("overall_score", 0)
    is_satisfactory = evaluation_result.get("is_satisfactory", False)
    optimization_priority = evaluation_result.get("optimization_priority", "none")

    return (
        score < 70 or
        not is_satisfactory or
        optimization_priority in ["high", "medium"]
    )

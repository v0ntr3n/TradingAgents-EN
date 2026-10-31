import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
from tradingagents.agents.utils.agent_states import AgentState

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


def compute_shannon_entropy(p: Sequence[float]) -> float:
    """Compute base-2 Shannon entropy for a discrete probability vector.

    H_2(P) = -sum(p * log2(p)) for p > 0.
    """
    return -sum(x * math.log2(x) for x in p if x > 0.0)


def compute_jensen_shannon_divergence(
    posteriors: Any,
    weights: Optional[Any] = None,
) -> float:
    """Compute base-2 Jensen-Shannon Divergence across N discrete distributions or analyst posteriors.

    Formula:
        M = sum(w_i * P_i) where sum(w_i) = 1.0
        D_JS = H_2(M) - sum(w_i * H_2(P_i))

    Guaranteed properties:
    - 0.0 <= D_JS <= 1.0 (base-2)
    - Returns 0.0 for identical distributions/posteriors, empty input, or N <= 1
    - Returns 1.0 for orthogonal distributions under uniform weights
    - Pure Python, zero external dependencies

    Args:
        posteriors: Either:
            - Dict mapping analyst_id to posterior dict (with p_optimistic, etc.) or prob vector
            - List of probability vectors (List[List[float]])
            - List of posterior dicts
        weights: Optional dict or sequence mapping items to weights. If None, uniform weights apply.

    Returns:
        float: Base-2 JSD in [0.0, 1.0].
    """
    if not posteriors:
        return 0.0

    parsed_posteriors: List[Tuple[Any, List[float]]] = []

    if isinstance(posteriors, dict):
        items = list(posteriors.items())
    elif isinstance(posteriors, (list, tuple)):
        items = list(enumerate(posteriors))
    else:
        return 0.0

    for aid, post in items:
        if isinstance(post, dict):
            try:
                p_opt = max(0.0, float(post.get("p_optimistic", 0.3333)))
                p_neu = max(0.0, float(post.get("p_neutral", 0.3334)))
                p_cau = max(0.0, float(post.get("p_cautious", 0.3333)))
            except (ValueError, TypeError):
                p_opt, p_neu, p_cau = 0.3333, 0.3334, 0.3333
            tot = p_opt + p_neu + p_cau
            dist = [p_opt / tot, p_neu / tot, p_cau / tot] if tot > 0 else [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
            parsed_posteriors.append((aid, dist))
        elif isinstance(post, (list, tuple)):
            try:
                p_vals = [max(0.0, float(x)) for x in post]
                tot = sum(p_vals)
                k = len(p_vals) if len(p_vals) > 0 else 3
                dist = [x / tot for x in p_vals] if tot > 0 else [1.0 / k] * k
            except (ValueError, TypeError):
                dist = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
            parsed_posteriors.append((aid, dist))

    n = len(parsed_posteriors)
    if n <= 1:
        return 0.0

    k_len = len(parsed_posteriors[0][1])
    for _, dist in parsed_posteriors:
        if len(dist) != k_len:
            raise ValueError(f"Inconsistent distribution dimensions: expected {k_len}, got {len(dist)}")

    raw_weights: List[float] = []
    if weights and isinstance(weights, dict):
        for aid, _ in parsed_posteriors:
            try:
                w_val = max(0.0, float(weights.get(aid, weights.get(str(aid), 1.0))))
            except (ValueError, TypeError):
                w_val = 1.0
            raw_weights.append(w_val)
    elif weights and isinstance(weights, (list, tuple)):
        for idx, _ in enumerate(parsed_posteriors):
            if idx < len(weights):
                try:
                    w_val = max(0.0, float(weights[idx]))
                except (ValueError, TypeError):
                    w_val = 1.0
            else:
                w_val = 1.0
            raw_weights.append(w_val)
    else:
        raw_weights = [1.0] * n

    total_w = sum(raw_weights)
    if total_w > 0:
        norm_weights = [w / total_w for w in raw_weights]
    else:
        norm_weights = [1.0 / n] * n

    mixture = [
        sum(w * dist[k] for (_, dist), w in zip(parsed_posteriors, norm_weights))
        for k in range(k_len)
    ]

    h_m = compute_shannon_entropy(mixture)
    avg_h = sum(
        w * compute_shannon_entropy(dist)
        for (_, dist), w in zip(parsed_posteriors, norm_weights)
    )
    return max(0.0, min(1.0, h_m - avg_h))


def compute_base2_jsd(distributions: List[List[float]]) -> float:
    """Compute base-2 Jensen-Shannon Divergence across N discrete distributions.

    Formula:
        M = (1/N) * sum(P_i)
        JSD = H_2(M) - (1/N) * sum(H_2(P_i))

    Guaranteed properties:
    - 0 <= JSD <= 1 (base-2)
    - Returns 0.0 for identical distributions or N <= 1
    - Pure Python, zero external dependencies
    """
    return compute_jensen_shannon_divergence(distributions)


def calculate_base2_jsd(
    posteriors: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Compute base-2 JSD from analyst posteriors dictionary."""
    return compute_jensen_shannon_divergence(posteriors, weights=weights)


def compute_cbs_bps(
    posteriors_or_jsd: Any,
    weights_or_move: Any = None,
    estimated_spread_bps: float = 15.0,
) -> float:
    """Calculate Coordination Breakeven Spread (CBS) in basis points.

    Formula:
        CBS_bps = (D_JS * weighted_expected_move_bps) / 2.0

    Supports both:
        - compute_cbs_bps(posteriors, weights=None, estimated_spread_bps=15.0)
        - compute_cbs_bps(jsd: float, move_bps: float)
    """
    if isinstance(posteriors_or_jsd, (int, float)):
        jsd = max(0.0, float(posteriors_or_jsd))
        try:
            move = abs(float(weights_or_move if weights_or_move is not None else 0.0))
        except (ValueError, TypeError):
            move = 0.0
        return (jsd * move) / 2.0

    posteriors = posteriors_or_jsd
    weights = weights_or_move

    if not posteriors or not isinstance(posteriors, (dict, list, tuple)):
        return 0.0

    jsd = compute_jensen_shannon_divergence(
        posteriors,
        weights=weights if isinstance(weights, (dict, list, tuple)) else None
    )
    if jsd <= 0.0:
        return 0.0

    moves: List[float] = []
    w_list: List[float] = []

    items = posteriors.items() if isinstance(posteriors, dict) else enumerate(posteriors)
    for aid, post in items:
        if isinstance(post, dict):
            try:
                raw_move = post.get("expected_move_bps", 0.0)
                move = abs(float(raw_move if raw_move is not None else 0.0))
            except (ValueError, TypeError):
                move = 0.0

            if weights and isinstance(weights, dict):
                try:
                    w = max(0.0, float(weights.get(aid, weights.get(str(aid), 1.0))))
                except (ValueError, TypeError):
                    w = 1.0
            else:
                try:
                    raw_conf = post.get("confidence", 0.5)
                    w = max(0.01, float(raw_conf if raw_conf is not None else 0.5))
                except (ValueError, TypeError):
                    w = 0.5

            moves.append(move)
            w_list.append(w)

    tot_w = sum(w_list)
    if tot_w > 0:
        weighted_move = sum(m * w for m, w in zip(moves, w_list)) / tot_w
    else:
        weighted_move = sum(moves) / len(moves) if moves else 0.0

    return (jsd * weighted_move) / 2.0


def calculate_cbs_routing(
    posteriors: Dict[str, Any],
    estimated_spread_bps: float = 15.0,
    max_debate_rounds: int = 3,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Calculate Coordination Breakeven Spread (CBS) and determine debate routing.

    Formula:
        CBS_bps = (JSD * weighted_expected_move_bps) / 2.0
    Gating:
        JSD < 0.12 or CBS_bps <= estimated_spread_bps -> fast_path
        JSD >= 0.12 and CBS_bps > estimated_spread_bps -> multi_round_debate
    """
    jsd = compute_jensen_shannon_divergence(posteriors, weights=weights)

    moves: List[float] = []
    w_list: List[float] = []
    if posteriors and isinstance(posteriors, dict):
        for aid, post in posteriors.items():
            if isinstance(post, dict):
                try:
                    raw_move = post.get("expected_move_bps", 0.0)
                    move = abs(float(raw_move if raw_move is not None else 0.0))
                except (ValueError, TypeError):
                    move = 0.0
                if weights and isinstance(weights, dict):
                    try:
                        w = max(0.0, float(weights.get(aid, weights.get(str(aid), 1.0))))
                    except (ValueError, TypeError):
                        w = 1.0
                else:
                    try:
                        raw_conf = post.get("confidence", 0.5)
                        w = max(0.01, float(raw_conf if raw_conf is not None else 0.5))
                    except (ValueError, TypeError):
                        w = 0.5
                moves.append(move)
                w_list.append(w)

    tot_w = sum(w_list)
    if tot_w > 0:
        weighted_move = sum(m * w for m, w in zip(moves, w_list)) / tot_w
    else:
        weighted_move = sum(moves) / len(moves) if moves else 0.0

    expected_debate_gain_bps = jsd * weighted_move
    cbs_bps = expected_debate_gain_bps / 2.0

    if jsd < 0.12 or cbs_bps <= estimated_spread_bps:
        route = "fast_path"
        dynamic_rounds = 0
    else:
        route = "multi_round_debate"
        # Dynamic rounds scaled 1 to max_debate_rounds
        scaling = (jsd - 0.12) / (1.0 - 0.12)
        scaled_rounds = 1 + (max_debate_rounds - 1) * scaling
        dynamic_rounds = int(max(1, min(max_debate_rounds, round(scaled_rounds))))

    return {
        "route": route,
        "jsd": jsd,
        "weighted_expected_move_bps": weighted_move,
        "expected_debate_gain_bps": expected_debate_gain_bps,
        "cbs_bps": cbs_bps,
        "estimated_spread_bps": estimated_spread_bps,
        "dynamic_debate_rounds": dynamic_rounds,
        "is_fast_path": (route == "fast_path"),
    }


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.dynamic_debate_rounds = max_debate_rounds

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        last_message = messages[-1]

        # Infinite loop repair: Add tool call count check
        tool_call_count = state.get("market_tool_call_count", 0)
        max_tool_calls = 3

        # Check if there is already a market analysis report
        market_report = state.get("market_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_market")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(market_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")
        logger.info(f"🔀 [Conditional judgment] - last message type: {type(last_message).__name__}")
        logger.info(f"🔀 [Conditional judgment] - Is there tool_calls: {hasattr(last_message, 'tool_calls')}")
        if hasattr(last_message, 'tool_calls'):
            logger.info(f"🔀 [Conditional judgment] - tool_calls Quantity: {len(last_message.tool_calls) if last_message.tool_calls else 0}")
            if last_message.tool_calls:
                for i, tc in enumerate(last_message.tool_calls):
                    logger.info(f"🔀 [Conditional judgment] - tool_call[{i}]: {tc.get('name', 'unknown')}")

        # Infinite loop repair: If the maximum number of tool calls is reached, force the end
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [Infinite loop repair] The maximum number of tool calls is reached and it is forced to end.: Msg Clear Market")
            return "Msg Clear Market"

        # If there is already report content, it means that the analysis has been completed and there will be no more loops.
        if market_report and len(market_report) > 100:
            logger.info(f"🔀 [Conditional judgment] ✅ Report completed, return: Msg Clear Market")
            return "Msg Clear Market"

        # Only AIMessage has tool_calls attribute
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔀 [Conditional judgment] 🔧 tool_calls detected, return: tools_market")
            return "tools_market"

        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear Market")
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        last_message = messages[-1]

        # Infinite loop repair: Add tool call count check
        tool_call_count = state.get("sentiment_tool_call_count", 0)
        max_tool_calls = 3

        # Check if there is already a sentiment analysis report
        sentiment_report = state.get("sentiment_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_social")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(sentiment_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")

        # Infinite loop repair: If the maximum number of tool calls is reached, force the end
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [Infinite loop repair] The maximum number of tool calls is reached and it is forced to end.: Msg Clear Social")
            return "Msg Clear Social"

        # If there is already report content, it means that the analysis has been completed and there will be no more loops.
        if sentiment_report and len(sentiment_report) > 100:
            logger.info(f"🔀 [Conditional judgment] ✅ Report completed, return: Msg Clear Social")
            return "Msg Clear Social"

        # Only AIMessage has tool_calls attribute
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔀 [Conditional judgment] 🔧 tool_calls detected, return: tools_social")
            return "tools_social"

        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear Social")
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        last_message = messages[-1]

        # Infinite loop repair: Add tool call count check
        tool_call_count = state.get("news_tool_call_count", 0)
        max_tool_calls = 3

        # Check if there is already a news analysis report
        news_report = state.get("news_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_news")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(news_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")

        # Infinite loop repair: If the maximum number of tool calls is reached, force the end
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [Infinite loop repair] The maximum number of tool calls is reached and it is forced to end.: Msg Clear News")
            return "Msg Clear News"

        # If there is already report content, it means that the analysis has been completed and there will be no more loops.
        if news_report and len(news_report) > 100:
            logger.info(f"🔀 [Conditional judgment] ✅ Report completed, return: Msg Clear News")
            return "Msg Clear News"

        # Only AIMessage has tool_calls attribute
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔀 [Conditional judgment] 🔧 tool_calls detected, return: tools_news")
            return "tools_news"

        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear News")
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine whether fundamental analysis should continue"""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        last_message = messages[-1]

        # Infinite loop repair: Add tool call count check
        tool_call_count = state.get("fundamentals_tool_call_count", 0)
        max_tool_calls = 1  # Get all data in one tool call

        # Check if there is already a fundamental report
        fundamentals_report = state.get("fundamentals_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_fundamentals")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(fundamentals_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")
        logger.info(f"🔀 [Conditional judgment] - last message type: {type(last_message).__name__}")
        
        # 🔍 [debug log] Print the details of the last message
        logger.info(f"🤖 [Conditional judgment] Details of the last message:")
        logger.info(f"🤖 [Conditional judgment] - Message type: {type(last_message).__name__}")
        if hasattr(last_message, 'content'):
            content_preview = last_message.content[:300] + "..." if len(last_message.content) > 300 else last_message.content
            logger.info(f"🤖 [Conditional judgment] - Content preview: {content_preview}")
        
        # 🔍 [debug log] Print details of tool_calls
        logger.info(f"🔀 [Conditional judgment] - Is there tool_calls: {hasattr(last_message, 'tool_calls')}")
        if hasattr(last_message, 'tool_calls'):
            logger.info(f"🔀 [Conditional judgment] - tool_calls Quantity: {len(last_message.tool_calls) if last_message.tool_calls else 0}")
            if last_message.tool_calls:
                logger.info(f"🔧 [Conditional judgment] detected {len(last_message.tool_calls)} tool calls:")
                for i, tc in enumerate(last_message.tool_calls):
                    logger.info(f"🔧 [Conditional judgment] - Tool call {i+1}: {tc.get('name', 'unknown')} (ID: {tc.get('id', 'unknown')})")
                    if 'args' in tc:
                        logger.info(f"🔧 [Conditional judgment] - parameters: {tc['args']}")
            else:
                logger.info(f"🔧 [Conditional judgment] tool_calls Is an empty list")
        else:
            logger.info(f"🔧 [Conditional judgment] No tool_calls attribute")

        # ✅ priority 1: If there is already report content, it means that the analysis has been completed and there will be no more loops.
        if fundamentals_report and len(fundamentals_report) > 100:
            logger.info(f"🔀 [Conditional judgment] ✅ Report completed, return: Msg Clear Fundamentals")
            return "Msg Clear Fundamentals"

        # ✅ priority 2: If there are tool_calls, execute the tool
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            # Check if the maximum number of calls has been exceeded
            if tool_call_count >= max_tool_calls:
                logger.warning(f"🔧 [Infinite loop repair] The number of tool calls has reached the upper limit({tool_call_count}/{max_tool_calls}), But there are still tool_calls, forced to end")
                return "Msg Clear Fundamentals"

            logger.info(f"🔀 [Conditional judgment] 🔧 tool_calls detected, return: tools_fundamentals")
            return "tools_fundamentals"

        # ✅ priority 3: No tool_calls, ends normally
        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear Fundamentals")
        return "Msg Clear Fundamentals"

    def should_continue_index_analyst(self, state: AgentState):
        """Determine whether market/index analysis should continue"""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        if not messages:
            logger.info(f"🔀 [Conditional judgment] should_continue_index_analyst - No message, return: tools_index_analyst")
            return "tools_index_analyst"

        last_message = messages[-1]
        tool_call_count = state.get("index_tool_call_count", 0)
        max_tool_calls = 2  # Market analysis may require multiple tool calls

        # Check whether there is already a market analysis report
        index_report = state.get("index_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_index_analyst")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(index_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")
        logger.info(f"🔀 [Conditional judgment] - last message type: {type(last_message).__name__}")

        # Infinite loop repair: If the maximum number of tool calls is reached, force the end
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [Infinite loop repair] Maximum number of tool calls reached {max_tool_calls}, force end")
            return "Msg Clear Index Analyst"

        # Check if there is a tool call
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔀 [Conditional judgment] There are tool_calls, return: tools_index_analyst")
            return "tools_index_analyst"

        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear Index Analyst")
        return "Msg Clear Index Analyst"

    def should_continue_sector_analyst(self, state: AgentState):
        """Determine whether industry/sector analysis should continue"""
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("agents")

        messages = state["messages"]
        if not messages:
            logger.info(f"🔀 [Conditional judgment] should_continue_sector_analyst - No message, return: tools_sector_analyst")
            return "tools_sector_analyst"

        last_message = messages[-1]
        tool_call_count = state.get("sector_tool_call_count", 0)
        max_tool_calls = 2  # Sector analysis may require multiple tool calls

        # Check whether there is already a sector analysis report
        sector_report = state.get("sector_report", "")

        logger.info(f"🔀 [Conditional judgment] should_continue_sector_analyst")
        logger.info(f"🔀 [Conditional judgment] - Number of messages: {len(messages)}")
        logger.info(f"🔀 [Conditional judgment] - Report length: {len(sector_report)}")
        logger.info(f"🔧 [Infinite loop repair] - Number of tool calls: {tool_call_count}/{max_tool_calls}")
        logger.info(f"🔀 [Conditional judgment] - last message type: {type(last_message).__name__}")

        # Infinite loop repair: If the maximum number of tool calls is reached, force the end
        if tool_call_count >= max_tool_calls:
            logger.warning(f"🔧 [Infinite loop repair] Maximum number of tool calls reached {max_tool_calls}, force end")
            return "Msg Clear Sector Analyst"

        # Check if there is a tool call
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"🔀 [Conditional judgment] There are tool_calls, return: tools_sector_analyst")
            return "tools_sector_analyst"

        logger.info(f"🔀 [Conditional judgment] ✅ No tool_calls, return: Msg Clear Sector Analyst")
        return "Msg Clear Sector Analyst"

    def should_trigger_multi_round_debate(self, state: AgentState) -> str:
        """Evaluate JSD and CBS against transaction spread to gate multi-round debate.

        Returns:
            "fast_path" or "multi_round_debate"
        """
        posteriors = state.get("analyst_posteriors") if isinstance(state, dict) else getattr(state, "analyst_posteriors", None)
        raw_spread = state.get("estimated_spread_bps") if isinstance(state, dict) else getattr(state, "estimated_spread_bps", 15.0)
        try:
            spread_bps = float(raw_spread if raw_spread is not None else 15.0)
        except (ValueError, TypeError):
            spread_bps = 15.0

        weights = state.get("analyst_weights") if isinstance(state, dict) else getattr(state, "analyst_weights", None)

        routing = calculate_cbs_routing(
            posteriors=posteriors or {},
            estimated_spread_bps=spread_bps,
            max_debate_rounds=self.max_debate_rounds,
            weights=weights,
        )
        decision = routing["route"]
        jsd = routing["jsd"]
        cbs_bps = routing["cbs_bps"]
        expected_gain = routing["expected_debate_gain_bps"]
        weighted_move = routing["weighted_expected_move_bps"]
        dynamic_rounds = routing["dynamic_debate_rounds"]

        if decision == "fast_path":
            logger.info(
                f"🔀 [CBS Debate Gate] -> FAST_PATH | JSD={jsd:.4f} (<0.12: {jsd < 0.12}), "
                f"CBS={cbs_bps:.2f} bps <= Spread={spread_bps:.2f} bps ({cbs_bps <= spread_bps})"
            )
        else:
            logger.info(
                f"🔀 [CBS Debate Gate] -> MULTI_ROUND_DEBATE | JSD={jsd:.4f} >= 0.12, "
                f"CBS={cbs_bps:.2f} bps > Spread={spread_bps:.2f} bps | Dynamic Rounds={dynamic_rounds}/{self.max_debate_rounds}"
            )

        # Store runtime metrics in state (for observability and downstream logging)
        if isinstance(state, dict):
            state["debate_jsd"] = jsd
            state["cbs_bps"] = cbs_bps
            state["expected_debate_gain_bps"] = expected_gain
            state["weighted_expected_move_bps"] = weighted_move
            state["dynamic_debate_rounds"] = dynamic_rounds
            state["_max_debate_rounds"] = dynamic_rounds if dynamic_rounds > 0 else 1
            if decision == "fast_path":
                state["_risk_self_debate"] = True
            else:
                state["_risk_self_debate"] = False

        self.dynamic_debate_rounds = dynamic_rounds if dynamic_rounds > 0 else self.max_debate_rounds
        return decision

    def should_gate_debate(self, state: Dict[str, Any]) -> str:
        """Alias for should_trigger_multi_round_debate."""
        return self.should_trigger_multi_round_debate(state)

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""
        current_count = state["investment_debate_state"]["count"]
        # Use dynamic debate rounds if scaled by should_trigger_multi_round_debate, fallback to max_debate_rounds
        effective_rounds = state.get("dynamic_debate_rounds") if isinstance(state, dict) else None
        if not effective_rounds or effective_rounds < 1:
            effective_rounds = getattr(self, "dynamic_debate_rounds", self.max_debate_rounds)
        if not effective_rounds or effective_rounds < 1:
            effective_rounds = self.max_debate_rounds

        max_count = 2 * effective_rounds
        current_speaker = state["investment_debate_state"]["current_response"]

        # 🔍 Detailed log
        logger.info(f"🔍 [investment debate control] Current number of speeches: {current_count}, Maximum times: {max_count} (Configuration rounds: {self.max_debate_rounds}, Effective: {effective_rounds})")
        logger.info(f"🔍 [investment debate control] current speaker: {current_speaker}")

        if current_count >= max_count:
            logger.info(f"✅ [investment debate control] Reach the maximum number of times and end the debate -> Research Manager")
            return "Research Manager"

        next_speaker = "Bear Researcher" if current_speaker.startswith("Bull") else "Bull Researcher"
        logger.info(f"🔄 [investment debate control] continue the debate -> {next_speaker}")
        return next_speaker

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        current_count = state["risk_debate_state"]["count"]
        max_count = 3 * self.max_risk_discuss_rounds
        latest_speaker = state["risk_debate_state"]["latest_speaker"]

        # 🔍 Detailed log
        logger.info(f"🔍 [risk discussion control] Current number of speeches: {current_count}, Maximum times: {max_count} (Configuration rounds: {self.max_risk_discuss_rounds})")
        logger.info(f"🔍 [risk discussion control] last speaker: {latest_speaker}")

        if current_count >= max_count:
            logger.info(f"✅ [risk discussion control] Reached the maximum number of times and ended the discussion -> Risk Judge")
            return "Risk Judge"

        # Determine next speaker
        if latest_speaker.startswith("Risky"):
            next_speaker = "Safe Analyst"
        elif latest_speaker.startswith("Safe"):
            next_speaker = "Neutral Analyst"
        else:
            next_speaker = "Risky Analyst"

        logger.info(f"🔄 [risk discussion control] continue discussion -> {next_speaker}")
        return next_speaker


def should_trigger_multi_round_debate(state: AgentState) -> str:
    """Module-level convenience gateway for conditional debate routing."""
    logic = ConditionalLogic()
    return logic.should_trigger_multi_round_debate(state)


def should_gate_debate(state: Dict[str, Any]) -> str:
    """Public alias for should_trigger_multi_round_debate."""
    logic = ConditionalLogic()
    return logic.should_gate_debate(state)

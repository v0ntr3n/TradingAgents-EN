# TradingAgents/graph/conditional_logic.py

try:
    from tradingagents.agents.utils.agent_states import AgentState
except (ImportError, KeyError):
    AgentState = dict

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")



def compute_jensen_shannon_divergence(
    posteriors: dict,
    weights: dict = None
) -> float:
    """
    Compute the base-2 Jensen-Shannon Divergence (JSD in [0, log2(3)]) normalized to [0, 1]
    across 3-class analyst probability vectors (p_optimistic, p_neutral, p_cautious).
    """
    import math

    if not posteriors or len(posteriors) < 2:
        return 0.0

    keys = list(posteriors.keys())
    if weights:
        raw_w = [max(0.0, float(weights.get(k, 1.0))) for k in keys]
        total_w = sum(raw_w)
        w = [x / total_w for x in raw_w] if total_w > 0 else [1.0 / len(keys)] * len(keys)
    else:
        w = [1.0 / len(keys)] * len(keys)

    def _shannon_entropy(p_vec):
        h = 0.0
        for p in p_vec:
            if p > 1e-12:
                h -= p * math.log2(p)
        return h

    p_bar = [0.0, 0.0, 0.0]
    weighted_entropies = 0.0
    for idx, k in enumerate(keys):
        post = posteriors[k]
        p_vec = [
            float(post.get("p_optimistic", 1.0 / 3.0)),
            float(post.get("p_neutral", 1.0 / 3.0)),
            float(post.get("p_cautious", 1.0 / 3.0)),
        ]
        s = sum(p_vec)
        if s > 0:
            p_vec = [x / s for x in p_vec]
        else:
            p_vec = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
        for c in range(3):
            p_bar[c] += w[idx] * p_vec[c]
        weighted_entropies += w[idx] * _shannon_entropy(p_vec)

    jsd_bits = max(0.0, _shannon_entropy(p_bar) - weighted_entropies)
    max_bits = math.log2(3.0)
    return min(1.0, jsd_bits / max_bits)


def compute_cbs_bps(posteriors: dict, weights: dict = None) -> float:
    """
    Compute the Coordination Breakeven Spread (CBS in bps):
    CBS_bps = (JSD * weighted_expected_move_bps) / 2.0
    """
    if not posteriors:
        return 0.0

    jsd = compute_jensen_shannon_divergence(posteriors, weights=weights)
    keys = list(posteriors.keys())
    if weights:
        raw_w = [max(0.0, float(weights.get(k, 1.0))) for k in keys]
        total_w = sum(raw_w)
        w = [x / total_w for x in raw_w] if total_w > 0 else [1.0 / len(keys)] * len(keys)
    else:
        w = [1.0 / len(keys)] * len(keys)

    weighted_move_bps = sum(
        w[idx] * abs(float(posteriors[k].get("expected_move_bps", 50.0)))
        for idx, k in enumerate(keys)
    )
    return round((jsd * weighted_move_bps) / 2.0, 4)


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1, jsd_threshold: float = 0.12, default_spread_bps: float = 15.0):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.jsd_threshold = float(jsd_threshold)
        self.default_spread_bps = float(default_spread_bps)

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

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""
        current_count = state["investment_debate_state"]["count"]
        target_rounds = self.max_debate_rounds
        if "cbs_gating_decision" in state and isinstance(state["cbs_gating_decision"], dict):
            target_rounds = state["cbs_gating_decision"].get("target_debate_rounds", self.max_debate_rounds)
        max_count = 2 * target_rounds
        current_speaker = state["investment_debate_state"]["current_response"]

        # 🔍 Detailed log
        logger.info(f"🔍 [investment debate control] Current number of speeches: {current_count}, Maximum times: {max_count} (Configuration rounds: {target_rounds})")
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


    def should_gate_debate(self, state: AgentState) -> dict:
        """
        Evaluate whether multi-round Bull/Bear debate clears the JSD and
        Coordination Breakeven Spread (CBS) thresholds.
        """
        posteriors = state.get("analyst_posteriors")
        if not posteriors:
            try:
                from core.agents.analyst import extract_structured_posterior
                extracted = {}
                for key, role in [
                    ("market_report", "market"),
                    ("fundamentals_report", "fundamentals"),
                    ("news_report", "news"),
                    ("sentiment_report", "social"),
                    ("index_report", "index"),
                    ("sector_report", "sector"),
                ]:
                    report_text = state.get(key)
                    if report_text:
                        extracted[role] = extract_structured_posterior(str(report_text))
                if extracted:
                    posteriors = extracted
                    state["analyst_posteriors"] = posteriors
            except Exception as e:
                logger.warning(f"Error extracting posteriors from reports: {e}")

        posteriors = posteriors or {}
        weights = state.get("analyst_weights")
        regime = state.get("market_regime", "sideways")
        if not weights and posteriors:
            try:
                from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
                wm = RegimeMultiplicativeWeightManager()
                weights = wm.get_weights(regime)
                state["analyst_weights"] = weights
            except Exception as e:
                logger.warning(f"Error obtaining regime weights: {e}")
                weights = None

        spread_bps = float(state.get("estimated_spread_bps", self.default_spread_bps))
        jsd_thresh = float(state.get("jsd_threshold", self.jsd_threshold))

        jsd = compute_jensen_shannon_divergence(posteriors, weights=weights)
        cbs_bps = compute_cbs_bps(posteriors, weights=weights)

        if jsd < jsd_thresh or cbs_bps <= spread_bps:
            state["_risk_self_debate"] = True
            target_rounds = 0
            route = "fast_path_single_pass"
        else:
            state["_risk_self_debate"] = False
            target_rounds = min(self.max_debate_rounds, max(1, int(round(jsd * 4))))
            route = "multi_round_debate"

        gating_decision = {
            "jsd": round(jsd, 6),
            "cbs_bps": round(cbs_bps, 4),
            "estimated_spread_bps": spread_bps,
            "target_debate_rounds": target_rounds,
            "risk_self_debate": state["_risk_self_debate"],
            "route": route,
        }
        state["cbs_gating_decision"] = gating_decision
        return gating_decision

    def should_trigger_multi_round_debate(self, state: AgentState) -> str:
        """Route to 'Research Manager' (fast-path) or 'Bull Researcher' (debate) based on CBS gate."""
        decision = self.should_gate_debate(state)
        if decision["route"] == "fast_path_single_pass":
            return "Research Manager"
        return "Bull Researcher"

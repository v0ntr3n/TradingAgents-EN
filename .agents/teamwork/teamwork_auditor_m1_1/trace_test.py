import math
from core.agents.analyst import AnalystAgent
from tradingagents.graph.conditional_logic import ConditionalLogic, should_trigger_multi_round_debate

class TestAgent(AnalystAgent):
    analyst_type = 'test'
    output_field = 'test_report'
    def _build_system_prompt(self, *a, **k): return ''
    def _build_user_prompt(self, *a, **k): return ''

agent = TestAgent(config=None)

# 1. Tracing _normalize_posterior with adversarial inputs
print('--- TRACE 1: _normalize_posterior ---')
adv1 = {'p_optimistic': ' 60% ', 'p_neutral': '30 %', 'p_cautious': '10%', 'expected_move_bps': '+125.5 bps', 'confidence': '85%', 'market_regime': 'BULLISH'}
norm1 = agent._normalize_posterior(adv1)
print('Adversarial 1 (strings, percentages, spaces):', norm1)
assert norm1['p_optimistic'] == 0.60
assert norm1['p_neutral'] == 0.30
assert norm1['p_cautious'] == 0.10
assert abs(sum([norm1['p_optimistic'], norm1['p_neutral'], norm1['p_cautious']]) - 1.0) < 1e-6
assert norm1['expected_move_bps'] == 125.5
assert norm1['confidence'] == 0.85
assert norm1['market_regime'] == 'bull'

adv2 = {'p_optimistic': None, 'p_neutral': 'invalid', 'p_cautious': -5, 'expected_move_bps': None, 'confidence': 999}
norm2 = agent._normalize_posterior(adv2)
print('Adversarial 2 (None, invalid, negative, out-of-bounds):', norm2)
assert abs(sum([norm2['p_optimistic'], norm2['p_neutral'], norm2['p_cautious']]) - 1.0) < 1e-4
assert norm2['confidence'] == 1.0

# 2. Tracing _parse_response
print('\n--- TRACE 2: _parse_response ---')
fence = "```"
text_with_fences = f"""Here is my report on 600519.SH:
Revenues grew 15% YoY.
{fence}json:signal
{{
  "p_optimistic": 0.65,
  "p_neutral": 0.25,
  "p_cautious": 0.10,
  "expected_move_bps": 100.0,
  "confidence": 0.80,
  "market_regime": "bull"
}}
{fence}
Conclusion: Strong buy."""
parsed = agent._parse_response(text_with_fences)
print('Parsed report text without signal block:\n', parsed['content'])
assert '```json:signal' not in parsed['content']
assert 'p_optimistic' not in parsed['content']
assert 'Strong buy' in parsed['content']
print('Parsed posterior:\n', parsed['posterior'])
assert parsed['posterior']['p_optimistic'] == 0.65

# 3. Tracing should_trigger_multi_round_debate
print('\n--- TRACE 3: should_trigger_multi_round_debate ---')
cl = ConditionalLogic(max_debate_rounds=3)
state = {
    'analyst_posteriors': {
        'market_analyst_v2': {'p_optimistic': 0.85, 'p_neutral': 0.10, 'p_cautious': 0.05, 'expected_move_bps': 180.0, 'confidence': 0.90},
        'news_analyst_v2': {'p_optimistic': 0.10, 'p_neutral': 0.15, 'p_cautious': 0.75, 'expected_move_bps': -180.0, 'confidence': 0.85},
    },
    'investment_debate_state': {'count': 0, 'current_response': ''}
}
decision = cl.should_trigger_multi_round_debate(state)
print('Decision:', decision)
print('State metrics injected: JSD =', state['debate_jsd'], 'CBS_bps =', state['cbs_bps'], 'Dynamic rounds =', state['dynamic_debate_rounds'])
assert decision == 'multi_round_debate'
assert state['debate_jsd'] >= 0.12
assert state['cbs_bps'] > 15.0
assert state['dynamic_debate_rounds'] >= 2

# Low disagreement test
state_low = {
    'analyst_posteriors': {
        'market_analyst_v2': {'p_optimistic': 0.85, 'p_neutral': 0.10, 'p_cautious': 0.05, 'expected_move_bps': 180.0, 'confidence': 0.90},
        'news_analyst_v2': {'p_optimistic': 0.80, 'p_neutral': 0.15, 'p_cautious': 0.05, 'expected_move_bps': 180.0, 'confidence': 0.85},
    }
}
decision_low = cl.should_trigger_multi_round_debate(state_low)
print('Low disagreement decision:', decision_low)
assert decision_low == 'fast_path'
print('\nALL TRACES VERIFIED SUCCESSFULLY.')

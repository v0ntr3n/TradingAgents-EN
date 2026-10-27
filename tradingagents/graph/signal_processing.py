# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI

# Import the unified logging system and graph processing module log decorator
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_graph_module
logger = get_logger("graph.signal_processing")


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    @log_graph_module("signal_processing")
    def process_signal(self, full_signal: str, stock_symbol: str = None) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text
            stock_symbol: Stock symbol to determine currency type

        Returns:
            Dictionary containing extracted decision information
        """

        # Validate input parameters
        if not full_signal or not isinstance(full_signal, str) or len(full_signal.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] The input signal is empty or invalid: {repr(full_signal)}")
            return {
                'action': 'hold',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': 'Input signal is invalid, hold suggestion by default'
            }

        # Clean and validate signal content
        full_signal = full_signal.strip()
        if len(full_signal) == 0:
            logger.error(f"❌ [SignalProcessor] Signal content is empty")
            return {
                'action': 'hold',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': 'The signal content is empty and holds suggestions by default.'
            }

        # Detect stock type and currency
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(stock_symbol)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.info(f"🔍 [SignalProcessor] Process signals: stocks={stock_symbol}, market={market_info['market_name']}, Currency={currency}",
                   extra={'stock_symbol': stock_symbol, 'market': market_info['market_name'], 'currency': currency})

        messages = [
            (
                "system",
                f"""You are a professional financial analysis assistant responsible for extracting structured investment decision-making information from traders analysis reports.

Please extract the following information from the provided analysis report and return it in JSON format:

{{
    "action": "Buy/Hold/Sell",
    "target_price": numbers({currency}price,**A specific value must be provided and cannot be null**),
    "confidence": numbers(0-1 between, if not explicitly mentioned then 0.7),
    "risk_score": numbers(0-1 between, if not explicitly mentioned then 0.5),
    "reasoning": "Summary of the main reasons for the decision"
}}

Please make sure:
1. action Field must be"buy", "hold"or"sell"One (English buy/hold/sell is absolutely not allowed)
2. target_price Must be a specific number,target_price should be reasonable{currency}price figure (using{currency_symbol}symbol)
3. confidence and risk_score should be between 0-1
4. reasoning Should be a concise Chinese summary
5. All content must be in Chinese, no investment advice in English is allowed

Special attention:
- Stock code {stock_symbol or 'unknown'} Yes{market_info['market_name']}, Use{currency}Pricing
- The target price must be consistent with the currency in which the stock is traded ({currency_symbol}) 

If some information is not explicitly mentioned in the report, use reasonable defaults.""",
            ),
            ("human", full_signal),
        ]

        # Verify message content
        if not messages or len(messages) == 0:
            logger.error(f"❌ [SignalProcessor] messages is empty")
            return self._get_default_decision()
        
        # Verify human message content
        human_content = messages[1][1] if len(messages) > 1 else ""
        if not human_content or len(human_content.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] human The message content is empty")
            return self._get_default_decision()

        logger.debug(f"🔍 [SignalProcessor] Prepare to call LLM, number of messages: {len(messages)}, Signal length: {len(full_signal)}")

        try:
            response = self.quick_thinking_llm.invoke(messages).content
            logger.debug(f"🔍 [SignalProcessor] LLM response: {response[:200]}...")

            # Try to parse JSON response
            import json
            import re

            # Extract JSON part
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                logger.debug(f"🔍 [SignalProcessor] extracted JSON: {json_text}")
                decision_data = json.loads(json_text)

                # Validate and standardize data
                action = decision_data.get('action', 'hold')
                if action not in ['buy', 'hold', 'sell']:
                    # Try mapping English and other variants
                    action_map = {
                        'buy': 'buy', 'hold': 'hold', 'sell': 'sell',
                        'BUY': 'buy', 'HOLD': 'hold', 'SELL': 'sell',
                        'buy': 'buy', 'keep': 'hold', 'for sale': 'sell',
                        'purchase': 'buy', 'keep': 'hold', 'dispose': 'sell'
                    }
                    action = action_map.get(action, 'hold')
                    if action != decision_data.get('action', 'hold'):
                        logger.debug(f"🔍 [SignalProcessor] Investment advice mapping: {decision_data.get('action')} -> {action}")

                # Handle target prices to ensure correct extraction
                target_price = decision_data.get('target_price')
                if target_price is None or target_price == "null" or target_price == "":
                    # If there is no target price in JSON, try to extract from reasoning and full text
                    reasoning = decision_data.get('reasoning', '')
                    full_text = f"{reasoning} {full_signal}"  # Expand search
                    
                    # Enhanced price matching mode
                    price_patterns = [
                        r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
                        r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
                        r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # price: 45.50
                        r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # price: 45.50
                        r'reasonable[Price]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)', # Reasonable price: 45.50
                        r'Valuation[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # Valuation: 45.50
                        r'[¥\$](\d+(?:\.\d+)?)',                      # ¥45.50 or $190
                        r'(\d+(?:\.\d+)?)Yuan',                         # 45.50 Yuan
                        r'(\d+(?:\.\d+)?)US dollars',                       # 190 US dollars
                        r'Suggestions[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # Suggestions: 45.50
                        r'expected[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',        # expected: 45.50
                        r'look[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',          # see 45.50
                        r'rise[Arrive]\s*[¥\$]?(\d+(?:\.\d+)?)',        # rise to 45.50
                        r'(\d+(?:\.\d+)?)\s*[¥\$]',                  # 45.50¥
                    ]
                    
                    for pattern in price_patterns:
                        price_match = re.search(pattern, full_text, re.IGNORECASE)
                        if price_match:
                            try:
                                target_price = float(price_match.group(1))
                                logger.debug(f"🔍 [SignalProcessor] Extract target price from text: {target_price} (mode: {pattern})")
                                break
                            except (ValueError, IndexError):
                                continue

                    # If you still don't find a price, try smart reckoning
                    if target_price is None or target_price == "null" or target_price == "":
                        target_price = self._smart_price_estimation(full_text, action, is_china)
                        if target_price:
                            logger.debug(f"🔍 [SignalProcessor] Intelligent calculation of target price: {target_price}")
                        else:
                            target_price = None
                            logger.warning(f"🔍 [SignalProcessor] Failed to extract target price, set to None")
                else:
                    # Make sure the price is a numeric type
                    try:
                        if isinstance(target_price, str):
                            # Clean up prices in string format
                            clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').replace('Yuan', '').replace('US dollars', '').strip()
                            target_price = float(clean_price) if clean_price and clean_price.lower() not in ['none', 'null', ''] else None
                        elif isinstance(target_price, (int, float)):
                            target_price = float(target_price)
                        logger.debug(f"🔍 [SignalProcessor] Processed target price: {target_price}")
                    except (ValueError, TypeError):
                        target_price = None
                        logger.warning(f"🔍 [SignalProcessor] Price conversion failed, set to None")

                result = {
                    'action': action,
                    'target_price': target_price,
                    'confidence': float(decision_data.get('confidence', 0.7)),
                    'risk_score': float(decision_data.get('risk_score', 0.5)),
                    'reasoning': decision_data.get('reasoning', 'Investment advice based on comprehensive analysis')
                }
                logger.info(f"🔍 [SignalProcessor] Processing results: {result}",
                           extra={'action': result['action'], 'target_price': result['target_price'],
                                 'confidence': result['confidence'], 'stock_symbol': stock_symbol})
                return result
            else:
                # If unable to parse JSON, use simple text extraction
                return self._extract_simple_decision(response)

        except Exception as e:
            logger.error(f"Signal handling error: {e}", exc_info=True, extra={'stock_symbol': stock_symbol})
            # Fallback to simple extraction
            return self._extract_simple_decision(full_signal)

    def _smart_price_estimation(self, text: str, action: str, is_china: bool) -> float:
        """Intelligent price calculation method"""
        import re
        
        # Try to extract current price and increase and decrease information from text
        current_price = None
        percentage_change = None
        
        # Extract current price
        current_price_patterns = [
            r'current price[grid position]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'Current price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'stock price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',
        ]
        
        for pattern in current_price_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    current_price = float(match.group(1))
                    break
                except ValueError:
                    continue
        
        # Extract price increase and decrease information
        percentage_patterns = [
            r'rise\s*(\d+(?:\.\d+)?)%',
            r'Increase\s*(\d+(?:\.\d+)?)%',
            r'growth\s*(\d+(?:\.\d+)?)%',
            r'(\d+(?:\.\d+)?)%\s*of?rise',
        ]
        
        for pattern in percentage_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    percentage_change = float(match.group(1)) / 100
                    break
                except ValueError:
                    continue
        
        # Calculate target price based on actions and information
        if current_price and percentage_change:
            if action == 'buy':
                return round(current_price * (1 + percentage_change), 2)
            elif action == 'sell':
                return round(current_price * (1 - percentage_change), 2)
        
        # If there is a current price but no increase or decrease, use the default estimate
        if current_price:
            if action == 'buy':
                # Buying recommendation defaults to 10-20% increase
                multiplier = 1.15 if is_china else 1.12
                return round(current_price * multiplier, 2)
            elif action == 'sell':
                # Sell recommendation defaults to a 5-10% drop
                multiplier = 0.95 if is_china else 0.92
                return round(current_price * multiplier, 2)
            else:  # hold
                # Hold recommendation using current prices
                return current_price
        
        return None

    def _extract_simple_decision(self, text: str) -> dict:
        """Simple decision extraction method as fallback"""
        import re

        # Extract action
        action = 'hold'  # Default
        if re.search(r'buy|BUY', text, re.IGNORECASE):
            action = 'buy'
        elif re.search(r'sell|SELL', text, re.IGNORECASE):
            action = 'sell'
        elif re.search(r'hold|HOLD', text, re.IGNORECASE):
            action = 'hold'

        # Try to extract target price (using enhanced mode)
        target_price = None
        price_patterns = [
            r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
            r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # **target price**: 45.50
            r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
            r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # price: 45.50
            r'[¥\$](\d+(?:\.\d+)?)',                      # ¥45.50 or $190
            r'(\d+(?:\.\d+)?)Yuan',                         # 45.50 Yuan
        ]

        for pattern in price_patterns:
            price_match = re.search(pattern, text)
            if price_match:
                try:
                    target_price = float(price_match.group(1))
                    break
                except ValueError:
                    continue

        # If price not found, try smart calculation
        if target_price is None:
            # Detect stock type
            is_china = True  # The default assumption is A shares, the actual value should be obtained from the context
            target_price = self._smart_price_estimation(text, action, is_china)

        return {
            'action': action,
            'target_price': target_price,
            'confidence': 0.7,
            'risk_score': 0.5,
            'reasoning': 'Investment advice based on comprehensive analysis'
        }

    def _get_default_decision(self) -> dict:
        """Return to default investment decision"""
        return {
            'action': 'hold',
            'target_price': None,
            'confidence': 0.5,
            'risk_score': 0.5,
            'reasoning': 'Invalid input data, default holds suggestions'
        }

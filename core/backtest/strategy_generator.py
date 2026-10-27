"""
LLM Strategy generation
After the user confirms the parameters, the Backtrader Python code is generated + config
Supports L2 semantic verification, L3 execution verification and self-correction loop
"""
import json
import logging
import re
from typing import Any, Dict, Optional

from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

RETRY_MAX = 2  # Retries up to 2 times, for a total of 3 attempts

GENERATE_SYSTEM = """You are a strategy code generator. Based on the user s policy description, generate **Backtrader** Python Policy code and configuration.

 [Output format] Must output pure JSON, the format is as follows:
{
  "code": "Complete Python code string",
  "config": {
    "start_year": 2016,
    "end_year": 2025,
    "initial_capital": 1000000,
    "max_positions": 10,
    "benchmark": "000300",
    "market": "CN",
    "data_source": "tushare",
    "universe": {"type": "static", "symbols": ["600519", "000858", "000568", "002304", "000596", "603288", "000651", "000333", "600887", "601888"]}
  }
}

 [Important: Avoid Survivor Bias]
⚠️ Using current leading stocks to backtest the past 10-20 years will lead to serious survivor bias!

**Recommended practices (priority from high to low)**: 

1. **🆕 Use industry classification + Historical market capitalization**: universe.type = "industry"
   - The system will automatically obtain the stock with the largest market capitalization in the industry on the start date of the backtest
   - For example, when backtesting the liquor strategy from 2010 to 2020, the liquor faucet in 2010 will be used (rather than the current one).
   - Example:{"type": "industry", "industry": "Liquor", "max_symbols": 10}

2. **Use industry indices**: universe.type = "index"
   - Use the historical constituent stocks of the index (if there are restrictions on constituent stock data, very early data may not be obtained)
   - Example:{"type": "index", "index_code": "000932.SH"}

3. **Shorten the backtest cycle**: Static stock pool backtesting does not exceed 5 years (such as 2020-2025)

 [Industry Classification] (Recommended universe.type="industry") ⭐ best choice
Supported industry names:
- Consumer categories: liquor, food, home appliances, consumption (comprehensive)
- Financial: Banking, insurance, securities dealers, finance (comprehensive)
- Technology: semiconductors, software, communications, technology (comprehensive)
- New energy: photovoltaic, lithium battery, new energy, new energy vehicles
- Pharmaceutical category: medicine
- Others: real estate, building materials, steel, chemical industry

Example configuration:
```json
"universe": {"type": "industry", "industry": "Liquor", "max_symbols": 10}
```

 [Industry index code] (optional universe.type="index") 
- Consumer category: 000932.SH (CSI Consumer), 399997.SZ (CSI Liquor)
- Financial: 399986.SZ (China Securities Bank), 000914.SH (300 Finance)
- Technology: 399006.SZ (GEM Index), 000993.SH (All Index Information)

 [Static stock pool] (only used for backtesting in the past 3-5 years, long-term backtesting is not recommended)
Consumer category: 600519, 000858, 000568, 603288, 000651, 000333,600887

 [Backtrader Instructions for use]
- Class name must be defined:`GeneratedStrategy`, inheritance `bt.Strategy`
- `self.datas` is the data list,`self.datas[i]._name` for stock code
- Buy:`self.buy(data=..., size=Quantity)` or `self.buy(data=...)` (Full position when size is not specified)
- Sell:`self.sell(data=...)` or `self.close(data=...)`
- Position:`self.getposition(data).size`
- in `next()` Implement daily logic in
- **K thread index**: `data.close[0]` current bar,`data.close[-1]` Previous bar; historical N lowest price is used `min(data.low[-i] for i in range(1, N+1))`, and need to judge first `len(self) >= N`
- **Date**: use `data.datetime.date(0)` Get the current bar date
- **Breakthrough strategy key**: Tang Qian/channel breakthrough must be used**previous one**channel value!`Highest(high, 20)[0]` Contains the day s high, resulting in `close > entry_high` Almost impossible (close≤high) . Correct:`entry_high = highest_ind[-1]` (the 20-day highest of the previous root), and `next()` Add at the beginning `if len(self) < period+1: return` Skip warm-up

 [Easy mistakes in position calculation]
- If you customize size:`size` must be**Number of shares** (≥100 and is an integer multiple of 100)
- Error example:`units_to_buy = min(unit_count, cash//(price*100)*100)` If unit_count is lot size , you will get <100 shares, leading to `if size>=100` never established
- Correct: Number of lots converted into shares `shares = unit_count * 100`, Again `size = min(shares, cash//price//100*100)` and `size >= 100`

 [China A-share rules]
- The minimum trading unit is 100 shares (1 lot), and the backtesting engine automatically rounds to 100 shares.
- When no position is specified, the default is full position (use all available funds to buy)

 [Notes on strategy logic]
- in `__init__` Initialize all state variables used (such as `_last_sell_date`, `_checked_year`) , avoid `hasattr` causing the first execution to be skipped
- Circular logic (such as every Spring Festival): ensure that it can be triggered every year within the backtest interval, check the starting year of the data (for example, 600519 has data from 2001) and the strategy conditions cover the entire interval
- The selling conditions must be clear: immediately when you have a position and meet the selling opportunity `self.close(data)` or `self.sell(data)`

 [Rules]
- universe.type support "static" (symbols for a list of 6-digit ticker symbols) or "index" (index_code Such as "000300", parsed by the main platform)
- config.data_source: data source, optional tushare/akshare/baostock
- code Only import backtrader (as bt); datetime, date, timedelta have been injected and can be used directly (such as datetime(2024,1,1), date(2024,1,1), timedelta(days=30)) , No need import
- Pure JSON must be output, code is a string (internal line breaks are \\n) , Do not wrap markdown code blocks
"""


RETRY_USER_TEMPLATE = """The policy generated last time has the following problems. Please correct it and re-output pure JSON:

 [Last output]
{output}

 [Error]
{errors}

Please correct the above errors and output the corrected complete JSON (including code and config) without markdown code blocks."""


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse the JSON output by LLM (including code and config)"""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    if "code" not in data or "config" not in data:
        raise ValueError("Output must contain code and config fields")
    return data


async def generate_strategy_dsl(
    user_description: str,
    llm_client: Optional[UnifiedLLMClient] = None,
    validate_on_generate: bool = True,
    run_execution_check: bool = True,
) -> Dict[str, Any]:
    """
    Generate strategy (Python code + config) , Support evaluation and self-correction
    Args:
        user_description: User description (can include confirmed parameters)
        llm_client: Optional LLM client
        validate_on_generate: Whether to perform L2/L3 verification
        run_execution_check: Whether to perform L3 execution verification (requires validate_on_generate=True) 
    Returns:
        {"code": str, "config": dict}, Throws if parsing fails
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config

        cfg = await get_coding_llm_config()
        if not cfg:
            raise ValueError("LLM is not configured and policy cannot be generated")
        client = UnifiedLLMClient.from_config(cfg)

    from .dsl_evaluator import evaluate_strategy_python_full

    messages = [
        Message(role=MessageRole.SYSTEM, content=GENERATE_SYSTEM),
        Message(role=MessageRole.USER, content=user_description),
    ]

    last_error: Optional[str] = None
    for attempt in range(RETRY_MAX + 1):
        response = await client.achat(messages)
        raw = (response.content or "").strip()
        try:
            result = _parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Policy parsing failed (attempt %d): %s", attempt + 1, e)
            last_error = f"The generated policy is in the wrong format: {e}"
            if attempt < RETRY_MAX:
                messages.append(Message(role=MessageRole.ASSISTANT, content=raw))
                messages.append(
                    Message(
                        role=MessageRole.USER,
                        content=RETRY_USER_TEMPLATE.format(
                            output=raw[:800] + ("..." if len(raw) > 800 else ""),
                            errors=last_error,
                        ),
                    )
                )
                continue
            raise ValueError(last_error)

        if not validate_on_generate:
            return result

        passed, errors = await evaluate_strategy_python_full(
            result["code"], result["config"], run_execution_check=run_execution_check
        )
        if passed:
            return result

        last_error = "; ".join(errors)
        logger.warning("Strategy evaluation failed (attempt %d): %s", attempt + 1, last_error)
        if attempt < RETRY_MAX:
            messages.append(Message(role=MessageRole.ASSISTANT, content=raw))
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content=RETRY_USER_TEMPLATE.format(
                        output=json.dumps(result, ensure_ascii=False)[:800]
                        + ("..." if len(json.dumps(result)) > 800 else ""),
                        errors=last_error,
                    ),
                )
            )
            continue
        raise ValueError(f"Policy verification failed (retried{RETRY_MAX}times): {last_error}")

    raise ValueError(last_error or "Build failed")

"""Financial expert advisory module

When the helper returns no_data, use LLM as a senior financial practitioner to judge:
1. Is the business reasonable if the stock does not have such data (for example, it is reasonable for bank stocks to be unpledged)
2. If it is unreasonable, recommend a more suitable test stock
3. Give expert advice and feedback to the Skill generation pipeline

Applicable scenarios:
- Pledge analysis helper returns no_data: bank stocks/white horse stocks may not be pledged (reasonable), private stocks may not be pledged and may be unreasonable
- Financial analysis helper returns no_data: New stocks may not have annual reports (reasonable), old stocks may not have annual reports, which is unreasonable.
- News analysis helper returns no_data: There may be no news for unpopular stocks (semi-reasonable), but it is unreasonable to have no news for hot stocks.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm import UnifiedLLMClient

logger = logging.getLogger(__name__)


@dataclass
class ExpertJudgment:
    """Financial experts judgment results on no_data"""

    is_rational: bool = True  # no_data Whether the business is reasonable
    reasoning: str = ""  # Reasons for judgment
    recommended_stocks: List[Dict[str, str]] = field(default_factory=list)  # Recommended stocks that are more suitable for testing
    advice: str = ""  # Suggestions for LLM (inject feedback)
    confidence: float = 0.0  # Judgment Confidence 0-1

    def to_feedback_text(self) -> str:
        """Convert to text that can be injected with feedback"""
        lines = []
        lines.append(" [Financial expert judgment — no_data Rationality analysis]")
        lines.append(f"判断结果: {'合理（该股票本应无此类数据）' if self.is_rational else '不合理（该股票本应有此类数据）'}")
        if self.reasoning:
            lines.append(f"判断理由: {self.reasoning}")
        if self.recommended_stocks:
            lines.append("It is recommended to exchange shares and try again (these stocks are more likely to have data):")
            for stock in self.recommended_stocks[:3]:
                code = stock.get("code", "")
                name = stock.get("name", "")
                reason = stock.get("reason", "")
                lines.append(f"  - {code} {name}: {reason}")
        if self.advice:
            lines.append(f"专家建议: {self.advice}")
        return "\n".join(lines)


class FinancialExpertAdvisor:
    """Financial expert consultant: Use LLM to determine whether no_data is a reasonable business + Recommend more suitable test stocks"""

    # A Common stock pools with pledge data (typical of private companies and high pledge rates)
    # Used as a reference for LLM recommendations to avoid LLM fabrication.
    _PLEDGE_LIKELY_STOCKS = [
        {"code": "000651", "name": "格力电器", "industry": "家电", "reason": "The major shareholder has a pledge history and the data is complete"},
        {"code": "002594", "name": "比亚迪", "industry": "汽车", "reason": "Rich pledge records (400+ Article)"},
        {"code": "300750", "name": "宁德时代", "industry": "新能源", "reason": "There are pledge records and data specifications"},
        {"code": "600276", "name": "恒瑞医药", "industry": "医药", "reason": "White horse stocks, less pledged but possible"},
        {"code": "600519", "name": "贵州茅台", "industry": "白酒", "reason": "For blue chip stocks, major shareholders usually do not pledge"},
    ]

    # A general pool of test stocks recommended by various Skills (with complete financial data, news, pledges, etc.)
    _GENERAL_TEST_STOCKS = [
        {"code": "000651", "name": "格力电器", "industry": "家电", "reason": "Complete data, financial standards, and pledge"},
        {"code": "600519", "name": "贵州茅台", "industry": "白酒", "reason": "Blue chip leader, complete financial report, rich news"},
        {"code": "002594", "name": "比亚迪", "industry": "汽车", "reason": "Hot stocks with complete data"},
        {"code": "300750", "name": "宁德时代", "industry": "新能源", "reason": "GEM leader, data standardization"},
        {"code": "600036", "name": "招商银行", "industry": "银行", "reason": "Financial blue chip, complete financial report"},
    ]

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
    ):
        self._llm_client = llm_client
        self._provider = provider
        self._model = model

    def _get_client(self) -> UnifiedLLMClient:
        if self._llm_client is None:
            kwargs = {}
            if self._model:
                kwargs["model"] = self._model
            self._llm_client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
        return self._llm_client

    def judge_no_data_rationality(
        self,
        stock_symbol: str,
        stock_name: str,
        industry: str,
        skill_purpose: str,
        data_type: str,
        helper_name: str,
        helper_warnings: List[str],
        skill_category: str = "",
    ) -> ExpertJudgment:
        """
        Determine whether the helper returns no_data is business reasonable

        Args:
            stock_symbol: Test a stock symbol (e.g. "000001") 
            stock_name: Test stock name (e.g. "Ping An Bank") 
            industry: The industry to which the stock belongs (e.g. "bank") 
            skill_purpose: Skill Function description (such as "Equity Pledge Risk Portrait and Trend Analysis") 
            data_type: Data type description (e.g. "Pledge data", "Annual report financial data") 
            helper_name: helper Function name (such as "get_pledge_risk_profile") 
            helper_warnings: helper Returned warnings list
            skill_category: Skill categories (such as "fundamentals") 

        Returns:
            ExpertJudgment: Expert judgment results
        """
        try:
            client = self._get_client()
            prompt = self._build_judgment_prompt(
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                industry=industry,
                skill_purpose=skill_purpose,
                data_type=data_type,
                helper_name=helper_name,
                helper_warnings=helper_warnings,
                skill_category=skill_category,
            )

            from core.llm import Message

            response = client.chat([Message(role="user", content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)
            return self._parse_judgment(raw, stock_symbol, data_type)
        except Exception as e:
            logger.warning(f"⚠️ The judgment of financial experts failed and was downgraded to reasonable by default.: {e}")
            # Downgrade: By default, no_data is considered reasonable to avoid misjudgments.
            return ExpertJudgment(
                is_rational=True,
                reasoning=f"专家判断失败（{e}），默认认为 no_data 业务合理",
                recommended_stocks=[],
                advice="Please manually confirm whether no_data is reasonable",
                confidence=0.0,
            )

    def _build_judgment_prompt(
        self,
        stock_symbol: str,
        stock_name: str,
        industry: str,
        skill_purpose: str,
        data_type: str,
        helper_name: str,
        helper_warnings: List[str],
        skill_category: str,
    ) -> str:
        """Build financial expert judgment prompt"""
        # Provide reference stock pool based on data type
        reference_pool = ""
        if "质押" in data_type or "pledge" in helper_name.lower():
            reference_pool = "\n".join(
                f"  - {s['code']} {s['name']}（{s['industry']}）: {s['reason']}"
                for s in self._PLEDGE_LIKELY_STOCKS
            )
        else:
            reference_pool = "\n".join(
                f"  - {s['code']} {s['name']}（{s['industry']}）: {s['reason']}"
                for s in self._GENERAL_TEST_STOCKS
            )

        warnings_text = "\n".join(f"  - {w}" for w in helper_warnings) if helper_warnings else "  (无)"

        return f"""你是一位资深 A 股金融分析师，擅长判断金融数据的业务合理性。

## 背景
我们正在生成一个 Skill 工具：{skill_purpose}
测试股票：{stock_symbol} {stock_name}（行业：{industry}）
调用的标准 helper 函数：{helper_name}
helper 返回状态：no_data（无数据）
helper 返回的警告：
{warnings_text}

## 你的任务
判断"{stock_name}（{stock_symbol}）没有{data_type}"是否业务合理。

## 判断要点
1. **行业特性**：银行股通常无质押（监管限制），民营制造股通常有质押
2. **公司性质**：央企/国企蓝筹通常质押少，民营中小企业通常质押多
3. **数据类型特性**：
   - 质押数据：银行/保险/白酒龙头可能无质押（合理），民营制造业应有质押
   - 年报财务：上市超过 1 年的公司应有年报，次新股可能无年报（合理）
   - 新闻数据：热点股应有新闻，冷门股可能无新闻（半合理）
   - 技术指标：所有上市股票都应有技术指标数据（无数据=不合理）
4. **不要假设数据源失效**：先假设数据源正常，判断 no_data 是否业务合理

## 输出格式（严格 JSON）
```json
{{
  "is_rational": true或false,
  "reasoning": "判断理由（用金融从业者视角，结合行业和公司特性）",
  "recommended_stocks": [
    {{"code": "股票代码", "name": "股票名称", "reason": "推荐理由（为什么这只股票更可能有数据）"}}
  ],
  "advice": "给 Skill 生成 LLM 的建议（如：建议换股重试 / no_data 是业务正确结果应返回 success / 检查数据源权限等）",
  "confidence": 0.0到1.0
}}
```

## 参考股票池（A 股常见有数据股票）
{reference_pool}

## 重要约束
- recommended_stocks 最多 3 个，必须从参考股票池中选择
- 如果 is_rational=true（no_data 业务合理），advice 应建议"返回 success + 标注无数据"
- 如果 is_rational=false（no_data 不合理），advice 应建议"换股重试"
- confidence 反映你对判断的把握程度

请只输出纯 JSON，不要任何其他文字。"""


    def _parse_judgment(self, raw: str, original_symbol: str, data_type: str) -> ExpertJudgment:
        """Parse JSON judgment returned by LLM"""
        # Extract JSON
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            logger.warning(f"⚠️ Financial experts return to Africa JSON: {raw[:200]}")
            return ExpertJudgment(
                is_rational=True,
                reasoning="The expert returns an abnormal format and by default considers the no_data business to be reasonable.",
                confidence=0.0,
            )

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Financial Expert JSON parsing failed: {e}")
            return ExpertJudgment(
                is_rational=True,
                reasoning="Expert JSON parsing fails, and the default is that no_data business is reasonable",
                confidence=0.0,
            )

        # Analyze recommended stocks
        recommended = []
        for stock in data.get("recommended_stocks", [])[:3]:
            if isinstance(stock, dict) and stock.get("code"):
                recommended.append(
                    {
                        "code": str(stock.get("code", "")).strip(),
                        "name": str(stock.get("name", "")).strip(),
                        "reason": str(stock.get("reason", "")).strip(),
                    }
                )

        return ExpertJudgment(
            is_rational=bool(data.get("is_rational", True)),
            reasoning=str(data.get("reasoning", "")),
            recommended_stocks=recommended,
            advice=str(data.get("advice", "")),
            confidence=float(data.get("confidence", 0.0)),
        )


# Global singleton
_expert_advisor: Optional[FinancialExpertAdvisor] = None


def get_financial_expert_advisor(
    llm_client: Optional[UnifiedLLMClient] = None,
    provider: str = "deepseek",
    model: Optional[str] = None,
) -> FinancialExpertAdvisor:
    """获取财经专家顾问全局实例"""
    global _expert_advisor
    if _expert_advisor is None or llm_client is not None:
        _expert_advisor = FinancialExpertAdvisor(
            llm_client=llm_client, provider=provider, model=model
        )
    return _expert_advisor

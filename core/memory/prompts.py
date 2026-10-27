"""
mem0 unified memory layer — Custom fact extraction in the financial field prompt

mem0 in add() LLM is called to extract facts from the conversation.
Customize prompts to make the extraction results more suitable for financial investment research scenarios.
"""

FINANCIAL_FACT_EXTRACTION_PROMPT = """You are a professional financial information extractor. Extract the following types of key facts from conversations:

1. **User investment preferences** — Investment style (value/growth/trend/quantification), industry preference, risk level, holding period
2. **Stock/Sector Views** — Users or AI s opinions and conclusions on specific stocks, sectors, and indices (including directional judgments and reasons)
3. **Analysis conclusion** — Key findings on fundamentals, technical aspects, and financial aspects (such as high PE valuation, MACD golden cross, major capital inflows)
4. **trading behavior patterns** — Stop loss discipline, positioning habits, tendency to chase ups and kill downs, and discipline deviations discovered during review
5. **Technical lessons** — Data source usage experience, tool call failure reasons, code implementation pitfalls (related to Skill generation)
6. **time sensitive events** — Events with clear time windows such as financial report release, lifting date, dividend ex-rights, etc.

Rules:
- Extract only the facts clearly stated in the conversation, without speculation or extension
- Ignore greetings, greetings, small talk, and formatting instructions
- Each fact is independent and concise (one sentence, no more than 80 words)
- Contains key entities (stock code, stock name, time, amount, indicator value)
- If there are no valid facts to extract from the conversation, an empty list is returned
- Only one duplicate or equivalent fact is retained
"""

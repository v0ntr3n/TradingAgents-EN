from __future__ import annotations
import sys as _sys

# === position.technical_analyst_v2 ===
"""
technical analyst v2.0 (Position analysis)

Technical analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


def _build_market_data_tool_date_guard(code: str, analysis_date: str) -> str:
    return (
        "\n\n## Tool call parameter constraints\n"
        f"- To call get_stock_market_data_unified, ticker must be used {code}\n"
        f"- start_date Must be filled in strictly as {analysis_date}\n"
        f"- end_date Must be filled in strictly as {analysis_date}\n"
        "- Do not use sample dates, historical placeholder dates, or extrapolate other dates.\n"
    )


# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class TechnicalAnalystV2(ResearcherAgent):
    """
    technical analyst v2.0 (Position analysis)
    
    Function:
    - Analyze K-line trends and technical indicators
    - Evaluate support and resistance levels
    - Determine short-term trends
    
    Workflow:
    1. Read position information and market data
    2. Using LLM to analyze technical aspects
    3. Generate technical analysis reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("pa_technical_v2", llm)

        result = agent.execute({
            "position_info": {...},
            "market_data": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="pa_technical_v2",
        name="technical analyst v2.0",
        description="Analyze the technical aspects of held stocks, including K-line patterns, technical indicators, support and resistance levels",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_stock_market_data_unified"],  # 🔧 Fix: Need to call tools to obtain market data when there is no cache
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="position_info", type="object", description="Position information details", required=False),
            AgentInput(name="market_data", type="object", description="market data", required=False),
        ],
        outputs=[
            AgentOutput(name="technical_analysis", type="string", description="Technical analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["technical_analysis"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # Researcher type
    researcher_type = "position_technical"
    
    # Position (Neutral)
    stance = "neutral"
    
    # Output field name
    output_field = "technical_analysis"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: Position (for technical analysts, always neutral)
            state: Workflow status (optional, used to extract variables)
            
        Returns:
            System prompt word
        """
        # Prepare template variables (if there is state)
        variables = {}
        if state:
            position_info = state.get("position_info", {})
            code = position_info.get("code", "")
            name = position_info.get("name", "N/A")
            market = position_info.get("market", "CN")
            
            from datetime import datetime
            variables = {
                "code": code,
                "name": name,
                "ticker": code,  # Variable names compatible with old templates
                "company_name": name,  # Variable names compatible with old templates
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "market_name": "A shares" if market == "CN" else "Hong Kong stocks" if market == "HK" else "US stocks",
                "market": market,
            }
        
        # Use the general method of the base class to obtain prompt words from the template system (Special Agent for position analysis, refer to research_manager_v2)
        logger.info("🔍 [TechnicalAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="position_analysis_v2",
            agent_name="pa_technical_v2",
            variables=variables,  # 🔧 Fix: Pass prepared variables to template system
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"✅ Obtain technical analyst prompt words from the template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: Use default prompt word
        return """You are a professional technical analyst.

    Your responsibility is to analyze the technical status of the stocks you hold, and refine the trend structure, signal strength and subsequent verification points.

    Analysis points:
    1. Trend Judgment - Which type of structure is currently in an upward/downward/concussive trend?
    2. Technical indicators - MACD/KDJ/RSI and other indicators status and consistency
    3. Momentum and Volatility - Volume, Volatility Levels and Sentiment Changes
    4. Verification signals - technical public signals that need to be followed up in the future
    5. Technical Rating - technical rating on a scale of 1-10

    Strict requirements: It is prohibited to output buying and selling recommendations, specific support and resistance prices, target prices or stop-loss and take-profit.

    Please use Chinese and conduct analysis based on real data."""
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform technical analysis (override base class method to pass state to _build_system_prompt)
        """
        logger.info(f"Start performing technical analysis: {self.agent_id}")

        try:
            # 1. Extract input parameters (compatible with multiple parameter names)
            ticker = state.get("ticker") or state.get("company_of_interest")
            
            # 🆕 Extract code from position_info as ticker
            if not ticker and "position_info" in state:
                position_info = state.get("position_info", {})
                if isinstance(position_info, dict):
                    ticker = position_info.get("code")
            
            # 🆕 Support transaction review scenario: extracted from trade_info code
            if not ticker and "trade_info" in state:
                trade_info = state.get("trade_info", {})
                if isinstance(trade_info, dict):
                    ticker = trade_info.get("code")

            analysis_date = state.get("analysis_date") or state.get("trade_date") or state.get("end_date")
            
            # 🆕 Support transaction review scenario: use the current date as the analysis date
            if not analysis_date:
                from datetime import datetime
                analysis_date = datetime.now().strftime("%Y-%m-%d")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            # 2. Collect required reports
            reports = self._collect_reports(state)
            
            if not reports:
                raise ValueError("No reports available for analysis")
            
            # 🔧 Key fix: Generate preference_id based on cache situation and set to state["context"] in
            # This way both _build_system_prompt and _build_user_prompt will use the same preference_id
            stock_report = state.get("stock_analysis_report", {})
            has_cache = stock_report.get("has_cache", False)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            
            # update state["context"] in preference_id
            context = state.get("context")
            if context:
                if isinstance(context, dict):
                    context = {**context, "preference_id": preference_id}
                else:
                    # If it is an object, create a dictionary wrapper
                    context_dict = {"user_id": getattr(context, "user_id", None)}
                    context_dict["preference_id"] = preference_id
                    context = context_dict
            else:
                context = {"preference_id": preference_id}
            
            # Set the updated context back to state to ensure that subsequent methods can be used
            state["context"] = context
            logger.info(f"🔧 [technical analyst] generated in execute preference_id: {preference_id}")
            
            # 3. Get the historical context from the memory system (if any)
            historical_context = self._get_historical_context(ticker) if self.memory else None
            
            # 4. Build prompt word (pass state to _build_system_prompt)
            system_prompt = self._build_system_prompt(self.stance, state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, reports, historical_context, state)
            
            # 5. Call LLM analysis
            from langchain_core.messages import SystemMessage, HumanMessage
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")
            
            if self._llm:
                # 🔧 Fix: Use invoke_with_tools to support tool calls (tools need to be called to obtain market data when there is no cache)
                if self._langchain_tools:
                    logger.info("🔧 [technical analyst] Tools detected, use invoke_with_tools method")
                    # Prepare analysis prompt words (generate report after tool execution)
                    analysis_prompt = """✅ The tool call has been completed and all required data has been obtained.

🚫 **It is strictly prohibited to call the tool again**

📝 **Please do it now**: 
Based on the real data returned by the above tools, a complete position technical analysis report is directly written according to the previous analysis requirements and output format.

⚠️ **Important reminder**: 
- Do not return any tool calls (tool_calls)
- don t say"I need to call the tool"or"Let me get the data first"
- Directly output Chinese analysis report content

Start writing your report now:"""
                    report_content = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    report = self._parse_response(report_content)
                else:
                    logger.info("🔧 [technical analyst] No tools, call directly LLM")
                    response = self._llm.invoke(messages)
                    report = self._parse_response(response.content)
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Save to memory system (if available)
            if self.memory:
                self._save_to_memory(ticker, report)
            
            # 7. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.researcher_type}_report"

            logger.info(f"technical analyst {self.agent_id} Executed successfully")
            return {
                output_key: report
            }

        except Exception as e:
            logger.error(f"technical analyst {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.researcher_type}_report"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words
        
        Choose different prompt word templates based on whether there is a single stock analysis report cache.
        
        Args:
            ticker: Stock symbol (extracted from position_info)
            analysis_date: Analysis date
            reports: Various types of data (position_info, market_data etc.)
            historical_context: historical context
            state: Current status
            
        Returns:
            User prompt words
        """
        position_info = state.get("position_info", {})
        market_data = state.get("market_data", {})
        stock_report = state.get("stock_analysis_report", {})
        
        code = position_info.get("code", ticker)
        name = position_info.get("name", "N/A")
        
        # Check if there are cached reports
        has_cache = stock_report.get("has_cache", False)
        logger.info(f"🔧 [technical analyst] Check cache status: has_cache={has_cache}, code={code}")
        
        # 🔧 Critical fix: preference_id has been generated and set to state["context"] in
        # Get it directly from context here, make sure to use the same one as _build_system_prompt preference_id
        context = state.get("context")
        if context:
            if isinstance(context, dict):
                preference_id = context.get("preference_id", "neutral")
            else:
                preference_id = getattr(context, "preference_id", "neutral")
        else:
            # Downgrade: if there is no context, use the default value (this should not happen)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            logger.warning(f"⚠️ [technical analyst] context Does not exist, use downgrade preference_id: {preference_id}")
        
        logger.info(f"🔧 [technical analyst] Get from context preference_id: {preference_id}")
        
        # Prepare template variables (supports multiple variable name mappings and is compatible with different templates)
        from datetime import datetime
        cost_price = position_info.get('cost_price', 0)
        current_price = position_info.get('current_price', 0)
        
        variables = {
            # Standard variable name
            "code": code,
            "name": name,
            "ticker": code,  # Variable names compatible with old templates
            "company_name": name,  # Variable names compatible with old templates
            "cost_price": f"{cost_price:.2f}",
            "current_price": f"{current_price:.2f}",
            # 🔧 Fix: unrealized_pnl_pct is already in percentage format (such as 6.05) in the data source and does not need to be used anymore :.2% Format
            "unrealized_pnl_pct": f"{position_info.get('unrealized_pnl_pct', 0):.2f}%",
            "market_data_summary": market_data.get('summary', 'No K line data'),
            "technical_indicators": market_data.get('technical_indicators', 'No technical indicator data'),
            # Date related
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "analysis_date": analysis_date,
            # Price related (extracted from market data, default value used if none)
            "resistance_price": market_data.get('resistance_price', f"{current_price * 1.05:.2f}"),  # Default 5% increase
            "support_price": market_data.get('support_price', f"{current_price * 0.95:.2f}"),  # Default 5% drop
            "secondary_resistance": market_data.get('secondary_resistance', f"{current_price * 1.08:.2f}"),
            "secondary_support": market_data.get('secondary_support', f"{current_price * 0.92:.2f}"),
            # currency symbol
            "currency_symbol": "¥",
            "currency_name": "RMB",
            # RSI Value (extracted from market data, default value used if none)
            "rsi_value": market_data.get('rsi', "50"),
            # Other position information
            "holding_days": position_info.get('holding_days', 0),
            "industry": position_info.get('industry', 'unknown'),
            "quantity": position_info.get('quantity', 0),
            "market_value": f"{position_info.get('market_value', 0):.2f}",
        }
        
        # If there is cache, add market report content (the template will be displayed based on whether there is content)
        if has_cache:
            reports_data = stock_report.get("reports", {})
            market_report_content = reports_data.get("market_report", "")[:2000]
            variables["market_report"] = market_report_content
            variables["has_cache"] = "true"  # Flag bit, the template can use this to judge
            logger.info(f"🔧 [technical analyst] Template variables are ready: market_report exist=True, length={len(market_report_content)}")
        else:
            variables["market_report"] = ""  # Empty string, the template will not display this part
            variables["has_cache"] = "false"
            logger.info("🔧 [technical analyst] Template variables are ready: market_report exist=False")
        
        # Try loading the template from the database (preference_id has been set to the context in the execute method)
        try:
            # Extract context from state (already contains preference_id)
            context = state.get("context") if state else None
            
            logger.info(f"🔧 [technical analyst] Pass preference_id to template system: {preference_id}")

            prompt = self._get_prompt_from_template(
                agent_type="position_analysis_v2",  # Position analysis Agent type v2.0 (consistent with workflow ID)
                agent_name="pa_technical_v2",    # Position Technical Analyst v2.0
                variables=variables,
                context=context,  # context Already included preference_id
                fallback_prompt=None
            )
            if prompt:
                logger.info(f"✅ [technical analyst] Load prompt word template from database (scene: {preference_id}, length: {len(prompt)})")
                if not has_cache:
                    return prompt.rstrip() + _build_market_data_tool_date_guard(code, analysis_date)
                return prompt
        except Exception as e:
            logger.warning(f"⚠️ [technical analyst] Failed to load prompt words from database: {e}, Use demotion prompts")
        
        # Downgrade: Use hardcoded prompt words (select different content based on has_cache)
        if has_cache:
            reports_data = stock_report.get("reports", {})
            market_report = reports_data.get("market_report", "")[:2000]
            return f"""Please conduct position technical analysis based on the following single stock technical analysis report and position information:

=== Single stock technical analysis report (reference)===
{market_report}

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- floating profit and loss: {position_info.get('unrealized_pnl_pct', 0):.2f}%

Please combine the position situation (cost price, profit and loss, etc.) to analyze the technical position perspective:
1. The relationship between the current trend structure and the cost of holding a position
2. Are Momentum, Volume and Volatility Improving or Weakening?
3. Is there consistency between optimism and caution evidence?
4. Technical verification signals that need to be followed up
5. Technical score (1-10 points)

It is prohibited to output buying and selling recommendations, specific support and resistance prices, target prices or stop-loss and take-profit."""
        else:
            return f"""Please analyze the technical aspects of the following stocks:

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- floating profit and loss: {position_info.get('unrealized_pnl_pct', 0):.2f}%

=== market data ===
{market_data.get('summary', 'No K line data')}

=== Technical indicators ===
{market_data.get('technical_indicators', 'No technical indicator data')}

Please write a detailed technical analysis report, including:
1. Trend judgment
2. Technical indicator analysis
3. Momentum and wave states
4. Technical verification signals that need to be followed up
5. Technical score (1-10 points)

It is prohibited to output buying and selling recommendations, specific support and resistance prices, target prices or stop-loss and take-profit.""" + _build_market_data_tool_date_guard(code, analysis_date)

    def _get_required_reports(self) -> List[str]:
        """
        Get the required data list
        
        Returns:
            List of data field names
        """
        return [
            "position_info",
            "market_data"
        ]


# === position.fundamental_analyst_v2 ===
"""
fundamental analyst v2.0 (Position analysis)

Fundamental analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class FundamentalAnalystV2(ResearcherAgent):
    """
    fundamental analyst v2.0 (Position analysis)
    
    Function:
    - Analyze financial data and valuation levels
    - Assess industry status and growth
    - Determine fundamental value
    
    Workflow:
    1. Read position information and fundamental reports
    2. Using LLM to analyze fundamentals
    3. Generate fundamental analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("pa_fundamental_v2", llm)

        result = agent.execute({
            "position_info": {...},
            "stock_analysis_report": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="pa_fundamental_v2",
        name="fundamental analyst v2.0",
        description="Analyze the fundamentals of held stocks, including financial data, valuation levels, and industry status",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # No tools required
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="position_info", type="object", description="Position information details", required=False),
            AgentInput(name="stock_analysis_report", type="object", description="Stock analysis report", required=False),
        ],
        outputs=[
            AgentOutput(name="fundamental_analysis", type="string", description="Fundamental analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["fundamental_analysis"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # Researcher type
    researcher_type = "position_fundamental"
    
    # Position (Neutral)
    stance = "neutral"
    
    # Output field name
    output_field = "fundamental_analysis"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: Position (for fundamental analysts, always neutral)
            state: Workflow status (optional, used to extract variables)
            
        Returns:
            System prompt word
        """
        # Prepare template variables (if there is state)
        variables = {}
        if state:
            position_info = state.get("position_info", {})
            code = position_info.get("code", "")
            name = position_info.get("name", "N/A")
            market = position_info.get("market", "CN")
            
            from datetime import datetime
            variables = {
                "code": code,
                "name": name,
                "ticker": code,  # Variable names compatible with old templates
                "company_name": name,  # Variable names compatible with old templates
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "market_name": "A shares" if market == "CN" else "Hong Kong stocks" if market == "HK" else "US stocks",
                "market": market,
            }
        
        # Obtain prompt words from the template system (Special Agent for position analysis, refer to research_manager_v2)
        logger.info("🔍 [FundamentalAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="position_analysis_v2",
            agent_name="pa_fundamental_v2",
            variables=variables,  # 🔧 Fix: Pass prepared variables to template system
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"✅ Get fundamental analyst prompt words from template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: Use default prompt word
        return """You are a professional fundamental analyst.

    Your responsibility is to analyze the fundamental status of the stocks you hold, and refine the operating quality, valuation matching and subsequent verification key points.

    Analysis points:
    1. Financial Condition - Revenue, Profit, Cash Flow Analysis
    2. Valuation level - PE/PB/PEG and other valuation indicators match the fundamentals
    3. Industry Position - Competitive Advantage and Market Share
    4. Growth potential - future growth potential and conditions for realization
    5. Fundamental Rating - Fundamental Rating on a scale of 1-10

    Strict requirements: It is prohibited to output buying and selling suggestions, suggestions for increasing or decreasing positions, target prices or specific price ranges.

    Please use Chinese and conduct analysis based on real data."""
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform fundamental analysis (override base class method to pass state to _build_system_prompt)
        """
        logger.info(f"Start performing fundamental analysis: {self.agent_id}")

        try:
            # 1. Extract input parameters (compatible with multiple parameter names)
            ticker = state.get("ticker") or state.get("company_of_interest")
            
            # 🆕 Extract code from position_info as ticker
            if not ticker and "position_info" in state:
                position_info = state.get("position_info", {})
                if isinstance(position_info, dict):
                    ticker = position_info.get("code")
            
            # 🆕 Support transaction review scenario: extracted from trade_info code
            if not ticker and "trade_info" in state:
                trade_info = state.get("trade_info", {})
                if isinstance(trade_info, dict):
                    ticker = trade_info.get("code")

            analysis_date = state.get("analysis_date") or state.get("trade_date") or state.get("end_date")
            
            # 🆕 Support transaction review scenario: use the current date as the analysis date
            if not analysis_date:
                from datetime import datetime
                analysis_date = datetime.now().strftime("%Y-%m-%d")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            # 2. Collect required reports
            reports = self._collect_reports(state)
            
            if not reports:
                raise ValueError("No reports available for analysis")
            
            # 🔧 Key fix: Generate preference_id based on cache situation and set to state["context"] in
            # This way both _build_system_prompt and _build_user_prompt will use the same preference_id
            stock_report = state.get("stock_analysis_report", {})
            has_cache = stock_report.get("has_cache", False)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            
            # update state["context"] in preference_id
            context = state.get("context")
            if context:
                if isinstance(context, dict):
                    context = {**context, "preference_id": preference_id}
                else:
                    # If it is an object, create a dictionary wrapper
                    context_dict = {"user_id": getattr(context, "user_id", None)}
                    context_dict["preference_id"] = preference_id
                    context = context_dict
            else:
                context = {"preference_id": preference_id}
            
            # Set the updated context back to state to ensure that subsequent methods can be used
            state["context"] = context
            logger.info(f"🔧 [fundamental analyst] generated in execute preference_id: {preference_id}")
            
            # 3. Get the historical context from the memory system (if any)
            historical_context = self._get_historical_context(ticker) if self.memory else None
            
            # 4. Build prompt word (pass state to _build_system_prompt)
            system_prompt = self._build_system_prompt(self.stance, state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, reports, historical_context, state)
            
            # 5. Call LLM analysis
            from langchain_core.messages import SystemMessage, HumanMessage
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")            
            
            if self._llm:
                # 🔧 Fix: Use invoke_with_tools to support tool calls (tools need to be called to obtain fundamental data when there is no cache)
                if self._langchain_tools:
                    logger.info("🔧 [fundamental analyst] Tools detected, use invoke_with_tools method")
                    # Prepare analysis prompt words (generate report after tool execution)
                    analysis_prompt = """✅ The tool call has been completed and all required data has been obtained.

🚫 **It is strictly prohibited to call the tool again**

📝 **Please do it now**: 
Based on the real data returned by the above tools, a complete position fundamental analysis report is directly written according to the previous analysis requirements and output format.

⚠️ **Important reminder**: 
- Do not return any tool calls (tool_calls)
- don t say"I need to call the tool"or"Let me get the data first"
- Directly output Chinese analysis report content

Start writing your report now:"""
                    report_content = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    report = self._parse_response(report_content)
                else:
                    logger.info("🔧 [fundamental analyst] No tools, call directly LLM")
                    response = self._llm.invoke(messages)
                    report = self._parse_response(response.content)
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Save to memory system (if available)
            if self.memory:
                self._save_to_memory(ticker, report)
            
            # 7. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.researcher_type}_report"

            logger.info(f"fundamental analyst {self.agent_id} Executed successfully")
            return {
                output_key: report
            }

        except Exception as e:
            logger.error(f"fundamental analyst {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.researcher_type}_report"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words
        
        Args:
            ticker: Stock symbol (extracted from position_info)
            analysis_date: Analysis date
            reports: Various types of data (position_info, stock_analysis_report etc.)
            historical_context: historical context
            state: Current status
            
        Returns:
            User prompt words
        """
        position_info = state.get("position_info", {})
        stock_report = state.get("stock_analysis_report", {})
        
        code = position_info.get("code", ticker)
        name = position_info.get("name", "N/A")
        
        # Check if there are cached reports
        has_cache = stock_report.get("has_cache", False)
        logger.info(f"🔧 [fundamental analyst] Check cache status: has_cache={has_cache}, code={code}")
        
        # 🔧 Critical fix: preference_id has been generated and set to state["context"] in
        # Get it directly from context here, make sure to use the same one as _build_system_prompt preference_id
        context = state.get("context")
        if context:
            if isinstance(context, dict):
                preference_id = context.get("preference_id", "neutral")
            else:
                preference_id = getattr(context, "preference_id", "neutral")
        else:
            # Downgrade: if there is no context, use the default value (this should not happen)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            logger.warning(f"⚠️ [fundamental analyst] context Does not exist, use downgrade preference_id: {preference_id}")
        
        logger.info(f"🔧 [fundamental analyst] Get from context preference_id: {preference_id}")
        
        # Prepare template variables (supports multiple variable name mappings and is compatible with different templates)
        from datetime import datetime
        cost_price = position_info.get('cost_price', 0)
        current_price = position_info.get('current_price', 0)
        
        variables = {
            # Standard variable name
            "code": code,
            "name": name,
            "ticker": code,  # Variable names compatible with old templates
            "company_name": name,  # Variable names compatible with old templates
            "industry": position_info.get('industry', 'unknown'),
            "cost_price": f"{cost_price:.2f}",
            "current_price": f"{current_price:.2f}",
            # 🔧 Fix: unrealized_pnl_pct is already in percentage format (such as 6.05) in the data source and does not need to be used anymore :.2% Format
            "unrealized_pnl_pct": f"{position_info.get('unrealized_pnl_pct', 0):.2f}%",
            "holding_days": position_info.get('holding_days', 0),
            # Date related
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "analysis_date": analysis_date,
            # currency symbol
            "currency_symbol": "¥",
            "currency_name": "RMB",
            # Other position information
            "quantity": position_info.get('quantity', 0),
            "market_value": f"{position_info.get('market_value', 0):.2f}",
        }
        
        # If there is cache, add fundamental report content (the template will be displayed based on whether there is content)
        if has_cache:
            reports_data = stock_report.get("reports", {})
            fundamentals_report_content = reports_data.get("fundamentals_report", "")
            variables["fundamentals_report"] = fundamentals_report_content
            variables["has_cache"] = "true"  # Flag bit, the template can use this to judge
            logger.info(f"🔧 [fundamental analyst] Template variables are ready: fundamentals_report exist=True, length={len(fundamentals_report_content)}")
        else:
            variables["fundamentals_report"] = ""  # Empty string, the template will not display this part
            variables["has_cache"] = "false"
            logger.info("🔧 [fundamental analyst] Template variables are ready: fundamentals_report exist=False")
        
        # Try loading the template from the database (preference_id has been set to the context in the execute method)
        try:
            # Extract context from state (already contains preference_id)
            context = state.get("context") if state else None
            
            logger.info(f"🔧 [fundamental analyst] Pass preference_id to template system: {preference_id}")

            prompt = self._get_prompt_from_template(
                agent_type="position_analysis_v2",  # Position analysis Agent type v2.0 (consistent with workflow ID)
                agent_name="pa_fundamental_v2", # Fundamental Analyst v2.0
                variables=variables,
                context=context,  # context Already included preference_id
                fallback_prompt=None
            )
            if prompt:
                logger.info(f"✅ [fundamental analyst] Load prompt word template from database (scene: {preference_id}, length: {len(prompt)})")
                return prompt
        except Exception as e:
            logger.warning(f"⚠️ [fundamental analyst] Failed to load prompt words from database: {e}, Use demotion prompts")
        
        # Downgrade: Use hardcoded prompt words (select different content based on has_cache)
        if has_cache:
            reports_data = stock_report.get("reports", {})
            fundamentals_report = reports_data.get("fundamentals_report", "")
            return f"""Please conduct fundamental analysis of positions based on the following single stock fundamental analysis report and position information:

=== Single stock fundamental analysis report (reference)===
{fundamentals_report}

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- Industry: {position_info.get('industry', 'unknown')}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- Position holding days: {position_info.get('holding_days', 0)} day

Please analyze the fundamentals from a position perspective based on the position situation (cost price, number of days held, etc.):
1. The relationship between the current fundamental status, position cost and position cycle
2. Matching of valuation level with key financial indicators
3. Signs of improvement or weakening in growth and operating quality
4. Public verification signals that need to be tracked
5. Fundamental score (1-10 points)

It is prohibited to output buying and selling suggestions, suggestions for increasing or decreasing positions, target prices or specific price ranges."""
        else:
            return f"""Please analyze the fundamentals of the following stocks:

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- Industry: {position_info.get('industry', 'unknown')}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- Position holding days: {position_info.get('holding_days', 0)} day

Please write a detailed fundamental analysis report, including:
1. financial situation analysis
2. Valuation level assessment
3. Industry status analysis
4. growth judgment
5. Public verification signals that need to be tracked
6. Fundamental score (1-10 points)

It is prohibited to output buying and selling suggestions, suggestions for increasing or decreasing positions, target prices or specific price ranges."""

    def _get_required_reports(self) -> List[str]:
        """
        Get the required data list
        
        Returns:
            List of data field names
        """
        return [
            "position_info",
            "stock_analysis_report"
        ]


# === position.risk_assessor_v2 ===
"""
risk assessor v2.0 (Position analysis)

Risk assessor implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent
from app.utils.compliance import sanitize_position_text_block, sanitize_text_block

logger = logging.getLogger(__name__)


def _summarize_upstream_position_report(value: Any, fallback: str) -> str:
    """Compress upstream technical/fundamental reports to avoid direct transmission of original trigger words into risk warning words."""
    cleaned = sanitize_position_text_block(value, fallback="")
    if not cleaned:
        secondary = sanitize_text_block(value, fallback="")
        cleaned = sanitize_position_text_block(secondary, fallback="") if secondary else ""
    normalized = "；".join(fragment.strip() for fragment in cleaned.splitlines() if fragment.strip())
    normalized = normalized.strip("； ")
    return normalized[:600] if normalized else fallback

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None


@register_agent
class RiskAssessorV2(ResearcherAgent):
    """
    risk assessor v2.0 (Position analysis)

    Function:
    - Assess risk exposure
    - Identify risk scenarios and vulnerabilities
    - Analysis of volatility and key follow-up observations
    
    Workflow:
    1. Read position information, capital information and market data
    2. Use LLM to assess risk
    3. Generate risk assessment report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("pa_risk_v2", llm)

        result = agent.execute({
            "position_info": {...},
            "capital_info": {...},
            "market_data": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="pa_risk_v2",
        name="risk assessor v2.0",
        description="Assess position risk, including risk exposure, risk scenarios and volatility analysis",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # No tools required
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="position_info", type="object", description="Position information details", required=False),
            AgentInput(name="capital_info", type="object", description="Funding information", required=False),
            AgentInput(name="market_data", type="object", description="market data", required=False),
        ],
        outputs=[
            AgentOutput(name="risk_analysis", type="string", description="Risk assessment results"),
        ],
        growth_role="extractor",
        growth_outputs=["risk_analysis"],
        memory_scope_hint="pattern",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # Researcher type
    researcher_type = "position_risk"
    
    # Position (Neutral)
    stance = "neutral"
    
    # Output field name
    output_field = "risk_analysis"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: stance (for risk assessors, always neutral)
            state: Workflow status (optional, used to extract variables)
            
        Returns:
            System prompt word
        """
        # Prepare template variables (if there is state)
        variables = {}
        if state:
            position_info = state.get("position_info", {})
            code = position_info.get("code", "")
            name = position_info.get("name", "N/A")
            market = position_info.get("market", "CN")
            
            from datetime import datetime
            variables = {
                "code": code,
                "name": name,
                "ticker": code,  # Variable names compatible with old templates
                "company_name": name,  # Variable names compatible with old templates
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "market_name": "A shares" if market == "CN" else "Hong Kong stocks" if market == "HK" else "US stocks",
                "market": market,
                # currency symbol
                "currency_symbol": "¥",
                "currency_name": "RMB",
            }

        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [RiskAssessorV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="position_analysis_v2",
            agent_name="pa_risk_v2",
            variables=variables,  # 🔧 Fix: Pass prepared variables to template system
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"✅ Get risk assessor prompt words from template system (length: {len(prompt)})")
            return prompt

        # Downgrade: Use default prompt word
        return """You are a professional risk assessor.

    Your role is to assess the current risk structure, vulnerabilities and risk signals of stock holdings that require ongoing verification.

    Analysis points:
    1. Risk exposure analysis - the impact of current positions on the overall fluctuation of the account
    2. Breakdown of risk sources - technical, fundamental, industry and liquidity risk sources
    3. Risk scenarios - what public changes could weaken research judgments
    4. Volatility Risk - Stock volatility and its impact on the holding experience
    5. Risk Level - Low/Medium/High Risk Rating

    Strict requirements: It is prohibited to output stop loss and take profit, reference price, target price, and position adjustment suggestions.

    Please use Chinese and conduct analysis based on real data."""
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform risk assessment (override base class method to pass state to _build_system_prompt)
        """
        logger.info(f"Start an Executive Risk Assessor: {self.agent_id}")

        try:
            # 1. Extract input parameters (compatible with multiple parameter names)
            ticker = state.get("ticker") or state.get("company_of_interest")
            
            # 🆕 Extract code from position_info as ticker
            if not ticker and "position_info" in state:
                position_info = state.get("position_info", {})
                if isinstance(position_info, dict):
                    ticker = position_info.get("code")
            
            # 🆕 Support transaction review scenario: extracted from trade_info code
            if not ticker and "trade_info" in state:
                trade_info = state.get("trade_info", {})
                if isinstance(trade_info, dict):
                    ticker = trade_info.get("code")

            analysis_date = state.get("analysis_date") or state.get("trade_date") or state.get("end_date")
            
            # 🆕 Support transaction review scenario: use the current date as the analysis date
            if not analysis_date:
                from datetime import datetime
                analysis_date = datetime.now().strftime("%Y-%m-%d")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            # 2. Collect required reports
            reports = self._collect_reports(state)
            
            if not reports:
                raise ValueError("No reports available for analysis")
            
            # 🔧 Key fix: Risk assessors also need to consider caching scenarios (similar to technical and fundamental analysts)
            # Set preference_id to state["context"] , make sure _build_system_prompt and _build_user_prompt use the same preference_id
            stock_report = state.get("stock_analysis_report", {})
            has_cache = stock_report.get("has_cache", False)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            
            # update state["context"] in preference_id
            context = state.get("context")
            if context:
                if isinstance(context, dict):
                    context = {**context, "preference_id": preference_id}
                else:
                    # If it is an object, create a dictionary wrapper
                    context_dict = {"user_id": getattr(context, "user_id", None)}
                    context_dict["preference_id"] = preference_id
                    context = context_dict
            else:
                context = {"preference_id": preference_id}
            
            # Set the updated context back to state to ensure that subsequent methods can be used
            state["context"] = context
            logger.info(f"🔧 [risk assessor] generated in execute preference_id: {preference_id}")
            
            # 3. Get the historical context from the memory system (if any)
            historical_context = self._get_historical_context(ticker) if self.memory else None
            
            # 4. Build prompt word (pass state to _build_system_prompt)
            system_prompt = self._build_system_prompt(self.stance, state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, reports, historical_context, state)
            
            # 5. Call LLM analysis
            from langchain_core.messages import SystemMessage, HumanMessage
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")
            
            if self._llm:
                response = self._llm.invoke(messages)
                report = self._parse_response(response.content)
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Save to memory system (if available)
            if self.memory:
                self._save_to_memory(ticker, report)
            
            # 7. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.researcher_type}_report"

            logger.info(f"risk assessor {self.agent_id} Executed successfully")
            return {
                output_key: report
            }

        except Exception as e:
            logger.error(f"risk assessor {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.researcher_type}_report"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words
        
        Choose different prompt word templates based on whether there is a single stock analysis report cache.
        Simultaneous access to technical and fundamental analysis results (since risk analysis is performed after them)
        
        Args:
            ticker: Stock symbol (extracted from position_info)
            analysis_date: Analysis date
            reports: Various types of data (position_info, capital_info, market_data etc.)
            historical_context: historical context
            state: Current status
            
        Returns:
            User prompt words
        """
        position_info = state.get("position_info", {})
        capital_info = state.get("capital_info", {})
        market_data = state.get("market_data", {})
        stock_report = state.get("stock_analysis_report", {})
        
        # 🔧 New: Access to technical and fundamental analysis results (since risk analysis is performed after them)
        technical_analysis_raw = state.get("technical_analysis", "")
        fundamental_analysis_raw = state.get("fundamental_analysis", "")
        
        # 🔧 Fix: Make sure technical_analysis and fundamental_analysis are string types
        # If they are dictionaries or other types, convert to strings
        if isinstance(technical_analysis_raw, str):
            technical_source = technical_analysis_raw
        elif technical_analysis_raw:
            technical_source = str(technical_analysis_raw)
        else:
            technical_source = ""

        if isinstance(fundamental_analysis_raw, str):
            fundamental_source = fundamental_analysis_raw
        elif fundamental_analysis_raw:
            fundamental_source = str(fundamental_analysis_raw)
        else:
            fundamental_source = ""

        technical_analysis = _summarize_upstream_position_report(
            technical_source,
            fallback="There is still a lack of stable, directly citable research summaries in technology.",
        )
        fundamental_analysis = _summarize_upstream_position_report(
            fundamental_source,
            fallback="Fundamentals currently lacks stable, directly quotable research summaries.",
        )
        
        code = position_info.get("code", ticker)
        name = position_info.get("name", "N/A")
        
        # Check if there are cached reports
        has_cache = stock_report.get("has_cache", False)
        logger.info(f"🔧 [risk assessor] Check cache status: has_cache={has_cache}, code={code}")
        
        # 🔧 Critical fix: preference_id has been generated and set to state["context"] in
        # Get it directly from context here, make sure to use the same one as _build_system_prompt preference_id
        context = state.get("context")
        if context:
            if isinstance(context, dict):
                preference_id = context.get("preference_id", "neutral")
            else:
                preference_id = getattr(context, "preference_id", "neutral")
        else:
            # Downgrade: if there is no context, use the default value (this should not happen)
            user_preference = state.get("user_preference", "neutral")
            cache_scenario = "with_cache" if has_cache else "without_cache"
            preference_id = f"{cache_scenario}_{user_preference}"
            logger.warning(f"⚠️ [risk assessor] context Does not exist, use downgrade preference_id: {preference_id}")
        
        logger.info(f"🔧 [risk assessor] Get from context preference_id: {preference_id}")
        
        # Calculate risk exposure proportion
        market_value = position_info.get("market_value", 0)
        total_assets = capital_info.get("total_assets", 0)
        risk_exposure_ratio = (market_value / total_assets * 100) if total_assets > 0 else 0
        
        # Prepare template variables (supports multiple variable name mappings and is compatible with different templates)
        from datetime import datetime
        # 🔧 Fix: unrealized_pnl_pct is already in percentage format (such as 6.05) in the data source and does not need to be used anymore :.2% Format (will be multiplied by 100 again)
        # should use :.2f Format and add the % sign manually
        unrealized_pnl_pct_raw = position_info.get('unrealized_pnl_pct', 0)
        unrealized_pnl_pct_str = f"{unrealized_pnl_pct_raw:.2f}%" if isinstance(unrealized_pnl_pct_raw, (int, float)) else "0.00%"
        
        # 🔥 Fix: Handle None values, ensure numeric fields are not None
        cost_price_raw = position_info.get('cost_price')
        cost_price = cost_price_raw if cost_price_raw is not None else 0.0
        
        current_price_raw = position_info.get('current_price')
        current_price = current_price_raw if current_price_raw is not None else 0.0
        
        unrealized_pnl_raw = position_info.get('unrealized_pnl')
        unrealized_pnl = unrealized_pnl_raw if unrealized_pnl_raw is not None else 0.0
        
        variables = {
            # Standard variable name
            "code": code,
            "name": name,
            "ticker": code,  # Variable names compatible with old templates
            "company_name": name,  # Variable names compatible with old templates
            "cost_price": f"{cost_price:.2f}",
            "current_price": f"{current_price:.2f}",
            "unrealized_pnl": f"{unrealized_pnl:.2f}",
            "unrealized_pnl_pct": unrealized_pnl_pct_str,
            "market_value": f"{market_value:.2f}",
            "total_assets": f"{total_assets:.2f}",
            "risk_exposure_ratio": f"{risk_exposure_ratio:.2f}",
            "quantity": position_info.get('quantity', 0),
            "volatility": market_data.get('volatility', 'unknown'),
            # Date related
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "analysis_date": analysis_date,
            # currency symbol
            "currency_symbol": "¥",
            "currency_name": "RMB",
            # 🔧 New: Technical and fundamental analysis results (make sure they are strings before slicing)
            # 🔧 Fix: Make slicing operations safe to avoid unhashable type: 'slice' Error
            "technical_analysis": (technical_analysis[:800] if isinstance(technical_analysis, str) and len(technical_analysis) > 800 else technical_analysis) if technical_analysis else "",
            "fundamental_analysis": (fundamental_analysis[:800] if isinstance(fundamental_analysis, str) and len(fundamental_analysis) > 800 else fundamental_analysis) if fundamental_analysis else "",
        }
        
        # If cached, add risk assessor's decision report (risk_management_decision)
        if has_cache:
            reports_data = stock_report.get("reports", {})
            # 🔧 Fix: Use correct field name risk_management_decision (Risk Assessor's Decision Report)
            risk_management_decision = reports_data.get("risk_management_decision", "")
            variables["risk_report"] = risk_management_decision  # Use the risk_report variable name in the template
            variables["risk_management_decision"] = risk_management_decision  # Also provide complete field names
            variables["has_cache"] = "true"
            logger.info(f"🔧 [risk assessor] Template variables are ready: risk_management_decision exist={bool(risk_management_decision)}, length={len(risk_management_decision) if risk_management_decision else 0}")
        else:
            variables["risk_report"] = ""
            variables["risk_management_decision"] = ""
            variables["has_cache"] = "false"
            logger.info("🔧 [risk assessor] Template variables are ready: No cached reports")
        
        # Try loading the template from the database (preference_id has been set to the context in the execute method)
        try:
            # Extract context from state (already contains preference_id)
            context = state.get("context") if state else None
            
            logger.info(f"🔧 [risk assessor] Pass preference_id to template system: {preference_id}")

            prompt = self._get_prompt_from_template(
                agent_type="position_analysis_v2",  # Position analysis Agent type v2.0 (consistent with workflow ID)
                agent_name="pa_risk_v2",    # Position risk assessor v2.0
                variables=variables,
                context=context,  # context Already included preference_id
                fallback_prompt=None
            )
            if prompt:
                logger.info(f"✅ [risk assessor] Load prompt word template from database (scene: {preference_id}, length: {len(prompt)})")
                return prompt
        except Exception as e:
            logger.warning(f"⚠️ [risk assessor] Failed to load prompt words from database: {e}, Use demotion prompts")
        
        # Downgrade: Use hard-coded prompt words (select different content based on has_cache and technical/fundamental analysis results)
        if technical_analysis or fundamental_analysis or has_cache:
            # As long as there is an upstream research summary, it is explicitly included in the downgrade prompt word; the cache risk report is only used as an additional reference
            reports_data = stock_report.get("reports", {})
            risk_report_content = reports_data.get("risk_report", "")
            
            # 🔧 Fix: Slice operation outside f-string to avoid unhashable type: 'slice' Error
            risk_report_section = ""
            if risk_report_content:
                risk_report_text = risk_report_content[:2000] if isinstance(risk_report_content, str) else str(risk_report_content)[:2000]
                risk_report_section = f"""
=== Risk Analysis in Single Stock Analysis Report (Reference)===
{risk_report_text}

"""
            
            # 🔧 Fix: Slicing outside of f-string
            technical_text = (technical_analysis[:800] if isinstance(technical_analysis, str) and len(technical_analysis) > 800 else technical_analysis) if technical_analysis else 'No technical analysis results yet'
            fundamental_text = (fundamental_analysis[:800] if isinstance(fundamental_analysis, str) and len(fundamental_analysis) > 800 else fundamental_analysis) if fundamental_analysis else 'No fundamental analysis results yet'
            
            return f"""Please conduct a position risk assessment based on the risk analysis, technical, fundamental analysis results and position information in the following single stock analysis report:

{risk_report_section}=== Technical analysis results ===
{technical_text}

=== Fundamental analysis results ===
{fundamental_text}

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- Position quantity: {position_info.get('quantity', 0)} shares
- cost price: {cost_price:.2f}
- Current price: {current_price:.2f}
- Position market value: {market_value:.2f}
- floating profit and loss: {unrealized_pnl:.2f} ({unrealized_pnl_pct_str})

=== Funding information ===
- total assets: {total_assets:.2f}
- Risk exposure ratio: {risk_exposure_ratio:.2f}%

Please combine the risk analysis, technical and fundamental analysis results in the single stock analysis report to write a detailed risk assessment report, including:
1. Risk exposure assessment (refer to the risk analysis in the single stock analysis report, combined with position status)
2. Main risk sources and triggering scenarios (explain which public changes require vigilance)
3. Volatility risk analysis (refer to the risk analysis in the single stock analysis report, combined with the position cycle)
4. Risk level assessment (risk analysis, technical aspects, fundamentals and position risks in the comprehensive single stock analysis report, low/medium/high)
5. Follow-up observations (list public signals that need to be followed up)

It is prohibited to output risk control reference prices, profit expected reference prices, stop-loss and take-profit or specific position recommendations."""
        else:
            # No caching or technical/fundamental analysis results
            return f"""Please evaluate the risk of the following positions:

=== Position information ===
- Stock code: {code}
- Stock name: {name}
- Position quantity: {position_info.get('quantity', 0)} shares
- cost price: {cost_price:.2f}
- Current price: {current_price:.2f}
- Position market value: {market_value:.2f}
- floating profit and loss: {unrealized_pnl:.2f} ({unrealized_pnl_pct_str})

=== Funding information ===
- total assets: {total_assets:.2f}
- Risk exposure ratio: {risk_exposure_ratio:.2f}%

=== market data ===
- Volatility: {market_data.get('volatility', 'unknown')}

Please write a detailed risk assessment report, including:
1. Risk exposure assessment
2. Main risk sources and triggering scenarios
3. Volatility Risk Analysis
4. Risk level assessment (low/medium/high)
5. Follow-up observations

It is prohibited to output risk control reference prices, profit expected reference prices, stop-loss and take-profit or specific position recommendations."""

    def _get_required_reports(self) -> List[str]:
        """
        Get the required data list
        
        Returns:
            List of data field names
        """
        return [
            "position_info",
            "capital_info",
            "market_data"
        ]


# === position.action_advisor_v2 ===
"""
Position research integrator v2.0 (Position analysis)

Position research integrator implemented based on ManagerAgent base class
"""

import logging
import re
from typing import Dict, Any, List

from ..manager import ManagerAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent
from app.utils.compliance import sanitize_position_text_block, sanitize_text_block

logger = logging.getLogger(__name__)

_LEGACY_EXECUTION_PROMPT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bstop_loss\b",
        r"\btake_profit\b",
        r"risk_reference(?:_price)?",
        r"profit_reference(?:_price)?",
        r"price_monitoring",
        r"recommended_action",
        r"price analysis range",
        r"Stop loss reference price|first target price|Second target price",
        r"Please give operation suggestions in JSON format",
        r"Operational advisor",
        r"2000-5000 word",
    )
]


def _contains_legacy_execution_prompt_terms(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _LEGACY_EXECUTION_PROMPT_PATTERNS)


def _summarize_position_research_input(value: Any, fallback: str) -> str:
    """Condensate upstream analysis into research summaries that can be used to integrate prompt words."""
    cleaned = sanitize_position_text_block(value, fallback="")
    if not cleaned:
        secondary = sanitize_text_block(value, fallback="")
        cleaned = sanitize_position_text_block(secondary, fallback="") if secondary else ""
    normalized = re.sub(r"\s+", " ", cleaned).strip(" ；")
    return normalized[:600] if normalized else fallback

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class ActionAdvisorV2(ManagerAgent):
    """
    Position research integrator v2.0 (Position analysis)

    Function:
    - Comprehensive technical, fundamental and risk assessment
    - Form position research judgment
    - Summarize risk boundaries and follow-up observations

    Workflow:
    1. Read the analysis results of each dimension
    2. Comprehensive integration using LLM
    3. Generate position research observations
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("pa_advisor_v2", llm)

        result = agent.execute({
            "position_info": {...},
            "technical_analysis": "...",
            "fundamental_analysis": "...",
            "risk_analysis": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="pa_advisor_v2",
        name="Position research integrator v2.0",
        description="Comprehensive analysis of various dimensions to form position research judgments and observations",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # No tools required
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="position_info", type="object", description="Position information details", required=False),
            AgentInput(name="technical_analysis", type="string", description="Technical analysis results", required=False),
            AgentInput(name="fundamental_analysis", type="string", description="Fundamental analysis results", required=False),
            AgentInput(name="risk_analysis", type="string", description="Risk assessment results", required=False),
        ],
        outputs=[
            AgentOutput(name="action_advice", type="string", description="Position Research Observation"),
        ],
        growth_role="optimizer",
        growth_outputs=["action_advice"],
        memory_scope_hint="research_asset",
        review_level="manual_required",
        growth_source_type="manager_decision",
    )

    # manager type
    manager_type = "position_advisor"
    
    # Output field name
    output_field = "action_advice"
    
    # Whether to enable debate (position analysis does not require debate)
    enable_debate = False

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            state: Workflow status (optional, used to extract variables)
        
        Returns:
            System prompt word
        """
        # Prepare template variables (if there is state)
        variables = {}
        if state:
            position_info = state.get("position_info", {})
            code = position_info.get("code", "")
            name = position_info.get("name", "N/A")
            market = position_info.get("market", "CN")
            
            from datetime import datetime
            variables = {
                "code": code,
                "name": name,
                "ticker": code,  # Variable names compatible with old templates
                "company_name": name,  # Variable names compatible with old templates
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "market_name": "A shares" if market == "CN" else "Hong Kong stocks" if market == "HK" else "US stocks",
                "market": market,
                # currency symbol
                "currency_symbol": "¥",
                "currency_name": "RMB",
            }
        
        # Use the base class's general method to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="position_analysis_v2",
            agent_name="pa_advisor_v2",
            variables=variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else state,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )
        if prompt:
            logger.info(f"✅ Obtain the position analyst s prompt words from the template system (length: {len(prompt)})")
            # Check whether the template still has execution semantics remaining
            if "confidence" in prompt.lower():
                logger.info("📊 [ActionAdvisorV2] ✅ The prompt word contains the confidence field requirement")
            else:
                logger.warning("⚠️ [ActionAdvisorV2] ❌ The prompt word does not contain the confidence field requirement!")
            if _contains_legacy_execution_prompt_terms(prompt):
                logger.warning("⚠️ [ActionAdvisorV2] The prompt word still contains executable terms, please check the template content")
            if "observation_factors" in prompt.lower() or "Things to observe" in prompt:
                logger.info("📊 [ActionAdvisorV2] ✅ Prompt word contains observation field requirements")
            else:
                logger.warning("⚠️ [ActionAdvisorV2] ❌ The prompt word does not contain the observation field requirements!")
            
            # Print the last 500 characters of the prompt word (usually required in JSON format here)
            logger.info(f"📊 [ActionAdvisorV2] The last 500 characters of the prompt word:\n{prompt[-500:]}")
            return prompt
        
        # Downgrade: Use default prompt word (compliant version)
        return """You are a professional position research integrator.

Your responsibility is to synthesize technical, fundamental and risk assessment results to form non-executive position research judgments.

Analysis points:
1. Comprehensive research judgment - Which research status is the current position in: strong/neutral/weak/to be verified?
2. Core evidence - the main facts and logic supporting the current judgment
3. Risk Boundary - The current risk sources and scenario changes that deserve the most vigilance
4. Potential Catalyst - Operational, industry or policy factors that could change research judgment
5. Follow-up observations - public signals that need to be continuously verified in the future

Strict requirements:
- It is prohibited to output execution suggestions such as buying, selling, holding, increasing positions, reducing positions, clearing positions, etc.
- It is prohibited to output target price, stop loss and take profit, price range, position ratio, recommended quantity or recommended amount.
- It is prohibited to output any sorting expressions such as ratings, scores, point scales, and confidence scores.
- Prohibited use stand firm  breakthrough  fell below  Increase the volume  shrink  Right intervention  left intervention Wait for hidden transaction triggers.
- Only research judgments, risk tips, catalysts and observations are output.

Please use Chinese and conduct objective analysis based on real data.

Output format requirements:
Please give the position research conclusion in JSON format:
```json
{
    "user_view": {
        "conclusion": "1 2 short sentences in vernacular, directly explaining the current position status, no more than 36 words; no terms such as technical, fundamental, PB, ROE, moving average, MACD, RSI, KDJ etc. shall appear",
        "position_context": "Explain what this position currently means based on the relationship between profit and loss, holding time, cost and current price. It should not exceed 55 words; do not write long sentences in a research style.",
        "key_points": ["Core basis 1, complete short sentences", "Core basis 2, complete short sentences", "Core basis 3, complete short sentences"],
        "risk_focus": ["Risk Tip 1, complete short sentences", "Risk Tip 2, complete short sentences", "Risk Tip 3, complete short sentences"],
        "watch_items": ["Follow-up observation point 1, complete short sentence", "Follow-up observation point 2, complete short sentence", "Follow-up observation point 3, complete short sentences"],
        "uncertainty_note": "One sentence describing what public information verification is still missing, no more than 45 words"
    },
    "analysis_summary": {
        "overall_view": "Comprehensive Research Overview",
        "key_points": ["Key points 1", "Key points 2"]
    },
    "neutral_operation_advice": {
        "recommended_analysis_view": "Stronger|Neutral|Weak|To be verified",
        "confidence": 0-100 an integer (indicating the stability of research judgment, not representing trading certainty), 
        "core_judgment": "The research stage and core judgment of the current position",
        "reasoning": ["Basis 1", "Basis 2"],
        "analysis_points": ["Observation points 1", "Observation points 2"],
        "specific_suggestions": [
            {
                "action": "Continue to follow",
                "reason": "Describe the current public signals that should be tracked with the highest priority"
            }
        ],
        "risk_reminder": "Main risk warning"
    },
    "risk_assessment": "Detailed risk assessment (300-500 words)",
    "opportunity_assessment": "Detailed catalysis and improvement conditions (300-500 words)",
    "specific_plan": {
        "immediate_step": "Facts or disclosures that should be prioritized next",
        "observation_factors": ["Follow-up observations 1", "Follow-up observations 2"]
    }
}
```

**Important tips**: 
1. **user_view It is the user version content that is directly displayed on the front-end main interface. It must be output strictly according to the structure, and the content must not be piled into the conclusion field.** key_points, risk_focus, watch_items Each must be output as a string array independently, and conclusion only contains 1-2 sentences of core judgment.
2. user_view.conclusion and user_view.position_context must be in vernacular Chinese and must not appear technical aspect  Fundamentals  PB  ROE  moving average  MACD  RSI  KDJ  stand firm  breakthrough  support level  resistance level  Right intervention  Increase the volume terms or trigger words
3. user_view.key_points, risk_focus, watch_items Each group has a maximum of 3 entries, and each entry must be a complete short sentence; it is better to write less than to output half sentences, truncated sentences or long paragraphs.
4. key_points Not allowed to write Current judgment is mainly based on disclosed information  Please continue to pay attention  Follow-up key observations Waiting for empty words, you must write down concrete evidence
5. **confidence** The field is required and must be an integer from 0 to 100. It represents the stability of research and judgment, but does not represent the certainty of trading.
6. It is strictly prohibited to output execution content such as adding positions, reducing positions, clearing positions, buying and selling, target price, price range, stop loss and profit, position ratio, etc.
7. Please give a real confidence value based on comprehensive analysis and do not use the default value.
8. specific_suggestions and observation_factors must be public signals, research actions or information verification matters that can be continuously verified and cannot be written as trading actions
9. Output is strictly prohibited Rating  stand firm  breakthrough  Increase the volume  Right intervention will be understood by users as an expression of transaction triggering conditions
10. **user_view The six fields (conclusion, position_context, key_points, risk_focus, watch_items, uncertainty_note) are indispensable and all must be output.** It must be output even if the content is short, and it is prohibited to omit or merge it into other fields.

**Disclaimer**: 
This analysis is only used for research assistance and risk warning, and does not constitute any trading advice or execution instructions."""

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute position analysis view (override base class method in order to pass state to _build_system_prompt)
        """
        logger.info(f"Start executing position analysis point of view expert: {self.agent_id}")

        try:
            # 1. Extract input parameters (compatible with multiple parameter names)
            ticker = state.get("ticker") or state.get("company_of_interest")

            # 🆕 Support transaction review scenario: extracted from trade_info code
            if not ticker and "trade_info" in state:
                trade_info = state.get("trade_info", {})
                if isinstance(trade_info, dict):
                    ticker = trade_info.get("code")
            
            # 🆕 Support position analysis scenario: extracted from position_info code
            if not ticker and "position_info" in state:
                position_info = state.get("position_info", {})
                if isinstance(position_info, dict):
                    ticker = position_info.get("code")

            analysis_date = state.get("analysis_date") or state.get("trade_date") or state.get("end_date")

            # 🆕 Support transaction review scenario: use the current date as the analysis date
            if not analysis_date:
                from datetime import datetime
                analysis_date = datetime.now().strftime("%Y-%m-%d")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            # 2. Gather the required input
            inputs = self._collect_inputs(state)
            
            if not inputs:
                raise ValueError("No inputs available for decision making")
            
            # 🔧 Position research observers only need style preferences (neutral/aggressive/conservative) and do not need to consider caching scenarios.
            # Set preference_id to state["context"] , make sure _build_system_prompt and _build_user_prompt use the same preference_id
            user_preference = state.get("user_preference", "neutral")
            preference_id = user_preference  # Position research observers only need style preferences and do not need to cache scenarios
            
            # update state["context"] in preference_id
            context = state.get("context")
            if context:
                if isinstance(context, dict):
                    context = {**context, "preference_id": preference_id}
                else:
                    # If it is an object, create a dictionary wrapper
                    context_dict = {"user_id": getattr(context, "user_id", None)}
                    context_dict["preference_id"] = preference_id
                    context = context_dict
            else:
                context = {"preference_id": preference_id}
            
            # Set the updated context back to state to ensure that subsequent methods can be used
            state["context"] = context
            logger.info(f"🔧 [Position Research Observer] generated in execute preference_id: {preference_id}")
            
            # 3. If debate is enabled, debate
            if self.enable_debate:
                debate_summary = self._conduct_debate(inputs, state)
            else:
                debate_summary = None
            
            # 4. Build prompt word (pass state to _build_system_prompt)
            system_prompt = self._build_system_prompt(state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, inputs, debate_summary, state)
            
            # 5. Call LLM to make decisions
            from langchain_core.messages import SystemMessage, HumanMessage
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")            
            
            if self._llm:
                logger.info("📊 [ActionAdvisorV2] Call LLM to generate position research observations...")
                
                # Print the user prompt word and check whether it contains JSON format requirements
                logger.info(f"📊 [ActionAdvisorV2] User prompt word length: {len(user_prompt)}")
                logger.info(f"📊 [ActionAdvisorV2] The last 500 characters of the user prompt word:\n{user_prompt[-500:]}")
                if "confidence" in user_prompt.lower():
                    logger.info("📊 [ActionAdvisorV2] ✅ The user prompt word contains the confidence field requirement")
                else:
                    logger.warning("⚠️ [ActionAdvisorV2] ❌ The user prompt word does not contain the confidence field requirement!")
                if _contains_legacy_execution_prompt_terms(user_prompt):
                    logger.warning("⚠️ [ActionAdvisorV2] The user prompt word still contains execution terms, please check the downgrade prompt word")
                if "observation_factors" in user_prompt.lower() or "Things to observe" in user_prompt:
                    logger.info("📊 [ActionAdvisorV2] ✅ The user prompt word contains observation field requirements")
                else:
                    logger.warning("⚠️ [ActionAdvisorV2] ❌ The user prompt word does not contain the observation field requirements!")
                
                response = self._llm.invoke(messages)
                logger.info(f"📊 [ActionAdvisorV2] LLM Response successful, content length: {len(response.content)}")
                logger.info(f"📊 [ActionAdvisorV2] LLM First 500 characters of response: {response.content[:500]}")
                
                decision = self._parse_response(response.content)
                logger.info(f"📊 [ActionAdvisorV2] The parsed decision type: {type(decision)}, Field: {list(decision.keys()) if isinstance(decision, dict) else 'N/A'}")
                
                # Note: decision is{"content": response_string, "success": True}Format
                # confidence The fields are in the JSON of the content string, which will be parsed in portfolio_service.py
                if isinstance(decision, dict) and "content" in decision:
                    content_preview = decision.get("content", "")[:200]
                    logger.info(f"📊 [ActionAdvisorV2] content Preview: {content_preview}")
                    if "confidence" in decision.get("content", "").lower():
                        logger.info("📊 [ActionAdvisorV2] ✅ content may contain a confidence field")
                    else:
                        logger.warning("⚠️ [ActionAdvisorV2] ⚠️ content may not contain the confidence field")
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.manager_type}_decision"
            result = {
                output_key: decision
            }
            
            logger.info(f"📊 [ActionAdvisorV2] Output to state,key: {output_key}")

            # 7. Save debate history (if available)
            if self.enable_debate and hasattr(self, 'debate_history') and self.debate_history:
                result[f"{self.agent_id}_debate_history"] = self.debate_history

            logger.info(f"✅ [ActionAdvisorV2] Position Research Observer {self.agent_id} Executed successfully")
            return result

        except Exception as e:
            logger.error(f"Position Research Observer {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.manager_type}_decision"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, str],
        debate_summary: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words
        
        Args:
            ticker: Stock symbol (extracted from position_info)
            analysis_date: Analysis date
            inputs: Various analysis results (technical_analysis, fundamental_analysis etc.)
            debate_summary: Debate summary (not used in position analysis)
            state: Current status
            
        Returns:
            User prompt words
        """
        position_info = state.get("position_info", {})
        user_goal = state.get("user_goal", {})
        
        code = position_info.get("code", ticker)
        name = position_info.get("name", "N/A")
        
        # 🔧 Position research observers only need style preferences (neutral/aggressive/conservative) and do not need to consider caching scenarios.
        # preference_id Already generated and set to state["context"] in
        # Get it directly from context here, make sure to use the same one as _build_system_prompt preference_id
        context = state.get("context")
        if context:
            if isinstance(context, dict):
                preference_id = context.get("preference_id", "neutral")
            else:
                preference_id = getattr(context, "preference_id", "neutral")
        else:
            # Downgrade: if there is no context, use the default value (this should not happen)
            user_preference = state.get("user_preference", "neutral")
            preference_id = user_preference
            logger.warning(f"⚠️ [Position Research Observer] context Does not exist, use downgrade preference_id: {preference_id}")
        
        logger.info(f"🔧 [Position Research Observer] Get from context preference_id: {preference_id}")
        
        # Extract each dimension for analysis (handling the case where it may be a dictionary)
        def extract_content(value, default: str = "No analysis"):
            """Extract analysis content, supporting dictionary and string formats"""
            if isinstance(value, dict):
                # If it is a dictionary, the content field is extracted first, otherwise the error field is extracted, and finally converted to a string.
                return value.get("content", value.get("error", str(value)))
            elif isinstance(value, str):
                return value
            else:
                return str(value) if value else default
        
        technical_raw = state.get("technical_analysis", "No technical analysis")
        fundamental_raw = state.get("fundamental_analysis", "No fundamental analysis")
        risk_raw = state.get("risk_analysis", "Risk-free review")
        
        # Extract content and limit length
        technical = _summarize_position_research_input(
            extract_content(technical_raw, "No technical analysis"),
            fallback="There is still a lack of stable, directly citable research summaries in technology.",
        )
        fundamental = _summarize_position_research_input(
            extract_content(fundamental_raw, "No fundamental analysis"),
            fallback="Fundamentals currently lacks stable, directly quotable research summaries.",
        )
        risk = _summarize_position_research_input(
            extract_content(risk_raw, "No risk assessment"),
            fallback="There is still a lack of stable, directly citable research summaries on the risk side.",
        )
        
        # Prepare template variables (supports multiple variable name mappings and is compatible with different templates)
        from datetime import datetime
        variables = {
            # Standard variable name
            "code": code,
            "name": name,
            "ticker": code,  # Variable names compatible with old templates
            "company_name": name,  # Variable names compatible with old templates
            "cost_price": f"{position_info.get('cost_price', 0):.2f}",
            "current_price": f"{position_info.get('current_price', 0):.2f}",
            # 🔧 Fix: unrealized_pnl_pct is already in percentage format (such as 6.05) in the data source and does not need to be used anymore :.2% Format
            "unrealized_pnl_pct": f"{position_info.get('unrealized_pnl_pct', 0):.2f}%",
            # Date related
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "analysis_date": analysis_date,
            # currency symbol
            "currency_symbol": "¥",
            "currency_name": "RMB",
            # 🔧 New: Technical, fundamental and risk analysis results
            "technical_analysis": technical[:800] if technical else "",
            "fundamental_analysis": fundamental[:800] if fundamental else "",
            "risk_analysis": risk[:800] if risk else "",
            # User background reference
            "target_return": str(user_goal.get('target_return', 10)),
            "stop_loss": str(user_goal.get('stop_loss', -10)),
        }
        
        # Try loading the template from the database (preference_id has been set to the context in the execute method)
        try:
            # Extract context from state (already contains preference_id)
            context = state.get("context") if state else None
            
            logger.info(f"🔧 [Position Research Observer] Pass preference_id to template system: {preference_id}")

            prompt = self._get_prompt_from_template(
                agent_type="position_analysis_v2",  # Position analysis Agent type v2.0 (consistent with workflow ID)
                agent_name="pa_advisor_v2",    # Position Research Observer v2.0
                variables=variables,
                context=context,  # context Already contains preference_id (only style preference, no caching scenarios)
                fallback_prompt=None
            )
            if prompt:
                logger.info(f"✅ [Position Research Observer] Load prompt word template from database (style: {preference_id}, length: {len(prompt)})")
                return prompt
        except Exception as e:
            logger.warning(f"⚠️ [Position Research Observer] Failed to load prompt words from database: {e}, Use demotion prompts")
        
        # 🆕 Calculate the weight of each dimension analysis (position analysis scenario)
        # In position analysis, the weights of technical, fundamental, and risk reviews can be adjusted according to the position type.
        # Default weighting: technical 40%, fundamental 30%, risk review 30%
        analysis_reports = {
            "technical_analysis": technical,
            "fundamental_analysis": fundamental,
            "risk_analysis": risk,
        }
        
        # Filter out empty reports
        selected_analyses = {
            k: v for k, v in analysis_reports.items()
            if v and isinstance(v, str) and len(v.strip()) > 0
        }
        
        # Weight allocation for position analysis (fixed weight, independent of trading style)
        if len(selected_analyses) == 3:
            # If there are three dimensions, use the default weight
            weights = {
                "technical_analysis": 0.40,   # technical aspect 40%
                "fundamental_analysis": 0.30,  # Fundamentals 30%
                "risk_analysis": 0.30,        # risk review 30%
            }
        elif len(selected_analyses) == 2:
            # If there are only two dimensions, divide them equally
            weights = {k: 0.50 for k in selected_analyses.keys()}
        else:
            # If there is only one dimension, the weight 100%
            weights = {k: 1.0 for k in selected_analyses.keys()}
        
        # Make sure it's a string and limit the length (avoid slicing issues in f-string)
        technical_text = (technical[:800] if isinstance(technical, str) else str(technical)[:800])
        fundamental_text = (fundamental[:800] if isinstance(fundamental, str) else str(fundamental)[:800])
        risk_text = (risk[:800] if isinstance(risk, str) else str(risk)[:800])
        
        # 🆕 Format weighted analysis reports
        analysis_labels = {
            "technical_analysis": "Technical analysis",
            "fundamental_analysis": "fundamental analysis",
            "risk_analysis": "risk review",
        }
        
        # Sort by weight
        sorted_analyses = sorted(
            weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Construct weighted analysis report text
        analysis_parts = []
        for analysis_key, weight in sorted_analyses:
            if analysis_key in selected_analyses:
                label = analysis_labels.get(analysis_key, analysis_key)
                weight_pct = int(weight * 100)
                if analysis_key == "technical_analysis":
                    content = technical_text
                elif analysis_key == "fundamental_analysis":
                    content = fundamental_text
                else:
                    content = risk_text
                analysis_parts.append(f"=== {label} (weight{weight_pct}%, Please pay attention) ===\n{content}\n")
        
        weighted_analyses_text = "\n".join(analysis_parts)
        
        return f"""Please combine the following analysis to form a position research judgment:

=== Position information ===
- stocks: {code} {name}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- floating profit and loss: {position_info.get('unrealized_pnl_pct', 0):.2f}%

{weighted_analyses_text}

**Weight description**: 
- Please focus on high-weighted analyses, which are more important to research judgments
- When making a comprehensive judgment, please give appropriate attention based on the weight.

=== Position background reference ===
- Earnings Expectation Reference: {user_goal.get('target_return', 10)}%
- Tolerable fluctuation reference: {user_goal.get('stop_loss', -10)}%
- The above information is only used to understand the background of the position and no execution suggestions may be output based on it.

Please give the position research conclusion in JSON format:
```json
{{
    "user_view": {{
        "conclusion": "One sentence conclusion, short vernacular sentences",
        "position_context": "Explanation of the impact of holding positions, short sentences in vernacular",
        "key_points": ["Core basis 1, complete short sentences", "Core basis 2, complete short sentences", "Core basis 3, complete short sentences"],
        "risk_focus": ["Risk Tip 1, complete short sentences", "Risk Tip 2, complete short sentences", "Risk Tip 3, complete short sentences"],
        "watch_items": ["Follow-up observation point 1, complete short sentence", "Follow-up observation point 2, complete short sentence", "Follow-up observation point 3, complete short sentences"],
        "uncertainty_note": "Uncertainty explanation, short sentences in vernacular"
    }},
    "analysis_summary": {{
        "overall_view": "Comprehensive Research Overview",
        "key_points": ["Key points 1", "Key points 2"]
    }},
    "neutral_operation_advice": {{
        "recommended_analysis_view": "Stronger|Neutral|Weak|To be verified",
        "confidence": 0-100 an integer (research on the stability of judgment, does not represent trading certainty), 
        "core_judgment": "The research stage and core judgment of the current position",
        "reasoning": ["Reason 1", "Reason 2"],
        "analysis_points": ["Analysis points 1", "Analysis points 2"],
        "specific_suggestions": [
            {{
                "action": "Continue to follow",
                "reason": "Describe the current public signals that should be tracked with the highest priority"
            }}
        ],
        "risk_reminder": "Main risk warning"
    }},
    "risk_assessment": "Detailed risk review",
    "opportunity_assessment": "Detailed catalysis and improvement conditions",
    "specific_plan": {{
        "immediate_step": "Facts or disclosures that should be prioritized next",
        "observation_factors": ["Follow-up observations 1", "Follow-up observations 2"]
    }}
}}
```

**Important tips**: 
1. **user_view It is the user version content that is directly displayed on the front-end main interface. It must be output strictly according to the structure, and the content must not be piled into the conclusion field.** key_points, risk_focus, watch_items Each must be output as a string array independently, and conclusion only contains 1-2 sentences of core judgment.
2. user_view.conclusion and user_view.position_context must be in vernacular Chinese and must not appear technical aspect  Fundamentals  PB  ROE  moving average  MACD  RSI  KDJ  stand firm  breakthrough  support level  resistance level  Right intervention  Increase the volume terms or trigger words
3. user_view.key_points, risk_focus, watch_items Each group has a maximum of 3 entries, and each entry must be a complete short sentence; it is better to write less than to output half sentences, truncated sentences or long paragraphs.
4. If a piece of content ends with will  let  get  and  But  with  or  rule  Need Ending with etc means the sentence is incomplete and must be rewritten and cannot be output directly.
5. key_points Not allowed to write Current judgment is mainly based on disclosed information  Please continue to pay attention  Follow-up key observations Waiting for empty words, you must write down concrete evidence
6. **confidence** The field is required and must be an integer from 0 to 100. It represents the stability of research and judgment, but does not represent the certainty of trading.
7. It is strictly prohibited to output execution content such as adding positions, reducing positions, clearing positions, buying and selling, target price, price range, stop loss and profit, position ratio, etc.
8. Please give a real confidence value based on comprehensive analysis and do not use the default value.
9. specific_suggestions and observation_factors must be public signals, research actions or information verification matters that can be continuously verified and cannot be written as trading actions
10. Output is strictly prohibited Rating  stand firm  breakthrough  Increase the volume  Right intervention will be understood by users as an expression of transaction triggering conditions
11. **user_view The six fields (conclusion, position_context, key_points, risk_focus, watch_items, uncertainty_note) are indispensable and all must be output.** It must be output even if the content is short, and it is prohibited to omit or merge it into other fields."""

    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list
        
        Returns:
            Enter a list of field names
        """
        return [
            "technical_analysis",
            "fundamental_analysis",
            "risk_analysis"
        ]
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response (uses base class default implementation, returns raw text)
        
        Args:
            response: LLM response text
            
        Returns:
            A dictionary containing content fields
        """
        # Use the base class default implementation, returning raw text (let portfolio_service.py take care of JSON parsing)
        # This maintains backward compatibility and does not break existing logic
        return {
            "content": response,
            "success": True
        }


_self_mod = _sys.modules[__name__]
for _sub in ['position.technical_analyst_v2', 'position.fundamental_analyst_v2', 'position.risk_assessor_v2', 'position.action_advisor_v2']:
    _sys.modules[f"core.agents.adapters.{_sub}"] = _self_mod
"""
technical analyst v2.0 (Position analysis)

Technical analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ...researcher import ResearcherAgent
from ...config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ...registry import register_agent

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
                    logger.info(f"🔧 [technical analyst] Tools detected, use invoke_with_tools method")
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
                    logger.info(f"🔧 [technical analyst] No tools, call directly LLM")
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
            logger.info(f"🔧 [technical analyst] Template variables are ready: market_report exist=False")
        
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


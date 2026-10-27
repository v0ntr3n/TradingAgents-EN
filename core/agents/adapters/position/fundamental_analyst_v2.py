"""
fundamental analyst v2.0 (Position analysis)

Fundamental analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ...researcher import ResearcherAgent
from ...config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ...registry import register_agent

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
                    logger.info(f"🔧 [fundamental analyst] Tools detected, use invoke_with_tools method")
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
                    logger.info(f"🔧 [fundamental analyst] No tools, call directly LLM")
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
            logger.info(f"🔧 [fundamental analyst] Template variables are ready: fundamentals_report exist=False")
        
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


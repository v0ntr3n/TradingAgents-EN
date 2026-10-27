"""
risk assessor v2.0 (Position analysis)

Risk assessor implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ...researcher import ResearcherAgent
from ...config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ...registry import register_agent
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
            logger.info(f"🔧 [risk assessor] Template variables are ready: No cached reports")
        
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


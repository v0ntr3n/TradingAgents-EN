"""
Research IntegratorAgent base class

Used to implement the research integrator Agent (outputs a summary of research observations and does not constitute investment advice)
v2.0 New: configuration-based research integrator Agent architecture
"""

import logging
import json
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .base import BaseAgent
from .config import AgentMetadata, AgentCategory

logger = logging.getLogger(__name__)


def _stringify_trading_plan(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    return str(value)


class TraderAgent(BaseAgent):
    """
    Research IntegratorAgent base class
    
    Working mode: Read decisions → Generate summary of research observations
    
    Features:
    - Do not call tools
    - Depends on the output of all pre-order Agents
    - Requires memory system (historical research records)
    - Output format: Summary of research observations
    
    Workflow:
    1. Read research plans and all analysis reports from state
    2. Generate study observation summaries using LLM
    3. Output research observation summary
    4. Output to state["trading_plan"]
    
    Subclasses need to implement:
    - _build_system_prompt(): Build system prompt words
    - _build_user_prompt(): Build user prompt words
    """
    
    # Output field name (subclass definition)
    output_field: str = "trading_plan"
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        memory: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize research integrator Agent
        
        Args:
            config: Agent Configuration
            llm: LLM Example
            memory: Examples of memory systems (for historical research records)
            **kwargs: Other parameters
        """
        super().__init__(config=config, llm=llm, **kwargs)
        
        self.memory = memory
        
        logger.debug(f"TraderAgent '{self.agent_id}' Initialization completed")
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform research integration analysis
        
        Args:
            state: Workflow status dictionary, including:
                - ticker: Stock code
                - analysis_date: Analysis date
                - investment_plan: Comprehensive research conclusion
                - market_report: Market analysis report (optional)
                - news_report: News analysis report (optional)
                - Other reports...
                
        Returns:
            Updated status dictionary with summary of research observations
        """
        logger.info(f"Start an Executive Research Integrator Agent: {self.agent_id}")
        
        try:
            # 1. Extract input parameters (unified use of base class methods, compatible with various field names and scenarios)
            ticker, analysis_date = self._extract_common_params(state)

            investment_plan = state.get("investment_plan")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            if not investment_plan:
                raise ValueError("Missing investment_plan")
            
            # 2. Collect all relevant reports
            all_reports = self._collect_all_reports(state)
            
            # 3. Get historical transaction records from the memory system (if any)
            historical_trades = self._get_historical_trades(ticker) if self.memory else None
            
            # 4. Build prompt words
            system_prompt = self._build_system_prompt(state=state)
            user_prompt = self._build_user_prompt(
                ticker, 
                analysis_date, 
                investment_plan, 
                all_reports,
                historical_trades,
                state
            )
            
            # 5. Call LLM to generate a transaction analysis plan
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")
            # 🔍 Debug log: print prompt word length
            logger.info(f"🔍 [TraderAgent] System prompt word length: {len(system_prompt)}")
            logger.info(f"🔍 [TraderAgent] User prompt word length: {len(user_prompt)}")
            logger.info(f"🔍 [TraderAgent] The first 500 characters of the user prompt word:\n{user_prompt[:500]}")

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                self._last_llm_response = response  # P1: stash For subcategory collection token_usage

                # 🔍 Debug log: print LLM response
                logger.info(f"🔍 [TraderAgent] LLM response length: {len(response.content)}")
                logger.info(f"🔍 [TraderAgent] LLM Response content:\n{response.content}")

                trading_plan = self._parse_response(response.content)

                # 🔍 Debug log: print the parsed transaction analysis plan
                logger.info(f"🔍 [TraderAgent] Parsed Transaction Analysis Plan Type: {type(trading_plan)}")
                if isinstance(trading_plan, dict):
                    logger.info(f"🔍 [TraderAgent] Transaction Analysis Plan Fields: {list(trading_plan.keys())}")
                    if 'content' in trading_plan:
                        logger.info(f"🔍 [TraderAgent] Transaction Analysis Plan Content Length: {len(str(trading_plan['content']))}")
            else:
                raise ValueError("LLM not initialized")

            # 6. Save to memory system (if available)
            if self.memory:
                self._save_to_memory(ticker, trading_plan)

            # 7. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            logger.info(f"✅ [TraderAgent] {self.agent_id} Successful execution, output field: {self.output_field}")
            return {
                self.output_field: trading_plan
            }

        except Exception as e:
            logger.error(f"research integrator Agent {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            return {
                self.output_field: {
                    "error": str(e),
                    "success": False
                }
            }
    
    def _collect_all_reports(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect all relevant reports
        
        Args:
            state: Workflow status
            
        Returns:
            report dictionary
        """
        report_keys = [
            "market_report",
            "news_report",
            "fundamentals_report",
            "sentiment_report",
            "sector_report",
            "index_report",
            "bull_report",
            "bear_report",
            "risk_assessment"
        ]
        
        reports = {}
        for key in report_keys:
            if key in state:
                reports[key] = state[key]

        if "sentiment_report" not in reports and "social_report" in state:
            reports["sentiment_report"] = state["social_report"]

        return reports

    def _get_historical_trades(self, ticker: str) -> Optional[List[Dict[str, Any]]]:
        """
        Obtain historical transaction records from the memory system

        Args:
            ticker: Stock code

        Returns:
            Historical transaction list
        """
        if not self.memory:
            return None

        try:
            query = f"Stock code: {ticker}\n Transaction Analysis Plan\n Historical trading experience"

            if not hasattr(self.memory, 'search_memories'):
                logger.warning("Memory instances do not support search_memories and historical transaction recall has been skipped: %s", type(self.memory).__name__)
                return None

            memories = self.memory.search_memories(
                query=query,
                n_results=3,
                filter_metadata={"ticker": ticker} if ticker else None,
            )
            return [
                {
                    "content": item.get("content", ""),
                    "metadata": item.get("metadata", {}),
                    "similarity": item.get("similarity", 0.0),
                }
                for item in (memories or [])
            ]

            return None
        except Exception as e:
            logger.warning(f"Failed to obtain historical transaction records: {e}")
            return None

    def _save_to_memory(self, ticker: str, trading_plan: Dict[str, Any]) -> None:
        """
        Save to memory system

        Args:
            ticker: Stock code
            trading_plan: Transaction Analysis Plan
        """
        if not self.memory:
            return

        try:
            content = _stringify_trading_plan(trading_plan)

            if not hasattr(self.memory, 'add_memory'):
                logger.warning("Memory instances do not support add_memory and transaction plan saving has been skipped: %s", type(self.memory).__name__)
                return

            metadata = {
                "ticker": ticker,
                "agent_id": self.agent_id,
                "output_field": self.output_field,
                "memory_kind": "trader_plan",
                "source": "trader_agent_runtime",
            }
            self.memory.add_memory(content=content, metadata=metadata)
        except Exception as e:
            logger.warning(f"Failed to save to memory system: {e}")

    @abstractmethod
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (subclass implementation)

        Args:
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)

        Returns:
            System prompt word
        """
        pass

    @abstractmethod
    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        investment_plan: Dict[str, Any],
        all_reports: Dict[str, Any],
        historical_trades: Optional[List[Dict[str, Any]]],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (subclass implementation)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            investment_plan: investment plan
            all_reports: All report dictionaries
            historical_trades: Historical transaction records
            state: Workflow status

        Returns:
            User prompt words
        """
        pass

    # Note:_get_prompt_from_template() Method has been moved to BaseAgent base class, shared by all Agents

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response (can be overridden by subclasses)

        Args:
            response: LLM response text

        Returns:
            Parsed Transaction Analysis Plan Dictionary
        """
        # 🔍 debug log
        logger.info(f"🔍 [TraderAgent._parse_response] Start parsing the response")
        logger.info(f"🔍 [TraderAgent._parse_response] response length: {len(response)}")

        # Default implementation: return text directly
        result = {
            "content": response,
            "success": True
        }

        logger.info(f"🔍 [TraderAgent._parse_response] The parsing is completed and the dictionary is returned.")
        return result

    @property
    def agent_id(self) -> str:
        """get Agent ID"""
        if self.metadata:
            return self.metadata.id
        return self.__class__.__name__.lower()


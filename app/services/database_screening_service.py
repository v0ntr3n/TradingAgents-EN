"""
Stock screening service based on MongoDB
Use basic stock information in local databases for efficient screening
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.core.database import get_mongo_db
from core.skill_runtime.fundamental_factors import (
    _build_factor_diagnostics,
    _build_growth_factor_warnings,
    _build_quality_factor_warnings,
    _build_value_factor_warnings,
    _compute_cagr,
    _compute_yoy_growth,
    _estimate_altman_z_score,
    _estimate_beneish_m_score,
    _estimate_interest_coverage,
    _estimate_piotroski_f_score,
    _estimate_roic,
)
# from app.models.screening import ScreeningCondition  # Avoid circular imports

logger = logging.getLogger(__name__)


class DatabaseScreeningService:
    """基于数据库的股票筛选服务"""
    
    def __init__(self):
        # Use views instead of basic information tables. The views already contain real-time market data.
        self.collection_name = "stock_screening_view"
        
        # Supported basic information field mapping
        self.basic_fields = {
            # Basic information
            "code": "code",
            "name": "name", 
            "industry": "industry",
            "area": "area",
            "market": "market",
            "list_date": "list_date",
            
            # Market capitalization information (billion)
            "total_mv": "total_mv",      # Total market capitalization
            "circ_mv": "circ_mv",        # Circulation market value
            "market_cap": "total_mv",    # market capitalization alias

            # financial indicators
            "pe": "pe",                  # P/E ratio
            "pb": "pb",                  # price to book ratio
            "pe_ttm": "pe_ttm",         # rolling price to earnings ratio
            "ps_ttm": "ps_ttm",         # rolling price-to-sales ratio
            "pb_mrq": "pb_mrq",         # Latest price-to-book ratio
            "roe": "roe",                # Return on equity (latest period)
            "roa": "roa",                # return on total assets
            "gross_margin": "gross_margin",          # Gross profit margin
            "netprofit_margin": "netprofit_margin",  # net profit margin
            "revenue_ttm": "revenue_ttm",            # rolling revenue
            "net_profit_ttm": "net_profit_ttm",      # rolling net profit
            "n_cashflow_act": "n_cashflow_act",      # Net operating cash flow
            "revenue_yoy": "revenue_yoy",            # Year-on-year revenue (%)
            "net_profit_yoy": "net_profit_yoy",      # Net profit year-on-year (%)
            "oper_profit_yoy": "oper_profit_yoy",    # Operating profit year-on-year (%)
            "peg": "peg",                            # PEG
            "roic": "roic",                          # ROIC (%)
            "cash_conversion": "cash_conversion",    # Profit to cash conversion rate
            "accrual_ratio": "accrual_ratio",        # accruals ratio (%)
            "asset_turnover": "asset_turnover",      # asset turnover rate
            "gross_profit_to_assets": "gross_profit_to_assets",  # Gross profit/total assets (%)
            "interest_coverage": "interest_coverage",  # interest coverage ratio
            "inventory_turnover": "inventory_turnover",  # Inventory turnover
            "receivable_turnover": "receivable_turnover",  # Accounts receivable turnover ratio
            "net_cash_position": "net_cash_position",  # Net Cash Position Proxy (%)
            "fcf": "fcf",                            # free cash flow
            "fcf_yield": "fcf_yield",                # free cash flow yield (%)
            "fcf_margin": "fcf_margin",              # free cash flow rate (%)
            "ocf_yield": "ocf_yield",                # operating cash flow yield (%)
            "revenue_cagr_3y": "revenue_cagr_3y",    # Three-year revenue compound growth rate (%)
            "profit_cagr_3y": "profit_cagr_3y",      # Three-year profit compound growth rate (%)
            "working_capital_change": "working_capital_change",  # working capital changes (billion)

            # trading indicators
            "turnover_rate": "turnover_rate",  # turnover rate%
            "volume_ratio": "volume_ratio",    # Quantity ratio

            # Technical indicators (from technical snapshot materialized collection)
            "ma20": "ma20",
            "rsi14": "rsi14",
            "kdj_k": "kdj_k",
            "kdj_d": "kdj_d",
            "kdj_j": "kdj_j",
            "dif": "dif",
            "dea": "dea",
            "macd_hist": "macd_hist",

            # Extended financial metrics (calculated fields from stock_screening_view)
            "debt_to_assets": "debt_to_assets",      # Asset-liability ratio (%)
            "assets_to_eqt": "assets_to_eqt",        # equity multiplier
            "current_ratio": "current_ratio",        # current ratio
            "quick_ratio": "quick_ratio",            # quick ratio
            "cash_ratio": "cash_ratio",              # cash ratio
            "dividend_yield": "dividend_yield",      # dividend yield (%)
            "net_working_capital": "net_working_capital",  # net working capital (billion)
            "is_st": "is_st",                        # Whether ST shares (True/False)
            "report_period": "report_period",        # Latest financial reporting period

            # Search keywords (virtual fields)
            "keyword": "keyword",

            # Real-time market quotation field (requires related query from market_quotes)
            "pct_chg": "pct_chg",              # Increase or decrease%
            "amount": "amount",                # Transaction volume (10,000 yuan)
            "close": "close",                  # closing price
            "volume": "volume",                # Volume
        }
        
        # Supported operators
        self.operators = {
            ">": "$gt",
            "<": "$lt", 
            ">=": "$gte",
            "<=": "$lte",
            "==": "$eq",
            "!=": "$ne",
            "between": "$between",  # Custom processing
            "in": "$in",
            "not_in": "$nin",
            "contains": "$regex",   # string contains
        }
    
    async def can_handle_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
        """
        Check if these conditions can be handled entirely by database filtering
        
        Args:
            conditions: filter list
            
        Returns:
            bool: can it be processed
        """
        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
            
            # Check if the field supports
            if field not in self.basic_fields:
                logger.debug(f"字段 {field} 不支持数据库筛选")
                return False
            
            # Check if the operator is supported
            if operator not in self.operators:
                logger.debug(f"操作符 {operator} 不支持数据库筛选")
                return False
        
        return True
    
    async def screen_stocks(
        self,
        conditions: List[Dict[str, Any]],
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[List[Dict[str, str]]] = None,
        source: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Stock screening based on database (two stages: basic screening → Market filtering)

        Args:
            conditions: filter list
            limit: Return quantity limit
            offset: offset
            order_by: Sorting conditions [{"field": "total_mv", "direction": "desc"}]
            source: Data source (optional), the data source with the highest priority is used by default

        Returns:
            Tuple[List[Dict], int]: (Filter results, total quantity)
        """
        try:
            db = get_mongo_db()

            if not source:
                from app.core.data_source_priority import get_preferred_data_source_async
                source = await get_preferred_data_source_async(market_category="a_shares")
                logger.info(f"✅ [database_screening] final data source used: {source}")

            # Separate basic conditions and market conditions
            basic_conditions, quote_conditions = self._separate_conditions(conditions)

            # Build a basic query (only including non-quote fields)
            query = await self._build_query(basic_conditions)
            query["source"] = source

            # Build sorting criteria
            sort_conditions = self._build_sort_conditions(order_by)

            logger.info(f"📋 基础查询条件: {query}")
            logger.info(f"📋 行情筛选条件: {quote_conditions}")
            logger.info(f"📋 排序条件: {sort_conditions}")

            has_real_conditions = any(k != "source" for k in query)
            has_quote_conditions = len(quote_conditions) > 0

            # Fast path: no basic filtering + No market filtering → Check directly stock_basic_info
            if not has_real_conditions and not has_quote_conditions:
                logger.info("⚡ Use the fast path: direct query stock_basic_info")
                results, total_count = await self._query_basic_info_directly(
                    db, source, sort_conditions, limit, offset
                )
                codes = [r.get("code") for r in results if r.get("code")]
                if codes:
                    await self._enrich_with_quote_data(results, codes)
                return results, total_count

            # When there are market conditions, two stages of screening are required:
            # Stage 1 — Basic filter (stock_basic_info or view)
            if has_quote_conditions:
                # When filtering the market, first take the basic results (take more for secondary filtering)
                phase1_limit = min(max(limit * 20, 2000), 10000)
                logger.info(f"📋 第 1 阶段取 {phase1_limit} 条候选用于行情过滤")
            else:
                phase1_limit = limit

            # Decide whether to use a view or stock_basic_info
            # ⚠️ Performance fix: Disable use of stock_screening_view view
            # This view passes $lookup Relate market_quotes and stock_financial_periods,
            # Even count_documents triggers the entire aggregation pipeline, causing the query to timeout (>30s) . 
            # Subsequent _enrich_with_financial_data and _enrich_with_quote_data have
            # Use batch $in Query implements the same data enrichment function without going through views.
            if has_real_conditions:
                collection = db["stock_basic_info"]
                total_count = await collection.count_documents(query)
            else:
                collection = db["stock_basic_info"]
                total_count = min(phase1_limit + offset + 1000, 10000)

            cursor = collection.find(query)
            if sort_conditions:
                cursor = cursor.sort(sort_conditions)
            if not has_quote_conditions:
                cursor = cursor.skip(offset)
            cursor = cursor.limit(phase1_limit)

            results = []
            codes = []
            async for doc in cursor:
                result = self._format_result(doc)
                results.append(result)
                codes.append(doc.get("code"))

            # Supplement financial data in batches
            if codes:
                await self._enrich_with_financial_data(results, codes)

            # Supplement market data in batches (guarantee close/pct_chg can always be displayed)
            if codes:
                await self._enrich_with_quote_data(results, codes)

            # Stage 2 — Market conditions filter
            if has_quote_conditions:
                results = self._apply_quote_filter(results, quote_conditions)
                total_count = len(results)
                # The sorting field may be a quotation field and needs to be reordered in memory.
                if order_by:
                    sort_field = order_by[0].get("field", "total_mv")
                    sort_dir = order_by[0].get("direction", "desc")
                    reverse = sort_dir.lower() == "desc"
                    results.sort(
                        key=lambda x: x.get(sort_field) if isinstance(x.get(sort_field), (int, float)) else float("-inf"),
                        reverse=reverse,
                    )
                results = results[offset:offset + limit]

            logger.info(f"✅ 数据库筛选完成: 总数={total_count}, 返回={len(results)}, 数据源={source}")
            return results, total_count

        except Exception as e:
            logger.error(f"❌ 数据库筛选失败: {e}")
            raise Exception(f"数据库筛选失败: {str(e)}")
    
    async def _query_basic_info_directly(
        self,
        db,
        source: str,
        sort_conditions: List[Tuple[str, int]],
        limit: int,
        offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query stock_basic_info directly to avoid the aggregation pipeline overhead of the view
        
        This is for simple queries (only source + sorting) optimization path
        """
        try:
            basic_info_collection = db["stock_basic_info"]
            
            # Build query conditions (source only)
            query = {"source": source}
            
            # Execute query (using index)
            cursor = basic_info_collection.find(query)
            
            # Apply sorting (using composite index)
            if sort_conditions:
                cursor = cursor.sort(sort_conditions)
            
            # Apply paging
            cursor = cursor.skip(offset).limit(limit)
            
            # Get results
            results = []
            codes = []
            async for doc in cursor:
                # Use a unified formatting method to ensure consistent formatting
                result = self._format_result(doc)
                results.append(result)
                codes.append(doc.get("code"))
            
            # Batch query financial data (ROE, etc.)
            if codes:
                await self._enrich_with_financial_data(results, codes)
            
            # Estimate totals (avoid count_documents)
            total_count = min(limit + offset + 1000, 10000)
            
            logger.info(f"✅ 快速路径查询完成: 返回={len(results)}, 数据源={source}")
            
            return results, total_count
            
        except Exception as e:
            logger.error(f"❌ 快速路径查询失败: {e}")
            raise
    
    async def _build_query(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build MongoDB query conditions"""
        query = {}

        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
            value = condition.get("value") if isinstance(condition, dict) else condition.value

            logger.info(f"🔍 [_build_query] Processing conditions: field={field}, operator={operator}, value={value}")

            # Special handling of keyword fields
            if field == "keyword":
                query["$or"] = [
                    {"code": {"$regex": str(value), "$options": "i"}},
                    {"name": {"$regex": str(value), "$options": "i"}},
                    {"symbol": {"$regex": str(value), "$options": "i"}}
                ]
                continue

            # Mapping field name
            db_field = self.basic_fields.get(field)
            if not db_field:
                continue
            
            # Handle special operators
            if operator == "between":
                # between The operation requires two values
                if isinstance(value, list) and len(value) == 2:
                    query[db_field] = {
                        "$gte": value[0],
                        "$lte": value[1]
                    }
            elif operator == "contains":
                # String contains (case insensitive)
                query[db_field] = {
                    "$regex": str(value),
                    "$options": "i"
                }
            elif operator in self.operators:
                # Standard operators
                mongo_op = self.operators[operator]
                query[db_field] = {mongo_op: value}
            
        return query
    
    def _build_sort_conditions(self, order_by: Optional[List[Dict[str, str]]]) -> List[Tuple[str, int]]:
        """构建排序条件"""
        if not order_by:
            # Sort by total market capitalization in descending order by default
            return [("total_mv", -1)]
        
        sort_conditions = []
        for order in order_by:
            field = order.get("field")
            direction = order.get("direction", "desc")
            
            # Mapping field name
            db_field = self.basic_fields.get(field)
            if not db_field:
                continue
            
            # Mapping sort direction
            sort_direction = -1 if direction.lower() == "desc" else 1
            sort_conditions.append((db_field, sort_direction))
        
        return sort_conditions
    
    async def _enrich_with_financial_data(self, results: List[Dict[str, Any]], codes: List[str]) -> None:
        """
        Query financial data in batches and populate the results

        Args:
            results: Filter the results list
            codes: Stock code list
        """
        try:
            db = get_mongo_db()
            financial_collection = db['stock_financial_periods']
            basic_info_collection = db['stock_basic_info']

            # 🔥 Use unified data source priority management functions
            from app.core.data_source_priority import get_preferred_data_source_async
            preferred_source = await get_preferred_data_source_async(market_category="a_shares")
            basic_info_map: Dict[str, Dict[str, Any]] = {}
            basic_info_cursor = basic_info_collection.find(
                {"code": {"$in": codes}, "source": preferred_source},
                {
                    "_id": 0,
                    "code": 1,
                    "source": 1,
                    "pe": 1,
                    "pe_ttm": 1,
                    "pb": 1,
                    "pb_mrq": 1,
                    "ps": 1,
                    "ps_ttm": 1,
                    "dividend_yield": 1,
                    "total_mv": 1,
                    "market_cap": 1,
                },
            )
            async for basic_info_doc in basic_info_cursor:
                basic_info_map[basic_info_doc.get("code")] = basic_info_doc

            def build_snapshot_record(snapshot: Dict[str, Any]) -> Dict[str, Any]:
                raw_balance = snapshot.get("raw_balance_sheet") or {}
                raw_income = snapshot.get("raw_income_statement") or {}
                raw_cashflow = snapshot.get("raw_cashflow_statement") or {}
                raw_indicators = snapshot.get("raw_financial_indicators") or {}
                return {
                    "report_period": snapshot.get("report_period"),
                    "revenue_ttm": snapshot.get("revenue_ttm"),
                    "revenue": snapshot.get("revenue"),
                    "oper_rev": snapshot.get("oper_rev"),
                    "net_profit_ttm": snapshot.get("net_profit_ttm"),
                    "net_profit": snapshot.get("net_profit"),
                    "net_income": snapshot.get("net_income"),
                    "total_profit": snapshot.get("total_profit"),
                    "oper_profit": snapshot.get("oper_profit"),
                    "operating_profit": snapshot.get("operating_profit"),
                    "ebit": snapshot.get("ebit"),
                    "oper_cost": snapshot.get("oper_cost"),
                    "oper_exp": snapshot.get("oper_exp"),
                    "admin_exp": snapshot.get("admin_exp"),
                    "rd_exp": snapshot.get("rd_exp"),
                    "fin_exp": snapshot.get("fin_exp"),
                    "roe": snapshot.get("roe"),
                    "roa": snapshot.get("roa"),
                    "gross_margin": snapshot.get("gross_margin"),
                    "netprofit_margin": snapshot.get("netprofit_margin"),
                    "debt_to_assets": snapshot.get("debt_to_assets"),
                    "assets_to_eqt": snapshot.get("assets_to_eqt"),
                    "current_ratio": snapshot.get("current_ratio"),
                    "quick_ratio": snapshot.get("quick_ratio"),
                    "cash_ratio": snapshot.get("cash_ratio"),
                    "total_assets": snapshot.get("total_assets"),
                    "total_cur_assets": snapshot.get("total_cur_assets"),
                    "total_nca": snapshot.get("total_nca"),
                    "total_cur_liab": snapshot.get("total_cur_liab"),
                    "total_liab": snapshot.get("total_liab"),
                    "total_equity": snapshot.get("total_equity"),
                    "total_ncl": snapshot.get("total_ncl"),
                    "money_cap": snapshot.get("money_cap"),
                    "fix_assets": snapshot.get("fix_assets"),
                    "accounts_receiv": snapshot.get("accounts_receiv"),
                    "inventories": snapshot.get("inventories"),
                    "n_cashflow_act": snapshot.get("n_cashflow_act"),
                    "n_cashflow_inv_act": snapshot.get("n_cashflow_inv_act"),
                    "n_cashflow_fin_act": snapshot.get("n_cashflow_fin_act"),
                    "balance_sheet": raw_balance,
                    "income_statement": raw_income,
                    "cashflow_statement": raw_cashflow,
                    "financial_indicators": raw_indicators,
                    "raw_data": {
                        "balance_sheet": [raw_balance] if raw_balance else [],
                        "income_statement": [raw_income] if raw_income else [],
                        "cashflow_statement": [raw_cashflow] if raw_cashflow else [],
                        "financial_indicators": [raw_indicators] if raw_indicators else [],
                    },
                }

            def is_newer_report_period(candidate: Any, current: Any) -> bool:
                candidate_value = str(candidate or "")
                current_value = str(current or "")
                return bool(candidate_value) and candidate_value > current_value

            snapshot_fields = (
                "roe",
                "roa",
                "gross_margin",
                "netprofit_margin",
                "revenue_ttm",
                "net_profit_ttm",
                "n_cashflow_act",
                "debt_to_assets",
                "assets_to_eqt",
                "current_ratio",
                "quick_ratio",
                "cash_ratio",
                "dividend_yield",
                "net_working_capital",
            )

            # Query the latest financial data in batches
            # Group by code and get the latest data for each code (only query the data source with the highest priority)
            pipeline = [
                {"$match": {"code": {"$in": codes}, "source": preferred_source}},
                {"$sort": {"code": 1, "report_period": -1, "ann_date": -1}},
                {"$group": {
                    "_id": "$code",
                    "roe": {"$first": "$roe"},
                    "roa": {"$first": "$roa"},
                    "net_profit": {"$first": "$net_profit"},
                    "total_profit": {"$first": "$total_profit"},
                    "oper_profit": {"$first": "$oper_profit"},
                    "netprofit_margin": {"$first": "$netprofit_margin"},
                    "gross_margin": {"$first": "$gross_margin"},
                    "netprofit_margin": {"$first": "$netprofit_margin"},
                    "revenue": {"$first": "$revenue"},
                    "oper_rev": {"$first": "$oper_rev"},
                    "net_income": {"$first": "$net_income"},
                    "total_assets": {"$first": "$total_assets"},
                    "total_nca": {"$first": "$total_nca"},
                    "fix_assets": {"$first": "$fix_assets"},
                    "oper_cost": {"$first": "$oper_cost"},
                    "oper_exp": {"$first": "$oper_exp"},
                    "admin_exp": {"$first": "$admin_exp"},
                    "rd_exp": {"$first": "$rd_exp"},
                    "fin_exp": {"$first": "$fin_exp"},
                    "ebit": {"$first": "$ebit"},
                    "operating_profit": {"$first": "$operating_profit"},
                    "pe_ttm": {"$first": "$pe_ttm"},
                    "revenue_ttm": {"$first": "$revenue_ttm"},
                    "net_profit_ttm": {"$first": "$net_profit_ttm"},
                    "n_cashflow_act": {"$first": "$n_cashflow_act"},
                    "n_cashflow_inv_act": {"$first": "$n_cashflow_inv_act"},
                    "n_cashflow_fin_act": {"$first": "$n_cashflow_fin_act"},
                    "revenue_yoy": {"$first": "$revenue_yoy"},
                    "net_profit_yoy": {"$first": "$net_profit_yoy"},
                    "oper_profit_yoy": {"$first": "$oper_profit_yoy"},
                    "roe": {"$first": "$roe"},
                    "roa": {"$first": "$roa"},
                    "assets_to_eqt": {"$first": "$assets_to_eqt"},
                    "debt_to_assets": {"$first": "$debt_to_assets"},
                    "current_ratio": {"$first": "$current_ratio"},
                    "quick_ratio": {"$first": "$quick_ratio"},
                    "cash_ratio": {"$first": "$cash_ratio"},
                    "dividend_yield": {"$first": "$dividend_yield"},
                    "total_cur_assets": {"$first": "$total_cur_assets"},
                    "total_cur_liab": {"$first": "$total_cur_liab"},
                    "total_liab": {"$first": "$total_liab"},
                    "total_equity": {"$first": "$total_equity"},
                    "money_cap": {"$first": "$money_cap"},
                    "total_ncl": {"$first": "$total_ncl"},
                    "accounts_receiv": {"$first": "$accounts_receiv"},
                    "inventories": {"$first": "$inventories"},
                    "period_snapshots": {
                        "$push": {
                            "total_cur_assets": "$total_cur_assets",
                            "total_cur_liab": "$total_cur_liab",
                            "total_assets": "$total_assets",
                            "total_liab": "$total_liab",
                            "total_ncl": "$total_ncl",
                            "fix_assets": "$fix_assets",
                            "accounts_receiv": "$accounts_receiv",
                            "inventories": "$inventories",
                            "revenue_ttm": "$revenue_ttm",
                            "revenue": "$revenue",
                            "oper_rev": "$oper_rev",
                            "net_profit_ttm": "$net_profit_ttm",
                            "net_profit": "$net_profit",
                            "net_income": "$net_income",
                            "total_profit": "$total_profit",
                            "oper_profit": "$oper_profit",
                            "operating_profit": "$operating_profit",
                            "ebit": "$ebit",
                            "oper_cost": "$oper_cost",
                            "oper_exp": "$oper_exp",
                            "admin_exp": "$admin_exp",
                            "rd_exp": "$rd_exp",
                            "fin_exp": "$fin_exp",
                            "roe": "$roe",
                            "roa": "$roa",
                            "gross_margin": "$gross_margin",
                            "netprofit_margin": "$netprofit_margin",
                            "debt_to_assets": "$debt_to_assets",
                            "assets_to_eqt": "$assets_to_eqt",
                            "current_ratio": "$current_ratio",
                            "quick_ratio": "$quick_ratio",
                            "cash_ratio": "$cash_ratio",
                            "n_cashflow_act": "$n_cashflow_act",
                            "n_cashflow_inv_act": "$n_cashflow_inv_act",
                            "n_cashflow_fin_act": "$n_cashflow_fin_act",
                            "total_nca": "$total_nca",
                            "total_equity": "$total_equity",
                            "money_cap": "$money_cap",
                            "raw_balance_sheet": "$raw_data.balance_sheet",
                            "raw_income_statement": "$raw_data.income_statement",
                            "raw_cashflow_statement": "$raw_data.cashflow_statement",
                            "raw_financial_indicators": "$raw_data.financial_indicators",
                            "report_period": "$report_period"
                        }
                    },
                    "report_period": {"$first": "$report_period"},
                }}
            ]

            financial_data_map = {}
            async for doc in financial_collection.aggregate(pipeline):
                code = doc.get("_id")
                debt_to_assets = doc.get("debt_to_assets")
                assets_to_eqt = doc.get("assets_to_eqt")
                current_ratio = doc.get("current_ratio")
                quick_ratio = doc.get("quick_ratio")
                cash_ratio = doc.get("cash_ratio")
                dividend_yield = doc.get("dividend_yield")
                total_cur_assets = doc.get("total_cur_assets")
                total_cur_liab = doc.get("total_cur_liab")
                total_liab = doc.get("total_liab")
                total_equity = doc.get("total_equity")
                money_cap = doc.get("money_cap")
                total_ncl = doc.get("total_ncl")
                accounts_receiv = doc.get("accounts_receiv")
                inventories = doc.get("inventories")
                net_working_capital = None
                if total_cur_assets is not None and total_cur_liab is not None:
                    net_working_capital = (total_cur_assets - total_cur_liab) / 1e8
                working_capital_change = None
                period_snapshots = doc.get("period_snapshots") or []
                if len(period_snapshots) > 1:
                    current_snapshot = period_snapshots[0] or {}
                    previous_snapshot = period_snapshots[1] or {}
                    current_nwc = None
                    previous_nwc = None
                    if current_snapshot.get("total_cur_assets") is not None and current_snapshot.get("total_cur_liab") is not None:
                        current_nwc = current_snapshot.get("total_cur_assets") - current_snapshot.get("total_cur_liab")
                    if previous_snapshot.get("total_cur_assets") is not None and previous_snapshot.get("total_cur_liab") is not None:
                        previous_nwc = previous_snapshot.get("total_cur_assets") - previous_snapshot.get("total_cur_liab")
                    if current_nwc is not None and previous_nwc is not None:
                        working_capital_change = (current_nwc - previous_nwc) / 1e8
                fcf = None
                if doc.get("n_cashflow_act") is not None and doc.get("n_cashflow_inv_act") is not None:
                    fcf = doc.get("n_cashflow_act") + doc.get("n_cashflow_inv_act")
                cash_conversion = None
                if doc.get("n_cashflow_act") is not None and doc.get("net_profit") not in (None, 0):
                    cash_conversion = doc.get("n_cashflow_act") / doc.get("net_profit")
                accrual_ratio = None
                if doc.get("net_profit") is not None and doc.get("n_cashflow_act") is not None and doc.get("total_assets") not in (None, 0):
                    accrual_ratio = (doc.get("net_profit") - doc.get("n_cashflow_act")) / doc.get("total_assets") * 100
                revenue_base = doc.get("revenue_ttm") if doc.get("revenue_ttm") not in (None, 0) else doc.get("revenue")
                fcf_margin = None
                if fcf is not None and revenue_base not in (None, 0):
                    fcf_margin = fcf / revenue_base * 100
                asset_turnover = None
                if revenue_base not in (None, 0) and doc.get("total_assets") not in (None, 0):
                    asset_turnover = revenue_base / doc.get("total_assets")
                gross_profit_to_assets = None
                if revenue_base not in (None, 0) and doc.get("gross_margin") is not None and doc.get("total_assets") not in (None, 0):
                    gross_profit_to_assets = revenue_base * doc.get("gross_margin") / 100 / doc.get("total_assets") * 100
                interest_coverage = None
                inventory_turnover = None
                cost_base = doc.get("oper_cost")
                if cost_base in (None, 0) and revenue_base not in (None, 0) and doc.get("gross_margin") is not None:
                    cost_base = revenue_base * (1 - doc.get("gross_margin") / 100)
                if cost_base not in (None, 0) and inventories not in (None, 0):
                    inventory_turnover = cost_base / inventories
                receivable_turnover = None
                if revenue_base not in (None, 0) and accounts_receiv not in (None, 0):
                    receivable_turnover = revenue_base / accounts_receiv
                net_cash_position = None
                if money_cap is not None and doc.get("total_assets") not in (None, 0):
                    debt_proxy = total_ncl
                    if debt_proxy is None and total_liab is not None and total_cur_liab is not None:
                        debt_proxy = total_liab - total_cur_liab
                    if debt_proxy is not None:
                        net_cash_position = (money_cap - max(debt_proxy, 0)) / doc.get("total_assets") * 100
                financial_records = [build_snapshot_record(snapshot) for snapshot in period_snapshots if snapshot]
                revenue_yoy = None
                net_profit_yoy = None
                oper_profit_yoy = None
                revenue_cagr_3y = None
                profit_cagr_3y = None
                roic = None
                piotroski_f_score = None
                beneish_m_score = None
                if financial_records:
                    latest_financial = financial_records[0]
                    factor_context = {
                        "symbol": code,
                        "basic_info": {},
                        "market_quotes": {},
                        "financial_records": financial_records,
                        "latest_financial": latest_financial,
                        "current_price": None,
                    }
                    revenue_yoy = _compute_yoy_growth(financial_records, "revenue")
                    net_profit_yoy = _compute_yoy_growth(financial_records, "net_profit")
                    oper_profit_yoy = _compute_yoy_growth(financial_records, "oper_profit")
                    revenue_cagr_3y = _compute_cagr(financial_records, (("revenue_ttm",), ("revenue",), ("oper_rev",)), 3)
                    profit_cagr_3y = _compute_cagr(financial_records, (("net_profit_ttm",), ("net_profit",), ("net_income",)), 3)
                    roic = _estimate_roic(latest_financial)
                    interest_coverage = _estimate_interest_coverage(latest_financial)
                    piotroski_f_score = _estimate_piotroski_f_score(factor_context)
                    beneish_m_score = _estimate_beneish_m_score(factor_context)
                financial_data_map[code] = {
                    "roe": doc.get("roe"),
                    "roa": doc.get("roa"),
                    "netprofit_margin": doc.get("netprofit_margin"),
                    "gross_margin": doc.get("gross_margin"),
                    "revenue_ttm": doc.get("revenue_ttm"),
                    "revenue_yoy": revenue_yoy,
                    "net_profit_ttm": doc.get("net_profit_ttm"),
                    "net_profit_yoy": net_profit_yoy,
                    "oper_profit_yoy": oper_profit_yoy,
                    "n_cashflow_act": doc.get("n_cashflow_act"),
                    "fcf": fcf,
                    "fcf_margin": fcf_margin,
                    "cash_conversion": cash_conversion,
                    "accrual_ratio": accrual_ratio,
                    "asset_turnover": asset_turnover,
                    "gross_profit_to_assets": gross_profit_to_assets,
                    "interest_coverage": interest_coverage,
                    "inventory_turnover": inventory_turnover,
                    "receivable_turnover": receivable_turnover,
                    "net_cash_position": net_cash_position,
                    "piotroski_f_score": piotroski_f_score,
                    "beneish_m_score": beneish_m_score,
                    "debt_to_assets": debt_to_assets,
                    "assets_to_eqt": assets_to_eqt,
                    "current_ratio": current_ratio,
                    "quick_ratio": quick_ratio,
                    "cash_ratio": cash_ratio,
                    "dividend_yield": dividend_yield,
                    "total_equity": total_equity,
                    "roic": roic,
                    "revenue_cagr_3y": revenue_cagr_3y,
                    "profit_cagr_3y": profit_cagr_3y,
                    "working_capital_change": working_capital_change,
                    "net_working_capital": net_working_capital,
                    "report_period": doc.get("report_period"),
                    "_financial_records": financial_records,
                }

            # Populate financial data into results
            for result in results:
                code = result.get("code")
                if code in financial_data_map:
                    financial_data = financial_data_map[code]
                    raw_basic_info = dict(basic_info_map.get(code) or {})
                    basic_info_context = {
                        **raw_basic_info,
                        "total_mv": raw_basic_info.get("total_mv", result.get("total_mv")),
                        "market_cap": raw_basic_info.get("market_cap", result.get("total_mv")),
                    }
                    latest_report_period = financial_data.get("report_period")
                    newer_snapshot = is_newer_report_period(latest_report_period, result.get("report_period"))
                    if latest_report_period is not None and (newer_snapshot or result.get("report_period") is None):
                        result["report_period"] = latest_report_period

                    for field_name in snapshot_fields:
                        field_value = financial_data.get(field_name)
                        if field_value is None:
                            continue
                        if newer_snapshot or result.get(field_name) is None:
                            result[field_name] = field_value

                    if newer_snapshot or result.get("pb_mrq") is None:
                        total_mv = result.get("total_mv")
                        total_equity = financial_data.get("total_equity")
                        if total_mv not in (None, 0) and total_equity not in (None, 0):
                            result["pb_mrq"] = (total_mv * 100000000) / total_equity
                    if newer_snapshot or result.get("pe_ttm") is None:
                        total_mv = result.get("total_mv")
                        net_profit_ttm = financial_data.get("net_profit_ttm")
                        if total_mv not in (None, 0) and net_profit_ttm not in (None, 0):
                            result["pe_ttm"] = (total_mv * 100000000) / net_profit_ttm
                    if result.get("asset_turnover") is None:
                        result["asset_turnover"] = financial_data.get("asset_turnover")
                    if result.get("gross_profit_to_assets") is None:
                        result["gross_profit_to_assets"] = financial_data.get("gross_profit_to_assets")
                    if result.get("interest_coverage") is None:
                        result["interest_coverage"] = financial_data.get("interest_coverage")
                    if result.get("inventory_turnover") is None:
                        result["inventory_turnover"] = financial_data.get("inventory_turnover")
                    if result.get("receivable_turnover") is None:
                        result["receivable_turnover"] = financial_data.get("receivable_turnover")
                    if result.get("net_cash_position") is None:
                        result["net_cash_position"] = financial_data.get("net_cash_position")
                    if result.get("piotroski_f_score") is None:
                        result["piotroski_f_score"] = financial_data.get("piotroski_f_score")
                    if result.get("beneish_m_score") is None:
                        result["beneish_m_score"] = financial_data.get("beneish_m_score")
                    if financial_data.get("revenue_yoy") is not None:
                        result["revenue_yoy"] = financial_data.get("revenue_yoy")
                    if financial_data.get("net_profit_yoy") is not None:
                        result["net_profit_yoy"] = financial_data.get("net_profit_yoy")
                    if financial_data.get("oper_profit_yoy") is not None:
                        result["oper_profit_yoy"] = financial_data.get("oper_profit_yoy")
                    if financial_data.get("revenue_cagr_3y") is not None:
                        result["revenue_cagr_3y"] = financial_data.get("revenue_cagr_3y")
                    if financial_data.get("profit_cagr_3y") is not None:
                        result["profit_cagr_3y"] = financial_data.get("profit_cagr_3y")
                    if result.get("fcf") is None:
                        result["fcf"] = financial_data.get("fcf")
                    if result.get("fcf_margin") is None:
                        result["fcf_margin"] = financial_data.get("fcf_margin")
                    if result.get("cash_conversion") is None:
                        result["cash_conversion"] = financial_data.get("cash_conversion")
                    if result.get("accrual_ratio") is None:
                        result["accrual_ratio"] = financial_data.get("accrual_ratio")
                    if financial_data.get("roic") is not None:
                        result["roic"] = financial_data.get("roic")
                    if result.get("peg") is None:
                        pe_ttm = result.get("pe_ttm")
                        growth = financial_data.get("net_profit_yoy")
                        if pe_ttm not in (None, 0) and growth not in (None, 0) and growth > 0:
                            result["peg"] = pe_ttm / growth
                    if result.get("fcf_yield") is None:
                        fcf = financial_data.get("fcf")
                        total_mv = result.get("total_mv")
                        if fcf is not None and total_mv not in (None, 0):
                            result["fcf_yield"] = fcf / (total_mv * 1e8) * 100
                    if result.get("ocf_yield") is None:
                        ocf = financial_data.get("n_cashflow_act")
                        total_mv = result.get("total_mv")
                        if ocf is not None and total_mv not in (None, 0):
                            result["ocf_yield"] = ocf / (total_mv * 1e8) * 100
                    if financial_data.get("working_capital_change") is not None:
                        result["working_capital_change"] = financial_data.get("working_capital_change")
                    if result.get("altman_z_score") is None:
                        total_mv = result.get("total_mv")
                        financial_records = financial_data.get("_financial_records") or []
                        if total_mv not in (None, 0) and financial_records:
                            altman_context = {
                                "symbol": code,
                                "basic_info": {"total_mv": total_mv},
                                "market_quotes": {},
                                "financial_records": financial_records,
                                "latest_financial": financial_records[0],
                                "current_price": None,
                            }
                            result["altman_z_score"] = _estimate_altman_z_score(altman_context)

                    financial_records = financial_data.get("_financial_records") or []
                    if financial_records:
                        latest_financial = financial_records[0]
                        diagnostics_context = {
                            "symbol": code,
                            "basic_info": basic_info_context,
                            "market_quotes": {},
                            "financial_records": financial_records,
                            "latest_financial": latest_financial,
                            "current_price": None,
                        }
                        cautious_factor_values = {
                            "piotroski_f_score": result.get("piotroski_f_score"),
                            "altman_z_score": result.get("altman_z_score"),
                            "beneish_m_score": result.get("beneish_m_score"),
                        }
                        factor_diagnostics = _build_factor_diagnostics(diagnostics_context, cautious_factor_values)
                        null_factor_diagnostics = {
                            field_name: diagnostic
                            for field_name, diagnostic in factor_diagnostics.items()
                            if result.get(field_name) is None
                        }
                        if null_factor_diagnostics:
                            result["factor_diagnostics"] = null_factor_diagnostics

                        factor_values_for_warnings = {
                            "pe_ttm": result.get("pe_ttm"),
                            "pb": result.get("pb"),
                            "pb_mrq": result.get("pb_mrq"),
                            "ps_ttm": result.get("ps_ttm"),
                            "dividend_yield": result.get("dividend_yield"),
                            "industry_pe_median": result.get("industry_pe_median"),
                            "industry_pb_median": result.get("industry_pb_median"),
                            "roic": result.get("roic"),
                            "interest_coverage": result.get("interest_coverage"),
                            "inventory_turnover": result.get("inventory_turnover"),
                            "net_cash_position": result.get("net_cash_position"),
                            "net_profit_ttm": result.get("net_profit_ttm"),
                            "fcf": result.get("fcf"),
                        }
                        factor_warnings = {
                            **_build_value_factor_warnings(diagnostics_context, factor_values_for_warnings, {}, {}),
                            **_build_quality_factor_warnings(diagnostics_context, factor_values_for_warnings),
                            **_build_growth_factor_warnings(diagnostics_context, factor_values_for_warnings),
                        }
                        if factor_warnings:
                            result["factor_warnings"] = factor_warnings

            logger.debug(f"✅ 已填充 {len(financial_data_map)} 条财务数据")

        except Exception as e:
            logger.warning(f"⚠️ 填充财务数据失败: {e}")
            # No exception is thrown, allowing the basic data to continue to be returned

    def _format_result(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format query results and use backend field names uniformly"""
        # Infer market type based on stock symbol
        code = doc.get("code", "")
        market_type = "A股"  # Default A shares
        if code:
            if code.startswith("6"):
                market_type = "A股"  # Shanghai
            elif code.startswith(("0", "3")):
                market_type = "A股"  # Shenzhen
            elif code.startswith("8") or code.startswith("4"):
                market_type = "A股"  # Beijing Exchange

        result = {
            # Basic information
            "code": doc.get("code"),
            "name": doc.get("name"),
            "industry": doc.get("industry"),
            "area": doc.get("area"),
            "market": market_type,  # Market type (A shares, US stocks, Hong Kong stocks)
            "board": doc.get("market"),  # Sectors (Main Board, GEM, Science and Technology Innovation Board, etc.)
            "exchange": doc.get("sse"),  # Exchanges (Shanghai Stock Exchange, Shenzhen Stock Exchange, etc.)
            "list_date": doc.get("list_date"),

            # Market value information (100 million yuan)
            "total_mv": doc.get("total_mv"),
            "circ_mv": doc.get("circ_mv"),

            # financial indicators
            "pe": doc.get("pe"),
            "pb": doc.get("pb"),
            "pe_ttm": doc.get("pe_ttm"),
            "ps_ttm": doc.get("ps_ttm"),
            "pb_mrq": doc.get("pb_mrq"),
            "roe": doc.get("roe"),
            "roa": doc.get("roa"),
            "gross_margin": doc.get("gross_margin"),
            "netprofit_margin": doc.get("netprofit_margin"),
            "peg": doc.get("peg"),
            "roic": doc.get("roic"),
            "asset_turnover": doc.get("asset_turnover"),
            "gross_profit_to_assets": doc.get("gross_profit_to_assets"),
            "interest_coverage": doc.get("interest_coverage"),
            "inventory_turnover": doc.get("inventory_turnover"),
            "receivable_turnover": doc.get("receivable_turnover"),
            "net_cash_position": doc.get("net_cash_position"),
            "piotroski_f_score": doc.get("piotroski_f_score"),
            "altman_z_score": doc.get("altman_z_score"),
            "beneish_m_score": doc.get("beneish_m_score"),
            "revenue_cagr_3y": doc.get("revenue_cagr_3y"),
            "profit_cagr_3y": doc.get("profit_cagr_3y"),
            "revenue_ttm": doc.get("revenue_ttm"),
            "revenue_yoy": doc.get("revenue_yoy"),
            "net_profit_ttm": doc.get("net_profit_ttm"),
            "net_profit_yoy": doc.get("net_profit_yoy"),
            "oper_profit_yoy": doc.get("oper_profit_yoy"),
            "n_cashflow_act": doc.get("n_cashflow_act"),
            "fcf": doc.get("fcf"),
            "fcf_yield": doc.get("fcf_yield"),
            "fcf_margin": doc.get("fcf_margin"),
            "ocf_yield": doc.get("ocf_yield"),
            "cash_conversion": doc.get("cash_conversion"),
            "accrual_ratio": doc.get("accrual_ratio"),
            "working_capital_change": doc.get("working_capital_change"),

            # Extended financial indicators (new calculated fields from stock_screening_view)
            "debt_to_assets": doc.get("debt_to_assets"),      # Asset-liability ratio (%)
            "assets_to_eqt": doc.get("assets_to_eqt"),        # equity multiplier
            "current_ratio": doc.get("current_ratio"),        # current ratio
            "quick_ratio": doc.get("quick_ratio"),            # quick ratio
            "cash_ratio": doc.get("cash_ratio"),              # cash ratio
            "dividend_yield": doc.get("dividend_yield"),      # dividend yield (%)
            "net_working_capital": doc.get("net_working_capital"),  # net working capital (billion)
            "is_st": doc.get("is_st"),                        # Whether ST shares
            "report_period": doc.get("report_period"),        # Latest financial reporting period

            # trading indicators
            "turnover_rate": doc.get("turnover_rate"),
            "volume_ratio": doc.get("volume_ratio"),

            # Transaction data (obtained from the view, which already contains real-time market data)
            "close": doc.get("close"),              # closing price
            "pct_chg": doc.get("pct_chg"),          # Increase or decrease(%)
            "amount": doc.get("amount"),            # Turnover
            "volume": doc.get("volume"),            # Volume
            "open": doc.get("open"),                # opening price
            "high": doc.get("high"),                # highest price
            "low": doc.get("low"),                  # lowest price

            # Technical Indicators (from Materialized Technology Snapshot)
            "ma20": doc.get("ma20"),
            "rsi14": doc.get("rsi14"),
            "kdj_k": doc.get("kdj_k"),
            "kdj_d": doc.get("kdj_d"),
            "kdj_j": doc.get("kdj_j"),
            "dif": doc.get("dif"),
            "dea": doc.get("dea"),
            "macd_hist": doc.get("macd_hist"),

            # metadata
            "source": doc.get("source", "database"),
            "updated_at": doc.get("updated_at"),
        }
        
        # Remove None value
        return {k: v for k, v in result.items() if v is not None}
    
    async def get_field_statistics(self, field: str) -> Dict[str, Any]:
        """
        Get field statistics
        
        Args:
            field: Field name
            
        Returns:
            Dict: Statistics {min, max, avg, count}
        """
        try:
            db_field = self.basic_fields.get(field)
            if not db_field:
                return {}
            
            db = get_mongo_db()
            # ⚠️ Performance fix: use stock_basic_info instead of stock_screening_view (view triggers $lookup Aggregation, query is extremely slow)
            collection = db["stock_basic_info"]
            
            # Get statistics using aggregation pipeline
            pipeline = [
                {"$match": {db_field: {"$exists": True, "$ne": None}}},
                {"$group": {
                    "_id": None,
                    "min": {"$min": f"${db_field}"},
                    "max": {"$max": f"${db_field}"},
                    "avg": {"$avg": f"${db_field}"},
                    "count": {"$sum": 1}
                }}
            ]
            
            result = await collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                avg_value = stats.get("avg")
                return {
                    "field": field,
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "avg": round(avg_value, 2) if avg_value is not None else None,
                    "count": stats.get("count", 0)
                }
            
            return {"field": field, "count": 0}
            
        except Exception as e:
            logger.error(f"获取字段统计失败: {e}")
            return {"field": field, "error": str(e)}
    
    def _separate_conditions(self, conditions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Separate basic information conditions and real-time market conditions

        Args:
            conditions: All filters

        Returns:
            Tuple[List of basic information conditions, List of real-time market conditions]
        """
        # Real-time quotation field (need to be queried from market_quotes)
        quote_fields = {"pct_chg", "amount", "close", "volume"}

        basic_conditions = []
        quote_conditions = []

        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            if field in quote_fields:
                quote_conditions.append(condition)
            else:
                basic_conditions.append(condition)

        return basic_conditions, quote_conditions

    async def _enrich_with_quote_data(
        self,
        results: List[Dict[str, Any]],
        codes: List[str],
    ) -> None:
        """
        Supplement market data from market_quotes to the results in batches.
        Ensure close / pct_chg / amount / volume always has a value to display.
        """
        try:
            db = get_mongo_db()
            quotes_collection = db["market_quotes"]
            quotes_cursor = quotes_collection.find({"code": {"$in": codes}})
            quotes_map: Dict[str, Dict[str, Any]] = {}
            async for quote in quotes_cursor:
                code = quote.get("code")
                if code:
                    quotes_map[code] = {
                        "close": quote.get("close"),
                        "pct_chg": quote.get("pct_chg"),
                        "amount": quote.get("amount"),
                        "volume": quote.get("volume"),
                        "open": quote.get("open"),
                        "high": quote.get("high"),
                        "low": quote.get("low"),
                        "pre_close": quote.get("pre_close"),
                        "trade_date": quote.get("trade_date"),
                    }

            for result in results:
                code = result.get("code")
                qd = quotes_map.get(code)
                if qd:
                    for k, v in qd.items():
                        if v is not None and result.get(k) is None:
                            result[k] = v

            logger.debug(f"✅ 行情数据补充完成: {len(quotes_map)}/{len(codes)} 只股票有行情")
        except Exception as e:
            logger.warning(f"⚠️ 补充行情数据失败: {e}")

    def _apply_quote_filter(
        self,
        results: List[Dict[str, Any]],
        quote_conditions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter results according to quotation conditions in memory (results have been supplemented with quotations through _enrich_with_quote_data)"""
        filtered = []
        for result in results:
            match = True
            for condition in quote_conditions:
                field = condition.get("field") if isinstance(condition, dict) else condition.field
                operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
                value = condition.get("value") if isinstance(condition, dict) else condition.value

                field_value = result.get(field)
                if field_value is None:
                    match = False
                    break

                if operator == "between" and isinstance(value, list) and len(value) == 2:
                    if not (value[0] <= field_value <= value[1]):
                        match = False
                elif operator == ">":
                    if not (field_value > value):
                        match = False
                elif operator == "<":
                    if not (field_value < value):
                        match = False
                elif operator == ">=":
                    if not (field_value >= value):
                        match = False
                elif operator == "<=":
                    if not (field_value <= value):
                        match = False
                elif operator == "==":
                    if field_value != value:
                        match = False
                elif operator == "!=":
                    if field_value == value:
                        match = False

                if not match:
                    break

            if match:
                filtered.append(result)
        return filtered

    async def _filter_by_quotes(
        self,
        results: List[Dict[str, Any]],
        codes: List[str],
        quote_conditions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Secondary screening based on real-time market data

        Args:
            results: Initial screening results
            codes: Stock code list
            quote_conditions: Real-time market filter conditions

        Returns:
            List[Dict]: Filtered results
        """
        try:
            db = get_mongo_db()
            quotes_collection = db['market_quotes']

            # Query real-time market data in batches
            quotes_cursor = quotes_collection.find({"code": {"$in": codes}})
            quotes_map = {}
            async for quote in quotes_cursor:
                code = quote.get("code")
                quotes_map[code] = {
                    "close": quote.get("close"),
                    "pct_chg": quote.get("pct_chg"),
                    "amount": quote.get("amount"),
                    "volume": quote.get("volume"),
                }

            logger.info(f"📊 查询到 {len(quotes_map)} 只股票的实时行情数据")

            # Filter results
            filtered_results = []
            for result in results:
                code = result.get("code")
                quote_data = quotes_map.get(code)

                if not quote_data:
                    # There is no real-time market data, skip it
                    continue

                # Check whether all real-time market conditions are met
                match = True
                for condition in quote_conditions:
                    field = condition.get("field") if isinstance(condition, dict) else condition.field
                    operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
                    value = condition.get("value") if isinstance(condition, dict) else condition.value

                    field_value = quote_data.get(field)
                    if field_value is None:
                        match = False
                        break

                    # Check conditions
                    if operator == "between" and isinstance(value, list) and len(value) == 2:
                        if not (value[0] <= field_value <= value[1]):
                            match = False
                            break
                    elif operator == ">":
                        if not (field_value > value):
                            match = False
                            break
                    elif operator == "<":
                        if not (field_value < value):
                            match = False
                            break
                    elif operator == ">=":
                        if not (field_value >= value):
                            match = False
                            break
                    elif operator == "<=":
                        if not (field_value <= value):
                            match = False
                            break

                if match:
                    # Incorporate real-time market data into results
                    result.update(quote_data)
                    filtered_results.append(result)

            logger.info(f"✅ 实时行情筛选完成: 筛选前={len(results)}, 筛选后={len(filtered_results)}")
            return filtered_results

        except Exception as e:
            logger.error(f"❌ 实时行情筛选失败: {e}")
            # If it fails, return the original result
            return results

    async def get_available_values(self, field: str, limit: int = 100) -> List[str]:
        """
        Get a list of optional values for a field (for enumeration type fields)
        
        Args:
            field: Field name
            limit: Return quantity limit
            
        Returns:
            List[str]: list of optional values
        """
        try:
            db_field = self.basic_fields.get(field)
            if not db_field:
                return []
            
            db = get_mongo_db()
            # ⚠️ Performance fix: use stock_basic_info instead of stock_screening_view (view triggers $lookup Aggregation, query is extremely slow)
            collection = db["stock_basic_info"]
            
            # Get unique values of a field
            values = await collection.distinct(db_field)
            
            # Filter None values and sort
            values = [v for v in values if v is not None]
            values.sort()
            
            return values[:limit]
            
        except Exception as e:
            logger.error(f"获取字段可选值失败: {e}")
            return []


# Global service instance
_database_screening_service: Optional[DatabaseScreeningService] = None


def get_database_screening_service() -> DatabaseScreeningService:
    """获取数据库筛选服务实例"""
    global _database_screening_service
    if _database_screening_service is None:
        _database_screening_service = DatabaseScreeningService()
    return _database_screening_service

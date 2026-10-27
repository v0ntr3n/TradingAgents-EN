"""
Transaction review service
Provide transaction review and periodic review functions
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from bson import ObjectId

from app.core.database import get_mongo_db, get_database

# ==================== Feature switch ====================
# Whether to use the template system to generate prompt words (off by default to maintain backward compatibility)
# NOTE: Use functions to read dynamically and make sure the .env file is loaded
def _use_template_prompts() -> bool:
    """Dynamically read the USE_TEMPLATE_PROMPTS environment variable"""
    value = os.getenv("USE_TEMPLATE_PROMPTS", "false").lower() == "true"
    # Print log when first called
    if not hasattr(_use_template_prompts, '_logged'):
        _use_template_prompts._logged = True
        logging.getLogger("app.services.trade_review").info(
            f"📋 [Feature switch] USE_TEMPLATE_PROMPTS = {value}"
        )
    return value

def _use_workflow_review() -> bool:
    """Dynamically read the USE_STOCK_ENGINE environment variable (reuse the engine switch for position research)

    When USE_STOCK_ENGINE=true At the same time, the transaction review will also use the workflow engine to conduct multi-dimensional analysis.
    """
    value = os.getenv("USE_STOCK_ENGINE", "false").lower() == "true"
    if not hasattr(_use_workflow_review, '_logged'):
        _use_workflow_review._logged = True
        logging.getLogger("app.services.trade_review").info(
            f"📋 [Feature switch] USE_STOCK_ENGINE (Review workflow) = {value}"
        )
    return value

from app.models.review import (
    ReviewType, ReviewStatus, PeriodType,
    TradeRecord, TradeInfo, MarketSnapshot,
    AITradeReview, TradeReviewReport,
    TradingStatistics, AIPeriodicReview, TradeSummaryItem, PeriodicReviewReport,
    CreateTradeReviewRequest, CreatePeriodicReviewRequest,
    TradeReviewResponse, PeriodicReviewResponse, ReviewListItem
)
from app.utils.compliance import sanitize_periodic_review_payload, sanitize_trade_review_payload
from app.utils.timezone import now_tz

# ==================== v2.0 Tool import ====================
# Import transaction review tool set
try:
    from core.tools.implementations.trade_review import (
        get_trade_records as tool_get_trade_records,
        build_trade_info as tool_build_trade_info,
        get_account_info as tool_get_account_info,
        get_market_snapshot_for_review as tool_get_market_snapshot
    )
    TOOLS_AVAILABLE = True
except ImportError:
    logger = logging.getLogger("app.services.trade_review")
    logger.warning("⚠️ v2.0 The transaction review tool is not loaded and traditional methods will be used.")
    TOOLS_AVAILABLE = False

# Import unified data source tool
from tradingagents.utils.stock_utils import StockUtils
from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider
from tradingagents.dataflows.providers.us.optimized import get_optimized_us_data_provider

logger = logging.getLogger("app.services.trade_review")


async def _store_trade_pattern_memory(
    db,
    user_id: str,
    trade_info,
    ai_review,
    review_id: str,
) -> None:
    """After the review is completed, write the key discipline points into the mem0 trade_pattern scope.

    As long as the AI review has output (any summary/strengths/weaknesses/suggestions/plan_deviation is not empty),
    Just write it into the trade_pattern memory so that it can be displayed and recalled as a trading discipline in the smart assistant later.
    """
    if not user_id:
        logger.warning(f"[trade_review] trade_pattern Skip: user_id is empty, review_id={review_id}")
        return
    if ai_review is None:
        logger.warning(f"[trade_review] trade_pattern Skip: ai_review is empty, review_id={review_id}")
        return
    try:
        weaknesses = list(getattr(ai_review, "weaknesses", []) or [])
        strengths = list(getattr(ai_review, "strengths", []) or [])
        suggestions = list(getattr(ai_review, "suggestions", []) or [])
        plan_deviation = (getattr(ai_review, "plan_deviation", "") or "").strip()
        summary = (getattr(ai_review, "summary", "") or "").strip()

        # If there is no AI review output, it will be skipped.
        if not weaknesses and not suggestions and not plan_deviation and not summary and not strengths:
            logger.info(f"[trade_review] trade_pattern Skip: AI review content is empty, review_id={review_id}")
            return

        code = getattr(trade_info, "code", "") or ""
        name = getattr(trade_info, "name", "") or ""
        first_buy = getattr(trade_info, "first_buy_date", "") or ""

        parts = [f"交易复盘 {name}({code}) {first_buy}: {summary}" if summary else f"交易复盘 {name}({code})"]
        if strengths:
            parts.append("做得好: " + "；".join(str(s).strip() for s in strengths[:3] if s))
        if weaknesses:
            parts.append("不足: " + "；".join(str(w).strip() for w in weaknesses[:3] if w))
        if plan_deviation:
            parts.append("计划偏差: " + plan_deviation[:200])
        if suggestions:
            parts.append("改进建议: " + "；".join(str(s).strip() for s in suggestions[:3] if s))

        content = "\n".join(parts).strip()
        if not content:
            logger.info(f"[trade_review] trade_pattern Skip: content is empty, review_id={review_id}")
            return

        from core.memory.service import get_memory_service
        from core.memory.models import MemoryScope
        svc = get_memory_service(db)
        result = await svc.store(
            [{"role": "assistant", "content": content}],
            user_id=user_id,
            agent_id="trade_review",
            scope=MemoryScope.TRADE_PATTERN,
            metadata={
                "review_id": review_id,
                "symbol": str(code).upper(),
                "name": name,
                "source": "trade_review_completed",
            },
            infer=False,  # Already a structural point
        )
        if result.success:
            logger.info(
                f"[trade_review] Written to trade_pattern memory: user={user_id} symbol={code} review={review_id}"
            )
        else:
            logger.warning(f"[trade_review] trade_pattern Write failed: {result.error}")
    except Exception as e:
        logger.warning(f"[trade_review] trade_pattern write exception: {e}", exc_info=True)


async def _reflect_trade_review_lesson(
    db,
    user_id: str,
    trade_info,
    ai_review,
    review_id: str,
) -> None:
    """Review, reflection and refinement (v3.5.0 item 2): Transform the original review conclusions into structured experience.

    Write in _store_trade_pattern_memory"Original text trade_pattern"Then call,
    Use LLM to extract 4-dimensional structured lessons (reasoning/improvement/summary/query),
    Write to the same TRADE_PATTERN scope but metadata.memory_kind=trade_lesson, 
    This makes it easier to recall structured lessons instead of the original text when analyzing the same stock next time.

    Downgrade strategy:
    - LLM Timeout/return non JSON → fallback Write the original text (memory_kind is still trade_lesson, but reflection_success=False) 
    - mem0 Not available → Skip, do not block the main process
    """
    if not user_id or ai_review is None or trade_info is None:
        return

    try:
        from core.agents.reflection_helper import run_reflection
        from core.agents.reflection_prompts import (
            TRADE_REFLECTION_SYSTEM_PROMPT,
            build_trade_reflection_user_prompt,
        )
        from core.memory.models import MemoryScope

        code = str(getattr(trade_info, "code", "") or "").upper()
        name = getattr(trade_info, "name", "") or ""

        # Use the original text trade_pattern content as fallback (the recallable original text will still be written when reflection fails)
        summary = (getattr(ai_review, "summary", "") or "").strip()
        fallback_parts = [f"交易复盘 {name}({code})"]
        if summary:
            fallback_parts.append(summary)
        fallback_content = "\n".join(fallback_parts)

        user_prompt = build_trade_reflection_user_prompt(trade_info, ai_review)
        if not user_prompt.strip():
            logger.info(f"[trade_review] Reflection skipped: user_prompt is empty, review_id={review_id}")
            return

        success = await run_reflection(
            db=db,
            user_id=user_id,
            agent_id="trade_review_reflection",
            scope=MemoryScope.TRADE_PATTERN,
            memory_kind="trade_lesson",
            system_prompt=TRADE_REFLECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            fallback_content=fallback_content,
            fallback_metadata={
                "review_id": review_id,
                "symbol": code,
                "name": name,
                "source": "trade_review_reflection",
            },
        )
        if success:
            logger.info(
                f"[trade_review] Trade_lesson lesson written: user={user_id} symbol={code} review={review_id}"
            )
    except Exception as e:
        logger.warning(f"[trade_review] trade_lesson Reflection exception: {e}", exc_info=True)


def _derive_risk_level(score) -> str:
    """根据综合评分推导风险等级"""
    if score is None:
        return ""
    if score >= 80:
        return "低风险"
    elif score >= 60:
        return "中低风险"
    elif score >= 40:
        return "中风险"
    elif score >= 20:
        return "中高风险"
    else:
        return "高风险"


class TradeReviewService:
    """交易复盘服务"""

    def __init__(self):
        self.db = get_mongo_db()
        self.trade_reviews_collection = "trade_reviews"
        self.periodic_reviews_collection = "periodic_reviews"
        self.paper_trades_collection = "paper_trades"
        self.trading_systems_collection = "trading_systems"

    def _append_review_guardrails(self, prompt: str) -> str:
        """Add unified compliance constraints to review prompt words."""
        guardrails = """
## Output constraints
- Only the review conclusions, areas that have been done well, areas that need improvement, disciplinary reflections and follow-up observation points are allowed to be output.
- The improvement content is limited to research preparation, rule execution, risk identification and recording methods. Suggestions for future buying and selling, holding, adding or subtracting positions, stop loss and profit, target price or specific position ratio are not allowed.
- If you need to describe the problem, focus on why this transaction deviated from the plan. Do not write the output as the next transaction instruction.
""".strip()
        return f"{prompt.rstrip()}\n\n{guardrails}\n"

    def _sanitize_trade_review_result(self, result: AITradeReview) -> AITradeReview:
        """Unifiedly convert the transaction review results into review improvement mode."""
        if result is None:
            return AITradeReview()

        raw_data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        sanitized_data = sanitize_trade_review_payload(raw_data)
        return AITradeReview(**sanitized_data)

    def _sanitize_trade_review_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Unified cleaning of result fields in transaction review details and history records."""
        return sanitize_trade_review_payload(data)

    def _sanitize_periodic_review_result(self, result: AIPeriodicReview) -> AIPeriodicReview:
        """Unify the phased review results into a review improvement model."""
        if result is None:
            return AIPeriodicReview()

        raw_data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        sanitized_data = sanitize_periodic_review_payload(raw_data)
        return AIPeriodicReview(**sanitized_data)

    def _sanitize_periodic_review_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Unified cleaning of the result fields in the staged review details."""
        return sanitize_periodic_review_payload(data)

    # ==================== Helper methods ====================

    async def _get_current_price(self, code: str, market: str = "CN") -> Optional[float]:
        """Get the current price of a stock

        Args:
            code: Stock code
            market: market type (CN/HK/US)

        Returns:
            Current price, returned if acquisition fails None
        """
        try:
            # 🔥 Get prices using the same method as the position research service
            from app.services.portfolio_service import PortfolioService
            portfolio_service = PortfolioService()
            current_price = await portfolio_service._get_stock_price(code, market)
            
            if current_price:
                logger.info(f"✅ [获取当前价格] {code} ({market}): {current_price}")
                return float(current_price)
            
            logger.warning(f"⚠️ [获取当前价格] 未找到 {code} ({market}) 的行情数据")
            return None
        except Exception as e:
            logger.warning(f"❌ [Get current price] Failed to obtain: {e}", exc_info=True)
            return None

    async def _calculate_unrealized_pnl(self, trade_info: TradeInfo) -> TradeInfo:
        """Calculate floating profit and loss (transactions in positions)

        Args:
            trade_info: transaction information

        Returns:
            Updated transaction information (including floating profit and loss)
        """
        if not trade_info.is_holding or trade_info.remaining_quantity <= 0:
            return trade_info

        # 🔥 Get the current price (pass the market parameter)
        current_price = await self._get_current_price(trade_info.code, trade_info.market)
        if not current_price:
            logger.warning(f"⚠️ [Calculate floating profit and loss] Unable to get current price ({trade_info.code}, {trade_info.market}), Skip floating profit and loss calculations")
            return trade_info

        # Calculate floating profit and loss
        unrealized_pnl = (current_price - trade_info.avg_buy_price) * trade_info.remaining_quantity
        cost_basis = trade_info.avg_buy_price * trade_info.remaining_quantity
        unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        # update trade_info
        trade_info.current_price = current_price
        trade_info.unrealized_pnl = round(unrealized_pnl, 2)
        trade_info.unrealized_pnl_pct = round(unrealized_pnl_pct, 2)

        logger.info(f"✅ [计算浮动盈亏] {trade_info.code}:")
        logger.info(f"   - 当前价格: {current_price}")
        logger.info(f"   - 成本价: {trade_info.avg_buy_price}")
        logger.info(f"   - 持仓数量: {trade_info.remaining_quantity}")
        logger.info(f"   - 浮动盈亏: {unrealized_pnl:.2f} 元 ({unrealized_pnl_pct:.2f}%)")

        return trade_info

    async def _get_trading_system(self, user_id: str, trading_system_id: str) -> Optional[Dict[str, Any]]:
        """获取交易计划信息"""
        try:
            from bson import ObjectId
            logger.info(f"📋 [Get a trading plan] user_id={user_id}, trading_system_id={trading_system_id}")

            system = await self.db[self.trading_systems_collection].find_one({
                "_id": ObjectId(trading_system_id),
                "user_id": user_id
            })

            if system:
                logger.info(f"✅ [Get a trading plan] successfully obtained: {system.get('name', 'N/A')}")
                logger.info(f"   - 风格: {system.get('style', 'N/A')}")
                logger.info(f"   - 选股规则: {len(system.get('stock_selection', {}).get('must_have', []))} 条必须满足")
                logger.info(f"   - 择时规则: {len(system.get('timing', {}).get('entry_signals', []))} 条入场信号")
                logger.info(f"   - 纪律规则: {len(system.get('discipline', {}).get('must_do', []))} 条必须做到")
            else:
                logger.warning(f"⚠️ [Get a trading plan] Trading plan not found: {trading_system_id}")

            return system
        except Exception as e:
            logger.warning(f"❌ [Get a trading plan] Failed to obtain: {e}")
            return None

    # ==================== Transaction review ====================

    async def create_trade_review(
        self,
        user_id: str,
        request: CreateTradeReviewRequest,
        progress_callback: Optional[Callable] = None  # 🔥 New parameters
    ) -> TradeReviewResponse:
        """创建交易复盘"""
        review_id = str(uuid.uuid4())

        # 1. Get transaction records
        trade_records = await self._get_trade_records(user_id, request.trade_ids, request.source)
        if not trade_records:
            raise ValueError("未找到指定的交易记录")

        # 2. Build transaction information
        trade_info = self._build_trade_info(trade_records, request.code)

        # 🆕 2.5. If the transaction is a holding position, calculate the floating profit and loss
        if trade_info.is_holding:
            logger.info(f"📊 [Create review] Detect transactions in positions and calculate floating profit and loss...")
            trade_info = await self._calculate_unrealized_pnl(trade_info)

        # 3. Get trading plan information (if a trading plan is associated)
        trading_system_name = None
        if request.trading_system_id:
            trading_system = await self._get_trading_system(user_id, request.trading_system_id)
            if trading_system:
                trading_system_name = trading_system.get("name")

        # 4. Create review report
        # Unify the source field:real -> position, paper -> paper
        source = request.source or "paper"
        if source == "real":
            source = "position"  # Uniformly use position to represent position operations

        report = TradeReviewReport(
            review_id=review_id,
            user_id=user_id,
            review_type=request.review_type,
            trade_info=trade_info,
            source=source,  # Set data source
            trading_system_id=request.trading_system_id,
            trading_system_name=trading_system_name,
            status=ReviewStatus.PROCESSING
        )
        
        # 4. Save initial report
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        await self.db[self.trade_reviews_collection].insert_one(report_dict)
        
        try:
            start_time = datetime.now()
            
            # 5. Get a snapshot of market data
            market_snapshot = await self._get_market_snapshot(
                code=trade_info.code,
                market=trade_info.market,
                first_buy_date=trade_info.first_buy_date,
                last_sell_date=trade_info.last_sell_date
            )
            
            # 6. Get trading plan information (if a trading plan is associated)
            trading_system = None
            if request.trading_system_id:
                trading_system = await self._get_trading_system(user_id, request.trading_system_id)

            # 7. Call AI analysis (pass in user_id, trading plan and analysis version)
            ai_review = await self._call_ai_trade_review(
                trade_info,
                market_snapshot,
                user_id=user_id,
                trading_system=trading_system,
                use_workflow=request.use_workflow,
                progress_callback=progress_callback  # 🔥 Pass progress callback
            )
            ai_review = self._sanitize_trade_review_result(ai_review)
            
            execution_time = (datetime.now() - start_time).total_seconds()

            # 🔍 Verbose log: Check ai_review object
            logger.info(f"🔍 [Create review] ai_review Type: {type(ai_review)}")
            logger.info(f"🔍 [Create review] ai_review.plan_adherence: {ai_review.plan_adherence}")
            logger.info(f"🔍 [Create review] ai_review.plan_deviation: {ai_review.plan_deviation}")

            ai_review_dict = ai_review.model_dump()
            logger.info(f"🔍 [Create review] ai_review_dict key: {list(ai_review_dict.keys())}")
            logger.info(f"🔍 [Create review] ai_review_dict['plan_adherence']: {ai_review_dict.get('plan_adherence')}")
            logger.info(f"🔍 [Create review] ai_review_dict['plan_deviation']: {ai_review_dict.get('plan_deviation')}")

            # 8. update report
            await self.db[self.trade_reviews_collection].update_one(
                {"review_id": review_id},
                {"$set": {
                    "market_snapshot": market_snapshot.model_dump(),
                    "ai_review": ai_review.model_dump(),
                    "status": ReviewStatus.COMPLETED.value,
                    "execution_time": execution_time
                }}
            )

            logger.info(f"✅ 交易复盘完成: {review_id}, 股票: {trade_info.code}")

            # v3.6.0 fix: Automatically trigger reflection and refinement after review is completed
            # Note: What is triggered here is structured lesson refining (trade_lesson), not original text writing (trade_pattern)
            # trade_pattern The original text is still written when the user actively "saves to case library"
            try:
                await _reflect_trade_review_lesson(
                    db=self.db,
                    user_id=user_id,
                    trade_info=trade_info,
                    ai_review=ai_review,
                    review_id=review_id,
                )
            except Exception as reflect_exc:
                logger.warning(f"[Create review] Reflection on refining failure (not blocking): {reflect_exc}")

            # 🔍 Detailed log: Check the returned TradeReviewResponse
            response = TradeReviewResponse(
                review_id=review_id,
                status=ReviewStatus.COMPLETED,
                trade_info=trade_info,
                ai_review=ai_review,
                market_snapshot=market_snapshot,
                execution_time=execution_time,
                created_at=report.created_at
            )

            logger.info(f"🔍 [Create review] response.ai_review Type: {type(response.ai_review)}")
            logger.info(f"🔍 [Create review] response.ai_review.plan_adherence: {response.ai_review.plan_adherence}")
            logger.info(f"🔍 [Create review] response.ai_review.plan_deviation: {response.ai_review.plan_deviation}")

            return response
            
        except Exception as e:
            logger.error(f"❌ 交易复盘失败: {e}", exc_info=True)
            await self.db[self.trade_reviews_collection].update_one(
                {"review_id": review_id},
                {"$set": {
                    "status": ReviewStatus.FAILED.value,
                    "error_message": str(e)
                }}
            )
            return TradeReviewResponse(
                review_id=review_id,
                status=ReviewStatus.FAILED,
                trade_info=trade_info,
                created_at=report.created_at
            )

    async def create_trade_review_v2(
        self,
        user_id: str,
        request: CreateTradeReviewRequest
    ) -> TradeReviewResponse:
        """Create transaction review v2.0 - using unified task engine

        Advantages:
        - Support multi-engine switching (workflow/legacy/llm)
        - Unified task management and progress tracking
        - Automatically select the best engine
        - Tasks can be queried and canceled

        Args:
            user_id: User ID
            request: Review request

        Returns:
            Review report response
        """
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType
        from app.models.user import PyObjectId

        review_id = str(uuid.uuid4())

        logger.info(f"🚀 [Transaction review v2.0] Create a review using the unified task engine: {review_id}")

        # 1. Get transaction records
        trade_records = await self._get_trade_records(user_id, request.trade_ids, request.source)
        if not trade_records:
            raise ValueError("未找到指定的交易记录")

        # 2. Build transaction information
        trade_info = self._build_trade_info(trade_records, request.code)

        # 2.5. If the transaction is a holding position, calculate the floating profit and loss
        if trade_info.is_holding:
            logger.info(f"📊 [Review v2.0] Detect transactions in positions and calculate floating profit and loss...")
            trade_info = await self._calculate_unrealized_pnl(trade_info)

        # 3. Get trading plan information
        trading_system_name = None
        trading_system = None
        if request.trading_system_id:
            trading_system = await self._get_trading_system(user_id, request.trading_system_id)
            if trading_system:
                trading_system_name = trading_system.get("name")

        # 4. Unify source field
        source = request.source or "paper"
        if source == "real":
            source = "position"

        # 5. Create initial report
        report = TradeReviewReport(
            review_id=review_id,
            user_id=user_id,
            review_type=request.review_type,
            trade_info=trade_info,
            source=source,
            trading_system_id=request.trading_system_id,
            trading_system_name=trading_system_name,
            status=ReviewStatus.PROCESSING
        )

        # Save initial report
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        await self.db[self.trade_reviews_collection].insert_one(report_dict)

        try:
            # 6. Get a snapshot of market data
            market_snapshot = await self._get_market_snapshot(
                code=trade_info.code,
                market=trade_info.market,
                first_buy_date=trade_info.first_buy_date,
                last_sell_date=trade_info.last_sell_date
            )

            # 7. Prepare task parameters
            task_params = {
                "review_id": review_id,
                "code": trade_info.code,
                "market": trade_info.market,
                "trade_info": trade_info.model_dump(),
                "market_snapshot": market_snapshot.model_dump(),
                "trading_system": trading_system,
                "review_type": request.review_type
            }

            # 8. Use unified task engine
            task_service = get_task_analysis_service()

            # Get engine type and preferences
            engine_type = "workflow" if request.use_workflow else "auto"
            # 🔥 Read risk preference settings from user preferences
            from app.routers.analysis import get_user_risk_preference
            preference_type = await get_user_risk_preference(user_id)
            logger.info(f"📊 [Review analysis service] Use user risk preferences: {preference_type}")

            # Create and execute tasks
            task = await task_service.create_and_execute_task(
                user_id=PyObjectId(user_id),
                task_type=AnalysisTaskType.TRADE_REVIEW,
                task_params=task_params,
                engine_type=engine_type,
                preference_type=preference_type
            )

            # 9. Extract AI review from task results
            if task.result and "ai_review" in task.result:
                ai_review = self._sanitize_trade_review_result(
                    AITradeReview(**task.result["ai_review"])
                )
            else:
                raise ValueError("ai_review data is missing from task results")

            # 10. update report
            await self.db[self.trade_reviews_collection].update_one(
                {"review_id": review_id},
                {"$set": {
                    "market_snapshot": market_snapshot.model_dump(),
                    "ai_review": ai_review.model_dump(),
                    "status": ReviewStatus.COMPLETED.value,
                    "execution_time": task.execution_time
                }}
            )

            logger.info(f"✅ [交易复盘v2.0] 复盘完成: {review_id}, 任务ID: {task.task_id}")

            # v3.6.0 fix: Automatically trigger reflection and refinement after review is completed
            try:
                await _reflect_trade_review_lesson(
                    db=self.db,
                    user_id=user_id,
                    trade_info=trade_info,
                    ai_review=ai_review,
                    review_id=review_id,
                )
            except Exception as reflect_exc:
                logger.warning(f"[Review v2.0] Reflection on refining failure (not blocking): {reflect_exc}")

            # 11. Return response
            return TradeReviewResponse(
                review_id=review_id,
                status=ReviewStatus.COMPLETED,
                trade_info=trade_info,
                ai_review=ai_review,
                market_snapshot=market_snapshot,
                execution_time=task.execution_time,
                created_at=report.created_at
            )

        except Exception as e:
            logger.error(f"❌ [Transaction review v2.0] Review failed: {e}", exc_info=True)

            # Update report status is failed
            await self.db[self.trade_reviews_collection].update_one(
                {"review_id": review_id},
                {"$set": {
                    "status": ReviewStatus.FAILED.value,
                    "error_message": str(e)
                }}
            )

            return TradeReviewResponse(
                review_id=review_id,
                status=ReviewStatus.FAILED,
                trade_info=trade_info,
                created_at=report.created_at
            )

    async def _get_trade_records(
        self,
        user_id: str,
        trade_ids: List[str],
        source: str = "paper"
    ) -> List[Dict[str, Any]]:
        """Get transaction records

        Args:
            user_id: User ID
            trade_ids: Transaction ID list
            source: data source (real=User positions, paper=Simulated position)
        """
        # Transaction record uses ObjectId as _id
        object_ids = []
        for tid in trade_ids:
            try:
                object_ids.append(ObjectId(tid))
            except Exception:
                logger.warning(f"无效的交易ID: {tid}")

        if not object_ids:
            return []

        # Select collection based on source
        if source == "real":
            # User positions: get and convert from position_changes
            collection = "position_changes"
            logger.info(f"📊 从 position_changes 获取交易记录: {len(object_ids)} 条")
        else:
            # Simulated position: obtained from paper_trades
            collection = self.paper_trades_collection
            logger.info(f"📊 从 paper_trades 获取交易记录: {len(object_ids)} 条")

        cursor = self.db[collection].find({
            "user_id": user_id,
            "_id": {"$in": object_ids}
        })
        records = await cursor.to_list(None)

        # If it is a user position, the format needs to be converted
        if source == "real":
            converted_records = []
            for c in records:
                change_type = c.get("change_type")
                side = "buy" if change_type in ["buy", "add"] else "sell"
                quantity = abs(c.get("quantity_change", 0))
                price = c.get("trade_price") or c.get("cost_price_after", 0)

                # Handle pnl: make sure it is a number
                pnl = c.get("realized_profit")
                if pnl is None:
                    pnl = 0.0

                # Handle timestamp: convert to ISO format string
                created_at = c.get("created_at")
                timestamp_str = created_at.isoformat() if created_at else ""

                # Processing timestamp: use trade_time (actual transaction time) first, followed by created_at (record creation time)
                trade_time = c.get("trade_time")
                created_at = c.get("created_at")

                # 🔥 Helper function: safely convert datetime or string to ISO format string
                def to_iso_str(dt_value):
                    if not dt_value:
                        return ""
                    if isinstance(dt_value, str):
                        try:
                            # Try to parse ISO format string
                            dt_obj = datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
                            return dt_obj.isoformat()
                        except (ValueError, AttributeError):
                            # If parsing fails, try other formats
                            try:
                                dt_obj = datetime.strptime(dt_value, "%Y-%m-%d %H:%M:%S")
                                return dt_obj.isoformat()
                            except ValueError:
                                logger.warning(f"⚠️ 无法解析时间格式: {dt_value}")
                                return dt_value  # Return original string
                    elif isinstance(dt_value, datetime):
                        return dt_value.isoformat()
                    else:
                        return str(dt_value)

                # Use trade_time first, if not available then use created_at
                if trade_time:
                    timestamp_str = to_iso_str(trade_time)
                else:
                    timestamp_str = to_iso_str(created_at)

                converted_records.append({
                    "_id": c.get("_id"),
                    "code": c.get("code"),
                    "name": c.get("name"),  # Add stock name
                    "market": c.get("market", "CN"),
                    "side": side,
                    "quantity": quantity,
                    "price": float(price) if price else 0.0,
                    "amount": float(quantity * price) if price else 0.0,
                    "pnl": float(pnl),
                    "commission": 0.0,
                    "timestamp": timestamp_str  # ISO Format string (using transaction time)
                })
            return converted_records

        return records

    def _build_trade_info(
        self,
        trade_records: List[Dict[str, Any]],
        code: Optional[str] = None
    ) -> TradeInfo:
        """构建交易信息"""
        if not trade_records:
            return TradeInfo(code=code or "")

        def _parse_trade_time(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str) and value:
                normalized = value.replace('Z', '+00:00')
                try:
                    return datetime.fromisoformat(normalized)
                except ValueError:
                    try:
                        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        return datetime.max
            return datetime.max

        trade_records = sorted(
            trade_records,
            key=lambda record: _parse_trade_time(record.get("timestamp"))
        )

        # Print entered transaction records (for debugging)
        logger.info(f"📊 [_build_trade_info] 收到 {len(trade_records)} 笔交易记录")
        for i, record in enumerate(trade_records):
            logger.info(f"  记录 {i+1}: side={record.get('side')}, qty={record.get('quantity')}, "
                       f"price={record.get('price')}, pnl={record.get('pnl')}, "
                       f"timestamp={record.get('timestamp')}")

        # Use the stock information from the first record
        first_trade = trade_records[0]
        stock_code = code or first_trade.get("code", "")
        stock_name = first_trade.get("name") or first_trade.get("stock_name")  # Try to get the stock name from the record
        market = first_trade.get("market", "CN")
        currency = first_trade.get("currency", "CNY")

        # Build transaction list
        trades = []
        total_buy_qty = 0
        total_buy_amount = 0.0
        total_sell_qty = 0
        total_sell_amount = 0.0
        total_pnl = 0.0
        total_commission = 0.0

        buy_timestamps = []
        sell_timestamps = []

        for record in trade_records:
            trade = TradeRecord(
                trade_id=str(record.get("_id", "")),
                side=record.get("side", ""),
                quantity=record.get("quantity", 0),
                price=record.get("price", 0.0),
                amount=record.get("amount", 0.0),
                commission=record.get("commission", 0.0),
                timestamp=record.get("timestamp", ""),
                pnl=record.get("pnl", 0.0)
            )
            trades.append(trade)

            if trade.timestamp:
                if trade.side == "buy":
                    buy_timestamps.append(trade.timestamp)
                elif trade.side == "sell":
                    sell_timestamps.append(trade.timestamp)

            total_commission += trade.commission

            if trade.side == "buy":
                total_buy_qty += trade.quantity
                total_buy_amount += trade.amount
            else:
                total_sell_qty += trade.quantity
                total_sell_amount += trade.amount
                total_pnl += trade.pnl
                logger.info(f"  累加卖出 pnl: {trade.pnl}, 累计 total_pnl: {total_pnl}")

        # Calculate average price
        avg_buy_price = total_buy_amount / total_buy_qty if total_buy_qty > 0 else 0.0
        avg_sell_price = total_sell_amount / total_sell_qty if total_sell_qty > 0 else 0.0

        # Calculate profit and loss percentage
        pnl_pct = (total_pnl / total_buy_amount * 100) if total_buy_amount > 0 else 0.0

        logger.info(f"📊 [_build_trade_info] Statistical results:")
        logger.info(f"  - total_buy_amount: {total_buy_amount}")
        logger.info(f"  - total_sell_amount: {total_sell_amount}")
        logger.info(f"  - total_pnl: {total_pnl}")
        logger.info(f"  - pnl_pct: {pnl_pct}%")

        # 🆕 Calculate position status
        remaining_quantity = total_buy_qty - total_sell_qty
        is_holding = remaining_quantity > 0
        
        # Calculate position holding days
        buy_timestamps.sort()
        sell_timestamps.sort()
        first_buy_date = buy_timestamps[0] if buy_timestamps else None
        last_sell_date = sell_timestamps[-1] if sell_timestamps else None
        
        holding_days = 0
        if first_buy_date:
            try:
                from app.utils.timezone import now_tz, ensure_timezone
                
                # Parse date string, ensuring time zone
                first_dt_str = first_buy_date.replace('Z', '+00:00')
                if '+' in first_dt_str or first_dt_str.endswith('Z'):
                    # ISO format with time zone
                    first_dt = datetime.fromisoformat(first_dt_str.replace('Z', '+00:00'))
                else:
                    # Format without time zone, parse first and then add time zone
                    first_dt = datetime.fromisoformat(first_dt_str.split('+')[0])
                    first_dt = ensure_timezone(first_dt)
                
                if is_holding:
                    # 🔥 Open position: from the first purchase to the current date
                    current_dt = now_tz()
                    holding_days = (current_dt - first_dt).days
                    logger.info(f"📊 [持仓天数] 持仓中交易，从 {first_buy_date} 到当前: {holding_days} 天")
                else:
                    # Closed position: from the first purchase to the last sale
                    if last_sell_date:
                        last_dt_str = last_sell_date.replace('Z', '+00:00')
                        if '+' in last_dt_str or last_dt_str.endswith('Z'):
                            last_dt = datetime.fromisoformat(last_dt_str.replace('Z', '+00:00'))
                        else:
                            last_dt = datetime.fromisoformat(last_dt_str.split('+')[0])
                            last_dt = ensure_timezone(last_dt)
                        holding_days = (last_dt - first_dt).days
                        logger.info(f"📊 [持仓天数] 已平仓交易，从 {first_buy_date} 到 {last_sell_date}: {holding_days} 天")
            except Exception as e:
                logger.warning(f"⚠️ [Position holding days] Calculation failed: {e}", exc_info=True)
                pass

        # 🆕 Calculate floating profit and loss (initial value, actual calculation is in _calculate_unrealized_pnl)
        unrealized_pnl = 0.0
        unrealized_pnl_pct = 0.0
        current_price = None

        if is_holding:
            logger.info(f"📊 [_build_trade_info] 检测到持仓中: 剩余 {remaining_quantity} 股")
            # Get the current price (asynchronous method, obtained when calling _calculate_unrealized_pnl in create_trade_review)

        logger.info(f"📊 [_build_trade_info] Position status:")
        logger.info(f"  - is_holding: {is_holding}")
        logger.info(f"  - remaining_quantity: {remaining_quantity}")
        logger.info(f"  - realized_pnl: {total_pnl}")
        logger.info(f"  - unrealized_pnl: {unrealized_pnl} (待计算)")

        return TradeInfo(
            code=stock_code,
            name=stock_name,  # Add stock name
            market=market,
            currency=currency,
            trades=trades,
            total_buy_quantity=total_buy_qty,
            total_buy_amount=round(total_buy_amount, 2),
            avg_buy_price=round(avg_buy_price, 4),
            total_sell_quantity=total_sell_qty,
            total_sell_amount=round(total_sell_amount, 2),
            avg_sell_price=round(avg_sell_price, 4),
            realized_pnl=round(total_pnl, 2),
            realized_pnl_pct=round(pnl_pct, 2),
            unrealized_pnl=round(unrealized_pnl, 2),  # 🆕
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2),  # 🆕
            total_commission=round(total_commission, 2),
            is_holding=is_holding,  # 🆕
            current_price=current_price,  # 🆕
            remaining_quantity=remaining_quantity,  # 🆕
            first_buy_date=first_buy_date,
            last_sell_date=last_sell_date,
            holding_days=holding_days
        )

    async def _build_trade_info_with_tools(
        self,
        trade_records: List[Dict[str, Any]],
        user_id: str,
        code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build complete transaction information (including account information) using v2.0 tools

        This method uses the v2.0 tool system to obtain data, which conforms to the system architecture.
        """
        if not TOOLS_AVAILABLE:
            logger.warning("⚠️ v2.0 Tools unavailable, traditional methods used")
            trade_info = self._build_trade_info(trade_records, code)
            return trade_info.model_dump()

        try:
            # Build transaction information using v2.0 tools
            trade_info_result = tool_build_trade_info(trade_records, code)

            if not trade_info_result.get("success"):
                logger.warning(f"⚠️ 构建交易信息失败: {trade_info_result.get('error')}")
                trade_info = self._build_trade_info(trade_records, code)
                return trade_info.model_dump()

            trade_info_data = trade_info_result.get("data", {})

            # Use v2.0 tools to obtain account information
            account_result = await tool_get_account_info(user_id)

            if account_result.get("success"):
                account_info = account_result.get("data", {})
                trade_info_data["account_info"] = account_info
                logger.info(f"✅ Account information has been added to transaction information")
            else:
                logger.warning(f"⚠️ 获取账户信息失败: {account_result.get('error')}")

            return trade_info_data

        except Exception as e:
            logger.error(f"❌ Failed to build transaction information using v2.0 tool: {e}")
            trade_info = self._build_trade_info(trade_records, code)
            return trade_info.model_dump()

    async def _get_market_snapshot(
        self,
        code: str,
        market: str,
        first_buy_date: Optional[str],
        last_sell_date: Optional[str]
    ) -> MarketSnapshot:
        """获取市场数据快照"""
        snapshot = MarketSnapshot()

        if not first_buy_date:
            return snapshot

        try:
            # parse date
            start_date = datetime.fromisoformat(first_buy_date.replace('Z', '+00:00').split('+')[0])
            end_date = datetime.fromisoformat(last_sell_date.replace('Z', '+00:00').split('+')[0]) if last_sell_date else datetime.now()

            # Extended date range (10 days before and after)
            query_start = (start_date - timedelta(days=10)).strftime("%Y-%m-%d")
            query_end = (end_date + timedelta(days=10)).strftime("%Y-%m-%d")

            # Get K-line data
            kline_data = await self._get_kline_data(code, market, query_start, query_end)

            if kline_data:
                snapshot.kline_data = kline_data

                # Find the highest and lowest price during the holding period
                period_start = start_date.strftime("%Y-%m-%d")
                period_end = end_date.strftime("%Y-%m-%d")

                period_klines = [k for k in kline_data if period_start <= k.get("date", "") <= period_end]

                if period_klines:
                    # Find the highest price
                    max_kline = max(period_klines, key=lambda x: x.get("high", 0))
                    snapshot.period_high = max_kline.get("high")
                    snapshot.period_high_date = max_kline.get("date")

                    # Find the lowest price
                    min_kline = min(period_klines, key=lambda x: x.get("low", float('inf')))
                    snapshot.period_low = min_kline.get("low")
                    snapshot.period_low_date = min_kline.get("date")

                    # Best buying and selling point
                    snapshot.optimal_buy_price = snapshot.period_low
                    snapshot.optimal_sell_price = snapshot.period_high

                # Buy the current day's price
                buy_date_str = start_date.strftime("%Y-%m-%d")
                buy_kline = next((k for k in kline_data if k.get("date") == buy_date_str), None)
                if buy_kline:
                    snapshot.buy_date_open = buy_kline.get("open")
                    snapshot.buy_date_high = buy_kline.get("high")
                    snapshot.buy_date_low = buy_kline.get("low")
                    snapshot.buy_date_close = buy_kline.get("close")

                # Sell the day's price
                if last_sell_date:
                    sell_date_str = end_date.strftime("%Y-%m-%d")
                    sell_kline = next((k for k in kline_data if k.get("date") == sell_date_str), None)
                    if sell_kline:
                        snapshot.sell_date_open = sell_kline.get("open")
                        snapshot.sell_date_high = sell_kline.get("high")
                        snapshot.sell_date_low = sell_kline.get("low")
                        snapshot.sell_date_close = sell_kline.get("close")

        except Exception as e:
            logger.error(f"获取市场快照失败: {e}", exc_info=True)

        return snapshot

    async def _get_kline_data(
        self,
        code: str,
        market: str,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """获取K线数据"""
        try:
            # Get historical K-line from database
            cursor = self.db["stock_daily_history"].find({
                "code": code,
                "date": {"$gte": start_date, "$lte": end_date}
            }).sort("date", 1)

            klines = await cursor.to_list(None)

            if klines:
                return [
                    {
                        "date": k.get("date"),
                        "open": k.get("open"),
                        "high": k.get("high"),
                        "low": k.get("low"),
                        "close": k.get("close"),
                        "volume": k.get("volume")
                    }
                    for k in klines
                ]

            # If the database does not exist, try to use the unified interface to obtain it.
            logger.info(f"There is no K-line data in the database. Try to obtain it from the unified interface.: {code} ({market})")
            return await self._fetch_kline_unified(code, market, start_date, end_date)

        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            return []

    async def _fetch_kline_unified(
        self,
        code: str,
        market: str,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Obtain K-line data from the unified interface (supports A shares, Hong Kong stocks, and US stocks)"""
        try:
            # Automatically identify markets
            market_info = StockUtils.get_market_info(code)
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']
            is_china = market_info['is_china']
            
            logger.info(f"🔄 [统一K线获取] 股票: {code}, 市场识别: {market_info['market_name']}")

            df = None

            if is_hk:
                # Hong Kong stocks
                provider = get_improved_hk_provider()
                df = provider.get_daily_data(code, start_date, end_date)
            
            elif is_us:
                # US stocks
                provider = get_optimized_us_data_provider()
                df = provider.get_daily_data(code, start_date, end_date)
                
            elif is_china or market == 'CN':
                # A shares (Keep the original akshare logic)
                import akshare as ak
                start = start_date.replace("-", "")
                end = end_date.replace("-", "")
                
                # Try using akshare to get
                try:
                    df_ak = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust="qfq"
                    )
                    if df_ak is not None and not df_ak.empty:
                        # Unified listing
                        df = df_ak.rename(columns={
                            "日期": "date",
                            "开盘": "open",
                            "最高": "high",
                            "最低": "low",
                            "收盘": "close",
                            "成交量": "volume"
                        })
                        df['date'] = df['date'].astype(str)
                except Exception as e:
                    logger.error(f"akshare Failed to obtain A-share data: {e}")
            
            # Process the returned DataFrame
            if df is not None and not df.empty:
                klines = []
                # Make sure column names are lowercase
                df.columns = [c.lower() for c in df.columns]
                
                for _, row in df.iterrows():
                    try:
                        kline = {
                            "date": str(row.get("date", "")),
                            "open": float(row.get("open", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "close": float(row.get("close", 0)),
                            "volume": float(row.get("volume", 0))
                        }
                        # Filter invalid dates
                        if len(kline["date"]) >= 10:
                            kline["date"] = kline["date"][:10]
                            klines.append(kline)
                    except Exception as row_e:
                        continue
                        
                logger.info(f"✅ [统一K线获取] 成功获取 {len(klines)} 条数据: {code}")
                return klines
                
        except Exception as e:
            logger.error(f"❌ [Unified K-line acquisition] failed: {code} - {e}")

        return []

    async def _call_ai_trade_review(
        self,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot,
        user_id: Optional[str] = None,
        trading_system: Optional[Dict[str, Any]] = None,
        use_workflow: Optional[bool] = None,
        progress_callback: Optional[Callable] = None  # 🔥 New parameters
    ) -> AITradeReview:
        """Call AI for transaction review analysis

        If the workflow engine is enabled (USE_WORKFLOW_REVIEW=true or use_workflow=True) , Using multi-agent workflow analysis
        Otherwise use a single LLM call to analyze

        Args:
            trade_info: transaction information
            market_snapshot: market snapshot
            user_id: User ID
            trading_system: Associated trading plan (if any)
            use_workflow: Whether to use a workflow engine. None means use environment variable settings
        """
        # Determine whether to use the workflow engine (request parameters take precedence over environment variables)
        should_use_workflow = use_workflow if use_workflow is not None else _use_workflow_review()

        if should_use_workflow:
            try:
                logger.info(f"🔄 [Transaction review] Use workflow engines for multi-dimensional analysis (v2.0)")
                return await self._call_workflow_trade_review(
                    trade_info, market_snapshot, user_id, trading_system,
                    progress_callback=progress_callback  # 🔥 Pass progress callback
                )
            except Exception as e:
                import traceback
                logger.warning(f"⚠️ [Transaction review] Workflow engine execution fails and is downgraded to a single LLM call: {e}")
                logger.warning(f"⚠️ [Transaction review] Full stack trace:\n{traceback.format_exc()}")
                # Downgrade to a single LLM call

        logger.info(f"📝 [Transaction review] Use traditional analysis methods (v1.0)")

        try:
            # If the template system is enabled, first obtain market and industry benchmark data
            benchmark_data = None
            if _use_template_prompts():
                try:
                    benchmark_data = await self._get_benchmark_data(
                        stock_code=trade_info.code,
                        market=trade_info.market,
                        start_date=trade_info.first_buy_date[:10] if trade_info.first_buy_date else "",
                        end_date=trade_info.last_sell_date[:10] if trade_info.last_sell_date else ""
                    )
                    logger.info(f"📊 [Transaction review] Obtaining benchmark data is completed")
                except Exception as e:
                    logger.warning(f"⚠️ [Transaction review] Failed to obtain benchmark data: {e}")

            prompt = self._build_trade_review_prompt(
                trade_info, market_snapshot, user_id, benchmark_data, trading_system
            )

            # Use unified LLM adapter
            from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
            from tradingagents.graph.trading_graph import create_llm_by_provider

            model_name = "qwen-plus"
            provider_info = get_provider_and_url_by_model_sync(model_name)

            logger.info(f"🏭 [AI Review] model supplier: {provider_info.get('provider', 'unknown')}")
            logger.info(f"🔗 [AI Review] API address: {provider_info.get('backend_url', 'Not configured')}")
            logger.info(f"🔑 [AI Review] API Key: {'configured' if provider_info.get('api_key') else 'Not configured'}")
            logger.info(f"📝 [AI复盘] Prompt长度: {len(prompt)} 字符")
            logger.info(f"📝 [AI Review] Prompt first 500 characters:\n{prompt[:500]}")

            # Create an instance using the unified LLM adapter
            logger.info(f"🔧 [AI Review] Start creating an LLM instance...")
            llm = create_llm_by_provider(
                provider=provider_info.get("provider", "dashscope"),
                model=model_name,
                backend_url=provider_info.get("backend_url"),
                temperature=0.3,
                max_tokens=4000,
                timeout=120,
                api_key=provider_info.get("api_key")
            )
            logger.info(f"✅ [AI Review] LLM Instance created successfully: {type(llm).__name__}")

            # asynchronous call LLM
            logger.info(f"🚀 [AI Review] Start calling LLM API...")
            response = await llm.ainvoke(prompt)

            # Record token usage
            try:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=response,
                    session_id=user_id or "trade_review",
                    analysis_type="trade_review",
                    stock_code=trade_info.code
                )
            except Exception as e:
                logger.warning(f"Record token usage failure: {e}")

            logger.info(f"✅ [AI Review] LLM API Call successful")
            logger.info(f"📦 [AI Review] Response Type: {type(response).__name__}")
            logger.info(f"📦 [AI Review] Response Properties: {dir(response)}")

            content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📄 [AI复盘] 返回内容长度: {len(content)} 字符")
            logger.info(f"📄 [AI Review] Return the first 500 characters of the content:\n{content[:500]}")
            logger.info(f"📄 [AI Review] Return 500 characters after content:\n{content[-500:]}")

            logger.info(f"🔍 [AI Review] Start parsing AI responses...")
            result = self._parse_ai_trade_review(content, trade_info, market_snapshot)
            logger.info(f"✅ [AI复盘] 解析完成 - 总分: {result.overall_score}, 摘要长度: {len(result.summary)}")

            return self._sanitize_trade_review_result(result)

        except Exception as e:
            logger.error(f"AI复盘分析失败: {e}", exc_info=True)
            from app.utils.error_formatter import ErrorFormatter

            return self._sanitize_trade_review_result(AITradeReview(
                summary=f"AI Analysis is temporarily unavailable:{ErrorFormatter.format_user_message(str(e))}",
                overall_score=50
            ))



    def _build_trade_review_prompt(
        self,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot,
        user_id: Optional[str] = None,
        benchmark_data: Optional[Dict[str, Any]] = None,
        trading_system: Optional[Dict[str, Any]] = None
    ) -> str:
        """Construct transaction review prompts

        Support template system (controlled by USE_TEMPLATE_PROMPTS feature switch)

        Args:
            trade_info: transaction information
            market_snapshot: market snapshot
            user_id: User ID (used in the template system)
            benchmark_data: Market and industry benchmark data (from index_analyst + sector_analyst) 
            trading_system: Associated trading plan (if any)
        """
        # Build a hardcoded version first as a fallback for downgrades
        legacy_prompt = self._build_legacy_trade_review_prompt(
            trade_info, market_snapshot, benchmark_data, trading_system
        )

        # If the template system is enabled, try to use templates to generate prompt words
        if _use_template_prompts():
            try:
                from tradingagents.utils.template_client import get_agent_prompt

                variables = self._build_trade_review_vars(trade_info, market_snapshot)

                # If there is baseline data, fill it into the variable
                if benchmark_data:
                    variables["market_benchmark"] = benchmark_data.get("market_benchmark", {})
                    variables["industry_benchmark"] = benchmark_data.get("industry_benchmark", {})
                    variables["attribution"] = benchmark_data.get("attribution", {})

                logger.info(f"📝 [Transaction review] Prepare to call the template system, the number of variables: {len(variables)}")
                logger.info(f"📝 [Transaction review] variable key: {list(variables.keys())}")

                prompt = get_agent_prompt(
                    agent_type="managers",
                    agent_name="trade_reviewer",
                    variables=variables,
                    user_id=user_id,
                    preference_id="neutral",  # Review analysis uses neutral style by default
                    fallback_prompt=legacy_prompt
                )

                if prompt and prompt != legacy_prompt:
                    logger.info(f"✅ [Transaction review] Use template system to generate prompt words (length: {len(prompt)})")
                    logger.info(f"📝 [Transaction review] The first 500 characters of the prompt word:\n{prompt[:500]}")
                    logger.info(f"📝 [Transaction review] 500 characters after the prompt word:\n{prompt[-500:]}")
                    return self._append_review_guardrails(prompt)

            except Exception as e:
                logger.warning(f"⚠️ [Transaction review] Template system call failed with hardcoded prompt word: {e}")

        return self._append_review_guardrails(legacy_prompt)

    def _build_legacy_trade_review_prompt(
        self,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot,
        benchmark_data: Optional[Dict[str, Any]] = None,
        trading_system: Optional[Dict[str, Any]] = None
    ) -> str:
        """Construct hard-coded transaction review prompt words (old version, as a cover for downgrade)

        Args:
            trade_info: transaction information
            market_snapshot: market snapshot
            benchmark_data: Market and industry benchmark data (optional)
            trading_system: Associated trading plan (optional)
        """
        # Transaction record details
        trades_detail = ""
        for t in trade_info.trades:
            trades_detail += f"- {t.timestamp[:10]} {t.side.upper()} {t.quantity}股 @ {t.price}元"
            if t.pnl != 0:
                trades_detail += f" (盈亏: {t.pnl}元)"
            trades_detail += "\n"

        # K Line data summary (last 10 items)
        kline_summary = ""
        if market_snapshot.kline_data:
            recent_klines = market_snapshot.kline_data[-20:]
            for k in recent_klines:
                kline_summary += f"  {k['date']}: 开{k['open']:.2f} 高{k['high']:.2f} 低{k['low']:.2f} 收{k['close']:.2f}\n"

        # Construct broad market and industry benchmark information (if available)
        benchmark_section = ""
        if benchmark_data:
            market_bench = benchmark_data.get("market_benchmark", {})
            industry_bench = benchmark_data.get("industry_benchmark", {})
            attribution = benchmark_data.get("attribution", {})

            if market_bench.get("change_pct") is not None:
                benchmark_section += f"""
## 大盘与行业基准

### 大盘表现（{market_bench.get('index_name', '沪深300')}）
- 持仓期间涨跌幅: {market_bench.get('change_pct', 'N/A')}%
- 期间最高: {market_bench.get('period_high', 'N/A')}
- 期间最低: {market_bench.get('period_low', 'N/A')}
"""

            if industry_bench.get("industry_name"):
                benchmark_section += f"""
### 行业表现
- 所属行业: {industry_bench.get('industry_name', 'N/A')}
- 行业涨跌幅: {industry_bench.get('change_pct', 'N/A') or '暂无数据'}%
- 相对大盘超额: {industry_bench.get('vs_market', 'N/A') or '暂无数据'}%
"""

            if attribution.get("beta_contribution") is not None:
                benchmark_section += f"""
### Revenue Attribution (Preliminary)
- Market contribution(Beta): {attribution.get('beta_contribution', 'N/A')}%
- industry excess: {attribution.get('industry_excess', 'N/A') or 'To be calculated'}%
- individual stocks Alpha: {attribution.get('alpha', 'N/A') or 'To be calculated'}%
"""

        # Building a trading plan rules section
        trading_system_section = ""
        if trading_system:
            trading_system_section = f"""
## Associated trading plans

This transaction is associated with a trading plan:**{trading_system.get('name', 'Unnamed')}**

### trading plan rules

"""
            # Add stock selection rules
            stock_selection = trading_system.get('stock_selection', {})
            if stock_selection:
                trading_system_section += "**选股规则**:\n"
                must_meet = stock_selection.get('must_meet', [])
                if must_meet:
                    trading_system_section += "- 必须满足: " + "; ".join(must_meet) + "\n"
                exclude = stock_selection.get('exclude', [])
                if exclude:
                    trading_system_section += "- 排除条件: " + "; ".join(exclude) + "\n"
                trading_system_section += "\n"

            # Add timing rules
            timing = trading_system.get('timing', {})
            if timing:
                trading_system_section += "**择时规则**:\n"
                entry_signals = timing.get('entry_signals', [])
                if entry_signals:
                    trading_system_section += "- 入场信号: " + "; ".join(entry_signals) + "\n"
                exit_signals = timing.get('exit_signals', [])
                if exit_signals:
                    trading_system_section += "- 出场信号: " + "; ".join(exit_signals) + "\n"
                trading_system_section += "\n"

            # Add position rules
            position = trading_system.get('position', {})
            if position:
                trading_system_section += "**仓位规则**:\n"
                trading_system_section += f"- 单只股票上限: {position.get('single_stock_limit', 'N/A')}%\n"
                trading_system_section += f"- 最大持股数: {position.get('max_stocks', 'N/A')}只\n"
                trading_system_section += "\n"

            # Add risk management rules
            risk_management = trading_system.get('risk_management', {})
            if risk_management:
                trading_system_section += "**风险管理规则**:\n"
                stop_loss = risk_management.get('stop_loss', {})
                if stop_loss:
                    trading_system_section += f"- 止损: {stop_loss.get('type', 'N/A')} {stop_loss.get('value', 'N/A')}\n"
                take_profit = risk_management.get('take_profit', {})
                if take_profit:
                    trading_system_section += f"- 止盈: {take_profit.get('type', 'N/A')} {take_profit.get('value', 'N/A')}\n"
                trading_system_section += "\n"

            # Add disciplinary rules
            discipline = trading_system.get('discipline', {})
            if discipline:
                trading_system_section += "**纪律规则**:\n"
                must_do = discipline.get('must_do', [])
                if must_do:
                    trading_system_section += "- 必须做到: " + "; ".join(must_do) + "\n"
                forbidden = discipline.get('forbidden', [])
                if forbidden:
                    trading_system_section += "- 严禁操作: " + "; ".join(forbidden) + "\n"
                trading_system_section += "\n"

            trading_system_section += "**In the review analysis, please focus on checking whether this transaction complies with the above trading plan rules and point out any violations of the rules.**\n"

        prompt = f"""# 交易复盘分析任务

你是一位专业的交易复盘分析师，请对以下交易进行深入分析。

## 交易信息

- **股票代码**: {trade_info.code}
- **市场**: {trade_info.market}
- **持仓周期**: {trade_info.first_buy_date[:10] if trade_info.first_buy_date else '未知'} 至 {trade_info.last_sell_date[:10] if trade_info.last_sell_date else '未知'}
- **持仓天数**: {trade_info.holding_days} 天

### 交易明细
{trades_detail}

### 交易汇总
- 买入: {trade_info.total_buy_quantity}股，均价 {trade_info.avg_buy_price:.2f}元，金额 {trade_info.total_buy_amount:.2f}元
- 卖出: {trade_info.total_sell_quantity}股，均价 {trade_info.avg_sell_price:.2f}元，金额 {trade_info.total_sell_amount:.2f}元
- **实现盈亏**: {trade_info.realized_pnl:.2f}元 ({trade_info.realized_pnl_pct:.2f}%)
- 手续费: {trade_info.total_commission:.2f}元

## 交易期间行情数据

### 关键价格
- 持仓期间最高价: {market_snapshot.period_high or '未知'}元 (日期: {market_snapshot.period_high_date or '未知'})
- 持仓期间最低价: {market_snapshot.period_low or '未知'}元 (日期: {market_snapshot.period_low_date or '未知'})
- 买入当日: 开{market_snapshot.buy_date_open or '-'} 高{market_snapshot.buy_date_high or '-'} 低{market_snapshot.buy_date_low or '-'} 收{market_snapshot.buy_date_close or '-'}
- 卖出当日: 开{market_snapshot.sell_date_open or '-'} 高{market_snapshot.sell_date_high or '-'} 低{market_snapshot.sell_date_low or '-'} 收{market_snapshot.sell_date_close or '-'}

### K线数据
{kline_summary if kline_summary else '暂无K线数据'}
{benchmark_section}
{trading_system_section}
## 分析要求

请从以下维度分析这笔交易，以JSON格式输出：

```json
{{
    "overall_score": 0-100的整数（兼容保留字段，供内部归档使用）, 
    "timing_score": 0-100的整数（兼容保留字段）, 
    "position_score": 0-100的整数（兼容保留字段）, 
    "discipline_score": 0-100的整数（兼容保留字段）, 

    "summary": "80字以内的复盘结论，直白说明这笔交易最核心的得失与问题",
    "strengths": ["做得好的地方1", "做得好的地方2"],
    "weaknesses": ["需要改进的地方1", "需要改进的地方2"],
    "suggestions": ["后续研究或流程改进重点1", "后续研究或流程改进重点2"],

    "timing_analysis": "买入卖出时机的详细分析（100字以内）",
    "position_analysis": "仓位控制分析（50字以内）",
    "emotion_analysis": "是否存在情绪化操作（50字以内）",

    "market_analysis": "大盘环境对本次交易的影响（50字以内，如有大盘数据）",
    "industry_analysis": "行业因素对本次交易的影响（50字以内，如有行业数据）"
}}
```

**输出要求**：
- 分数字段仅用于兼容旧结构和内部归档，不得让总结围绕评分展开
- summary、weaknesses、suggestions 应优先说明关键问题、成因和后续研究改进重点
- suggestions 只能写成复盘改进重点、研究补强点或流程优化点，不得写成未来买卖、加减仓、止损止盈等执行动作

**收益归因分析要点**：
- 如果个股涨幅 > 大盘涨幅 + 行业超额，说明选股能力较强
- 如果个股涨幅 ≈ 大盘涨幅，说明主要是跟随市场Beta
- 请在分析中区分"运气"（市场/行业贡献）和"能力"（选股/择时Alpha）
"""
        return prompt

    def _parse_ai_trade_review(
        self,
        content: str,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot
    ) -> AITradeReview:
        """Analyze AI review results

        Compatible with two JSON formats:
        1. standard format: overall_score, summary, strengths, weaknesses, suggestions Wait
        2. template format: analysis, improvement_recommendations, score_interpretation Wait
        """
        import re
        import json

        logger.info(f"🔍 [Parse AI responses] Start parsing, content length: {len(content)}")

        result = AITradeReview(actual_pnl=trade_info.realized_pnl)

        # Try to extract JSON
        logger.info(f"🔍 [Parse AI responses] Try to extract JSON code block...")
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)

        if json_match:
            logger.info(f"✅ [Parse AI responses] Find the JSON code block")
            json_str = json_match.group(1)
            logger.info(f"📄 [Parse AI responses] JSON content length: {len(json_str)}")
            logger.info(f"📄 [Parse AI responses] JSON The first 500 characters of the content:\n{json_str[:500]}")

            try:
                data = json.loads(json_str)
                logger.info(f"✅ [Parse AI responses] JSON Parsed successfully")
                logger.info(f"📊 [Parse AI responses] JSON key: {list(data.keys())}")

                # Analytical scoring - compatible with both 0-100 and 1-10 scoring systems
                def normalize_score(score_value, default=50):
                    """Unified scoring conversion logic:1-10 → 0-100"""
                    if isinstance(score_value, (int, float)) and score_value <= 10:
                        return int(score_value * 10)
                    return int(score_value)

                result.overall_score = normalize_score(data.get("overall_score", 0))
                result.timing_score = normalize_score(data.get("timing_score", 0))
                result.position_score = normalize_score(data.get("position_score", 0))
                result.discipline_score = normalize_score(data.get("discipline_score", 0))

                # Parse summary - compatible with a variety of field names
                result.summary = (
                    data.get("summary") or
                    data.get("score_interpretation") or
                    self._extract_nested_field(data, "analysis", "overall_assessment") or
                    ""
                )

                # Parse strengths - Compatible with strengths and analysis.strengths
                result.strengths = (
                    data.get("strengths") or
                    self._extract_nested_field(data, "analysis", "strengths") or
                    []
                )

                # Parsing Weaknesses - Compatible with weaknesses and analysis.weaknesses
                result.weaknesses = (
                    data.get("weaknesses") or
                    self._extract_nested_field(data, "analysis", "weaknesses") or
                    []
                )

                # Parse suggestions - compatible with suggestions and improvement_recommendations
                result.suggestions = (
                    data.get("suggestions") or
                    data.get("improvement_recommendations") or
                    []
                )

                # Analyze detailed analysis
                result.timing_analysis = (
                    data.get("timing_analysis") or
                    self._extract_nested_field(data, "analysis", "timing") or
                    ""
                )
                result.position_analysis = (
                    data.get("position_analysis") or
                    self._extract_nested_field(data, "analysis", "position") or
                    ""
                )
                result.emotion_analysis = (
                    data.get("emotion_analysis") or
                    self._extract_nested_field(data, "analysis", "emotion") or
                    ""
                )

                # 🆕 Analyze the execution of the trading plan (if any)
                result.plan_adherence = data.get("plan_adherence")
                result.plan_deviation = data.get("plan_deviation")

                logger.info(f"✅ [解析AI响应] 解析完成 - 总分: {result.overall_score}, 摘要: {result.summary[:100] if result.summary else '空'}")
                if result.plan_adherence or result.plan_deviation:
                    logger.info(f"✅ [Parse AI responses] Contains trading plan analysis: adherence={bool(result.plan_adherence)}, deviation={bool(result.plan_deviation)}")
                return result

            except json.JSONDecodeError as e:
                logger.warning(f"❌ [Parse AI responses] JSON Parsing failed: {e}")
                logger.warning(f"📄 [Parse AI responses] Failed JSON content:\n{json_str}")
        else:
            logger.warning(f"⚠️ [Parse AI responses] JSON code block not found")
            logger.warning(f"📄 [Parse AI responses] full content:\n{content}")

        result.summary = content[:200] if content else "AI分析完成"
        logger.info(f"⚠️ [Parse AI responses] Complete with alternatives - Summary: {result.summary}")
        return result

    def _extract_nested_field(self, data: Dict[str, Any], *keys) -> Any:
        """Extract field value from nested dictionary

        Args:
            data: data dictionary
            *keys: Nested key paths like ("analysis", "strengths")

        Returns:
            the value found, or None
        """
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    # ==================== Review history query ====================

    async def get_review_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        review_type: Optional[str] = None,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Obtain the review history list and support filtering by stock code, time period, review type, and data source.
        
        Args:
            source: Data source filtering, paper(simulated trading) or position(Position operation), If empty, get all
        """
        skip = (page - 1) * page_size

        # Build query conditions
        query = {"user_id": user_id}

        # Data source filtering
        if source:
            query["source"] = source

        # Stock code filter
        if code:
            query["trade_info.code"] = code

        # Review type filter
        if review_type:
            query["review_type"] = review_type

        # Time period filter
        if start_date or end_date:
            query["created_at"] = {}
            if start_date:
                from datetime import datetime
                query["created_at"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                from datetime import datetime
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query["created_at"]["$lte"] = end_dt

        # Query transaction review
        cursor = self.db[self.trade_reviews_collection].find(
            query
        ).sort("created_at", -1).skip(skip).limit(page_size)

        items = await cursor.to_list(None)
        total = await self.db[self.trade_reviews_collection].count_documents(query)

        result = []
        # Collect all stock codes whose names need to be queried (grouped by market)
        codes_by_market = {}  # {market: [codes]}
        for item in items:
            trade_info = item.get("trade_info", {})
            code = trade_info.get("code")
            name = trade_info.get("name")
            market = trade_info.get("market", "CN")
            # If there is no name, it needs to be obtained from the database
            if code and not name:
                if market not in codes_by_market:
                    codes_by_market[market] = []
                codes_by_market[market].append(code)
        
        # Query stock names in batches
        stock_names = {}
        # A Stock: Query from stock_basic_info
        if "CN" in codes_by_market:
            unique_codes = list(set(codes_by_market["CN"]))
            for code in unique_codes:
                stock_info = await self.db["stock_basic_info"].find_one({"code": code})
                if stock_info and stock_info.get("name"):
                    stock_names[code] = stock_info.get("name")
        
        # Hong Kong stocks/US stocks: query from paper_positions or positions (these tables usually have a name field)
        for market in ["HK", "US"]:
            if market in codes_by_market:
                unique_codes = list(set(codes_by_market[market]))
                for code in unique_codes:
                    # First try to get it from paper_positions
                    pos = await self.db["paper_positions"].find_one({"code": code})
                    if pos and pos.get("name"):
                        stock_names[code] = pos.get("name")
                        continue
                    # Try getting it from positions again
                    pos = await self.db["positions"].find_one({"code": code})
                    if pos and pos.get("name"):
                        stock_names[code] = pos.get("name")
        
        for item in items:
            trade_info = item.get("trade_info", {})
            ai_review = item.get("ai_review", {})
            code = trade_info.get("code")
            # Prioritize using the name in trade_info, if not, get it from stock_names
            name = trade_info.get("name") or stock_names.get(code) or None
            
            result.append(ReviewListItem(
                review_id=item.get("review_id", ""),
                review_type=item.get("review_type", "complete_trade"),
                code=code,
                name=name,
                realized_pnl=trade_info.get("realized_pnl", 0),
                overall_score=ai_review.get("overall_score", 0),
                status=item.get("status", "pending"),
                is_case_study=item.get("is_case_study", False),
                created_at=item.get("created_at")
            ))

        return {
            "items": [r.model_dump() for r in result],
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def get_review_summary_by_stock(
        self,
        user_id: str,
        stock_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the latest review summary by stock code (for stock details page use)
        """
        try:
            from app.models.user import PyObjectId
            db = get_database()
            user_oid = PyObjectId(user_id)

            # Query unified_analysis_tasks
            query_filter = {
                "user_id": user_oid,
                "task_type": "trade_review",
                "status": "completed",
                "$or": [
                    {"task_params.stock_code": stock_code},
                    {"task_params.symbol": stock_code},
                    {"task_params.code": stock_code},
                ]
            }
            logger.info(f"[Review summary] DEBUG: user_id={user_id}, user_oid={user_oid}, stock_code={stock_code}")
            logger.info(f"[Review summary] DEBUG: query={query_filter}")
            
            task = await db.unified_analysis_tasks.find_one(query_filter, sort=[("completed_at", -1)])

            if not task:
                count = await db.unified_analysis_tasks.count_documents({"task_type": "trade_review", "status": "completed"})
                logger.warning(f"[Review summary] not found! completed_tasks total={count}")
                sample = await db.unified_analysis_tasks.find_one({"task_type": "trade_review", "status": "completed"})
                if sample:
                    logger.warning(f"[Review summary] sample: user_id={sample.get('user_id')}, stock_code={sample.get('task_params', {}).get('stock_code')}")
                return None

            result = task.get("result", {})
            task_params = task.get("task_params", {})

            # Compatible with multiple result formats
            # v2: result.review_summary Yes dict
            # v1: result.ai_review is dict (current mainstream format)
            # old v1: result The top level has fields such as summary/recommendation
            is_v2 = bool(result and isinstance(result.get("review_summary"), dict))
            raw_ai = result.get("ai_review")
            ai_review = raw_ai if isinstance(raw_ai, dict) else {}
            logger.info(f"[Review summary] DEBUG: result keys={list(result.keys())[:10]}, "
                       f"is_v2={is_v2}, has_ai_review={bool(ai_review)}, "
                       f"ai_review_type={type(raw_ai).__name__}")

            summary = {}
            if is_v2:
                rs = result["review_summary"]
                summary = {
                    "has": True,
                    "task_id": task["task_id"],
                    "completed_at": task.get("completed_at", task.get("created_at")),
                    "summary": rs.get("summary", ""),
                    "recommendation": rs.get("lessons", ""),
                    "risk_level": rs.get("rating", rs.get("risk_level", "")),
                    "confidence_score": None,
                    "trade_count": len(result.get("trade_info", {}).get("trades", [])) if result.get("trade_info") else None
                }
            elif ai_review:
                # v1 Format: data in result.ai_review
                suggestions = ai_review.get("suggestions", [])
                suggestion_text = "\n".join([f"- {s}" for s in suggestions]) if suggestions else ""
                trade_info = result.get("trade_info", {})
                summary = {
                    "has": True,
                    "task_id": task["task_id"],
                    "completed_at": task.get("completed_at", task.get("created_at")),
                    "summary": ai_review.get("summary", ""),
                    "recommendation": suggestion_text,
                    "risk_level": _derive_risk_level(ai_review.get("overall_score")),
                    "confidence_score": ai_review.get("overall_score"),
                    "trade_count": len(trade_info.get("trades", [])) if trade_info else None
                }
            else:
                summary = {
                    "has": True,
                    "task_id": task["task_id"],
                    "completed_at": task.get("completed_at", task.get("created_at")),
                    "summary": result.get("summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "risk_level": result.get("risk_level", ""),
                    "confidence_score": result.get("confidence_score"),
                    "trade_count": len(result.get("detailed_analysis", {}).get("trade_info", {}).get("trades", [])) if result.get("detailed_analysis") else None
                }

            return summary

        except Exception as e:
            logger.warning(f"[复盘摘要] 查询失败: {e}")
            return None

    async def get_review_detail(
        self,
        user_id: str,
        review_id: str
    ) -> Optional[TradeReviewReport]:
        """
        Get review details

        Two data sources are supported:
        1. trade_reviews Collection (traditional mode)
        2. unified_analysis_tasks Collection (mission-centric mode)
        """
        # 1. First query from the trade_reviews collection (traditional mode)
        doc = await self.db[self.trade_reviews_collection].find_one({
            "user_id": user_id,
            "review_id": review_id
        })

        if doc:
            logger.info(f"📊 [Get review details] Find data from trade_reviews collection: {review_id}")
            doc = dict(doc)
            doc["ai_review"] = self._sanitize_trade_review_dict(doc.get("ai_review") or {})
            return TradeReviewReport(**doc)

        # 2. If not found, query from unified_analysis_tasks collection (task center mode)
        logger.info(f"🔍 [Get review details] trade_reviews Not found in, try querying from unified_analysis_tasks: {review_id}")

        # Note: user_id in unified_analysis_tasks is of type ObjectId
        from bson import ObjectId
        try:
            user_object_id = ObjectId(user_id)
        except Exception as e:
            logger.error(f"❌ [Get review details] user_id Conversion failed: {user_id} - {e}")
            return None

        task_doc = await self.db["unified_analysis_tasks"].find_one({
            "user_id": user_object_id,  # Use the ObjectId type
            "task_id": review_id  # review_id actually task_id
        })

        if not task_doc:
            logger.warning(f"❌ [Get review details] No data found in both collections: {review_id}")
            return None

        logger.info(f"✅ [Get review details] Find data from unified_analysis_tasks: {review_id}")

        # 3. Convert task data to TradeReviewReport format
        return self._convert_task_to_review_report(task_doc)

    def _convert_task_to_review_report(self, task_doc: dict) -> TradeReviewReport:
        """
        Convert task data of unified_analysis_tasks to TradeReviewReport format

        Args:
            task_doc: unified_analysis_tasks Documents in the collection

        Returns:
            TradeReviewReport object
        """
        from app.models.review import (
            TradeReviewReport, TradeInfo, MarketSnapshot, AITradeReview,
            ReviewType, ReviewStatus
        )
        from datetime import datetime

        # Extract data from task results
        # Note: result may be None, need to use or {} Make sure it's a dictionary
        result = task_doc.get("result") or {}
        task_params = task_doc.get("task_params") or {}

        # build TradeInfo
        trade_info_data = result.get("trade_info", {})
        if trade_info_data and "code" in trade_info_data:
            # If you have complete transaction information data, use it directly
            trade_info = TradeInfo(**trade_info_data)
        else:
            # If there is no data, get the stock symbol from task_params and create a default object
            stock_code = task_params.get("stock_code", "000000")
            stock_name = task_params.get("stock_name")
            trade_info = TradeInfo(
                code=stock_code,
                name=stock_name,
                market="CN",
                currency="CNY"
            )

        # build MarketSnapshot
        market_snapshot_data = result.get("market_snapshot", {})
        market_snapshot = MarketSnapshot(**market_snapshot_data) if market_snapshot_data else MarketSnapshot()

        # build AITradeReview
        ai_review_data = result.get("ai_review", {})
        ai_review = self._sanitize_trade_review_result(
            AITradeReview(**ai_review_data) if ai_review_data else AITradeReview()
        )

        # Mapping status
        status_mapping = {
            "pending": ReviewStatus.PENDING,
            "processing": ReviewStatus.PROCESSING,
            "completed": ReviewStatus.COMPLETED,
            "failed": ReviewStatus.FAILED
        }
        status = status_mapping.get(task_doc.get("status", "pending"), ReviewStatus.PENDING)

        # build TradeReviewReport
        # Note: user_id may be of type ObjectId and needs to be converted to a string
        user_id_value = task_doc.get("user_id")
        user_id_str = str(user_id_value) if user_id_value else ""

        return TradeReviewReport(
            review_id=task_doc.get("task_id"),
            user_id=user_id_str,
            review_type=ReviewType.COMPLETE_TRADE,
            trade_info=trade_info,
            market_snapshot=market_snapshot,
            ai_review=ai_review,
            status=status,
            error_message=task_doc.get("error_message"),
            execution_time=task_doc.get("execution_time", 0.0),
            is_case_study=False,  # Task center mode does not currently support case libraries
            tags=[],
            source=task_params.get("source", "paper"),
            created_at=task_doc.get("created_at", datetime.now()),
            trading_system_id=task_params.get("trading_system_id"),
            trading_system_name=task_params.get("trading_system_name")
        )

    # ==================== Case library function ====================

    async def save_as_case(
        self,
        user_id: str,
        review_id: str,
        tags: List[str] = None,
        source: Optional[str] = None
    ) -> bool:
        """Save as case
        
        Args:
            source: Data source, set if provided, otherwise keep the original value or use the default value
        
        Returns:
            True If successful, False if the review report does not exist
        """
        # 🔍 First check whether the review report exists (two data sources are supported)
        # 1. Check the trade_reviews collection (legacy mode)
        report = await self.db[self.trade_reviews_collection].find_one({
            "user_id": user_id,
            "review_id": review_id
        })
        
        # 2. If not found, check unified_analysis_tasks collection (task-centric mode)
        if not report:
            from bson import ObjectId
            try:
                user_object_id = ObjectId(user_id)
                task_doc = await self.db["unified_analysis_tasks"].find_one({
                    "user_id": user_object_id,
                    "task_id": review_id,
                    "task_type": "trade_review"  # Make sure it is a transaction review task
                })
                if task_doc:
                    logger.info(f"📊 [save case] Find review tasks from unified_analysis_tasks: {review_id}")
                    # If the task has been completed, first synchronize to trade_reviews
                    if task_doc.get("status") == "completed":
                        logger.info(f"📊 [save case] The task has been completed and synchronized to trade_reviews: {review_id}")
                        try:
                            # Call get_review_detail to obtain the report object (the format will be automatically converted)
                            review_report = await self.get_review_detail(user_id, review_id)
                            if review_report:
                                # Save report to trade_reviews collection
                                report_dict = review_report.model_dump()
                                # Make sure to include the necessary fields
                                report_dict["user_id"] = user_id
                                report_dict["review_id"] = review_id
                                report_dict["created_at"] = review_report.created_at or task_doc.get("created_at")
                                
                                # Insert into trade_reviews (use upsert to avoid duplication)
                                await self.db[self.trade_reviews_collection].update_one(
                                    {"user_id": user_id, "review_id": review_id},
                                    {"$set": report_dict},
                                    upsert=True
                                )
                                logger.info(f"✅ [save case] Already synced to trade_reviews: {review_id}")
                                # Query again
                                report = await self.db[self.trade_reviews_collection].find_one({
                                    "user_id": user_id,
                                    "review_id": review_id
                                })
                            else:
                                logger.warning(f"⚠️ [save case] Unable to create report object from task data: {review_id}")
                                return False
                        except Exception as sync_error:
                            logger.error(f"❌ [save case] Sync to trade_reviews failed: {sync_error}", exc_info=True)
                            return False
                    else:
                        logger.warning(f"⚠️ [save case] The review task is still being processed: {review_id}, status={task_doc.get('status')}")
                        return False
            except Exception as e:
                logger.error(f"❌ [save case] Query for unified_analysis_tasks failed: {e}", exc_info=True)
        
        # If neither collection is found, return False
        if not report:
            logger.warning(f"⚠️ [save case] The review report does not exist: user_id={user_id}, review_id={review_id}")
            return False
        
        # Build update fields
        update_fields = {
            "is_case_study": True,
            "tags": tags or []
        }
        
        # Set if source is provided; otherwise ensure source field exists (read from review report or use default value)
        if source:
            update_fields["source"] = source
        else:
            # If the review report has a source field, keep it; otherwise set the default value
            if "source" not in report or not report.get("source"):
                update_fields["source"] = "paper"  # Default value
        
        result = await self.db[self.trade_reviews_collection].update_one(
            {"user_id": user_id, "review_id": review_id},
            {"$set": update_fields}
        )
        
        # Even if modified_count == 0 (field values are the same), it is also considered successful.
        if result.matched_count > 0:
            logger.info(f"✅ [save case] success: user_id={user_id}, review_id={review_id}, modified={result.modified_count > 0}")
            
            # After saving the case, write the transaction discipline memory (mem0 trade_pattern scope)
            try:
                # Reread the complete report (including ai_review, trade_info)
                full_report = await self.db[self.trade_reviews_collection].find_one({
                    "user_id": user_id,
                    "review_id": review_id
                })
                if full_report:
                    ai_review_dict = full_report.get("ai_review") or {}
                    trade_info_dict = full_report.get("trade_info") or {}
                    # Construct lightweight objects for use by _store_trade_pattern_memory
                    ai_review_obj = AITradeReview(**ai_review_dict) if ai_review_dict else None
                    trade_info_obj = TradeInfo(**trade_info_dict) if trade_info_dict else None
                    if ai_review_obj and trade_info_obj:
                        await _store_trade_pattern_memory(
                            self.db, user_id, trade_info_obj, ai_review_obj, review_id,
                        )
                        # v3.5.0 Item 2: Review, reflection and refinement (add structured lessons after writing the original text)
                        # When it fails, the helper has been downgraded internally and does not block the main process.
                        await _reflect_trade_review_lesson(
                            self.db, user_id, trade_info_obj, ai_review_obj, review_id,
                        )
            except Exception as mem_err:
                logger.warning(f"[save case] Failed to write trade_pattern memory (ignored): {mem_err}", exc_info=True)
            
            return True
        else:
            logger.warning(f"⚠️ [save case] Update failed: user_id={user_id}, review_id={review_id}")
            return False

    async def get_cases(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get case library

        Args:
            source: Data source filtering, paper(simulated trading) or position(Position operation), If empty, get all
        """
        skip = (page - 1) * page_size

        query = {
            "user_id": user_id,
            "is_case_study": True
        }
        if source:
            if source == "position":
                # Position operation review includes real trading(real)and position operations(position)
                query["source"] = {"$in": ["position", "real"]}
            else:
                query["source"] = source

        cursor = self.db[self.trade_reviews_collection].find(query).sort("created_at", -1).skip(skip).limit(page_size)

        items = await cursor.to_list(None)
        total = await self.db[self.trade_reviews_collection].count_documents(query)

        result = []
        # Collect all stock codes whose names need to be queried (grouped by market)
        codes_by_market = {}  # {market: [codes]}
        for item in items:
            trade_info = item.get("trade_info", {})
            code = trade_info.get("code")
            name = trade_info.get("name")
            market = trade_info.get("market", "CN")
            # If there is no name, it needs to be obtained from the database
            if code and not name:
                if market not in codes_by_market:
                    codes_by_market[market] = []
                codes_by_market[market].append(code)
        
        # Query stock names in batches
        stock_names = {}
        # A Stock: Query from stock_basic_info
        if "CN" in codes_by_market:
            unique_codes = list(set(codes_by_market["CN"]))
            for code in unique_codes:
                stock_info = await self.db["stock_basic_info"].find_one({"code": code})
                if stock_info and stock_info.get("name"):
                    stock_names[code] = stock_info.get("name")
        
        # Hong Kong stocks/US stocks: query from paper_positions or positions (these tables usually have a name field)
        for market in ["HK", "US"]:
            if market in codes_by_market:
                unique_codes = list(set(codes_by_market[market]))
                for code in unique_codes:
                    # First try to get it from paper_positions
                    pos = await self.db["paper_positions"].find_one({"code": code})
                    if pos and pos.get("name"):
                        stock_names[code] = pos.get("name")
                        continue
                    # Try getting it from positions again
                    pos = await self.db["positions"].find_one({"code": code})
                    if pos and pos.get("name"):
                        stock_names[code] = pos.get("name")
        
        for item in items:
            trade_info = item.get("trade_info", {})
            ai_review = item.get("ai_review", {})
            code = trade_info.get("code")
            # Prioritize using the name in trade_info, if not, get it from stock_names
            name = trade_info.get("name") or stock_names.get(code) or None
            
            result.append({
                "review_id": item.get("review_id", ""),
                "code": code,
                "name": name,
                "realized_pnl": trade_info.get("realized_pnl", 0),
                "overall_score": ai_review.get("overall_score", 0),
                "tags": item.get("tags", []),
                "source": item.get("source", "paper"),
                "created_at": item.get("created_at")
            })

        return {
            "items": result,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def delete_case(
        self,
        user_id: str,
        review_id: str
    ) -> bool:
        """从案例库移除"""
        result = await self.db[self.trade_reviews_collection].update_one(
            {"user_id": user_id, "review_id": review_id},
            {"$set": {"is_case_study": False}}
        )
        return result.modified_count > 0

    async def delete_review(
        self,
        user_id: str,
        review_id: str
    ) -> bool:
        """删除复盘记录"""
        result = await self.db[self.trade_reviews_collection].delete_one(
            {"user_id": user_id, "review_id": review_id}
        )
        return result.deleted_count > 0

    # ==================== Transaction statistics ====================

    async def get_trading_statistics(
        self,
        user_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> TradingStatistics:
        """获取交易统计"""
        query = {"user_id": user_id, "side": "sell"}

        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date

        # Get all sell transactions
        cursor = self.db[self.paper_trades_collection].find(query)
        trades = await cursor.to_list(None)

        if not trades:
            return TradingStatistics()

        stats = TradingStatistics()
        stats.total_trades = len(trades)

        profits = []
        losses = []
        total_commission = 0.0

        for trade in trades:
            pnl = trade.get("pnl", 0)
            commission = trade.get("commission", 0)
            total_commission += commission

            if pnl > 0:
                stats.winning_trades += 1
                profits.append(pnl)
            elif pnl < 0:
                stats.losing_trades += 1
                losses.append(abs(pnl))

            stats.total_pnl += pnl

        # Calculate statistical indicators
        if stats.total_trades > 0:
            stats.win_rate = round(stats.winning_trades / stats.total_trades * 100, 2)

        if profits:
            stats.avg_profit = round(sum(profits) / len(profits), 2)
            stats.max_single_profit = round(max(profits), 2)

        if losses:
            stats.avg_loss = round(sum(losses) / len(losses), 2)
            stats.max_single_loss = round(max(losses), 2)

        if stats.avg_loss > 0:
            stats.profit_loss_ratio = round(stats.avg_profit / stats.avg_loss, 2)

        stats.total_pnl = round(stats.total_pnl, 2)
        stats.total_commission = round(total_commission, 2)

        return stats

    # ==================== Periodic review ====================

    async def create_periodic_review(
        self,
        user_id: str,
        request: CreatePeriodicReviewRequest
    ) -> PeriodicReviewResponse:
        """Create a staged review

        Supports two data sources:
        - paper: simulated trading (paper_trades)
        - position: Position operation (position_changes)
        """
        import time
        start_time = time.time()

        review_id = str(uuid.uuid4())
        source = getattr(request, 'source', 'paper') or 'paper'

        # parse date
        period_start = datetime.strptime(request.start_date, "%Y-%m-%d")
        period_end = datetime.strptime(request.end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

        # Select collections and query conditions based on data source
        if source == "position":
            # Position operation data source
            collection = "position_changes"
            date_field = "created_at"
        else:
            # Simulated trading data source
            collection = self.paper_trades_collection
            date_field = "timestamp"

        # Get all transactions within this time period
        query = {
            "user_id": user_id,
            date_field: {
                "$gte": period_start,
                "$lte": period_end
            }
        }
        cursor = self.db[collection].find(query).sort(date_field, 1)
        trades = await cursor.to_list(None)

        source_name = "持仓操作" if source == "position" else "模拟交易"
        if not trades:
            raise ValueError(f"在 {request.start_date} 至 {request.end_date} 期间没有{source_name}记录")

        # Calculate transaction statistics (Use different processing methods depending on the data source)
        if source == "position":
            statistics = await self._calculate_position_period_statistics(trades)
            trades_summary = self._build_position_trades_summary(trades)
        else:
            statistics = await self._calculate_period_statistics(trades)
            trades_summary = self._build_trades_summary(trades)

        # Call AI for staged analysis
        ai_review = await self._call_ai_periodic_review(
            period_type=request.period_type.value,
            start_date=request.start_date,
            end_date=request.end_date,
            statistics=statistics,
            trades_summary=trades_summary
        )
        ai_review = self._sanitize_periodic_review_result(ai_review)

        execution_time = time.time() - start_time

        # Save review report
        report = PeriodicReviewReport(
            review_id=review_id,
            user_id=user_id,
            period_type=request.period_type,
            period_start=period_start,
            period_end=period_end,
            source=source,
            statistics=statistics,
            trades_summary=trades_summary,
            ai_review=ai_review,
            status=ReviewStatus.COMPLETED,
            execution_time=execution_time,
            created_at=now_tz()
        )

        await self.db[self.periodic_reviews_collection].insert_one(
            report.model_dump(by_alias=True)
        )

        return PeriodicReviewResponse(
            review_id=review_id,
            status=ReviewStatus.COMPLETED,
            period_type=request.period_type,
            period_start=period_start,
            period_end=period_end,
            statistics=statistics,
            ai_review=ai_review,
            execution_time=execution_time,
            created_at=report.created_at
        )

    async def _calculate_period_statistics(
        self,
        trades: List[Dict[str, Any]]
    ) -> TradingStatistics:
        """计算阶段性交易统计"""
        stats = TradingStatistics()

        sell_trades = [t for t in trades if t.get("side") == "sell"]
        stats.total_trades = len(sell_trades)

        profits = []
        losses = []
        total_commission = 0.0

        for trade in sell_trades:
            pnl = trade.get("pnl", 0)
            commission = trade.get("commission", 0)
            total_commission += commission

            if pnl > 0:
                stats.winning_trades += 1
                profits.append(pnl)
            elif pnl < 0:
                stats.losing_trades += 1
                losses.append(abs(pnl))

            stats.total_pnl += pnl

        # Calculate statistical indicators
        if stats.total_trades > 0:
            stats.win_rate = round(stats.winning_trades / stats.total_trades * 100, 2)

        if profits:
            stats.avg_profit = round(sum(profits) / len(profits), 2)
            stats.max_single_profit = round(max(profits), 2)

        if losses:
            stats.avg_loss = round(sum(losses) / len(losses), 2)
            stats.max_single_loss = round(max(losses), 2)

        if stats.avg_loss > 0:
            stats.profit_loss_ratio = round(stats.avg_profit / stats.avg_loss, 2)

        stats.total_pnl = round(stats.total_pnl, 2)
        stats.total_commission = round(total_commission, 2)

        return stats

    def _build_trades_summary(
        self,
        trades: List[Dict[str, Any]]
    ) -> List[TradeSummaryItem]:
        """构建交易摘要列表"""
        summary = []
        for trade in trades:
            if trade.get("side") == "sell":
                pnl = trade.get("pnl", 0)
                amount = trade.get("amount", 0)
                pnl_pct = (pnl / amount * 100) if amount > 0 else 0

                summary.append(TradeSummaryItem(
                    code=trade.get("code", ""),
                    name=trade.get("name", ""),
                    side=trade.get("side", ""),
                    quantity=trade.get("quantity", 0),
                    price=trade.get("price", 0),
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    timestamp=trade.get("timestamp", "").isoformat() if isinstance(trade.get("timestamp"), datetime) else str(trade.get("timestamp", ""))
                ))

        return summary

    async def _calculate_position_period_statistics(
        self,
        changes: List[Dict[str, Any]]
    ) -> TradingStatistics:
        """Calculate periodic statistics of position operations

        position_changes data structure:
        - change_type: BUY/SELL/ADJUST
        - quantity_before/quantity_after: Quantity before and after change
        - cost_price_before/cost_price_after: Cost before and after changes
        - price: transaction price
        - realized_profit: Realized profit and loss (Value when sold)
        """
        stats = TradingStatistics()

        # Filter out sell operations
        sell_changes = [c for c in changes if c.get("change_type") == "SELL"]
        stats.total_trades = len(sell_changes)

        profits = []
        losses = []

        for change in sell_changes:
            pnl = change.get("realized_profit", 0) or 0

            if pnl > 0:
                stats.winning_trades += 1
                profits.append(pnl)
            elif pnl < 0:
                stats.losing_trades += 1
                losses.append(abs(pnl))

            stats.total_pnl += pnl

        # Calculate statistical indicators
        if stats.total_trades > 0:
            stats.win_rate = round(stats.winning_trades / stats.total_trades * 100, 2)

        if profits:
            stats.avg_profit = round(sum(profits) / len(profits), 2)
            stats.max_single_profit = round(max(profits), 2)

        if losses:
            stats.avg_loss = round(sum(losses) / len(losses), 2)
            stats.max_single_loss = round(max(losses), 2)

        if stats.avg_loss > 0:
            stats.profit_loss_ratio = round(stats.avg_profit / stats.avg_loss, 2)

        stats.total_pnl = round(stats.total_pnl, 2)

        return stats

    def _build_position_trades_summary(
        self,
        changes: List[Dict[str, Any]]
    ) -> List[TradeSummaryItem]:
        """构建持仓操作交易摘要列表"""
        summary = []
        for change in changes:
            change_type = change.get("change_type", "")
            # Only show buying and selling operations
            if change_type not in ["BUY", "SELL"]:
                continue

            pnl = change.get("realized_profit", 0) or 0
            price = change.get("price", 0) or 0
            qty_before = change.get("quantity_before", 0) or 0
            qty_after = change.get("quantity_after", 0) or 0
            quantity = abs(qty_after - qty_before)

            # Calculate profit and loss percentage
            cost_price = change.get("cost_price_before", 0) or 0
            pnl_pct = 0
            if cost_price > 0 and change_type == "SELL":
                pnl_pct = (price - cost_price) / cost_price * 100

            created_at = change.get("created_at")
            timestamp = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or "")

            summary.append(TradeSummaryItem(
                code=change.get("code", ""),
                name=change.get("name", ""),
                side="sell" if change_type == "SELL" else "buy",
                quantity=quantity,
                price=round(price, 2),
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                timestamp=timestamp
            ))

        return summary

    async def _call_ai_periodic_review(
        self,
        period_type: str,
        start_date: str,
        end_date: str,
        statistics: TradingStatistics,
        trades_summary: List[TradeSummaryItem]
    ) -> AIPeriodicReview:
        """Call AI for periodic review analysis"""
        from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
        import asyncio

        # Build prompt words
        period_names = {
            "week": "周度",
            "month": "月度",
            "quarter": "季度",
            "year": "年度"
        }
        period_name = period_names.get(period_type, "阶段性")

        # Build transaction details
        trades_detail = "\n".join([
            f"- {t.code}: {t.side} {t.quantity}股 @ {t.price}, 盈亏: {t.pnl} ({t.pnl_pct}%)"
            for t in trades_summary[:20]  # Display up to 20 items
        ])
        if len(trades_summary) > 20:
            trades_detail += f"\n... 还有 {len(trades_summary) - 20} 条交易记录"

        prompt = f"""# {period_name}交易复盘

## 复盘周期
{start_date} 至 {end_date}

## 交易统计
- 总交易次数: {statistics.total_trades}
- 盈利次数: {statistics.winning_trades} / 亏损次数: {statistics.losing_trades}
- 胜率: {statistics.win_rate}%
- 总盈亏: {statistics.total_pnl}
- 平均盈利: {statistics.avg_profit} / 平均亏损: {statistics.avg_loss}
- 盈亏比: {statistics.profit_loss_ratio}
- 最大单笔盈利: {statistics.max_single_profit}
- 最大单笔亏损: {statistics.max_single_loss}
- 总手续费: {statistics.total_commission}

## 交易明细
{trades_detail}

请对这段时间的交易进行全面复盘分析，包括：
1. 阶段结论（分数字段仅作兼容保留，不作为总结主体）
2. 交易风格分析
3. 常见错误总结
4. 改进方向建议
5. 后续观察与复盘重点
6. 最佳交易分析
7. 最差交易分析

请以JSON格式输出，格式如下：
{{
    "overall_score": 75,
    "summary": "整体评价，需直白总结这段时间最突出的得失与问题...",
    "trading_style": "交易风格分析...",
    "common_mistakes": ["错误1", "错误2"],
    "improvement_areas": ["改进方向1", "改进方向2"],
    "action_plan": ["后续观察重点1", "后续复盘重点2"],
    "best_trade": "最佳交易分析...",
    "worst_trade": "最差交易分析..."
}}

注意：action_plan 字段是兼容旧结构的名称，实际内容必须写成后续观察重点或复盘跟踪事项，不得写成未来交易动作。
"""
        prompt = self._append_review_guardrails(prompt)

        try:
            model_name = "qwen-plus"
            provider_info = get_provider_and_url_by_model_sync(model_name)

            # Use synchronous requests calls to avoid proxy issues with asynchronous httpx
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                self._call_llm_sync,
                prompt,
                model_name,
                provider_info.get("backend_url"),
                provider_info.get("api_key")
            )

            # Parse JSON response
            import json
            import re

            # Try to extract JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                return self._sanitize_periodic_review_result(AIPeriodicReview(
                    overall_score=data.get("overall_score", 60),
                    summary=data.get("summary", ""),
                    trading_style=data.get("trading_style", ""),
                    common_mistakes=data.get("common_mistakes", []),
                    improvement_areas=data.get("improvement_areas", []),
                    action_plan=data.get("action_plan", []),
                    best_trade=data.get("best_trade"),
                    worst_trade=data.get("worst_trade")
                ))
            else:
                # If the JSON cannot be parsed, return the default result
                return self._sanitize_periodic_review_result(AIPeriodicReview(
                    overall_score=60,
                    summary=content[:500] if content else "AI分析完成"
                ))

        except Exception as e:
            logger.error(f"AI阶段性复盘分析失败: {e}")
            return self._sanitize_periodic_review_result(AIPeriodicReview(
                overall_score=0,
                summary=f"AI分析失败: {str(e)}"
            ))

    async def get_periodic_review_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get periodic review history

        Args:
            source: Data source filtering, paper(simulated trading) or position(Position operation), If empty, get all
        """
        skip = (page - 1) * page_size

        query = {"user_id": user_id}
        if source:
            query["source"] = source

        cursor = self.db[self.periodic_reviews_collection].find(
            query
        ).sort("created_at", -1).skip(skip).limit(page_size)

        items = await cursor.to_list(None)
        total = await self.db[self.periodic_reviews_collection].count_documents(query)

        result = []
        for item in items:
            ai_review = item.get("ai_review", {})
            statistics = item.get("statistics", {})
            result.append({
                "review_id": item.get("review_id", ""),
                "period_type": item.get("period_type", "month"),
                "period_start": item.get("period_start"),
                "period_end": item.get("period_end"),
                "source": item.get("source", "paper"),
                "total_trades": statistics.get("total_trades", 0),
                "total_pnl": statistics.get("total_pnl", 0),
                "win_rate": statistics.get("win_rate", 0),
                "overall_score": ai_review.get("overall_score", 0),
                "status": item.get("status", "pending"),
                "created_at": item.get("created_at")
            })

        return {
            "items": result,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def get_periodic_review_detail(
        self,
        user_id: str,
        review_id: str
    ) -> Optional[PeriodicReviewReport]:
        """获取阶段性复盘详情"""
        doc = await self.db[self.periodic_reviews_collection].find_one({
            "user_id": user_id,
            "review_id": review_id
        })

        if not doc:
            return None

        doc = dict(doc)
        doc["ai_review"] = self._sanitize_periodic_review_dict(doc.get("ai_review") or {})
        return PeriodicReviewReport(**doc)

    def _build_trade_review_vars(
        self,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot
    ) -> Dict[str, Any]:
        """Construct transaction review template variables

        Args:
            trade_info: transaction information
            market_snapshot: market snapshot

        Returns:
            template variable dictionary
        """
        # Build transaction record details
        trades_detail = []
        for t in trade_info.trades:
            trade_record = {
                "date": t.timestamp[:10] if t.timestamp else "",
                "side": t.side.upper(),
                "quantity": t.quantity,
                "price": t.price,
                "pnl": t.pnl
            }
            trades_detail.append(trade_record)

        # Construct K-line data summary
        kline_data = []
        if market_snapshot.kline_data:
            for k in market_snapshot.kline_data[-20:]:
                kline_data.append({
                    "date": k.get("date", ""),
                    "open": k.get("open", 0),
                    "high": k.get("high", 0),
                    "low": k.get("low", 0),
                    "close": k.get("close", 0)
                })

        return {
            "trade": {
                "code": trade_info.code,
                "name": trade_info.name or trade_info.code,
                "market": trade_info.market,
                "first_buy_date": trade_info.first_buy_date[:10] if trade_info.first_buy_date else "",
                "last_sell_date": trade_info.last_sell_date[:10] if trade_info.last_sell_date else "",
                "holding_days": trade_info.holding_days,
                "trades": trades_detail,
                "total_buy_quantity": trade_info.total_buy_quantity,
                "total_sell_quantity": trade_info.total_sell_quantity,
                "avg_buy_price": trade_info.avg_buy_price,
                "avg_sell_price": trade_info.avg_sell_price,
                "total_buy_amount": trade_info.total_buy_amount,
                "total_sell_amount": trade_info.total_sell_amount,
                "realized_pnl": trade_info.realized_pnl,
                "realized_pnl_pct": trade_info.realized_pnl_pct,
                "total_commission": trade_info.total_commission
            },
            "market": {
                "period_high": market_snapshot.period_high,
                "period_high_date": market_snapshot.period_high_date,
                "period_low": market_snapshot.period_low,
                "period_low_date": market_snapshot.period_low_date,
                "buy_date": {
                    "open": market_snapshot.buy_date_open,
                    "high": market_snapshot.buy_date_high,
                    "low": market_snapshot.buy_date_low,
                    "close": market_snapshot.buy_date_close
                },
                "sell_date": {
                    "open": market_snapshot.sell_date_open,
                    "high": market_snapshot.sell_date_high,
                    "low": market_snapshot.sell_date_low,
                    "close": market_snapshot.sell_date_close
                },
                "kline_data": kline_data
            },
            # Market and industry benchmark data (subsequently populated through _get_benchmark_data)
            "market_benchmark": {},
            "industry_benchmark": {},
            "attribution": {}
        }

    async def _get_benchmark_data(
        self,
        stock_code: str,
        market: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Get broad market and industry benchmark data

        Obtain data using a unified data source manager and automatically select data sources based on database configuration

        Args:
            stock_code: Stock code
            market: market type
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)

        Returns:
            Dictionary containing market benchmarks, industry benchmarks, and earnings attribution
        """
        result = {
            "market_benchmark": {
                "index_code": "",
                "index_name": "",
                "start_price": None,
                "end_price": None,
                "change_pct": None,
                "period_high": None,
                "period_low": None
            },
            "industry_benchmark": {
                "industry_name": "",
                "index_code": "",
                "change_pct": None,
                "vs_market": None  # Relative to the market excess
            },
            "attribution": {
                "beta_contribution": None,
                "industry_excess": None,
                "alpha": None,
                "timing_score": None
            }
        }

        try:
            # Directly use tushare provider to obtain index data (refer to the implementation of index_tools.py)
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            from core.tools.sector_tools import get_stock_sector_info

            provider = get_tushare_provider()

            # 1. Get broad market benchmark data (CSI 300)
            benchmark_code = "000300.SH"
            benchmark_name = "沪深300"

            start_date_clean = start_date.replace('-', '')
            end_date_clean = end_date.replace('-', '')

            logger.info(f"📊 [Review] Get market data: {benchmark_code}, {start_date_clean} ~ {end_date_clean}")

            # Use the get_index_daily method of tushare provider
            index_df = await provider.get_index_daily(
                ts_code=benchmark_code,
                start_date=start_date_clean,
                end_date=end_date_clean
            )

            if index_df is not None and not index_df.empty:
                index_df = index_df.sort_values('trade_date')
                start_close = index_df.iloc[0]['close']
                end_close = index_df.iloc[-1]['close']
                market_change_pct = ((end_close - start_close) / start_close) * 100

                result["market_benchmark"] = {
                    "index_code": benchmark_code,
                    "index_name": benchmark_name,
                    "start_price": float(start_close),
                    "end_price": float(end_close),
                    "change_pct": round(market_change_pct, 2),
                    "period_high": float(index_df['high'].max()),
                    "period_low": float(index_df['low'].min())
                }
                logger.info(f"✅ [Review] Obtaining market data from tushare successfully: {market_change_pct:.2f}%")
            else:
                logger.warning(f"⚠️ [Review] No market data was obtained")

            # 2. Obtain industry benchmark data (using unified tool functions)
            sector_info = await get_stock_sector_info(stock_code)
            if sector_info and sector_info.get("industry"):
                result["industry_benchmark"]["industry_name"] = sector_info["industry"]
                logger.info(f"📊 [复盘] 股票 {stock_code} 所属行业: {sector_info['industry']}")

            # 3. Calculate revenue attribution (simplified version)
            if result["market_benchmark"]["change_pct"] is not None:
                result["attribution"]["beta_contribution"] = result["market_benchmark"]["change_pct"]

            logger.info(f"✅ [Review] Baseline data acquisition completed: Market={result['market_benchmark']['change_pct']}%")

        except ImportError as e:
            logger.warning(f"⚠️ [Review] Data Tools module is not available: {e}")
        except Exception as e:
            logger.error(f"❌ [Review] Failed to obtain benchmark data: {e}", exc_info=True)

        return result

    def _format_trading_plan_for_workflow(self, trading_system: Dict[str, Any]) -> Dict[str, Any]:
        """Format trading plan rules for workflow input

        Args:
            trading_system: Trading plan data

        Returns:
            Formatted trading plan rules dictionary
        """
        # 🔧 Adapt to actual database structure
        # Database usage: stock_selection, timing, position, risk_management, discipline
        # instead of: stock_selection_rules, timing_rules, position_rules, risk_rules, discipline_rules

        stock_selection = trading_system.get("stock_selection", {})
        timing = trading_system.get("timing", {})
        position = trading_system.get("position", {})
        risk_management = trading_system.get("risk_management", {})
        discipline = trading_system.get("discipline", {})

        return {
            "plan_id": trading_system.get("system_id", ""),
            "plan_name": trading_system.get("name", ""),
            "style": trading_system.get("style", ""),
            "rules": {
                "stock_selection": {
                    "must_meet": stock_selection.get("must_have", []),  # 🔧 must_have -> must_meet
                    "exclude": stock_selection.get("exclude", []),
                },
                "timing": {
                    "entry_signals": timing.get("entry_signals", []),
                    "exit_signals": timing.get("exit_signals", []),  # may be empty
                },
                "position": {
                    "single_stock_limit": position.get("max_per_stock", 0),  # 🔧 max_per_stock -> single_stock_limit
                    "max_stocks": position.get("max_holdings", 0),  # 🔧 max_holdings -> max_stocks
                },
                "risk": {
                    "stop_loss": risk_management.get("stop_loss", {}),
                    "take_profit": risk_management.get("take_profit", {}),
                },
                "discipline": {
                    "must_do": discipline.get("must_do", []),
                    "forbidden": discipline.get("must_not", []),  # 🔧 must_not -> forbidden
                },
            },
            "rules_text": self._format_trading_plan_rules_text(trading_system),  # Text format for use with prompt words
        }

    def _format_trading_plan_rules_text(self, trading_system: Dict[str, Any]) -> str:
        """Format trading plan rules as text for use with prompt words

        Args:
            trading_system: Trading plan data

        Returns:
            Formatted rule text
        """
        rules_parts = []

        # 🔧 Adapt to actual database structure
        # Database usage: stock_selection, timing, position, risk_management, discipline

        # Stock selection rules
        stock_selection = trading_system.get("stock_selection", {})
        must_have = stock_selection.get("must_have", [])
        exclude = stock_selection.get("exclude", [])

        if must_have or exclude:
            rules_parts.append("**选股规则**:")
            if must_have:
                # must_have is an array of objects, each object has rule and description
                must_have_texts = [f"{item.get('rule', '')} ({item.get('description', '')})" for item in must_have]
                rules_parts.append(f"- 必须满足: {'; '.join(must_have_texts)}")
            if exclude:
                # exclude Also an array of objects
                exclude_texts = [f"{item.get('rule', '')} ({item.get('description', '')})" for item in exclude]
                rules_parts.append(f"- 排除条件: {'; '.join(exclude_texts)}")

        # timing rules
        timing = trading_system.get("timing", {})
        entry_signals = timing.get("entry_signals", [])
        exit_signals = timing.get("exit_signals", [])

        if entry_signals or exit_signals:
            rules_parts.append("\n**择时规则**:")
            if entry_signals:
                # entry_signals is an array of objects, each object has signal and description
                entry_texts = [f"{item.get('signal', '')} ({item.get('description', '')})" for item in entry_signals]
                rules_parts.append(f"- 入场信号: {'; '.join(entry_texts)}")
            if exit_signals:
                exit_texts = [f"{item.get('signal', '')} ({item.get('description', '')})" for item in exit_signals]
                rules_parts.append(f"- 出场信号: {'; '.join(exit_texts)}")

        # Position rules
        position = trading_system.get("position", {})
        max_per_stock = position.get("max_per_stock")
        max_holdings = position.get("max_holdings")

        if max_per_stock or max_holdings:
            rules_parts.append("\n**仓位规则**:")
            if max_per_stock:
                rules_parts.append(f"- 单只股票上限: {max_per_stock * 100}%")
            if max_holdings:
                rules_parts.append(f"- 最大持股数: {max_holdings}只")

        # risk management rules
        risk_management = trading_system.get("risk_management", {})
        stop_loss = risk_management.get("stop_loss", {})
        take_profit = risk_management.get("take_profit", {})

        if stop_loss or take_profit:
            rules_parts.append("\n**风险管理规则**:")
            if stop_loss.get("type"):
                stop_loss_desc = stop_loss.get("description", "")
                if stop_loss.get("percentage"):
                    rules_parts.append(f"- 止损: {stop_loss.get('percentage') * 100}% ({stop_loss_desc})")
                else:
                    rules_parts.append(f"- 止损: {stop_loss_desc}")
            if take_profit.get("type"):
                take_profit_desc = take_profit.get("description", "")
                rules_parts.append(f"- 止盈: {take_profit_desc}")

        # disciplinary rules
        discipline = trading_system.get("discipline", {})
        must_do = discipline.get("must_do", [])
        must_not = discipline.get("must_not", [])

        if must_do or must_not:
            rules_parts.append("\n**纪律规则**:")
            if must_do:
                # must_do is an array of objects, each object has rule and description
                must_do_texts = [f"{item.get('rule', '')} ({item.get('description', '')})" for item in must_do]
                rules_parts.append(f"- 必须做到: {'; '.join(must_do_texts)}")
            if must_not:
                must_not_texts = [f"{item.get('rule', '')} ({item.get('description', '')})" for item in must_not]
                rules_parts.append(f"- 严禁操作: {'; '.join(must_not_texts)}")

        return "\n".join(rules_parts) if rules_parts else "无规则"

    async def _call_workflow_trade_review(
        self,
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot,
        user_id: Optional[str] = None,
        trading_system: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None  # 🔥 New parameters
    ) -> AITradeReview:
        """Use workflow engine to conduct multi-dimensional transaction review analysis

        Workflow contains:
        1. Timing Analyst - Analyze buying and selling timing
        2. Position Analyst - Analyze position management
        3. Emotion Analyst - Analyze Emotional Control
        4. Attribution Analyst - Analyze Revenue Sources
        5. Review Summarizer - Comprehensive Summary Report

        Args:
            trade_info: transaction information
            market_snapshot: market snapshot
            user_id: User ID
            trading_system: Associated trading plan (if any)
        """
        from core.workflow.engine import WorkflowEngine
        from core.workflow.default_workflow_provider import get_default_workflow_provider

        logger.info(f"🚀 [Workflow review] Start execution of transaction review workflow")

        # 🔍 Debugging: Print raw input data
        logger.info(f"🔍 [Workflow review] raw data - trade_info.code: {trade_info.code}")
        logger.info(f"🔍 [Workflow review] raw data - trade_info.name: {trade_info.name}")
        logger.info(f"🔍 [Workflow review] Raw data - trade_info.trades quantity: {len(trade_info.trades) if trade_info.trades else 0}")
        if trade_info.trades:
            logger.info(f"🔍 [Workflow review] Raw data - first transaction: side={trade_info.trades[0].side}, quantity={trade_info.trades[0].quantity}, price={trade_info.trades[0].price}")
        logger.info(f"🔍 [Workflow review] Raw data - trade_info type: {type(trade_info)}")
        logger.info(f"🔍 [Workflow review] Raw data - trade_info attribute: {[attr for attr in dir(trade_info) if not attr.startswith('_')]}")

        # 1. Load review workflow (priority use"My analysis flow"Default process for trade_review type in)
        provider = get_default_workflow_provider()
        workflow_id = provider.get_active_workflow_id("trade_review")
        workflow = provider.load_workflow(workflow_id)
        logger.info(f"✅ [Workflow review] Load workflow: {workflow.name} ({workflow.id})")

        # 2. Get benchmark data
        benchmark_data = {}
        try:
            benchmark_data = await self._get_benchmark_data(
                stock_code=trade_info.code,
                market=trade_info.market,
                start_date=trade_info.first_buy_date[:10] if trade_info.first_buy_date else "",
                end_date=trade_info.last_sell_date[:10] if trade_info.last_sell_date else ""
            )
            logger.info(f"📊 [Workflow review] Obtaining benchmark data is completed")
        except Exception as e:
            logger.warning(f"⚠️ [Workflow review] Failed to obtain benchmark data: {e}")

        # Construct K-line date index for calculating pre-trade price changes
        kline_by_date = {}
        for k in (market_snapshot.kline_data or []):
            kd = k.get("date", "")
            if kd:
                kline_by_date[kd[:10]] = k

        # 3. Prepare workflow input
        # 🆕 Add user_id and trade_ids for Agent to obtain complete data through tools
        # ⚠️ Parameter mapping: Agent expects the ticker field, which must be mapped from code, otherwise it will report "Missing required parameters: ticker"
        inputs = {
            "ticker": trade_info.code,  # 🔥 Key: Agent uses ticker uniformly and maps from code
            "user_id": user_id,  # User ID, used by the tool
            "trade_ids": [str(t.trade_id) for t in trade_info.trades] if trade_info.trades else [],  # Transaction ID list
            "trade_info": {
                "code": trade_info.code,
                "name": trade_info.name,
                "market": trade_info.market,
                # 🔧 Fixed field names to be consistent with what analysts expect
                "holding_days": trade_info.holding_days,  # Modification:holding_period -> holding_days
                "realized_pnl": trade_info.realized_pnl,  # Modification:pnl -> realized_pnl
                "realized_pnl_pct": trade_info.realized_pnl_pct,  # New:realized_pnl_pct
                # 🆕 Add floating profit and loss field
                "unrealized_pnl": trade_info.unrealized_pnl if hasattr(trade_info, 'unrealized_pnl') else 0.0,
                "unrealized_pnl_pct": trade_info.unrealized_pnl_pct if hasattr(trade_info, 'unrealized_pnl_pct') else 0.0,
                "current_price": trade_info.current_price if hasattr(trade_info, 'current_price') else None,
                "is_holding": trade_info.is_holding if hasattr(trade_info, 'is_holding') else False,
                "remaining_quantity": trade_info.remaining_quantity if hasattr(trade_info, 'remaining_quantity') else 0,
                # Keep old field names for compatibility
                "holding_period": trade_info.holding_days,
                "return_rate": trade_info.realized_pnl_pct / 100.0 if trade_info.realized_pnl_pct else 0,
                "pnl": trade_info.realized_pnl,
                "avg_buy_price": trade_info.avg_buy_price,
                "avg_sell_price": trade_info.avg_sell_price,
                "max_profit": self._calculate_max_profit_pct(trade_info, market_snapshot),
                "max_loss": self._calculate_max_loss_pct(trade_info, market_snapshot),
                "trades": [
                    {
                        "date": t.timestamp[:10] if t.timestamp else "",
                        "side": t.side,
                        "quantity": t.quantity,
                        "price": t.price,
                        "pnl": t.pnl or 0,
                        "price_change_before": self._calc_price_change_before(t, kline_by_date),
                    }
                    for t in trade_info.trades
                ],
            },
            "market_data": {
                "kline_data": market_snapshot.kline_data or [],
                "period_high": market_snapshot.period_high or 0.0,
                "period_low": market_snapshot.period_low or 0.0,
                "period_high_date": market_snapshot.period_high_date or "",
                "period_low_date": market_snapshot.period_low_date or "",
                "summary": f"持仓期间最高价: {market_snapshot.period_high or 'N/A'}, 最低价: {market_snapshot.period_low or 'N/A'}",
            },
            "benchmark_data": {
                "market_return": benchmark_data.get("market_benchmark", {}).get("change_pct", 0) / 100.0 if benchmark_data.get("market_benchmark", {}).get("change_pct") else 0,
                "industry_return": benchmark_data.get("industry_benchmark", {}).get("change_pct", 0) / 100.0 if benchmark_data.get("industry_benchmark", {}).get("change_pct") else 0,
                "industry_name": benchmark_data.get("industry_benchmark", {}).get("industry_name", ""),
            },
            "messages": [],
        }

        # 🆕 If a trading plan is associated, add trading plan rules to the input
        if trading_system:
            logger.info(f"📋 [Workflow review] Related party transaction plan: {trading_system.get('name', 'N/A')}")
            formatted_plan = self._format_trading_plan_for_workflow(trading_system)
            inputs["trading_plan"] = formatted_plan
            logger.info(f"✅ [Workflow review] trading_plan added to inputs")
            logger.info(f"   - plan_name: {formatted_plan.get('plan_name', 'N/A')}")
            logger.info(f"   - rules_text length: {len(formatted_plan.get('rules_text', ''))}")
        else:
            logger.info(f"📋 [Workflow review] Unlinked transaction plan")

        logger.info(f"📝 [Workflow review] Workflow input is ready")
        logger.info(f"📋 [工作流复盘] 股票: {trade_info.code}, 持仓周期: {trade_info.holding_days}天")
        logger.info(f"📋 [工作流复盘] 收益率: {trade_info.realized_pnl_pct:.2f}%, 盈亏: {trade_info.realized_pnl:.2f}元")
        logger.info(f"📋 [Workflow review] Number of transaction records: {len(trade_info.trades) if trade_info.trades else 0}")
        logger.info(f"📋 [工作流复盘] 基准数据: 大盘={benchmark_data.get('market_benchmark', {}).get('change_pct', 'N/A')}%, 行业={benchmark_data.get('industry_benchmark', {}).get('industry_name', 'N/A')}")

        # 🔍 Debugging: Print the actual data passed into the workflow
        logger.info(f"🔍 [Workflow review] Debugging - inputs['trade_info']['code']: {inputs['trade_info']['code']}")
        logger.info(f"🔍 [Workflow review] Debugging - inputs['trade_info']['trades'] length: {len(inputs['trade_info']['trades'])}")
        if inputs['trade_info']['trades']:
            logger.info(f"🔍 [Workflow review] Debugging - First Transaction: {inputs['trade_info']['trades'][0]}")

        # 4. Build legacy configurations (consistent with the single-stock analysis process and obtain complete LLM configuration parameters)
        legacy_config = {}
        try:
            from app.services.config_provider import provider as config_provider
            from app.services.unified_analysis_engine import UnifiedAnalysisEngine
            
            # Use config_provider to obtain system settings (including quick_analysis_model and deep_analysis_model)
            effective_settings = await config_provider.get_effective_system_settings()
            
            # Read quick_analysis_model and deep_analysis_model
            quick_analysis_model = effective_settings.get("quick_analysis_model")
            deep_analysis_model = effective_settings.get("deep_analysis_model")
            
            if quick_analysis_model and deep_analysis_model:
                # 🔥 Get the complete LLM configuration using UnifiedAnalysisEngine's _build_llm_config method
                # This way you can get temperature, timeout, max_tokens and other parameters
                engine = UnifiedAnalysisEngine()
                full_config = await engine._build_llm_config(quick_analysis_model, deep_analysis_model)
                
                if full_config:
                    legacy_config.update(full_config)
                    logger.info(f"🔧 [Workflow review] Get full model configuration from database: quick={quick_analysis_model}, deep={deep_analysis_model}")
                    logger.info(f"  quick: temperature={legacy_config.get('quick_temperature')}, max_tokens={legacy_config.get('quick_max_tokens')}, timeout={legacy_config.get('quick_timeout')}")
                    logger.info(f"  deep: temperature={legacy_config.get('deep_temperature')}, max_tokens={legacy_config.get('deep_max_tokens')}, timeout={legacy_config.get('deep_timeout')}")
                else:
                    # If retrieval fails, at least set the model name
                    legacy_config["quick_think_llm"] = quick_analysis_model
                    legacy_config["deep_think_llm"] = deep_analysis_model
                    legacy_config["llm_provider"] = "dashscope"
                    logger.warning(f"⚠️ [Workflow review] Unable to get full model configuration, only set model name")
            else:
                logger.warning(f"⚠️ [Workflow review] system_settings quick_analysis_model or deep_analysis_model not found, use default configuration")
                # If not configured, use default value
                legacy_config["quick_think_llm"] = quick_analysis_model or "qwen-turbo"
                legacy_config["deep_think_llm"] = deep_analysis_model or "qwen-plus"
                legacy_config["llm_provider"] = "dashscope"
        except Exception as e:
            logger.error(f"❌ [Workflow review] Failed to get model configuration from database: {e}", exc_info=True)
            # Use default configuration on failure
            from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
            model_name = "qwen-plus"
            provider_info = get_provider_and_url_by_model_sync(model_name)
            legacy_config = {
                "llm_provider": provider_info.get("provider", "dashscope"),
                "quick_think_llm": model_name,
                "deep_think_llm": model_name,
                "backend_url": provider_info.get("backend_url"),
                "api_key": provider_info.get("api_key"),
            }
            logger.info(f"🔧 [Workflow review] Use default LLM configuration: provider={legacy_config['llm_provider']}, model={model_name}")

        # 5. Create and execute workflow engines
        engine = WorkflowEngine(legacy_config=legacy_config)
        engine.load(workflow)
        logger.info(f"🔨 [工作流复盘] 工作流引擎已加载，节点数: {len(workflow.nodes)}, 边数: {len(workflow.edges)}")

        # List workflow nodes
        for node in workflow.nodes:
            agent_info = f" (agent: {node.agent_id})" if node.agent_id else ""
            logger.info(f"   📍 节点: {node.id} [{node.type}]{agent_info}")

        import asyncio
        # 🔥 Save a reference to the main event loop (before calling asyncio.to_thread)
        main_loop = asyncio.get_running_loop()

        def workflow_progress_callback(progress, message, **kwargs):
            """Wrapped progress callback: print log and call external progress callback"""
            step_name = kwargs.get("step_name", "")
            step_info = f" [{step_name}]" if step_name else ""
            logger.info(f"📊 [Workflow review] Progress: {progress:.1f}%{step_info} - {message}")

            # 🔥 Call external progress callback (save progress to database)
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        # If it is an asynchronous callback, it needs to be run in the main event loop
                        future = asyncio.run_coroutine_threadsafe(
                            progress_callback(progress, message, **kwargs),
                            main_loop
                        )
                        # Wait for callback to complete (up to 5 seconds)
                        try:
                            future.result(timeout=5)
                        except Exception as callback_error:
                            logger.warning(f"⚠️ 进度回调执行异常: {callback_error}")
                    else:
                        # Synchronous callbacks can be called directly
                        progress_callback(progress, message, **kwargs)
                except Exception as e:
                    logger.warning(f"⚠️ 进度回调调用失败: {e}")

        logger.info(f"🚀 [Workflow review] Start executing workflow...")
        logger.error(f"🔍 [Workflow review] inputs keys: {list(inputs.keys())}, ticker={inputs.get('ticker')}, trade_info exist={('trade_info' in inputs)}, trade_info_code={inputs.get('trade_info', {}).get('code') if isinstance(inputs.get('trade_info'), dict) else 'N/A'}")
        # 🔥 Key fix: Use asyncio.to_thread to execute synchronous workflows in separate threads
        # Avoid blocking the uvicorn event loop (this is also done for single stock analysis)
        result = await asyncio.to_thread(engine.execute, inputs=inputs, progress_callback=workflow_progress_callback)

        logger.info(f"✅ [Workflow review] Workflow execution completed")
        logger.info(f"📋 [Workflow review] output fields: {list(result.keys())}")

        # Print summary of analysis results for each dimension
        for key in ["timing_analysis", "position_analysis", "emotion_analysis", "attribution_analysis", "review_summary"]:
            if key in result:
                content = result[key]
                # 🔧 Handle possible dictionary formats (Agent may return {"content": "..."} format)
                if isinstance(content, dict):
                    content_str = content.get("content", "") or content.get("text", "") or str(content)
                elif isinstance(content, str):
                    content_str = content
                else:
                    content_str = str(content)

                content_len = len(content_str)
                preview = (content_str[:100] + "...") if content_len > 100 else content_str
                logger.info(f"   📄 {key}: {content_len}字符, 预览: {preview}")

        # 6. Parse workflow output
        return self._parse_workflow_result(result, trade_info, market_snapshot)

    def _parse_workflow_result(
        self,
        workflow_result: Dict[str, Any],
        trade_info: TradeInfo,
        market_snapshot: MarketSnapshot
    ) -> AITradeReview:
        """The analysis workflow execution result is AITradeReview"""
        import re
        import json

        logger.info(f"🔍 [Workflow review] Parse workflow results")
        logger.info(f"📋 [Workflow review] result key: {list(workflow_result.keys())}")

        # 🔍 Print specific output for each analyst
        analysis_fields = ['timing_analysis', 'position_analysis', 'emotion_analysis', 'attribution_analysis', 'review_summary']
        for field in analysis_fields:
            if field in workflow_result:
                content = workflow_result[field]
                logger.info(f"📊 [工作流复盘] {field}: {content[:200] if isinstance(content, str) else str(content)[:200]}...")
            else:
                logger.warning(f"⚠️ [Workflow review] Missing fields: {field}")

        result = AITradeReview(actual_pnl=trade_info.realized_pnl)

        # Extract analysis results of each dimension
        timing_analysis = workflow_result.get("timing_analysis", "")
        position_analysis = workflow_result.get("position_analysis", "")
        emotion_analysis = workflow_result.get("emotion_analysis", "")
        attribution_analysis = workflow_result.get("attribution_analysis", "")
        review_summary_raw = workflow_result.get("review_summary", "")

        # 🔧 Process the dictionary format returned by Agent (extract content field)
        if isinstance(review_summary_raw, dict):
            review_summary = review_summary_raw.get("content", "") or review_summary_raw.get("text", "") or str(review_summary_raw)
            logger.info(f"📄 [AI Review] review_summary is a dictionary, extract the content field")
        else:
            review_summary = review_summary_raw if isinstance(review_summary_raw, str) else str(review_summary_raw)

        # Set analysis results (also handles possible dictionary formats)
        result.timing_analysis = timing_analysis.get("content", str(timing_analysis)) if isinstance(timing_analysis, dict) else (timing_analysis if isinstance(timing_analysis, str) else str(timing_analysis))
        result.position_analysis = position_analysis.get("content", str(position_analysis)) if isinstance(position_analysis, dict) else (position_analysis if isinstance(position_analysis, str) else str(position_analysis))
        result.emotion_analysis = emotion_analysis.get("content", str(emotion_analysis)) if isinstance(emotion_analysis, dict) else (emotion_analysis if isinstance(emotion_analysis, str) else str(emotion_analysis))
        result.attribution_analysis = attribution_analysis.get("content", str(attribution_analysis)) if isinstance(attribution_analysis, dict) else (attribution_analysis if isinstance(attribution_analysis, str) else str(attribution_analysis))

        # Extract ratings and recommendations from summary
        if review_summary:
            logger.info(f"📄 [AI Review] review_summary length: {len(review_summary)}")
            logger.info(f"📄 [AI Review] first 500 characters: {review_summary[:500]}")
            logger.info(f"📄 [AI Review] last 500 characters: {review_summary[-500:]}")

            # Try to extract JSON from summary (multiple formats supported)
            json_match = re.search(r'```json\s*(.*?)\s*```', review_summary, re.DOTALL)
            if not json_match:
                # Try the code block without json tag
                json_match = re.search(r'```\s*(\{.*?\})\s*```', review_summary, re.DOTALL)
            if not json_match:
                # Try to match JSON object directly
                json_match = re.search(r'(\{[^{]*?"overall_score".*?\})', review_summary, re.DOTALL)

            if json_match:
                logger.info(f"✅ [AI Review] JSON match found")
                try:
                    json_str = json_match.group(1)
                    logger.info(f"📄 [AI Review] JSON The first 500 characters of the string: {json_str[:500]}")
                    logger.info(f"📄 [AI Review] JSON 500 characters after string: {json_str[-500:]}")
                    data = json.loads(json_str)
                    logger.info(f"📄 [AI Review] JSON Parsed successfully, top-level key: {list(data.keys())}")

                    # 🔧 Handle nested JSON structures (such as {"Review report": {...}}) 
                    if len(data) == 1 and isinstance(list(data.values())[0], dict):
                        logger.info(f"📄 [AI Review] Detect nested structures and extract inner data")
                        data = list(data.values())[0]
                        logger.info(f"📄 [AI Review] inner key: {list(data.keys())}")

                    # Extract ratings (supports multiple field names, unified conversion 1-10 → 0-100) 
                    def normalize_score(score_value, default=50):
                        """Unified scoring conversion logic:1-10 → 0-100"""
                        if isinstance(score_value, (int, float)) and score_value <= 10:
                            return int(score_value * 10)
                        return int(score_value)

                    result.overall_score = normalize_score(data.get("overall_score") or data.get("综合评分") or data.get("总分") or 0)
                    result.timing_score = normalize_score(data.get("timing_score") or data.get("时机评分") or data.get("买卖时机评分") or 0)
                    result.position_score = normalize_score(data.get("position_score") or data.get("仓位评分") or data.get("仓位管理评分") or 0)
                    result.emotion_score = normalize_score(data.get("emotion_score") or data.get("情绪评分") or data.get("情绪控制评分") or 0)
                    result.attribution_score = normalize_score(data.get("attribution_score") or data.get("归因评分") or data.get("收益归因评分") or 0)
                    result.discipline_score = normalize_score(data.get("discipline_score") or data.get("纪律评分") or data.get("执行纪律评分") or 0)

                    # Extract text field (make sure it is a string)
                    summary_raw = data.get("summary") or data.get("综合评价") or data.get("核心结论") or ""
                    result.summary = summary_raw if isinstance(summary_raw, str) else str(summary_raw) if summary_raw else ""

                    strengths_raw = data.get("strengths") or data.get("优点") or data.get("做得好的地方") or []
                    result.strengths = strengths_raw if isinstance(strengths_raw, list) else [str(strengths_raw)] if strengths_raw else []

                    weaknesses_raw = data.get("weaknesses") or data.get("不足") or data.get("需要改进的地方") or []
                    result.weaknesses = weaknesses_raw if isinstance(weaknesses_raw, list) else [str(weaknesses_raw)] if weaknesses_raw else []

                    suggestions_raw = data.get("suggestions") or data.get("建议") or data.get("改进建议") or []
                    result.suggestions = suggestions_raw if isinstance(suggestions_raw, list) else [str(suggestions_raw)] if suggestions_raw else []

                    # 🆕 Extract trading plan execution status (if any)
                    result.plan_adherence = data.get("plan_adherence")
                    result.plan_deviation = data.get("plan_deviation")

                    logger.info(f"✅ [AI复盘] JSON 解析成功 - 总分: {result.overall_score}, 时机: {result.timing_score}, 仓位: {result.position_score}, 情绪: {result.emotion_score}, 归因: {result.attribution_score}, 纪律: {result.discipline_score}")
                    logger.info(f"✅ [AI复盘] 提取字段 - 摘要长度: {len(result.summary)}, 优点: {len(result.strengths)}, 不足: {len(result.weaknesses)}, 建议: {len(result.suggestions)}")
                    logger.info(f"✅ [AI复盘] 分析内容 - 时机: {len(result.timing_analysis)}字符, 仓位: {len(result.position_analysis)}字符, 情绪: {len(result.emotion_analysis)}字符, 归因: {len(result.attribution_analysis)}字符")
                    if result.plan_adherence or result.plan_deviation:
                        logger.info(f"✅ [AI Review] Contains trading plan analysis: adherence={bool(result.plan_adherence)}, deviation={bool(result.plan_deviation)}")
                except Exception as e:
                    import traceback
                    logger.warning(f"⚠️ [Workflow review] Parsing summary JSON failed: {e}")
                    logger.warning(f"⚠️ [Workflow review] full stack:\n{traceback.format_exc()}")
                    logger.warning(f"⚠️ [Workflow review] JSON content: {json_match.group(1)[:500]}")
            else:
                logger.warning(f"⚠️ [AI Review] No JSON match found")

            # If no summary is extracted, use summary text
            if not result.summary:
                result.summary = review_summary[:200] if len(review_summary) > 200 else review_summary

        logger.info(f"✅ [Workflow review] Analysis Complete - Total Score: {result.overall_score}")

        return self._sanitize_trade_review_result(result)

    @staticmethod
    def _calc_price_change_before(trade, kline_by_date: dict) -> float:
        """Calculate the price change before the transaction: the increase or decrease of the opening price on the day of the transaction relative to the closing price of the previous day(%). """
        try:
            trade_date = trade.timestamp[:10] if trade.timestamp else ""
            if not trade_date or not kline_by_date:
                return 0.0
            # Find the K-line of the trading day and the K-line of the previous day
            sorted_dates = sorted(kline_by_date.keys())
            if trade_date not in kline_by_date:
                return 0.0
            idx = sorted_dates.index(trade_date)
            if idx == 0:
                return 0.0  # No data for the previous day
            prev_kline = kline_by_date[sorted_dates[idx - 1]]
            trade_kline = kline_by_date[trade_date]
            prev_close = prev_kline.get("close", 0)
            trade_open = trade_kline.get("open", 0)
            if not prev_close or not trade_open:
                return 0.0
            return round((trade_open - prev_close) / prev_close * 100, 2)
        except Exception:
            return 0.0

    def _calculate_max_profit_pct(self, trade_info: TradeInfo, market_snapshot: MarketSnapshot) -> float:
        """计算最大可能盈利百分比"""
        if not market_snapshot.period_high or not trade_info.avg_buy_price:
            return 0.0
        return (market_snapshot.period_high - trade_info.avg_buy_price) / trade_info.avg_buy_price

    def _calculate_max_loss_pct(self, trade_info: TradeInfo, market_snapshot: MarketSnapshot) -> float:
        """计算最大可能亏损百分比"""
        if not market_snapshot.period_low or not trade_info.avg_buy_price:
            return 0.0
        return (market_snapshot.period_low - trade_info.avg_buy_price) / trade_info.avg_buy_price


# Singleton pattern
_trade_review_service: Optional[TradeReviewService] = None


def get_trade_review_service() -> TradeReviewService:
    """获取交易复盘服务实例"""
    global _trade_review_service
    if _trade_review_service is None:
        _trade_review_service = TradeReviewService()
    return _trade_review_service


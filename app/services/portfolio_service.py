"""
Position analysis service
Provide position management and AI analysis functions
"""

import asyncio
import os
import re
import uuid
import logging
from datetime import datetime, timedelta, timezone as tz
from typing import Dict, Any, Optional, List
from bson import ObjectId
from app.utils.api_key_utils import truncate_api_key

from app.core.database import get_mongo_db


# ==================== Utility function ====================
def _format_user_friendly_error(error_msg: str) -> str:
    """Convert technical/English error messages into user-understandable friendly Chinese prompts.

    Specially handle common current limiting, network, timeout, insufficient balance and other situations.
    Avoid displaying English errors directly to users.
    """
    if not error_msg:
        return "An error occurred during analysis, please try again later."

    msg = error_msg.lower()

    # Rate limiting class (429/RATE_LIMIT)
    if any(key in msg for key in (
        "429", "rate_limit", "rate limit", "tokens limit",
        "rate_limited", "访问限制", "限流", "quota exceeded"
    )):
        return "There are currently many people using AI analysis and the service is busy. Please try again later. (Tip: Avoid initiating multiple analyzes in a short period of time)"

    # Network/Connectivity
    if any(key in msg for key in (
        "network error", "connection error", "connection refused",
        "failed to fetch", "连接失败", "网络错误",
    )):
        return "The network connection failed, please check the network status and try again."

    # timeout class
    if any(key in msg for key in ("timeout", "timed out", "超时")):
        return "The request timed out, please try again later. If it occurs frequently, please contact the administrator."

    # Authentication/Permission Class
    if any(key in msg for key in ("401", "403", "unauthorized", "forbidden", "无权限", "未授权")):
        return "Login has expired, please refresh the page and log in again and try again."

    # Insufficient balance/limit
    if any(key in msg for key in (
        "insufficient balance", "余额不足", "额度不足", "out of quota",
    )):
        return "AI Analysis: The quota is insufficient. Please contact the administrator to replenish the quota and try again."

    # Server error
    if any(key in msg for key in ("server error", "500", "502", "503", "internal error")):
        return "The server is temporarily unavailable, please try again later."

    # If it is Chinese and relatively short, return directly
    import re as _re
    if _re.search(r"[\u4e00-\u9fa5]", error_msg) and len(error_msg) <= 80:
        return error_msg

    # Default to cover up
    return "An error occurred during analysis, please try again later."


# ==================== Feature switch ====================
# Whether to use the template system to generate prompt words (off by default to maintain backward compatibility)
# NOTE: Use functions to read dynamically and make sure the .env file is loaded
def _use_template_prompts() -> bool:
    """Dynamically read the USE_TEMPLATE_PROMPTS environment variable"""
    return os.getenv("USE_TEMPLATE_PROMPTS", "false").lower() == "true"

# Whether to use the new version of the stock analysis engine (off by default to maintain backward compatibility)
def _use_stock_engine() -> bool:
    """Dynamically read the USE_STOCK_ENGINE environment variable"""
    return os.getenv("USE_STOCK_ENGINE", "false").lower() == "true"

# Whether to use the new version of analysis engine (including workflow engine)
def _use_stock_engine() -> bool:
    """Dynamically read the USE_STOCK_ENGINE environment variable"""
    return os.getenv("USE_STOCK_ENGINE", "false").lower() == "true"

from app.models.portfolio import (
    RealPosition, PositionSource, PortfolioAnalysisStatus, PositionAction,
    PositionSnapshot, PortfolioSnapshot, IndustryDistribution, AccountSnapshot,
    ConcentrationAnalysis, AIAnalysisResult, PortfolioAnalysisReport,
    PositionCreate, PositionUpdate, PositionResponse, PortfolioStatsResponse,
    PositionAnalysisRequest, PositionAnalysisReport, PositionAnalysisResult,
    PriceTarget, PositionAnalysisResponse, PositionRiskMetrics,
    PositionUserView,
    RealAccount, CapitalTransaction, CapitalTransactionType,
    AccountInitRequest, AccountTransactionRequest, AccountSettingsRequest, AccountSummary,
    PositionChangeType, PositionChange, PositionChangeResponse,
    PositionOperationType, PositionOperationRequest
)
from app.utils.timezone import now_tz
from app.utils.compliance import sanitize_position_analysis_payload

logger = logging.getLogger("app.services.portfolio_service")

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")

# Market code mapping: code used by frontend/database -> Chinese name used for single stock analysis service
MARKET_CODE_TO_NAME = {
    "CN": "A股",
    "HK": "港股",
    "US": "美股"
}

# Market name mapping: Chinese name -> code
MARKET_NAME_TO_CODE = {
    "A股": "CN",
    "港股": "HK",
    "美股": "US"
}


def _is_cn_etf_symbol(code: str) -> bool:
    code_str = str(code or "").strip().upper().zfill(6)
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def convert_market_code_to_name(market_code: str, stock_code: Optional[str] = None) -> str:
    """Convert market symbols to Chinese names (for single stock analysis services)"""
    if str(market_code).upper() == "ETF":
        return "ETF"
    if str(market_code).upper() == "CN" and stock_code and _is_cn_etf_symbol(stock_code):
        return "ETF"
    return MARKET_CODE_TO_NAME.get(market_code, market_code)


def convert_market_name_to_code(market_name: str) -> str:
    """Convert market Chinese name to code (for database storage)"""
    return MARKET_NAME_TO_CODE.get(market_name, market_name)


class PortfolioService:
    """持仓分析服务"""

    def __init__(self):
        self.db = get_mongo_db()
        self.positions_collection = "real_positions"
        self.analysis_collection = "portfolio_analysis_reports"
        self.position_analysis_collection = "position_analysis_reports"
        self.paper_positions_collection = "paper_positions"
        self.accounts_collection = "real_accounts"
        self.transactions_collection = "capital_transactions"
        self.position_changes_collection = "position_changes"

    # ==================== Capital account management ====================

    async def get_or_create_account(self, user_id: str) -> Dict[str, Any]:
        """获取或创建资金账户"""
        acc = await self.db[self.accounts_collection].find_one({"user_id": user_id})
        if not acc:
            now = now_tz()
            acc = {
                "user_id": user_id,
                "cash": {"CNY": 0.0, "HKD": 0.0, "USD": 0.0},
                "initial_capital": {"CNY": 0.0, "HKD": 0.0, "USD": 0.0},
                "total_deposit": {"CNY": 0.0, "HKD": 0.0, "USD": 0.0},
                "total_withdraw": {"CNY": 0.0, "HKD": 0.0, "USD": 0.0},
                "settings": {
                    "default_market": "CN",
                    "max_position_pct": 30.0,
                    "max_loss_pct": 10.0
                },
                "created_at": now,
                "updated_at": now
            }
            await self.db[self.accounts_collection].insert_one(acc)
        return acc

    async def initialize_account(
        self, user_id: str, initial_capital: float, currency: str = "CNY"
    ) -> Dict[str, Any]:
        """Initialize capital account (set initial capital)"""
        acc = await self.get_or_create_account(user_id)
        now = now_tz()

        # Get current balance
        current_cash = acc.get("cash", {}).get(currency, 0.0)
        new_cash = current_cash + initial_capital

        # Update account
        update_data = {
            f"cash.{currency}": new_cash,
            f"initial_capital.{currency}": acc.get("initial_capital", {}).get(currency, 0.0) + initial_capital,
            "updated_at": now
        }
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

        # record transaction
        transaction = {
            "user_id": user_id,
            "transaction_type": CapitalTransactionType.INITIAL.value,
            "amount": initial_capital,
            "currency": currency,
            "balance_before": current_cash,
            "balance_after": new_cash,
            "description": f"初始资金 {initial_capital:,.2f} {currency}",
            "created_at": now
        }
        await self.db[self.transactions_collection].insert_one(transaction)

        return await self.get_or_create_account(user_id)

    async def deposit(
        self, user_id: str, amount: float, currency: str = "CNY", description: str = None
    ) -> Dict[str, Any]:
        """入金"""
        acc = await self.get_or_create_account(user_id)
        now = now_tz()

        current_cash = acc.get("cash", {}).get(currency, 0.0)
        new_cash = current_cash + amount
        current_deposit = acc.get("total_deposit", {}).get(currency, 0.0)

        update_data = {
            f"cash.{currency}": new_cash,
            f"total_deposit.{currency}": current_deposit + amount,
            "updated_at": now
        }
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

        transaction = {
            "user_id": user_id,
            "transaction_type": CapitalTransactionType.DEPOSIT.value,
            "amount": amount,
            "currency": currency,
            "balance_before": current_cash,
            "balance_after": new_cash,
            "description": description or f"入金 {amount:,.2f} {currency}",
            "created_at": now
        }
        await self.db[self.transactions_collection].insert_one(transaction)

        return await self.get_or_create_account(user_id)

    async def withdraw(
        self, user_id: str, amount: float, currency: str = "CNY", description: str = None
    ) -> Dict[str, Any]:
        """出金"""
        acc = await self.get_or_create_account(user_id)
        now = now_tz()

        current_cash = acc.get("cash", {}).get(currency, 0.0)
        if current_cash < amount:
            raise ValueError(f"可用{currency}不足：需要 {amount:.2f}，可用 {current_cash:.2f}")

        new_cash = current_cash - amount
        current_withdraw = acc.get("total_withdraw", {}).get(currency, 0.0)

        update_data = {
            f"cash.{currency}": new_cash,
            f"total_withdraw.{currency}": current_withdraw + amount,
            "updated_at": now
        }
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

        transaction = {
            "user_id": user_id,
            "transaction_type": CapitalTransactionType.WITHDRAW.value,
            "amount": -amount,  # Withdrawal is a negative number
            "currency": currency,
            "balance_before": current_cash,
            "balance_after": new_cash,
            "description": description or f"出金 {amount:,.2f} {currency}",
            "created_at": now
        }
        await self.db[self.transactions_collection].insert_one(transaction)

        return await self.get_or_create_account(user_id)

    async def update_account_settings(
        self, user_id: str, settings: AccountSettingsRequest
    ) -> Dict[str, Any]:
        """更新账户设置"""
        acc = await self.get_or_create_account(user_id)
        now = now_tz()

        update_data = {"updated_at": now}
        if settings.max_position_pct is not None:
            update_data["settings.max_position_pct"] = settings.max_position_pct
        if settings.max_loss_pct is not None:
            update_data["settings.max_loss_pct"] = settings.max_loss_pct
        if settings.default_market is not None:
            update_data["settings.default_market"] = settings.default_market

        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

        return await self.get_or_create_account(user_id)

    async def get_account_summary(self, user_id: str) -> AccountSummary:
        """Get account summary (including position market value calculation)"""
        acc = await self.get_or_create_account(user_id)

        # Get the market value of positions (only calculate user positions, exclude simulated trading)
        positions = await self.get_positions(user_id, include_market_data=True)
        positions_value = {"CNY": 0.0, "HKD": 0.0, "USD": 0.0}
        for pos in positions:
            # Only positions that are not simulated are calculated
            if pos.source == "paper":
                continue
            currency = pos.currency or "CNY"
            positions_value[currency] = positions_value.get(currency, 0.0) + (pos.market_value or 0.0)

        # Calculate various indicators
        cash = acc.get("cash", {"CNY": 0.0, "HKD": 0.0, "USD": 0.0})
        initial_capital = acc.get("initial_capital", {"CNY": 0.0, "HKD": 0.0, "USD": 0.0})
        total_deposit = acc.get("total_deposit", {"CNY": 0.0, "HKD": 0.0, "USD": 0.0})
        total_withdraw = acc.get("total_withdraw", {"CNY": 0.0, "HKD": 0.0, "USD": 0.0})

        net_capital = {}
        total_assets = {}
        profit = {}
        profit_pct = {}

        for currency in ["CNY", "HKD", "USD"]:
            # net deposit = initial + Deposit - Withdraw
            net = (initial_capital.get(currency, 0.0) +
                   total_deposit.get(currency, 0.0) -
                   total_withdraw.get(currency, 0.0))
            net_capital[currency] = round(net, 2)

            # total assets = Cash + Position market value
            assets = cash.get(currency, 0.0) + positions_value.get(currency, 0.0)
            total_assets[currency] = round(assets, 2)

            # income = Total Assets - Net Deposits
            pnl = assets - net
            profit[currency] = round(pnl, 2)

            # Yield
            if net > 0:
                profit_pct[currency] = round((pnl / net) * 100, 2)
            else:
                profit_pct[currency] = 0.0

        return AccountSummary(
            cash=cash,
            initial_capital=initial_capital,
            total_deposit=total_deposit,
            total_withdraw=total_withdraw,
            net_capital=net_capital,
            positions_value=positions_value,
            total_assets=total_assets,
            profit=profit,
            profit_pct=profit_pct,
            settings=acc.get("settings", {})
        )

    async def get_transactions(
        self, user_id: str, currency: str = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取资金交易记录"""
        query = {"user_id": user_id}
        if currency:
            query["currency"] = currency

        cursor = self.db[self.transactions_collection].find(query).sort("created_at", -1).limit(limit)
        transactions = await cursor.to_list(None)

        # Convert ObjectId
        for t in transactions:
            t["id"] = str(t.pop("_id"))

        return transactions

    async def get_total_capital(self, user_id: str, currency: str = "CNY") -> float:
        """Get the user s total funds (cash + Position market value), used for position analysis"""
        summary = await self.get_account_summary(user_id)
        return summary.total_assets.get(currency, 0.0)

    # ==================== Position change record ====================

    async def record_position_change(
        self,
        user_id: str,
        change_type: PositionChangeType,
        code: str,
        name: str,
        market: str,
        currency: str,
        position_id: str = None,
        quantity_before: int = 0,
        cost_price_before: float = 0.0,
        quantity_after: int = 0,
        cost_price_after: float = 0.0,
        trade_price: float = None,
        realized_profit: float = None,
        description: str = None,
        trade_time: datetime = None,
        extra_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Record position changes

        Args:
            trade_time: Transaction time (the time when the actual transaction occurs, manually entered by the user)
                       If not provided, the current time is used
            extra_data: Additional data (such as handling fee details)
        """
        cost_value_before = quantity_before * cost_price_before
        cost_value_after = quantity_after * cost_price_after
        quantity_change = quantity_after - quantity_before
        cash_change = cost_value_before - cost_value_after  # A positive number means releasing funds

        change_doc = {
            "user_id": user_id,
            "position_id": position_id,
            "code": code,
            "name": name,
            "market": market,
            "currency": currency,
            "change_type": change_type.value,
            "quantity_before": quantity_before,
            "cost_price_before": cost_price_before,
            "cost_value_before": round(cost_value_before, 2),
            "quantity_after": quantity_after,
            "cost_price_after": cost_price_after,
            "cost_value_after": round(cost_value_after, 2),
            "quantity_change": quantity_change,
            "cash_change": round(cash_change, 2),
            "trade_price": trade_price,
            "realized_profit": round(realized_profit, 2) if realized_profit else None,
            "description": description,
            "trade_time": trade_time or now_tz(),  # Transaction time, if not provided the current time will be used
            "created_at": now_tz()  # record creation time
        }

        # Incorporate additional data (such as fee details)
        if extra_data:
            change_doc.update(extra_data)

        result = await self.db[self.position_changes_collection].insert_one(change_doc)
        change_doc["_id"] = result.inserted_id

        logger.info(f"📝 记录持仓变动: {user_id} - {code} - {change_type.value}")
        return change_doc

    async def get_position_changes(
        self,
        user_id: str,
        code: str = None,
        market: str = None,
        change_type: str = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[PositionChangeResponse]:
        """获取持仓变动记录"""
        query = {"user_id": user_id}
        if code:
            query["code"] = code
        if market:
            query["market"] = market
        if change_type:
            query["change_type"] = change_type

        cursor = self.db[self.position_changes_collection].find(query).sort("created_at", -1).skip(skip).limit(limit)
        changes = await cursor.to_list(None)

        result = []
        for c in changes:
            result.append(PositionChangeResponse(
                id=str(c["_id"]),
                position_id=c.get("position_id"),
                code=c["code"],
                name=c["name"],
                market=c["market"],
                currency=c.get("currency", "CNY"),
                change_type=c["change_type"],
                quantity_before=c.get("quantity_before", 0),
                cost_price_before=c.get("cost_price_before", 0.0),
                cost_value_before=c.get("cost_value_before", 0.0),
                quantity_after=c.get("quantity_after", 0),
                cost_price_after=c.get("cost_price_after", 0.0),
                cost_value_after=c.get("cost_value_after", 0.0),
                quantity_change=c.get("quantity_change", 0),
                cash_change=c.get("cash_change", 0.0),
                trade_price=c.get("trade_price"),
                realized_profit=c.get("realized_profit"),
                description=c.get("description"),
                trade_time=c.get("trade_time"),  # trading hours
                created_at=c["created_at"]
            ))

        return result

    async def get_position_changes_count(
        self,
        user_id: str,
        code: str = None,
        market: str = None,
        change_type: str = None
    ) -> int:
        """获取持仓变动记录总数"""
        query = {"user_id": user_id}
        if code:
            query["code"] = code
        if market:
            query["market"] = market
        if change_type:
            query["change_type"] = change_type

        return await self.db[self.position_changes_collection].count_documents(query)

    async def update_position_change(
        self,
        user_id: str,
        change_id: str,
        quantity: int,
        price: float,
        trade_time: datetime = None
    ) -> Dict[str, Any]:
        """
        Modify single transaction record (used to correct entry errors: quantity, unit price)
        Supports buy/add/reduce/sell type. After modification, subsequent records will be recalculated in cascade and positions will be updated.
        """
        from bson import ObjectId
        try:
            obj_id = ObjectId(change_id)
        except Exception:
            raise ValueError("无效的变动记录ID")

        change = await self.db[self.position_changes_collection].find_one(
            {"_id": obj_id, "user_id": user_id}
        )
        if not change:
            raise ValueError("变动记录不存在或无权修改")

        ct = change.get("change_type")
        if ct not in ("buy", "add", "reduce", "sell"):
            raise ValueError("Only supports modification of buying, adding, reducing, and selling records")

        code = change["code"]
        name = change.get("name", code)
        market = change.get("market", "CN")
        currency = change.get("currency", "CNY")

        # Get all change records of the stock, sorted by time
        cursor = self.db[self.position_changes_collection].find(
            {"user_id": user_id, "code": code, "market": market}
        ).sort("created_at", 1)
        all_changes = await cursor.to_list(None)

        edit_idx = None
        for i, c in enumerate(all_changes):
            if c["_id"] == obj_id:
                edit_idx = i
                break
        if edit_idx is None:
            raise ValueError("变动记录不存在")

        # Calculate the state before editing (the previous one's quantity_after, cost_value_after) 
        prev_qty = 0
        prev_cost_val = 0.0
        if edit_idx > 0:
            prev = all_changes[edit_idx - 1]
            prev_qty = prev.get("quantity_after", 0)
            prev_cost_val = prev.get("cost_value_after", 0.0)

        # Calculate edited records based on type
        def compute_updated_change(c, qty_before, cost_val_before, new_qty, new_price):
            ct = c.get("change_type")
            cost_val_before = round(cost_val_before, 2)
            cost_price_before = round(cost_val_before / qty_before, 4) if qty_before > 0 else 0.0

            if ct in ("buy", "add"):
                qty_after = qty_before + new_qty
                cost_val_after = round(qty_before * cost_price_before + new_qty * new_price, 2)
                cost_price_after = round(cost_val_after / qty_after, 4) if qty_after > 0 else 0.0
                cost_val_after = round(qty_after * cost_price_after, 2)
                cash_change = round(cost_val_before - cost_val_after, 2)
                return {
                    "quantity_before": qty_before,
                    "cost_price_before": cost_price_before,
                    "cost_value_before": cost_val_before,
                    "quantity_after": qty_after,
                    "cost_price_after": cost_price_after,
                    "cost_value_after": cost_val_after,
                    "quantity_change": new_qty,
                    "cash_change": cash_change,
                    "trade_price": None,
                    "realized_profit": None,
                }
            else:  # reduce, sell
                qty_after = qty_before - new_qty
                cost_per_share = cost_val_before / qty_before if qty_before > 0 else 0.0
                cost_val_after = round(qty_after * cost_per_share, 2) if qty_after > 0 else 0.0
                cost_price_after = round(cost_val_after / qty_after, 4) if qty_after > 0 else 0.0
                realized = round(new_qty * (new_price - cost_per_share), 2)
                cash_change = round(cost_val_before - cost_val_after + new_qty * new_price, 2)
                return {
                    "quantity_before": qty_before,
                    "cost_price_before": cost_price_before,
                    "cost_value_before": cost_val_before,
                    "quantity_after": qty_after,
                    "cost_price_after": cost_price_after,
                    "cost_value_after": cost_val_after,
                    "quantity_change": -new_qty,
                    "cash_change": cash_change,
                    "trade_price": new_price,
                    "realized_profit": realized,
                }

        # Update edited record
        updated = compute_updated_change(change, prev_qty, prev_cost_val, quantity, price)
        update_doc = {**updated}
        if trade_time:
            update_doc["trade_time"] = trade_time
        await self.db[self.position_changes_collection].update_one(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_doc}
        )

        # Cascading updates to subsequent records (recalculating the derived fields of each transaction with the new curr state)
        curr_qty = updated["quantity_after"]
        curr_cost_val = updated["cost_value_after"]
        for i in range(edit_idx + 1, len(all_changes)):
            c = all_changes[i]
            cid = c["_id"]
            ct = c.get("change_type")
            if ct in ("buy", "add"):
                qty_change = c.get("quantity_change", 0)
                orig_qty_after = c.get("quantity_after", 0)
                orig_cost_after = c.get("cost_price_after", 0)
                unit_price = (orig_cost_after * orig_qty_after - curr_cost_val) / qty_change if qty_change > 0 else 0
                cascade_updated = compute_updated_change(c, curr_qty, curr_cost_val, qty_change, unit_price)
            else:  # reduce, sell
                qty_sold = abs(c.get("quantity_change", 0))
                trade_p = c.get("trade_price", 0)
                cascade_updated = compute_updated_change(c, curr_qty, curr_cost_val, qty_sold, trade_p)
            await self.db[self.position_changes_collection].update_one(
                {"_id": cid, "user_id": user_id},
                {"$set": cascade_updated}
            )
            curr_qty = cascade_updated["quantity_after"]
            curr_cost_val = cascade_updated["cost_value_after"]

        cost_price = round(curr_cost_val / curr_qty, 4) if curr_qty > 0 else 0.0

        # Update positions table
        position = await self.db[self.positions_collection].find_one(
            {"user_id": user_id, "code": code, "market": market}
        )
        if position:
            await self.db[self.positions_collection].update_one(
                {"_id": position["_id"]},
                {"$set": {
                    "quantity": curr_qty,
                    "cost_price": cost_price,
                    "original_avg_cost": cost_price,
                    "updated_at": now_tz()
                }}
            )

        logger.info(f"单笔记录修正: {code} 变动记录 {change_id}, 数量 {quantity}, 单价 {price}")
        return {"message": "记录修正成功", "quantity": curr_qty, "cost_price": cost_price}

    async def delete_position_change(
        self,
        user_id: str,
        change_id: str
    ) -> Dict[str, Any]:
        """
        Delete a single change record, cascade recalculate subsequent records and update positions
        """
        from bson import ObjectId
        try:
            obj_id = ObjectId(change_id)
        except Exception:
            raise ValueError("无效的变动记录ID")

        change = await self.db[self.position_changes_collection].find_one(
            {"_id": obj_id, "user_id": user_id}
        )
        if not change:
            raise ValueError("变动记录不存在或无权删除")

        code = change["code"]
        market = change.get("market", "CN")

        # Get all change records of the stock, sort by time, and exclude those to be deleted
        cursor = self.db[self.position_changes_collection].find(
            {"user_id": user_id, "code": code, "market": market}
        ).sort("created_at", 1)
        all_changes = await cursor.to_list(None)
        remaining = [c for c in all_changes if c["_id"] != obj_id]

        # Delete this record
        await self.db[self.position_changes_collection].delete_one(
            {"_id": obj_id, "user_id": user_id}
        )

        # Replay the remaining records and update each record cascade
        def compute_updated_change(c, qty_before, cost_val_before, new_qty, new_price):
            ct = c.get("change_type")
            cost_val_before = round(cost_val_before, 2)
            cost_price_before = round(cost_val_before / qty_before, 4) if qty_before > 0 else 0.0
            if ct in ("buy", "add"):
                qty_after = qty_before + new_qty
                cost_val_after = round(qty_before * cost_price_before + new_qty * new_price, 2)
                cost_price_after = round(cost_val_after / qty_after, 4) if qty_after > 0 else 0.0
                cost_val_after = round(qty_after * cost_price_after, 2)
                cash_change = round(cost_val_before - cost_val_after, 2)
                return {
                    "quantity_before": qty_before, "cost_price_before": cost_price_before,
                    "cost_value_before": cost_val_before, "quantity_after": qty_after,
                    "cost_price_after": cost_price_after, "cost_value_after": cost_val_after,
                    "quantity_change": new_qty, "cash_change": cash_change,
                    "trade_price": None, "realized_profit": None,
                }
            else:
                qty_after = qty_before - new_qty
                cost_per_share = cost_val_before / qty_before if qty_before > 0 else 0.0
                cost_val_after = round(qty_after * cost_per_share, 2) if qty_after > 0 else 0.0
                cost_price_after = round(cost_val_after / qty_after, 4) if qty_after > 0 else 0.0
                realized = round(new_qty * (new_price - cost_per_share), 2)
                cash_change = round(cost_val_before - cost_val_after + new_qty * new_price, 2)
                return {
                    "quantity_before": qty_before, "cost_price_before": cost_price_before,
                    "cost_value_before": cost_val_before, "quantity_after": qty_after,
                    "cost_price_after": cost_price_after, "cost_value_after": cost_val_after,
                    "quantity_change": -new_qty, "cash_change": cash_change,
                    "trade_price": new_price, "realized_profit": realized,
                }

        curr_qty = 0
        curr_cost_val = 0.0
        for c in remaining:
            cid = c["_id"]
            ct = c.get("change_type")
            if ct in ("buy", "add"):
                qty_change = c.get("quantity_change", 0)
                orig_qty_after = c.get("quantity_after", 0)
                orig_cost_after = c.get("cost_price_after", 0)
                unit_price = (orig_cost_after * orig_qty_after - curr_cost_val) / qty_change if qty_change > 0 else 0
                updated = compute_updated_change(c, curr_qty, curr_cost_val, qty_change, unit_price)
            else:
                qty_sold = abs(c.get("quantity_change", 0))
                trade_p = c.get("trade_price", 0)
                updated = compute_updated_change(c, curr_qty, curr_cost_val, qty_sold, trade_p)
            await self.db[self.position_changes_collection].update_one(
                {"_id": cid, "user_id": user_id},
                {"$set": updated}
            )
            curr_qty = updated["quantity_after"]
            curr_cost_val = updated["cost_value_after"]

        cost_price = round(curr_cost_val / curr_qty, 4) if curr_qty > 0 else 0.0

        position = await self.db[self.positions_collection].find_one(
            {"user_id": user_id, "code": code, "market": market}
        )
        if position:
            await self.db[self.positions_collection].update_one(
                {"_id": position["_id"]},
                {"$set": {
                    "quantity": curr_qty,
                    "cost_price": cost_price,
                    "original_avg_cost": cost_price,
                    "updated_at": now_tz()
                }}
            )
        elif curr_qty > 0:
            # There is a change record but no position, a new one needs to be created
            name = change.get("name", code)
            currency = change.get("currency", "CNY")
            now = now_tz()
            await self.db[self.positions_collection].insert_one({
                "user_id": user_id, "code": code, "name": name, "market": market,
                "currency": currency, "quantity": curr_qty, "cost_price": cost_price,
                "original_avg_cost": cost_price, "source": PositionSource.MANUAL.value,
                "created_at": now, "updated_at": now
            })

        logger.info(f"删除变动记录: {code} {change_id}")
        return {"message": "删除成功", "quantity": curr_qty, "cost_price": cost_price}

    async def reset_position(self, user_id: str, code: str, market: str = "CN") -> Dict[str, Any]:
        """
        Reset the entire position: delete all change records and positions of the stock, and the funds will not be returned (the user will re-enter)
        """
        position = await self.db[self.positions_collection].find_one(
            {"user_id": user_id, "code": code, "market": market}
        )
        deleted_changes = await self.db[self.position_changes_collection].delete_many(
            {"user_id": user_id, "code": code, "market": market}
        )
        result = await self.db[self.positions_collection].delete_one(
            {"user_id": user_id, "code": code, "market": market}
        )
        logger.info(f"重置持仓: {code} {market}, 删除 {deleted_changes.deleted_count} 条变动, 持仓 {'已删' if result.deleted_count else '不存在'}")
        return {
            "message": "重置成功",
            "deleted_changes": deleted_changes.deleted_count,
            "position_deleted": result.deleted_count > 0
        }

    async def reset_all_positions(self, user_id: str) -> Dict[str, Any]:
        """
        Clear all positions: Delete all positions and change records of the user, and completely clear the capital account
        All capital accounts are reset to zero: cash, initial funds, deposits, withdrawals, and accumulated income are all 0
        """
        deleted_changes = await self.db[self.position_changes_collection].delete_many(
            {"user_id": user_id}
        )
        deleted_positions = await self.db[self.positions_collection].delete_many(
            {"user_id": user_id}
        )

        # Completely clear the capital account: cash, initial funds, deposits, and withdrawals are all set to 0
        zero_balance = {"CNY": 0.0, "HKD": 0.0, "USD": 0.0}
        now = now_tz()
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {
                "cash": zero_balance,
                "initial_capital": zero_balance,
                "total_deposit": zero_balance,
                "total_withdraw": zero_balance,
                "updated_at": now
            }}
        )

        logger.info(f"清零全部持仓: user={user_id}, 删除 {deleted_changes.deleted_count} 条变动, {deleted_positions.deleted_count} 个持仓, 资金账户已完全清零")
        return {
            "message": "清零成功",
            "deleted_changes": deleted_changes.deleted_count,
            "deleted_positions": deleted_positions.deleted_count
        }

    async def _clear_existing_real_positions_for_sync(self, user_id: str) -> Dict[str, Any]:
        """Clear the current user s real positions and return the position costs to cash for QMT coverage synchronization."""
        positions = await self.db[self.positions_collection].find(
            {"user_id": user_id, "quantity": {"$gt": 0}}
        ).to_list(None)

        if not positions:
            return {
                "deleted_positions": 0,
                "deleted_changes": 0,
                "restored_cash": {"CNY": 0.0, "HKD": 0.0, "USD": 0.0},
            }

        restored_cash: Dict[str, float] = {"CNY": 0.0, "HKD": 0.0, "USD": 0.0}
        for position in positions:
            currency = position.get("currency", "CNY")
            position_cost = float(position.get("quantity", 0) or 0) * float(position.get("cost_price", 0.0) or 0.0)
            restored_cash[currency] = round(restored_cash.get(currency, 0.0) + position_cost, 2)

        deleted_changes = await self.db[self.position_changes_collection].delete_many({"user_id": user_id})
        deleted_positions = await self.db[self.positions_collection].delete_many({"user_id": user_id})

        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {})
        update_doc: Dict[str, Any] = {"updated_at": now_tz()}
        cash_updated = False
        for currency, amount in restored_cash.items():
            if amount <= 0:
                continue
            update_doc[f"cash.{currency}"] = round(current_cash.get(currency, 0.0) + amount, 2)
            cash_updated = True

        if cash_updated:
            await self.db[self.accounts_collection].update_one(
                {"user_id": user_id},
                {"$set": update_doc}
            )

        logger.info(
            "QMT Clear local real positions before overwriting synchronization: user=%s, Delete %s positions, %s Article changes, Return funds %s",
            user_id,
            deleted_positions.deleted_count,
            deleted_changes.deleted_count,
            restored_cash,
        )
        return {
            "deleted_positions": deleted_positions.deleted_count,
            "deleted_changes": deleted_changes.deleted_count,
            "restored_cash": restored_cash,
        }

    def _build_qmt_import_positions(self, positions_df: Any) -> List[PositionCreate]:
        """Convert the QMT position DataFrame into a PositionCreate list used by the system to import."""
        positions: List[PositionCreate] = []
        if positions_df is None:
            return positions

        for _, row in positions_df.iterrows():
            code = str(row.get("code", "")).strip().zfill(6)
            if not code or len(code) != 6:
                continue

            try:
                quantity = int(float(row.get("quantity", 0)))
                cost_price = float(row.get("cost_price", 0))
            except (TypeError, ValueError):
                continue

            if quantity <= 0 or cost_price <= 0:
                continue

            buy_date = row.get("buy_date")
            notes = row.get("notes")
            positions.append(PositionCreate(
                code=code,
                name=(str(row.get("name", "")).strip() or None),
                market=str(row.get("market", "CN") or "CN").strip() or "CN",
                quantity=quantity,
                cost_price=round(cost_price, 4),
                buy_date=buy_date if isinstance(buy_date, datetime) else None,
                notes=str(notes).strip() if notes not in (None, "") else None,
            ))

        return positions

    async def _sync_qmt_cash_to_account(self, user_id: str, asset_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Mirror QMT account available cash to local funds account."""
        asset_summary = asset_summary or {}
        qmt_cash = asset_summary.get("cash")
        if qmt_cash is None:
            return {
                "cash_synced": False,
                "synced_currency": None,
                "synced_cash": None,
            }

        synced_cash = round(float(qmt_cash), 2)
        await self.get_or_create_account(user_id)
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {"cash.CNY": synced_cash, "updated_at": now_tz()}}
        )

        logger.info("QMT Cash synchronization completed: user=%s, CNY=%s", user_id, synced_cash)
        return {
            "cash_synced": True,
            "synced_currency": "CNY",
            "synced_cash": synced_cash,
        }

    async def preview_qmt_position_import(
        self,
        user_id: str,
        account_id: str,
        account_type: str = "STOCK",
    ) -> Dict[str, Any]:
        """Preview the impact of QMT position coverage synchronization on the current account."""
        from app.services.data_sources.qmt_adapter import QMTAdapter

        adapter = QMTAdapter()
        snapshot = await asyncio.to_thread(adapter.query_account_snapshot, account_id, account_type)
        if snapshot is None:
            raise ValueError("QMT No account information found, please confirm that QMT is logged in and the account is available")

        positions_df = snapshot.get("positions_df")
        asset_summary = snapshot.get("asset") or {}
        importable_positions = self._build_qmt_import_positions(positions_df)

        current_position_count = await self.db[self.positions_collection].count_documents(
            {"user_id": user_id, "quantity": {"$gt": 0}}
        )
        current_change_count = await self.db[self.position_changes_collection].count_documents({"user_id": user_id})
        account_summary = await self.get_account_summary(user_id)

        qmt_position_count = 0 if positions_df is None else len(positions_df)
        qmt_cash = asset_summary.get("cash")
        qmt_market_value = asset_summary.get("market_value")
        qmt_total_asset = asset_summary.get("total_asset")

        return {
            "account_id": account_id,
            "account_type": account_type,
            "will_replace_position_count": current_position_count,
            "will_clear_change_count": current_change_count,
            "local_cash": round(account_summary.cash.get("CNY", 0.0), 2),
            "local_total_assets": round(account_summary.total_assets.get("CNY", 0.0), 2),
            "qmt_position_count": qmt_position_count,
            "qmt_importable_count": len(importable_positions),
            "qmt_cash": round(float(qmt_cash), 2) if qmt_cash is not None else None,
            "qmt_market_value": round(float(qmt_market_value), 2) if qmt_market_value is not None else None,
            "qmt_total_asset": round(float(qmt_total_asset), 2) if qmt_total_asset is not None else None,
            "will_sync_cash": qmt_cash is not None,
            "cash_currency": "CNY",
            "sync_note": "The local real position will be overwritten, and the CNY available cash will be updated to the QMT account cash; the initial funds and cumulative deposit and withdrawal records will remain unchanged.",
        }

    # ==================== Position management ====================

    async def get_positions(
        self, 
        user_id: str, 
        source: str = "all",
        include_market_data: bool = True
    ) -> List[PositionResponse]:
        """
        Get the user s position list
        
        Args:
            user_id: User ID
            source: Data source (all/real/paper)
            include_market_data: Whether to include real-time quotes
        """
        positions = []

        # Get user holdings (only get quantity > 0 position)
        if source in ["all", "real"]:
            real_positions = await self.db[self.positions_collection].find(
                {"user_id": user_id, "quantity": {"$gt": 0}}
            ).to_list(None)

            for p in real_positions:
                pos = await self._enrich_position(p, "real", include_market_data)
                positions.append(pos)

        # Get simulated trading positions (only get quantity > 0 position)
        if source in ["all", "paper"]:
            paper_positions = await self.db[self.paper_positions_collection].find(
                {"user_id": user_id, "quantity": {"$gt": 0}}
            ).to_list(None)
            
            for p in paper_positions:
                pos = await self._enrich_position(p, "paper", include_market_data)
                positions.append(pos)

        return positions

    async def get_history_positions(
        self,
        user_id: str,
        source: str = "real",
        limit: int = 50,
        skip: int = 0
    ) -> Dict[str, Any]:
        """
        Get historical positions (records of cleared positions)
        Aggregated by ticker, showing a summary of trades for each stock
        Only positions that have been completely liquidated (buy quantity = quantity sold)
        """
        # Aggregate historical position data from change records
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": {"code": "$code", "market": "$market"},
                "name": {"$last": "$name"},
                "currency": {"$last": "$currency"},
                "first_buy_date": {"$min": {"$cond": [
                    {"$in": ["$change_type", ["buy", "add"]]},
                    "$trade_time", None
                ]}},
                "last_sell_date": {"$max": {"$cond": [
                    {"$in": ["$change_type", ["sell", "reduce"]]},
                    "$trade_time", None
                ]}},
                "total_buy_qty": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["buy", "add"]]},
                    {"$abs": "$quantity_change"}, 0
                ]}},
                "total_sell_qty": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["sell", "reduce"]]},
                    {"$abs": "$quantity_change"}, 0
                ]}},
                "total_buy_amount": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["buy", "add"]]},
                    {"$abs": "$cash_change"}, 0
                ]}},
                "total_sell_amount": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["sell", "reduce"]]},
                    {"$abs": "$cash_change"}, 0
                ]}},
                "total_realized_pnl": {"$sum": {"$ifNull": ["$realized_profit", 0]}},
                "avg_buy_price": {"$avg": {"$cond": [
                    {"$in": ["$change_type", ["buy", "add"]]},
                    "$cost_price_after", None
                ]}},
                "avg_sell_price": {"$avg": {"$cond": [
                    {"$in": ["$change_type", ["sell", "reduce"]]},
                    "$trade_price", None
                ]}}
            }},
            # Only displayed positions that have been completely cleared (buying quantity = quantity sold)
            {"$match": {
                "$expr": {
                    "$and": [
                        {"$gt": ["$total_sell_qty", 0]},
                        {"$eq": ["$total_buy_qty", "$total_sell_qty"]}
                    ]
                }
            }},
            {"$sort": {"last_sell_date": -1}},
            {"$skip": skip},
            {"$limit": limit}
        ]

        results = await self.db[self.position_changes_collection].aggregate(pipeline).to_list(None)

        # Calculate the total
        count_pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": {"code": "$code", "market": "$market"},
                "total_buy_qty": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["buy", "add"]]},
                    {"$abs": "$quantity_change"}, 0
                ]}},
                "total_sell_qty": {"$sum": {"$cond": [
                    {"$in": ["$change_type", ["sell", "reduce"]]},
                    {"$abs": "$quantity_change"}, 0
                ]}}
            }},
            {"$match": {
                "$expr": {
                    "$and": [
                        {"$gt": ["$total_sell_qty", 0]},
                        {"$eq": ["$total_buy_qty", "$total_sell_qty"]}
                    ]
                }
            }},
            {"$count": "total"}
        ]
        count_result = await self.db[self.position_changes_collection].aggregate(count_pipeline).to_list(None)
        total = count_result[0]["total"] if count_result else 0

        items = []
        for r in results:
            # Calculate holding days
            first_buy = r.get("first_buy_date")
            last_sell = r.get("last_sell_date")
            hold_days = 0
            if first_buy and last_sell:
                # 🔥 Handle dates of string type (MongoDB may return strings)
                if isinstance(first_buy, str):
                    first_buy = datetime.fromisoformat(first_buy.replace('Z', '+00:00'))
                if isinstance(last_sell, str):
                    last_sell = datetime.fromisoformat(last_sell.replace('Z', '+00:00'))
                delta = last_sell - first_buy
                hold_days = delta.days

            # Calculate profit and loss percentage
            total_buy_amount = r.get("total_buy_amount", 0)
            total_realized_pnl = r.get("total_realized_pnl", 0)
            realized_pnl_pct = 0
            if total_buy_amount > 0:
                realized_pnl_pct = (total_realized_pnl / total_buy_amount) * 100

            items.append({
                "id": f"{r['_id']['code']}_{r['_id']['market']}",
                "code": r["_id"]["code"],
                "name": r.get("name"),
                "market": r["_id"]["market"],
                "currency": r.get("currency", "CNY"),
                "total_buy_qty": r.get("total_buy_qty", 0),
                "total_sell_qty": r.get("total_sell_qty", 0),
                "avg_buy_price": round(r.get("avg_buy_price") or 0, 2),
                "avg_sell_price": round(r.get("avg_sell_price") or 0, 2),
                "first_buy_date": first_buy.isoformat() if first_buy else None,
                "last_trade_date": last_sell.isoformat() if last_sell else None,
                "realized_pnl": round(total_realized_pnl, 2),
                "realized_pnl_pct": round(realized_pnl_pct, 2),
                "hold_days": hold_days,
                "cleared_at": last_sell.isoformat() if last_sell else None
            })

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "skip": skip
        }

    async def _enrich_position(
        self, 
        position: Dict, 
        source: str,
        include_market_data: bool = True
    ) -> PositionResponse:
        """Enrich position data (add real-time quotes)"""
        code = position.get("code", "")
        market = position.get("market", "CN")
        quantity = int(position.get("quantity", 0))
        
        # Get cost price
        if source == "paper":
            cost_price = float(position.get("avg_cost", 0.0))
            original_avg_cost = cost_price  # There is no original cost distinction for simulated disks
        else:
            cost_price = float(position.get("cost_price", 0.0))
            # Backward compatibility: used when original_avg_cost is not available cost_price
            original_avg_cost = position.get("original_avg_cost")
            if original_avg_cost is None:
                original_avg_cost = cost_price
            else:
                original_avg_cost = float(original_avg_cost)

        # Get real-time prices
        current_price = None
        market_value = None
        unrealized_pnl = None
        unrealized_pnl_pct = None

        if include_market_data:
            current_price = await self._get_stock_price(code, market)
            if current_price and current_price > 0:
                market_value = round(current_price * quantity, 2)
                cost_value = cost_price * quantity
                if cost_value > 0:
                    unrealized_pnl = round(market_value - cost_value, 2)
                    unrealized_pnl_pct = round((unrealized_pnl / cost_value) * 100, 2)

        # Get stock name
        name = position.get("name")
        if not name:
            name = await self._get_stock_name(code, market)

        # 🔥 Get industry information: If empty, try to get and update from the database
        industry = position.get("industry")
        if not industry or industry == "未知":
            logger.info(f"🔄 [丰富持仓] 持仓 {code} ({source}) 行业为空或'未知'，尝试获取...")
            industry = await self._get_stock_industry(code, market)
            logger.info(f"📊 [丰富持仓] 持仓 {code} 获取到的行业: {industry}")
            
            # If industry information is obtained, update it to the database
            if industry:
                try:
                    position_id = position.get("_id")
                    if position_id:
                        # Select the corresponding collection according to the data source
                        collection_name = self.paper_positions_collection if source == "paper" else self.positions_collection
                        
                        update_result = await self.db[collection_name].update_one(
                            {"_id": position_id},
                            {"$set": {"industry": industry, "updated_at": now_tz()}}
                        )
                        if update_result.modified_count > 0:
                            logger.info(f"✅ [丰富持仓] 已更新持仓 {code} ({source}) 的行业信息: {industry}")
                        else:
                            logger.debug(f"ℹ️ [丰富持仓] 持仓 {code} 行业信息未修改（可能已存在）")
                except Exception as e:
                    logger.warning(f"⚠️ [丰富持仓] 更新持仓 {code} 行业信息失败: {e}")
            else:
                # If it is not available, use"unknown"
                logger.warning(f"⚠️ [丰富持仓] 持仓 {code} 无法获取行业信息，使用'未知'")
                industry = "未知"

        return PositionResponse(
            id=str(position.get("_id", "")),
            code=code,
            name=name,
            market=market,
            currency=position.get("currency", "CNY"),
            quantity=quantity,
            cost_price=cost_price,
            original_avg_cost=round(original_avg_cost, 4) if original_avg_cost is not None else None,
            original_cost_price=position.get("original_cost_price"),
            price_adjust_type=position.get("price_adjust_type"),
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            buy_date=position.get("buy_date"),
            industry=industry,
            notes=position.get("notes"),
            source=source,
            created_at=position.get("created_at", now_tz()),
            updated_at=position.get("updated_at", now_tz())
        )

    async def add_position(
        self,
        user_id: str,
        data: PositionCreate,
        source: PositionSource = PositionSource.MANUAL,
        validate_input: bool = True,
    ) -> PositionResponse:
        """Add user position (if there is already a position, it will be added automatically)"""
        # Historical data verification is still retained during manual entry; QMT snapshot synchronization will skip this level of verification and write directly according to known positions.
        adjust_info = None  # Restoration conversion information
        if validate_input:
            current_price = await self._get_stock_price(data.code, data.market)
            if not current_price or current_price <= 0:
                raise ValueError(
                    f"股票 {data.code} 暂无行情数据，无法添加持仓。请先在「股票筛选」或「单股分析」中同步该股票的历史数据后再添加。"
                )

            # 🔥 You must fill in the purchase date and verify whether the cost price is within the historical high and low price range of that day
            if not data.buy_date:
                raise ValueError("When adding a position, the purchase date must be filled in to verify whether the cost price is correct.")
            adjust_info = await self._validate_cost_price_against_historical(
                code=data.code,
                market=data.market,
                buy_date=data.buy_date,
                cost_price=data.cost_price
            )

        # ---- Restoration price conversion ----
        # adjust_info If it is not None, it means that the user input is the non-rights restoration price and needs to be converted to the pre-rights restoration price.
        original_cost_price = None  # Save the original irrevocable price
        price_adjust_type = None    # Price mark
        effective_cost_price = data.cost_price  # Cost price actually used for calculation (before re-righting)

        if adjust_info and adjust_info.get("adjust_type") == "none":
            original_cost_price = data.cost_price  # Save the non-rightsing price originally input by the user
            price_adjust_type = "none"
            qfq_price = adjust_info.get("qfq_price")
            if qfq_price is not None and qfq_price > 0:
                effective_cost_price = qfq_price  # Use the converted pre-right price
                logger.info(
                    f"🔄 成本价转换：不复权 {data.cost_price:.2f} → 前复权 {qfq_price:.2f}"
                    f" (Reweighting factor={adjust_info.get('adj_factor', 'N/A')}) "
                )
            else:
                # Unable to convert, retain the non-rights price (there may be small errors in subsequent profit and loss calculations)
                effective_cost_price = data.cost_price
                logger.warning(
                    f"⚠️ 无法将不复权价格 {data.cost_price:.2f} 转为前复权，"
                    f"It will be saved at a non-restorable price (the profit and loss calculation may contain errors caused by dividends)"
                )

        # Get stock name and industry
        name = data.name
        logger.debug(f"📝 [添加持仓] 股票代码: {data.code}, 市场: {data.market}, 已有名称: {name}")
        
        # 🔥 Fix: Try to get industry information regardless of name being empty
        # If the name is empty, get the name first; if the name is not empty, also get the industry information
        if not name:
            name = await self._get_stock_name(data.code, data.market)
            logger.debug(f"📝 [Add position] The name obtained: {name}")
        
        # Always try to get industry information (even if the name already exists)
        industry = await self._get_stock_industry(data.code, data.market)
        logger.info(f"📝 [添加持仓] 股票 {data.code} 行业信息: {industry}")

        # Calculate holding cost (using converted pre-right price)
        currency = self._get_currency_by_market(data.market)
        position_cost = data.quantity * effective_cost_price

        # 🔥 Calculate purchase fees
        trade_amount = data.quantity * effective_cost_price
        market_rules = await self._get_real_market_rules(data.market)
        commission_info = self._calculate_real_commission(data.market, "buy", trade_amount, market_rules or {})
        total_commission = commission_info["commission"]
        total_cost = position_cost + total_commission  # total expenditure = Transaction amount + handling fee

        # Deduct costs from funding account+handling fee
        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {}).get(currency, 0.0)

        if current_cash < total_cost:
            raise ValueError(f"可用资金不足。当前可用: {current_cash:.2f} {currency}，需要: {total_cost:.2f} {currency}（含手续费 {total_commission:.2f}）")

        # Check whether there is already a position in the stock (same user, same stock code, same market)
        existing_position = await self.db[self.positions_collection].find_one({
            "user_id": user_id,
            "code": data.code,
            "market": data.market,
            "quantity": {"$gt": 0}  # Only search for positions with a quantity greater than 0 (uncleared positions)
        })

        if existing_position:
            # Already have a position, perform add position operation
            old_quantity = existing_position.get("quantity", 0)
            old_cost_price = existing_position.get("cost_price", 0.0)
            old_total_cost = old_quantity * old_cost_price

            # Calculate new position quantity and average cost price
            new_quantity = old_quantity + data.quantity
            new_total_cost = old_total_cost + position_cost
            new_cost_price = new_total_cost / new_quantity if new_quantity > 0 else 0.0

            # Deduct funds (including handling fees)
            new_cash = current_cash - total_cost
            await self.db[self.accounts_collection].update_one(
                {"user_id": user_id},
                {"$set": {f"cash.{currency}": new_cash, "updated_at": now_tz()}}
            )

            # Update the position record (when adding a position, cost_price and original_avg_cost are both weighted average prices)
            now = now_tz()
            update_fields = {
                "quantity": new_quantity,
                "cost_price": round(new_cost_price, 4),
                "original_avg_cost": round(new_cost_price, 4),
                "updated_at": now,
                "notes": data.notes if data.notes else existing_position.get("notes")
            }
            # If there is a no-rights mark when adding a position, it will also be saved to the position record.
            if original_cost_price is not None:
                update_fields["original_cost_price"] = original_cost_price
                update_fields["price_adjust_type"] = price_adjust_type
            await self.db[self.positions_collection].update_one(
                {"_id": existing_position["_id"]},
                {"$set": update_fields}
            )

            # Record position changes (position addition, including handling fee details)
            change_description = f"加仓: +{data.quantity}股 @ {effective_cost_price:.2f}"
            if total_commission > 0:
                change_description += f"（手续费 ¥{total_commission:.2f}）"
            await self.record_position_change(
                user_id=user_id,
                change_type=PositionChangeType.BUY,
                code=data.code,
                name=name or existing_position.get("name") or data.code,
                market=data.market,
                currency=currency,
                position_id=str(existing_position["_id"]),
                quantity_before=old_quantity,
                cost_price_before=old_cost_price,
                quantity_after=new_quantity,
                cost_price_after=new_cost_price,
                description=change_description,
                extra_data={"commission": commission_info} if total_commission > 0 else None
            )

            logger.info(f"✅ 加仓成功: {user_id} - {data.code}，{old_quantity} → {new_quantity}股，成本价: {old_cost_price:.2f} → {new_cost_price:.2f}，扣除资金: {total_cost:.2f} {currency}（含手续费 {total_commission:.2f}）")

            # Return updated positions
            updated_position = await self.db[self.positions_collection].find_one({"_id": existing_position["_id"]})
            return await self._enrich_position(updated_position, "real")

        # There is no existing position, create a new position record
        # Deduct funds (including handling fees)
        new_cash = current_cash - total_cost
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {f"cash.{currency}": new_cash, "updated_at": now_tz()}}
        )

        now = now_tz()
        position_doc = {
            "user_id": user_id,
            "code": data.code,
            "name": name,
            "market": data.market,
            "currency": currency,
            "quantity": data.quantity,
            "cost_price": effective_cost_price,
            "original_avg_cost": effective_cost_price,
            "original_cost_price": original_cost_price,
            "price_adjust_type": price_adjust_type,
            "buy_date": data.buy_date,
            "industry": industry,
            "notes": data.notes,
            "source": source.value,
            "created_at": now,
            "updated_at": now
        }

        result = await self.db[self.positions_collection].insert_one(position_doc)
        position_doc["_id"] = result.inserted_id

        # Record position changes (including handling fee details)
        change_description = f"新建持仓: {data.notes}" if data.notes else "新建持仓"
        if total_commission > 0:
            change_description += f"（手续费 ¥{total_commission:.2f}）"
        await self.record_position_change(
            user_id=user_id,
            change_type=PositionChangeType.BUY,
            code=data.code,
            name=name or data.code,
            market=data.market,
            currency=currency,
            position_id=str(result.inserted_id),
            quantity_before=0,
            cost_price_before=0.0,
            quantity_after=data.quantity,
            cost_price_after=effective_cost_price,
            description=change_description,
            trade_time=data.buy_date,
            extra_data={"commission": commission_info} if total_commission > 0 else None
        )

        logger.info(f"✅ 新建持仓成功: {user_id} - {data.code}，扣除资金: {total_cost:.2f} {currency}（含手续费 {total_commission:.2f}）")
        return await self._enrich_position(position_doc, "real")

    async def operate_position(
        self,
        user_id: str,
        data: PositionOperationRequest
    ) -> Dict[str, Any]:
        """
        Execute position operations (increase positions, reduce positions, dividends, split shares, combine shares, adjust costs)
        """
        # Find existing positions in this stock
        existing_position = await self.db[self.positions_collection].find_one({
            "user_id": user_id,
            "code": data.code,
            "market": data.market,
            "quantity": {"$gt": 0}
        })

        if not existing_position and data.operation_type != PositionOperationType.ADD:
            raise ValueError(f"未找到 {data.code} 的持仓记录")

        currency = self._get_currency_by_market(data.market)
        now = now_tz()

        if data.operation_type == PositionOperationType.ADD:
            # Add position: reuse add_position logic
            return await self._handle_add_operation(user_id, data, existing_position, currency, now)

        elif data.operation_type == PositionOperationType.REDUCE:
            # Reduce positions
            return await self._handle_reduce_operation(user_id, data, existing_position, currency, now)

        elif data.operation_type == PositionOperationType.DIVIDEND:
            # dividend
            return await self._handle_dividend_operation(user_id, data, existing_position, currency, now)

        elif data.operation_type == PositionOperationType.SPLIT:
            # stock split
            return await self._handle_split_operation(user_id, data, existing_position, currency, now)

        elif data.operation_type == PositionOperationType.MERGE:
            # partnership
            return await self._handle_merge_operation(user_id, data, existing_position, currency, now)

        elif data.operation_type == PositionOperationType.ADJUST:
            # Adjust cost price
            return await self._handle_adjust_operation(user_id, data, existing_position, currency, now)

        else:
            raise ValueError(f"不支持的操作类型: {data.operation_type}")

    async def _handle_add_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Optional[Dict], currency: str, now
    ) -> Dict[str, Any]:
        """处理加仓操作"""
        if not data.quantity or not data.price:
            raise ValueError("加仓需要指定数量和价格")

        position_cost = data.quantity * data.price

        # 🔥 Calculate purchase fees
        market_rules = await self._get_real_market_rules(data.market)
        commission_info = self._calculate_real_commission(data.market, "buy", position_cost, market_rules or {})
        total_commission = commission_info["commission"]
        total_cost = position_cost + total_commission

        # Check funds
        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {}).get(currency, 0.0)
        if current_cash < total_cost:
            raise ValueError(f"可用资金不足。当前: {current_cash:.2f}，需要: {total_cost:.2f}（含手续费 {total_commission:.2f}）")

        # Deduct funds (including handling fees)
        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {f"cash.{currency}": current_cash - total_cost, "updated_at": now}}
        )

        if existing_position:
            # Already have positions, merge them (when adding positions, cost_price and original_avg_cost are both weighted average prices)
            old_qty = existing_position["quantity"]
            old_cost = existing_position["cost_price"]
            new_qty = old_qty + data.quantity
            new_cost = (old_qty * old_cost + position_cost) / new_qty

            await self.db[self.positions_collection].update_one(
                {"_id": existing_position["_id"]},
                {"$set": {
                    "quantity": new_qty,
                    "cost_price": round(new_cost, 4),
                    "original_avg_cost": round(new_cost, 4),
                    "updated_at": now
                }}
            )

            await self.record_position_change(
                user_id=user_id, change_type=PositionChangeType.BUY,
                code=data.code, name=existing_position.get("name", data.code),
                market=data.market, currency=currency,
                position_id=str(existing_position["_id"]),
                quantity_before=old_qty, cost_price_before=old_cost,
                quantity_after=new_qty, cost_price_after=new_cost,
                description=f"加仓: +{data.quantity}股 @ {data.price:.2f}",
                trade_time=data.operation_date  # Use operation date as transaction time
            )

            logger.info(f"✅ 加仓成功: {data.code}, {old_qty} → {new_qty}股")
            return {"message": "加仓成功", "new_quantity": new_qty, "new_cost_price": round(new_cost, 4)}
        else:
            # New position
            name = await self._get_stock_name(data.code, data.market)
            position_doc = {
                "user_id": user_id, "code": data.code, "name": name,
                "market": data.market, "currency": currency,
                "quantity": data.quantity, "cost_price": data.price,
                "original_avg_cost": data.price,
                "buy_date": data.operation_date or now,
                "source": PositionSource.MANUAL.value,
                "created_at": now, "updated_at": now
            }
            result = await self.db[self.positions_collection].insert_one(position_doc)

            await self.record_position_change(
                user_id=user_id, change_type=PositionChangeType.BUY,
                code=data.code, name=name or data.code,
                market=data.market, currency=currency,
                position_id=str(result.inserted_id),
                quantity_before=0, cost_price_before=0.0,
                quantity_after=data.quantity, cost_price_after=data.price,
                description="新建持仓",
                trade_time=data.operation_date  # Use operation date as transaction time
            )

            logger.info(f"✅ 新建持仓: {data.code}, {data.quantity}股 @ {data.price:.2f}")
            return {"message": "新建持仓成功", "new_quantity": data.quantity, "new_cost_price": data.price}

    async def _handle_reduce_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Dict, currency: str, now
    ) -> Dict[str, Any]:
        """处理减仓操作"""
        if not data.quantity or not data.price:
            raise ValueError("减仓需要指定数量和价格")

        old_qty = existing_position["quantity"]
        old_cost = existing_position["cost_price"]

        if data.quantity > old_qty:
            raise ValueError(f"减仓数量({data.quantity})超过持仓数量({old_qty})")

        # Calculate selling amount
        sell_amount = data.quantity * data.price

        # 🔥 Calculate selling fees
        market_rules = await self._get_real_market_rules(data.market)
        commission_info = self._calculate_real_commission(data.market, "sell", sell_amount, market_rules or {})
        total_commission = commission_info["commission"]
        net_proceeds = sell_amount - total_commission  # Actual arrival = Amount sold - handling fee

        # Add to cash (after deducting handling fees)
        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {}).get(currency, 0.0)

        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {f"cash.{currency}": current_cash + net_proceeds, "updated_at": now}}
        )

        new_qty = old_qty - data.quantity
        old_total_cost = old_qty * old_cost

        if new_qty == 0:
            # Clearance
            await self.db[self.positions_collection].update_one(
                {"_id": existing_position["_id"]},
                {"$set": {"quantity": 0, "updated_at": now}}
            )
            change_type = PositionChangeType.SELL
            description = f"清仓: -{data.quantity}股 @ {data.price:.2f}"
            if total_commission > 0:
                description += f"（手续费 ¥{total_commission:.2f}）"
            new_cost = 0.0
        else:
            # Partial reduction of positions: using dilution cost logic (consistent with mainstream trading software)
            # remaining cost = (Total cost of original position - Amount of current sale) / Remaining quantity
            # When you reduce your position with profit, the cost decreases, and when you reduce your position with loss, the cost increases.
            remaining_cost = old_total_cost - sell_amount
            new_cost = remaining_cost / new_qty if new_qty > 0 else 0.0
            # To avoid negative costs (when extremely profitable), the minimum guarantee is 0.01
            new_cost = max(0.01, round(new_cost, 4))

            await self.db[self.positions_collection].update_one(
                {"_id": existing_position["_id"]},
                {"$set": {"quantity": new_qty, "cost_price": new_cost, "updated_at": now}}
            )
            change_type = PositionChangeType.REDUCE
            description = f"减仓: -{data.quantity}股 @ {data.price:.2f}，成本 {old_cost:.2f} → {new_cost:.2f}"
            if total_commission > 0:
                description += f"（手续费 ¥{total_commission:.2f}）"

        # Calculate profit and loss (actual profit and loss after deducting handling fees)
        profit = (data.price - old_cost) * data.quantity - total_commission
        profit_pct = (profit) / (old_cost * data.quantity) * 100 if old_cost > 0 else 0

        await self.record_position_change(
            user_id=user_id, change_type=change_type,
            code=data.code, name=existing_position.get("name", data.code),
            market=data.market, currency=currency,
            position_id=str(existing_position["_id"]),
            quantity_before=old_qty, cost_price_before=old_cost,
            quantity_after=new_qty, cost_price_after=new_cost,
            trade_price=data.price,
            realized_profit=profit,
            description=description,
            trade_time=data.operation_date,
            extra_data={"commission": commission_info} if total_commission > 0 else None
        )

        logger.info(
            f"✅ 减仓成功: {data.code}, {old_qty} → {new_qty}股, "
            f"cost {old_cost:.2f} → {new_cost:.2f}, Profit and loss: {profit:.2f}"
        )
        result = {
            "message": "清仓成功" if new_qty == 0 else "减仓成功",
            "new_quantity": new_qty,
            "sell_amount": round(sell_amount, 2),
            "net_proceeds": round(net_proceeds, 2),
            "commission": round(total_commission, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
        }
        if new_qty > 0:
            result["new_cost_price"] = round(new_cost, 4)
        return result

    async def _handle_dividend_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Dict, currency: str, now
    ) -> Dict[str, Any]:
        """处理分红操作"""
        if not data.dividend_amount or data.dividend_amount <= 0:
            raise ValueError("分红需要指定分红金额")

        # Dividend amount added to cash
        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {}).get(currency, 0.0)

        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {f"cash.{currency}": current_cash + data.dividend_amount, "updated_at": now}}
        )

        # Record changes
        await self.record_position_change(
            user_id=user_id, change_type=PositionChangeType.ADJUST,
            code=data.code, name=existing_position.get("name", data.code),
            market=data.market, currency=currency,
            position_id=str(existing_position["_id"]),
            quantity_before=existing_position["quantity"],
            cost_price_before=existing_position["cost_price"],
            quantity_after=existing_position["quantity"],
            cost_price_after=existing_position["cost_price"],
            description=f"现金分红: +{data.dividend_amount:.2f} {currency}",
            trade_time=data.operation_date  # Use operation date as transaction time
        )

        logger.info(f"✅ 分红成功: {data.code}, +{data.dividend_amount:.2f} {currency}")
        return {"message": "分红记录成功", "dividend_amount": data.dividend_amount}

    async def _handle_split_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Dict, currency: str, now
    ) -> Dict[str, Any]:
        """Handle stock split operations (such as 10 for 10, the ratio is 2:1) """
        if not data.ratio:
            raise ValueError("A stock split requires a specified ratio, such as 2:1")

        try:
            parts = data.ratio.split(":")
            new_ratio = float(parts[0])
            old_ratio = float(parts[1])
            multiplier = new_ratio / old_ratio
        except Exception:
            raise ValueError("Scale format error, should be x:y format, such as 2:1")

        old_qty = existing_position["quantity"]
        old_cost = existing_position["cost_price"]

        new_qty = int(old_qty * multiplier)
        new_cost = old_cost / multiplier

        await self.db[self.positions_collection].update_one(
            {"_id": existing_position["_id"]},
            {"$set": {"quantity": new_qty, "cost_price": round(new_cost, 4), "updated_at": now}}
        )

        await self.record_position_change(
            user_id=user_id, change_type=PositionChangeType.ADJUST,
            code=data.code, name=existing_position.get("name", data.code),
            market=data.market, currency=currency,
            position_id=str(existing_position["_id"]),
            quantity_before=old_qty, cost_price_before=old_cost,
            quantity_after=new_qty, cost_price_after=new_cost,
            description=f"拆股: {data.ratio}，数量 {old_qty} → {new_qty}",
            trade_time=data.operation_date  # Use operation date as transaction time
        )

        logger.info(f"✅ 拆股成功: {data.code}, {old_qty} → {new_qty}股")
        return {"message": "拆股成功", "new_quantity": new_qty, "new_cost_price": round(new_cost, 4)}

    async def _handle_merge_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Dict, currency: str, now
    ) -> Dict[str, Any]:
        """Handles partnership operations (e.g. 10-in-1, with a ratio of 1:10) """
        if not data.ratio:
            raise ValueError("A partnership requires a specified proportion, such as 1:10")

        try:
            parts = data.ratio.split(":")
            new_ratio = float(parts[0])
            old_ratio = float(parts[1])
            multiplier = new_ratio / old_ratio
        except Exception:
            raise ValueError("Scale format error, should be x:y format, such as 1:10")

        old_qty = existing_position["quantity"]
        old_cost = existing_position["cost_price"]

        new_qty = int(old_qty * multiplier)
        new_cost = old_cost / multiplier

        if new_qty < 1:
            raise ValueError(f"合股后数量({new_qty})不能小于1")

        await self.db[self.positions_collection].update_one(
            {"_id": existing_position["_id"]},
            {"$set": {"quantity": new_qty, "cost_price": round(new_cost, 4), "updated_at": now}}
        )

        await self.record_position_change(
            user_id=user_id, change_type=PositionChangeType.ADJUST,
            code=data.code, name=existing_position.get("name", data.code),
            market=data.market, currency=currency,
            position_id=str(existing_position["_id"]),
            quantity_before=old_qty, cost_price_before=old_cost,
            quantity_after=new_qty, cost_price_after=new_cost,
            description=f"合股: {data.ratio}，数量 {old_qty} → {new_qty}",
            trade_time=data.operation_date  # Use operation date as transaction time
        )

        logger.info(f"✅ 合股成功: {data.code}, {old_qty} → {new_qty}股")
        return {"message": "合股成功", "new_quantity": new_qty, "new_cost_price": round(new_cost, 4)}

    async def _handle_adjust_operation(
        self, user_id: str, data: PositionOperationRequest,
        existing_position: Dict, currency: str, now
    ) -> Dict[str, Any]:
        """处理调整成本价操作"""
        if not data.new_cost_price or data.new_cost_price <= 0:
            raise ValueError("Adjusting the cost price requires specifying a new cost price")

        old_cost = existing_position["cost_price"]

        await self.db[self.positions_collection].update_one(
            {"_id": existing_position["_id"]},
            {"$set": {"cost_price": data.new_cost_price, "updated_at": now}}
        )

        await self.record_position_change(
            user_id=user_id, change_type=PositionChangeType.ADJUST,
            code=data.code, name=existing_position.get("name", data.code),
            market=data.market, currency=currency,
            position_id=str(existing_position["_id"]),
            quantity_before=existing_position["quantity"],
            cost_price_before=old_cost,
            quantity_after=existing_position["quantity"],
            cost_price_after=data.new_cost_price,
            description=f"调整成本价: {old_cost:.2f} → {data.new_cost_price:.2f}",
            trade_time=data.operation_date  # Use operation date as transaction time
        )

        logger.info(f"✅ 调整成本价成功: {data.code}, {old_cost:.2f} → {data.new_cost_price:.2f}")
        return {"message": "调整成本价成功", "new_cost_price": data.new_cost_price}

    async def update_position(
        self,
        user_id: str,
        position_id: str,
        data: PositionUpdate
    ) -> Optional[PositionResponse]:
        """更新持仓"""
        try:
            obj_id = ObjectId(position_id)
        except Exception:
            logger.error(f"无效的持仓ID: {position_id}")
            return None

        # Get original position information
        old_position = await self.db[self.positions_collection].find_one(
            {"_id": obj_id, "user_id": user_id}
        )
        if not old_position:
            return None

        # Calculate changes in funds
        old_cost = old_position["quantity"] * old_position["cost_price"]
        new_quantity = data.quantity if data.quantity is not None else old_position["quantity"]
        new_cost_price = data.cost_price if data.cost_price is not None else old_position["cost_price"]
        new_cost = new_quantity * new_cost_price
        cost_diff = new_cost - old_cost  # A positive number indicates the need for additional funds, a negative number indicates the release of funds.

        # Update funding account
        if cost_diff != 0:
            currency = old_position["currency"]
            account = await self.get_or_create_account(user_id)
            current_cash = account.get("cash", {}).get(currency, 0.0)

            if cost_diff > 0 and current_cash < cost_diff:
                raise ValueError(f"Insufficient funds available. Currently available: {current_cash:.2f} {currency}, Need to add: {cost_diff:.2f} {currency}")

            new_cash = current_cash - cost_diff
            await self.db[self.accounts_collection].update_one(
                {"user_id": user_id},
                {"$set": {f"cash.{currency}": new_cash, "updated_at": now_tz()}}
            )

        # Build update data
        update_data = {"updated_at": now_tz()}
        if data.name is not None:
            update_data["name"] = data.name
        if data.quantity is not None:
            update_data["quantity"] = data.quantity
        if data.cost_price is not None:
            update_data["cost_price"] = data.cost_price
        if data.buy_date is not None:
            update_data["buy_date"] = data.buy_date
        if data.notes is not None:
            update_data["notes"] = data.notes

        result = await self.db[self.positions_collection].find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_data},
            return_document=True
        )

        if result:
            # Record position changes
            currency = old_position["currency"]
            old_qty = old_position["quantity"]
            old_price = old_position["cost_price"]

            # Determine the type of change
            if new_quantity > old_qty:
                change_type = PositionChangeType.ADD
                desc = f"加仓 {new_quantity - old_qty} 股"
            elif new_quantity < old_qty:
                change_type = PositionChangeType.REDUCE
                desc = f"减仓 {old_qty - new_quantity} 股"
            else:
                change_type = PositionChangeType.ADJUST
                desc = "调整持仓信息"

            await self.record_position_change(
                user_id=user_id,
                change_type=change_type,
                code=old_position["code"],
                name=result.get("name", old_position["code"]),
                market=old_position["market"],
                currency=currency,
                position_id=position_id,
                quantity_before=old_qty,
                cost_price_before=old_price,
                quantity_after=new_quantity,
                cost_price_after=new_cost_price,
                description=desc
            )

            logger.info(f"✅ 更新持仓成功: {position_id}，资金变化: {-cost_diff:.2f} {currency}")
            return await self._enrich_position(result, "real")
        return None

    async def delete_position(self, user_id: str, position_id: str) -> bool:
        """删除持仓"""
        try:
            obj_id = ObjectId(position_id)
        except Exception:
            logger.error(f"无效的持仓ID: {position_id}")
            return False

        # Get position information to release funds
        position = await self.db[self.positions_collection].find_one(
            {"_id": obj_id, "user_id": user_id}
        )
        if not position:
            return False

        # Release funds (return holding costs to available funds)
        position_cost = position["quantity"] * position["cost_price"]
        currency = position["currency"]

        account = await self.get_or_create_account(user_id)
        current_cash = account.get("cash", {}).get(currency, 0.0)
        new_cash = current_cash + position_cost

        await self.db[self.accounts_collection].update_one(
            {"user_id": user_id},
            {"$set": {f"cash.{currency}": new_cash, "updated_at": now_tz()}}
        )

        # Record position changes (recorded before deletion)
        await self.record_position_change(
            user_id=user_id,
            change_type=PositionChangeType.SELL,
            code=position["code"],
            name=position.get("name", position["code"]),
            market=position["market"],
            currency=currency,
            position_id=position_id,
            quantity_before=position["quantity"],
            cost_price_before=position["cost_price"],
            quantity_after=0,
            cost_price_after=0.0,
            description="清仓卖出"
        )

        # Delete position
        result = await self.db[self.positions_collection].delete_one(
            {"_id": obj_id, "user_id": user_id}
        )

        if result.deleted_count > 0:
            logger.info(f"✅ 删除持仓成功: {position_id}，释放资金: {position_cost:.2f} {currency}")
            return True
        return False

    async def import_positions(
        self,
        user_id: str,
        positions: List[PositionCreate],
        validate_input: bool = True,
        replace_existing: bool = False,
    ) -> Dict[str, Any]:
        """批量导入持仓"""
        sync_result: Optional[Dict[str, Any]] = None
        if replace_existing:
            sync_result = await self._clear_existing_real_positions_for_sync(user_id)

        success_count = 0
        failed_count = 0
        errors = []

        for pos in positions:
            try:
                await self.add_position(
                    user_id,
                    pos,
                    source=PositionSource.IMPORT,
                    validate_input=validate_input,
                )
                success_count += 1
            except Exception as e:
                failed_count += 1
                errors.append({"code": pos.code, "error": str(e)})

        logger.info(f"✅ 批量导入完成: 成功 {success_count}, 失败 {failed_count}")
        result = {
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": errors
        }
        if sync_result:
            result.update(sync_result)
        result["replace_existing"] = replace_existing
        return result

    async def import_positions_from_qmt(
        self,
        user_id: str,
        account_id: str,
        account_type: str = "STOCK",
    ) -> Dict[str, Any]:
        """Read-only query of positions from QMT and import into current user s position list."""
        from app.services.data_sources.qmt_adapter import QMTAdapter

        adapter = QMTAdapter()
        snapshot = await asyncio.to_thread(adapter.query_account_snapshot, account_id, account_type)
        if snapshot is None:
            raise ValueError("QMT No account information found, please confirm that QMT is logged in and the account is available")

        positions_df = snapshot.get("positions_df")
        asset_summary = snapshot.get("asset") or {}
        positions = self._build_qmt_import_positions(positions_df)

        if (positions_df is None or len(positions_df) == 0) and asset_summary.get("cash") is None:
            raise ValueError("QMT No positions or account assets that can be synchronized were found.")

        result = await self.import_positions(
            user_id,
            positions,
            validate_input=False,
            replace_existing=True,
        )
        result.update(await self._sync_qmt_cash_to_account(user_id, asset_summary))
        result.update({
            "account_id": account_id,
            "account_type": account_type,
            "queried_count": 0 if positions_df is None else len(positions_df),
            "imported_count": len(positions),
            "qmt_market_value": asset_summary.get("market_value"),
            "qmt_total_asset": asset_summary.get("total_asset"),
            "sync_note": "Local real market positions have been covered, and CNY available cash has been synchronized to QMT account cash. The initial funds and cumulative deposits and withdrawals records remain unchanged.",
        })
        return result

    # ==================== Position statistics ====================

    async def get_portfolio_statistics(self, user_id: str) -> PortfolioStatsResponse:
        """获取持仓统计"""
        positions = await self.get_positions(user_id, source="all", include_market_data=True)

        total_value = 0.0
        total_cost = 0.0
        industry_map: Dict[str, Dict] = {}
        market_map: Dict[str, float] = {}

        for pos in positions:
            cost = pos.cost_price * pos.quantity
            total_cost += cost

            if pos.market_value:
                total_value += pos.market_value
            else:
                total_value += cost  # Use cost when market cap cannot be obtained

            # 🔥 Fix: If industry is empty, try to get and update to database in real time
            industry = pos.industry
            logger.info(f"📊 [统计] 持仓 {pos.code} ({pos.name}) 当前行业: {industry}")
            
            if not industry or industry == "未知":
                logger.info(f"🔄 [统计] 持仓 {pos.code} 行业为空或'未知'，尝试实时获取...")
                # Try to get industry information from the database
                industry = await self._get_stock_industry(pos.code, pos.market)
                logger.info(f"📊 [统计] 持仓 {pos.code} 获取到的行业: {industry}")
                
                # If industry information is obtained, update it to the database
                if industry:
                    try:
                        update_result = await self.db[self.positions_collection].update_one(
                            {"_id": ObjectId(pos.id)},
                            {"$set": {"industry": industry, "updated_at": now_tz()}}
                        )
                        if update_result.modified_count > 0:
                            logger.info(f"✅ [统计] 已更新持仓 {pos.code} 的行业信息: {industry}")
                        else:
                            logger.warning(f"⚠️ [统计] 更新持仓 {pos.code} 行业信息失败: 未找到记录或未修改")
                    except Exception as e:
                        logger.error(f"❌ [统计] 更新持仓 {pos.code} 行业信息失败: {e}", exc_info=True)
                else:
                    # If it is not available, use"unknown"
                    logger.warning(f"⚠️ [统计] 持仓 {pos.code} 无法获取行业信息，使用'未知'")
                    industry = "未知"
            
            # Industry Statistics
            if industry not in industry_map:
                industry_map[industry] = {"value": 0.0, "count": 0}
            industry_map[industry]["value"] += pos.market_value or cost
            industry_map[industry]["count"] += 1

            # market statistics
            market = pos.market
            if market not in market_map:
                market_map[market] = 0.0
            market_map[market] += pos.market_value or cost

        # Calculate profit and loss
        unrealized_pnl = total_value - total_cost
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

        # Convert industry distribution
        industry_dist = []
        for industry, data in industry_map.items():
            pct = (data["value"] / total_value * 100) if total_value > 0 else 0.0
            industry_dist.append(IndustryDistribution(
                industry=industry,
                value=round(data["value"], 2),
                percentage=round(pct, 2),
                count=data["count"]
            ))
        industry_dist.sort(key=lambda x: x.value, reverse=True)

        return PortfolioStatsResponse(
            total_positions=len(positions),
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
            industry_distribution=industry_dist,
            market_distribution={k: round(v, 2) for k, v in market_map.items()}
        )

    # ==================== Position analysis ====================

    async def analyze_portfolio(
        self,
        user_id: str,
        include_paper: bool = True,
        research_depth: str = "标准"
    ) -> PortfolioAnalysisReport:
        """
        Perform position analysis

        Args:
            user_id: User ID
            include_paper: Whether to include simulated trading positions
            research_depth: Analysis depth
        """
        analysis_id = str(uuid.uuid4())
        analysis_date = datetime.now().strftime("%Y-%m-%d")

        # Create analysis report
        report = PortfolioAnalysisReport(
            analysis_id=analysis_id,
            user_id=user_id,
            analysis_date=analysis_date,
            status=PortfolioAnalysisStatus.PROCESSING
        )

        try:
            # 1. Get position data
            source = "all" if include_paper else "real"
            positions = await self.get_positions(user_id, source=source)

            if not positions:
                report.status = PortfolioAnalysisStatus.FAILED
                report.error_message = "没有持仓数据"
                await self._save_analysis_report(report)
                return report

            # 2. Get fund account information
            account_summary = await self.get_account_summary(user_id)

            # 3. Build a position snapshot (including capital account information)
            portfolio_snapshot = await self._build_portfolio_snapshot(positions, account_summary)
            report.portfolio_snapshot = portfolio_snapshot

            # 4. Calculate industry distribution
            report.industry_distribution = await self._calculate_industry_distribution(positions)

            # 5. Calculate concentration
            report.concentration_analysis = self._calculate_concentration(positions)

            # 6. Call AI analysis (incoming capital account information)
            start_time = datetime.now()
            ai_result = await self._call_ai_analysis(portfolio_snapshot, report.industry_distribution, user_id)
            execution_time = (datetime.now() - start_time).total_seconds()

            report.ai_analysis = ai_result
            report.health_score = self._calculate_health_score(report)
            report.risk_level = self._calculate_risk_level(report)
            report.execution_time = execution_time
            report.status = PortfolioAnalysisStatus.COMPLETED

            logger.info(f"✅ 持仓分析完成: {analysis_id}, 健康度: {report.health_score}")

        except Exception as e:
            logger.error(f"❌ 持仓分析失败: {e}")
            report.status = PortfolioAnalysisStatus.FAILED
            report.error_message = str(e)

        # save report
        await self._save_analysis_report(report)
        return report

    async def get_analysis_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """获取分析历史"""
        skip = (page - 1) * page_size

        cursor = self.db[self.analysis_collection].find(
            {"user_id": user_id}
        ).sort("created_at", -1).skip(skip).limit(page_size)

        items = await cursor.to_list(None)
        total = await self.db[self.analysis_collection].count_documents({"user_id": user_id})

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def get_analysis_detail(self, analysis_id: str) -> Optional[Dict]:
        """获取分析报告详情"""
        return await self.db[self.analysis_collection].find_one({"analysis_id": analysis_id})

    # ==================== Helper methods ====================

    async def _build_portfolio_snapshot(
        self,
        positions: List[PositionResponse],
        account_summary: AccountSummary = None
    ) -> PortfolioSnapshot:
        """Build a position snapshot (including capital account information)"""
        total_value = 0.0
        total_cost = 0.0
        snapshots = []

        # Obtain total assets for calculating proportion (CNY is used by default)
        total_assets = 0.0
        if account_summary:
            total_assets = account_summary.total_assets.get("CNY", 0.0)

        for pos in positions:
            cost = pos.cost_price * pos.quantity
            value = pos.market_value or cost
            total_cost += cost
            total_value += value

            # Calculate position holding days
            holding_days = None
            if pos.buy_date:
                holding_days = (datetime.now() - pos.buy_date).days

            # Calculate the capital occupation ratio (relative to total assets)
            cost_pct = None
            position_pct = None
            if total_assets > 0:
                cost_pct = round((cost / total_assets) * 100, 2)
                position_pct = round((value / total_assets) * 100, 2)

            snapshots.append(PositionSnapshot(
                code=pos.code,
                name=pos.name,
                market=pos.market,
                quantity=pos.quantity,
                cost_price=pos.cost_price,
                current_price=pos.current_price,
                market_value=pos.market_value,
                unrealized_pnl=pos.unrealized_pnl,
                unrealized_pnl_pct=pos.unrealized_pnl_pct,
                industry=pos.industry,
                holding_days=holding_days,
                cost_value=round(cost, 2),
                cost_pct=cost_pct,
                position_pct=position_pct
            ))

        unrealized_pnl = total_value - total_cost
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

        # Build a capital account snapshot
        account_snapshot = None
        if account_summary:
            cash_cny = account_summary.cash.get("CNY", 0.0)
            positions_value_cny = account_summary.positions_value.get("CNY", 0.0)
            total_assets_cny = account_summary.total_assets.get("CNY", 0.0)
            initial_capital_cny = account_summary.initial_capital.get("CNY", 0.0)
            net_capital_cny = account_summary.net_capital.get("CNY", 0.0)
            profit_cny = account_summary.profit.get("CNY", 0.0)
            profit_pct_cny = account_summary.profit_pct.get("CNY", 0.0)

            position_ratio = (positions_value_cny / total_assets_cny * 100) if total_assets_cny > 0 else 0.0
            cash_ratio = (cash_cny / total_assets_cny * 100) if total_assets_cny > 0 else 0.0

            account_snapshot = AccountSnapshot(
                total_assets=round(total_assets_cny, 2),
                cash=round(cash_cny, 2),
                positions_value=round(positions_value_cny, 2),
                position_ratio=round(position_ratio, 2),
                cash_ratio=round(cash_ratio, 2),
                initial_capital=round(initial_capital_cny, 2),
                net_capital=round(net_capital_cny, 2),
                total_profit=round(profit_cny, 2),
                total_profit_pct=round(profit_pct_cny, 2),
                currency="CNY"
            )

        return PortfolioSnapshot(
            total_positions=len(positions),
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
            positions=snapshots,
            account=account_snapshot
        )

    async def _calculate_industry_distribution(
        self,
        positions: List[PositionResponse]
    ) -> List[IndustryDistribution]:
        """计算行业分布"""
        industry_map: Dict[str, Dict] = {}
        total_value = 0.0

        for pos in positions:
            value = pos.market_value or (pos.cost_price * pos.quantity)
            total_value += value

            industry = pos.industry or "未知"
            if industry not in industry_map:
                industry_map[industry] = {"value": 0.0, "count": 0}
            industry_map[industry]["value"] += value
            industry_map[industry]["count"] += 1

        result = []
        for industry, data in industry_map.items():
            pct = (data["value"] / total_value * 100) if total_value > 0 else 0.0
            result.append(IndustryDistribution(
                industry=industry,
                value=round(data["value"], 2),
                percentage=round(pct, 2),
                count=data["count"]
            ))

        result.sort(key=lambda x: x.value, reverse=True)
        return result

    def _calculate_concentration(self, positions: List[PositionResponse]) -> ConcentrationAnalysis:
        """计算集中度分析"""
        if not positions:
            return ConcentrationAnalysis()

        # Calculate the market capitalization of each stock
        values = []
        industries = set()
        total_value = 0.0

        for pos in positions:
            value = pos.market_value or (pos.cost_price * pos.quantity)
            values.append(value)
            total_value += value
            if pos.industry:
                industries.add(pos.industry)

        if total_value == 0:
            return ConcentrationAnalysis(stock_count=len(positions))

        # Sort to get Top N
        values.sort(reverse=True)

        top1_pct = (values[0] / total_value * 100) if len(values) >= 1 else 0
        top3_pct = (sum(values[:3]) / total_value * 100) if len(values) >= 3 else (sum(values) / total_value * 100)
        top5_pct = (sum(values[:5]) / total_value * 100) if len(values) >= 5 else (sum(values) / total_value * 100)

        # Calculate HHI index
        hhi = sum((v / total_value * 100) ** 2 for v in values)

        return ConcentrationAnalysis(
            stock_count=len(positions),
            top1_pct=round(top1_pct, 2),
            top3_pct=round(top3_pct, 2),
            top5_pct=round(top5_pct, 2),
            hhi_index=round(hhi, 2),
            industry_count=len(industries)
        )

    async def _call_ai_analysis(
        self,
        snapshot: PortfolioSnapshot,
        industry_dist: List[IndustryDistribution],
        user_id: str = None
    ) -> AIAnalysisResult:
        """调用AI进行持仓分析"""
        try:
            # Query dividend data
            dividend_info = {}
            if user_id:
                dividend_info = await self._get_dividend_summary(user_id)

            # Build analysis prompt words
            prompt = self._build_analysis_prompt(snapshot, industry_dist, dividend_info)

            # Obtain in-depth analysis model from system configuration (consistent with individual stock analysis)
            from app.services.model_capability_service import get_model_capability_service
            from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
            from tradingagents.graph.trading_graph import create_llm_by_provider

            capability_service = get_model_capability_service()
            _, deep_model = capability_service._get_default_models()
            model_name = deep_model

            logger.info(f"🤖 [Overall position AI analysis] Get deep analysis model from system configuration: {model_name}")

            provider_info = get_provider_and_url_by_model_sync(model_name)
            backend_url = provider_info.get("backend_url")
            api_key = provider_info.get("api_key")

            logger.info(f"🏭 [Overall position AI analysis] model supplier: {provider_info.get('provider', 'unknown')}")
            logger.info(f"🔗 [Overall position AI analysis] API address: {backend_url or 'Not configured'}")
            logger.info(f"🔑 [Overall position AI analysis] API Key: {'configured' if api_key else 'Not configured'}")

            if not backend_url:
                raise ValueError(f"模型 {model_name} 的API地址未配置，请在设置页面配置")

            # Use unified LLM adapter
            provider_name = provider_info.get("provider", "dashscope")
            logger.info(f"🔧 [Position AI analysis] ready to create LLM: provider={provider_name}, model={model_name}, temperature=0.3")
            if api_key:
                logger.info(f"🔑 [Position AI analysis] API Key: {truncate_api_key(api_key)}")
            llm = create_llm_by_provider(
                provider=provider_name,
                model=model_name,
                backend_url=backend_url,
                temperature=0.3,
                max_tokens=4000,
                timeout=120,
                api_key=api_key
            )

            response = await llm.ainvoke(prompt)

            # Record token usage
            try:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=response,
                    session_id="portfolio",
                    analysis_type="portfolio"
                )
            except Exception as e:
                logger.warning(f"Record token usage failure: {e}")

            content = response.content if hasattr(response, 'content') else str(response)

            # Parse response
            return self._parse_ai_response(content)

        except Exception as e:
            logger.error(f"AI分析失败: {e}", exc_info=True)
            from app.utils.error_formatter import ErrorFormatter

            user_message = ErrorFormatter.format_user_message(str(e))
            return AIAnalysisResult(
                summary=f"AI Analysis is temporarily unavailable:{user_message}",
                suggestions=["Please check the big model account, API Key, balance or package configuration and try again"]
            )

    async def _get_real_market_rules(self, market: str) -> Optional[Dict[str, Any]]:
        """Obtain the market rule configuration of the real position (reusing the paper_market_rules collection)"""
        try:
            rules_doc = await self.db["paper_market_rules"].find_one({"market": market})
            if rules_doc:
                return rules_doc.get("rules", {})
        except Exception as e:
            logger.warning(f"获取市场规则失败: {e}")
        return None

    def _calculate_real_commission(
        self, market: str, side: str, amount: float, rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate the handling fees for real position transactions

        Args:
            market: Market (CN/HK/US)
            side: buy/sell
            amount: Transaction amount
            rules: Market rules configuration

        Returns:
            {
                "commission": float,        # total handling fee
                "broker_fee": float,        # Commission
                "stamp_duty": float,        # stamp duty
                "transfer_fee": float,      # Transfer fee
                "other_fee": float,         # Other fees (Hong Kong stocks/US stocks)
            }
        """
        result = {
            "commission": 0.0,
            "broker_fee": 0.0,
            "stamp_duty": 0.0,
            "transfer_fee": 0.0,
            "other_fee": 0.0,
        }
        if not rules or "commission" not in rules:
            return result

        config = rules["commission"]

        # Commission
        comm_rate = config.get("rate", 0.0)
        comm_min = config.get("min", 0.0)
        broker_fee = max(amount * comm_rate, comm_min) if comm_rate > 0 else 0.0
        result["broker_fee"] = round(broker_fee, 2)

        # Stamp duty (A-shares are only sold, Hong Kong stocks are collected for all transactions)
        stamp_duty = 0.0
        if "stamp_duty_rate" in config:
            if market == "CN" and side == "sell":
                stamp_duty = amount * config["stamp_duty_rate"]
            elif market == "HK":
                stamp_duty = amount * config["stamp_duty_rate"]
        result["stamp_duty"] = round(stamp_duty, 2)

        # Transfer fee (A shares)
        transfer_fee = 0.0
        if "transfer_fee_rate" in config and market == "CN":
            transfer_fee = amount * config["transfer_fee_rate"]
        result["transfer_fee"] = round(transfer_fee, 2)

        # Other expenses (Hong Kong stocks)
        other_fee = 0.0
        if market == "HK":
            if "transaction_levy_rate" in config:
                other_fee += amount * config["transaction_levy_rate"]
            if "trading_fee_rate" in config:
                other_fee += amount * config["trading_fee_rate"]
            if "settlement_fee_rate" in config:
                other_fee += amount * config["settlement_fee_rate"]

        # SEC Fees (US stocks, sell only)
        if market == "US" and side == "sell" and "sec_fee_rate" in config:
            other_fee += amount * config["sec_fee_rate"]
        result["other_fee"] = round(other_fee, 2)

        result["commission"] = round(
            broker_fee + stamp_duty + transfer_fee + other_fee, 2
        )
        return result

    async def _get_dividend_summary(self, user_id: str) -> Dict[str, Any]:
        """Query the user s dividend income summary

        Returns:
            {
                "total_dividend": float,      # Total cumulative dividends
                "dividend_count": int,         # Number of dividend stocks
                "by_stock": {                  # Summary by stock
                    "000001": {"name": "Ping An Bank", "amount": 120.0, "count": 2},
                    ...
                }
            }
        """
        result = {"total_dividend": 0.0, "dividend_count": 0, "by_stock": {}}
        try:
            # Query the dividend record in the capital account
            cursor = self.db[self.transactions_collection].find({
                "user_id": user_id,
                "type": "dividend"
            })
            total = 0.0
            by_stock = {}
            async for txn in cursor:
                amount = float(txn.get("amount", 0))
                code = txn.get("code", "")
                name = txn.get("name", "")
                if amount <= 0:
                    continue
                total += amount
                if code:
                    if code not in by_stock:
                        by_stock[code] = {"name": name, "amount": 0.0, "count": 0}
                    by_stock[code]["amount"] += amount
                    by_stock[code]["count"] += 1

            result["total_dividend"] = total
            result["dividend_count"] = len(by_stock)
            result["by_stock"] = by_stock

            if total > 0:
                logger.info(f"💵 查询到用户 {user_id} 累计分红 ¥{total:,.2f}，{len(by_stock)} 只股票")
        except Exception as e:
            logger.warning(f"查询分红数据失败: {e}")
        return result

    def _build_analysis_prompt(
        self,
        snapshot: PortfolioSnapshot,
        industry_dist: List[IndustryDistribution],
        dividend_info: Dict[str, Any] = None
    ) -> str:
        """Construct analysis prompt words (including capital account, individual stock income and dividend information)"""

        # Fund account information
        account_section = ""
        if snapshot.account:
            acc = snapshot.account
            account_section = f"""## 💰 资金账户概况
| 项目 | 金额 | 说明 |
|------|------|------|
| 总资产 | ¥{acc.total_assets:,.2f} | 现金+持仓市值 |
| 可用现金 | ¥{acc.cash:,.2f} | 占比 {acc.cash_ratio:.1f}% |
| 持仓市值 | ¥{acc.positions_value:,.2f} | 占比 {acc.position_ratio:.1f}% |
| 净投入资金 | ¥{acc.net_capital:,.2f} | 初始资金+入金-出金 |
| 总盈亏 | ¥{acc.total_profit:,.2f} | 收益率 {acc.total_profit_pct:.2f}% |

### 仓位水平评估
- 当前仓位: **{acc.position_ratio:.1f}%**
- {"⚠️ 重仓状态（>80%），风险敞口较大" if acc.position_ratio > 80 else "⚠️ 偏重仓位（60-80%），建议保留部分现金" if acc.position_ratio > 60 else "✅ 仓位适中（40-60%），攻守兼备" if acc.position_ratio > 40 else "💡 轻仓状态（<40%），可择机加仓"}

"""

        # Position details (enhanced version: includes fund occupation and income details)
        position_table = "| Stock code | Stock name | Industry | Position holding days | cost amount | Market value | Profit and loss amount | Profit and loss% | Fund proportion |\n"
        position_table += "|---------|---------|-----|--------|---------|-----|---------|------|--------|\n"

        # Sort by profit and loss amount for easy analysis
        sorted_positions = sorted(
            snapshot.positions,
            key=lambda x: x.unrealized_pnl or 0,
            reverse=True
        )

        for pos in sorted_positions:
            pnl_emoji = "🟢" if (pos.unrealized_pnl or 0) >= 0 else "🔴"
            holding_days_str = f"{pos.holding_days}天" if pos.holding_days else "-"
            cost_value = pos.cost_value or (pos.cost_price * pos.quantity)
            position_table += f"| {pos.code} | {pos.name or '-'} | {pos.industry or '-'} | "
            position_table += f"{holding_days_str} | ¥{cost_value:,.0f} | ¥{pos.market_value or cost_value:,.0f} | "
            position_table += f"{pnl_emoji} ¥{pos.unrealized_pnl or 0:,.0f} | {pos.unrealized_pnl_pct or 0:.2f}% | "
            position_table += f"{pos.position_pct or '-'}% |\n"

        # Individual stock income analysis
        profitable_positions = [p for p in snapshot.positions if (p.unrealized_pnl or 0) > 0]
        losing_positions = [p for p in snapshot.positions if (p.unrealized_pnl or 0) < 0]
        total_profit = sum(p.unrealized_pnl or 0 for p in profitable_positions)
        total_loss = sum(p.unrealized_pnl or 0 for p in losing_positions)

        performance_section = f"""## 📊 个股收益分析
- 盈利股票: {len(profitable_positions)}只，合计盈利 ¥{total_profit:,.2f}
- 亏损股票: {len(losing_positions)}只，合计亏损 ¥{total_loss:,.2f}
- 盈亏比: {abs(total_profit/total_loss) if total_loss != 0 else '∞'}:1

### 盈利最多的股票
"""
        for pos in sorted_positions[:3]:
            if (pos.unrealized_pnl or 0) > 0:
                performance_section += f"- {pos.name}({pos.code}): +¥{pos.unrealized_pnl:,.0f} (+{pos.unrealized_pnl_pct:.2f}%)\n"

        performance_section += "\n### 亏损最多的股票\n"
        for pos in reversed(sorted_positions[-3:]):
            if (pos.unrealized_pnl or 0) < 0:
                performance_section += f"- {pos.name}({pos.code}): ¥{pos.unrealized_pnl:,.0f} ({pos.unrealized_pnl_pct:.2f}%)\n"

        # Fund occupation analysis
        capital_section = ""
        if snapshot.account and snapshot.account.total_assets > 0:
            high_concentration = [p for p in snapshot.positions if (p.position_pct or 0) > 20]
            if high_concentration:
                capital_section = "\n### ⚠️ High concentration of positions (single stock>20%) \n"
                for pos in high_concentration:
                    capital_section += f"- {pos.name}({pos.code}): 占比 {pos.position_pct:.1f}%，资金占用 ¥{pos.cost_value:,.0f}\n"

        # Industry distribution
        industry_text = "\n".join([
            f"- {d.industry}: {d.percentage:.1f}% ({d.count}只)"
            for d in industry_dist[:5]
        ])

        # Dividend income information
        dividend_section = ""
        if dividend_info and dividend_info.get("total_dividend", 0) > 0:
            dividend_section = f"""
## 💵 分红收益
- 累计分红总额: ¥{dividend_info['total_dividend']:,.2f}
- 分红股票数: {dividend_info['dividend_count']} 只
"""
            stock_dividends = dividend_info.get("by_stock", {})
            if stock_dividends:
                dividend_section += "\n| Stock code | Stock name | Cumulative dividends | Number of dividends |\n"
                dividend_section += "|---------|---------|---------|--------|\n"
                for code, info in sorted(stock_dividends.items(), key=lambda x: x[1]["amount"], reverse=True):
                    dividend_section += f"| {code} | {info.get('name', '-')} | ¥{info['amount']:,.2f} | {info.get('count', 0)}次 |\n"
            dividend_section += "\n**Note**: Dividend income is not included in floating profits and losses, and the actual total income = floating profit and loss + Cumulative dividends.\n"

        prompt = f"""# 持仓组合分析任务

{account_section}## 📈 持仓概况
- 持仓总市值: ¥{snapshot.total_value:,.2f}
- 持仓成本: ¥{snapshot.total_cost:,.2f}
- 浮动盈亏: ¥{snapshot.unrealized_pnl:,.2f} ({snapshot.unrealized_pnl_pct:.2f}%)
- 持仓股票数: {snapshot.total_positions} 只

## 📋 持仓明细
{position_table}

{performance_section}
{capital_section}

## 🏭 行业分布
{industry_text}
{dividend_section}
## 分析要求
请基于以上数据，从以下维度进行专业分析（用中文回答）：

1. **持仓健康度评估** (给出0-100分，并说明主要扣分项)
2. **风险评估** (低/中/高，结合仓位水平和集中度分析)
3. **资金配置评估** (评估现金/持仓比例是否合理，资金利用效率)
4. **个股表现分析** (哪些股票表现好/差，是否需要止盈/止损；如有分红数据，需结合分红计算真实总收益)
5. **分红收益分析** (如有分红数据，评估分红对组合收益的贡献，哪些股票分红稳定)
6. **组合优势** (列出2-3点)
7. **组合劣势** (列出2-3点)
8. **调仓建议** (列出2-3条具体建议，包括：
   - 是否需要调整仓位水平
   - 是否需要止盈/止损某些股票
   - 是否需要调整行业配置)
9. **综合评价** (150字以内的总结，含分红的总收益)

请直接给出分析结果，不需要JSON格式。"""

        return prompt

    def _parse_ai_response(self, content: str) -> AIAnalysisResult:
        """解析AI响应"""
        # Simple analysis to extract key information
        lines = content.split('\n')

        summary = ""
        strengths = []
        weaknesses = []
        suggestions = []

        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "综合评价" in line or "总结" in line:
                current_section = "summary"
            elif "优势" in line:
                current_section = "strengths"
            elif "劣势" in line or "不足" in line:
                current_section = "weaknesses"
            elif "建议" in line:
                current_section = "suggestions"
            elif line.startswith("-") or line.startswith("•") or line.startswith("*"):
                item = line.lstrip("-•* ").strip()
                if current_section == "strengths" and item:
                    strengths.append(item)
                elif current_section == "weaknesses" and item:
                    weaknesses.append(item)
                elif current_section == "suggestions" and item:
                    suggestions.append(item)
            elif current_section == "summary":
                summary += line + " "

        return AIAnalysisResult(
            summary=summary.strip() or content[:200],
            strengths=strengths[:3],
            weaknesses=weaknesses[:3],
            suggestions=suggestions[:5],
            detailed_report=content
        )

    def _calculate_health_score(self, report: PortfolioAnalysisReport) -> float:
        """Calculate health score

        Improve logic:
        1. No points will be deducted due to concentration when holding a single stock position (it is normal to start with a single stock)
        2. Rating is mainly based on profit and loss situation
        3. Concentration and industry dispersion are considered only when there are multiple stocks
        """
        score = 70.0  # The basic score is increased to 70

        concentration = report.concentration_analysis
        stock_count = concentration.stock_count or 1
        pnl_pct = report.portfolio_snapshot.total_unrealized_pnl_pct or 0

        # === Scoring logic for single stock positions ===
        if stock_count == 1:
            # Concentration points are not deducted for single stocks, and the main focus is on profit and loss.
            if pnl_pct > 20:
                score += 20
            elif pnl_pct > 10:
                score += 15
            elif pnl_pct > 5:
                score += 10
            elif pnl_pct > 0:
                score += 5
            elif pnl_pct > -5:
                score += 0  # Small losses, no points will be deducted
            elif pnl_pct > -10:
                score -= 5
            elif pnl_pct > -20:
                score -= 10
            else:
                score -= 20  # Loss exceeds 20%

            return max(0, min(100, score))

        # === Scoring logic for multi-stock positions ===
        # concentration score (Up to 15 points deducted)
        if concentration.top1_pct > 60:
            score -= 12
        elif concentration.top1_pct > 40:
            score -= 6

        if concentration.hhi_index > 4000:
            score -= 8
        elif concentration.hhi_index > 2500:
            score -= 4

        # Bonus points for industry dispersion (Up to 15 points added)
        if concentration.industry_count >= 5:
            score += 12
        elif concentration.industry_count >= 3:
            score += 8
        elif concentration.industry_count >= 2:
            score += 4

        # Bonus points for profitability (Up to 15 points added/deducted)
        if pnl_pct > 20:
            score += 12
        elif pnl_pct > 10:
            score += 8
        elif pnl_pct > 0:
            score += 4
        elif pnl_pct < -20:
            score -= 12
        elif pnl_pct < -10:
            score -= 6

        return max(0, min(100, score))

    def _calculate_risk_level(self, report: PortfolioAnalysisReport) -> str:
        """Calculate risk level

        Improve logic:
        1. When holding a single stock position, high risk should not be judged simply based on concentration.
        2. Combined with absolute risk indicators such as position market value and loss ratio
        3. Small funds and light positions should be judged as low risk
        """
        concentration = report.concentration_analysis
        snapshot = report.portfolio_snapshot

        # Get basic indicators
        stock_count = concentration.stock_count or 1
        total_value = snapshot.total_market_value or 0
        total_pnl_pct = snapshot.total_unrealized_pnl_pct or 0

        # === Special treatment for single stock positions ===
        if stock_count == 1:
            # When holding a single stock position, the main focus is the loss magnitude and absolute amount.
            # Starting a single stock with small capital is a normal investment behavior and should not be considered high risk

            # Losses exceeding 20% are considered high risk
            if total_pnl_pct < -20:
                return "高"
            # Loss of more than 10% is medium risk
            elif total_pnl_pct < -10:
                return "中"
            # Profit or small loss is low risk
            else:
                return "低"

        # === Concentration risk assessment of multiple stock positions ===
        # High-risk conditions: excessive concentration and large losses
        if concentration.top1_pct > 50 and total_pnl_pct < -10:
            return "高"

        if concentration.hhi_index > 3000 and total_pnl_pct < -5:
            return "高"

        # Low risk conditions: good diversification
        if concentration.top1_pct < 30 and concentration.industry_count >= 3:
            return "低"

        if concentration.top1_pct < 20 and concentration.industry_count >= 5:
            return "低"

        return "中"

    async def _save_analysis_report(self, report: PortfolioAnalysisReport):
        """保存分析报告"""
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        await self.db[self.analysis_collection].insert_one(report_dict)
        logger.info(f"✅ 保存分析报告: {report.analysis_id}")

    # ==================== data acquisition tool ====================

    async def _get_stock_price(self, code: str, market: str) -> Optional[float]:
        """获取股票最新价格"""
        code6 = str(code).strip().zfill(6)
        if market in {"CN", "ETF"}:
            # A Shares are obtained from the database:1) market_quotes 2) stock_basic_info 3) stock_daily_quotes historical data
            q = await self.db["market_quotes"].find_one(
                {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
                {"_id": 0, "close": 1}
            )
            if q and q.get("close"):
                try:
                    return float(q["close"])
                except (ValueError, TypeError):
                    pass

            # Fallback to basic_info
            basic = await self.db["stock_basic_info"].find_one(
                {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
                {"_id": 0, "current_price": 1}
            )
            if basic and basic.get("current_price"):
                try:
                    return float(basic["current_price"])
                except (ValueError, TypeError):
                    pass

            # Return to stock_daily_quotes historical data (get the latest closing price)
            daily = await self.db["stock_daily_quotes"].find_one(
                {"$or": [{"symbol": code}, {"symbol": code6}, {"code": code}, {"code": code6}]},
                sort=[("trade_date", -1)],
                projection={"_id": 0, "close": 1}
            )
            if daily and daily.get("close"):
                try:
                    return float(daily["close"])
                except (ValueError, TypeError):
                    pass

            # Fall back to etf_daily_quotes (ETF quotes)
            etf_daily = await self.db["etf_daily_quotes"].find_one(
                {"code": code6},
                sort=[("trade_date", -1)],
                projection={"_id": 0, "close": 1}
            )
            if etf_daily and etf_daily.get("close"):
                try:
                    return float(etf_daily["close"])
                except (ValueError, TypeError):
                    pass
        else:
            # Hong Kong stocks/US stocks
            try:
                from app.services.foreign_stock_service import ForeignStockService
                service = ForeignStockService(db=self.db)
                quote = await service.get_quote(market, code)
                if quote:
                    for field in ['regularMarketPrice', 'price', 'last']:
                        if quote.get(field):
                            return float(quote[field])
            except Exception as e:
                logger.warning(f"获取{market}股票价格失败: {code}, {e}")

        return None

    async def _validate_cost_price_against_historical(
        self, code: str, market: str, buy_date, cost_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Verify whether the cost price is within the range of the highest and lowest price of the historical data on the purchase day.

        Verification strategy:
        1. Priority is given to using the pre-reright data in the database for verification (in most cases the cost price is the pre-reright price)
        2. If the previous restoration verification fails, call the API in real time to obtain the non-restoration data for full verification.
            (The actual transaction price input by the user is not re-righted and may be inconsistent with the previous re-righted K-line)
        3. When the non-restoration verification is passed, the restoration factor is calculated and used to convert the user price to the pre-restoration save.

        Args:
            code: Stock code
            market: market type
            buy_date: Purchase date
            cost_price: Cost price entered by user

        Returns:
            None — The cost price is consistent with the previous re-righting data, no conversion is required
            Dict — The cost price is the non-rights price and needs to be converted:
                {"adjust_type": "none", "qfq_price": float, "adj_factor": float}

        Raises:
            ValueError — The cost price is obviously wrong and the addition is refused.
        """
        if not buy_date:
            return None
        # Format purchase date: support datetime, date, ISO string
        # ⚠️ Time zone correction: frontend passed toISOString() Send a UTC string (such as "2026-05-11T16:00:00.000Z") , 
        # Pydantic Resolves as aware datetime. Direct strftime will use the UTC field value, causing users in the East Eighth District to
        # The selected May 12th is formatted as "2026-05-11". Must be converted to local time zone before formatting.
        if hasattr(buy_date, "strftime"):
            if getattr(buy_date, "tzinfo", None) is not None:
                # aware datetime: Go to local time zone (server TZ, usually Asia/Shanghai)
                buy_date = buy_date.astimezone()
            buy_date_str = buy_date.strftime("%Y-%m-%d")
            buy_date_compact = buy_date.strftime("%Y%m%d")
        elif isinstance(buy_date, str):
            buy_date_str = buy_date[:10] if len(buy_date) >= 10 else buy_date
            buy_date_compact = buy_date_str.replace("-", "") if "-" in buy_date_str else buy_date_str
        else:
            return None  # If it cannot be parsed, the verification will be skipped.
        code6 = str(code).strip().zfill(6)
        symbol_conds = [{"symbol": code}, {"symbol": code6}, {"code": code}, {"code": code6}]
        date_conds = [{"trade_date": buy_date_str}, {"trade_date": buy_date_compact}]
        normalized_market = "CN" if market == "ETF" else market

        # ---- The first level: Use the pre-replacement data verification in the database ----
        collection_map = {"CN": "stock_daily_quotes", "HK": "stock_daily_quotes_hk", "US": "stock_daily_quotes_us"}
        coll_name = collection_map.get(normalized_market, "stock_daily_quotes")
        coll = self.db[coll_name]
        doc = None
        for date_cond in date_conds:
            doc = await coll.find_one(
                {"$or": symbol_conds, **date_cond},
                {"_id": 0, "high": 1, "low": 1, "open": 1, "close": 1}
            )
            if doc:
                break
        # Fall back to etf_daily_quotes (ETF quotes)
        if not doc and normalized_market == "CN":
            for date_cond in date_conds:
                doc = await self.db["etf_daily_quotes"].find_one(
                    {"code": code6, **date_cond},
                    {"_id": 0, "high": 1, "low": 1, "open": 1, "close": 1}
                )
                if doc:
                    break

        if not doc:
            # There is no historical data in the database. Trying the API does not allow you to know the details.
            return await self._validate_with_unadjusted_api(
                code6, normalized_market, buy_date_str, cost_price
            )

        # Restoration before withdrawal high/low
        high_val = doc.get("high")
        low_val = doc.get("low")
        if high_val is None or low_val is None:
            open_val = doc.get("open")
            close_val = doc.get("close")
            if open_val is not None and close_val is not None:
                high_val = max(open_val, close_val)
                low_val = min(open_val, close_val)
            else:
                return None  # If it cannot be verified, it will be released.
        try:
            high_f = float(high_val)
            low_f = float(low_val)
        except (ValueError, TypeError):
            return None

        # Pre-right verification passed — The price entered by the user is consistent with the previous weighting data
        # ⚠️ Tolerance strategy: copied by the user from the brokerage app"cost price"Usually includes transaction costs such as commission/transfer fee,
        # It is not a pure transaction price. The upper and lower limits are relaxed by 2% tolerance to cover the impact of handling fees and slippage.
        #   Buying cost price = Transaction price + Commission + Transfer fee (approx. 0.05%~0.5%) 
        #   2% The tolerance is much larger than the actual handling fee ratio, which can tolerate errors without letting go of obvious errors.
        tolerance = 0.02
        high_with_tol = high_f * (1 + tolerance)
        low_with_tol = low_f * (1 - tolerance)
        if low_with_tol <= cost_price <= high_with_tol:
            logger.info(
                f"✅ 成本价 {cost_price:.2f} 通过前复权校验（{buy_date_str}，"
                f"original range {low_f:.2f}~{high_f:.2f}, With 2% tolerance {low_with_tol:.2f}~{high_with_tol:.2f}) "
            )
            return None

        # ---- Second level: The pre-right restoration verification failed, and the non-right restoration API was tried to find out. ----
        logger.info(
            f"⚠️ 成本价 {cost_price:.2f} 未通过前复权校验（{buy_date_str}，范围 {low_f:.2f}~{high_f:.2f}），"
            f"Try to verify the data without regaining rights..."
        )
        return await self._validate_with_unadjusted_api(
            code6, normalized_market, buy_date_str, cost_price
        )

    async def _validate_with_unadjusted_api(
        self, code6: str, market: str, buy_date_str: str, cost_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Obtain the non-reweighting data through the API for full verification, and calculate the re-weighting factor for price conversion.

        Scenario: The user inputs the non-restoration price (actual transaction price), while the data stored in the data inventory is the pre-restoration data.
        For example: the transaction price without reinstatement is 14.11, and the highest price before reinstatement is 13.72 (the difference is caused by dividends/bonus shares).

        Returns:
            None — The non-rights verification also fails and is rejected (ValueError is thrown by the caller)
            Dict — If the non-rights verification passes, the conversion information will be returned:
                {"adjust_type": "none", "qfq_price": float, "adj_factor": float}
        """
        if market != "CN":
            # Currently, only A-share non-resumption verification is supported.
            raise ValueError(
                f"成本价 {cost_price:.2f} 无法通过校验，非 A 股市场暂不支持不复权兜底校验。"
            )

        try:
            from app.services.data_sources.manager import DataSourceManager
            ds_manager = DataSourceManager()
        except Exception as e:
            logger.warning(f"无法初始化数据源管理器: {e}")
            raise ValueError(
                f"成本价 {cost_price:.2f} 无法通过校验，数据源服务不可用。"
            )

        # Obtain daily data without regaining rights
        unadj_ohlc, unadj_source = ds_manager.get_daily_ohlc_with_fallback(
            code=code6, trade_date=buy_date_str, adj=None
        )
        if not unadj_ohlc:
            raise ValueError(
                f"成本价 {cost_price:.2f} 无法校验：数据库为前复权数据且 API 无法获取不复权数据。"
                f"Please check whether the purchase date is a trading day, or leave the purchase date blank for now."
            )

        unadj_high = unadj_ohlc.get("high")
        unadj_low = unadj_ohlc.get("low")
        if unadj_high is None or unadj_low is None:
            raise ValueError(
                f"成本价 {cost_price:.2f} 无法校验：API 返回的不复权数据缺少最高/最低价。"
            )

        try:
            unadj_high_f = float(unadj_high)
            unadj_low_f = float(unadj_low)
        except (ValueError, TypeError):
            raise ValueError(
                f"成本价 {cost_price:.2f} 无法校验：API 返回的不复权数据格式异常。"
            )

        # Non-rights verification
        # ⚠️ Same as the previous weight verification, the upper and lower limits are relaxed according to a 2% tolerance, covering the situation where the cost price of the brokerage app includes handling fees.
        tolerance = 0.02
        unadj_high_with_tol = unadj_high_f * (1 + tolerance)
        unadj_low_with_tol = unadj_low_f * (1 - tolerance)
        if cost_price < unadj_low_with_tol or cost_price > unadj_high_with_tol:
            raise ValueError(
                f"成本价 {cost_price:.2f} 超出 {buy_date_str} 的波动范围"
                f" (Non-resumption of rights is the lowest {unadj_low_f:.2f}~highest {unadj_high_f:.2f}, "
                f"Includes 2% handling fee tolerance {unadj_low_with_tol:.2f}~{unadj_high_with_tol:.2f}) . "
                f"The cost price displayed on the brokerage app usually includes commission/transfer fee (approximately 0.05%~0.5%) , "
                f"It is recommended to use pure transaction price entry instead."
            )

        # ---- If the non-reweighting verification passes, calculate the reweighting factor. ----
        # Obtain the data of the previous restoration of rights on the same day and calculate the conversion ratio: former restoration of rights / no restoration of rights
        qfq_ohlc, qfq_source = ds_manager.get_daily_ohlc_with_fallback(
            code=code6, trade_date=buy_date_str, adj="qfq"
        )
        if not qfq_ohlc or qfq_ohlc.get("close") is None or unadj_ohlc.get("close") is None:
            # Unable to obtain pre-restoration data, retain non-restoration price and label type
            logger.warning(
                f"无法获取前复权数据进行转换，成本价 {cost_price:.2f} 将以不复权价格保存"
            )
            return {
                "adjust_type": "none",
                "qfq_price": None,  # Unable to convert
                "adj_factor": None,
            }

        # Reweighting factor = Closing price before restoration of rights / Closing price without restoration of rights
        qfq_close = float(qfq_ohlc["close"])
        unadj_close = float(unadj_ohlc["close"])

        if unadj_close <= 0:
            logger.warning(f"不复权收盘价异常（{unadj_close}），无法计算复权因子")
            return {
                "adjust_type": "none",
                "qfq_price": None,
                "adj_factor": None,
            }

        adj_factor = qfq_close / unadj_close
        qfq_price = cost_price * adj_factor

        logger.info(
            f"✅ 成本价 {cost_price:.2f} 通过不复权校验（{buy_date_str}，范围 {unadj_low_f:.2f}~{unadj_high_f:.2f}），"
            f"Reweighting factor={adj_factor:.6f}, Price before conversion to restoration price={qfq_price:.2f}"
        )

        return {
            "adjust_type": "none",  # The original input is unrecoverable
            "qfq_price": round(qfq_price, 4),
            "adj_factor": round(adj_factor, 6),
        }

    async def _get_stock_name(self, code: str, market: str) -> Optional[str]:
        """Get the stock name (with ETF fallback)"""
        if market in {"CN", "ETF"}:
            basic = await self.db["stock_basic_info"].find_one(
                {"$or": [{"code": code}, {"symbol": code}]},
                {"_id": 0, "name": 1}
            )
            if basic and basic.get("name"):
                return basic["name"]
            # Fallback to etf_basic_info
            etf = await self.db["etf_basic_info"].find_one(
                {"code": code}, {"_id": 0, "name": 1}
            )
            if etf and etf.get("name"):
                return etf["name"]
        return None

    async def _get_stock_industry(self, code: str, market: str) -> Optional[str]:
        """Get the industry to which the stock belongs
        
        Get it from the official website first (to avoid AKShare polling and banning accounts), and then query according to the priority of the database data source
        """
        try:
            if market == "CN":
                logger.info(f"🔍 [获取行业] 查询股票代码: {code}, 市场: {market}")

                # 🔥 Prioritize obtaining industry data from the official website (to avoid AKShare polling and banning accounts)
                from app.services.official_industry_service import get_industry
                official_industry = await get_industry(code)
                if official_industry:
                    logger.info(f"✅ [Get industry] Get it from the official website: {code} -> {official_industry}")
                    return official_industry
                
                # 🔥 Get the list of enabled data sources (sorted by priority from high to low)
                from app.core.data_source_priority import get_enabled_data_sources_async
                enabled_sources = await get_enabled_data_sources_async(market_category="a_shares")
                logger.info(f"📊 [Get industry] Data source priority: {enabled_sources}")
                
                # Try multiple query methods
                query_conditions = [
                    {"code": code},
                    {"symbol": code},
                    {"code": code.strip().zfill(6)},  # pad leading zeros
                    {"symbol": code.strip().zfill(6)}
                ]
                
                # 🔥 Query by data source priority order
                for source in enabled_sources:
                    logger.info(f"🔍 [Get industry] try data source: {source}")
                    
                    for condition in query_conditions:
                        # 🔥 Add data source filters
                        condition_with_source = {**condition, "source": source}
                        basic = await self.db["stock_basic_info"].find_one(
                            condition_with_source,
                            {"_id": 0, "industry": 1, "code": 1, "symbol": 1, "name": 1, "source": 1}
                        )
                        
                        if basic:
                            industry = basic.get("industry")
                            code_found = basic.get("code") or basic.get("symbol")
                            name_found = basic.get("name")
                            source_found = basic.get("source")
                            logger.info(f"✅ [获取行业] 使用数据源 {source_found} 和查询条件 {condition} 找到记录")
                            logger.info(f"✅ [获取行业] 股票 {code} 查询结果 - 代码: {code_found}, 名称: {name_found}, 行业: {industry}, 数据源: {source_found}")
                            
                            if industry:
                                logger.info(f"✅ [获取行业] 成功获取行业信息: {industry} (数据源: {source_found})")
                                return industry
                            else:
                                logger.warning(f"⚠️ [获取行业] 股票 {code} 在数据源 {source_found} 中找到记录，但 industry 字段为空，继续尝试下一个数据源")
                                break  # Break out of the query condition loop and try the next data source
                
                # 🔥 If no industry information is found from all data sources, log a warning
                logger.warning(f"⚠️ [获取行业] 股票 {code} 在所有数据源中均未找到行业信息")
                # Print some debugging information
                count = await self.db["stock_basic_info"].count_documents({})
                logger.info(f"📊 [Get industry] stock_basic_info The total number of records in the collection: {count}")
                # Find similar code (without limiting the data source)
                similar = await self.db["stock_basic_info"].find_one(
                    {"code": {"$regex": code[-4:]}},  # Find the same last 4 digits
                    {"_id": 0, "code": 1, "symbol": 1, "name": 1, "source": 1}
                )
                if similar:
                    logger.info(f"🔍 [Get industry] Find similar code: {similar}")
            else:
                logger.info(f"🔍 [获取行业] 市场 {market} 暂不支持行业查询")
        except Exception as e:
            logger.error(f"❌ [获取行业] 获取股票 {code} 行业信息失败: {e}", exc_info=True)
        return None

    def _get_currency_by_market(self, market: str) -> str:
        """根据市场获取货币"""
        currency_map = {
            "CN": "CNY",
            "HK": "HKD",
            "US": "USD"
        }
        return currency_map.get(market, "CNY")

    # ==================== Single stock position analysis ====================

    async def get_position_by_id(self, user_id: str, position_id: str) -> Optional[PositionResponse]:
        """根据ID获取持仓"""
        try:
            obj_id = ObjectId(position_id)
        except Exception:
            return None

        position = await self.db[self.positions_collection].find_one(
            {"_id": obj_id, "user_id": user_id}
        )
        if position:
            return await self._enrich_position(position, "real")
        return None

    async def analyze_position(
        self,
        user_id: str,
        position_id: str,
        params: PositionAnalysisRequest
    ) -> PositionAnalysisReport:
        """Single stock position analysis

        Process:
        1. Check whether there is a cached single stock analysis report (only read the cache, do not create a new task)
        2. If there is a cache, use the cached report; if there is no cache, use the empty report
        3. Will analyze the report (or empty report)+ Position information is sent to position analysis only LLM
        4. Generate personalized position research observations (not trading recommendations)
        """
        analysis_id = str(uuid.uuid4())

        # Get position data
        position = await self.get_position_by_id(user_id, position_id)
        if not position:
            report = PositionAnalysisReport(
                analysis_id=analysis_id,
                user_id=user_id,
                position_id=position_id,
                status=PortfolioAnalysisStatus.FAILED,
                error_message="持仓不存在"
            )
            return report

        # Build a position snapshot
        holding_days = None
        if position.buy_date:
            holding_days = (datetime.now() - datetime.fromisoformat(position.buy_date.replace('Z', '+00:00').split('+')[0])).days

        # Calculate position proportion (if total funds are provided)
        position_pct = None
        if params.total_capital and params.total_capital > 0 and position.market_value:
            position_pct = round((position.market_value / params.total_capital) * 100, 2)

        snapshot = PositionSnapshot(
            code=position.code,
            name=position.name,
            market=position.market,
            quantity=position.quantity,
            cost_price=position.cost_price,
            current_price=position.current_price,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            unrealized_pnl_pct=position.unrealized_pnl_pct,
            industry=position.industry,
            holding_days=holding_days,
            total_capital=params.total_capital,
            position_pct=position_pct
        )

        report = PositionAnalysisReport(
            analysis_id=analysis_id,
            user_id=user_id,
            position_id=position_id,
            position_snapshot=snapshot,
            status=PortfolioAnalysisStatus.PROCESSING
        )

        try:
            start_time = datetime.now()

            # Convert market code to Chinese name (for cached queries)
            market_name = convert_market_code_to_name(position.market, position.code)

            # Check whether there is a cached single stock analysis report (only read the cache, do not create a new task)
            logger.info(f"📊 [持仓分析] 检查单股分析报告缓存 - {position.code} (市场: {position.market} -> {market_name})")
            stock_analysis_report = await self._get_cached_stock_analysis_report(
                stock_code=position.code,
                market=market_name,
                cache_hours=24  # Use cache within 24 hours
            )

            # If there is no cached report, create an empty structure and perform position analysis directly.
            if not stock_analysis_report:
                logger.info(f"ℹ️ [Position analysis] Cache report not found, proceed directly to position analysis - {position.code}")
                stock_analysis_report = {
                    "task_id": None,
                    "reports": {},
                    "decision": {},
                    "summary": "",
                    "recommendation": "",
                    "source": "none"
                }
            else:
                logger.info(f"✅ [持仓分析] 找到缓存报告，将作为参考 - {position.code}, 来源: {stock_analysis_report.get('source', 'unknown')}")

            # Conduct position analysis based on position information
            logger.info(f"📊 [Position analysis] Start position-specific analysis - {position.code}")

            # Choose an analysis engine based on your configuration (USE_STOCK_ENGINE=true when using Workflow Engine v2.0)
            if _use_stock_engine():
                logger.info(f"🚀 [Position analysis] Analysis using Workflow Engine v2.0")
                ai_result = await self._call_position_ai_analysis_workflow(
                    snapshot=snapshot,
                    params=params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )
            else:
                logger.info(f"🤖 [Position analysis] Using traditional LLM analysis")
                ai_result = await self._call_position_ai_analysis_v2(
                    snapshot=snapshot,
                    params=params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            report.ai_analysis = ai_result
            report.execution_time = execution_time
            report.status = PortfolioAnalysisStatus.COMPLETED
            # Save a reference to a single stock analysis report
            report.stock_analysis_task_id = stock_analysis_report.get("task_id")
            logger.info(f"✅ 单股持仓分析完成: {position.code}, 建议: {ai_result.action}")

        except Exception as e:
            logger.error(f"❌ 单股持仓分析失败: {e}", exc_info=True)
            report.status = PortfolioAnalysisStatus.FAILED
            report.error_message = str(e)

        # save report
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        await self.db[self.position_analysis_collection].insert_one(report_dict)
        return report

    async def create_position_analysis_task(
        self,
        user_id: str,
        code: str,
        market: str,
        params: "PositionAnalysisByCodeRequest"
    ) -> Dict[str, Any]:
        """Create a position analysis task (asynchronous mode)

        Immediately return task information and perform analysis in the background
        """
        import asyncio
        from app.models.portfolio import PositionAnalysisByCodeRequest

        analysis_id = str(uuid.uuid4())

        # Check if there is already an analysis in progress
        existing = await self.db[self.position_analysis_collection].find_one({
            "user_id": user_id,
            "position_id": f"{code}_{market}",
            "status": {"$in": ["pending", "processing"]}
        })

        if existing:
            return {
                "analysis_id": existing.get("analysis_id"),
                "code": code,
                "market": market,
                "status": existing.get("status"),
                "message": "已有分析任务正在进行中",
                "created_at": existing.get("created_at").isoformat() if existing.get("created_at") else None
            }

        # Check for recently completed analysis (within 30 minutes)
        # 🔥 Use now_tz() Make sure the time zone matches
        recent_cutoff = now_tz() - timedelta(minutes=30)
        recent_completed = await self.db[self.position_analysis_collection].find_one({
            "user_id": user_id,
            "position_id": f"{code}_{market}",
            "status": "completed",
            "created_at": {"$gte": recent_cutoff}
        }, sort=[("created_at", -1)])

        if recent_completed:
            return {
                "analysis_id": recent_completed.get("analysis_id"),
                "code": code,
                "market": market,
                "status": "completed",
                "message": "The most recent analysis reports are available and can be viewed directly",
                "created_at": recent_completed.get("created_at").isoformat() if recent_completed.get("created_at") else None
            }

        # Create a new analysis task record
        report = PositionAnalysisReport(
            analysis_id=analysis_id,
            user_id=user_id,
            position_id=f"{code}_{market}",
            status=PortfolioAnalysisStatus.PENDING
        )

        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        await self.db[self.position_analysis_collection].insert_one(report_dict)

        # Start analysis tasks in the background
        asyncio.create_task(self._execute_position_analysis_background(
            user_id=user_id,
            analysis_id=analysis_id,
            code=code,
            market=market,
            params=params
        ))

        return {
            "analysis_id": analysis_id,
            "code": code,
            "market": market,
            "status": "pending",
            "message": "The analysis task has been created and is expected to take 2-5 minutes.",
            "created_at": report.created_at.isoformat()
        }

    async def _execute_position_analysis_background(
        self,
        user_id: str,
        analysis_id: str,
        code: str,
        market: str,
        params: "PositionAnalysisByCodeRequest"
    ):
        """后台执行持仓分析"""
        try:
            # Update status is processing
            await self.db[self.position_analysis_collection].update_one(
                {"analysis_id": analysis_id},
                {"$set": {"status": "processing"}}
            )

            # Perform actual analysis
            report = await self.analyze_position_by_code(user_id, code, market, params)

            # Update analysis results
            update_data = {
                "status": report.status.value,
                "position_snapshot": report.position_snapshot.model_dump() if report.position_snapshot else None,
                "ai_analysis": report.ai_analysis.model_dump() if report.ai_analysis else None,
                "execution_time": report.execution_time,
                "error_message": report.error_message,
                "stock_analysis_task_id": report.stock_analysis_task_id
            }

            await self.db[self.position_analysis_collection].update_one(
                {"analysis_id": analysis_id},
                {"$set": update_data}
            )

            logger.info(f"✅ 后台持仓分析完成: {code}, analysis_id={analysis_id}")

        except Exception as e:
            logger.error(f"❌ 后台持仓分析失败: {code}, error={e}", exc_info=True)
            await self.db[self.position_analysis_collection].update_one(
                {"analysis_id": analysis_id},
                {"$set": {"status": "failed", "error_message": str(e)}}
            )

    async def get_position_analysis_by_id(
        self,
        user_id: str,
        analysis_id: str
    ) -> Optional[Dict[str, Any]]:
        """根据分析ID获取分析报告"""
        report = await self.db[self.position_analysis_collection].find_one({
            "user_id": user_id,
            "analysis_id": analysis_id
        })

        if not report:
            return None

        return self._format_position_analysis_report(report)

    async def get_latest_position_analysis(
        self,
        user_id: str,
        code: str,
        market: str,
        position_type: str = "real"
    ) -> Optional[Dict[str, Any]]:
        """Get the latest analysis report on a stock
        
        Args:
            user_id: User ID
            code: Stock code
            market: market type
            position_type: Position type (real/simulated)
        """
        # 🔥 Query the corresponding analysis report based on position_type
        query = {
            "user_id": user_id,
            "position_id": f"{code}_{market}",
            "position_type": position_type  # Add position_type filter
        }
        
        report = await self.db[self.position_analysis_collection].find_one(
            query,
            sort=[("created_at", -1)]
        )

        if not report:
            return None

        return self._format_position_analysis_report(report)

    def _format_position_analysis_report(self, report: Dict) -> Dict[str, Any]:
        """格式化分析报告为响应格式"""
        snapshot = report.get("position_snapshot") or {}
        ai_analysis = report.get("ai_analysis") or {}
        price_targets = ai_analysis.get("price_targets") or {}
        
        # Process action_reason: If it is in JSON format, convert it to Markdown
        action_reason_raw = ai_analysis.get("action_reason")
        action_reason_formatted = action_reason_raw
        
        if action_reason_raw:
            logger.info(f"📊 [格式化报告] 原始action_reason类型: {type(action_reason_raw)}, 长度: {len(str(action_reason_raw)) if action_reason_raw else 0}")
            
            import json
            advice_json = None
            
            # If it is a string, try to parse JSON
            if isinstance(action_reason_raw, str):
                action_reason_str = action_reason_raw.strip()
                logger.info(f"📊 [Format reports] action_reason first 100 characters: {action_reason_str[:100]}")
                
                # Check if it contains JSON code block or JSON format
                if "```json" in action_reason_str or (action_reason_str.startswith("{") and ("analysis_summary" in action_reason_str or "neutral_operation" in action_reason_str)):
                    try:
                        # Extract JSON
                        if "```json" in action_reason_str:
                            json_start = action_reason_str.find("```json") + 7
                            json_end = action_reason_str.find("```", json_start)
                            if json_end > json_start:
                                json_str = action_reason_str[json_start:json_end].strip()
                                logger.info(f"📊 [Format reports] Extract JSON from code block, length: {len(json_str)}")
                                advice_json = json.loads(json_str)
                        elif action_reason_str.strip().startswith("{"):
                            logger.info(f"📊 [Format reports] Directly parse JSON format")
                            advice_json = json.loads(action_reason_str)
                        
                        if advice_json:
                            logger.info(f"📊 [Format reports] JSON Parsed successfully, field: {list(advice_json.keys())}")
                            action_reason_formatted = self._convert_action_advice_json_to_markdown(advice_json)
                            logger.info(f"📊 [Format reports] JSON Conversion to Markdown successful, length: {len(action_reason_formatted)}")
                        else:
                            logger.warning(f"⚠️ [Format reports] JSON Empty after parsing, use original value")
                    except Exception as e:
                        logger.warning(f"⚠️ [Format reports] JSON Parse failed, original value used: {e}", exc_info=True)
            elif isinstance(action_reason_raw, dict):
                # If it is already in dictionary format, convert it directly
                logger.info(f"📊 [Format reports] action_reason is a dictionary format, field: {list(action_reason_raw.keys())}")
                action_reason_formatted = self._convert_action_advice_json_to_markdown(action_reason_raw)
                logger.info(f"📊 [Format reports] Dictionary converted to Markdown successfully, length: {len(action_reason_formatted)}")
        
        return {
            "analysis_id": report.get("analysis_id"),
            "position_id": report.get("position_id"),
            "code": snapshot.get("code") or report.get("position_id", "").split("_")[0],
            "name": snapshot.get("name"),
            "market": snapshot.get("market") or report.get("position_id", "").split("_")[-1],
            "status": report.get("status"),
            "action": ai_analysis.get("action"),
            "action_reason": action_reason_formatted,
            "confidence": ai_analysis.get("confidence"),
            "price_targets": price_targets,
            "risk_assessment": ai_analysis.get("risk_assessment"),
            "opportunity_assessment": ai_analysis.get("opportunity_assessment"),
            "detailed_analysis": ai_analysis.get("detailed_analysis"),
            "execution_time": report.get("execution_time"),
            "error_message": report.get("error_message"),
            "created_at": report.get("created_at").isoformat() if report.get("created_at") else None,
            "summary": {
                "quantity": snapshot.get("quantity"),
                "cost_price": snapshot.get("cost_price"),
                "current_price": snapshot.get("current_price"),
                "market_value": snapshot.get("market_value"),
                "unrealized_pnl": snapshot.get("unrealized_pnl"),
                "unrealized_pnl_pct": snapshot.get("unrealized_pnl_pct"),
                "holding_days": snapshot.get("holding_days"),
                "position_pct": snapshot.get("position_pct"),
            }
        }

    async def analyze_position_by_code(
        self,
        user_id: str,
        code: str,
        market: str,
        params: "PositionAnalysisByCodeRequest"
    ) -> PositionAnalysisReport:
        """Analyze positions by stock symbol - summarize all positions opened on the same stock

        This method will:
        1. Query all position records of this stock
        2. Summarize and calculate total quantity, average cost price, total market value, etc.
        3. Analyze as a whole
        """
        from app.models.portfolio import PositionAnalysisByCodeRequest

        analysis_id = str(uuid.uuid4())

        # 🔥 Choose whether to query user positions or simulate positions based on position_type
        position_type = params.position_type if hasattr(params, 'position_type') else "real"
        if position_type == "simulated":
            # Query simulated positions
            collection = self.paper_positions_collection
            logger.info(f"📊 [Position analysis] Query simulated positions: {code} ({market})")
        else:
            # Query user positions
            collection = self.positions_collection
            logger.info(f"📊 [Position analysis] Query user positions: {code} ({market})")

        # Query all position records of this stock
        storage_market = "CN" if market == "ETF" else market
        positions = await self.db[collection].find({
            "user_id": user_id,
            "code": code,
            "market": storage_market
        }).to_list(None)

        if not positions:
            report = PositionAnalysisReport(
                analysis_id=analysis_id,
                user_id=user_id,
                position_id=f"{code}_{storage_market}",  # Use stock symbols as identifiers
                status=PortfolioAnalysisStatus.FAILED,
                error_message=f"未找到 {code} 的持仓记录"
            )
            return report

        # Summary calculation
        total_quantity = sum(p.get("quantity", 0) for p in positions)
        # 🔥 Select the cost price field according to the position type: use avg_cost for simulated positions, use avg_cost for user positions cost_price
        if position_type == "simulated":
            total_cost = sum(p.get("quantity", 0) * p.get("avg_cost", 0) for p in positions)
        else:
            total_cost = sum(p.get("quantity", 0) * p.get("cost_price", 0) for p in positions)
        avg_cost_price = total_cost / total_quantity if total_quantity > 0 else 0

        # Get current price
        current_price = await self._get_stock_price(code, storage_market)
        # 🔥 Fix: Make sure market_value, unrealized_pnl and unrealized_pnl_pct are not None (may be None when simulating position analysis)
        if current_price and current_price > 0:
            market_value = current_price * total_quantity
            unrealized_pnl = market_value - total_cost
            unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
        else:
            market_value = 0.0
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0

        # Get stock name and industry
        name = positions[0].get("name") or await self._get_stock_name(code, storage_market)
        industry = positions[0].get("industry") or await self._get_stock_industry(code, storage_market)

        # Calculate the number of days the position has been held (using the earliest opening date)
        holding_days = None
        earliest_date = None
        for p in positions:
            buy_date = p.get("buy_date")
            if buy_date:
                if isinstance(buy_date, str):
                    buy_date = datetime.fromisoformat(buy_date.replace('Z', '+00:00').split('+')[0])
                if earliest_date is None or buy_date < earliest_date:
                    earliest_date = buy_date
        if earliest_date:
            holding_days = (datetime.now() - earliest_date).days

        # Calculate position proportion
        position_pct = None
        if params.total_capital and params.total_capital > 0 and market_value:
            position_pct = round((market_value / params.total_capital) * 100, 2)

        # Construct a position snapshot (aggregated)
        snapshot = PositionSnapshot(
            code=code,
            name=name,
            market=storage_market,
            quantity=total_quantity,
            cost_price=round(avg_cost_price, 4),
            current_price=current_price if current_price else 0.0,
            market_value=round(market_value, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
            industry=industry,
            holding_days=holding_days,
            total_capital=params.total_capital,
            position_pct=position_pct
        )

        # Create analysis parameters (converted to PositionAnalysisRequest)
        analysis_params = PositionAnalysisRequest(
            research_depth=params.research_depth,
            include_add_position=params.include_add_position,
            target_profit_pct=params.target_profit_pct,
            total_capital=params.total_capital,
            max_position_pct=params.max_position_pct,
            max_loss_pct=params.max_loss_pct
        )

        report = PositionAnalysisReport(
            analysis_id=analysis_id,
            user_id=user_id,
            position_id=f"{code}_{storage_market}",  # Use stock symbols as identifiers
            position_snapshot=snapshot,
            status=PortfolioAnalysisStatus.PROCESSING
        )

        try:
            start_time = datetime.now()

            # Convert market symbols to Chinese names (required for single stock analysis service)
            market_name = convert_market_code_to_name(market, code)

            # Check whether there is a cached single stock analysis report (only read the cache, do not create a new task)
            stock_analysis_report = None
            if params.use_stock_analysis:
                logger.info(f"📊 [汇总持仓分析] 检查单股分析报告缓存 - {code} (市场: {market} -> {market_name}, 共{len(positions)}条记录)")
                stock_analysis_report = await self._get_cached_stock_analysis_report(
                    stock_code=code,
                    market=market_name,
                    cache_hours=24  # Use cache within 24 hours
                )

                # If no report is cached, log
                if not stock_analysis_report:
                    logger.info(f"ℹ️ [Summary position analysis] Cache report not found, position analysis will be performed directly - {code}")
                else:
                    logger.info(f"✅ [汇总持仓分析] 找到缓存报告，将作为参考 - {code}, 来源: {stock_analysis_report.get('source', 'unknown')}")
            else:
                logger.info(f"⏭️ [Summary position analysis] User chooses not to use single stock analysis report - {code}")

            # If there is no single stock analysis report, create an empty report structure to avoid subsequent code errors.
            if not stock_analysis_report:
                stock_analysis_report = {
                    "task_id": None,
                    "reports": {},
                    "decision": {},
                    "summary": "",
                    "recommendation": "",
                    "source": "none"
                }

            # The second stage: position analysis based on position information
            logger.info(f"📊 [Summary position analysis] The second stage: position-specific analysis - {code}")

            # Choose an analysis engine based on your configuration (USE_STOCK_ENGINE=true when using Workflow Engine v2.0)
            if _use_stock_engine():
                logger.info(f"🚀 [Summary position analysis] Analysis using Workflow Engine v2.0")
                ai_result = await self._call_position_ai_analysis_workflow(
                    snapshot=snapshot,
                    params=analysis_params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )
            else:
                logger.info(f"🤖 [Summary position analysis] Using traditional LLM analysis")
                ai_result = await self._call_position_ai_analysis_v2(
                    snapshot=snapshot,
                    params=analysis_params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            report.ai_analysis = ai_result
            report.execution_time = execution_time
            report.status = PortfolioAnalysisStatus.COMPLETED
            report.stock_analysis_task_id = stock_analysis_report.get("task_id")
            logger.info(f"✅ 汇总持仓分析完成: {code}, 建议: {ai_result.action}, 共{len(positions)}条记录")

        except Exception as e:
            logger.error(f"❌ 汇总持仓分析失败: {e}", exc_info=True)
            report.status = PortfolioAnalysisStatus.FAILED
            report.error_message = str(e)

        # save report
        report_dict = report.model_dump(by_alias=True, exclude={"id"})
        # 🔥 Add the position_type field to the report record, which can be used to distinguish simulated positions and user positions in subsequent queries.
        report_dict["position_type"] = position_type
        await self.db[self.position_analysis_collection].insert_one(report_dict)
        return report

    async def analyze_position_by_code_v2(
        self,
        user_id: str,
        code: str,
        market: str,
        params: "PositionAnalysisByCodeRequest"
    ) -> PositionAnalysisReport:
        """Analyze positions by ticker v2.0 - using the Unified Task Engine

        Advantages:
        - Support multi-engine switching (workflow/legacy/llm)
        - Unified task management and progress tracking
        - Automatically select the best engine
        - Tasks can be queried and canceled

        Args:
            user_id: User ID
            code: Stock code
            market: Market type (CN/HK/US)
            params: Analysis parameters

        Returns:
            Position analysis report
        """
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType
        from app.models.portfolio import PositionAnalysisByCodeRequest
        from app.models.user import PyObjectId

        logger.info(f"🚀 [持仓分析v2.0] 使用统一任务引擎分析: {code} (市场: {market})")

        # Query all position records of this stock (used to build a snapshot)
        positions = await self.db[self.positions_collection].find({
            "user_id": user_id,
            "code": code,
            "market": market
        }).to_list(None)

        if not positions:
            # If there is no position record, a failure report will be returned.
            analysis_id = str(uuid.uuid4())
            report = PositionAnalysisReport(
                analysis_id=analysis_id,
                user_id=user_id,
                position_id=f"{code}_{market}",
                status=PortfolioAnalysisStatus.FAILED,
                error_message=f"未找到 {code} 的持仓记录"
            )
            return report

        # Summarize and calculate position data
        total_quantity = sum(p.get("quantity", 0) for p in positions)
        total_cost = sum(p.get("quantity", 0) * p.get("cost_price", 0) for p in positions)
        avg_cost_price = total_cost / total_quantity if total_quantity > 0 else 0

        # Get current price
        current_price = await self._get_stock_price(code, market)
        market_value = current_price * total_quantity if current_price else None
        unrealized_pnl = (market_value - total_cost) if market_value else None
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if unrealized_pnl and total_cost > 0 else None

        # Get stock name and industry
        name = positions[0].get("name") or await self._get_stock_name(code, market)
        industry = positions[0].get("industry") or await self._get_stock_industry(code, market)

        # Calculate position holding days
        holding_days = None
        earliest_date = None
        for p in positions:
            buy_date = p.get("buy_date")
            if buy_date:
                if isinstance(buy_date, str):
                    buy_date = datetime.fromisoformat(buy_date.replace('Z', '+00:00').split('+')[0])
                if earliest_date is None or buy_date < earliest_date:
                    earliest_date = buy_date
        if earliest_date:
            holding_days = (datetime.now() - earliest_date).days

        # Calculate position proportion
        position_pct = None
        if params.total_capital and params.total_capital > 0 and market_value:
            position_pct = round((market_value / params.total_capital) * 100, 2)

        # Build a position snapshot
        snapshot = PositionSnapshot(
            code=code,
            name=name,
            market=market,
            quantity=total_quantity,
            cost_price=round(avg_cost_price, 4),
            current_price=current_price,
            market_value=round(market_value, 2) if market_value else None,
            unrealized_pnl=round(unrealized_pnl, 2) if unrealized_pnl else None,
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2) if unrealized_pnl_pct else None,
            industry=industry,
            holding_days=holding_days,
            total_capital=params.total_capital,
            position_pct=position_pct
        )

        # Prepare task parameters
        task_params = {
            "code": code,
            "market": market,
            "snapshot": snapshot.model_dump(),
            "research_depth": params.research_depth,
            "include_add_position": params.include_add_position,
            "target_profit_pct": params.target_profit_pct,
            "total_capital": params.total_capital,
            "max_position_pct": params.max_position_pct,
            "max_loss_pct": params.max_loss_pct,
            "use_stock_analysis": params.use_stock_analysis
        }

        # Use unified task engine
        task_service = get_task_analysis_service()

        try:
            # Create and execute tasks
            task = await task_service.create_and_execute_task(
                user_id=PyObjectId(user_id),
                task_type=AnalysisTaskType.POSITION_ANALYSIS,
                task_params=task_params,
                engine_type=getattr(params, "engine_type", "auto"),  # Support engine selection
                preference_type=getattr(params, "preference_type", "neutral")
            )

            # Convert task results to PositionAnalysisReport
            report = PositionAnalysisReport(
                analysis_id=task.task_id,
                user_id=user_id,
                position_id=f"{code}_{market}",
                position_snapshot=snapshot,
                status=PortfolioAnalysisStatus.COMPLETED if task.status == "completed" else PortfolioAnalysisStatus.FAILED,
                execution_time=task.execution_time,
                error_message=task.error_message
            )

            # Extract AI analytics from task results
            if task.result and "ai_analysis" in task.result:
                report.ai_analysis = AIAnalysisResult(**task.result["ai_analysis"])

            logger.info(f"✅ [持仓分析v2.0] 分析完成: {code}, 任务ID: {task.task_id}")

            # save report
            report_dict = report.model_dump(by_alias=True, exclude={"id"})
            await self.db[self.position_analysis_collection].insert_one(report_dict)

            return report

        except Exception as e:
            logger.error(f"❌ [Position analysis v2.0] Analysis failed: {code} - {e}", exc_info=True)

            # Return failure report
            report = PositionAnalysisReport(
                analysis_id=str(uuid.uuid4()),
                user_id=user_id,
                position_id=f"{code}_{market}",
                position_snapshot=snapshot,
                status=PortfolioAnalysisStatus.FAILED,
                error_message=str(e)
            )

            # save report
            report_dict = report.model_dump(by_alias=True, exclude={"id"})
            await self.db[self.position_analysis_collection].insert_one(report_dict)

            return report

    async def check_stock_analysis_cache(
        self,
        stock_code: str,
        market: str = "A股"
    ) -> Dict[str, Any]:
        """Check Single Stock Analysis Report Cache Status
        
        Args:
            stock_code: Stock code
            market: Market type (A shares/Hong Kong stocks/US stocks)
            
        Returns:
            Dictionary containing cache status:
            {
                "has_cache": bool,  # Is there a cache
                "cache_age_minutes": int,  # Cache age (minutes)
                "cache_age_hours": float,  # Cache age (hours)
                "source": str  # cache source ("engine" or "legacy") 
            }
        """
        from app.core.database import get_mongo_db
        
        db = get_mongo_db()
        
        # Check reports within 24 hours (standard for front-end prompts users)
        cache_hours = 24
        # 🔥 Use now_tz() Make sure the time zone matches
        recent_cutoff = now_tz() - timedelta(hours=cache_hours)
        
        # Check the cache of legacy engines (analysis_reports collection)
        # This is the most common cache location and will be used regardless of whether the new engine is enabled or not
        existing_report = await db.analysis_reports.find_one({
            "stock_symbol": stock_code,
            "created_at": {"$gte": recent_cutoff},
            "status": "completed"
        }, sort=[("created_at", -1)])
        
        if existing_report:
            created_at = existing_report.get("created_at", datetime.now())
            if isinstance(created_at, str):
                from dateutil.parser import parse
                created_at = parse(created_at)
            elif created_at is None:
                created_at = now_tz()
            
            # 🔥 Make sure the time zone is consistent: MongoDB stores UTC time
            # If reading from MongoDB is a naive datetime, it should be assumed to be UTC
            # Note: tz and now_tz are imported at the top of the file
            current_time = now_tz()
            
            if created_at:
                # If created_at is a naive datetime, UTC is assumed (because MongoDB stores UTC)
                if isinstance(created_at, datetime) and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=tz.utc)
                # Convert to configured time zone for calculating time differences
                if created_at.tzinfo:
                    created_at = created_at.astimezone(current_time.tzinfo)
            else:
                created_at = current_time
            
            report_age = current_time - created_at
            age_minutes = int(report_age.total_seconds() / 60)
            age_hours = report_age.total_seconds() / 3600
            
            logger.info(f"✅ [检查缓存] 找到旧版引擎缓存: {stock_code}, 年龄: {age_minutes}分钟 (created_at: {created_at}, current_time: {current_time})")
            return {
                "has_cache": True,
                "cache_age_minutes": age_minutes,
                "cache_age_hours": round(age_hours, 2),
                "source": "legacy"
            }
        
        # cache not found
        logger.info(f"❌ [Check cache] cache not found: {stock_code}")
        return {
            "has_cache": False,
            "cache_age_minutes": None,
            "cache_age_hours": None,
            "source": None
        }

    async def _get_cached_stock_analysis_report(
        self,
        stock_code: str,
        market: str = "A股",
        cache_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """Only get the stock analysis report from the cache (do not create a new task)
        
        It is only used in position analysis scenarios. It only reads the existing cache and does not create new single stock analysis tasks.
        
        Args:
            stock_code: Stock code
            market: Market type (A shares/Hong Kong stocks/US stocks)
            cache_hours: Cache validity period (hours)
            
        Returns:
            Analysis report dictionary, returned if not cached None
        """
        from app.core.database import get_mongo_db
        
        db = get_mongo_db()
        # 🔥 Use now_tz() Make sure the time zone matches
        recent_cutoff = now_tz() - timedelta(hours=cache_hours)
        
        # Check if there is a completed analysis report (any user)
        existing_report = await db.analysis_reports.find_one({
            "stock_symbol": stock_code,
            "created_at": {"$gte": recent_cutoff},
            "status": "completed"
        }, sort=[("created_at", -1)])
        
        if existing_report:
            created_at = existing_report.get("created_at", datetime.now())
            if isinstance(created_at, str):
                from dateutil.parser import parse
                created_at = parse(created_at)
            
            # 🔥 Make sure the time zone is consistent: MongoDB stores UTC time
            # If reading from MongoDB is a naive datetime, it should be assumed to be UTC
            # Note: tz and now_tz are imported at the top of the file
            current_time = now_tz()
            
            if created_at:
                # If created_at is a naive datetime, UTC is assumed (because MongoDB stores UTC)
                if isinstance(created_at, datetime) and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=tz.utc)
                # Convert to configured time zone for calculating time differences
                if created_at.tzinfo:
                    created_at = created_at.astimezone(current_time.tzinfo)
            else:
                created_at = current_time
            
            report_age = current_time - created_at
            age_minutes = int(report_age.total_seconds() / 60)
            age_hours = report_age.total_seconds() / 3600
            
            logger.info(f"📚 [持仓分析] 从缓存读取单股分析报告: {stock_code}, "
                       f"task_id={existing_report.get('task_id')}, "
                       f"reporting time: {age_minutes}minutes ago (created_at: {created_at}, current_time: {current_time})")
            return {
                "task_id": existing_report.get("task_id"),
                "reports": existing_report.get("reports", {}),
                "decision": existing_report.get("decision", {}),
                "summary": existing_report.get("summary", ""),
                "recommendation": existing_report.get("recommendation", ""),
                "source": "cached",
                "cache_age_minutes": age_minutes,
                "cache_age_hours": round(age_hours, 2)
            }
        
        logger.info(f"❌ [Position analysis] Cached single stock analysis report not found: {stock_code}")
        return None

    async def _get_stock_analysis_via_engine(
        self,
        stock_code: str,
        market: str = "A股"
    ) -> Optional[Dict[str, Any]]:
        """Get analysis reports using the new version of StockAnalysisEngine — Deactivated

        v3.0 The old version of StockAnalysisEngine is deprecated (dead code, no caller).
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] PortfolioService._get_stock_analysis_via_engine deactivated,"
            "Please use analyze_position_by_code_v2 or _get_cached_stock_analysis_report."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            from tradingagents.core.engine.stock_analysis_engine import StockAnalysisEngine
            from core.workflow.builder import LegacyDependencyProvider

            # Switch market type
            market_type_map = {
                "A股": "cn",
                "港股": "hk",
                "美股": "us",
                "ETF": "cn"
            }
            market_type = market_type_map.get(market, "cn")

            logger.info(f"🚀 [持仓分析] 使用 StockAnalysisEngine 分析: {stock_code} (市场: {market_type})")

            # Create LLM dependency provider (get LLM from database configuration)
            dependency_provider = LegacyDependencyProvider.get_instance()
            llm = dependency_provider.get_llm("quick")

            engine = StockAnalysisEngine(
                llm=llm,
                use_stub=False
            )
            result = engine.analyze(
                ticker=stock_code,
                trade_date=datetime.now().strftime("%Y-%m-%d"),
                market_type=market_type
            )

            if result and result.success:
                logger.info(f"✅ [Position analysis] StockAnalysisEngine Analysis completed: {stock_code}")

                # Convert to unified return format
                context = result.context
                reports = {}

                # Extract each analyst report from context
                if hasattr(context, 'reports') and context.reports:
                    reports = context.reports
                elif hasattr(context, 'get'):
                    reports = {
                        "market_report": context.get("market_report", ""),
                        "fundamentals_report": context.get("fundamentals_report", ""),
                        "news_report": context.get("news_report", ""),
                        "sentiment_report": context.get("sentiment_report", ""),
                        "sector_report": context.get("sector_report", "")
                    }

                return {
                    "task_id": "engine",
                    "source": "stock_analysis_engine",
                    "reports": reports,
                    "decision": result.final_decision if hasattr(result, 'final_decision') else {},
                    "summary": result.summary if hasattr(result, 'summary') else "",
                    "recommendation": result.recommendation if hasattr(result, 'recommendation') else ""
                }
            else:
                logger.warning(f"⚠️ [Position analysis] StockAnalysisEngine Return failure result: {stock_code}")
                return None

        except ImportError as e:
            logger.warning(f"⚠️ [Position analysis] StockAnalysisEngine Module not available: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [Position analysis] StockAnalysisEngine Call exception: {e}", exc_info=True)
            return None

    async def _get_stock_analysis_via_legacy(
        self,
        user_id: str,
        stock_code: str,
        market: str = "A股",
        skip_if_not_exists: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Use the old version of simple_analysis_service to obtain analysis reports (downgrade scenario)— Deactivated

        v3.0 The legacy engine has been deactivated (dead code, no callers).
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Args:
            user_id: User ID
            stock_code: Stock code
            market: market type
            skip_if_not_exists: If there is no cached report, whether to skip it (no new task will be created)

        Returns:
            Analysis report dictionary if skip_if_not_exists=True And if there is no cache, return None

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] PortfolioService._get_stock_analysis_via_legacy deactivated,"
            "Please use analyze_position_by_code_v2 or _get_cached_stock_analysis_report."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        from app.services.simple_analysis_service import get_simple_analysis_service
        from app.models.analysis import SingleAnalysisRequest, AnalysisParameters
        from app.core.database import get_mongo_db
        import asyncio

        analysis_service = get_simple_analysis_service()

        db = get_mongo_db()

        # 3 Reports within hours can be reused (stock fundamentals and technical data change little)
        cache_hours = 3
        # 🔥 Use now_tz() Make sure the time zone matches
        recent_cutoff = now_tz() - timedelta(hours=cache_hours)

        # 1. First check whether there is a completed analysis report (within 3 hours, no limit to users)
        # The results of single stock analysis are the same for all users and can be shared
        # Note: The stock_symbol field (not stock_code) is used in the analysis_reports collection
        existing_report = await db.analysis_reports.find_one({
            "stock_symbol": stock_code,  # Use stock_symbol field matching
            "created_at": {"$gte": recent_cutoff},
            "status": "completed"
        }, sort=[("created_at", -1)])

        if existing_report:
            created_at = existing_report.get("created_at", datetime.now())
            if isinstance(created_at, str):
                from dateutil.parser import parse
                created_at = parse(created_at)
            
            # 🔥 Make sure the time zone is consistent: MongoDB stores UTC time
            # If reading from MongoDB is a naive datetime, it should be assumed to be UTC
            # Note: tz and now_tz are imported at the top of the file
            current_time = now_tz()
            
            if created_at:
                # If created_at is a naive datetime, UTC is assumed (because MongoDB stores UTC)
                if isinstance(created_at, datetime) and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=tz.utc)
                # Convert to configured time zone for calculating time differences
                if created_at.tzinfo:
                    created_at = created_at.astimezone(current_time.tzinfo)
            else:
                created_at = current_time
            
            report_age = current_time - created_at
            age_minutes = int(report_age.total_seconds() / 60)
            logger.info(f"📚 [持仓分析] 复用已完成的分析报告: {stock_code}, "
                       f"task_id={existing_report.get('task_id')}, "
                       f"reporting time: {age_minutes}minutes ago (created_at: {created_at}, current_time: {current_time})")
            return {
                "task_id": existing_report.get("task_id"),
                "reports": existing_report.get("reports", {}),
                "decision": existing_report.get("decision", {}),
                "summary": existing_report.get("summary", ""),
                "recommendation": existing_report.get("recommendation", ""),
                "source": "cached",
                "cache_age_minutes": age_minutes
            }

        # If skip_if_not_exists is set and there is no cached report, return directly None
        if skip_if_not_exists:
            logger.info(f"⏭️ [Position analysis] No cached single stock analysis report, skip single stock analysis: {stock_code}")
            return None

        # 2. Check if there are any running analysis tasks (avoid duplicate creation, not limited to users)
        # Note: The stock_symbol field is used in the analysis_reports collection
        running_report = await db.analysis_reports.find_one({
            "stock_symbol": stock_code,  # Use stock_symbol field matching
            "created_at": {"$gte": recent_cutoff},
            "status": {"$in": ["pending", "running"]}
        }, sort=[("created_at", -1)])

        if running_report:
            task_id = running_report.get("task_id")
            logger.info(f"⏳ [Position analysis] Found running tasks, waiting for completion: {stock_code}, task_id={task_id}")
            # Wait for this running task to complete
            return await self._wait_for_analysis_task(analysis_service, task_id, stock_code)

        # 3. There is no cache and no running tasks, create a new analysis
        logger.info(f"🔄 [Position analysis] 3 No reports available within hours, perform new single stock analysis: {stock_code}, market={market}")

        # Create an analysis request (using quick analysis mode)
        analysis_request = SingleAnalysisRequest(
            symbol=stock_code,
            stock_code=stock_code,
            parameters=AnalysisParameters(
                research_depth="快速",  # Use fast mode to reduce waiting time
                selected_analysts=["market", "fundamentals", "news"],
                market_type=market
            )
        )

        # Create task
        task_result = await analysis_service.create_analysis_task(user_id, analysis_request)
        task_id = task_result.get("task_id")

        # Execute analysis synchronously (wait for completion)
        await analysis_service.execute_analysis_background(task_id, user_id, analysis_request)

        # Wait for task to complete
        return await self._wait_for_analysis_task(analysis_service, task_id, stock_code)

    async def _wait_for_analysis_task(
        self,
        analysis_service,
        task_id: str,
        stock_code: str,
        max_wait: int = 300
    ) -> Dict[str, Any]:
        """Wait for the analysis task to complete and return results"""
        import asyncio

        waited = 0
        while waited < max_wait:
            task_status = await analysis_service.get_task_status(task_id)
            if task_status and task_status.get("status") == "completed":
                result_data = task_status.get("result_data", {})
                logger.info(f"✅ [Position analysis] Single stock analysis completed: {stock_code}")
                return {
                    "task_id": task_id,
                    "reports": result_data.get("reports", {}),
                    "decision": result_data.get("decision", {}),
                    "summary": result_data.get("summary", ""),
                    "recommendation": result_data.get("recommendation", ""),
                    "source": "fresh"
                }
            elif task_status and task_status.get("status") == "failed":
                error_msg = task_status.get("error_message", "未知错误")
                logger.warning(f"⚠️ [持仓分析] 单股分析失败: {stock_code}, 错误: {error_msg}")
                # If an empty report is returned, the position analysis can still give suggestions based on the position information.
                return {
                    "task_id": task_id,
                    "reports": {},
                    "decision": {},
                    "summary": f"单股分析未能完成: {error_msg}",
                    "recommendation": "",
                    "source": "failed"
                }

            await asyncio.sleep(2)
            waited += 2

        # timeout
        logger.warning(f"⚠️ [Position analysis] Single stock analysis timeout: {stock_code}")
        return {
            "task_id": task_id,
            "reports": {},
            "decision": {},
            "summary": "单股分析超时",
            "recommendation": "",
            "source": "timeout"
        }

    async def _call_position_ai_analysis_v2(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest,
        stock_analysis_report: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> PositionAnalysisResult:
        """Calling AI for single stock position analysis - solution 2

        Based on complete single stock analysis report + Position information to generate personalized position research observations
        Deep analysis model using system configuration
        """
        import httpx

        try:
            # Construct special prompt words for position analysis
            prompt = self._build_position_analysis_prompt_v2(
                snapshot=snapshot,
                params=params,
                stock_analysis_report=stock_analysis_report,
                user_id=user_id
            )

            from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
            from app.services.model_capability_service import get_model_capability_service
            from tradingagents.graph.trading_graph import create_llm_by_provider

            # Deep analysis model using system configuration
            capability_service = get_model_capability_service()
            _, deep_model = capability_service._get_default_models()
            model_name = deep_model

            logger.info(f"🤖 [Position AI analysis] Get deep analysis model from system configuration: {model_name}")

            # Get the complete configuration of the model from the database (including API URL and API Key)
            provider_info = get_provider_and_url_by_model_sync(model_name)

            base_url = provider_info.get("backend_url")
            api_key = provider_info.get("api_key")
            provider = provider_info.get("provider")

            logger.info(f"🤖 [Position AI analysis] Use model: {model_name}")
            logger.info(f"🏭 [Position AI analysis] model supplier: {provider}")
            logger.info(f"🔗 [Position AI analysis] API address: {base_url}")
            logger.info(f"🔑 [Position AI analysis] API Key: {'configured' if api_key else 'Not configured'}")

            if not api_key:
                logger.warning("⚠️ [Position AI analysis] API Key Not configured, will try to get from environment variables")

            if not base_url:
                logger.error("❌ [Position AI analysis] API Address not configured")
                return PositionAnalysisResult(
                    action=PositionAction.HOLD,
                    action_reason="AI The model is not configured correctly. Please configure the API address of the in-depth analysis model in the settings."
                )

            # Use unified LLM adapter
            logger.info(f"🔧 [Position AI analysis v2] ready to create LLM: provider={provider}, model={model_name}, temperature=0.3")
            if api_key:
                logger.info(f"🔑 [Position AI analysis v2] API Key: {truncate_api_key(api_key)}")
            llm = create_llm_by_provider(
                provider=provider,
                model=model_name,
                backend_url=base_url,
                temperature=0.3,
                max_tokens=4000,
                timeout=120,
                api_key=api_key
            )

            logger.info(f"📤 [Position AI analysis] Start calling LLM...")
            response = await llm.ainvoke(prompt)

            # Record token usage
            try:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=response,
                    session_id=user_id or "portfolio",
                    analysis_type="portfolio",
                    stock_code=snapshot.code
                )
            except Exception as e:
                logger.warning(f"Record token usage failure: {e}")

            content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📥 [Position AI analysis] LLM Response successful, content length: {len(content)}")

            return self._parse_position_ai_response_v2(content, snapshot)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ [Position AI analysis] Analysis failed: {error_msg}", exc_info=True)
            from app.utils.error_formatter import ErrorFormatter

            action_reason = f"AI Analysis is temporarily unavailable:{ErrorFormatter.format_user_message(error_msg, include_suggestion=False)}"

            return PositionAnalysisResult(
                action=PositionAction.HOLD,
                action_reason=action_reason
            )

    async def _call_position_ai_analysis(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest
    ) -> PositionAnalysisResult:
        """Call AI to conduct single stock position analysis (Old version, retain compatibility)"""
        try:
            prompt = self._build_position_analysis_prompt(snapshot, params)

            from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
            from tradingagents.graph.trading_graph import create_llm_by_provider

            model_name = "qwen-turbo"
            provider_info = get_provider_and_url_by_model_sync(model_name)

            # Use unified LLM adapter
            llm = create_llm_by_provider(
                provider=provider_info.get("provider", "dashscope"),
                model=model_name,
                backend_url=provider_info.get("backend_url"),
                temperature=0.3,
                max_tokens=4000,
                timeout=120,
                api_key=provider_info.get("api_key")
            )

            response = await llm.ainvoke(prompt)

            # Record token usage
            try:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=response,
                    session_id="portfolio",
                    analysis_type="portfolio",
                    stock_code=snapshot.code
                )
            except Exception as e:
                logger.warning(f"Record token usage failure: {e}")

            content = response.content if hasattr(response, 'content') else str(response)
            return self._parse_position_ai_response(content, snapshot)

        except Exception as e:
            logger.error(f"单股AI分析失败: {e}", exc_info=True)
            from app.utils.error_formatter import ErrorFormatter

            return PositionAnalysisResult(
                action=PositionAction.HOLD,
                action_reason=f"AI Analysis is temporarily unavailable:{ErrorFormatter.format_user_message(str(e), include_suggestion=False)}"
            )

    def _build_position_analysis_prompt(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest
    ) -> str:
        """构建单股持仓分析提示词"""
        pnl_status = "盈利" if (snapshot.unrealized_pnl or 0) >= 0 else "亏损"

        prompt = f"""# 单股持仓分析任务

## 持仓信息
- 股票代码: {snapshot.code}
- 股票名称: {snapshot.name or '未知'}
- 持仓数量: {snapshot.quantity} 股
- 成本价: {snapshot.cost_price:.2f} 元
- 当前价: {snapshot.current_price or '未知'} 元
- 持仓市值: {snapshot.market_value or '未知'} 元
- 浮动盈亏: {snapshot.unrealized_pnl or 0:.2f} 元 ({snapshot.unrealized_pnl_pct or 0:.2f}%)
- 持仓天数: {snapshot.holding_days or '未知'} 天
- 当前状态: {pnl_status}

## 用户设置
- 目标收益率: {params.target_profit_pct}%
- 是否考虑加仓: {'是' if params.include_add_position else '否'}

## 分析要求
请从以下维度分析该持仓，用中文回答：

1. **研究结论倾向** (必须是以下之一: 乐观/审慎/中性，不得输出加仓/减仓/持有/清仓等交易指令)
2. **研究观察理由** (100字以内)
3. **置信度** (0-100分)
4. **风险关注价格** (具体价格，用于用户自行跟踪下行风险)
5. **收益关注价格** (具体价格，用于用户自行跟踪上行观察价位)
6. **风险审阅** (300-500字，需详细说明主要风险点、风险等级、风险影响等)
7. **机会评估** (300-500字，需详细说明潜在机会、催化剂、收益空间等，但不得给出买入/卖出建议)
8. **详细分析** (200字以内的完整分析)

请直接给出分析结果。整体输出仅供学习研究参考，不构成投资建议。"""

        return prompt

    def _build_position_analysis_prompt_v2(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest,
        stock_analysis_report: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> str:
        """Constructing special prompt words for position analysis - plan 2

        Based on complete single stock analysis report + Position information to generate personalized position research observations
        Support template system (controlled by USE_TEMPLATE_PROMPTS feature switch)
        """
        # Build a hardcoded version first as a fallback for downgrades
        legacy_prompt = self._build_legacy_position_prompt(snapshot, params, stock_analysis_report)

        # If the template system is enabled, try to use templates to generate prompt words
        if _use_template_prompts():
            try:
                from tradingagents.utils.template_client import get_agent_prompt

                variables = self._build_position_vars(snapshot, params, stock_analysis_report)

                prompt = get_agent_prompt(
                    agent_type="trader",
                    agent_name="position_advisor",
                    variables=variables,
                    user_id=user_id,
                    preference_id=params.invest_style or "neutral",
                    fallback_prompt=legacy_prompt
                )

                if prompt and prompt != legacy_prompt:
                    logger.info(f"✅ [Position analysis] Use template system to generate prompt words (length: {len(prompt)})")
                    return prompt

            except Exception as e:
                logger.warning(f"⚠️ [Position analysis] Template system call failed with hardcoded prompt word: {e}")

        return legacy_prompt

    def _build_legacy_position_prompt(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest,
        stock_analysis_report: Dict[str, Any]
    ) -> str:
        """Construct hard-coded position analysis prompt words (old version, as a cover for downgrade)"""
        pnl_status = "盈利" if (snapshot.unrealized_pnl or 0) >= 0 else "亏损"
        pnl_pct = snapshot.unrealized_pnl_pct or 0

        # Extract each analyst report
        reports = stock_analysis_report.get("reports", {})
        decision = stock_analysis_report.get("decision", {})
        summary = stock_analysis_report.get("summary", "")
        recommendation = stock_analysis_report.get("recommendation", "")

        # Build an analysis report summary
        market_report = reports.get("market_report", "")[:1500] if reports.get("market_report") else "暂无"
        fundamentals_report = reports.get("fundamentals_report", "")[:1500] if reports.get("fundamentals_report") else "暂无"
        news_report = reports.get("news_report", "")[:1000] if reports.get("news_report") else "暂无"

        # Extract research conclusion tendencies
        trade_action = decision.get("action", "未知") if decision else "未知"
        target_price = decision.get("target_price") if decision else None

        prompt = f"""# 持仓分析专家任务

你是一位专业的持仓研究助理，需要基于完整的股票分析报告和用户的持仓情况，给出个性化的持仓研究观察（非交易建议）。

## 📊 股票分析报告摘要

### 技术面分析
{market_report}

### 基本面分析
{fundamentals_report}

### 新闻面分析
{news_report}

### 综合研究
- 摘要: {summary or '暂无'}
- 研究结论倾向: {trade_action}
- 关键验证价位: {target_price or '未知'}
- 详细研究观察: {recommendation or '暂无'}

---

## 💼 用户持仓信息

| 项目 | 数值 |
|------|------|
| 股票代码 | {snapshot.code} |
| 股票名称 | {snapshot.name or '未知'} |
| 持仓数量 | {snapshot.quantity} 股 |
| 成本价 | {snapshot.cost_price:.2f} 元 |
| 当前价 | {snapshot.current_price or '未知'} 元 |
| 持仓市值 | {snapshot.market_value or '未知':.2f} 元 |
| 浮动盈亏 | {snapshot.unrealized_pnl or 0:.2f} 元 ({pnl_pct:.2f}%) |
| 持仓天数 | {snapshot.holding_days or '未知'} 天 |
| 当前状态 | {pnl_status} |
| 行业 | {snapshot.industry or '未知'} |

## 🎯 用户投资目标
- 目标收益率: {params.target_profit_pct}%
- 是否考虑加仓: {'是' if params.include_add_position else '否'}
{self._build_capital_info_section(snapshot, params)}

---

## 📝 分析要求

请综合以上股票分析报告和持仓信息，给出个性化的持仓研究观察（非交易建议）。

**重要考量因素**：
1. 当前盈亏状态：{pnl_status} {pnl_pct:.2f}%
2. 与目标收益率的差距：目标 {params.target_profit_pct}%，当前 {pnl_pct:.2f}%
3. 股票分析报告中的研究结论倾向：{trade_action}
4. 技术面、基本面、新闻面的综合判断

**请以JSON格式输出**：
```json
{{
    "action": "乐观|审慎|中性",
    "action_reason": "研究观察的核心理由，需要结合分析报告和持仓情况说明（100字以内）",
    "confidence": 0-100的整数,
    "stop_loss_price": 风险关注价格（数字，保留2位小数）,
    "take_profit_price": 收益关注价格（数字，保留2位小数）,
    "risk_assessment": "基于分析报告的详细风险审阅（300-500字，需包含主要风险点、风险等级、风险影响等）",
    "opportunity_assessment": "基于分析报告的详细机会评估（300-500字，需包含潜在机会、催化剂、收益空间等，但不得给出买入/卖出建议）",
    "detailed_analysis": "结合分析报告和持仓情况的详细分析（200字以内）",
    "suggested_quantity": 0,
    "suggested_amount": 0,
    "position_risk_analysis": "仓位风险分析（如提供了资金总量，分析仓位占比是否合理，50字以内，可选，但不得给出加仓/减仓建议）"
}}
```

**注意事项**：
- 风险关注价格应低于当前价，用于用户自行跟踪下行风险
- 收益关注价格应高于当前价，用于用户自行跟踪上行观察价位
- 所有价格保留2位小数
- 必须基于提供的分析报告进行判断，不要凭空编造信息
- 如果用户提供了资金总量，可在分析中说明仓位占比观察，但不得给出加仓/减仓/清仓等交易指令
- 整体输出仅供学习研究参考，不构成投资建议
"""

        return prompt

    def _build_capital_info_section(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest
    ) -> str:
        """构建资金信息部分的提示词"""
        if not params.total_capital or params.total_capital <= 0:
            return ""

        # Calculate various risk indicators
        market_value = snapshot.market_value or (snapshot.quantity * (snapshot.current_price or snapshot.cost_price))
        position_pct = (market_value / params.total_capital) * 100 if params.total_capital > 0 else 0

        # Calculate the maximum possible loss (assuming it falls to the stop loss line)
        stop_loss_pct = params.max_loss_pct  # Default 10%
        max_loss_amount = market_value * (stop_loss_pct / 100)
        max_loss_impact_pct = (max_loss_amount / params.total_capital) * 100

        # Calculate the amount that can be added (based on the maximum position limit)
        max_position_value = params.total_capital * (params.max_position_pct / 100)
        available_add_amount = max(0, max_position_value - market_value)

        # Determine risk level
        risk_level = "low"
        if position_pct > params.max_position_pct:
            risk_level = "critical"
        elif position_pct > params.max_position_pct * 0.8:
            risk_level = "high"
        elif position_pct > params.max_position_pct * 0.5:
            risk_level = "medium"

        section = f"""
## 💰 Fund and position analysis

| Project | numerical value | Description |
|------|------|------|
| Total amount of investment funds | {params.total_capital:,.0f} Yuan | The total investment funds set by the user |
| Current position market value | {market_value:,.2f} Yuan | The market value of the stock s holdings |
| Current position proportion | {position_pct:.2f}% | Proportion of total funds |
| Maximum position limit | {params.max_position_pct:.0f}% | Maximum position in a single stock |
| Position risk level | {risk_level} | low/medium/high/critical |

### Risk exposure analysis
- If the stock falls {stop_loss_pct:.0f}% (Stop loss line), maximum loss amount: {max_loss_amount:,.2f} Yuan
- The impact of maximum loss on total funds: {max_loss_impact_pct:.2f}%
- The maximum acceptable loss ratio for users: {params.max_loss_pct:.0f}%

### Analysis of space for adding positions
- Maximum allowed position market value: {max_position_value:,.0f} Yuan
- Currently occupied: {market_value:,.2f} Yuan
- The remaining amount that can be added to the position: {available_add_amount:,.0f} Yuan
- Remaining quantity that can be added (according to current price): {int(available_add_amount / (snapshot.current_price or snapshot.cost_price))} shares

**⚠️ Important reminder**: 
- The position risk level is **{risk_level}**
- {'The position has exceeded the limit! Recommended to reduce positions' if risk_level == 'critical' else 'The position is close to the upper limit, add positions cautiously' if risk_level == 'high' else 'The position is reasonable' if risk_level == 'medium' else 'The position is light and there is room to add more positions'}
"""
        return section

    def _build_position_vars(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest,
        stock_analysis_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build template variables (for use in template systems)

        According to the variable specification defined in the design document portfolio-trade-review-engine-integration.md
        """
        pnl_pct = snapshot.unrealized_pnl_pct or 0

        # Extract analysis report
        reports = stock_analysis_report.get("reports", {})
        decision = stock_analysis_report.get("decision", {})

        # Calculate position information
        market_value = snapshot.market_value or (snapshot.quantity * (snapshot.current_price or snapshot.cost_price))
        position_pct = 0.0
        position_risk_level = "unknown"

        if params.total_capital and params.total_capital > 0:
            position_pct = (market_value / params.total_capital) * 100
            if position_pct > params.max_position_pct:
                position_risk_level = "critical"
            elif position_pct > params.max_position_pct * 0.8:
                position_risk_level = "high"
            elif position_pct > params.max_position_pct * 0.5:
                position_risk_level = "medium"
            else:
                position_risk_level = "low"

        return {
            # Position information
            "position": {
                "code": snapshot.code,
                "name": snapshot.name or "未知",
                "quantity": snapshot.quantity,
                "cost_price": f"{snapshot.cost_price:.2f}",
                "current_price": f"{snapshot.current_price:.2f}" if snapshot.current_price else "未知",
                "market_value": f"{market_value:.2f}",
                "holding_days": snapshot.holding_days or "未知",
                "unrealized_pnl": f"{snapshot.unrealized_pnl or 0:.2f}",
                "unrealized_pnl_pct": f"{pnl_pct:.2f}",
                "industry": snapshot.industry or "未知"
            },

            # Accounts and positions
            "capital": {
                "total_assets": f"{params.total_capital:,.0f}" if params.total_capital else "未提供",
                "position_pct": f"{position_pct:.2f}",
                "position_risk_level": position_risk_level,
                "max_position_pct": f"{params.max_position_pct:.0f}"
            },

            # User settings
            "goal": {
                "target_profit_pct": f"{params.target_profit_pct}",
                "max_loss_pct": f"{params.max_loss_pct}",
                "include_add_position": "是" if params.include_add_position else "否"
            },

            # Single stock analysis report
            "engine": {
                "market_report": (reports.get("market_report", "") or "暂无")[:1500],
                "fundamentals_report": (reports.get("fundamentals_report", "") or "暂无")[:1500],
                "news_report": (reports.get("news_report", "") or "暂无")[:1000],
                "sentiment_report": (reports.get("sentiment_report", "") or "暂无")[:500],
                "sector_report": (reports.get("sector_report", "") or "暂无")[:500],
                "final_decision": {
                    "action": decision.get("action", "未知") if decision else "未知",
                    "target_price": str(decision.get("target_price", "未知")) if decision else "未知",
                    "reason": decision.get("reason", stock_analysis_report.get("recommendation", "暂无"))[:500]
                }
            },

            # context
            "context": {
                "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                "user_style": params.invest_style or "neutral"
            }
        }

    def _parse_position_ai_response_v2(
        self,
        content: str,
        snapshot: PositionSnapshot
    ) -> PositionAnalysisResult:
        """Analyzing Position AI Response - Solution 2 (Enhanced JSON parsing)"""
        import re
        import json

        # Try to extract JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))

                # Analyze the tendency of research conclusions (compatible with the old version of operational advice terminology)
                action_str = data.get("action", "中性")
                action = PositionAction.HOLD
                if any(k in action_str for k in ["乐观", "加仓", "买入"]):
                    action = PositionAction.ADD
                elif any(k in action_str for k in ["审慎", "减仓", "卖出", "清仓"]):
                    action = PositionAction.REDUCE
                elif "中性" in action_str or "持有" in action_str:
                    action = PositionAction.HOLD

                # Construct price target
                price_targets = PriceTarget(
                    stop_loss_price=float(data.get("stop_loss_price", 0)) if data.get("stop_loss_price") else None,
                    take_profit_price=float(data.get("take_profit_price", 0)) if data.get("take_profit_price") else None,
                    breakeven_price=snapshot.cost_price
                )

                # Calculate percentage
                if price_targets.stop_loss_price and snapshot.cost_price > 0:
                    price_targets.stop_loss_pct = round((price_targets.stop_loss_price - snapshot.cost_price) / snapshot.cost_price * 100, 2)
                if price_targets.take_profit_price and snapshot.cost_price > 0:
                    price_targets.take_profit_pct = round((price_targets.take_profit_price - snapshot.cost_price) / snapshot.cost_price * 100, 2)

                # Parse recommended quantities and amounts
                suggested_quantity = None
                suggested_amount = None
                if data.get("suggested_quantity"):
                    try:
                        suggested_quantity = int(data["suggested_quantity"])
                    except (ValueError, TypeError):
                        pass
                if data.get("suggested_amount"):
                    try:
                        suggested_amount = float(data["suggested_amount"])
                    except (ValueError, TypeError):
                        pass

                # Construct risk metrics (if total funding is provided)
                risk_metrics = None
                if snapshot.total_capital and snapshot.total_capital > 0:
                    risk_metrics = self._calculate_risk_metrics(snapshot, price_targets)

                return PositionAnalysisResult(
                    action=action,
                    action_reason=data.get("action_reason", "基于综合分析给出建议"),
                    confidence=float(data.get("confidence", 50)),
                    price_targets=price_targets,
                    risk_assessment=data.get("risk_assessment", "请关注市场风险"),
                    opportunity_assessment=data.get("opportunity_assessment", "请关注市场机会"),
                    detailed_analysis=data.get("detailed_analysis", content[:500]),
                    suggested_quantity=suggested_quantity,
                    suggested_amount=suggested_amount,
                    risk_metrics=risk_metrics
                )
            except json.JSONDecodeError:
                logger.warning("JSON Parsing failed, use alternate parsing method")

        # Alternate parsing method (similar to the original method)
        return self._parse_position_ai_response(content, snapshot)

    def _parse_position_ai_response(
        self,
        content: str,
        snapshot: PositionSnapshot
    ) -> PositionAnalysisResult:
        """解析单股持仓AI响应"""
        # Determine the tendency of research conclusions (compatible with the old version of operational advice terminology)
        action = PositionAction.HOLD
        if any(k in content for k in ["乐观", "加仓", "买入"]):
            action = PositionAction.ADD
        elif any(k in content for k in ["审慎", "减仓", "卖出", "清仓"]):
            action = PositionAction.REDUCE
        elif "中性" in content or "持有" in content:
            action = PositionAction.HOLD

        # Extract confidence
        confidence = 50.0
        import re
        conf_match = re.search(r'Confidence[: :]\s*(\d+)', content)
        if conf_match:
            confidence = float(conf_match.group(1))

        # Extract risk focus/income focus price (compatible with old stop loss/take profit expressions)
        price_targets = PriceTarget()
        stop_loss_match = re.search(r'(risk focus price|Stop loss price)[: :]\s*(\d+\.?\d*)', content)
        if stop_loss_match:
            price_targets.stop_loss_price = float(stop_loss_match.group(2))
            if snapshot.cost_price > 0:
                price_targets.stop_loss_pct = round((price_targets.stop_loss_price - snapshot.cost_price) / snapshot.cost_price * 100, 2)

        take_profit_match = re.search(r'(Earnings focus on price|Take profit price)[: :]\s*(\d+\.?\d*)', content)
        if take_profit_match:
            price_targets.take_profit_price = float(take_profit_match.group(2))
            if snapshot.cost_price > 0:
                price_targets.take_profit_pct = round((price_targets.take_profit_price - snapshot.cost_price) / snapshot.cost_price * 100, 2)

        price_targets.breakeven_price = snapshot.cost_price

        # Extract the content of each part
        reason = ""
        risk = ""
        opportunity = ""

        lines = content.split('\n')
        current_section = None
        for line in lines:
            line = line.strip()
            if "建议理由" in line or "理由" in line:
                current_section = "reason"
            elif "风险评估" in line:
                current_section = "risk"
            elif "机会评估" in line:
                current_section = "opportunity"
            elif line and current_section:
                if current_section == "reason" and len(reason) < 100:
                    reason += line + " "
                elif current_section == "risk" and len(risk) < 100:
                    risk += line + " "
                elif current_section == "opportunity" and len(opportunity) < 100:
                    opportunity += line + " "

        return PositionAnalysisResult(
            action=action,
            action_reason=reason.strip() or "基于综合分析给出建议",
            confidence=confidence,
            price_targets=price_targets,
            risk_assessment=risk.strip() or "请关注市场风险",
            opportunity_assessment=opportunity.strip() or "请关注市场机会",
            detailed_analysis=content[:500]
        )

    def _calculate_risk_metrics(
        self,
        snapshot: PositionSnapshot,
        price_targets: PriceTarget
    ) -> PositionRiskMetrics:
        """计算持仓风险指标"""
        if not snapshot.total_capital or snapshot.total_capital <= 0:
            return PositionRiskMetrics()

        total_capital = snapshot.total_capital
        market_value = snapshot.market_value or (snapshot.quantity * (snapshot.current_price or snapshot.cost_price))
        position_pct = (market_value / total_capital) * 100 if total_capital > 0 else 0

        # Calculate maximum possible loss (use Risk Focus Price or default 10%)
        stop_loss_pct = 10.0  # Default 10%
        if price_targets.stop_loss_pct:
            stop_loss_pct = abs(price_targets.stop_loss_pct)
        max_loss_amount = market_value * (stop_loss_pct / 100)
        max_loss_impact_pct = (max_loss_amount / total_capital) * 100

        # Calculate the amount that can be added (assuming the maximum position is 30%)
        max_position_pct = 30.0
        max_position_value = total_capital * (max_position_pct / 100)
        available_add_amount = max(0, max_position_value - market_value)

        # Determine risk level
        if position_pct > max_position_pct:
            risk_level = "critical"
            risk_summary = f"仓位{position_pct:.1f}%已超出上限{max_position_pct:.0f}%，建议减仓"
        elif position_pct > max_position_pct * 0.8:
            risk_level = "high"
            risk_summary = f"仓位{position_pct:.1f}%接近上限，谨慎加仓"
        elif position_pct > max_position_pct * 0.5:
            risk_level = "medium"
            risk_summary = f"仓位{position_pct:.1f}%适中，可适度加仓"
        else:
            risk_level = "low"
            risk_summary = f"仓位{position_pct:.1f}%较轻，有较大加仓空间"

        return PositionRiskMetrics(
            position_pct=round(position_pct, 2),
            position_value=round(market_value, 2),
            max_loss_amount=round(max_loss_amount, 2),
            max_loss_impact_pct=round(max_loss_impact_pct, 2),
            available_add_amount=round(available_add_amount, 2),
            risk_level=risk_level,
            risk_summary=risk_summary
        )

    async def get_position_analysis_history(
        self,
        user_id: str,
        position_id: str,
        page: int = 1,
        page_size: int = 10,
        position_type: str = "real"
    ) -> Dict[str, Any]:
        """Get single stock analysis history
        
        Args:
            user_id: User ID
            position_id: Position ID (format: code_market)
            page: Page number
            page_size: page size
            position_type: Position type (real/simulated)
        """
        skip = (page - 1) * page_size

        # 🔥 Add filter criteria based on position_type
        query = {
            "user_id": user_id,
            "position_id": position_id,
            "position_type": position_type  # Add position_type filter
        }

        cursor = self.db[self.position_analysis_collection].find(query).sort("created_at", -1).skip(skip).limit(page_size)

        items = await cursor.to_list(None)
        total = await self.db[self.position_analysis_collection].count_documents(query)

        # Format data: Extract all fields in ai_analysis to the top level to facilitate front-end use
        formatted_items = []
        for item in items:
            formatted_item = dict(item)
            
            # 🔥 Extract the position_type field (used to distinguish simulated positions and user positions)
            formatted_item["position_type"] = item.get("position_type", "real")
            
            # Extract all fields in ai_analysis to the top level
            ai_analysis = item.get("ai_analysis", {})
            if ai_analysis:
                # Extract action (may be an enumeration type and needs to be converted to a string)
                action_value = ai_analysis.get("action")
                if action_value:
                    # If it is an enumeration type, get its value
                    if hasattr(action_value, "value"):
                        formatted_item["action"] = action_value.value
                    elif isinstance(action_value, str):
                        formatted_item["action"] = action_value
                    else:
                        formatted_item["action"] = str(action_value)
                else:
                    formatted_item["action"] = None
                
                # Extract other fields
                formatted_item["confidence"] = ai_analysis.get("confidence")
                formatted_item["action_reason"] = ai_analysis.get("action_reason", "")
                formatted_item["risk_assessment"] = ai_analysis.get("risk_assessment", "")
                formatted_item["opportunity_assessment"] = ai_analysis.get("opportunity_assessment", "")
                formatted_item["detailed_analysis"] = ai_analysis.get("detailed_analysis", "")
                
                # Extract price_targets if present
                price_targets = ai_analysis.get("price_targets")
                if price_targets:
                    # If it is a dictionary, use it directly; if it is an object, convert it to a dictionary.
                    if isinstance(price_targets, dict):
                        formatted_item["price_targets"] = price_targets
                    elif hasattr(price_targets, "model_dump"):
                        formatted_item["price_targets"] = price_targets.model_dump()
                    elif hasattr(price_targets, "dict"):
                        formatted_item["price_targets"] = price_targets.dict()
                    else:
                        formatted_item["price_targets"] = None
                else:
                    formatted_item["price_targets"] = None
                
                # Extract other optional fields
                formatted_item["suggested_quantity"] = ai_analysis.get("suggested_quantity")
                formatted_item["suggested_amount"] = ai_analysis.get("suggested_amount")
                formatted_item["risk_metrics"] = ai_analysis.get("risk_metrics")
                formatted_item["summary"] = ai_analysis.get("summary", "")
                formatted_item["recommendation"] = ai_analysis.get("recommendation", "")
            else:
                # If there is no ai_analysis, set the default value
                formatted_item["action"] = None
                formatted_item["confidence"] = None
                formatted_item["action_reason"] = ""
                formatted_item["risk_assessment"] = ""
                formatted_item["opportunity_assessment"] = ""
                formatted_item["detailed_analysis"] = ""
                formatted_item["price_targets"] = None
            
            # Keep the position information in position_snapshot to facilitate front-end display
            position_snapshot = item.get("position_snapshot")
            if position_snapshot:
                # Directly retain the complete position_snapshot object
                formatted_item["position_snapshot"] = position_snapshot
                
                # At the same time, extract common fields to the top level (for list display)
                formatted_item["quantity"] = position_snapshot.get("quantity", 0)
                formatted_item["cost_price"] = position_snapshot.get("cost_price", 0.0)
                formatted_item["current_price"] = position_snapshot.get("current_price", 0.0)
                
                # Calculate floating profit and loss (if not present in position_snapshot)
                if "unrealized_pnl" not in position_snapshot:
                    if formatted_item.get("quantity") and formatted_item.get("cost_price") and formatted_item.get("current_price"):
                        quantity = formatted_item["quantity"]
                        cost_price = formatted_item["cost_price"]
                        current_price = formatted_item["current_price"]
                        floating_pnl = (current_price - cost_price) * quantity
                        floating_pnl_pct = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 else 0.0
                        formatted_item["floating_pnl"] = floating_pnl
                        formatted_item["floating_pnl_pct"] = floating_pnl_pct
                else:
                    formatted_item["floating_pnl"] = position_snapshot.get("unrealized_pnl", 0.0)
                    formatted_item["floating_pnl_pct"] = position_snapshot.get("unrealized_pnl_pct", 0.0)
            
            formatted_items.append(formatted_item)

        return {
            "items": formatted_items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    # ==================== Workflow engine integration ====================

    async def _call_position_ai_analysis_workflow(
        self,
        snapshot: PositionSnapshot,
        params: PositionAnalysisRequest,
        stock_analysis_report: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> PositionAnalysisResult:
        """Position analysis using workflow engine

        Use the position analysis workflow, which includes:
        1. Position Technical Analyst - Analyze technical indicators and trends
        2. Position Fundamental Analyst - Analyze financial data and valuations
        3. Position Risk Assessor - Assess risks and give risk concern price references
        4. Position Research Observer - Comprehensive analysis gives position research observations
        """
        try:
            from core.api.workflow_api import WorkflowAPI

            # Prepare single stock analysis report data (the field name used in agents is stock_analysis_report)
            # If there is a cache, you need to set the has_cache flag and extract the reports sub-report
            stock_analysis_report_for_workflow = {}
            if stock_analysis_report and stock_analysis_report.get("reports"):
                # Has cache: set flag and pull report
                stock_analysis_report_for_workflow = {
                    "has_cache": True,
                    "reports": stock_analysis_report.get("reports", {}),
                    "task_id": stock_analysis_report.get("task_id"),
                    "source": stock_analysis_report.get("source", "cached")
                }
                logger.info(f"📊 [工作流持仓分析] 传递缓存报告到工作流: {snapshot.code}, reports字段: {list(stock_analysis_report_for_workflow.get('reports', {}).keys())}")
            else:
                # No cache: Set flag to empty
                stock_analysis_report_for_workflow = {
                    "has_cache": False,
                    "reports": {},
                    "task_id": None,
                    "source": "none"
                }
                logger.info(f"📊 [Workflow position analysis] No cached report, passing empty structure to workflow: {snapshot.code}")
            
            # Prepare workflow input data
            workflow_inputs = {
                # Basic information of positions
                "position_info": {
                    "code": snapshot.code,
                    "name": snapshot.name,
                    "market": snapshot.market,
                    "industry": snapshot.industry,
                    "quantity": snapshot.quantity,
                    "cost_price": snapshot.cost_price,
                    "current_price": snapshot.current_price,
                    "market_value": snapshot.market_value,
                    "unrealized_pnl": snapshot.unrealized_pnl,
                    "unrealized_pnl_pct": snapshot.unrealized_pnl_pct,
                    "holding_days": snapshot.holding_days,
                    "position_pct": snapshot.position_pct,
                    "total_capital": snapshot.total_capital
                },

                # Analyze target stocks: top-level ticker field (workflow agents rely on ticker to locate stocks, missing will be reported
                # "Missing required parameters: ticker") ; Also complete the symbol/company_of_interest compatible alias
                "ticker": snapshot.code,
                "symbol": snapshot.code,
                "company_of_interest": snapshot.code,

                # Analysis parameters
                "analysis_params": {
                    "research_depth": params.research_depth,
                    "include_add_position": params.include_add_position,
                    "target_profit_pct": params.target_profit_pct,
                    "total_capital": params.total_capital,
                    "max_position_pct": params.max_position_pct,
                    "max_loss_pct": params.max_loss_pct,
                    "risk_tolerance": params.risk_tolerance,
                    "investment_horizon": params.investment_horizon,
                    "analysis_focus": params.analysis_focus,
                    "position_type": params.position_type
                },

                # Single stock analysis report (the field name used in agents is stock_analysis_report)
                "stock_analysis_report": stock_analysis_report_for_workflow,

                # User preferences (used to select prompt word template style)
                "user_preference": self._get_user_analysis_preference(user_id, params.risk_tolerance),

                # Position type identifier
                "position_type": params.position_type
            }

            logger.info(f"🚀 [Workflow position analysis] Start executing the position analysis workflow - {snapshot.code}")

            # 🔥 Get the model configuration from the database and build legacy_config (consistent with the single-strand analysis process)
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
                        logger.info(f"📊 [Workflow position analysis] Get full model configuration from database: quick={quick_analysis_model}, deep={deep_analysis_model}")
                        logger.info(f"  quick: temperature={legacy_config.get('quick_temperature')}, max_tokens={legacy_config.get('quick_max_tokens')}, timeout={legacy_config.get('quick_timeout')}")
                        logger.info(f"  deep: temperature={legacy_config.get('deep_temperature')}, max_tokens={legacy_config.get('deep_max_tokens')}, timeout={legacy_config.get('deep_timeout')}")
                    else:
                        # If retrieval fails, at least set the model name
                        legacy_config["quick_think_llm"] = quick_analysis_model
                        legacy_config["deep_think_llm"] = deep_analysis_model
                        legacy_config["llm_provider"] = "dashscope"
                        logger.warning(f"⚠️ [Workflow position analysis] Unable to get full model configuration, only set model name")
                else:
                    logger.warning(f"⚠️ [Workflow position analysis] system_settings quick_analysis_model or deep_analysis_model not found, use default configuration")
                    # If not configured, use default value
                    legacy_config["quick_think_llm"] = quick_analysis_model or "qwen-turbo"
                    legacy_config["deep_think_llm"] = deep_analysis_model or "qwen-plus"
                    legacy_config["llm_provider"] = "dashscope"
            except Exception as e:
                logger.error(f"❌ [Workflow position analysis] Failed to get model configuration from database: {e}", exc_info=True)
                # Use default configuration on failure
                legacy_config["quick_think_llm"] = "qwen-turbo"
                legacy_config["deep_think_llm"] = "qwen-plus"
                legacy_config["llm_provider"] = "dashscope"

            # Execute workflow (Note:WorkflowAPI.execute() It is a synchronous method and does not require await)
            from core.workflow.default_workflow_provider import get_default_workflow_provider
            workflow_id = get_default_workflow_provider().get_active_workflow_id("position_analysis")
            workflow_api = WorkflowAPI()
            result = workflow_api.execute(
                workflow_id=workflow_id,
                inputs=workflow_inputs,
                legacy_config=legacy_config if legacy_config else None  # 🔥 Pass model configuration
            )

            if not result.get("success"):
                error_msg = result.get("error", "工作流执行失败")
                logger.error(f"❌ [Workflow position analysis] Execution failed: {error_msg}")
                return PositionAnalysisResult(
                    action=PositionAction.HOLD,
                    action_reason=f"分析失败: {error_msg}"
                )

            # Parse workflow results
            workflow_result = result.get("result", {})

            # Extract results for individual analysts (handling possible dictionary cases)
            def extract_content(value):
                """Safely extract content, handling possible dictionary cases"""
                if isinstance(value, dict):
                    return value.get("content", value.get("error", str(value)))
                elif isinstance(value, str):
                    return value
                else:
                    return str(value) if value else ""

            technical_analysis = extract_content(workflow_result.get("technical_analysis", ""))
            fundamental_analysis = extract_content(workflow_result.get("fundamental_analysis", ""))
            risk_analysis = extract_content(workflow_result.get("risk_analysis", ""))
            
            # action_advice May be a string (JSON) or a dictionary (containing the content field)
            action_advice_raw = workflow_result.get("action_advice", "")
            logger.info(f"📊 [Workflow position analysis] action_advice_raw Type: {type(action_advice_raw)}")
            
            # Use extract_content to extract the content field (regardless of the original format)
            action_advice = extract_content(action_advice_raw)
            logger.info(f"📊 [工作流持仓分析] action_advice提取后类型: {type(action_advice)}, 长度: {len(str(action_advice))}")

            logger.info(f"✅ [Workflow position analysis] Analysis completed - {snapshot.code}")

            # Initialize default value
            from app.models.portfolio import PriceTarget
            action = PositionAction.HOLD
            action_reason = ""
            confidence = 0.0
            price_targets = PriceTarget()
            risk_assessment_text = risk_analysis  # Risk assessment using workflow by default
            opportunity_assessment_text = ""
            
            # Extract research conclusions and rationales from research observations
            # If action_advice is in JSON format, first convert it to Markdown
            import json
            advice_json = None
            logger.info(f"📊 [工作流持仓分析] 开始解析action_advice，类型: {type(action_advice)}, 长度: {len(action_advice) if action_advice else 0}")
            
            # Try parsing JSON (action_advice should be a string)
            if action_advice and isinstance(action_advice, str) and ("```json" in action_advice or action_advice.strip().startswith("{")):
                try:
                    # Extract JSON
                    if "```json" in action_advice:
                        json_start = action_advice.find("```json") + 7
                        json_end = action_advice.find("```", json_start)
                        if json_end > json_start:
                            json_str = action_advice[json_start:json_end].strip()
                            logger.info(f"📊 [Workflow position analysis] Extract JSON from code block, length: {len(json_str)}")
                            advice_json = json.loads(json_str)
                    elif action_advice.strip().startswith("{"):
                        logger.info(f"📊 [Workflow position analysis] Directly parse JSON format")
                        advice_json = json.loads(action_advice)
                except Exception as e:
                    logger.warning(f"⚠️ [Workflow position analysis] JSON Parsing failed: {e}")
                    advice_json = None
            
            # Convert to Markdown format and extract other fields (whether action_advice is a dictionary or a parsed JSON string)
            if advice_json:
                logger.info(f"📊 [Workflow position analysis] JSON Parsed successfully, field: {list(advice_json.keys())}")
                action_reason = self._convert_action_advice_json_to_markdown(advice_json)
                logger.info(f"📊 [Workflow position analysis] JSON Conversion to Markdown successful, length: {len(action_reason)}")
                # Extract from JSON action
                action = self._extract_action_from_json(advice_json)
                logger.info(f"📊 [Workflow position analysis] extracted action: {action}")
                # Extract other fields
                # Confidence may be in multiple locations
                confidence = None
                if "confidence" in advice_json:
                    confidence = advice_json.get("confidence")
                elif "neutral_operation_advice" in advice_json:
                    neutral = advice_json["neutral_operation_advice"]
                    if isinstance(neutral, dict):
                        confidence = neutral.get("confidence")
                elif "neutral_operation_suggestion" in advice_json:
                    neutral = advice_json["neutral_operation_suggestion"]
                    if isinstance(neutral, dict):
                        confidence = neutral.get("confidence")
                
                if confidence is not None:
                    try:
                        confidence = float(confidence)
                        # Make sure the confidence level is in the range 0-100
                        confidence = max(0.0, min(100.0, confidence))
                    except (ValueError, TypeError):
                        confidence = 50.0  # Default value
                        logger.warning(f"⚠️ [Workflow position analysis] confidence Conversion failed, using default value 50")
                else:
                    # If AI does not generate confidence, set a reasonable default based on analysis quality
                    confidence = 50.0  # Default medium confidence
                    logger.info(f"📊 [Workflow position analysis] JSON There is no confidence field in, use the default value 50")
                
                logger.info(f"📊 [Workflow position analysis] extracted confidence: {confidence}")
                price_targets = self._extract_price_targets_from_json(advice_json, snapshot, params)
                logger.info(f"📊 [Workflow position analysis] extracted price_targets: stop_loss={price_targets.stop_loss_price}, take_profit={price_targets.take_profit_price}, breakeven={price_targets.breakeven_price}")
                risk_assessment_text = advice_json.get("risk_assessment", "") or risk_analysis
                logger.info(f"📊 [Workflow position analysis] Extracted risk_assessment length: {len(risk_assessment_text)}")
                opportunity_assessment_text = advice_json.get("opportunity_assessment", "")
                logger.info(f"📊 [Workflow position analysis] Extracted opportunity_assessment length: {len(opportunity_assessment_text)}")
            else:
                logger.warning(f"⚠️ [Workflow position analysis] advice_json If empty, use text parsing")
                action, action_reason = self._parse_workflow_action_advice(action_advice if isinstance(action_advice, str) else str(action_advice))

            # Build complete analysis results
            # NOTE: Use converted action_reason (Markdown format) instead of original action_advice (probably JSON)
            action_advice_for_summary = action_reason if action_reason else action_advice
            logger.info(f"📊 [Workflow position analysis] build analysis_summary: Use converted action_reason(length: {len(action_advice_for_summary)}) ")
            
            # analysis_summary Include everything (for summary field)
            analysis_summary = f"""
【技术面分析】
{technical_analysis}

【基本面分析】
{fundamental_analysis}

【风险评估】
{risk_analysis}

【研究观察】
{action_advice_for_summary}
            """.strip()
            
            # detailed_analysis Contains only technical aspects, fundamentals and risk assessment, and does not include research observations (to avoid duplication with action_reason)
            detailed_analysis = f"""
【技术面分析】
{technical_analysis}

【基本面分析】
{fundamental_analysis}

【风险评估】
{risk_analysis}
            """.strip()
            
            logger.info(f"📊 [Workflow position analysis] analysis_summary length: {len(analysis_summary)}, detailed_analysis length: {len(detailed_analysis)}")
            
            # Make sure detailed_analysis is not empty
            if not detailed_analysis:
                logger.warning(f"⚠️ [Workflow position analysis] detailed_analysis Empty, use default content")
                detailed_analysis = f"【技术面分析】\n{technical_analysis}\n\n【基本面分析】\n{fundamental_analysis}\n\n【风险评估】\n{risk_analysis}".strip()

            logger.info(f"📊 [Workflow position analysis] Build analysis results: action={action}, risk_assessment length={len(risk_assessment_text)}, detailed_analysis length={len(detailed_analysis)}")
            
            # recommendation Fields should also be in converted Markdown format (consistent with action_reason)
            # If action_reason has been converted, use it directly; otherwise use the original action_advice (but must be a string)
            if action_reason and isinstance(action_reason, str) and action_reason:
                recommendation_markdown = action_reason
            elif isinstance(action_advice, str):
                recommendation_markdown = action_advice
            else:
                # If action_advice is a dictionary, use the converted action_reason, or the empty string
                recommendation_markdown = action_reason if isinstance(action_reason, str) else ""
            
            # Make sure recommendation_markdown is a string
            if not isinstance(recommendation_markdown, str):
                logger.warning(f"⚠️ [Workflow position analysis] recommendation Not a string, type: {type(recommendation_markdown)}, Convert to string")
                recommendation_markdown = str(recommendation_markdown) if recommendation_markdown else ""
            
            logger.info(f"📊 [Workflow position analysis] recommendation Field: Using converted Markdown, length: {len(recommendation_markdown)}")

            # Build user version display content (user_view): Extract from the JSON returned by LLM for direct display on the front-end main interface
            user_view = PositionUserView()
            raw_user_view = advice_json.get("user_view") if advice_json else None
            if isinstance(raw_user_view, dict):
                user_view.conclusion = str(raw_user_view.get("conclusion") or "").strip()
                user_view.position_context = str(raw_user_view.get("position_context") or "").strip()
                user_view.uncertainty_note = str(raw_user_view.get("uncertainty_note") or "").strip()
                for field, key in (
                    ("key_points", "key_points"),
                    ("risk_focus", "risk_focus"),
                    ("watch_items", "watch_items"),
                ):
                    raw_items = raw_user_view.get(key) or []
                    if isinstance(raw_items, str):
                        raw_items = [raw_items]
                    cleaned_items: List[str] = []
                    if isinstance(raw_items, list):
                        for item in raw_items:
                            text = str(item or "").strip()
                            if text and text not in cleaned_items:
                                cleaned_items.append(text)
                    setattr(user_view, field, cleaned_items[:3])

            # ===== Bottom line: If LLM does not generate compliant user_view list fields, downgrade and extract them from fields such as neutral_operation_advice / specific_plan =====
            # Make sure that the three cards "Core Basis/Risk Warning/Follow-up Observation Points" have at least content to display.
            def _to_clean_list(value, limit=3):
                if not value:
                    return []
                if isinstance(value, str):
                    value = [s.strip() for s in re.split(r'[；;。\n]', value) if s.strip()]
                if isinstance(value, list):
                    result = []
                    for item in value:
                        text = str(item or "").strip()
                        if text and text not in result:
                            result.append(text)
                    return result[:limit]
                return []

            neutral_advice = advice_json.get("neutral_operation_advice") if advice_json else None
            specific_plan = advice_json.get("specific_plan") if advice_json else None
            if isinstance(neutral_advice, dict):
                # Core basis: Reasoning is used first, followed by core_judgment
                if not user_view.key_points:
                    reasoning = neutral_advice.get("reasoning") or []
                    core_judgment = neutral_advice.get("core_judgment") or ""
                    merged = _to_clean_list(reasoning, 3)
                    if not merged and core_judgment:
                        merged = [core_judgment]
                    user_view.key_points = merged

                # Risk reminder: Prioritize using risk_reminder (string), split display
                if not user_view.risk_focus:
                    risk_reminder = neutral_advice.get("risk_reminder") or ""
                    if risk_reminder:
                        user_view.risk_focus = _to_clean_list(risk_reminder, 3)

                # Follow-up observation points: use analysis_points first, followed by specific_plan.observation_factors / immediate_step
                if not user_view.watch_items:
                    analysis_points = neutral_advice.get("analysis_points") or []
                    obs_factors = (specific_plan.get("observation_factors") or []) if isinstance(specific_plan, dict) else []
                    immediate_step = (specific_plan.get("immediate_step") or "") if isinstance(specific_plan, dict) else ""
                    merged = _to_clean_list(analysis_points, 3)
                    if not merged:
                        merged = _to_clean_list(obs_factors, 3)
                    if not merged and immediate_step:
                        merged = [immediate_step]
                    user_view.watch_items = merged

            # Conclusion: If conclusion is empty, use recommendation_markdown / action_reason instead
            if not user_view.conclusion:
                if recommendation_markdown:
                    user_view.conclusion = recommendation_markdown
                elif action_reason:
                    user_view.conclusion = action_reason

            logger.info(
                f"📊 [工作流持仓分析] 构建user_view: conclusion={user_view.conclusion[:40]}, "
                f"key_points={len(user_view.key_points)}Article, risk_focus={len(user_view.risk_focus)}Article, watch_items={len(user_view.watch_items)}Article"
            )

            return PositionAnalysisResult(
                action=action,
                action_reason=action_reason,
                confidence=confidence,
                price_targets=price_targets,
                risk_assessment=risk_assessment_text,
                opportunity_assessment=opportunity_assessment_text,
                detailed_analysis=detailed_analysis,
                summary=analysis_summary,
                recommendation=recommendation_markdown,
                user_view=user_view,
                source="workflow_engine_v2"
            )

        except Exception as e:
            logger.error(f"❌ [Workflow position analysis] Execution exception: {e}", exc_info=True)
            # Convert technical/English error messages into user-friendly Chinese prompts
            error_msg = _format_user_friendly_error(str(e))
            return PositionAnalysisResult(
                action=PositionAction.HOLD,
                action_reason=error_msg,
                error_message=error_msg
            )

    def _get_user_analysis_preference(self, user_id: Optional[str], risk_tolerance: str) -> str:
        """Determine analysis style based on user ID and risk appetite

        Returns:
            str: 'aggressive', 'neutral', 'conservative'
        """
        # Mapping to analysis style based on risk appetite
        risk_to_preference = {
            "low": "conservative",      # low risk -> Conservative
            "medium": "neutral",        # medium risk -> neutral type
            "high": "aggressive"        # high risk -> Radical
        }

        return risk_to_preference.get(risk_tolerance, "neutral")

    def _convert_action_advice_json_to_markdown(self, advice_json: Dict[str, Any]) -> str:
        """Convert JSON-formatted research observations to Markdown-formatted text
        
        Args:
            advice_json: JSON object for research observations
            
        Returns:
            Markdown Formatted Research Observation Text
        """
        lines = []
        
        # 1. Analysis summary (if available)
        if "analysis_summary" in advice_json:
            summary = advice_json["analysis_summary"]
            if isinstance(summary, str) and summary:
                lines.append(f"## 📊 分析摘要\n\n{summary}\n")
            elif isinstance(summary, dict):
                overall_view = summary.get("overall_view", summary.get("overall_assessment", ""))
                if overall_view:
                    lines.append(f"## 📊 分析摘要\n\n{overall_view}\n")
                key_points = summary.get("key_points", [])
                if isinstance(key_points, list) and key_points:
                    lines.append("\n**Key points**: \n\n")
                    for point in key_points:
                        if point:
                            lines.append(f"- {point}\n")
        
        # 2. Comprehensive assessment (if any)
        if "comprehensive_assessment" in advice_json:
            assessment = advice_json["comprehensive_assessment"]
            if isinstance(assessment, dict):
                lines.append("\n## 🔍 综合评估\n\n")
                
                # Position status
                if "position_status" in assessment:
                    pos_status = assessment["position_status"]
                    if isinstance(pos_status, dict):
                        lines.append("### 📈 持仓状态\n\n")
                        current_price = pos_status.get("current_price", "")
                        cost_price = pos_status.get("cost_price", "")
                        floating_loss_ratio = pos_status.get("floating_loss_ratio", "")
                        assessment_text = pos_status.get("assessment", "")
                        if current_price or cost_price or floating_loss_ratio:
                            lines.append(f"- **current price**: ¥{current_price}\n")
                            lines.append(f"- **cost price**: ¥{cost_price}\n")
                            lines.append(f"- **浮动盈亏**: {floating_loss_ratio}\n")
                        if assessment_text:
                            lines.append(f"\n{assessment_text}\n")
                
                # technical perspective
                if "technical_perspective" in assessment:
                    tech = assessment["technical_perspective"]
                    if isinstance(tech, dict):
                        lines.append("\n### 📊 技术面视角\n\n")
                        trend = tech.get("trend", "")
                        momentum = tech.get("momentum", "")
                        neutral_view = tech.get("neutral_view", "")
                        if trend:
                            lines.append(f"**趋势判断**: {trend}\n\n")
                        if momentum:
                            lines.append(f"**动能分析**: {momentum}\n\n")
                        if neutral_view:
                            lines.append(f"**中性观点**: {neutral_view}\n\n")
                
                # fundamental perspective
                if "fundamental_perspective" in assessment:
                    fund = assessment["fundamental_perspective"]
                    if isinstance(fund, dict):
                        lines.append("\n### 💼 基本面视角\n\n")
                        strengths = fund.get("strengths", "")
                        challenges = fund.get("challenges", "")
                        neutral_view = fund.get("neutral_view", "")
                        if strengths:
                            lines.append(f"**优势**: {strengths}\n\n")
                        if challenges:
                            lines.append(f"**挑战**: {challenges}\n\n")
                        if neutral_view:
                            lines.append(f"**中性观点**: {neutral_view}\n\n")
                
                # risk perspective
                if "risk_perspective" in assessment:
                    risk = assessment["risk_perspective"]
                    if isinstance(risk, dict):
                        lines.append("\n### ⚠️ 风险视角\n\n")
                        volatility = risk.get("volatility", "")
                        key_risk_factors = risk.get("key_risk_factors", "")
                        neutral_view = risk.get("neutral_view", "")
                        if volatility:
                            lines.append(f"**波动性**: {volatility}\n\n")
                        if key_risk_factors:
                            lines.append(f"**关键风险因素**: {key_risk_factors}\n\n")
                        if neutral_view:
                            lines.append(f"**中性观点**: {neutral_view}\n\n")
        
        # 3. Neutral research observation (the core content)
        # Two formats are supported: neutral_operation_advice and neutral_operation_suggestion
        neutral_advice = None
        if "neutral_operation_advice" in advice_json:
            neutral_advice = advice_json["neutral_operation_advice"]
        elif "neutral_operation_suggestion" in advice_json:
            neutral_advice = advice_json["neutral_operation_suggestion"]
        
        if neutral_advice and isinstance(neutral_advice, dict):
            lines.append("\n## 💡 研究观察\n\n")
            
            # core judgment
            core_judgment = neutral_advice.get("core_judgment", "")
            if core_judgment:
                lines.append(f"### 核心判断\n\n{core_judgment}\n\n")
            
            # Research conclusion tendencies/suggestions (compatible with different field names)
            recommended_action = neutral_advice.get("analysis_view", neutral_advice.get("recommended_action", neutral_advice.get("suggested_action", "")))
            if recommended_action:
                lines.append(f"**研究结论倾向**: {recommended_action}\n\n")
            
            # Reason description (reasoning field, may be a list or string)
            reasoning = neutral_advice.get("reasoning", [])
            if isinstance(reasoning, list) and reasoning:
                lines.append("### 理由说明\n\n")
                for idx, reason_item in enumerate(reasoning, 1):
                    if isinstance(reason_item, str) and reason_item:
                        lines.append(f"{idx}. {reason_item}\n\n")
                    elif isinstance(reason_item, dict):
                        # If it is a dictionary, extract all key-value pairs
                        for key, value in reason_item.items():
                            if value:
                                lines.append(f"**{key}**: {value}\n\n")
            elif isinstance(reasoning, str) and reasoning:
                lines.append(f"### 理由说明\n\n{reasoning}\n\n")
            
            # Specific recommendations (new format)
            specific_suggestions = neutral_advice.get("specific_suggestions", [])
            if isinstance(specific_suggestions, list) and specific_suggestions:
                lines.append("### 具体建议\n\n")
                for idx, suggestion in enumerate(specific_suggestions, 1):
                    if isinstance(suggestion, dict):
                        action = suggestion.get("action", "")
                        reason = suggestion.get("reason", "")
                        if action or reason:
                            lines.append(f"#### {idx}. {action}\n\n")
                            if reason:
                                # Handle Markdown format in reason (such as**Bold**) 
                                lines.append(f"{reason}\n\n")
            
            # Detailed recommended steps (compatible with older formats)
            detailed_suggestions = neutral_advice.get("detailed_suggestions", [])
            if isinstance(detailed_suggestions, list) and detailed_suggestions:
                for suggestion in detailed_suggestions:
                    if isinstance(suggestion, dict):
                        step = suggestion.get("step", "")
                        content = suggestion.get("content", "")
                        if step or content:
                            if step:
                                lines.append(f"**{step}**\n\n")
                            if content:
                                lines.append(f"{content}\n\n")
            
            # Reason statement (compatible with old format)
            action_reasoning = neutral_advice.get("action_reasoning", "")
            if action_reasoning:
                lines.append(f"{action_reasoning}\n\n")
            
            # Risk reminder
            risk_reminder = neutral_advice.get("risk_reminder", "")
            if risk_reminder:
                lines.append(f"\n---\n\n> ⚠️ **Risk reminder**: {risk_reminder}\n")
        
        # Handle specific_plan field (new format)
        if "specific_plan" in advice_json:
            specific_plan = advice_json["specific_plan"]
            if isinstance(specific_plan, dict):
                lines.append("\n## 📋 具体计划\n\n")
                
                # Immediate steps
                immediate_step = specific_plan.get("immediate_step", "")
                if immediate_step:
                    lines.append(f"### 立即行动\n\n{immediate_step}\n\n")
                
                # price monitoring
                price_monitoring = specific_plan.get("price_monitoring", {})
                if isinstance(price_monitoring, dict) and price_monitoring:
                    lines.append("### 价格监控\n\n")
                    stop_loss_ref = price_monitoring.get("风险关注参考价", price_monitoring.get("止损参考价", ""))
                    if stop_loss_ref:
                        lines.append(f"**风险关注参考价**: {stop_loss_ref}\n\n")
                    first_target = price_monitoring.get("第一关键验证价位（减亏/解套）", price_monitoring.get("第一目标价（减亏/解套）", ""))
                    if first_target:
                        lines.append(f"**The first key is to verify the price (loss reduction/unwinding)**: {first_target}\n\n")
                    second_target = price_monitoring.get("第二关键验证价位（达成收益）", price_monitoring.get("第二目标价（达成收益）", ""))
                    if second_target:
                        lines.append(f"**The second key is to verify the price (achieve profit)**: {second_target}\n\n")
                
                # Observation factors
                observation_factors = specific_plan.get("observation_factors", [])
                if isinstance(observation_factors, list) and observation_factors:
                    lines.append("### 观察要点\n\n")
                    for factor in observation_factors:
                        if factor:
                            lines.append(f"- {factor}\n")
                    lines.append("\n")
        
        # 4. Specific recommendations based on goals (compatible with older formats)
        if "specific_suggestions_based_on_your_goals" in advice_json:
            suggestions = advice_json["specific_suggestions_based_on_your_goals"]
            if isinstance(suggestions, dict):
                lines.append("\n## 🎯 Specific recommendations based on your goals\n\n")
                
                if_price_rises = suggestions.get("if_price_rises", {})
                if isinstance(if_price_rises, dict):
                    scenario = if_price_rises.get("scenario", "")
                    suggestion = if_price_rises.get("suggestion", "")
                    if scenario or suggestion:
                        lines.append(f"### 📈 如果股价上涨\n\n")
                        if scenario:
                            lines.append(f"**情景**: {scenario}\n\n")
                        if suggestion:
                            lines.append(f"{suggestion}\n\n")
                
                if_price_falls = suggestions.get("if_price_falls", {})
                if isinstance(if_price_falls, dict):
                    scenario = if_price_falls.get("scenario", "")
                    suggestion = if_price_falls.get("suggestion", "")
                    if scenario or suggestion:
                        lines.append(f"### 📉 如果股价下跌\n\n")
                        if scenario:
                            lines.append(f"**情景**: {scenario}\n\n")
                        if suggestion:
                            lines.append(f"{suggestion}\n\n")
                
                if_price_consolidates = suggestions.get("if_price_consolidates", {})
                if isinstance(if_price_consolidates, dict):
                    scenario = if_price_consolidates.get("scenario", "")
                    suggestion = if_price_consolidates.get("suggestion", "")
                    if scenario or suggestion:
                        lines.append(f"### ➡️ If the stock price consolidates\n\n")
                        if scenario:
                            lines.append(f"**情景**: {scenario}\n\n")
                        if suggestion:
                            lines.append(f"{suggestion}\n\n")
        
        # 5. Risk reminder (top level, compatible with old formats)
        if "risk_reminder" in advice_json and "neutral_operation_advice" not in advice_json:
            risk_reminder = advice_json["risk_reminder"]
            if risk_reminder:
                lines.append(f"\n---\n\n> ⚠️ **Risk reminder**: {risk_reminder}\n")
        
        # 6. Data difference description (compatible with old formats)
        if "data_discrepancy_note" in advice_json:
            note = advice_json["data_discrepancy_note"]
            if isinstance(note, dict):
                important_note = note.get("**重要提示**", note.get("important_note", ""))
                if important_note:
                    lines.append(f"\n> 📌 **Important tips**: {important_note}\n")
            elif isinstance(note, str) and note:
                lines.append(f"\n> 📌 **Data difference explanation**: {note}\n")
        
        # If nothing is extracted, try other fields
        if len(lines) == 0:
            if "conclusion" in advice_json:
                lines.append(advice_json["conclusion"])
            elif "operation_suggestion" in advice_json:
                lines.append(advice_json["operation_suggestion"])
        
        return "\n".join(lines).strip() if lines else "基于综合分析给出建议"
    
    def _extract_price_targets_from_json(self, advice_json: Dict[str, Any], snapshot: PositionSnapshot, params: Optional[PositionAnalysisRequest] = None) -> PriceTarget:
        """Extract risk focus/return focus prices from JSON
        
        Args:
            advice_json: JSON object for research observations
            snapshot: Position snapshot
            
        Returns:
            PriceTarget object
        """
        from app.models.portfolio import PriceTarget
        import re
        price_targets = PriceTarget()
        
        logger.info(f"📊 [Extract price target] JSON Field: {list(advice_json.keys())}")
        
        # Extract risk focus price (possibly at multiple positions, compatible with legacy stop price field)
        stop_loss_price = None
        
        # 1. Extract from top level
        stop_loss_price = advice_json.get("stop_loss_price")
        
        # 2. Extracted from specific_plan.price_monitoring
        if not stop_loss_price and "specific_plan" in advice_json:
            specific_plan = advice_json["specific_plan"]
            if isinstance(specific_plan, dict):
                price_monitoring = specific_plan.get("price_monitoring", {})
                if isinstance(price_monitoring, dict):
                    # Extract"Risk focus reference price"Field (compatible with older versions"Stop loss reference price", May be a string containing price)
                    stop_loss_ref = price_monitoring.get("风险关注参考价", price_monitoring.get("止损参考价", ""))
                    if stop_loss_ref:
                        # Try to extract the price number from a string (like"¥4.73"or"4.73") 
                        price_match = re.search(r'[\d.]+', str(stop_loss_ref))
                        if price_match:
                            try:
                                stop_loss_price = float(price_match.group())
                                logger.info(f"📊 [Extract price target] Extract risk focus price from specific_plan.price_monitoring: {stop_loss_price}")
                            except (ValueError, TypeError):
                                pass
        
        # 3. Extracted from neutral_operation_advice if available
        if not stop_loss_price and "neutral_operation_advice" in advice_json:
            neutral = advice_json["neutral_operation_advice"]
            if isinstance(neutral, dict):
                stop_loss_price = neutral.get("stop_loss_price")
        
        # Deal with risk and focus on price
        if stop_loss_price:
            try:
                price_targets.stop_loss_price = float(stop_loss_price)
                if snapshot.cost_price and snapshot.cost_price > 0:
                    price_targets.stop_loss_pct = round(
                        (price_targets.stop_loss_price - snapshot.cost_price) / snapshot.cost_price * 100, 2
                    )
                logger.info(f"📊 [提取价格目标] 风险关注价格: {price_targets.stop_loss_price}, 百分比: {price_targets.stop_loss_pct}")
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ [Extract price target] Risk focus price conversion failed: {e}")
        else:
            logger.info(f"📊 [Extract price target] JSON The stop_loss_price field was not found in")
        
        # Extract the profit and focus on the price (may be in multiple positions, compatible with the old version of the take profit price field)
        take_profit_price = None
        
        # 1. Extract from top level
        take_profit_price = advice_json.get("take_profit_price")
        
        # 2. Extracted from specific_plan.price_monitoring (the second key verification price is usually the earnings focus price)
        if not take_profit_price and "specific_plan" in advice_json:
            specific_plan = advice_json["specific_plan"]
            if isinstance(specific_plan, dict):
                price_monitoring = specific_plan.get("price_monitoring", {})
                if isinstance(price_monitoring, dict):
                    # priority use"The second key is to verify the price (achieve profit)"
                    second_target = price_monitoring.get("第二关键验证价位（达成收益）", price_monitoring.get("第二目标价（达成收益）", ""))
                    if second_target:
                        price_match = re.search(r'[\d.]+', str(second_target))
                        if price_match:
                            try:
                                take_profit_price = float(price_match.group())
                                logger.info(f"📊 [Extract price target] Extract the revenue focus price from specific_plan.price_monitoring: {take_profit_price}")
                            except (ValueError, TypeError):
                                pass
                    # If there is no second key verification price, try to use the first key verification price
                    if not take_profit_price:
                        first_target = price_monitoring.get("第一关键验证价位（减亏/解套）", price_monitoring.get("第一目标价（减亏/解套）", ""))
                        if first_target:
                            price_match = re.search(r'[\d.]+', str(first_target))
                            if price_match:
                                try:
                                    take_profit_price = float(price_match.group())
                                    logger.info(f"📊 [Extract price target] Extract revenue focus price from specific_plan.price_monitoring (use first key to verify price): {take_profit_price}")
                                except (ValueError, TypeError):
                                    pass
        
        # 3. Extracted from neutral_operation_advice if available
        if not take_profit_price and "neutral_operation_advice" in advice_json:
            neutral = advice_json["neutral_operation_advice"]
            if isinstance(neutral, dict):
                take_profit_price = neutral.get("take_profit_price")
        
        # Handle earnings focus on price
        if take_profit_price:
            try:
                price_targets.take_profit_price = float(take_profit_price)
                if snapshot.cost_price and snapshot.cost_price > 0:
                    price_targets.take_profit_pct = round(
                        (price_targets.take_profit_price - snapshot.cost_price) / snapshot.cost_price * 100, 2
                    )
                logger.info(f"📊 [提取价格目标] 收益关注价格: {price_targets.take_profit_price}, 百分比: {price_targets.take_profit_pct}")
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ [Extract price target] Yield focus price conversion failed: {e}")
        else:
            logger.info(f"📊 [Extract price target] JSON The take_profit_price field was not found in")
        
        # The return price is the cost price
        if snapshot.cost_price and snapshot.cost_price > 0:
            price_targets.breakeven_price = snapshot.cost_price
            logger.info(f"📊 [Extract price target] return price: {price_targets.breakeven_price}")
        
        # If the AI does not generate a price target, it is calculated based on the percentage set by the user (fallback logic)
        if not price_targets.stop_loss_price and params and snapshot.cost_price and snapshot.cost_price > 0:
            # Calculate risk focus price using user-set maximum loss percentage
            max_loss_pct = params.max_loss_pct if params.max_loss_pct else 10.0  # Default 10%
            price_targets.stop_loss_price = round(snapshot.cost_price * (1 - max_loss_pct / 100), 2)
            price_targets.stop_loss_pct = round(-max_loss_pct, 2)
            logger.info(f"📊 [提取价格目标] AI未生成风险关注价格，根据用户设定计算: stop_loss={price_targets.stop_loss_price} (基于{max_loss_pct}%亏损)")
        
        if not price_targets.take_profit_price and params and snapshot.cost_price and snapshot.cost_price > 0:
            # Calculate the revenue focus price using the target revenue percentage set by the user
            target_profit_pct = params.target_profit_pct if params.target_profit_pct else 10.0  # Default 10%
            price_targets.take_profit_price = round(snapshot.cost_price * (1 + target_profit_pct / 100), 2)
            price_targets.take_profit_pct = round(target_profit_pct, 2)
            logger.info(f"📊 [提取价格目标] AI未生成收益关注价格，根据用户设定计算: take_profit={price_targets.take_profit_price} (基于{target_profit_pct}%收益)")
        
        return price_targets
    
    def _extract_action_from_json(self, advice_json: Dict[str, Any]) -> PositionAction:
        """Extract research conclusion tendencies corresponding to JSON PositionAction
        
        Args:
            advice_json: JSON object for research observations
            
        Returns:
            PositionAction Enumeration values (for learning and research reference only, not trading advice)
        """
        # Prioritize extraction from neutral_operation_advice.specific_suggestions (new format)
        if "neutral_operation_advice" in advice_json:
            neutral = advice_json["neutral_operation_advice"]
            if isinstance(neutral, dict):
                # New format: extract the first one from the specific_suggestions array action
                specific_suggestions = neutral.get("specific_suggestions", [])
                if isinstance(specific_suggestions, list) and specific_suggestions:
                    first_suggestion = specific_suggestions[0]
                    if isinstance(first_suggestion, dict):
                        action_text = first_suggestion.get("action", "")
                        if action_text:
                            action_lower = action_text.lower()
                            if any(k in action_lower for k in ["乐观", "加仓", "买入", "补仓"]):
                                return PositionAction.ADD
                            elif any(k in action_lower for k in ["审慎", "减仓", "减持", "卖出", "清仓", "全部卖出"]):
                                return PositionAction.REDUCE
                            elif any(k in action_lower for k in ["中性", "持有", "继续持有", "观察"]):
                                return PositionAction.HOLD
                
                # Compatible with old formats: extracted from recommended_action/analysis_view
                recommended = neutral.get("analysis_view", neutral.get("recommended_action", ""))
                if recommended:
                    recommended_lower = recommended.lower()
                    if any(k in recommended_lower for k in ["乐观", "加仓", "买入"]):
                        return PositionAction.ADD
                    elif any(k in recommended_lower for k in ["审慎", "减仓", "卖出", "清仓"]):
                        return PositionAction.REDUCE
                    elif any(k in recommended_lower for k in ["中性", "持有"]):
                        return PositionAction.HOLD
        
        # Hold by default
        return PositionAction.HOLD
    
    def _parse_workflow_action_advice(self, action_advice: str) -> tuple[PositionAction, str]:
        """Analyze the tendencies and reasons for research conclusions from research observations on workflow

        Args:
            action_advice: Research observer output text

        Returns:
            tuple: (PositionAction, Reasons for research and observation)
        """
        if not action_advice:
            return PositionAction.HOLD, "未获取到研究观察"

        # Convert to lowercase for easier matching
        advice_lower = action_advice.lower()

        # Determine the tendency of research conclusions based on keywords (compatible with compliance terms and old version operational terms)
        if any(keyword in advice_lower for keyword in ["乐观", "买入", "加仓", "增持", "建议买", "推荐买", "add"]):
            action = PositionAction.ADD
        elif any(keyword in advice_lower for keyword in ["审慎", "清仓", "建议卖", "推荐卖", "clear", "卖出", "减仓", "reduce"]):
            action = PositionAction.REDUCE
        elif any(keyword in advice_lower for keyword in ["中性", "持有", "观望", "hold"]):
            action = PositionAction.HOLD
        else:
            action = PositionAction.HOLD

        # Extract reasons for research observations (take the first 200 characters as brief reasons)
        action_reason = action_advice[:200] + "..." if len(action_advice) > 200 else action_advice

        return action, action_reason

    def _sanitize_position_analysis_dict(
        self,
        data: Dict[str, Any],
        position_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Unified cleansing of result fields in position study details and history (compliance: removal of execution trading orders)."""
        return sanitize_position_analysis_payload(data, position_snapshot=position_snapshot)


# Service instance
_portfolio_service: Optional[PortfolioService] = None


def get_portfolio_service() -> PortfolioService:
    """获取持仓分析服务实例"""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service


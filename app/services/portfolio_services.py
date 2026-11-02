from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['portfolio_service', 'favorites_service', 'tags_service', 'stop_gain_alert_service', 'stop_loss_alert_service', 'trade_review_service']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === portfolio_service.py ===
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
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
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
def _portfolio_service_use_template_prompts() -> bool:
    """Dynamically read the USE_TEMPLATE_PROMPTS environment variable"""
    return os.getenv("USE_TEMPLATE_PROMPTS", "false").lower() == "true"

# Whether to use the new version of the stock analysis engine (off by default to maintain backward compatibility)
def _portfolio_service_use_stock_engine() -> bool:
    """Dynamically read the USE_STOCK_ENGINE environment variable"""
    return os.getenv("USE_STOCK_ENGINE", "false").lower() == "true"

# Whether to use the new version of analysis engine (including workflow engine)
def _portfolio_service_use_stock_engine() -> bool:
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
            if _portfolio_service_use_stock_engine():
                logger.info("🚀 [Position analysis] Analysis using Workflow Engine v2.0")
                ai_result = await self._call_position_ai_analysis_workflow(
                    snapshot=snapshot,
                    params=params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )
            else:
                logger.info("🤖 [Position analysis] Using traditional LLM analysis")
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
                            logger.info("📊 [Format reports] Directly parse JSON format")
                            advice_json = json.loads(action_reason_str)
                        
                        if advice_json:
                            logger.info(f"📊 [Format reports] JSON Parsed successfully, field: {list(advice_json.keys())}")
                            action_reason_formatted = self._convert_action_advice_json_to_markdown(advice_json)
                            logger.info(f"📊 [Format reports] JSON Conversion to Markdown successful, length: {len(action_reason_formatted)}")
                        else:
                            logger.warning("⚠️ [Format reports] JSON Empty after parsing, use original value")
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
            if _portfolio_service_use_stock_engine():
                logger.info("🚀 [Summary position analysis] Analysis using Workflow Engine v2.0")
                ai_result = await self._call_position_ai_analysis_workflow(
                    snapshot=snapshot,
                    params=analysis_params,
                    stock_analysis_report=stock_analysis_report,
                    user_id=user_id
                )
            else:
                logger.info("🤖 [Summary position analysis] Using traditional LLM analysis")
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

            logger.info("📤 [Position AI analysis] Start calling LLM...")
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
        if _portfolio_service_use_template_prompts():
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
                        logger.warning("⚠️ [Workflow position analysis] Unable to get full model configuration, only set model name")
                else:
                    logger.warning("⚠️ [Workflow position analysis] system_settings quick_analysis_model or deep_analysis_model not found, use default configuration")
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
                        logger.info("📊 [Workflow position analysis] Directly parse JSON format")
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
                        logger.warning("⚠️ [Workflow position analysis] confidence Conversion failed, using default value 50")
                else:
                    # If AI does not generate confidence, set a reasonable default based on analysis quality
                    confidence = 50.0  # Default medium confidence
                    logger.info("📊 [Workflow position analysis] JSON There is no confidence field in, use the default value 50")
                
                logger.info(f"📊 [Workflow position analysis] extracted confidence: {confidence}")
                price_targets = self._extract_price_targets_from_json(advice_json, snapshot, params)
                logger.info(f"📊 [Workflow position analysis] extracted price_targets: stop_loss={price_targets.stop_loss_price}, take_profit={price_targets.take_profit_price}, breakeven={price_targets.breakeven_price}")
                risk_assessment_text = advice_json.get("risk_assessment", "") or risk_analysis
                logger.info(f"📊 [Workflow position analysis] Extracted risk_assessment length: {len(risk_assessment_text)}")
                opportunity_assessment_text = advice_json.get("opportunity_assessment", "")
                logger.info(f"📊 [Workflow position analysis] Extracted opportunity_assessment length: {len(opportunity_assessment_text)}")
            else:
                logger.warning("⚠️ [Workflow position analysis] advice_json If empty, use text parsing")
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
                logger.warning("⚠️ [Workflow position analysis] detailed_analysis Empty, use default content")
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
                        lines.append("### 📈 如果股价上涨\n\n")
                        if scenario:
                            lines.append(f"**情景**: {scenario}\n\n")
                        if suggestion:
                            lines.append(f"{suggestion}\n\n")
                
                if_price_falls = suggestions.get("if_price_falls", {})
                if isinstance(if_price_falls, dict):
                    scenario = if_price_falls.get("scenario", "")
                    suggestion = if_price_falls.get("suggestion", "")
                    if scenario or suggestion:
                        lines.append("### 📉 如果股价下跌\n\n")
                        if scenario:
                            lines.append(f"**情景**: {scenario}\n\n")
                        if suggestion:
                            lines.append(f"{suggestion}\n\n")
                
                if_price_consolidates = suggestions.get("if_price_consolidates", {})
                if isinstance(if_price_consolidates, dict):
                    scenario = if_price_consolidates.get("scenario", "")
                    suggestion = if_price_consolidates.get("suggestion", "")
                    if scenario or suggestion:
                        lines.append("### ➡️ If the stock price consolidates\n\n")
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
            logger.info("📊 [Extract price target] JSON The stop_loss_price field was not found in")
        
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
            logger.info("📊 [Extract price target] JSON The take_profit_price field was not found in")
        
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


# === favorites_service.py ===
"""
股票关注列表服务
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db
from app.models.user import FavoriteStock
# The online market completion function has been removed and only data is read from the database.
# Users can pass"Synchronize real-time quotes"button to update data
# from app.services.quotes_service import get_quotes_service

logger = logging.getLogger("webapi")


class FavoritesService:
    """股票关注列表服务类"""
    
    def __init__(self):
        self.db = None
    
    async def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def _ensure_tags_exist(self, user_id: str, tags: Optional[List[str]]) -> List[str]:
        """Make sure that the tags used in the stock watchlist have been synchronized to the user_tags collection."""
        normalized_tags: List[str] = []
        seen = set()
        for item in tags or []:
            tag_name = str(item or "").strip()
            if not tag_name or tag_name in seen:
                continue
            seen.add(tag_name)
            normalized_tags.append(tag_name)

        if not normalized_tags:
            return []

        try:

            existing_tags = {
                tag.get("name")
                for tag in await tags_service.list_tags(user_id)
                if tag.get("name")
            }
            for tag_name in normalized_tags:
                if tag_name in existing_tags:
                    continue
                try:
                    await tags_service.create_tag(user_id=user_id, name=tag_name)
                    existing_tags.add(tag_name)
                except Exception:
                    logger.debug("[FavoritesService] Failed to create missing tag: %s", tag_name, exc_info=True)
        except Exception:
            logger.warning("[FavoritesService] Automatically adding tags failed, continue to save the stock watch list", exc_info=True)

        return normalized_tags

    def _is_valid_object_id(self, user_id: str) -> bool:
        """
        Check if it is a valid ObjectId format
        Note: Only the format is checked here, it does not mean that the ObjectId type is actually stored in the database.
        For compatibility, we uniformly use the user_favorites collection to store stock watch lists.
        """
        # Forced to return False, uniformly use the user_favorites collection
        return False

    def _format_favorite(self, favorite: Dict[str, Any]) -> Dict[str, Any]:
        """Format collection items (basic information only, not including real-time quotes).
        Quotes will be batch enriched in get_user_favorites.
        """
        added_at = favorite.get("added_at")
        if isinstance(added_at, datetime):
            added_at = added_at.isoformat()
        return {
            "stock_code": favorite.get("stock_code"),
            "stock_name": favorite.get("stock_name"),
            "market": favorite.get("market", "A股"),
            "added_at": added_at,
            "tags": favorite.get("tags", []),
            "notes": favorite.get("notes", ""),
            "alert_price_high": favorite.get("alert_price_high"),
            "alert_price_low": favorite.get("alert_price_low"),
            "alert_gain_price": favorite.get("alert_gain_price"),
            # Market occupancy, will be filled in later
            "current_price": None,
            "change_percent": None,
            "volume": None,
        }
    async def update_alert_gain_price(self, user_id: str, stock_code: str, gain_price: Optional[float]) -> bool:
        """设置或清除止盈提醒价格"""
        db = await self._get_db()
        is_oid = self._is_valid_object_id(user_id)
        prefix = "favorite_stocks.$." if is_oid else "favorites.$."
        update_fields = {prefix + "alert_gain_price": gain_price}
        if is_oid:
            result = await db.users.update_one(
                {"_id": ObjectId(user_id), "favorite_stocks.stock_code": stock_code},
                {"$set": update_fields}
            )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {"user_id": user_id, "favorites.stock_code": stock_code},
                {"$set": {**update_fields, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0

    async def get_user_favorites(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Obtain the user s stock watch list, and read real-time quotes from the database for enrichment (compatible with string ID and ObjectId).
        
        Note:
        - Only read data from database (market_quotes, market_quotes_hk, market_quotes_us)
        - The online API will not be called to pull the latest prices to avoid interface timeout.
        - Users can pass"Synchronize real-time quotes"button to update data
        - Background scheduled tasks will regularly update the real-time market data in the database
        """
        import time
        start_time = time.time()
        db = await self._get_db()

        logger.info(f"🔍 [get_user_favorites] Start querying user s stock watch list: user_id={user_id}")

        favorites: List[Dict[str, Any]] = []
        if self._is_valid_object_id(user_id):
            # Try using ObjectId query first
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            # If ObjectId query fails, try using string query
            if user is None:
                user = await db.users.find_one({"_id": user_id})
            favorites = (user or {}).get("favorite_stocks", [])
            logger.info(f"✅ [get_user_favorites] 从 users 集合获取到 {len(favorites)} 只股票关注列表")
        else:
            # 🔥 Strict filtering: only query the current user's stock watch list
            # Use exact matching to ensure only fetching data for the current user
            doc = await db.user_favorites.find_one({"user_id": {"$eq": user_id}})
            if doc:
                # 🔥 Two-step verification: Make sure the document's user_id actually matches
                doc_user_id = doc.get("user_id")
                if doc_user_id != user_id:
                    logger.error(f"❌ [get_user_favorites] 用户ID不匹配！查询: {user_id}, 文档: {doc_user_id}")
                    favorites = []
                else:
                    favorites = doc.get("favorites", [])
                    logger.info(f"✅ [get_user_favorites] Obtained from user_favorites collection {len(favorites)} Only stock watch list (user_id={doc_user_id})")
            else:
                logger.warning(f"⚠️ [get_user_favorites] User stock watchlist data not found: user_id={user_id}")
                # 🔥 Debugging: Check if there are other users' documentation (for debugging only)
                all_docs_count = await db.user_favorites.count_documents({})
                logger.info(f"🔍 [get_user_favorites] 数据库中共有 {all_docs_count} 个文档")
                if all_docs_count > 0:
                    # Only query the first 5 documents for debugging
                    all_docs = await db.user_favorites.find({}, {"user_id": 1, "favorites": 1}).limit(5).to_list(length=5)
                    for idx, d in enumerate(all_docs):
                        logger.info(f"  文档 {idx+1}: user_id={d.get('user_id')}, favorites数量={len(d.get('favorites', []))}")
                favorites = []

        # Format the basic fields first
        items = [self._format_favorite(fav) for fav in favorites]

        # Obtain basic stock information in batches (sectors, etc.)
        codes = [it.get("stock_code") for it in items if it.get("stock_code")]
        if codes:
            try:
                # 🔥 Get data source priority configuration
                from app.core.unified_config import UnifiedConfigManager
                config = UnifiedConfigManager()
                data_source_configs = await config.get_data_source_configs_async()

                # Extract enabled data sources, sorted by priority
                enabled_sources = [
                    ds.type.lower() for ds in data_source_configs
                    if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
                ]

                if not enabled_sources:
                    enabled_sources = ['tushare', 'akshare', 'baostock']

                preferred_source = enabled_sources[0] if enabled_sources else 'tushare'

                # Get sector information from stock_basic_info (only query the data source with the highest priority)
                basic_info_coll = db["stock_basic_info"]
                cursor = basic_info_coll.find(
                    {"code": {"$in": codes}, "source": preferred_source},  # 🔥 Add data source filter
                    {"code": 1, "sse": 1, "market": 1, "_id": 0}
                )
                basic_docs = await cursor.to_list(length=None)
                basic_map = {str(d.get("code")).zfill(6): d for d in (basic_docs or [])}

                # Collect the missed codes in stock_basic_info and check later etf_basic_info
                missing_codes = []
                for it in items:
                    code = it.get("stock_code")
                    basic = basic_map.get(code)
                    if basic:
                        it["board"] = basic.get("market", "-")
                        it["exchange"] = basic.get("sse", "-")
                    else:
                        missing_codes.append(code)

                # Supplement ETF sector/exchange information from etf_basic_info
                if missing_codes:
                    etf_coll = db["etf_basic_info"]
                    etf_cursor = etf_coll.find(
                        {"code": {"$in": missing_codes}},
                        {"code": 1, "name": 1, "_id": 0}
                    )
                    etf_docs = await etf_cursor.to_list(length=None)
                    etf_set = {str(d.get("code")).zfill(6) for d in (etf_docs or [])}
                    etf_name_map = {
                        str(d.get("code")).zfill(6): d.get("name")
                        for d in (etf_docs or [])
                    }

                    for it in items:
                        code = it.get("stock_code")
                        if code in basic_map:
                            continue
                        if code in etf_set:
                            it["board"] = "ETF"
                            if code.startswith(("50", "51", "52")):
                                it["exchange"] = "上海证券交易所"
                            elif code.startswith(("15", "16")):
                                it["exchange"] = "深圳证券交易所"
                            else:
                                it["exchange"] = "-"
                            if not it.get("stock_name") or it["stock_name"] == code:
                                it["stock_name"] = etf_name_map.get(code) or it.get("stock_name", code)
                        else:
                            it["board"] = "-"
                            it["exchange"] = "-"
            except Exception as e:
                # Set default value when query fails
                for it in items:
                    it["board"] = "-"
                    it["exchange"] = "-"

        # Obtain market information in batches (processed separately according to market type to avoid unnecessary interface calls)
        if codes:
            try:
                # 🔥 Group by market type
                a_share_items = []  # A shares
                hk_items = []       # Hong Kong stocks
                us_items = []       # US stocks
                
                for it in items:
                    market = it.get("market", "A股")
                    if market == "港股":
                        hk_items.append(it)
                    elif market == "美股":
                        us_items.append(it)
                    else:
                        a_share_items.append(it)
                
                # 1. Processing of A shares: Priority is given to using the market_quotes stored in the database, updated in 30 seconds
                if a_share_items:
                    a_share_codes = [it.get("stock_code") for it in a_share_items if it.get("stock_code")]
                    if a_share_codes:
                        try:
                            coll = db["market_quotes"]
                            cursor = coll.find({"code": {"$in": a_share_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")).zfill(6): d for d in (docs or [])}
                            for it in a_share_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                                # If there is no data in the database, keep None (do not call the online API)
                                # Users can click"Synchronize real-time quotes"button to update data
                        except Exception as e:
                            logger.warning(f"⚠️ 查询A股行情失败: {e}")
                
                # 2. Process Hong Kong stocks: query from market_quotes_hk
                if hk_items:
                    hk_codes = [it.get("stock_code") for it in hk_items if it.get("stock_code")]
                    if hk_codes:
                        try:
                            coll = db["market_quotes_hk"]
                            cursor = coll.find({"code": {"$in": hk_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")): d for d in (docs or [])}
                            for it in hk_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                        except Exception as e:
                            logger.warning(f"⚠️ 查询港股行情失败: {e}")
                
                # 3. Processing US stocks: query from market_quotes_us
                if us_items:
                    us_codes = [it.get("stock_code") for it in us_items if it.get("stock_code")]
                    if us_codes:
                        try:
                            coll = db["market_quotes_us"]
                            cursor = coll.find({"code": {"$in": us_codes}}, {"code": 1, "close": 1, "pct_chg": 1, "amount": 1})
                            docs = await cursor.to_list(length=None)
                            quotes_map = {str(d.get("code")): d for d in (docs or [])}
                            for it in us_items:
                                code = it.get("stock_code")
                                q = quotes_map.get(code)
                                if q:
                                    it["current_price"] = q.get("close")
                                    it["change_percent"] = q.get("pct_chg")
                        except Exception as e:
                            logger.warning(f"⚠️ 查询美股行情失败: {e}")
                            
            except Exception as e:
                logger.warning(f"⚠️ 批量获取行情失败: {e}")
                # Keep the placeholder None when the query fails to avoid affecting basic functions.
                pass

        # Record performance logs
        elapsed_time = time.time() - start_time
        logger.info(f"✅ [get_user_favorites] 查询完成: user_id={user_id}, 返回 {len(items)} 只股票关注列表, 耗时 {elapsed_time:.2f}秒")
        if elapsed_time > 5:
            logger.warning(f"⚠️ [get_user_favorites] The interface takes a long time: {elapsed_time:.2f}seconds, there may be a performance issue")

        return items

    async def add_favorite(
        self,
        user_id: str,
        stock_code: str,
        stock_name: str,
        market: str = "A股",
        tags: List[str] = None,
        notes: str = "",
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None
    ) -> bool:
        """Add stocks to stock watchlist (compatible with String ID and ObjectId)"""
        import logging
        logger = logging.getLogger("webapi")

        try:
            logger.info(f"🔧 [add_favorite] Start adding to research list: user_id={user_id}, stock_code={stock_code}")

            db = await self._get_db()
            logger.info("🔧 [add_favorite] Database connection obtained successfully")

            normalized_tags = await self._ensure_tags_exist(user_id, tags)

            favorite_stock = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "market": market,
                "added_at": datetime.utcnow(),
                "tags": normalized_tags,
                "notes": notes,
                "alert_price_high": alert_price_high,
                "alert_price_low": alert_price_low
            }

            logger.info(f"🔧 [add_favorite] Stock watch list data construction completed: {favorite_stock}")

            is_oid = self._is_valid_object_id(user_id)
            logger.info(f"🔧 [add_favorite] User ID type check: is_valid_object_id={is_oid}")

            if is_oid:
                logger.info("🔧 [add_favorite] Add to users collection using ObjectId method")

                # Try using ObjectId query first
                result = await db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {
                        "$push": {"favorite_stocks": favorite_stock},
                        "$setOnInsert": {"favorite_stocks": []}
                    }
                )
                logger.info(f"🔧 [add_favorite] ObjectId Query results: matched_count={result.matched_count}, modified_count={result.modified_count}")

                # If ObjectId query fails, try using string query
                if result.matched_count == 0:
                    logger.info("🔧 [add_favorite] ObjectId Query failed, trying to query using string ID")
                    result = await db.users.update_one(
                        {"_id": user_id},
                        {
                            "$push": {"favorite_stocks": favorite_stock}
                        }
                    )
                    logger.info(f"🔧 [add_favorite] String ID query results: matched_count={result.matched_count}, modified_count={result.modified_count}")

                success = result.matched_count > 0
                logger.info(f"🔧 [add_favorite] Return results: {success}")
                return success
            else:
                logger.info("🔧 [add_favorite] Add to user_favorites collection using string ID")
                result = await db.user_favorites.update_one(
                    {"user_id": user_id},
                    {
                        "$setOnInsert": {"user_id": user_id, "created_at": datetime.utcnow()},
                        "$push": {"favorites": favorite_stock},
                        "$set": {"updated_at": datetime.utcnow()}
                    },
                    upsert=True
                )
                logger.info(f"🔧 [add_favorite] Update results: matched_count={result.matched_count}, modified_count={result.modified_count}, upserted_id={result.upserted_id}")
                logger.info("🔧 [add_favorite] Return results: True")
                return True
        except Exception as e:
            logger.error(f"❌ [add_favorite] Add to study list exception: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def remove_favorite(self, user_id: str, stock_code: str) -> bool:
        """Remove a stock from the stock watchlist (compatible with String ID and ObjectId)"""
        db = await self._get_db()

        if self._is_valid_object_id(user_id):
            # Try using ObjectId query first
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"favorite_stocks": {"stock_code": stock_code}}}
            )
            # If ObjectId query fails, try using string query
            if result.matched_count == 0:
                result = await db.users.update_one(
                    {"_id": user_id},
                    {"$pull": {"favorite_stocks": {"stock_code": stock_code}}}
                )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {"user_id": user_id},
                {
                    "$pull": {"favorites": {"stock_code": stock_code}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return result.modified_count > 0

    async def update_favorite(
        self,
        user_id: str,
        stock_code: str,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None,
        clear_alert_price_low: bool = False,
    ) -> bool:
        """Update stock watch list information (compatible with string ID and ObjectId)"""
        db = await self._get_db()

        # Unify the construction of update fields (set prefixes according to the field paths of different collections)
        is_oid = self._is_valid_object_id(user_id)
        prefix = "favorite_stocks.$." if is_oid else "favorites.$."
        update_fields: Dict[str, Any] = {}
        if tags is not None:
            normalized_tags = await self._ensure_tags_exist(user_id, tags)
            update_fields[prefix + "tags"] = normalized_tags
        if notes is not None:
            update_fields[prefix + "notes"] = notes
        if alert_price_high is not None:
            update_fields[prefix + "alert_price_high"] = alert_price_high
        if clear_alert_price_low:
            update_fields[prefix + "alert_price_low"] = None
        elif alert_price_low is not None:
            update_fields[prefix + "alert_price_low"] = alert_price_low

        if not update_fields:
            return True

        if is_oid:
            result = await db.users.update_one(
                {
                    "_id": ObjectId(user_id),
                    "favorite_stocks.stock_code": stock_code
                },
                {"$set": update_fields}
            )
            return result.modified_count > 0
        else:
            result = await db.user_favorites.update_one(
                {
                    "user_id": user_id,
                    "favorites.stock_code": stock_code
                },
                {
                    "$set": {
                        **update_fields,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0

    async def is_favorite(self, user_id: str, stock_code: str) -> bool:
        """Check whether the stock is in the stock watch list (compatible with String ID and ObjectId)"""
        import logging
        logger = logging.getLogger("webapi")

        try:
            logger.info(f"🔧 [is_favorite] Check stock watchlist: user_id={user_id}, stock_code={stock_code}")

            db = await self._get_db()

            is_oid = self._is_valid_object_id(user_id)
            logger.info(f"🔧 [is_favorite] User ID type: is_valid_object_id={is_oid}")

            if is_oid:
                # Try using ObjectId query first
                user = await db.users.find_one(
                    {
                        "_id": ObjectId(user_id),
                        "favorite_stocks.stock_code": stock_code
                    }
                )

                # If ObjectId query fails, try using string query
                if user is None:
                    logger.info("🔧 [is_favorite] ObjectId Query not found, try querying using string ID")
                    user = await db.users.find_one(
                        {
                            "_id": user_id,
                            "favorite_stocks.stock_code": stock_code
                        }
                    )

                result = user is not None
                logger.info(f"🔧 [is_favorite] Query results: {result}")
                return result
            else:
                doc = await db.user_favorites.find_one(
                    {
                        "user_id": user_id,
                        "favorites.stock_code": stock_code
                    }
                )
                result = doc is not None
                logger.info(f"🔧 [is_favorite] String ID query results: {result}")
                return result
        except Exception as e:
            logger.error(f"❌ [is_favorite] Check for stock watchlist exceptions: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    async def get_user_tags(self, user_id: str) -> List[str]:
        """Get all tags used by the user (compatible with string ID and ObjectId)"""
        db = await self._get_db()

        if self._is_valid_object_id(user_id):
            pipeline = [
                {"$match": {"_id": ObjectId(user_id)}},
                {"$unwind": "$favorite_stocks"},
                {"$unwind": "$favorite_stocks.tags"},
                {"$group": {"_id": "$favorite_stocks.tags"}},
                {"$sort": {"_id": 1}}
            ]
            result = await db.users.aggregate(pipeline).to_list(None)
        else:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$unwind": "$favorites"},
                {"$unwind": "$favorites.tags"},
                {"$group": {"_id": "$favorites.tags"}},
                {"$sort": {"_id": 1}}
            ]
            result = await db.user_favorites.aggregate(pipeline).to_list(None)

        return [item["_id"] for item in result if item.get("_id")]

    def _get_mock_price(self, stock_code: str) -> float:
        """获取模拟股价"""
        # Generate simulated prices based on stock symbols
        base_price = hash(stock_code) % 100 + 10
        return round(base_price + (hash(stock_code) % 1000) / 100, 2)
    
    def _get_mock_change(self, stock_code: str) -> float:
        """获取模拟涨跌幅"""
        # Generate simulated price increases and decreases based on stock codes
        change = (hash(stock_code) % 2000 - 1000) / 100
        return round(change, 2)
    
    def _get_mock_volume(self, stock_code: str) -> int:
        """获取模拟成交量"""
        # Generate simulated trading volume based on stock symbol
        return (hash(stock_code) % 10000 + 1000) * 100


# Create a global instance
favorites_service = FavoritesService()

# === tags_service.py ===
"""
用户自定义标签服务
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db


class TagsService:
    def __init__(self) -> None:
        self.db = None
        self._indexes_ensured = False

    async def _get_db(self):
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        db = await self._get_db()
        # Each user's tag name is unique
        await db.user_tags.create_index([("user_id", 1), ("name", 1)], unique=True, name="uniq_user_tag_name")
        await db.user_tags.create_index([("user_id", 1), ("sort_order", 1)], name="idx_user_tag_sort")
        self._indexes_ensured = True

    def _normalize_user_id(self, user_id: str) -> str:
        # Unified into string storage to facilitate compatibility with open source versions(admin)and the future ObjectId
        return str(user_id)

    def _format_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(doc.get("_id")),
            "name": doc.get("name"),
            "color": doc.get("color") or "#409EFF",
            "sort_order": doc.get("sort_order", 0),
            "created_at": (doc.get("created_at") or datetime.utcnow()).isoformat(),
            "updated_at": (doc.get("updated_at") or datetime.utcnow()).isoformat(),
        }

    async def list_tags(self, user_id: str) -> List[Dict[str, Any]]:
        db = await self._get_db()
        await self.ensure_indexes()
        cursor = db.user_tags.find({"user_id": self._normalize_user_id(user_id)}).sort([
            ("sort_order", 1), ("name", 1)
        ])
        docs = await cursor.to_list(length=None)
        return [self._format_doc(d) for d in docs]

    async def create_tag(self, user_id: str, name: str, color: Optional[str] = None, sort_order: int = 0) -> Dict[str, Any]:
        db = await self._get_db()
        await self.ensure_indexes()
        now = datetime.utcnow()
        doc = {
            "user_id": self._normalize_user_id(user_id),
            "name": name.strip(),
            "color": color or "#409EFF",
            "sort_order": int(sort_order or 0),
            "created_at": now,
            "updated_at": now,
        }
        result = await db.user_tags.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._format_doc(doc)

    async def update_tag(self, user_id: str, tag_id: str, *, name: Optional[str] = None, color: Optional[str] = None, sort_order: Optional[int] = None) -> bool:
        db = await self._get_db()
        await self.ensure_indexes()
        update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if name is not None:
            update["name"] = name.strip()
        if color is not None:
            update["color"] = color
        if sort_order is not None:
            update["sort_order"] = int(sort_order)
        if len(update) == 1:  # only updated_at
            return True
        result = await db.user_tags.update_one(
            {"_id": ObjectId(tag_id), "user_id": self._normalize_user_id(user_id)},
            {"$set": update}
        )
        return result.matched_count > 0

    async def delete_tag(self, user_id: str, tag_id: str) -> bool:
        db = await self._get_db()
        await self.ensure_indexes()
        result = await db.user_tags.delete_one({"_id": ObjectId(tag_id), "user_id": self._normalize_user_id(user_id)})
        return result.deleted_count > 0


# global instance
tags_service = TagsService()


# === stop_gain_alert_service.py ===
# Take profit reminder service
# Periodically scan the take-profit line (alert_gain_price) set by the user, and push notifications when hit

import asyncio
import logging
from typing import Any, Dict, List

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched

from app.core.database import get_mongo_db
from app.models.notification import NotificationCreate
try:
    from app.services.notifications_service import get_notifications_service
except ImportError:
    get_notifications_service = None

logger = logging.getLogger(__name__)


class StopGainAlertService:
    def __init__(self, scan_interval_minutes=10):
        self.scan_interval_minutes = scan_interval_minutes
        self.scheduler = BackgroundScheduler()
        self._job = None
        self._loop = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Called by main in lifespan to safely execute asynchronous logic in the scheduler thread."""
        self._loop = loop

    def start(self):
        if not self._job:
            self._job = self.scheduler.add_job(self.run_once, "interval", minutes=self.scan_interval_minutes)
            self.scheduler.start()
            logger.info("The take-profit reminder service is started with an interval of %s minutes.", self.scan_interval_minutes)

    def stop(self):
        if self._job is not None:
            self._job = None
        if getattr(self.scheduler, "running", False):
            self.scheduler.shutdown(wait=False)
            logger.info("止盈提醒服务已停止")

    @staticmethod
    def _get_db():
        return get_mongo_db()

    def run_once(self):
        watch_items = self._load_watch_items()
        if not watch_items:
            logger.info("[Take profit reminder] No configured take profit reminder")
            return

        notified = 0
        for item in watch_items:
            stop_gain = self._extract_stop_gain(item)
            if stop_gain and self._check_and_notify(item, stop_gain):
                notified += 1

        if notified:
            logger.info("[Take profit reminder] Send %s reminders this round", notified)
        else:
            logger.info("[Take profit reminder] No trigger reminder this round")

    def _load_watch_items(self) -> List[Dict[str, Any]]:
        if not self._loop or self._loop.is_closed():
            logger.warning("[Take profit reminder] No available event loop is set, skip this round of scanning")
            return []

        try:
            future = asyncio.run_coroutine_threadsafe(self._load_watch_items_async(), self._loop)
            return future.result(timeout=20)
        except Exception as e:
            logger.warning("[Take profit reminder] Failed to load monitoring items: %s", e)
            return []

    async def _load_watch_items_async(self) -> List[Dict[str, Any]]:
        """Load the profit-taking monitoring items and fill in the current price in batches."""
        items: List[Dict[str, Any]] = []
        db = self._get_db()

        cursor_users = db.users.find(
            {"favorite_stocks.alert_gain_price": {"$ne": None}},
            {"_id": 1, "favorite_stocks": 1},
        )
        async for u in cursor_users:
            user_id = str(u.get("_id"))
            for fav in u.get("favorite_stocks", []) or []:
                gain = fav.get("alert_gain_price")
                code = str(fav.get("stock_code") or "").strip()
                if gain is None or not code:
                    continue
                items.append(
                    {
                        "user_id": user_id,
                        "symbol": code,
                        "stock_name": fav.get("stock_name") or code,
                        "market": self._normalize_market(fav.get("market")),
                        "alert_gain_price": float(gain),
                    }
                )

        cursor_old = db.user_favorites.find(
            {"favorites.alert_gain_price": {"$ne": None}},
            {"user_id": 1, "favorites": 1},
        )
        async for d in cursor_old:
            user_id = str(d.get("user_id") or "").strip()
            if not user_id:
                continue
            for fav in d.get("favorites", []) or []:
                gain = fav.get("alert_gain_price")
                code = str(fav.get("stock_code") or "").strip()
                if gain is None or not code:
                    continue
                items.append(
                    {
                        "user_id": user_id,
                        "symbol": code,
                        "stock_name": fav.get("stock_name") or code,
                        "market": self._normalize_market(fav.get("market")),
                        "alert_gain_price": float(gain),
                    }
                )

        if not items:
            return []

        await self._fill_current_prices(items, db)
        return items

    async def _fill_current_prices(self, items: List[Dict[str, Any]], db) -> None:
        grouped: Dict[str, List[str]] = {"CN": [], "HK": [], "US": []}
        for item in items:
            market = item.get("market", "CN")
            symbol = item.get("symbol")
            if symbol:
                grouped.setdefault(market, []).append(symbol)

        quotes_cn: Dict[str, Dict[str, Any]] = {}
        quotes_hk: Dict[str, Dict[str, Any]] = {}
        quotes_us: Dict[str, Dict[str, Any]] = {}

        if grouped.get("CN"):
            cn_docs = await db.market_quotes.find(
                {"code": {"$in": grouped["CN"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_cn = {str(d.get("code")).zfill(6): d for d in (cn_docs or [])}

        if grouped.get("HK"):
            hk_docs = await db.market_quotes_hk.find(
                {"code": {"$in": grouped["HK"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_hk = {str(d.get("code")): d for d in (hk_docs or [])}

        if grouped.get("US"):
            us_docs = await db.market_quotes_us.find(
                {"code": {"$in": grouped["US"]}}, {"code": 1, "close": 1}
            ).to_list(length=None)
            quotes_us = {str(d.get("code")): d for d in (us_docs or [])}

        for item in items:
            market = item.get("market", "CN")
            symbol = str(item.get("symbol") or "")
            quote = None
            if market == "CN":
                quote = quotes_cn.get(symbol.zfill(6))
            elif market == "HK":
                quote = quotes_hk.get(symbol)
            else:
                quote = quotes_us.get(symbol)
            item["current_price"] = quote.get("close") if quote else None

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        m = (market or "CN").upper().strip()
        if m in ("A股", "CN", "SH", "SZ", "BJ"):
            return "CN"
        if m in ("港股", "HK"):
            return "HK"
        if m in ("美股", "US"):
            return "US"
        return "CN"

    def _extract_stop_gain(self, item):
        if "alert_gain_price" in item and item["alert_gain_price"]:
            return item["alert_gain_price"]
        if "analysis_report" in item and item["analysis_report"]:
            report = item["analysis_report"]
            if isinstance(report, dict) and "stop_gain" in report:
                return report["stop_gain"]
        return None

    def _check_and_notify(self, item, stop_gain) -> bool:
        current_price = item.get("current_price")
        if current_price is None or current_price < stop_gain:
            return False

        user_id = item.get("user_id")
        symbol = item.get("symbol", "")
        stock_name = item.get("stock_name") or symbol
        if not user_id:
            return False

        payload = NotificationCreate(
            user_id=str(user_id),
            type="alert",
            title=f"止盈提醒：{stock_name}({symbol}) 已达到止盈线",
            content=f"当前价格 {current_price:.2f} 已达到止盈线 {stop_gain:.2f}，请关注。",
            source="stop_gain_alert",
            severity="success",
            metadata={
                "stock_code": symbol,
                "current_price": current_price,
                "stop_gain_price": stop_gain,
            },
        )
        if self._loop and not self._loop.is_closed():
            try:
                async def _publish():
                    await get_notifications_service().create_and_publish(payload)

                asyncio.run_coroutine_threadsafe(_publish(), self._loop)
                return True
            except Exception as e:
                logger.warning("Take profit reminder failed to push(ignore): %s", e)
                return False

        logger.debug("Take profit reminder skip push: not set or turned off event_loop")
        return False


stop_gain_alert_service = StopGainAlertService()

# === stop_loss_alert_service.py ===
"""
Stop loss reminder service

Periodically scan the stop loss reminder (alert_price_low) set by the user,
Create notifications when price approaches or falls below a threshold.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from app.core.database import get_mongo_db
from app.models.notification import NotificationCreate
try:
    from app.services.notifications_service import get_notifications_service
except ImportError:
    get_notifications_service = None
from app.utils.timezone import now_tz

logger = logging.getLogger("app.services.stop_loss_alert_service")


class StopLossAlertService:
    def __init__(self):
        self.db = get_mongo_db()
        self.state_collection = "stop_loss_alert_states"

    async def ensure_indexes(self) -> None:
        try:
            await self.db[self.state_collection].create_index([("key", 1)], unique=True)
            await self.db[self.state_collection].create_index([("updated_at", -1)])
        except Exception as e:
            logger.warning("Failed to create stop loss reminder index(ignore): %s", e)

    async def run_once(self, near_pct: float = 0.02, cooldown_minutes: int = 180) -> None:
        """Perform a stop loss alert scan."""
        await self.ensure_indexes()

        watch_items = await self._load_watch_items()
        if not watch_items:
            logger.info("[Stop loss reminder] No stop loss reminder configured")
            return

        quotes = await self._load_quotes(watch_items)
        now = now_tz()
        notified = 0

        for item in watch_items:
            user_id = item["user_id"]
            code = item["code"]
            market = item["market"]
            stock_name = item.get("stock_name") or code
            threshold = item["alert_price_low"]

            current_price = self._get_price(quotes, market, code)
            if current_price is None:
                continue

            state = "safe"
            if current_price <= threshold:
                state = "below"
            elif current_price <= threshold * (1 + near_pct):
                state = "near"

            key = f"{user_id}:{market}:{code}"
            prev = await self.db[self.state_collection].find_one({"key": key})
            prev_state = prev.get("state") if prev else "safe"
            last_alert_at = prev.get("last_alert_at") if prev else None

            should_notify = False
            if state in ("near", "below"):
                if prev_state != state:
                    should_notify = True
                elif last_alert_at and now - last_alert_at >= timedelta(minutes=cooldown_minutes):
                    should_notify = True

            if should_notify:
                title = f"Stop loss reminder:{stock_name}({code})"
                if state == "below":
                    content = (
                        f"当前价 {current_price:.2f} 已跌破止损线 {threshold:.2f}，"
                        "It is recommended to check the position and risk control immediately."
                    )
                    severity = "error"
                else:
                    content = (
                        f"当前价 {current_price:.2f} 接近止损线 {threshold:.2f}，"
                        "Please monitor price fluctuations."
                    )
                    severity = "warning"

                await get_notifications_service().create_and_publish(
                    NotificationCreate(
                        user_id=user_id,
                        type="alert",
                        title=title,
                        content=content,
                        source="stop_loss_alert",
                        severity=severity,
                        metadata={
                            "stock_code": code,
                            "market": market,
                            "current_price": current_price,
                            "stop_loss_price": threshold,
                            "state": state,
                        },
                    )
                )
                notified += 1

            set_fields = {
                "key": key,
                "user_id": user_id,
                "code": code,
                "market": market,
                "stock_name": stock_name,
                "threshold": threshold,
                "state": state,
                "current_price": current_price,
                "updated_at": now,
            }
            if should_notify:
                set_fields["last_alert_at"] = now

            await self.db[self.state_collection].update_one(
                {"key": key},
                {
                    "$set": set_fields,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

        if notified:
            logger.info("[Price lower limit reminder] Send %s reminders this round", notified)
        else:
            logger.info("[Price lower limit reminder] No trigger reminder this round")

    async def _load_watch_items(self) -> List[Dict[str, Any]]:
        """Load reminder monitoring items.

        Priority:
        1) alert_price_low (favorites) manually set by the user
        2) Risk focus prices in the latest position analysis report (position_analysis_reports)
        """
        items: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # New structure:users.favorite_stocks
        cursor_users = self.db.users.find(
            {"favorite_stocks.alert_price_low": {"$ne": None}},
            {"_id": 1, "favorite_stocks": 1},
        )
        async for u in cursor_users:
            user_id = str(u.get("_id"))
            for fav in u.get("favorite_stocks", []) or []:
                low = fav.get("alert_price_low")
                code = str(fav.get("stock_code") or "").strip()
                if low is None or not code:
                    continue
                market = self._normalize_market(fav.get("market"))
                key = (user_id, market, code)
                items[key] = {
                    "user_id": user_id,
                    "code": code,
                    "market": market,
                    "stock_name": fav.get("stock_name") or code,
                    "alert_price_low": float(low),
                }

        # Old structure:user_favorites.favorites
        cursor_old = self.db.user_favorites.find(
            {"favorites.alert_price_low": {"$ne": None}},
            {"user_id": 1, "favorites": 1},
        )
        async for d in cursor_old:
            user_id = str(d.get("user_id") or "").strip()
            if not user_id:
                continue
            for fav in d.get("favorites", []) or []:
                low = fav.get("alert_price_low")
                code = str(fav.get("stock_code") or "").strip()
                if low is None or not code:
                    continue
                market = self._normalize_market(fav.get("market"))
                key = (user_id, market, code)
                if key not in items:
                    items[key] = {
                        "user_id": user_id,
                        "code": code,
                        "market": market,
                        "stock_name": fav.get("stock_name") or code,
                        "alert_price_low": float(low),
                    }

        # For stocks that have not manually set alerts: use the risk-focused prices in the latest position analysis report
        manual_keys = set(items.keys())
        pipeline = [
            {
                "$match": {
                    "position_type": "real",
                    "status": "completed",
                    "ai_analysis.price_targets": {"$exists": True},
                }
            },
            {"$sort": {"created_at": -1}},
            {
                "$group": {
                    "_id": {"user_id": "$user_id", "position_id": "$position_id"},
                    "doc": {"$first": "$$ROOT"},
                }
            },
        ]

        latest_reports = await self.db.position_analysis_reports.aggregate(pipeline).to_list(length=None)
        for row in latest_reports:
            doc = row.get("doc") or {}
            user_id = str((doc.get("user_id") or "")).strip()
            position_id = str((doc.get("position_id") or "")).strip()  # e.g. 300033_CN
            if not user_id or "_" not in position_id:
                continue

            code, market = position_id.rsplit("_", 1)
            market = self._normalize_market(market)
            key = (user_id, market, code)
            if key in manual_keys:
                continue

            price_targets = (doc.get("ai_analysis") or {}).get("price_targets") or {}
            stop_loss = self._extract_stop_loss(price_targets)
            if stop_loss is None:
                continue

            snapshot = doc.get("position_snapshot") or {}
            items[key] = {
                "user_id": user_id,
                "code": code,
                "market": market,
                "stock_name": snapshot.get("name") or code,
                "alert_price_low": float(stop_loss),
            }

        return list(items.values())

    @staticmethod
    def _extract_stop_loss(price_targets: Dict[str, Any]) -> float | None:
        """Compatible with multiple field names to extract risk and focus prices."""
        candidates = [
            price_targets.get("stop_loss"),
            price_targets.get("stop_loss_price"),
            price_targets.get("stopLoss"),
        ]
        for v in candidates:
            try:
                if v is not None:
                    return float(v)
            except Exception:
                continue
        return None

    async def _load_quotes(self, watch_items: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        market_codes: Dict[str, List[str]] = {"CN": [], "HK": [], "US": []}
        for item in watch_items:
            market_codes.setdefault(item["market"], []).append(item["code"])

        quotes: Dict[str, Dict[str, float]] = {"CN": {}, "HK": {}, "US": {}}

        if market_codes.get("CN"):
            docs = await self.db.market_quotes.find(
                {"code": {"$in": list(set(market_codes["CN"]))}},
                {"code": 1, "close": 1},
            ).to_list(length=None)
            quotes["CN"] = {str(d.get("code")).zfill(6): float(d.get("close")) for d in docs if d.get("close") is not None}

        if market_codes.get("HK"):
            docs = await self.db.market_quotes_hk.find(
                {"code": {"$in": list(set(market_codes["HK"]))}},
                {"code": 1, "close": 1},
            ).to_list(length=None)
            quotes["HK"] = {str(d.get("code")): float(d.get("close")) for d in docs if d.get("close") is not None}

        if market_codes.get("US"):
            docs = await self.db.market_quotes_us.find(
                {"code": {"$in": list(set(market_codes["US"]))}},
                {"code": 1, "close": 1},
            ).to_list(length=None)
            quotes["US"] = {str(d.get("code")): float(d.get("close")) for d in docs if d.get("close") is not None}

        return quotes

    @staticmethod
    def _normalize_market(market: Any) -> str:
        m = str(market or "CN").upper()
        if m in ("A股", "CN", "SH", "SZ"):
            return "CN"
        if m in ("港股", "HK"):
            return "HK"
        if m in ("美股", "US"):
            return "US"
        return "CN"

    @staticmethod
    def _get_price(quotes: Dict[str, Dict[str, float]], market: str, code: str):
        if market == "CN":
            return quotes.get("CN", {}).get(str(code).zfill(6))
        if market == "HK":
            return quotes.get("HK", {}).get(str(code))
        if market == "US":
            return quotes.get("US", {}).get(str(code))
        return None


_stop_loss_alert_service: StopLossAlertService | None = None


def get_stop_loss_alert_service() -> StopLossAlertService:
    global _stop_loss_alert_service
    if _stop_loss_alert_service is None:
        _stop_loss_alert_service = StopLossAlertService()
    return _stop_loss_alert_service

# === trade_review_service.py ===
"""
Transaction review service
Provide transaction review and periodic review functions
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

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
            logger.info("📊 [Create review] Detect transactions in positions and calculate floating profit and loss...")
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
            logger.info("📊 [Review v2.0] Detect transactions in positions and calculate floating profit and loss...")
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

        logger.info("📊 [_build_trade_info] Statistical results:")
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

        logger.info("📊 [_build_trade_info] Position status:")
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
                logger.info("✅ Account information has been added to transaction information")
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
                logger.info("🔄 [Transaction review] Use workflow engines for multi-dimensional analysis (v2.0)")
                return await self._call_workflow_trade_review(
                    trade_info, market_snapshot, user_id, trading_system,
                    progress_callback=progress_callback  # 🔥 Pass progress callback
                )
            except Exception as e:
                import traceback
                logger.warning(f"⚠️ [Transaction review] Workflow engine execution fails and is downgraded to a single LLM call: {e}")
                logger.warning(f"⚠️ [Transaction review] Full stack trace:\n{traceback.format_exc()}")
                # Downgrade to a single LLM call

        logger.info("📝 [Transaction review] Use traditional analysis methods (v1.0)")

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
                    logger.info("📊 [Transaction review] Obtaining benchmark data is completed")
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
            logger.info("🔧 [AI Review] Start creating an LLM instance...")
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
            logger.info("🚀 [AI Review] Start calling LLM API...")
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

            logger.info("✅ [AI Review] LLM API Call successful")
            logger.info(f"📦 [AI Review] Response Type: {type(response).__name__}")
            logger.info(f"📦 [AI Review] Response Properties: {dir(response)}")

            content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📄 [AI复盘] 返回内容长度: {len(content)} 字符")
            logger.info(f"📄 [AI Review] Return the first 500 characters of the content:\n{content[:500]}")
            logger.info(f"📄 [AI Review] Return 500 characters after content:\n{content[-500:]}")

            logger.info("🔍 [AI Review] Start parsing AI responses...")
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
        logger.info("🔍 [Parse AI responses] Try to extract JSON code block...")
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)

        if json_match:
            logger.info("✅ [Parse AI responses] Find the JSON code block")
            json_str = json_match.group(1)
            logger.info(f"📄 [Parse AI responses] JSON content length: {len(json_str)}")
            logger.info(f"📄 [Parse AI responses] JSON The first 500 characters of the content:\n{json_str[:500]}")

            try:
                data = json.loads(json_str)
                logger.info("✅ [Parse AI responses] JSON Parsed successfully")
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
            logger.warning("⚠️ [Parse AI responses] JSON code block not found")
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
                logger.warning("⚠️ [Review] No market data was obtained")

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

        logger.info("🚀 [Workflow review] Start execution of transaction review workflow")

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
            logger.info("📊 [Workflow review] Obtaining benchmark data is completed")
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
            logger.info("✅ [Workflow review] trading_plan added to inputs")
            logger.info(f"   - plan_name: {formatted_plan.get('plan_name', 'N/A')}")
            logger.info(f"   - rules_text length: {len(formatted_plan.get('rules_text', ''))}")
        else:
            logger.info("📋 [Workflow review] Unlinked transaction plan")

        logger.info("📝 [Workflow review] Workflow input is ready")
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
                    logger.warning("⚠️ [Workflow review] Unable to get full model configuration, only set model name")
            else:
                logger.warning("⚠️ [Workflow review] system_settings quick_analysis_model or deep_analysis_model not found, use default configuration")
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

        logger.info("🚀 [Workflow review] Start executing workflow...")
        logger.error(f"🔍 [Workflow review] inputs keys: {list(inputs.keys())}, ticker={inputs.get('ticker')}, trade_info exist={('trade_info' in inputs)}, trade_info_code={inputs.get('trade_info', {}).get('code') if isinstance(inputs.get('trade_info'), dict) else 'N/A'}")
        # 🔥 Key fix: Use asyncio.to_thread to execute synchronous workflows in separate threads
        # Avoid blocking the uvicorn event loop (this is also done for single stock analysis)
        result = await asyncio.to_thread(engine.execute, inputs=inputs, progress_callback=workflow_progress_callback)

        logger.info("✅ [Workflow review] Workflow execution completed")
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

        logger.info("🔍 [Workflow review] Parse workflow results")
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
            logger.info("📄 [AI Review] review_summary is a dictionary, extract the content field")
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
                logger.info("✅ [AI Review] JSON match found")
                try:
                    json_str = json_match.group(1)
                    logger.info(f"📄 [AI Review] JSON The first 500 characters of the string: {json_str[:500]}")
                    logger.info(f"📄 [AI Review] JSON 500 characters after string: {json_str[-500:]}")
                    data = json.loads(json_str)
                    logger.info(f"📄 [AI Review] JSON Parsed successfully, top-level key: {list(data.keys())}")

                    # 🔧 Handle nested JSON structures (such as {"Review report": {...}}) 
                    if len(data) == 1 and isinstance(list(data.values())[0], dict):
                        logger.info("📄 [AI Review] Detect nested structures and extract inner data")
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
                logger.warning("⚠️ [AI Review] No JSON match found")

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


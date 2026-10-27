from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
import re

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from app.services.database.serialization import serialize_document

router = APIRouter(prefix="/paper", tags=["paper"])
logger = logging.getLogger("webapi")

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


# Initial capital allocation per market
INITIAL_CASH_BY_MARKET = {
    "CNY": 1_000_000.0,   # A Shares: 1 million RMB
    "HKD": 1_000_000.0,   # Hong Kong stocks: HKD 1 million
    "USD": 100_000.0      # U.S. stocks: $100,000
}


class PlaceOrderRequest(BaseModel):
    code: str = Field(..., description="Stock code (supports A shares/ETF/Hong Kong stocks/US stocks)")
    side: Literal["buy", "sell"]
    quantity: int = Field(..., gt=0)
    market: Optional[str] = Field(None, description="market type (CN/ETF/HK/US), If not passed, it will be automatically recognized.")
    # Optional: Specify price (if not specified, current real-time price is used)
    price: Optional[float] = Field(None, description="Specify price (must be between the highest and lowest price of the day)")
    # Optional: associated analysis ID to facilitate tracking after placing an order with one click from the analysis page
    analysis_id: Optional[str] = None


def _detect_market_and_code(code: str) -> Tuple[str, str]:
    """
    Detect the market type of a ticker and standardize the ticker

    Returns:
        (market, normalized_code): Market types and standardized codes
            - CN: A Share (6 digits)
            - HK: Hong Kong stocks (4-5 digits or with .HK suffix)
            - US: US stocks (letter code)
    """
    code = code.strip().upper()

    # Hong Kong stocks: with .HK suffix
    if code.endswith('.HK'):
        return ('HK', code[:-3].zfill(5))

    # US stocks: pure letters
    if re.match(r'^[A-Z]+$', code):
        return ('US', code)

    # Hong Kong stocks: 4-5 digits
    if re.match(r'^\d{4,5}$', code):
        return ('HK', code.zfill(5))

    # A Share: 6 digits
    if re.match(r'^\d{6}$', code):
        return ('CN', code)

    # By default, it is treated as A shares, and 6 digits are added.
    return ('CN', code.zfill(6))


def _is_cn_etf_symbol(code: str) -> bool:
    code_str = str(code or "").strip().upper().zfill(6)
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _resolve_market_and_code(code: str, market: Optional[str] = None) -> Tuple[str, str, bool]:
    normalized_code = str(code or "").strip().upper()
    requested_market = str(market or "").strip().upper()

    if requested_market == "ETF":
        normalized_code = normalized_code.zfill(6)
        return "CN", normalized_code, True

    if requested_market in {"CN", "HK", "US"}:
        if requested_market == "CN":
            normalized_code = normalized_code.zfill(6)
        elif requested_market == "HK" and normalized_code.endswith('.HK'):
            normalized_code = normalized_code[:-3].zfill(5)
        return requested_market, normalized_code, requested_market == "CN" and _is_cn_etf_symbol(normalized_code)

    detected_market, normalized_code = _detect_market_and_code(code)
    is_etf = detected_market == "CN" and _is_cn_etf_symbol(normalized_code)
    return detected_market, normalized_code, is_etf


async def _get_or_create_account(user_id: str) -> Dict[str, Any]:
    """Get or create an account (multi-currency)"""
    db = get_mongo_db()
    acc = await db["paper_accounts"].find_one({"user_id": user_id})
    if not acc:
        now = datetime.utcnow().isoformat()
        acc = {
            "user_id": user_id,
            # Multi-currency cash account
            "cash": {
                "CNY": INITIAL_CASH_BY_MARKET["CNY"],
                "HKD": INITIAL_CASH_BY_MARKET["HKD"],
                "USD": INITIAL_CASH_BY_MARKET["USD"]
            },
            # Achieved profit and loss in multiple currencies
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            # Account settings
            "settings": {
                "auto_currency_conversion": False,
                "default_market": "CN"
            },
            "created_at": now,
            "updated_at": now,
        }
        await db["paper_accounts"].insert_one(acc)
    else:
        # Compatible with old account structures: if cash or realized_pnl are still scalars, migrate to multi-currency objects
        updates: Dict[str, Any] = {}
        try:
            cash_val = acc.get("cash")
            if not isinstance(cash_val, dict):
                base_cash = float(cash_val or 0.0)
                updates["cash"] = {"CNY": base_cash, "HKD": 0.0, "USD": 0.0}

            pnl_val = acc.get("realized_pnl")
            if not isinstance(pnl_val, dict):
                base_pnl = float(pnl_val or 0.0)
                updates["realized_pnl"] = {"CNY": base_pnl, "HKD": 0.0, "USD": 0.0}

            if updates:
                updates["updated_at"] = datetime.utcnow().isoformat()
                await db["paper_accounts"].update_one({"user_id": user_id}, {"$set": updates})
                # Reread migrated accounts
                acc = await db["paper_accounts"].find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"❌ Account structure migration failed user_id={user_id}: {e}")

    if acc:
        acc = serialize_document(acc)

    return acc


async def _get_market_rules(market: str) -> Optional[Dict[str, Any]]:
    """Get market rule configuration"""
    db = get_mongo_db()
    rules_doc = await db["paper_market_rules"].find_one({"market": market})
    if rules_doc:
        return rules_doc.get("rules", {})
    return None


def _calculate_commission(market: str, side: str, amount: float, rules: Dict[str, Any]) -> float:
    """Calculate handling fees"""
    if not rules or "commission" not in rules:
        return 0.0

    commission_config = rules["commission"]
    commission = 0.0

    # Commission
    comm_rate = commission_config.get("rate", 0.0)
    comm_min = commission_config.get("min", 0.0)
    commission += max(amount * comm_rate, comm_min)

    # Stamp duty (sale only)
    if side == "sell" and "stamp_duty_rate" in commission_config:
        commission += amount * commission_config["stamp_duty_rate"]

    # Other expenses (Hong Kong stocks)
    if market == "HK":
        if "transaction_levy_rate" in commission_config:
            commission += amount * commission_config["transaction_levy_rate"]
        if "trading_fee_rate" in commission_config:
            commission += amount * commission_config["trading_fee_rate"]
        if "settlement_fee_rate" in commission_config:
            commission += amount * commission_config["settlement_fee_rate"]

    # SEC Fees (US stocks, sell only)
    if market == "US" and side == "sell" and "sec_fee_rate" in commission_config:
        commission += amount * commission_config["sec_fee_rate"]

    return round(commission, 2)


async def _get_available_quantity(user_id: str, code: str, market: str) -> int:
    """Get the available quantity (consider T+1 restrictions)"""
    db = get_mongo_db()
    pos = await db["paper_positions"].find_one({"user_id": user_id, "code": code})

    if not pos:
        return 0

    total_qty = pos.get("quantity", 0)

    # A shares T+1: What you bought today cannot be sold
    if market == "CN":
        # Get market rules
        rules = await _get_market_rules(market)
        if rules and rules.get("t_plus", 0) > 0:
            # Check today's buying quantity
            today = datetime.utcnow().date().isoformat()
            pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "code": code,
                    "side": "buy",
                    "timestamp": {"$gte": today}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
            ]
            today_buy = await db["paper_trades"].aggregate(pipeline).to_list(1)
            today_buy_qty = today_buy[0]["total"] if today_buy else 0
            return max(0, total_qty - today_buy_qty)

    # Hong Kong stocks/US stocks T+0: All available
    return total_qty


async def _get_stock_name(code: str, market: str) -> str:
    """
    Get stock name (supports multiple markets)

    - A Stock: Obtained from stock_basic_info table
    - Hong Kong stocks/US stocks: use ForeignStockService.get_quote() (name field included)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        Stock name
    """
    try:
        # A Stock: Obtained from stock_basic_info
        if market in {"CN", "ETF"}:
            db = get_mongo_db()
            code6 = str(code or "").strip().zfill(6)
            stock_info = await db["stock_basic_info"].find_one({
                "$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]
            })
            if stock_info and stock_info.get("name"):
                return stock_info.get("name")
            etf_info = await db["etf_basic_info"].find_one({"code": code6}, {"_id": 0, "name": 1})
            if etf_info and etf_info.get("name"):
                return etf_info.get("name")
            return f"A shares{code}"

        # Hong Kong stocks/US stocks: Use ForeignStockService (reuse the obtained market data)
        elif market in ["HK", "US"]:
            try:
                from app.services.foreign_stock_service import ForeignStockService
                db = get_mongo_db()
                service = ForeignStockService(db=db)

                # Get market information (will be read from the cache first to avoid repeated API calls)
                quote = await service.get_quote(market, code, force_refresh=False)

                if quote and quote.get("name"):
                    name = quote.get("name")
                    # Avoid returning names in default format
                    if not name.startswith("Hong Kong stocks") and not name.startswith("US stocks"):
                        return name

                return f"{'Hong Kong stocks' if market == 'HK' else 'US stocks'}{code}"
            except Exception as e:
                logger.warning(f"⚠️ {market}Failed to obtain stock name {code}: {e}")
                return f"{'Hong Kong stocks' if market == 'HK' else 'US stocks'}{code}"

        else:
            return f"stocks{code}"

    except Exception as e:
        logger.error(f"❌ Failed to get stock name {code} ({market}): {e}")
        return f"stocks{code}"


async def _get_last_price(code: str, market: str) -> Optional[float]:
    """
    Get the latest stock price (supports multiple markets)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        The latest price, returned if the acquisition fails None
    """
    db = get_mongo_db()

    # A Shares: obtained from database
    if market in {"CN", "ETF"}:
        code6 = str(code or "").strip().zfill(6)
        # 1. Try to get from market_quotes
        q = await db["market_quotes"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "close": 1}
        )
        if q and q.get("close") is not None:
            try:
                price = float(q["close"])
                if price > 0:
                    logger.debug(f"✅ Get prices from market_quotes: {code} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ market_quotes Price conversion failed {code}: {e}")

        # 2. Fallback to stock_basic_info current_price
        basic_info = await db["stock_basic_info"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "current_price": 1}
        )
        if basic_info and basic_info.get("current_price") is not None:
            try:
                price = float(basic_info["current_price"])
                if price > 0:
                    logger.debug(f"✅ Get prices from stock_basic_info: {code} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ stock_basic_info Price conversion failed {code}: {e}")

        etf_daily = await db["etf_daily_quotes"].find_one(
            {"code": code6},
            sort=[("trade_date", -1)],
            projection={"_id": 0, "close": 1}
        )
        if etf_daily and etf_daily.get("close") is not None:
            try:
                price = float(etf_daily["close"])
                if price > 0:
                    logger.debug(f"✅ Get prices from etf_daily_quotes: {code6} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ etf_daily_quotes Price conversion failed {code6}: {e}")

        logger.error(f"❌ Unable to obtain A-share/ETF price from database: {code}")
        return None

    # Hong Kong stocks/US stocks: use ForeignStockService
    elif market in ['HK', 'US']:
        try:
            from app.services.foreign_stock_service import ForeignStockService
            db = get_mongo_db()
            service = ForeignStockService(db=db)

            quote = await service.get_quote(market, code, force_refresh=False)

            if quote:
                # Try multiple possible price fields
                price = quote.get("price") or quote.get("current_price") or quote.get("close")
                if price and float(price) > 0:
                    logger.debug(f"✅ Get from ForeignStockService{market}price: {code} = {price}")
                    return float(price)
        except Exception as e:
            logger.error(f"❌ get{market}stock price failure {code}: {e}")
            return None

    logger.error(f"❌ Unable to get stock price: {code} (market={market})")
    return None


async def _get_today_price_range(code: str, market: str) -> Optional[Dict[str, float]]:
    """
    Get the highest and lowest price of the stock on the day (supports multiple markets)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        A dictionary containing high and low, returned if acquisition fails None
    """
    db = get_mongo_db()

    # A Shares: obtained from market_quotes
    if market in {"CN", "ETF"}:
        code6 = str(code or "").strip().zfill(6)
        q = await db["market_quotes"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "high": 1, "low": 1}
        )
        if q:
            try:
                high = float(q.get("high", 0)) if q.get("high") is not None else None
                low = float(q.get("low", 0)) if q.get("low") is not None else None
                if high is not None and low is not None and high > 0 and low > 0:
                    logger.debug(f"✅ Get price range from market_quotes: {code} = high:{high}, low:{low}")
                    return {"high": high, "low": low}
            except Exception as e:
                logger.warning(f"⚠️ market_quotes Price range conversion failed {code}: {e}")

        etf_daily = await db["etf_daily_quotes"].find_one(
            {"code": code6},
            sort=[("trade_date", -1)],
            projection={"_id": 0, "high": 1, "low": 1, "open": 1, "close": 1}
        )
        if etf_daily:
            try:
                high = etf_daily.get("high")
                low = etf_daily.get("low")
                if high is None or low is None:
                    open_price = etf_daily.get("open")
                    close_price = etf_daily.get("close")
                    if open_price is not None and close_price is not None:
                        high = max(float(open_price), float(close_price))
                        low = min(float(open_price), float(close_price))
                high_val = float(high) if high is not None else None
                low_val = float(low) if low is not None else None
                if high_val is not None and low_val is not None and high_val > 0 and low_val > 0:
                    logger.debug(f"✅ Get price range from etf_daily_quotes: {code6} = high:{high_val}, low:{low_val}")
                    return {"high": high_val, "low": low_val}
            except Exception as e:
                logger.warning(f"⚠️ etf_daily_quotes Price range conversion failed {code6}: {e}")

        logger.warning(f"⚠️ Unable to obtain the A-share/ETF price range from the database: {code}")
        return None

    # Hong Kong stocks/US stocks: use ForeignStockService
    elif market in ['HK', 'US']:
        try:
            from app.services.foreign_stock_service import ForeignStockService
            service = ForeignStockService(db=db)

            quote = await service.get_quote(market, code, force_refresh=False)

            if quote:
                high = quote.get("high") or quote.get("day_high")
                low = quote.get("low") or quote.get("day_low")
                if high and low:
                    try:
                        high_val = float(high)
                        low_val = float(low)
                        if high_val > 0 and low_val > 0:
                            logger.debug(f"✅ Get from ForeignStockService{market}price range: {code} = high:{high_val}, low:{low_val}")
                            return {"high": high_val, "low": low_val}
                    except Exception as e:
                        logger.warning(f"⚠️ {market}Stock price range conversion failed {code}: {e}")
        except Exception as e:
            logger.error(f"❌ get{market}stock price range failure {code}: {e}")
            return None

    logger.warning(f"⚠️ Unable to get stock price range: {code} (market={market})")
    return None


def _zfill_code(code: str) -> str:
    s = str(code).strip()
    if len(s) == 6 and s.isdigit():
        return s
    return s.zfill(6)


@router.get("/account", response_model=dict)
async def get_account(current_user: dict = Depends(get_current_user)):
    """Obtain or create a paper account, return funds and position valuation summary (supports multiple markets)"""
    db = get_mongo_db()
    acc = await _get_or_create_account(current_user["id"])

    # Aggregated position valuation by currency
    positions = await db["paper_positions"].find({"user_id": current_user["id"]}).to_list(None)

    positions_value_by_currency = {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    }

    detailed_positions: List[Dict[str, Any]] = []
    for p in positions:
        code = p.get("code")
        name = p.get("name", "")  # Get stock name from database
        market = p.get("market", "CN")
        currency = p.get("currency", "CNY")
        qty = int(p.get("quantity", 0))
        avg_cost = float(p.get("avg_cost", 0.0))
        available_qty = p.get("available_qty", qty)

        # Get the latest price
        last = await _get_last_price(code, market)
        mkt_value = round((last or 0.0) * qty, 2)
        positions_value_by_currency[currency] += mkt_value

        detailed_positions.append({
            "code": code,
            "name": name,  # Add stock name to response
            "market": market,
            "currency": currency,
            "quantity": qty,
            "available_qty": available_qty,
            "avg_cost": avg_cost,
            "last_price": last,
            "market_value": mkt_value,
            "unrealized_pnl": None if last is None else round((last - avg_cost) * qty, 2)
        })

    # Calculate total assets (displayed separately by currency)
    cash = acc.get("cash", {})
    realized_pnl = acc.get("realized_pnl", {})

    # Compatible with old formats (single cash)
    if not isinstance(cash, dict):
        cash = {"CNY": float(cash), "HKD": 0.0, "USD": 0.0}
    if not isinstance(realized_pnl, dict):
        realized_pnl = {"CNY": float(realized_pnl), "HKD": 0.0, "USD": 0.0}

    summary = {
        "cash": {
            "CNY": round(float(cash.get("CNY", 0.0)), 2),
            "HKD": round(float(cash.get("HKD", 0.0)), 2),
            "USD": round(float(cash.get("USD", 0.0)), 2)
        },
        "realized_pnl": {
            "CNY": round(float(realized_pnl.get("CNY", 0.0)), 2),
            "HKD": round(float(realized_pnl.get("HKD", 0.0)), 2),
            "USD": round(float(realized_pnl.get("USD", 0.0)), 2)
        },
        "positions_value": positions_value_by_currency,
        "equity": {
            "CNY": round(float(cash.get("CNY", 0.0)) + positions_value_by_currency["CNY"], 2),
            "HKD": round(float(cash.get("HKD", 0.0)) + positions_value_by_currency["HKD"], 2),
            "USD": round(float(cash.get("USD", 0.0)) + positions_value_by_currency["USD"], 2)
        },
        "updated_at": acc.get("updated_at"),
    }

    return ok({"account": summary, "positions": detailed_positions})


@router.post("/order", response_model=dict)
async def place_order(payload: PlaceOrderRequest, current_user: dict = Depends(get_current_user)):
    """Submit a market price order and the transaction will be completed immediately at the latest price (supports multiple markets)"""
    db = get_mongo_db()

    # 1. Identify market type
    market, normalized_code, is_etf = _resolve_market_and_code(payload.code, payload.market)

    side = payload.side
    qty = int(payload.quantity)
    analysis_id = payload.analysis_id if hasattr(payload, "analysis_id") else None
    # 🔥 Fix: Get price field directly from Pydantic model (Pydantic model can access the field directly)
    specified_price = payload.price
    
    logger.info(f"📊 [Simulated trading order] Request received: code={normalized_code}, market={market}, is_etf={is_etf}, side={side}, qty={qty}, specified_price={specified_price}")

    # 2. Determine currency
    currency_map = {
        "CN": "CNY",
        "HK": "HKD",
        "US": "USD"
    }
    currency = currency_map.get(market, "CNY")

    # 3. Get an account
    acc = await _get_or_create_account(current_user["id"])

    # 4. get price
    if specified_price is not None and specified_price > 0:
        # 🔥 If a price is specified, verify whether the price is within the range of the highest and lowest prices of the day
        price_range = await _get_today_price_range(normalized_code, market)
        if not price_range:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to get stock {normalized_code} ({market}) of the day s price range, the specified price cannot be verified"
            )
        
        high = price_range.get("high", 0)
        low = price_range.get("low", 0)
        
        if specified_price < low or specified_price > high:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specify price {specified_price:.2f} Exceeding the price range of the day [{low:.2f}, {high:.2f}], Simulated trading cannot be successful"
            )
        
        price = float(specified_price)
        logger.info(f"✅ [simulated trading] Use specified price: {normalized_code} = {price:.2f} (interval: [{low:.2f}, {high:.2f}])")
    else:
        # No price specified, current real-time price used
        price = await _get_last_price(normalized_code, market)
        if price is None or price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to get stock {normalized_code} ({market}) latest price"
            )
        logger.info(f"✅ [simulated trading] Use real-time prices: {normalized_code} = {price:.2f}")

    # 5. Calculate amount
    notional = round(price * qty, 2)

    # 6. Get market rules and calculate fees
    rules = await _get_market_rules(market)
    commission = _calculate_commission(market, side, notional, rules) if rules else 0.0
    total_cost = notional + commission

    # 7. Get a position
    pos = await db["paper_positions"].find_one({"user_id": current_user["id"], "code": normalized_code})

    now_iso = datetime.utcnow().isoformat()
    realized_pnl_delta = 0.0

    # 8. Execute buying and selling logic
    if side == "buy":
        # Funds check (account using corresponding currency)
        cash = acc.get("cash", {})
        if isinstance(cash, dict):
            available_cash = float(cash.get(currency, 0.0))
        else:
            # Compatible with older formats
            available_cash = float(cash) if currency == "CNY" else 0.0

        if available_cash < total_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Available{currency}Disadvantage: need {total_cost:.2f}, Available {available_cash:.2f}"
            )

        # Deduct funds (from corresponding currency account)
        new_cash = round(available_cash - total_cost, 2)
        await db["paper_accounts"].update_one(
            {"user_id": current_user["id"]},
            {"$set": {f"cash.{currency}": new_cash, "updated_at": now_iso}}
        )

        # Update/Create Position: Weighted Average Cost
        if not pos:
            # Get stock name (according to market type)
            stock_name = await _get_stock_name(normalized_code, market)

            new_pos = {
                "user_id": current_user["id"],
                "code": normalized_code,
                "name": stock_name,  # Add stock name
                "market": market,
                "currency": currency,
                "quantity": qty,
                "available_qty": qty if market != "CN" else 0,  # A shares T+1, Not available for buying today
                "frozen_qty": 0,
                "avg_cost": price,
                "updated_at": now_iso
            }
            await db["paper_positions"].insert_one(new_pos)
        else:
            old_qty = int(pos.get("quantity", 0))
            old_cost = float(pos.get("avg_cost", 0.0))
            new_qty = old_qty + qty
            new_avg = round((old_cost * old_qty + price * qty) / new_qty, 4) if new_qty > 0 else price

            # A shares T+1: Not available for new purchases
            if market == "CN":
                new_available = pos.get("available_qty", old_qty)  # Keep the original available quantity
            else:
                new_available = new_qty  # Hong Kong stocks/US stocks T+0, All available

            await db["paper_positions"].update_one(
                {"_id": pos["_id"]},
                {"$set": {
                    "quantity": new_qty,
                    "available_qty": new_available,
                    "avg_cost": new_avg,
                    "updated_at": now_iso
                }}
            )

    else:  # sell
        # Check available quantities (consider T+1) 
        available_qty = await _get_available_quantity(current_user["id"], normalized_code, market)
        if available_qty < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient available positions: required {qty}, Available {available_qty}"
            )

        old_qty = int(pos.get("quantity", 0))
        avg_cost = float(pos.get("avg_cost", 0.0))
        new_qty = old_qty - qty
        pnl = round((price - avg_cost) * qty, 2)
        realized_pnl_delta = pnl

        # Sales income (added to the corresponding currency account, deducting handling fees)
        net_proceeds = notional - commission
        await db["paper_accounts"].update_one(
            {"user_id": current_user["id"]},
            {
                "$inc": {
                    f"cash.{currency}": net_proceeds,
                    f"realized_pnl.{currency}": realized_pnl_delta
                },
                "$set": {"updated_at": now_iso}
            }
        )

        # Update positions
        if new_qty == 0:
            await db["paper_positions"].delete_one({"_id": pos["_id"]})
        else:
            new_available = max(0, pos.get("available_qty", old_qty) - qty)
            await db["paper_positions"].update_one(
                {"_id": pos["_id"]},
                {"$set": {
                    "quantity": new_qty,
                    "available_qty": new_available,
                    "updated_at": now_iso
                }}
            )

    # 9. Record orders and transactions (concluded)
    order_doc = {
        "user_id": current_user["id"],
        "code": normalized_code,
        "market": market,
        "currency": currency,
        "side": side,
        "quantity": qty,
        "price": price,
        "amount": notional,
        "commission": commission,
        "status": "filled",
        "created_at": now_iso,
        "filled_at": now_iso,
    }
    if analysis_id:
        order_doc["analysis_id"] = analysis_id
    await db["paper_orders"].insert_one(order_doc)

    trade_doc = {
        "user_id": current_user["id"],
        "code": normalized_code,
        "market": market,
        "currency": currency,
        "side": side,
        "quantity": qty,
        "price": price,
        "amount": notional,
        "commission": commission,
        "pnl": realized_pnl_delta if side == "sell" else 0.0,
        "timestamp": now_iso,
    }
    if analysis_id:
        trade_doc["analysis_id"] = analysis_id
    await db["paper_trades"].insert_one(trade_doc)

    return ok({"order": {k: v for k, v in order_doc.items() if k != "_id"}})


@router.get("/positions", response_model=dict)
async def list_positions(current_user: dict = Depends(get_current_user)):
    """Get the position list (supports multiple markets)"""
    db = get_mongo_db()
    items = await db["paper_positions"].find({"user_id": current_user["id"]}).to_list(None)
    enriched: List[Dict[str, Any]] = []
    for p in items:
        code = p.get("code")
        name = p.get("name", "")  # Get stock name from database
        market = p.get("market", "CN")
        currency = p.get("currency", "CNY")
        qty = int(p.get("quantity", 0))
        available_qty = p.get("available_qty", qty)
        avg_cost = float(p.get("avg_cost", 0.0))

        last = await _get_last_price(code, market)
        mkt = round((last or 0.0) * qty, 2)
        enriched.append({
            "code": code,
            "name": name,  # Add stock name to response
            "market": market,
            "currency": currency,
            "quantity": qty,
            "available_qty": available_qty,
            "avg_cost": avg_cost,
            "last_price": last,
            "market_value": mkt,
            "unrealized_pnl": None if last is None else round((last - avg_cost) * qty, 2)
        })
    return ok({"items": enriched})


@router.get("/orders", response_model=dict)
async def list_orders(limit: int = Query(50, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    db = get_mongo_db()
    cursor = db["paper_orders"].find({"user_id": current_user["id"]}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(None)
    # remove _id
    cleaned = [{k: v for k, v in it.items() if k != "_id"} for it in items]
    return ok({"items": cleaned})


@router.get("/quote/{code}", response_model=dict)
async def get_quote(
    code: str,
    market: Optional[str] = Query(None, description="market type (CN/ETF/HK/US), If not passed, it will be automatically recognized."),
    current_user: dict = Depends(get_current_user)
):
    """Get stock price information (current price and today s price range)"""
    # 1. Identify market type
    market, normalized_code, is_etf = _resolve_market_and_code(code, market)
    
    # 2. Get current price
    current_price = await _get_last_price(normalized_code, market)
    
    # 3. Get the price range of the day
    price_range = await _get_today_price_range(normalized_code, market)
    
    return ok({
        "code": normalized_code,
        "market": "ETF" if is_etf else market,
        "current_price": current_price,
        "high": price_range.get("high") if price_range else None,
        "low": price_range.get("low") if price_range else None
    })


class InitializeAccountRequest(BaseModel):
    """Initialize account request (set initial amount)"""
    initial_cash: Dict[str, float] = Field(
        default_factory=lambda: {
            "CNY": INITIAL_CASH_BY_MARKET["CNY"],
            "HKD": INITIAL_CASH_BY_MARKET["HKD"],
            "USD": INITIAL_CASH_BY_MARKET["USD"]
        },
        description="Initial capital for each market (CNY/HKD/USD)"
    )


class ResetAccountRequest(BaseModel):
    """Reset account request"""
    initial_cash: Optional[Dict[str, float]] = Field(
        None,
        description="Initial funds after reset (CNY/HKD/USD), if not provided, the default value will be used"
    )


@router.post("/initialize", response_model=dict)
async def initialize_account(
    request: InitializeAccountRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Initialize account (set initial amount)
    
    If the account already exists, the initial amount will be updated (clear positions and orders, reset to the specified amount)
    If the account does not exist, a new account will be created
    """
    db = get_mongo_db()
    user_id = current_user["id"]
    
    # Verification amount
    initial_cash = request.initial_cash
    for currency, amount in initial_cash.items():
        if amount < 0:
            raise HTTPException(status_code=400, detail=f"{currency} The initial amount cannot be negative")
    
    # Check if the account exists
    existing_acc = await db["paper_accounts"].find_one({"user_id": user_id})
    
    if existing_acc:
        # The account already exists, clear positions and orders, and reset to the specified amount
        await db["paper_positions"].delete_many({"user_id": user_id})
        await db["paper_orders"].delete_many({"user_id": user_id})
        await db["paper_trades"].delete_many({"user_id": user_id})
        
        now = datetime.utcnow().isoformat()
        update_data = {
            "cash": initial_cash,
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            "updated_at": now
        }
        await db["paper_accounts"].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        logger.info(f"✅ Account has been initialized: user_id={user_id}, initial_cash={initial_cash}")
    else:
        # Account does not exist, create a new account
        now = datetime.utcnow().isoformat()
        acc = {
            "user_id": user_id,
            "cash": initial_cash,
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            "settings": {
                "auto_currency_conversion": False,
                "default_market": "CN"
            },
            "created_at": now,
            "updated_at": now,
        }
        await db["paper_accounts"].insert_one(acc)
        logger.info(f"✅ Account has been created: user_id={user_id}, initial_cash={initial_cash}")
    
    # Return to updated account
    acc = await _get_or_create_account(user_id)
    return ok({
        "message": "Account has been initialized",
        "cash": acc.get("cash", {}),
        "account": acc
    })


@router.post("/reset", response_model=dict)
async def reset_account(
    confirm: bool = Query(False),
    request: Optional[ResetAccountRequest] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Reset account (supports multiple currencies and custom initial amounts)
    
    If initial_cash is provided, the specified amount is used; otherwise the default amount is used
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Please set confirm=true to confirm reset")
    
    db = get_mongo_db()
    user_id = current_user["id"]
    
    # Determine the initial amount after reset
    if request and request.initial_cash:
        initial_cash = request.initial_cash
        # Verification amount
        for currency, amount in initial_cash.items():
            if amount < 0:
                raise HTTPException(status_code=400, detail=f"{currency} The initial amount cannot be negative")
    else:
        # Use default amount
        initial_cash = INITIAL_CASH_BY_MARKET.copy()
    
    # Clear all data
    await db["paper_accounts"].delete_many({"user_id": user_id})
    await db["paper_positions"].delete_many({"user_id": user_id})
    await db["paper_orders"].delete_many({"user_id": user_id})
    await db["paper_trades"].delete_many({"user_id": user_id})
    
    # Recreate account (with specified initial amount)
    now = datetime.utcnow().isoformat()
    acc = {
        "user_id": user_id,
        "cash": initial_cash,
        "realized_pnl": {
            "CNY": 0.0,
            "HKD": 0.0,
            "USD": 0.0
        },
        "settings": {
            "auto_currency_conversion": False,
            "default_market": "CN"
        },
        "created_at": now,
        "updated_at": now,
    }
    await db["paper_accounts"].insert_one(acc)
    
    logger.info(f"✅ Account has been reset: user_id={user_id}, initial_cash={initial_cash}")
    return ok({"message": "Account has been reset", "cash": acc.get("cash", {})})


# ==================== Market rules configuration API ====================

@router.get("/market-rules")
async def get_market_rules():
    """Get trading rule configurations for all markets"""
    db = get_mongo_db()
    rules = await db["paper_market_rules"].find({}, {"_id": 0}).to_list(None)
    if not rules:
        # If there is no configuration, return to the default value (the scripts directory is deleted in the community version, and if missing, it returns empty and prompts for initialization)
        try:
            from scripts.init_paper_trading_market_rules import MARKET_RULES
            return ok(MARKET_RULES)
        except ImportError:
            return ok([])
    return ok(rules)


class CommissionUpdateRequest(BaseModel):
    rules: List[Dict[str, Any]] = Field(..., description="Commission allocation for each market")


@router.post("/market-rules/commission")
async def update_market_rules_commission(req: CommissionUpdateRequest):
    """Update commission allocation for each market"""
    db = get_mongo_db()
    updated = 0
    for item in req.rules:
        market = item.get("market")
        commission = item.get("commission", {})
        if not market:
            continue
        # Only update the commission part and keep other rules
        result = await db["paper_market_rules"].update_one(
            {"market": market},
            {"$set": {f"rules.commission.{k}": v for k, v in commission.items()}}
        )
        if result.modified_count > 0:
            updated += 1
        elif result.matched_count == 0:
            # Market rules do not exist, create basic records
            logger.warning(f"market {market} Rule does not exist, skip commission configuration update")

    logger.info(f"✅ Update commission configuration: {updated} market")
    return ok({"message": f"updated {updated} Commission allocation for each market", "updated": updated})
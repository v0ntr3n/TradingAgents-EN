"""
Trading time judgment tool module

Provides unified trading time judgment logic to determine whether it is currently within the A-share trading hours.
"""

from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

from app.core.config import settings


def is_trading_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is during A-share trading hours or the post-closing buffer period

    Trading hours:
    - Morning:9:30-11:30
    - Afternoon:13:00-15:00
    - Post-closing buffer period:15:00-15:30 (Make sure to get the closing price)

    Description of the post-closing buffer period:
    - Continue to obtain for 30 minutes after the trading time ends
    - Assuming once every 6 minutes, 5 more synchronization opportunities can be added
    - Greatly reduces the risk of missing the closing price

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it within trading hours?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    
    # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
    morning = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    # Post-closing buffer period (extended by 30 minutes to 15:30) 
    buffer_end = dtime(15, 30)
    
    return (morning <= t <= noon) or (afternoon_start <= t <= buffer_end)


def is_strict_trading_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is within strict A-share trading hours (excluding the buffer period)

    Trading hours:
    - Morning:9:30-11:30
    - Afternoon:13:00-15:00

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Whether it is within strict trading hours
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    
    # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
    morning = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    afternoon_end = dtime(15, 0)
    
    return (morning <= t <= noon) or (afternoon_start <= t <= afternoon_end)


def is_pre_market_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is before the market time (9:00-9:30) 

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it during pre-market time?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    pre_market_start = dtime(9, 0)
    pre_market_end = dtime(9, 30)
    
    return pre_market_start <= t < pre_market_end


def is_after_market_time(now: Optional[datetime] = None) -> bool:
    """
    Determine whether it is after-hours time (15:00-15:30) 

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        bool: Is it after hours?
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # working day Mon-Fri
    if now.weekday() > 4:
        return False
    
    t = now.time()
    after_market_start = dtime(15, 0)
    after_market_end = dtime(15, 30)
    
    return after_market_start <= t <= after_market_end


def get_trading_status(now: Optional[datetime] = None) -> str:
    """
    Get current transaction status

    Args:
        now: Specify the time, defaults to the current time (using the configured time zone)

    Returns:
        str: transaction status
            - "pre_market": Before the market
            - "morning_session": morning trading session
            - "noon_break": Market closed at noon
            - "afternoon_session": Afternoon trading session
            - "after_market": After-hours buffer period
            - "closed": Market closed
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    
    # weekend
    if now.weekday() > 4:
        return "closed"
    
    t = now.time()
    
    # Define time point
    pre_market_start = dtime(9, 0)
    morning_start = dtime(9, 30)
    noon = dtime(11, 30)
    afternoon_start = dtime(13, 0)
    afternoon_end = dtime(15, 0)
    after_market_end = dtime(15, 30)
    
    # Judgment status
    if pre_market_start <= t < morning_start:
        return "pre_market"
    elif morning_start <= t <= noon:
        return "morning_session"
    elif noon < t < afternoon_start:
        return "noon_break"
    elif afternoon_start <= t <= afternoon_end:
        return "afternoon_session"
    elif afternoon_end < t <= after_market_end:
        return "after_market"
    else:
        return "closed"


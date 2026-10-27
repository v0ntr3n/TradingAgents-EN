"""
Data flow general tool functions

Migrated from tradingagents/dataflows/utils.py
"""
import os
import json
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Annotated

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    """
    Save DataFrame to CSV file
    
    Args:
        data: to be saved DataFrame
        tag: Tags (for logs)
        save_path: Save path, if None then do not save
    """
    if save_path:
        data.to_csv(save_path)
        logger.info(f"{tag} saved to {save_path}")


def get_current_date():
    """
    Get the current date (YYYY-MM-DD format)
    
    Returns:
        str: current date string
    """
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator):
    """
    Class decorator: Apply the specified decorator to all methods of the class
    
    Args:
        decorator: The decorator function to apply
        
    Returns:
        function: class decorator function
        
    Example:
        >>> @decorate_all_methods(my_decorator)
        >>> class MyClass:
        >>>     def method1(self):
        >>>         pass
    """
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date_input):
    """
    Get the next business day (skipping weekends)

    Args:
        date_input: Date object or date string (YYYY-MM-DD)

    Returns:
        datetime: Date object for next working day

    Example:
        >>> get_next_weekday("2025-10-04")  # Saturday
        datetime(2025, 10, 6)  # Return to Monday
    """
    if not isinstance(date_input, datetime):
        date_input = datetime.strptime(date_input, "%Y-%m-%d")

    if date_input.weekday() >= 5:  # Saturday(5)or sunday(6)
        days_to_add = 7 - date_input.weekday()
        next_weekday = date_input + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date_input


def clean_date_string(date_str: str) -> str:
    """
    Clean the date string and keep only the date part (remove the time part)

    Args:
        date_str: Date string, which may contain a time part, such as "2026-01-14 00:00:00"

    Returns:
        str: A string containing only the date part, such as "2026-01-14"
    """
    if not date_str:
        return date_str
    # Handle date strings that may contain time
    return date_str.split()[0] if ' ' in date_str else date_str


def get_trading_date_range(target_date=None, lookback_days=10):
    """
    Get the date range used to query transaction data

    Strategy: Obtain the data of the last N days to ensure that the data of the last trading day can be obtained
    This automatically handles weekends, holidays and data delays

    Args:
        target_date: Target date (datetime object or string YYYY-MM-DD), defaults to today
        lookback_days: The number of days to search forward, the default is 10 days (weekends can be covered+Short vacation)

    Returns:
        tuple: (start_date, end_date) Two strings, format YYYY-MM-DD

    Example:
        >>> get_trading_date_range("2025-10-13", 10)
        ("2025-10-03", "2025-10-13")

        >>> get_trading_date_range("2025-10-12", 10)  # Sunday
        ("2025-10-02", "2025-10-12")
    """
    from datetime import datetime, timedelta

    # Handle input date
    if target_date is None:
        target_date = datetime.now()
    elif isinstance(target_date, str):
        # Clean date string, remove possible time part
        target_date_clean = clean_date_string(target_date)
        target_date = datetime.strptime(target_date_clean, "%Y-%m-%d")

    # If it's a future date, use today
    today = datetime.now()
    if target_date.date() > today.date():
        target_date = today

    # Calculate start date (forward N days)
    start_date = target_date - timedelta(days=lookback_days)

    # Return date range
    return start_date.strftime("%Y-%m-%d"), target_date.strftime("%Y-%m-%d")


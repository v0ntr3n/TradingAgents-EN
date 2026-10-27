#!/usr/bin/env python3
"""
Tool call log decorator
Add unified logging for all tool calls
"""

import time
import functools
from typing import Any, Dict, Optional, Callable
from datetime import datetime
from zoneinfo import ZoneInfo
from tradingagents.config.runtime_settings import get_timezone_name


from tradingagents.utils.logging_init import get_logger

# Import log module
from tradingagents.utils.logging_manager import get_logger, get_logger_manager
logger = get_logger('agents')

# Tool call logger
tool_logger = get_logger("tools")


def log_tool_call(tool_name: Optional[str] = None, log_args: bool = True, log_result: bool = False):
    """
    Tool call log decorator

    Args:
        tool_name: Tool name, if not provided function name is used
        log_args: Whether to record parameters
        log_result: Whether to record the returned results (note: may contain a large amount of data)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Determine tool name
            name = tool_name or getattr(func, '__name__', 'unknown_tool')

            # Recording start time
            start_time = time.time()

            # Prepare parameter information
            args_info = {}
            if log_args:
                # Record location parameters
                if args:
                    args_info['args'] = [str(arg)[:100] + '...' if len(str(arg)) > 100 else str(arg) for arg in args]

                # Logging keyword arguments
                if kwargs:
                    args_info['kwargs'] = {
                        k: str(v)[:100] + '...' if len(str(v)) > 100 else str(v)
                        for k, v in kwargs.items()
                    }

            # Logging tool call starts
            tool_logger.info(
                f"🔧 [Tool call] {name} - start",
                extra={
                    'tool_name': name,
                    'event_type': 'tool_call_start',
                    'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat(),
                    'args_info': args_info if log_args else None
                }
            )

            try:
                # Execute tool function
                result = func(*args, **kwargs)

                # Calculate execution time
                duration = time.time() - start_time

                # Prepare results information
                result_info = None
                if log_result and result is not None:
                    result_str = str(result)
                    result_info = result_str[:200] + '...' if len(result_str) > 200 else result_str

                # Recording tool call successful
                tool_logger.info(
                    f"✅ [Tool call] {name} - Complete (Time consuming: {duration:.2f}s)",
                    extra={
                        'tool_name': name,
                        'event_type': 'tool_call_success',
                        'duration': duration,
                        'result_info': result_info if log_result else None,
                        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                    }
                )

                return result

            except Exception as e:
                # Calculate execution time
                duration = time.time() - start_time

                # Recording tool call failed
                tool_logger.error(
                    f"❌ [Tool call] {name} - failed (Time consuming: {duration:.2f}s): {str(e)}",
                    extra={
                        'tool_name': name,
                        'event_type': 'tool_call_error',
                        'duration': duration,
                        'error': str(e),
                        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                    },
                    exc_info=True
                )

                # rethrow exception
                raise

        return wrapper
    return decorator


def log_data_source_call(source_name: str):
    """
    Data source calls dedicated log decorator

    Args:
        source_name: Data source name (such as: tushare, akshare, yfinance, etc.)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Extract the stock symbol (usually the first parameter)
            symbol = args[0] if args else kwargs.get('symbol', kwargs.get('ticker', 'unknown'))

            # Record data source call starts
            tool_logger.info(
                f"📊 [data source] {source_name} - get {symbol} data",
                extra={
                    'data_source': source_name,
                    'symbol': symbol,
                    'event_type': 'data_source_call',
                    'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                }
            )

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Check if the result is successful
                success = result and "❌" not in str(result) and "Error" not in str(result)

                if success:
                    tool_logger.info(
                        f"✅ [data source] {source_name} - {symbol} Data acquisition successful (Time consuming: {duration:.2f}s)",
                        extra={
                            'data_source': source_name,
                            'symbol': symbol,
                            'event_type': 'data_source_success',
                            'duration': duration,
                            'data_size': len(str(result)) if result else 0,
                            'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                        }
                    )
                else:
                    tool_logger.warning(
                        f"⚠️ [data source] {source_name} - {symbol} Data acquisition failed (Time consuming: {duration:.2f}s)",
                        extra={
                            'data_source': source_name,
                            'symbol': symbol,
                            'event_type': 'data_source_failure',
                            'duration': duration,
                            'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                        }
                    )

                return result

            except Exception as e:
                duration = time.time() - start_time

                tool_logger.error(
                    f"❌ [data source] {source_name} - {symbol} Data acquisition exception (Time consuming: {duration:.2f}s): {str(e)}",
                    extra={
                        'data_source': source_name,
                        'symbol': symbol,
                        'event_type': 'data_source_error',
                        'duration': duration,
                        'error': str(e),
                        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                    },
                    exc_info=True
                )

                raise

        return wrapper
    return decorator


def log_llm_call(provider: str, model: str):
    """
    LLM Call the dedicated log decorator

    Args:
        provider: LLM Provider (such as: openai, deepseek, tongyi, etc.)
        model: Model name
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Logging LLM call starts
            tool_logger.info(
                f"🤖 [LLM call] {provider}/{model} - start",
                extra={
                    'llm_provider': provider,
                    'llm_model': model,
                    'event_type': 'llm_call_start',
                    'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                }
            )

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                tool_logger.info(
                    f"✅ [LLM call] {provider}/{model} - Complete (Time consuming: {duration:.2f}s)",
                    extra={
                        'llm_provider': provider,
                        'llm_model': model,
                        'event_type': 'llm_call_success',
                        'duration': duration,
                        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                    }
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                tool_logger.error(
                    f"❌ [LLM call] {provider}/{model} - failed (Time consuming: {duration:.2f}s): {str(e)}",
                    extra={
                        'llm_provider': provider,
                        'llm_model': model,
                        'event_type': 'llm_call_error',
                        'duration': duration,
                        'error': str(e),
                        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat()
                    },
                    exc_info=True
                )

                raise

        return wrapper
    return decorator


# Convenience function
def log_tool_usage(tool_name: str, symbol: str = None, **extra_data):
    """
    Convenience functions for recording tool usage

    Args:
        tool_name: Tool name
        symbol: Stock code (optional)
        **extra_data: additional data
    """
    extra = {
        'tool_name': tool_name,
        'event_type': 'tool_usage',
        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat(),
        **extra_data
    }

    if symbol:
        extra['symbol'] = symbol

    tool_logger.info(f"📋 [Tool usage] {tool_name}", extra=extra)


def log_analysis_step(step_name: str, symbol: str, **extra_data):
    """
    Convenience function for recording analysis steps

    Args:
        step_name: step name
        symbol: Stock code
        **extra_data: additional data
    """
    extra = {
        'step_name': step_name,
        'symbol': symbol,
        'event_type': 'analysis_step',
        'timestamp': datetime.now(ZoneInfo(get_timezone_name())).isoformat(),
        **extra_data
    }

    tool_logger.info(f"📈 [Analysis steps] {step_name} - {symbol}", extra=extra)


def log_analysis_module(module_name: str, session_id: str = None):
    """
    Analysis module log decorator
    Automatically record the start and end of a module

    Args:
        module_name: Module name (such as: market_analyst, fundamentals_analyst, etc.)
        session_id: Session ID (optional)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract ticker from parameter
            symbol = None

            # Special processing: parameter structure of signal processing module
            if module_name == "graph_signal_processing":
                # Signal processing module:process_signal(self, full_signal, stock_symbol=None)
                if len(args) >= 3:  # self, full_signal, stock_symbol
                    symbol = str(args[2]) if args[2] else None
                elif 'stock_symbol' in kwargs:
                    symbol = str(kwargs['stock_symbol']) if kwargs['stock_symbol'] else None
            else:
                if args:
                    # Check if the first parameter is a state dictionary (case of analyst node)
                    first_arg = args[0]
                    if isinstance(first_arg, dict) and 'company_of_interest' in first_arg:
                        symbol = str(first_arg['company_of_interest'])
                    # Check if the first parameter is a stock symbol
                    elif isinstance(first_arg, str) and len(first_arg) <= 10:
                        symbol = first_arg

            # Find stock ticker from kwargs
            if not symbol:
                for key in ['symbol', 'ticker', 'stock_code', 'stock_symbol', 'company_of_interest']:
                    if key in kwargs:
                        symbol = str(kwargs[key])
                        break

            # If still not found, use default value
            if not symbol:
                symbol = 'unknown'

            # Generate session ID
            actual_session_id = session_id or f"session_{int(time.time())}"

            # Recording module starts
            logger_manager = get_logger_manager()

            start_time = time.time()

            logger_manager.log_module_start(
                tool_logger, module_name, symbol, actual_session_id,
                function_name=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )

            try:
                # Execute analysis function
                result = func(*args, **kwargs)

                # Calculate execution time
                duration = time.time() - start_time

                # Recording module completed
                result_length = len(str(result)) if result else 0
                logger_manager.log_module_complete(
                    tool_logger, module_name, symbol, actual_session_id,
                    duration, success=True, result_length=result_length,
                    function_name=func.__name__
                )

                return result

            except Exception as e:
                # Calculate execution time
                duration = time.time() - start_time

                # Logging module errors
                logger_manager.log_module_error(
                    tool_logger, module_name, symbol, actual_session_id,
                    duration, str(e),
                    function_name=func.__name__
                )

                # rethrow exception
                raise

        return wrapper
    return decorator


def log_analyst_module(analyst_type: str):
    """
    Analyst module dedicated decorator

    Args:
        analyst_type: Analyst type (such as: market, fundamentals, technical, sentiment, etc.)
    """
    return log_analysis_module(f"{analyst_type}_analyst")


def log_graph_module(graph_type: str):
    """
    Special decorator for graph processing module

    Args:
        graph_type: Graph processing type (such as: signal_processing, workflow, etc.)
    """
    return log_analysis_module(f"graph_{graph_type}")


def log_dataflow_module(dataflow_type: str):
    """
    Data flow module dedicated decorator

    Args:
        dataflow_type: Data flow type (such as cache, interface, provider, etc.)
    """
    return log_analysis_module(f"dataflow_{dataflow_type}")

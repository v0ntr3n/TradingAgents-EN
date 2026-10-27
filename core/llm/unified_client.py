"""
Unified LLM client

Provide a unified interface to call various LLM providers
"""

import asyncio
import inspect
import json
import logging
import re
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from core.utils.retry import is_retryable as _is_retryable, retry_sync, retry_async

from .models import LLMConfig, LLMProvider, LLMResponse, Message, ToolCall, ToolResult
from .providers.base import BaseAdapter
from .providers.openai_compat import OpenAICompatAdapter

# Optional adapter
try:
    from .providers.google import GoogleAdapter
    GOOGLE_AVAILABLE = True
except ImportError:
    GoogleAdapter = None
    GOOGLE_AVAILABLE = False

try:
    from .providers.anthropic import AnthropicAdapter
    ANTHROPIC_AVAILABLE = True
except ImportError:
    AnthropicAdapter = None
    ANTHROPIC_AVAILABLE = False

from .tool_normalizer import ToolCallNormalizer


class UnifiedLLMClient:
    """
    Unified LLM client
    
    Automatically select the appropriate adapter and provide a unified calling interface
    
    Usage:
        client = UnifiedLLMClient.from_config(config)
        response = client.chat(messages)
        
        # Or use the convenience method
        client = UnifiedLLMClient.from_provider("deepseek")
    """
    
    def __init__(self, adapter: BaseAdapter):
        self._adapter = adapter
        self._tools: Dict[str, Callable] = {}

    @classmethod
    def _get_adapter_map(cls) -> Dict[LLMProvider, type]:
        """Dynamically build adapter mappings (based on availability)"""
        adapter_map = {
            LLMProvider.OPENAI: OpenAICompatAdapter,
            LLMProvider.DEEPSEEK: OpenAICompatAdapter,
            LLMProvider.DASHSCOPE: OpenAICompatAdapter,
            LLMProvider.ZHIPU: OpenAICompatAdapter,
            LLMProvider.SILICONFLOW: OpenAICompatAdapter,
            LLMProvider.OLLAMA: OpenAICompatAdapter,
            LLMProvider.OPENROUTER: OpenAICompatAdapter,
        }

        if GOOGLE_AVAILABLE:
            adapter_map[LLMProvider.GOOGLE] = GoogleAdapter

        if ANTHROPIC_AVAILABLE:
            adapter_map[LLMProvider.ANTHROPIC] = AnthropicAdapter

        return adapter_map

    @classmethod
    def from_config(cls, config: LLMConfig) -> "UnifiedLLMClient":
        """Create client from configuration"""
        adapter_map = cls._get_adapter_map()
        adapter_class = adapter_map.get(config.provider)

        if not adapter_class:
            available_providers = list(adapter_map.keys())
            raise ValueError(
                f"Unsupported provider: {config.provider}. "
                f"Available providers: {available_providers}"
            )
        
        adapter = adapter_class(config)
        adapter.initialize()
        return cls(adapter)
    
    @classmethod
    def from_provider(
        cls,
        provider: str,
        model: Optional[str] = None,
        **kwargs
    ) -> "UnifiedLLMClient":
        """
        Create client from provider name (Automatically read configuration from environment variables)
        
        Args:
            provider: Provider name (deepseek, dashscope, google, etc.)
            model: Model name (Optional, use default value)
            **kwargs: Other configuration parameters
        """
        provider_enum = LLMProvider(provider.lower())
        config = LLMConfig.from_env(provider_enum)
        
        if model:
            config.model = model
        
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return cls.from_config(config)
    
    def register_tool(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register tool function
        
        Args:
            func: Utility function
            name: Tool name
            description: Tool description
            
        Returns:
            Tool definition (Can be used for chat calls)
        """
        tool_def = ToolCallNormalizer.normalize_tool_definition(func, name, description)
        tool_name = tool_def["function"]["name"]
        self._tools[tool_name] = func
        return tool_def

    def inject_tools(self, tools: Dict[str, Callable]) -> None:
        """
        Batch injection of tool functions (used in scenarios such as smart assistants)
        tools: {tool_name: callable} mapping
        """
        self._tools.update(tools)

    @staticmethod
    def _estimate_message_chars(messages: List[Message]) -> int:
        total = 0
        for message in messages:
            total += len(message.role or "")
            total += len(message.name or "")
            total += len(message.tool_call_id or "")
            total += len(message.content or "")
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    total += len(tool_call.id or "")
                    total += len(tool_call.name or "")
                    try:
                        total += len(json.dumps(tool_call.arguments or {}, ensure_ascii=False, default=str))
                    except Exception:
                        total += len(str(tool_call.arguments or {}))
        return total

    @staticmethod
    def _build_message_size_summary(messages: List[Message]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        for index, message in enumerate(messages):
            tool_call_count = len(message.tool_calls or [])
            content_len = len(message.content or "")
            tool_args_len = 0
            for tool_call in message.tool_calls or []:
                try:
                    tool_args_len += len(json.dumps(tool_call.arguments or {}, ensure_ascii=False, default=str))
                except Exception:
                    tool_args_len += len(str(tool_call.arguments or {}))
            summary.append(
                {
                    "index": index,
                    "role": message.role,
                    "name": message.name,
                    "content_len": content_len,
                    "tool_call_count": tool_call_count,
                    "tool_args_len": tool_args_len,
                }
            )
        return summary

    def _log_tool_round_state(
        self,
        *,
        loop_name: str,
        round_number: int,
        stage: str,
        messages: List[Message],
    ) -> None:
        total_chars = self._estimate_message_chars(messages)
        top_messages = sorted(
            self._build_message_size_summary(messages),
            key=lambda item: item["content_len"] + item["tool_args_len"],
            reverse=True,
        )[:5]
        logger.info(
            "[%s] %s | round=%s | message_count=%s | approx_chars=%s | largest=%s",
            loop_name,
            stage,
            round_number,
            len(messages),
            total_chars,
            json.dumps(top_messages, ensure_ascii=False, default=str),
        )

    def _log_llm_call_timing(
        self,
        *,
        loop_name: str,
        stage: str,
        elapsed_seconds: float,
        messages: List[Message],
        response: Optional[LLMResponse],
        round_number: Optional[int] = None,
    ) -> None:
        logger.info(
            "[%s] %s | round=%s | elapsed=%.2fs | message_count=%s | approx_chars=%s | has_tool_calls=%s | tool_call_count=%s | content_chars=%s | finish_reason=%s",
            loop_name,
            stage,
            round_number if round_number is not None else "-",
            elapsed_seconds,
            len(messages),
            self._estimate_message_chars(messages),
            response.has_tool_calls if response else False,
            len(response.tool_calls) if response and response.tool_calls else 0,
            len(response.content or "") if response else 0,
            response.finish_reason if response else None,
        )

    @staticmethod
    def _serialize_message_for_log(message: Message) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "role": message.role,
            "name": message.name,
            "tool_call_id": message.tool_call_id,
            "content": message.content,
            "reasoning_content": message.reasoning_content,
        }
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
                for tool_call in message.tool_calls
            ]
        return payload

    @staticmethod
    def _serialize_response_for_log(response: Optional[LLMResponse]) -> Dict[str, Any]:
        if response is None:
            return {}

        return {
            "content": response.content,
            "reasoning_content": response.reasoning_content,
            "finish_reason": response.finish_reason,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
                for tool_call in response.tool_calls
            ],
        }

    def _log_llm_payload(
        self,
        *,
        loop_name: str,
        stage: str,
        payload_label: Optional[str],
        round_number: Optional[int] = None,
        messages: Optional[List[Message]] = None,
        response: Optional[LLMResponse] = None,
    ) -> None:
        if messages is not None:
            logger.info(
                "[%s] %s | label=%s | round=%s | payload=%s",
                loop_name,
                stage,
                payload_label or "-",
                round_number if round_number is not None else "-",
                json.dumps(
                    [self._serialize_message_for_log(message) for message in messages],
                    ensure_ascii=False,
                    default=str,
                ),
            )
            return

        logger.info(
            "[%s] %s | label=%s | round=%s | payload=%s",
            loop_name,
            stage,
            payload_label or "-",
            round_number if round_number is not None else "-",
            json.dumps(
                self._serialize_response_for_log(response),
                ensure_ascii=False,
                default=str,
            ),
        )

    @staticmethod
    def _log_tool_call_timing(
        *,
        loop_name: str,
        round_number: int,
        tool_name: str,
        elapsed_seconds: float,
        result: ToolResult,
    ) -> None:
        logger.info(
            "[%s] tool_exec_completed | round=%s | tool=%s | elapsed=%.2fs | chars=%s | is_error=%s",
            loop_name,
            round_number,
            tool_name,
            elapsed_seconds,
            len(result.content or ""),
            result.is_error,
        )

    async def _emit_progress(self, progress_callback: Optional[Callable], payload: Dict[str, Any]) -> None:
        """Unified processing of optional progress callbacks, compatible with synchronous/asynchronous functions."""
        if not progress_callback:
            return

        try:
            result = progress_callback(payload)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.debug("[UnifiedLLM] Progress callback failed(ignore): %s", e)

    def _summarize_tool_result(self, tool_name: str, content: str) -> Dict[str, Any]:
        """Extract batch tool result summaries to facilitate front-end display of execution output."""
        if not content:
            return {}

        if tool_name == "screen_stocks_by_criteria":
            match = re.search(r"Found in total\s*(\d+)\s*Only stocks that meet the criteria, before display below\s*(\d+)\s*only", content)
            if match:
                return {
                    "total_candidates": int(match.group(1)),
                    "displayed_candidates": int(match.group(2)),
                }
            if "No matching stocks found" in content:
                return {"total_candidates": 0, "displayed_candidates": 0}

        if tool_name == "batch_check_profit_consistency":
            match = re.search(r"stable\s*(\d+)\s*only\s*\|\s*unstable\s*(\d+)\s*only\s*\|\s*No data\s*(\d+)\s*only", content)
            if match:
                return {
                    "stable_count": int(match.group(1)),
                    "volatile_count": int(match.group(2)),
                    "no_data_count": int(match.group(3)),
                }

        if tool_name == "add_stocks_to_favorites":
            summary: Dict[str, Any] = {}
            added_match = re.search(r"Added\s*(\d+)\s*Only stocks to stock watchlist", content)
            existed_match = re.search(r"Already exists\s*(\d+)\s*only", content)
            failed_match = re.search(r"failed\s*(\d+)\s*only", content)
            if added_match:
                summary["added_count"] = int(added_match.group(1))
            if existed_match:
                summary["existing_count"] = int(existed_match.group(1))
            if failed_match:
                summary["failed_count"] = int(failed_match.group(1))
            return summary

        if tool_name == "add_stock_to_watchlist":
            summary: Dict[str, Any] = {}
            added_match = re.search(r"Added\s*(\d+)\s*Only stocks arrive[ [\"]?([^] \"\n]+)[] \"]?", content)
            created_match = re.search(r"Groups automatically created[ [\"]?([^] \"\n]+)[] \"]?and add\s*(\d+)\s*only stocks", content)
            existing_match = re.search(r"Already in group[ [\"]?([^] \"\n]+)[] \"]?in", content)
            if added_match:
                summary["added_count"] = int(added_match.group(1))
            if created_match:
                summary["group_created"] = 1
                summary["added_count"] = int(created_match.group(2))
            if existing_match and "added_count" not in summary:
                summary["existing_count"] = 1
            return summary

        return {}

    @property
    def _max_retries(self) -> int:
        return getattr(self._adapter.config, "retry_times", 3)

    def _retry_chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Call the adapter synchronously and retry with exponential backoff."""
        return retry_sync(
            self._adapter.chat,
            messages, tools,
            max_retries=self._max_retries,
            label="UnifiedLLM",
            **kwargs,
        )

    async def _aretry_chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Call the adapter asynchronously and retry with exponential backoff."""
        return await retry_async(
            self._adapter.achat,
            messages, tools,
            max_retries=self._max_retries,
            label="UnifiedLLM",
            **kwargs,
        )

    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        auto_execute_tools: bool = False,
        max_tool_rounds: int = 5,
        **kwargs
    ) -> LLMResponse:
        """
        synchronous chat
        
        Args:
            messages: Message list
            tools: tool definition list
            auto_execute_tools: Whether to automatically execute tool calls
            max_tool_rounds: Maximum tool call rounds
            **kwargs: Other parameters
        """
        response = self._retry_chat(messages, tools, **kwargs)
        
        if auto_execute_tools and response.has_tool_calls:
            return self._execute_tool_loop(
                messages, tools, response, max_tool_rounds, **kwargs
            )
        
        return response

    def chat_stream(
        self,
        messages: List[Message],
        on_delta: Optional[Callable[[str, str], None]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Synchronous streaming chat: callback thoughts/text increments piece by piece, eventually returning the full LLMResponse.

        Args:
            messages: Message list (only supports single-round scenarios without tool invocation)
            on_delta: callback on_delta(kind, text), kind ∈ {"reset", "reasoning", "content"}; 
                      It will be sent once before retrying. ("reset", "") Let the caller clear the received content
            **kwargs: Other parameters (max_tokens, temperature, etc.)

        When the adapter does not support streaming, it automatically falls back to normal chat and uses the complete reply as a content incremental callback.
        """
        stream_adapter = getattr(self._adapter, "chat_stream_deltas", None)

        if stream_adapter is None:
            response = self.chat(messages, **kwargs)
            if on_delta and response.content:
                on_delta("content", response.content)
            return response

        def _consume(**call_kwargs: Any) -> str:
            if on_delta:
                on_delta("reset", "")
            parts: List[str] = []
            for delta in stream_adapter(messages, **call_kwargs):
                if delta.get("type") == "content":
                    parts.append(delta.get("text") or "")
                if on_delta:
                    on_delta(delta.get("type", ""), delta.get("text") or "")
            return "".join(parts)

        content = retry_sync(
            _consume,
            max_retries=self._max_retries,
            label="UnifiedLLMStream",
            **kwargs,
        )
        return LLMResponse(
            content=content,
            model=getattr(self._adapter.config, "model", None),
            provider=getattr(self._adapter.config, "provider", None),
            finish_reason="stop",
        )
    
    async def achat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        auto_execute_tools: bool = False,
        max_tool_rounds: int = 5,
        tools_used: Optional[List[str]] = None,
        tool_results_collector: Optional[List[Dict[str, Any]]] = None,
        dry_run: bool = False,
        progress_callback: Optional[Callable] = None,
        log_payloads: bool = False,
        payload_log_label: Optional[str] = None,
        tool_interceptor: Optional[Callable[[ToolCall], Awaitable[Optional[ToolResult]]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Asynchronous chat

        Args:
            tools_used: Optional, used to collect each round of tool call names (used by the intelligent assistant to display execution steps)
            tool_results_collector: Optional, used to collect each round of tools and return the original text (for digital traceability verification),
                Each item is {"tool": Tool name, "content": return text, "is_error": Is there an error?}
            dry_run: If True, the tool call only records logs and returns simulation results, without actually executing the function (used for intent routing testing)
            tool_interceptor: Optional, called before actually executing the tool; return ToolResult to skip the default execution
        """
        if log_payloads:
            self._log_llm_payload(
                loop_name="UnifiedLLM·asynchronous",
                stage="initial_llm_prompt",
                payload_label=payload_log_label,
                messages=messages,
            )
        initial_started_at = time.perf_counter()
        response = await self._aretry_chat(messages, tools, **kwargs)
        if log_payloads:
            self._log_llm_payload(
                loop_name="UnifiedLLM·asynchronous",
                stage="initial_llm_response",
                payload_label=payload_log_label,
                response=response,
            )
        self._log_llm_call_timing(
            loop_name="UnifiedLLM·asynchronous",
            stage="initial_llm_completed",
            elapsed_seconds=time.perf_counter() - initial_started_at,
            messages=messages,
            response=response,
        )

        if auto_execute_tools and response.has_tool_calls:
            return await self._aexecute_tool_loop(
                messages, tools, response, max_tool_rounds,
                tools_used=tools_used,
                tool_results_collector=tool_results_collector,
                dry_run=dry_run,
                progress_callback=progress_callback,
                log_payloads=log_payloads,
                payload_log_label=payload_log_label,
                tool_interceptor=tool_interceptor,
                **kwargs
            )

        return response
    
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Asynchronous streaming output"""
        async for chunk in self._adapter.astream(messages, tools, **kwargs):
            yield chunk
    
    def _execute_tool_loop(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        response: LLMResponse,
        max_rounds: int,
        **kwargs
    ) -> LLMResponse:
        """Execute tool call loop"""
        current_messages = messages.copy()
        current_response = response
        rounds = 0
        
        while current_response.has_tool_calls and rounds < max_rounds:
            self._log_tool_round_state(
                loop_name="UnifiedLLM·sync",
                round_number=rounds + 1,
                stage="tool_round_started",
                messages=current_messages,
            )
            # Add assistant message
            current_messages.append(current_response.to_message())
            
            # Execute all tool calls
            for tool_call in current_response.tool_calls:
                result = ToolCallNormalizer.execute_tool_call(
                    tool_call, self._tools
                )
                # Add tool result message
                current_messages.append(Message(
                    role="tool",
                    content=result.content,
                    tool_call_id=result.tool_call_id,
                    name=result.name
                ))
                logger.info(
                    "[UnifiedLLM·sync] tool_result_appended | round=%s | tool=%s | chars=%s | is_error=%s",
                    rounds + 1,
                    result.name,
                    len(result.content or ""),
                    result.is_error,
                )

            self._log_tool_round_state(
                loop_name="UnifiedLLM·sync",
                round_number=rounds + 1,
                stage="before_retry_chat",
                messages=current_messages,
            )
            
            current_response = self._retry_chat(current_messages, tools, **kwargs)
            rounds += 1

        # ── Final Synthesis: Force text reply generation when tool rounds are exhausted but LLM still wants to call the tool ──
        if current_response.has_tool_calls:
            logger.warning(
                f"[UnifiedLLM·sync] The number of tool calling rounds has reached the upper limit ({max_rounds}), "
                f"LLM Still requesting tool calls to start final synthesis..."
            )
            # Assistant messages with tool_calls cannot be directly added to the history.
            # Otherwise the API will require the corresponding tool response message (400 error) to be followed immediately.
            if current_response.content:
                current_messages.append(Message(
                    role="assistant",
                    content=current_response.content,
                ))
            current_messages.append(Message(
                role="user",
                content=(
                    "The number of tool calls has reached the upper limit, please do not call any more tools."
                    "Please directly generate a complete analysis response based on all the data you have obtained above."
                ),
            ))
            current_response = self._retry_chat(
                current_messages, tools=None, **kwargs
            )

        return current_response

    async def _aexecute_tool_loop(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        response: LLMResponse,
        max_rounds: int,
        tools_used: Optional[List[str]] = None,
        tool_results_collector: Optional[List[Dict[str, Any]]] = None,
        dry_run: bool = False,
        progress_callback: Optional[Callable] = None,
        log_payloads: bool = False,
        payload_log_label: Optional[str] = None,
        tool_interceptor: Optional[Callable[[ToolCall], Awaitable[Optional[ToolResult]]]] = None,
        **kwargs
    ) -> LLMResponse:
        """Asynchronously execute the tool call loop, optionally collecting the tool name called in each round"""
        from .models import LLMResponse  # 🔥 Unified import at the beginning of the function: avoid local import in dry_run branch causing intercepted branch UnboundLocalError
        current_messages = messages.copy()
        current_response = response
        rounds = 0

        while current_response.has_tool_calls and rounds < max_rounds:
            self._log_tool_round_state(
                loop_name="UnifiedLLM·asynchronous",
                round_number=rounds + 1,
                stage="tool_round_started",
                messages=current_messages,
            )
            current_messages.append(current_response.to_message())
            await self._emit_progress(progress_callback, {
                "event": "tool_round_started",
                "round": rounds + 1,
                "tool_count": len(current_response.tool_calls),
            })

            intercepted_any = False
            for tool_call in current_response.tool_calls:
                if tools_used is not None:
                    tools_used.append(tool_call.name)

                await self._emit_progress(progress_callback, {
                    "event": "tool_started",
                    "round": rounds + 1,
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                })

                # ── v3.5.0 Item 4: Tool execution interceptor (such as smart assistant HITL)──
                intercepted_result: Optional[ToolResult] = None
                if tool_interceptor is not None and not dry_run:
                    try:
                        intercepted_result = await tool_interceptor(tool_call)
                        if intercepted_result is not None:
                            intercepted_any = True
                    except Exception as exc:
                        logger.warning(
                            "[UnifiedLLM·asynchronous] tool_interceptor Exception, continue execution by default: %s",
                            exc,
                        )

                if intercepted_result is not None:
                    result = intercepted_result
                elif dry_run:
                    # ── Test mode: only log and return simulation results ──
                    logger.info(
                        "[DRY_RUN] 🏷️ LLM Select tool: %s | parameters: %s",
                        tool_call.name,
                        json.dumps(tool_call.arguments, ensure_ascii=False),
                    )
                    result = ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=f"[dry_run] Tools {tool_call.name} has been called with parameters: {json.dumps(tool_call.arguments, ensure_ascii=False)}",
                        is_error=False,
                    )
                else:
                    # ── Normal mode: Really execute the tool ──
                    tool_started_at = time.perf_counter()
                    result = await ToolCallNormalizer.aexecute_tool_call(
                        tool_call,
                        self._tools
                    )
                    self._log_tool_call_timing(
                        loop_name="UnifiedLLM·asynchronous",
                        round_number=rounds + 1,
                        tool_name=tool_call.name,
                        elapsed_seconds=time.perf_counter() - tool_started_at,
                        result=result,
                    )
                    if log_payloads:
                        logger.info(
                            "[%s] tool_exec_payload | label=%s | round=%s | tool=%s | payload=%s",
                            "UnifiedLLM·asynchronous",
                            payload_log_label or "-",
                            rounds + 1,
                            tool_call.name,
                            json.dumps(
                                {
                                    "arguments": tool_call.arguments,
                                    "result": result.content,
                                    "is_error": result.is_error,
                                },
                                ensure_ascii=False,
                                default=str,
                            ),
                        )
                await self._emit_progress(progress_callback, {
                    "event": "tool_completed",
                    "round": rounds + 1,
                    "tool": tool_call.name,
                    "is_error": result.is_error,
                    "preview": (result.content or "")[:400],
                    "summary": self._summarize_tool_result(tool_call.name, result.content or ""),
                })
                current_messages.append(Message(
                    role="tool",
                    content=result.content,
                    tool_call_id=result.tool_call_id,
                    name=result.name
                ))
                if tool_results_collector is not None:
                    tool_results_collector.append({
                        "tool": result.name or tool_call.name,
                        "content": result.content or "",
                        "is_error": bool(result.is_error),
                        # Tool calling parameters (the fact memory layer uses query/url as the subject key)
                        "args": dict(tool_call.arguments) if tool_call.arguments else {},
                    })
                logger.info(
                    "[UnifiedLLM·asynchronous] tool_result_appended | round=%s | tool=%s | chars=%s | is_error=%s",
                    rounds + 1,
                    result.name,
                    len(result.content or ""),
                    result.is_error,
                )

            # dry_run Mode: Only look at what tools were selected in the first round of LLM, and do not continue with subsequent rounds.
            if dry_run:
                logger.info("[DRY_RUN] ✅ Round 1 tool selection recorded, subsequent rounds skipped")
                # No longer calling LLM, directly construct a plain text reply and return it
                return LLMResponse(
                    content=f"[dry_run test mode] LLM Tools of choice: {', '.join(tools_used or [])}",
                    model=current_response.model,
                )

            # If a tool is intercepted (such as HITL pause), a confirmation message will be returned directly and subsequent rounds will not continue.
            if intercepted_any:
                confirmation_contents = [
                    msg.content for msg in current_messages
                    if msg.role == "tool" and msg.content and "A critical operation is about to be performed" in msg.content
                ]
                return LLMResponse(
                    content="\n\n".join(confirmation_contents) or "The operation needs to be confirmed, please confirm before continuing.",
                    model=current_response.model,
                )

            self._log_tool_round_state(
                loop_name="UnifiedLLM·asynchronous",
                round_number=rounds + 1,
                stage="before_retry_chat",
                messages=current_messages,
            )
            if log_payloads:
                self._log_llm_payload(
                    loop_name="UnifiedLLM·asynchronous",
                    stage="post_tool_llm_prompt",
                    payload_label=payload_log_label,
                    round_number=rounds + 1,
                    messages=current_messages,
                )
            retry_started_at = time.perf_counter()
            # The next round of LLM thinking after the tool results are returned may also last for a long time (inference model).
            # Send a progress event to prevent the front end from falling into long silence after "tool completion"
            await self._emit_progress(progress_callback, {
                "event": "llm_thinking",
                "round": rounds + 2,
                "message": f"Being combined with the {rounds + 1} Wheel tool results continue to analyze…",
            })
            current_response = await self._aretry_chat(current_messages, tools, **kwargs)
            if log_payloads:
                self._log_llm_payload(
                    loop_name="UnifiedLLM·asynchronous",
                    stage="post_tool_llm_response",
                    payload_label=payload_log_label,
                    round_number=rounds + 1,
                    response=current_response,
                )
            self._log_llm_call_timing(
                loop_name="UnifiedLLM·asynchronous",
                stage="post_tool_llm_completed",
                round_number=rounds + 1,
                elapsed_seconds=time.perf_counter() - retry_started_at,
                messages=current_messages,
                response=current_response,
            )
            await self._emit_progress(progress_callback, {
                "event": "tool_round_completed",
                "round": rounds + 1,
            })
            rounds += 1

        # ── Final Synthesis: Force text reply generation when tool rounds are exhausted but LLM still wants to call the tool ──
        if current_response.has_tool_calls:
            logger.warning(
                f"[UnifiedLLM] The number of tool calling rounds has reached the upper limit ({max_rounds}), "
                f"LLM Still requesting tool calls to start final synthesis..."
            )
            await self._emit_progress(progress_callback, {
                "event": "tool_limit_reached",
                "max_rounds": max_rounds,
            })
            # Note: Assistant messages with tool_calls cannot be directly added to the history.
            # Otherwise the API will require the corresponding tool response message (400 error) to be followed immediately.
            # Only the text content within it (if any) is retained as a plain text assistant message.
            if current_response.content:
                current_messages.append(Message(
                    role="assistant",
                    content=current_response.content,
                ))
            # Add a user message to force LLM to generate the final analysis based on existing data
            current_messages.append(Message(
                role="user",
                content=(
                    "The number of tool calls has reached the upper limit, please do not call any more tools."
                    "Please directly generate a complete analysis response based on all the data you have obtained above."
                ),
            ))
            if log_payloads:
                self._log_llm_payload(
                    loop_name="UnifiedLLM·asynchronous",
                    stage="final_summary_llm_prompt",
                    payload_label=payload_log_label,
                    round_number=rounds + 1,
                    messages=current_messages,
                )
            final_summary_started_at = time.perf_counter()
            current_response = await self._aretry_chat(
                current_messages, tools=None, **kwargs
            )
            if log_payloads:
                self._log_llm_payload(
                    loop_name="UnifiedLLM·asynchronous",
                    stage="final_summary_llm_response",
                    payload_label=payload_log_label,
                    round_number=rounds + 1,
                    response=current_response,
                )
            self._log_llm_call_timing(
                loop_name="UnifiedLLM·asynchronous",
                stage="final_summary_llm_completed",
                round_number=rounds + 1,
                elapsed_seconds=time.perf_counter() - final_summary_started_at,
                messages=current_messages,
                response=current_response,
            )
            logger.info("[UnifiedLLM] ✅ Final comprehensive completion")
            await self._emit_progress(progress_callback, {
                "event": "tool_limit_summary_completed",
                "max_rounds": max_rounds,
            })

        return current_response

    @property
    def provider(self) -> LLMProvider:
        """Current provider"""
        return self._adapter.config.provider
    
    @property
    def model(self) -> str:
        """current model"""
        return self._adapter.config.model


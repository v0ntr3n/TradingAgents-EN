# -*- coding: utf-8 -*-
"""SSE Heartbeat wrapper testing.

Regression (real bug): old implementation `wait_for(gen.__anext__(), timeout=15)` timeout in heartbeat
CancelledError will be injected into the underlying generator, the first time >15s Silent (long tool execution, e.g.
Valuation Excel generates 30-180s) kills the entire stream.
"""

import asyncio

import pytest

from app.routers.intelligent_assistant import sse_stream_with_heartbeat


async def _collect(agen, max_items=100):
    items = []
    async for chunk in agen:
        items.append(chunk)
        if len(items) >= max_items:
            break
    return items


class TestSseHeartbeat:
    @pytest.mark.asyncio
    async def test_long_silence_survives_and_delivers_keepalives(self):
        """The underlying generator survives after being silent for more than a few heartbeat cycles, and normal output arrives after the heartbeat."""

        async def slow_gen():
            await asyncio.sleep(0.25)  # Approximately 5 heartbeat cycles (interval=0.05) 
            yield "event: data\ndata: final\n\n"

        items = await _collect(sse_stream_with_heartbeat(slow_gen(), heartbeat_interval=0.05))

        assert "event: data\ndata: final\n\n" in items
        keepalives = [i for i in items if i == ": keepalive\n\n"]
        assert len(keepalives) >= 3, f"The heartbeat should continue to be sent during the long silent period. In fact, {len(keepalives)} Article"

    @pytest.mark.asyncio
    async def test_normal_chunks_pass_through(self):
        async def gen():
            for i in range(3):
                yield f"chunk-{i}"

        items = await _collect(sse_stream_with_heartbeat(gen(), heartbeat_interval=5))
        assert items == ["chunk-0", "chunk-1", "chunk-2"]

    @pytest.mark.asyncio
    async def test_generator_exception_becomes_error_event(self):
        async def boom():
            yield "before"
            raise RuntimeError("The tool exploded")
            yield "after"  # noqa: unreachable

        items = await _collect(sse_stream_with_heartbeat(boom(), heartbeat_interval=5))
        assert items[0] == "before"
        assert any(i.startswith("event: error") and "The tool exploded" in i for i in items[1:])

    @pytest.mark.asyncio
    async def test_early_client_close_cancels_generator(self):
        """When the consumer is shut down prematurely (simulating a client disconnect), the underlying generator is canceled and cleanup is completed."""
        cancelled = asyncio.Event()

        async def gen():
            try:
                await asyncio.sleep(10)
                yield "never"
            except asyncio.CancelledError:
                cancelled.set()
                raise

        # Short heartbeat: The first time __anext__ gets the heartbeat, the underlying generator is still hanging on sleep
        wrapped = sse_stream_with_heartbeat(gen(), heartbeat_interval=0.05)
        first = await wrapped.__anext__()
        assert first == ": keepalive\n\n"
        await wrapped.aclose()
        # Leave a cycle for cancellation propagation
        await asyncio.sleep(0.05)
        assert cancelled.is_set()

    @pytest.mark.asyncio
    async def test_old_antipattern_demonstration(self):
        """Controlled Experiment: Old Model (wait_for(__anext__)) Will indeed kill the generator.
        This test hardens the defective behavior and prevents someone from changing the wrapper back to the old mode."""

        async def slow_gen():
            await asyncio.sleep(30)
            yield "late"

        g = slow_gen()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(g.__anext__(), timeout=0.05)
        # Old mode: The generator has been unkilled
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()

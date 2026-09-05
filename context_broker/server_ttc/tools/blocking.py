"""Run synchronous broker work without blocking shared HTTP sessions."""

from functools import partial
from typing import Any, Callable, TypeVar

import anyio

T = TypeVar("T")


async def run_blocking(function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Use AnyIO's bounded worker pool, preserving request ContextVars."""
    return await anyio.to_thread.run_sync(partial(function, *args, **kwargs))

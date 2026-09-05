"""Bounded OpenAI-compatible inference adapter; never silently switch models."""

import asyncio
import json
from urllib.parse import urlsplit

import httpx

from context_broker.config import LLM_API_KEY, LLM_BASE_URL

MAX_REPLY_BYTES = 64_000
REQUEST_TIMEOUT_SECONDS = 120


class WorkerError(RuntimeError):
    """A worker could not satisfy the delegation contract."""


class CompletionWorker:
    """Use operator-configured credentials, never caller-supplied destinations."""

    def endpoint(self) -> str:
        """Allow HTTPS providers and explicitly configured local HTTP servers."""
        url = urlsplit(LLM_BASE_URL)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and not (local and url.scheme == "http"))
        ):
            raise WorkerError("Configure a valid CONTEXT_BROKER_LLM_BASE_URL first")
        return LLM_BASE_URL.rstrip("/") + "/chat/completions"

    async def complete(self, model: str, prompt: str) -> dict:
        """Enforce a total deadline, even when a provider streams bytes very slowly."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                return await self._complete(model, prompt)
        except TimeoutError:
            raise WorkerError("Worker exceeded the total request deadline") from None

    async def _complete(self, model: str, prompt: str) -> dict:
        """Return complete JSON output only when the provider confirms the exact model."""
        if len(prompt.encode()) > 384_000:
            raise WorkerError("Prompt exceeds the limit; nothing was truncated")
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
                async with client.stream(
                    "POST", self.endpoint(), headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_REPLY_BYTES:
                            raise WorkerError("Worker response exceeded the size limit")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise WorkerError("Provider response must be a JSON object")
            if result.get("model") != model:
                raise WorkerError("Provider returned a different model; no fallback is allowed")
            choices = result.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise WorkerError("Provider response has no valid completion choice")
            choice = choices[0]
            if choice.get("finish_reason") != "stop":
                raise WorkerError("Worker output was incomplete or refused")
            content = json.loads(choice["message"]["content"])
            if not isinstance(content, dict):
                raise WorkerError("Worker must return a JSON object")
            return content
        except WorkerError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise WorkerError("Worker request failed or returned invalid JSON") from None

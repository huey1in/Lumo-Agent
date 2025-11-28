import asyncio
import json
import logging
from typing import Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("LLMClient")


class LLMClient:
    """
    Minimal OpenAI-compatible chat client for local or remote endpoints.
    Uses async httpx to avoid blocking the event loop.
    """

    def __init__(
        self,
        base_url: str = settings.llm_base_url,
        api_key: str = settings.llm_api_key,
        model: str = settings.llm_model,
        timeout: int = settings.request_timeout,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def complete_async(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Async call to OpenAI-compatible /chat/completions endpoint.
        """
        messages = [{"role": "system", "content": "You are a helpful Linux automation agent."}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = await self._get_client()
        
        logger.debug(f"LLM request to {self.base_url}/chat/completions")
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        
        if resp.status_code != 200:
            logger.error(f"LLM Error {resp.status_code}: {resp.text}")
        
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.debug(f"LLM response: {content[:50]}...")
        return content

    def complete(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Sync wrapper for backward compatibility.
        Runs async version in event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, need to run in executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    self._sync_complete, prompt, history, temperature
                )
                return future.result()
        except RuntimeError:
            # No running loop, create one
            return asyncio.run(self.complete_async(prompt, history, temperature))

    def _sync_complete(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
    ) -> str:
        """Pure sync version using requests for thread pool."""
        import requests
        
        messages = [{"role": "system", "content": "You are a helpful Linux automation agent."}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


__all__ = ["LLMClient"]

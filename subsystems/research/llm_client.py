"""
OpenAI-compatible client for local LM Studio only.
Never falls back to cloud Anthropic/OpenAI endpoints.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib import error, request

from loguru import logger

from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


class LocalLLMClient:
    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        model: str = LLM_MODEL,
        api_key: str = LLM_API_KEY,
        timeout_s: float = 45.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def is_reachable(self) -> bool:
        try:
            req = request.Request(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET",
            )
            with request.urlopen(req, timeout=min(5.0, self.timeout_s)) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        req = request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if not choices:
                return None
            return choices[0].get("message", {}).get("content")
        except error.URLError as e:
            logger.warning(f"[LLM] LM Studio unreachable at {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[LLM] chat failed: {e}")
            return None

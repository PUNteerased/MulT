"""
OpenAI-compatible client for local LM Studio only.
Never falls back to cloud Anthropic/OpenAI endpoints.
Supports optional tool-calling when the local model exposes it.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import error, request

from loguru import logger

from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


ToolHandler = Callable[[Dict[str, Any]], str]


class LocalLLMClient:
    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        model: str = LLM_MODEL,
        api_key: str = LLM_API_KEY,
        timeout_s: float = 90.0,
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

    def _post_chat(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                return json.loads(resp.read().decode("utf-8"))
        except error.URLError as e:
            logger.warning(f"[LLM] LM Studio unreachable at {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[LLM] chat failed: {e}")
            return None

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Optional[str]:
        body = self._post_chat(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if not body:
            return None
        choices = body.get("choices") or []
        if not choices:
            return None
        return choices[0].get("message", {}).get("content")

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, ToolHandler],
        temperature: float = 0.2,
        max_tokens: int = 1200,
        max_rounds: int = 4,
    ) -> Tuple[Optional[str], List[Dict[str, Any]], bool]:
        """
        Tool-calling loop against LM Studio.

        Returns (final_content, tool_trace, used_native_tools).
        If the model ignores tools / API rejects tools, used_native_tools=False
        and content may be None — caller should fall back to inject-search path.
        """
        msgs: List[Dict[str, Any]] = [dict(m) for m in messages]
        trace: List[Dict[str, Any]] = []
        used_tools = False

        for _round in range(max_rounds):
            body = self._post_chat(
                {
                    "model": self.model,
                    "messages": msgs,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "tools": tools,
                    "tool_choice": "auto",
                }
            )
            if body is None:
                return None, trace, used_tools

            choices = body.get("choices") or []
            if not choices:
                return None, trace, used_tools

            msg = choices[0].get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            # Some servers put tools under function_call (legacy)
            if not tool_calls and msg.get("function_call"):
                fc = msg["function_call"]
                tool_calls = [
                    {
                        "id": "call_0",
                        "type": "function",
                        "function": {
                            "name": fc.get("name"),
                            "arguments": fc.get("arguments") or "{}",
                        },
                    }
                ]

            if not tool_calls:
                content = msg.get("content")
                return (content if content else None), trace, used_tools

            used_tools = True
            msgs.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {"_raw": raw_args}

                handler = tool_handlers.get(name)
                if handler is None:
                    result = json.dumps({"error": f"unknown_tool:{name}"})
                else:
                    try:
                        result = handler(args if isinstance(args, dict) else {})
                    except Exception as e:
                        result = json.dumps({"error": str(e)})

                trace.append({"tool": name, "args": args, "result_preview": result[:500]})
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id") or "call_0",
                        "name": name,
                        "content": result,
                    }
                )

        # Exhausted rounds — ask for final answer without tools
        final = self.chat(msgs, temperature=temperature, max_tokens=max_tokens)
        return final, trace, used_tools

"""Local provider backed by Ollama (http://127.0.0.1:11434).

Uses the /api/chat endpoint which supports tool calling for models that
advertise the capability (llama3.2, qwen2.5, etc.).
"""

from __future__ import annotations

import json
import uuid

import requests

from .base import ChatResult, ProviderError, ToolCall


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    def available(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=2)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": self._to_ollama(messages),
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            r = requests.post(f"{self.host}/api/chat", json=payload, timeout=300)
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(f"Ollama error {r.status_code}: {r.text[:300]}")

        data = r.json()
        msg = data.get("message", {})
        calls = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(ToolCall(id=uuid.uuid4().hex[:12], name=fn.get("name", ""), arguments=args))
        return ChatResult(content=msg.get("content", "") or "", tool_calls=calls)

    @staticmethod
    def _to_ollama(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            role = m["role"]
            entry: dict = {"role": role, "content": m.get("content", "") or ""}
            if role == "assistant" and m.get("tool_calls"):
                entry["tool_calls"] = [
                    {
                        "function": {
                            "name": c["name"],
                            "arguments": c["arguments"],
                        }
                    }
                    for c in m["tool_calls"]
                ]
            if role == "tool":
                entry["content"] = m.get("content", "")
            out.append(entry)
        return out

"""Cloud providers: OpenAI, Anthropic, Gemini.

All three are normalised to the same ChatResult/ToolCall interface so the
brain code does not care which one is active.
"""

from __future__ import annotations

import json
import uuid

import requests

from .base import ChatResult, ProviderError, ToolCall


def make_cloud_provider(provider: str, model: str, api_key: str):
    provider = (provider or "openai").lower()
    if provider == "anthropic":
        return AnthropicProvider(model, api_key)
    if provider == "gemini":
        return GeminiProvider(model, api_key)
    return OpenAIProvider(model, api_key)


class OpenAIProvider:
    name = "openai"
    base = "https://api.openai.com/v1/chat/completions"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": self._to_openai(messages),
            "tools": tools,
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            r = requests.post(self.base, json=payload, headers=headers, timeout=120)
        except requests.RequestException as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(f"OpenAI error {r.status_code}: {r.text[:300]}")
        choice = r.json()["choices"][0]["message"]
        calls = []
        for tc in choice.get("tool_calls", []) or []:
            fn = tc["function"]
            args = fn.get("arguments", "{}")
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.get("id") or uuid.uuid4().hex[:12], name=fn["name"], arguments=args))
        return ChatResult(content=choice.get("content") or "", tool_calls=calls)

    @staticmethod
    def _to_openai(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            role = m["role"]
            if role == "assistant" and m.get("tool_calls"):
                out.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or None,
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {
                                    "name": c["name"],
                                    "arguments": json.dumps(c["arguments"]),
                                },
                            }
                            for c in m["tool_calls"]
                        ],
                    }
                )
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }
                )
            else:
                out.append({"role": role, "content": m.get("content", "")})
        return out


class AnthropicProvider:
    name = "anthropic"
    base = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        system = ""
        conv = []
        for m in messages:
            if m["role"] == "system":
                system += (m.get("content") or "") + "\n"
                continue
            conv.append(m)

        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]

        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system.strip(),
            "tools": anthropic_tools,
            "messages": self._to_anthropic(conv),
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            r = requests.post(self.base, json=payload, headers=headers, timeout=120)
        except requests.RequestException as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(f"Anthropic error {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = ""
        calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=block.get("id") or uuid.uuid4().hex[:12],
                        name=block.get("name", ""),
                        arguments=block.get("input", {}) or {},
                    )
                )
        return ChatResult(content=text, tool_calls=calls)

    @staticmethod
    def _to_anthropic(conv: list[dict]) -> list[dict]:
        out = []
        for m in conv:
            role = m["role"]
            if role == "assistant" and m.get("tool_calls"):
                content = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for c in m["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": c["id"],
                            "name": c["name"],
                            "input": c["arguments"],
                        }
                    )
                out.append({"role": "assistant", "content": content})
            elif role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.get("tool_call_id", ""),
                                "content": m.get("content", ""),
                            }
                        ],
                    }
                )
            else:
                out.append({"role": role, "content": m.get("content", "")})
        return out


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def _url(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        sys_text = ""
        contents = []
        for m in messages:
            role = m["role"]
            if role == "system":
                sys_text += (m.get("content") or "") + "\n"
                continue
            if role == "assistant" and m.get("tool_calls"):
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for c in m["tool_calls"]:
                    parts.append({"functionCall": {"name": c["name"], "args": c["arguments"]}})
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": m.get("name", "tool"),
                                    "response": {"result": m.get("content", "")},
                                }
                            }
                        ],
                    }
                )
            else:
                g_role = "model" if role == "assistant" else "user"
                contents.append({"role": g_role, "parts": [{"text": m.get("content", "")}]})

        fn_decls = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "parameters": t["function"]["parameters"],
            }
            for t in tools
        ]
        payload: dict = {"contents": contents, "tools": [{"functionDeclarations": fn_decls}]}
        if sys_text.strip():
            payload["systemInstruction"] = {"parts": [{"text": sys_text.strip()}]}

        try:
            r = requests.post(self._url(), json=payload, timeout=120)
        except requests.RequestException as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(f"Gemini error {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = ""
        calls = []
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            parts = []
        for p in parts:
            if "text" in p:
                text += p["text"]
            elif "functionCall" in p:
                fc = p["functionCall"]
                calls.append(
                    ToolCall(id=uuid.uuid4().hex[:12], name=fc.get("name", ""), arguments=fc.get("args", {}) or {})
                )
        return ChatResult(content=text, tool_calls=calls)

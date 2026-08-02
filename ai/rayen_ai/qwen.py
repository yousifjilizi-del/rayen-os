"""Qwen (DashScope) online engine."""
import json
import urllib.error
import urllib.request


class QwenEngine:
    def __init__(self, config):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.api_base = config.get(
            "api_base", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = config.get("api_model", "qwen-plus")

    @property
    def available(self):
        return bool(self.api_key) and self.api_key != "PASTE_QWEN_API_KEY_HERE"

    def _post(self, payload):
        url = f"{self.api_base}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error talking to Qwen: {exc}") from exc

    def chat(self, messages, temperature=0.7):
        if not self.available:
            raise RuntimeError("Qwen API key is not configured")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        data = self._post(payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Qwen response: {data}") from exc

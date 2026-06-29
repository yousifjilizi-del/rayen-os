"""The hybrid brain: chooses between the local (Ollama) and cloud providers.

Selection policy (mode = "hybrid"):
  - Prefer the LOCAL model (private, offline, free).
  - Fall back to the CLOUD provider if the local model is unavailable
    (Ollama not running / model not pulled) AND a cloud key is configured.
mode = "local"  -> only Ollama.
mode = "cloud"  -> only the cloud provider.
"""

from __future__ import annotations

from .config import Config
from .providers.base import ChatResult, ProviderError
from .providers.cloud import make_cloud_provider
from .providers.ollama import OllamaProvider

SYSTEM_PROMPT = """You are Rayen AI, the built-in assistant of Rayen OS, a Linux \
distribution based on Ubuntu with the Xfce desktop. You help the user operate \
their computer by reading the system state and performing actions through the \
tools provided to you.

Guidelines:
- Reply in the same language the user writes in (Arabic or English).
- When the user asks you to do something on the system, use the tools. Do not \
just describe commands — actually call the appropriate tool.
- Prefer the most specific tool (install_package, service_control, write_file, \
read_file, system_info, ...). Use run_command only when no specific tool fits.
- Read-only tools run automatically. Any action that modifies the system will be \
shown to the user for confirmation before it runs, so propose the smallest, \
clearest action that accomplishes the goal.
- After a tool returns, briefly explain the result to the user in plain language.
- Be careful and never propose destructive commands unless the user clearly asks, \
and even then explain the risk first.
- When you are completely done with the user's request, give a short final summary \
and stop calling tools.
"""


class Brain:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.local = OllamaProvider(cfg.ollama_host, cfg.local_model)
        self.cloud = make_cloud_provider(
            cfg.cloud_provider, cfg.cloud_default_model(), cfg.cloud_api_key
        )

    def active_backend(self) -> str:
        """Report which backend would be used right now."""
        if self.cfg.mode == "local":
            return "local"
        if self.cfg.mode == "cloud":
            return "cloud" if self.cloud.available() else "unavailable"
        # hybrid
        if self.local.available():
            return "local"
        if self.cloud.available():
            return "cloud"
        return "unavailable"

    def chat(self, messages: list[dict], tools: list[dict]) -> tuple[ChatResult, str]:
        """Run one model turn. Returns (result, backend_used)."""
        mode = self.cfg.mode
        errors = []

        order: list[str]
        if mode == "local":
            order = ["local"]
        elif mode == "cloud":
            order = ["cloud"]
        else:  # hybrid: local first, cloud fallback
            order = []
            if self.local.available():
                order.append("local")
            if self.cloud.available():
                order.append("cloud")
            if not order:
                order = ["local"]  # try anyway to produce a helpful error

        for backend in order:
            provider = self.local if backend == "local" else self.cloud
            try:
                result = provider.chat(messages, tools)
                return result, backend
            except ProviderError as exc:
                errors.append(f"{backend}: {exc}")
                continue

        raise ProviderError(
            "No AI backend is available. "
            + ("; ".join(errors) if errors else "")
            + " Make sure Ollama is running (and the model is pulled) "
            "or configure a cloud API key with `rayen config`."
        )

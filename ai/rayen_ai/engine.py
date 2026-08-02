"""Engine selection: online Qwen or offline local model."""
from .local import LocalEngine
from .qwen import QwenEngine


class Engine:
    def __init__(self, config):
        self.config = config
        self.qwen = QwenEngine(config)
        self.local = LocalEngine(config)

    def current_name(self):
        if self.config.get("prefer_offline", False):
            if self.local.available:
                return "local"
            return "local (unavailable)"
        if self.qwen.available:
            return "qwen"
        if self.local.available:
            return "local"
        return "none"

    def chat(self, messages, temperature=0.7):
        prefer_offline = self.config.get("prefer_offline", False)
        if not prefer_offline and self.qwen.available:
            return self.qwen.chat(messages, temperature)
        if self.local.available:
            return self.local.chat(messages, temperature)
        if self.qwen.available:
            return self.qwen.chat(messages, temperature)
        raise RuntimeError(
            "No AI engine available. Set a Qwen API key or install the local model."
        )

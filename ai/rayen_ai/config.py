"""Configuration loading for Rayen AI."""
import json
import os

DEFAULT_CONFIG = {
    "api_key": "",
    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_model": "qwen-plus",
    "local_model_path": "/usr/share/rayen-ai/models/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "local_binary": "llama-cli",
    "prefer_offline": False,
    "file_access": {
        "enabled": True,
        "read_dirs": ["/", "/home", "/etc", "/usr", "/var"],
        "allow_write": False,
        "max_read_bytes": 1048576,
    },
}

CONFIG_PATHS = [
    os.environ.get("RAYEN_AI_CONFIG", ""),
    "/etc/rayen-ai/config.json",
    os.path.expanduser("~/.config/rayen-ai/config.json"),
]


def _merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    config = dict(DEFAULT_CONFIG)
    for path in CONFIG_PATHS:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    config = _merge(config, json.load(fh))
            except (OSError, json.JSONDecodeError):
                continue
    return config

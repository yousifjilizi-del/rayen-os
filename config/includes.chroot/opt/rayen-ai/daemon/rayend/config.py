"""Configuration loading for Rayen AI.

Configuration is read from (in order of precedence):
  1. Environment variables (RAYEN_*)
  2. User config file:   ~/.config/rayen-ai/config.json
  3. System config file: /etc/rayen-ai/config.json
  4. Built-in defaults

The config controls which "brain" backend is used (hybrid / local / cloud),
the local Ollama model, and the cloud provider + API key.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

USER_CONFIG = Path(os.path.expanduser("~/.config/rayen-ai/config.json"))
SYSTEM_CONFIG = Path("/etc/rayen-ai/config.json")

# Where the daemon listens. Loopback only — never exposed to the network.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass
class Config:
    # brain mode: "hybrid" | "local" | "cloud"
    mode: str = "hybrid"

    # --- local (Ollama) ---
    ollama_host: str = "http://127.0.0.1:11434"
    local_model: str = "llama3.2:3b"

    # --- cloud ---
    # provider: "openai" | "anthropic" | "gemini"
    cloud_provider: str = "openai"
    cloud_model: str = ""  # empty -> provider default
    cloud_api_key: str = ""

    # --- behaviour ---
    # When True every system-modifying action requires explicit confirmation.
    require_confirmation: bool = True
    # Max agent steps (model<->tool round trips) per user message.
    # Kept modest: each step is a model call (and a cloud step costs money).
    max_steps: int = 6
    language: str = "auto"  # "auto" | "ar" | "en" ...

    # --- server ---
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    extra: dict[str, Any] = field(default_factory=dict)

    def cloud_default_model(self) -> str:
        if self.cloud_model:
            return self.cloud_model
        return {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-latest",
            "gemini": "gemini-1.5-flash",
        }.get(self.cloud_provider, "gpt-4o-mini")

    def save(self, path: Path | None = None) -> None:
        target = path or USER_CONFIG
        target.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_file():
            return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _env_overrides() -> dict[str, Any]:
    mapping = {
        "RAYEN_MODE": "mode",
        "RAYEN_OLLAMA_HOST": "ollama_host",
        "RAYEN_LOCAL_MODEL": "local_model",
        "RAYEN_CLOUD_PROVIDER": "cloud_provider",
        "RAYEN_CLOUD_MODEL": "cloud_model",
        "RAYEN_CLOUD_API_KEY": "cloud_api_key",
        "RAYEN_HOST": "host",
        "RAYEN_PORT": "port",
        "RAYEN_LANGUAGE": "language",
    }
    out: dict[str, Any] = {}
    for env_key, field_name in mapping.items():
        val = os.environ.get(env_key)
        if val is not None and val != "":
            out[field_name] = val

    # Common cloud key fallbacks so the daemon "just works" if a key exists.
    if "cloud_api_key" not in out:
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            if os.environ.get(key):
                out["cloud_api_key"] = os.environ[key]
                if key == "ANTHROPIC_API_KEY":
                    out.setdefault("cloud_provider", "anthropic")
                elif key == "GEMINI_API_KEY":
                    out.setdefault("cloud_provider", "gemini")
                break

    conf = os.environ.get("RAYEN_REQUIRE_CONFIRMATION")
    if conf is not None:
        out["require_confirmation"] = conf.lower() not in ("0", "false", "no")
    return out


def _coerce(cfg: Config) -> Config:
    # port may arrive as a string from env / json
    try:
        cfg.port = int(cfg.port)
    except (TypeError, ValueError):
        cfg.port = DEFAULT_PORT
    if isinstance(cfg.require_confirmation, str):
        cfg.require_confirmation = cfg.require_confirmation.lower() not in (
            "0",
            "false",
            "no",
        )
    return cfg


def load_config() -> Config:
    data: dict[str, Any] = {}
    data.update(_read_json(SYSTEM_CONFIG))
    data.update(_read_json(USER_CONFIG))
    data.update(_env_overrides())

    valid = {f for f in Config.__dataclass_fields__}  # type: ignore[attr-defined]
    known = {k: v for k, v in data.items() if k in valid}
    extra = {k: v for k, v in data.items() if k not in valid}
    cfg = Config(**known)
    if extra:
        cfg.extra.update(extra)
    return _coerce(cfg)

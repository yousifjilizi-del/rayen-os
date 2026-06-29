"""Append-only audit log for every action Rayen AI takes on the system.

Each tool execution (and each user confirmation/rejection) is recorded as a
single JSON line so the user can review exactly what the assistant did.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock

_LOG_DIR = Path(os.path.expanduser("~/.local/share/rayen-ai"))
_LOG_FILE = _LOG_DIR / "audit.log"
_lock = Lock()


def _log_path() -> Path:
    # Fall back to a system path if the home dir is not writable (e.g. service).
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        return _LOG_FILE
    except OSError:
        p = Path("/var/log/rayen-ai")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            return Path("/tmp/rayen-ai-audit.log")
        return p / "audit.log"


def record(event: str, **fields) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event}
    entry.update(fields)
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        try:
            with open(_log_path(), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def tail(n: int = 50) -> list[dict]:
    path = _log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out

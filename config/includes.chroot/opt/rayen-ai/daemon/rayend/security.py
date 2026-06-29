"""Security / confirmation guard for Rayen AI.

Two responsibilities:
  1. Classify each tool invocation as SAFE (read-only) or SENSITIVE
     (system-modifying). SAFE actions may run without confirmation;
     SENSITIVE actions must be approved by the user first.
  2. Detect a small set of catastrophic commands that are blocked outright,
     so the model can never wipe the disk even if the user clicks "approve".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tools that only read state. These never modify the system and so are
# allowed to run without an explicit confirmation prompt.
SAFE_TOOLS = {
    "system_info",
    "read_file",
    "list_directory",
    "search_files",
    "package_search",
    "service_status",
}

# Patterns that are catastrophic and are refused regardless of user approval.
# These are deliberately conservative.
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf?\s+(/|/\*|~|\$HOME|/\*\s|--no-preserve-root)",
    r"\brm\s+-rf?\s+/\s*$",
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;",          # fork bomb
    r"\bmkfs\.",                              # formatting filesystems
    r"\bdd\b.*\bof=/dev/(sd|nvme|vd|hd)",     # raw write to a disk
    r">\s*/dev/(sd|nvme|vd|hd)",              # redirect onto a raw disk
    r"\bchmod\s+-R?\s*0?00?\s+/\s*$",
    r"\b(shutdown|halt|poweroff)\b.*--force.*--force",
]

_BLOCKED_RE = [re.compile(p) for p in _BLOCKED_PATTERNS]


@dataclass
class Decision:
    sensitive: bool          # requires user confirmation
    blocked: bool            # refused outright
    reason: str = ""


def is_blocked_command(command: str) -> str | None:
    """Return a reason string if the command is catastrophic, else None."""
    text = command.strip()
    for rx in _BLOCKED_RE:
        if rx.search(text):
            return (
                "This command matches a catastrophic, irreversible pattern "
                "(e.g. wiping the disk or root filesystem) and is blocked for "
                "your safety."
            )
    return None


def classify(tool_name: str, arguments: dict, require_confirmation: bool) -> Decision:
    """Classify a tool call.

    A blocked command is always blocked. Otherwise, SAFE tools never need
    confirmation; everything else needs confirmation when the daemon is in
    confirmation mode.
    """
    # Hard block check first, for any tool that runs shell commands.
    if tool_name in ("run_command",):
        cmd = str(arguments.get("command", ""))
        reason = is_blocked_command(cmd)
        if reason:
            return Decision(sensitive=True, blocked=True, reason=reason)

    if tool_name in SAFE_TOOLS:
        return Decision(sensitive=False, blocked=False)

    # Everything else is system-modifying.
    if require_confirmation:
        return Decision(sensitive=True, blocked=False)
    return Decision(sensitive=False, blocked=False)

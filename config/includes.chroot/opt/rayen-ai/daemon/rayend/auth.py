"""Local API authentication token for Rayen AI.

The daemon binds to loopback only, but on a multi-user machine *any* local
process could still POST to it. We therefore require a shared secret token on
every request. The token is generated once and stored in the user's config
directory with 0600 permissions, so only the owning user (and the daemon,
which runs as that same user) can read it.

Clients (CLI + desktop) read the same file and send the token in the
`X-Rayen-Token` header. Comparison uses hmac.compare_digest to avoid timing
side-channels.
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

TOKEN_PATH = Path(os.path.expanduser("~/.config/rayen-ai/token"))

# In-process cache so we don't hit the filesystem on every request.
_cached: str | None = None


def get_or_create_token() -> str:
    """Return the API token, creating it (0600) on first use."""
    global _cached
    if _cached:
        return _cached

    # Explicit override (useful for testing / ephemeral setups).
    env = os.environ.get("RAYEN_TOKEN")
    if env:
        _cached = env
        return env

    try:
        if TOKEN_PATH.is_file():
            tok = TOKEN_PATH.read_text().strip()
            if tok:
                _cached = tok
                return tok
    except OSError:
        pass

    tok = secrets.token_urlsafe(32)
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive perms from the start.
        fd = os.open(str(TOKEN_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(tok)
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        # If we cannot persist, the token still works for this process run.
        pass
    _cached = tok
    return tok


def read_token() -> str | None:
    """Client-side: read the token without creating one."""
    env = os.environ.get("RAYEN_TOKEN")
    if env:
        return env
    try:
        if TOKEN_PATH.is_file():
            return TOKEN_PATH.read_text().strip() or None
    except OSError:
        pass
    return None


def verify(presented: str | None) -> bool:
    if not presented:
        return False
    expected = get_or_create_token()
    return hmac.compare_digest(presented, expected)

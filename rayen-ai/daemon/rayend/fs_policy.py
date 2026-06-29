"""Filesystem read policy for Rayen AI.

The model can read files and list directories, but it must NOT be able to
exfiltrate secrets (SSH keys, GPG keyrings, browser cookies/passwords, cloud
credentials, the shadow password file, ...). This is especially important in
hybrid mode, where file contents could be sent to a cloud provider.

Policy = allowlist of roots the model may read from, MINUS a denylist of
sensitive names/paths that are refused even when they live under an allowed
root. Writes are not governed here — they go through the confirmation guard.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))


def _allow_roots() -> list[Path]:
    roots = [
        HOME / "Documents",
        HOME / "Downloads",
        HOME / "Desktop",
        HOME / "Pictures",
        HOME / "Music",
        HOME / "Videos",
        HOME / "Public",
        HOME / "Projects",
        HOME / "Code",
        Path("/etc"),          # system configs (read-only intent)
        Path("/var/log"),      # logs for diagnostics
        Path("/proc"),         # live system state
        Path("/sys"),          # device / kernel info
        Path("/tmp"),
        Path("/opt/rayen-ai"), # the assistant's own code
        Path("/usr/share"),
        Path("/usr/lib/os-release".rsplit("/", 1)[0]),
    ]
    # Allow an extra root via env (advanced users), colon-separated.
    extra = os.environ.get("RAYEN_READ_ROOTS", "")
    for part in extra.split(":"):
        part = part.strip()
        if part:
            roots.append(Path(os.path.expanduser(part)))
    return [r.resolve() for r in roots]


# Sensitive path fragments that are ALWAYS denied, even under an allowed root.
# Matched case-insensitively against the resolved path string and its parts.
_DENY_DIR_NAMES = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".gcloud",
    ".config/gcloud",
    ".kube",
    ".docker",
    ".mozilla",
    ".thunderbird",
    "keyrings",
    "gnome-keyring",
}

# Browser profile dirs that hold cookies / saved passwords.
_DENY_PATH_SUBSTRINGS = (
    "/.config/google-chrome",
    "/.config/chromium",
    "/.config/brave",
    "/.config/microsoft-edge",
    "/.config/rayen-ai",   # our own token + api key live here
    "/.mozilla/firefox",
)

# Specific sensitive filenames anywhere.
_DENY_FILENAMES = {
    "shadow",
    "gshadow",
    "shadow-",
    "gshadow-",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".netrc",
    ".pgpass",
    ".git-credentials",
    "credentials",
    "token",
    "config.json",   # avoids leaking our own api key file by name
    ".env",
}

_DENY_SUFFIXES = (".pem", ".key", ".keystore", ".p12", ".pfx")


def check_read(path: str) -> tuple[bool, str, Path | None]:
    """Return (allowed, reason, resolved_path).

    `allowed` is False when the path is outside the allowlist or matches a
    sensitive pattern. `reason` explains a denial.
    """
    try:
        p = Path(os.path.expanduser(path)).resolve()
    except (OSError, RuntimeError) as exc:
        return False, f"Cannot resolve path: {exc}", None

    s = str(p)
    low = s.lower()

    # Denylist checks first (defence in depth).
    parts_low = {part.lower() for part in p.parts}
    if parts_low & {d.lower() for d in _DENY_DIR_NAMES if "/" not in d}:
        return False, "Refused: path is inside a sensitive directory (keys/credentials).", p
    for frag in _DENY_PATH_SUBSTRINGS:
        if frag in low:
            return False, "Refused: path holds private credentials or browser secrets.", p
    if p.name.lower() in _DENY_FILENAMES:
        return False, "Refused: this filename is treated as a secret.", p
    if low.endswith(_DENY_SUFFIXES):
        return False, "Refused: certificate/private-key files cannot be read.", p

    # Allowlist check.
    for root in _allow_roots():
        try:
            if p == root or root in p.parents:
                return True, "", p
        except OSError:
            continue
    return (
        False,
        "Refused: reading is restricted to your documents and system config "
        "directories. Ask the user to widen RAYEN_READ_ROOTS if needed.",
        p,
    )

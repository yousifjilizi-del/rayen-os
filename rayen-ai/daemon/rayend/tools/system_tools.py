"""Concrete tool implementations that touch the system.

Every function returns a dict. Errors are returned as {"ok": False, "error": ...}
rather than raised, so the model can read and react to them.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

# Maximum bytes we will read back from a file / command output so we never
# blow up the model context window.
_MAX_OUTPUT = 16000


def _truncate(text: str, limit: int = _MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


def _run(argv: list[str] | str, shell: bool = False, timeout: int = 120) -> dict:
    try:
        proc = subprocess.run(
            argv,
            shell=shell,
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
    try:
        p = Path(os.path.expanduser(path))
        if not p.is_file():
            return {"ok": False, "error": f"Not a file: {path}"}
        data = p.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "path": str(p), "content": _truncate(data, max_bytes)}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def list_directory(path: str = ".") -> dict:
    try:
        p = Path(os.path.expanduser(path))
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
    base = os.path.expanduser(path)
    res = _run(["grep", "-rIl", "--", pattern, base], timeout=60)
    if not res.get("ok") and not res.get("stdout"):
        return {"ok": True, "matches": []}
    matches = [m for m in res.get("stdout", "").splitlines() if m][:max_results]
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

def run_command(command: str, use_sudo: bool = False, timeout: int = 300) -> dict:
    """Run an arbitrary shell command. Sensitive — gated by the security guard."""
    cmd = command
    if use_sudo and not command.strip().startswith("sudo"):
        cmd = "sudo -n " + command
    return _run(cmd, shell=True, timeout=timeout)


def install_package(packages: str, use_sudo: bool = True) -> dict:
    """Install one or more APT packages (space-separated)."""
    pkgs = " ".join(packages.split())
    prefix = "sudo -n " if use_sudo else ""
    cmd = f"{prefix}env DEBIAN_FRONTEND=noninteractive apt-get install -y {pkgs}"
    return _run(cmd, shell=True, timeout=600)


def remove_package(packages: str, use_sudo: bool = True) -> dict:
    pkgs = " ".join(packages.split())
    prefix = "sudo -n " if use_sudo else ""
    cmd = f"{prefix}env DEBIAN_FRONTEND=noninteractive apt-get remove -y {pkgs}"
    return _run(cmd, shell=True, timeout=600)


def write_file(path: str, content: str, use_sudo: bool = False) -> dict:
    """Create or overwrite a file with the given content."""
    target = os.path.expanduser(path)
    try:
        if use_sudo:
            # Write via tee so we can elevate without a shell redirect.
            proc = subprocess.run(
                ["sudo", "-n", "tee", target],
                input=content,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stderr": _truncate(proc.stderr),
                "path": target,
            }
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(content, encoding="utf-8")
        return {"ok": True, "path": target, "bytes": len(content.encode())}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def service_control(action: str, name: str, use_sudo: bool = True) -> dict:
    """Control a systemd service. action: start|stop|restart|enable|disable."""
    if action not in ("start", "stop", "restart", "enable", "disable"):
        return {"ok": False, "error": f"Invalid action: {action}"}
    prefix = "sudo -n " if use_sudo else ""
    return _run(f"{prefix}systemctl {action} {name}", shell=True, timeout=60)

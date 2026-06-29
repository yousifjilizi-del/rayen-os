"""Tool registry: maps tool names to implementations + JSON schemas.

The schema is OpenAI "tools" format. Providers that use a different format
(Ollama is compatible, Anthropic / Gemini are adapted in their provider
modules) consume the same registry.
"""

from __future__ import annotations

from typing import Any, Callable

from . import system_tools as t


# name -> (callable, schema)
REGISTRY: dict[str, tuple[Callable[..., dict], dict]] = {}


def _register(name: str, fn: Callable[..., dict], description: str, parameters: dict):
    REGISTRY[name] = (
        fn,
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        },
    )


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
    }


# --- read-only ---
_register(
    "system_info",
    t.system_info,
    "Get a snapshot of the system: OS, kernel, CPU arch, memory, disk usage and load.",
    _obj({}),
)
_register(
    "read_file",
    t.read_file,
    "Read the contents of a text file on disk.",
    _obj({"path": {"type": "string", "description": "Absolute or ~ path to the file."}}, ["path"]),
)
_register(
    "list_directory",
    t.list_directory,
    "List the entries of a directory.",
    _obj({"path": {"type": "string", "description": "Directory path. Defaults to current dir."}}),
)
_register(
    "search_files",
    t.search_files,
    "Recursively search file contents for a text pattern and return matching file paths.",
    _obj(
        {
            "pattern": {"type": "string", "description": "Text pattern to search for."},
            "path": {"type": "string", "description": "Directory to search in."},
        },
        ["pattern"],
    ),
)
_register(
    "package_search",
    t.package_search,
    "Search the APT package repository for available packages by name.",
    _obj({"query": {"type": "string", "description": "Package name to search for."}}, ["query"]),
)
_register(
    "service_status",
    t.service_status,
    "Show the status of a systemd service / unit.",
    _obj({"name": {"type": "string", "description": "Service/unit name, e.g. NetworkManager."}}, ["name"]),
)

# --- system-modifying (require confirmation) ---
_register(
    "run_command",
    t.run_command,
    "Run an arbitrary shell command on the system. Use for tasks no other tool covers. "
    "Set use_sudo=true for commands needing root.",
    _obj(
        {
            "command": {"type": "string", "description": "The shell command to execute."},
            "use_sudo": {"type": "boolean", "description": "Run with sudo (root)."},
        },
        ["command"],
    ),
)
_register(
    "install_package",
    t.install_package,
    "Install one or more APT packages.",
    _obj({"packages": {"type": "string", "description": "Space-separated package names."}}, ["packages"]),
)
_register(
    "remove_package",
    t.remove_package,
    "Remove one or more APT packages.",
    _obj({"packages": {"type": "string", "description": "Space-separated package names."}}, ["packages"]),
)
_register(
    "write_file",
    t.write_file,
    "Create or overwrite a file with the given content. Set use_sudo=true for protected paths.",
    _obj(
        {
            "path": {"type": "string", "description": "Target file path."},
            "content": {"type": "string", "description": "Full file content to write."},
            "use_sudo": {"type": "boolean", "description": "Write as root via sudo."},
        },
        ["path", "content"],
    ),
)
_register(
    "service_control",
    t.service_control,
    "Start, stop, restart, enable or disable a systemd service.",
    _obj(
        {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "restart", "enable", "disable"],
            },
            "name": {"type": "string", "description": "Service/unit name."},
        },
        ["action", "name"],
    ),
)


def tool_schemas() -> list[dict]:
    """Return the list of OpenAI-style tool schemas."""
    return [schema for _, schema in REGISTRY.values()]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict:
    if name not in REGISTRY:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    fn, _ = REGISTRY[name]
    try:
        return fn(**(arguments or {}))
    except TypeError as exc:
        return {"ok": False, "error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001 - surface any tool error to the model
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def command_preview(name: str, arguments: dict[str, Any]) -> str:
    """Human-readable preview of what a tool call will do (for confirmation)."""
    a = arguments or {}
    if name == "run_command":
        sudo = "sudo " if a.get("use_sudo") else ""
        return f"$ {sudo}{a.get('command', '')}"
    if name == "install_package":
        return f"$ sudo apt-get install -y {a.get('packages', '')}"
    if name == "remove_package":
        return f"$ sudo apt-get remove -y {a.get('packages', '')}"
    if name == "write_file":
        sudo = " (as root)" if a.get("use_sudo") else ""
        content = a.get("content", "")
        preview = content if len(content) < 400 else content[:400] + "\n…"
        return f"Write file {a.get('path', '')}{sudo}:\n{preview}"
    if name == "service_control":
        return f"$ sudo systemctl {a.get('action', '')} {a.get('name', '')}"
    return f"{name}({a})"

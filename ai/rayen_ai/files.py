"""System file access for Rayen AI."""
import os


class FileAccess:
    def __init__(self, config):
        fa = config.get("file_access", {})
        self.enabled = fa.get("enabled", True)
        self.read_dirs = fa.get("read_dirs", ["/"])
        self.allow_write = fa.get("allow_write", False)
        self.max_read_bytes = fa.get("max_read_bytes", 1048576)

    def _allowed(self, path):
        real = os.path.realpath(path)
        for directory in self.read_dirs:
            d = os.path.realpath(directory)
            if real == d or real.startswith(d.rstrip(os.sep) + os.sep):
                return True
        return False

    def ls(self, path):
        if not self.enabled:
            return "File access is disabled."
        if not os.path.isdir(path):
            return f"Not a directory: {path}"
        if not self._allowed(path):
            return f"Access denied: {path}"
        try:
            entries = sorted(os.listdir(path))
        except OSError as exc:
            return f"Error listing {path}: {exc}"
        lines = []
        for name in entries[:500]:
            full = os.path.join(path, name)
            try:
                kind = "d" if os.path.isdir(full) else "f"
                size = os.path.getsize(full) if os.path.isfile(full) else "-"
            except OSError:
                kind, size = "?", "?"
            lines.append(f"{kind}\t{size}\t{name}")
        return "\n".join(lines)

    def read(self, path):
        if not self.enabled:
            return "File access is disabled."
        if not os.path.isfile(path):
            return f"Not a file: {path}"
        if not self._allowed(path):
            return f"Access denied: {path}"
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return f"Error reading {path}: {exc}"
        if size > self.max_read_bytes:
            return (
                f"File too large ({size} bytes). Reading first "
                f"{self.max_read_bytes} bytes only."
            )
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read(self.max_read_bytes)
        except OSError as exc:
            return f"Error reading {path}: {exc}"

    def search(self, term, start="/"):
        if not self.enabled:
            return "File access is disabled."
        if not self._allowed(start):
            return f"Access denied: {start}"
        matches = []
        matches.append(f"# Searching for '{term}' under {start}")
        for root, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if term.lower() in name.lower():
                    matches.append(os.path.join(root, name))
                    if len(matches) > 100:
                        matches.append("# ... results truncated")
                        return "\n".join(matches)
        return "\n".join(matches) or f"No files matching '{term}'."

    def write(self, path, content):
        if not self.enabled:
            return "File access is disabled."
        if not self.allow_write:
            return (
                "Write access is disabled. Launch Rayen AI with system "
                "permissions (pkexec rayen-ai) to enable it."
            )
        if not self._allowed(path):
            return f"Access denied: {path}"
        try:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                return f"Directory does not exist: {parent}"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return f"Wrote {len(content)} bytes to {path}"
        except OSError as exc:
            return f"Error writing {path}: {exc}"

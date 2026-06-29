"""Local HTTP API for Rayen AI.

Loopback-only JSON API consumed by the CLI and the desktop app. Stdlib only.

Endpoints:
  GET  /api/health                 -> {ok, version, backend, mode}
  POST /api/chat   {session, text} -> {type: message|confirm|error, ...}
  POST /api/confirm {session, approved} -> {type: message|confirm|error, ...}
  POST /api/reset  {session}       -> {ok}
  GET  /api/audit?n=50             -> {entries: [...]}
  GET  /api/config                 -> sanitised config
  POST /api/config {..fields..}    -> {ok} (persists to user config)
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, audit, auth
from .brain import Brain
from .config import Config, load_config
from .session import Agent, SessionStore


class _State:
    def __init__(self):
        self.cfg: Config = load_config()
        self.brain = Brain(self.cfg)
        self.agent = Agent(self.cfg, self.brain)
        self.store = SessionStore()

    def reload(self):
        self.cfg = load_config()
        self.brain = Brain(self.cfg)
        self.agent = Agent(self.cfg, self.brain)


STATE = _State()


class Handler(BaseHTTPRequestHandler):
    server_version = f"rayend/{__version__}"

    # silence default request logging
    def log_message(self, *_args):  # noqa: D401
        pass

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _authed(self) -> bool:
        """Verify the shared token. /api/health is intentionally exempt so
        clients can probe whether the daemon is up before authenticating."""
        return auth.verify(self.headers.get("X-Rayen-Token"))

    # -- routes ------------------------------------------------------------

    def do_GET(self):  # noqa: N802
        route = urlparse(self.path)
        if route.path == "/api/health":
            return self._send(
                200,
                {
                    "ok": True,
                    "version": __version__,
                    "mode": STATE.cfg.mode,
                    "backend": STATE.brain.active_backend(),
                    "local_model": STATE.cfg.local_model,
                    "cloud_provider": STATE.cfg.cloud_provider,
                },
            )
        if route.path == "/api/audit":
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            q = parse_qs(route.query)
            n = int((q.get("n", ["50"])[0]))
            return self._send(200, {"entries": audit.tail(n)})
        if route.path == "/api/config":
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, self._safe_config())
        return self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path)
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        data = self._read_json()

        if route.path == "/api/chat":
            sid = str(data.get("session", "default"))
            text = str(data.get("text", "")).strip()
            if not text:
                return self._send(400, {"type": "error", "error": "empty message"})
            session = STATE.store.get(sid)
            return self._send(200, STATE.agent.send(session, text))

        if route.path == "/api/confirm":
            sid = str(data.get("session", "default"))
            approved = bool(data.get("approved", False))
            session = STATE.store.get(sid)
            return self._send(200, STATE.agent.confirm(session, approved))

        if route.path == "/api/reset":
            sid = str(data.get("session", "default"))
            STATE.store.drop(sid)
            return self._send(200, {"ok": True})

        if route.path == "/api/config":
            return self._update_config(data)

        return self._send(404, {"error": "not found"})

    # -- config helpers ----------------------------------------------------

    def _safe_config(self) -> dict:
        c = STATE.cfg
        return {
            "mode": c.mode,
            "local_model": c.local_model,
            "ollama_host": c.ollama_host,
            "cloud_provider": c.cloud_provider,
            "cloud_model": c.cloud_model,
            "cloud_api_key_set": bool(c.cloud_api_key),
            "require_confirmation": c.require_confirmation,
            "language": c.language,
        }

    def _update_config(self, data: dict):
        c = STATE.cfg
        allowed = {
            "mode",
            "local_model",
            "ollama_host",
            "cloud_provider",
            "cloud_model",
            "cloud_api_key",
            "require_confirmation",
            "language",
        }
        for key, val in data.items():
            if key in allowed:
                setattr(c, key, val)
        c.save()
        STATE.reload()
        return self._send(200, {"ok": True, "config": self._safe_config()})


def run(host: str | None = None, port: int | None = None):
    cfg = STATE.cfg
    # Ensure the shared auth token exists (0600) before accepting requests.
    auth.get_or_create_token()
    addr = (host or cfg.host, int(port or cfg.port))
    httpd = ThreadingHTTPServer(addr, Handler)
    audit.record("daemon_start", host=addr[0], port=addr[1], mode=cfg.mode)
    print(f"[rayend] Rayen AI daemon listening on http://{addr[0]}:{addr[1]} (mode={cfg.mode})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        audit.record("daemon_stop")

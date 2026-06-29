"""Conversation sessions and the resumable agent loop.

The agent loop is fully reconstructable from the message list, so we never
need a blocking background thread. When the model asks for a SENSITIVE tool we
stop and return a "confirm" outcome; the client approves/rejects and the loop
resumes from the stored messages.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from . import audit
from .brain import Brain, SYSTEM_PROMPT
from .config import Config
from .providers.base import ProviderError
from .security import classify
from .tools.registry import command_preview, execute_tool, tool_schemas


@dataclass
class Pending:
    """A sensitive tool call awaiting user confirmation."""

    call_id: str
    tool: str
    arguments: dict
    preview: str


@dataclass
class Session:
    sid: str
    messages: list[dict] = field(default_factory=list)
    pending: Pending | None = None
    created: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    cloud_warned: bool = False

    def reset(self) -> None:
        self.messages = []
        self.pending = None
        self.cloud_warned = False


_CLOUD_WARNING = (
    "Using the cloud backend — your message and any file contents the assistant "
    "reads may be sent to the configured cloud provider. Switch to local-only "
    "with `rayen config mode=local` for full privacy."
)


class Agent:
    """Drives a single session's agent loop."""

    def __init__(self, cfg: Config, brain: Brain):
        self.cfg = cfg
        self.brain = brain

    # -- public API used by the server -------------------------------------

    def send(self, session: Session, user_text: str) -> dict:
        if not session.messages:
            session.messages.append({"role": "system", "content": SYSTEM_PROMPT})
        session.messages.append({"role": "user", "content": user_text})
        session.last_used = time.time()
        audit.record("user_message", sid=session.sid, text=user_text[:500])
        return self._loop(session)

    def confirm(self, session: Session, approved: bool) -> dict:
        if not session.pending:
            return {"type": "error", "error": "No pending action to confirm."}
        pending = session.pending
        session.pending = None

        if not approved:
            audit.record("rejected", sid=session.sid, tool=pending.tool, args=pending.arguments)
            self._append_tool_result(
                session, pending.call_id, pending.tool,
                {"ok": False, "error": "User declined this action."},
            )
            # Let the model react to the rejection and continue.
            return self._loop(session)

        audit.record("approved", sid=session.sid, tool=pending.tool, args=pending.arguments)
        result = execute_tool(pending.tool, pending.arguments)
        audit.record("executed", sid=session.sid, tool=pending.tool, ok=result.get("ok"))
        self._append_tool_result(session, pending.call_id, pending.tool, result)
        return self._loop(session)

    # -- internal ----------------------------------------------------------

    def _maybe_cloud_warning(self, session: Session, backend: str) -> str | None:
        """Return the privacy warning the first time cloud is used in a session."""
        if backend == "cloud" and not session.cloud_warned:
            session.cloud_warned = True
            audit.record("cloud_used", sid=session.sid)
            return _CLOUD_WARNING
        return None

    def _loop(self, session: Session) -> dict:
        tools = tool_schemas()
        for _ in range(self.cfg.max_steps):
            try:
                result, backend = self.brain.chat(session.messages, tools)
            except ProviderError as exc:
                return {"type": "error", "error": str(exc)}

            if not result.wants_tools:
                # Final assistant message.
                session.messages.append({"role": "assistant", "content": result.content})
                out = {
                    "type": "message",
                    "content": result.content or "(no response)",
                    "backend": backend,
                }
                warn = self._maybe_cloud_warning(session, backend)
                if warn:
                    out["warning"] = warn
                return out

            # Record the assistant turn that requested tools.
            session.messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [
                        {"id": c.id, "name": c.name, "arguments": c.arguments}
                        for c in result.tool_calls
                    ],
                }
            )

            # Execute safe tools immediately; stop at the first sensitive one.
            for call in result.tool_calls:
                decision = classify(call.name, call.arguments, self.cfg.require_confirmation)

                if decision.blocked:
                    self._append_tool_result(
                        session, call.id, call.name,
                        {"ok": False, "error": decision.reason},
                    )
                    audit.record("blocked", sid=session.sid, tool=call.name, args=call.arguments)
                    continue

                if decision.sensitive:
                    # Pause and ask the user. Remaining tool calls in this turn
                    # will be re-driven by the model after confirmation.
                    session.pending = Pending(
                        call_id=call.id,
                        tool=call.name,
                        arguments=call.arguments,
                        preview=command_preview(call.name, call.arguments),
                    )
                    audit.record("proposed", sid=session.sid, tool=call.name, args=call.arguments)
                    out = {
                        "type": "confirm",
                        "tool": call.name,
                        "arguments": call.arguments,
                        "preview": session.pending.preview,
                        "assistant_note": result.content or "",
                        "backend": backend,
                    }
                    warn = self._maybe_cloud_warning(session, backend)
                    if warn:
                        out["warning"] = warn
                    return out

                # Safe tool -> run now.
                res = execute_tool(call.name, call.arguments)
                audit.record("executed_safe", sid=session.sid, tool=call.name, ok=res.get("ok"))
                self._append_tool_result(session, call.id, call.name, res)

            # loop again so the model can read tool results
        return {
            "type": "message",
            "content": "Reached the maximum number of steps for this request.",
            "backend": "n/a",
        }

    @staticmethod
    def _append_tool_result(session: Session, call_id: str, name: str, result: dict) -> None:
        session.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get(self, sid: str) -> Session:
        s = self._sessions.get(sid)
        if s is None:
            s = Session(sid=sid)
            self._sessions[sid] = s
        return s

    def drop(self, sid: str) -> None:
        self._sessions.pop(sid, None)

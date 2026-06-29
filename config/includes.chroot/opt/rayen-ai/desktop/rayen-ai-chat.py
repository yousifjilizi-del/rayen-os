#!/usr/bin/env python3
"""Rayen AI — desktop chat application (GTK 3 / PyGObject).

A ChatGPT-style window for Rayen OS. Talks to the local rayend daemon and
implements the "confirm before execute" flow with an in-window approval card
for any system-modifying action.

Network/daemon calls run on a worker thread; UI updates are marshalled back to
the GTK main loop via GLib.idle_add.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from urllib import error, request

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

HOST = os.environ.get("RAYEN_HOST", "127.0.0.1")
PORT = os.environ.get("RAYEN_PORT", "8765")
BASE = f"http://{HOST}:{PORT}"

CSS = b"""
.rayen-window { background-color: #0f1419; }
.msg-user {
  background-color: #1d6fe0; color: #ffffff;
  border-radius: 14px; padding: 10px 14px; margin: 4px 8px;
}
.msg-assistant {
  background-color: #1b2430; color: #e6edf3;
  border-radius: 14px; padding: 10px 14px; margin: 4px 8px;
}
.msg-system { color: #8b98a5; font-style: italic; padding: 4px 8px; }
.confirm-card {
  background-color: #2a2113; color: #f0d99b;
  border: 1px solid #c79a3a; border-radius: 12px;
  padding: 12px; margin: 6px 8px;
}
.confirm-preview {
  background-color: #11161d; color: #d6e2ee;
  font-family: monospace; border-radius: 8px; padding: 8px;
}
.input-entry {
  background-color: #1b2430; color: #e6edf3;
  border-radius: 12px; padding: 8px; caret-color: #e6edf3;
}
.send-btn { background-color: #1d6fe0; color: #ffffff; border-radius: 12px; padding: 8px 16px; }
.approve-btn { background-color: #2ea043; color: #ffffff; border-radius: 8px; }
.reject-btn { background-color: #b6433a; color: #ffffff; border-radius: 8px; }
.statusbar { color: #8b98a5; padding: 4px 10px; font-size: 11px; }
.title { color: #e6edf3; font-weight: bold; }
"""


def api(method: str, path: str, payload: dict | None = None) -> dict:
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read() or b"{}")


class ChatWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Rayen AI")
        self.set_default_size(560, 720)
        self.get_style_context().add_class("rayen-window")
        self.session = uuid.uuid4().hex[:16]

        self._load_css()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        # Header
        header = Gtk.HeaderBar(title="Rayen AI")
        header.set_subtitle("Your built-in system assistant")
        header.set_show_close_button(True)
        self.status_btn = Gtk.Button(label="●")
        self.status_btn.set_tooltip_text("Backend status")
        self.status_btn.connect("clicked", lambda *_: self.refresh_status())
        header.pack_end(self.status_btn)
        clear_btn = Gtk.Button(label="New chat")
        clear_btn.connect("clicked", self.on_clear)
        header.pack_end(clear_btn)
        self.set_titlebar(header)

        # Scrollable message area
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.messages.set_margin_top(8)
        self.messages.set_margin_bottom(8)
        self.scroll.add(self.messages)
        root.pack_start(self.scroll, True, True, 0)

        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_row.set_margin_start(8)
        input_row.set_margin_end(8)
        input_row.set_margin_top(4)
        input_row.set_margin_bottom(8)
        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("input-entry")
        self.entry.set_placeholder_text("Ask Rayen to do anything on your system…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.on_send)
        self.send_btn = Gtk.Button(label="Send")
        self.send_btn.get_style_context().add_class("send-btn")
        self.send_btn.connect("clicked", self.on_send)
        input_row.pack_start(self.entry, True, True, 0)
        input_row.pack_start(self.send_btn, False, False, 0)
        root.pack_start(input_row, False, False, 0)

        # Status bar
        self.statusbar = Gtk.Label(label="Connecting…", xalign=0)
        self.statusbar.get_style_context().add_class("statusbar")
        root.pack_start(self.statusbar, False, False, 0)

        self.add_message("system", "Welcome to Rayen AI. Read-only actions run "
                                    "automatically; anything that changes your system "
                                    "will ask for your approval first.")
        self.refresh_status()

    # -- styling ----------------------------------------------------------
    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # -- message helpers --------------------------------------------------
    def add_message(self, role: str, text: str) -> Gtk.Label:
        align = Gtk.Align.END if role == "user" else Gtk.Align.START
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_selectable(True)
        label.set_max_width_chars(54)
        css_class = {
            "user": "msg-user",
            "assistant": "msg-assistant",
        }.get(role, "msg-system")
        label.get_style_context().add_class(css_class)
        if role == "system":
            row.set_halign(Gtk.Align.CENTER)
        else:
            row.set_halign(align)
        row.pack_start(label, False, False, 0)
        self.messages.pack_start(row, False, False, 0)
        row.show_all()
        self._scroll_to_bottom()
        return label

    def _scroll_to_bottom(self):
        def _do():
            adj = self.scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            return False
        GLib.idle_add(_do)

    # -- actions ----------------------------------------------------------
    def on_clear(self, *_):
        try:
            api("POST", "/api/reset", {"session": self.session})
        except error.URLError:
            pass
        self.session = uuid.uuid4().hex[:16]
        for child in self.messages.get_children():
            self.messages.remove(child)
        self.add_message("system", "Started a new conversation.")

    def set_busy(self, busy: bool):
        self.entry.set_sensitive(not busy)
        self.send_btn.set_sensitive(not busy)
        if busy:
            self.statusbar.set_text("Rayen is thinking…")

    def on_send(self, *_):
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.add_message("user", text)
        self.set_busy(True)
        threading.Thread(
            target=self._worker_chat, args=(text,), daemon=True
        ).start()

    def _worker_chat(self, text: str):
        try:
            resp = api("POST", "/api/chat", {"session": self.session, "text": text})
        except error.URLError as exc:
            GLib.idle_add(self._show_error, str(exc))
            return
        GLib.idle_add(self._handle_response, resp)

    def _worker_confirm(self, approved: bool):
        try:
            resp = api("POST", "/api/confirm", {"session": self.session, "approved": approved})
        except error.URLError as exc:
            GLib.idle_add(self._show_error, str(exc))
            return
        GLib.idle_add(self._handle_response, resp)

    # -- response handling ------------------------------------------------
    def _handle_response(self, resp: dict):
        kind = resp.get("type")
        if kind == "message":
            self.set_busy(False)
            self.statusbar.set_text(f"Backend: {resp.get('backend', '?')}")
            self.add_message("assistant", resp.get("content", ""))
        elif kind == "confirm":
            self._show_confirm_card(resp)
        elif kind == "error":
            self.set_busy(False)
            self._show_error(resp.get("error", "unknown error"))
        return False

    def _show_error(self, message: str):
        self.set_busy(False)
        self.statusbar.set_text("Error")
        self.add_message("system", f"⚠ {message}")
        return False

    def _show_confirm_card(self, resp: dict):
        note = resp.get("assistant_note") or ""
        if note:
            self.add_message("assistant", note)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("confirm-card")

        title = Gtk.Label(xalign=0)
        title.set_markup("<b>Rayen wants to perform this action</b>")
        card.pack_start(title, False, False, 0)

        preview = Gtk.Label(label=resp.get("preview", ""), xalign=0)
        preview.set_line_wrap(True)
        preview.set_selectable(True)
        preview.get_style_context().add_class("confirm-preview")
        card.pack_start(preview, False, False, 0)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        approve = Gtk.Button(label="Approve & run")
        approve.get_style_context().add_class("approve-btn")
        reject = Gtk.Button(label="Reject")
        reject.get_style_context().add_class("reject-btn")
        btns.pack_end(approve, False, False, 0)
        btns.pack_end(reject, False, False, 0)
        card.pack_start(btns, False, False, 0)

        row = Gtk.Box()
        row.set_halign(Gtk.Align.START)
        row.pack_start(card, False, False, 0)
        self.messages.pack_start(row, False, False, 0)
        row.show_all()
        self._scroll_to_bottom()

        def decide(approved: bool):
            approve.set_sensitive(False)
            reject.set_sensitive(False)
            result = Gtk.Label(xalign=0)
            result.set_text("→ Executing…" if approved else "→ Skipped.")
            result.get_style_context().add_class("msg-system")
            card.pack_start(result, False, False, 0)
            result.show()
            self.set_busy(True)
            threading.Thread(
                target=self._worker_confirm, args=(approved,), daemon=True
            ).start()

        approve.connect("clicked", lambda *_: decide(True))
        reject.connect("clicked", lambda *_: decide(False))
        return False

    # -- status -----------------------------------------------------------
    def refresh_status(self):
        def worker():
            try:
                h = api("GET", "/api/health")
                GLib.idle_add(self._apply_status, h)
            except error.URLError:
                GLib.idle_add(
                    self.statusbar.set_text,
                    "Daemon offline — start it with: systemctl --user start rayend",
                )
        threading.Thread(target=worker, daemon=True).start()

    def _apply_status(self, h: dict):
        backend = h.get("backend", "?")
        self.statusbar.set_text(
            f"mode: {h.get('mode')}  ·  backend: {backend}  ·  "
            f"model: {h.get('local_model')}"
        )
        return False


def main():
    win = ChatWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

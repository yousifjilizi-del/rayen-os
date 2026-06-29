# Rayen AI

A full system-level AI assistant built into **Rayen OS**. It understands natural
language (Arabic and English), reasons with a hybrid local/cloud brain, and can
**actually operate the system** — install packages, edit files, manage services,
inspect hardware — with a **confirm-before-execute** safety model.

## Architecture

```
 Desktop chat app (GTK)  ─┐
                          ├─►  rayend daemon  ─►  Hybrid Brain  ─►  Tools  ─►  Security guard
 rayen CLI               ─┘   (127.0.0.1:8765)   local + cloud      (system)    (confirm + audit)
```

| Component | Path | Description |
|-----------|------|-------------|
| Daemon (`rayend`) | `daemon/rayend/` | The brain + tools + security + audit, exposed over a loopback HTTP API. Runs as a systemd service. |
| CLI (`rayen`) | `cli/rayen` | Terminal client. One-shot (`rayen "..."`) or interactive (`rayen chat`). |
| Desktop app | `desktop/rayen-ai-chat.py` | GTK chat window, listed as **Rayen AI** in the app menu. |
| Installer | `install.sh` | Installs everything onto a running Debian/Ubuntu system. |

## The hybrid brain

`mode` controls which backend answers:

- **`hybrid`** (default) — uses the **local** model (Ollama) when available, and
  falls back to the **cloud** provider when a cloud API key is set and the
  local model is unreachable.
- **`local`** — Ollama only (fully offline, private).
- **`cloud`** — cloud provider only.

Default local model: **`llama3.2:3b`** (pulled on first boot). Supported cloud
providers: **OpenAI**, **Anthropic**, **Gemini** (the user supplies the key).

## Safety model — confirm before execute

Every tool is classified:

- **Read-only** tools (`system_info`, `read_file`, `list_directory`, `search_files`)
  run automatically with no prompt.
- **System-modifying** tools (`run_command`, `install_package`, `remove_package`,
  `write_file`, `service_control`) are **previewed and require explicit approval**
  before they run.
- A **blocklist** rejects catastrophic commands outright (e.g. `rm -rf /`,
  fork bombs, disk wipes) even if approved.
- Every action — proposed, approved, rejected, executed — is written to an
  **audit log** at `~/.local/share/rayen-ai/audit.log`.

## Usage

```bash
# one-shot
rayen "install neofetch then show me system info"

# interactive chat
rayen chat

# status of the daemon + active backend
rayen status

# view/set config
rayen config                                  # show all
rayen config mode=local                        # offline only
rayen config cloud_provider=openai cloud_api_key=sk-...
rayen config require_confirmation=false        # expert mode (not recommended)

# recent audit entries
rayen audit 20

# clear the conversation
rayen reset
```

The desktop app provides the same flow with on-screen **Approve / Reject**
buttons for each proposed action.

## Configuration

Config is merged from (highest priority first):

1. Environment variables — `RAYEN_MODE`, `RAYEN_LOCAL_MODEL`, `RAYEN_CLOUD_API_KEY`, …
2. `~/.config/rayen-ai/config.json` (per user)
3. `/etc/rayen-ai/config.json` (system default, written by the ISO build)
4. Built-in defaults

The daemon also auto-detects `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` /
`GEMINI_API_KEY` from the environment.

## Installing on a running system (for testing)

```bash
cd rayen-ai
sudo ./install.sh
```

This installs the Python deps, Ollama, the systemd service, the CLI, and the
desktop entry, then pulls the default model.

## How it ships in the ISO

`live-build` integration lives in the repo root:

- `config/package-lists/03-ai.list.chroot` — Python + GTK + curl runtime.
- `config/includes.chroot/opt/rayen-ai/` — the daemon + desktop app.
- `config/includes.chroot/usr/local/bin/rayen` — the CLI.
- `config/includes.chroot/etc/systemd/system/rayend.service` — the daemon service.
- `config/hooks/chroot/03-ai-setup.chroot` — installs Ollama, enables services,
  and schedules a first-boot model pull.

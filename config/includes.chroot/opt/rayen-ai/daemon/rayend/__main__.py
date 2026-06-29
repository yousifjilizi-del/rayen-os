"""Entry point: `python3 -m rayend` starts the Rayen AI daemon."""

from __future__ import annotations

import argparse

from .server import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="rayend", description="Rayen AI daemon")
    parser.add_argument("--host", default=None, help="Bind host (default from config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default from config)")
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

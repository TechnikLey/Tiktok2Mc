#!/usr/bin/env python3
"""Standalone API server entry point for TikTok2MC.

Starts the central FastAPI server on ``127.0.0.1:29185``.
All existing components (plugins, Minecraft server, TikTok bridge)
continue to run independently — this is the first step toward a
unified control plane.

Usage
-----
    python run.py                # dev mode
    python run.py --port 8080    # custom port
    python run.py --host 0.0.0.0 # network access (use with care)
"""

import argparse
import logging
import os
import sys

# Ensure src/ is on the path for development runs.
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import uvicorn

from core.api import create_app
from core.api.server import DEFAULT_PORT

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok2MC API server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RESOLVED_PORT_API_PORT", DEFAULT_PORT)),
        help=f"Port number (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    app = create_app()

    if args.host == "0.0.0.0":
        log.warning(
            "API bound to 0.0.0.0 — accessible from other network devices. "
            "Use 127.0.0.1 to restrict to localhost."
        )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

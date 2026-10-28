#!/usr/bin/env python3
"""CP1 smoke test for TigerGraph Savanna: can we reach the instance and run a trivial query?

Separate from the chain smoke test so a stopped free-tier instance (RISKS.md S1) is reported
as exactly that, rather than contaminating an unrelated checkpoint.

    python scripts/tg_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceledger.config import ConfigError, load_config


def _looks_stopped(host: str) -> str | None:
    """Ask an unauthenticated endpoint whether the workspace is simply stopped.

    Returns the server's own explanation, or None if that is not the problem.
    """
    try:
        import requests
        response = requests.get(f"{host}/api/ping", timeout=20)
    except Exception:  # noqa: BLE001 - diagnosis is best-effort
        return None
    body = response.text or ""
    for marker in ("Auto start is not enabled", "Failed to start workspace",
                   "workspace is not running", "Workspace is stopped"):
        if marker.lower() in body.lower():
            return marker
    return None


def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    if not cfg.tg_host:
        print("SKIP: TG_HOST is not set in .env.\n"
              "      See docs/setup_sponsors.md step 1. For a Savanna workspace you need TG_HOST\n"
              "      and TG_SECRET (a database secret); username/password is the self-hosted path.\n"
              "      CP1 cannot be ticked until this runs green.", file=sys.stderr)
        return 2
    if not (cfg.tg_secret or (cfg.tg_username and cfg.tg_password)):
        print("SKIP: no TigerGraph credentials. Set TG_SECRET (Savanna: a database secret), or\n"
              "      TG_USERNAME + TG_PASSWORD for a self-hosted instance.", file=sys.stderr)
        return 2

    try:
        import pyTigerGraph as tg
    except ImportError:
        print("FAIL: pyTigerGraph is not installed. Run: .venv/bin/pip install pyTigerGraph",
              file=sys.stderr)
        return 1

    print(f"host  : {cfg.tg_host}")
    print(f"graph : {cfg.tg_graph}")
    # Savanna authenticates with a database secret and no username/password; a self-hosted
    # instance uses username/password. Pick whichever the .env actually supplies.
    auth = "TG_SECRET (Savanna)" if cfg.tg_secret else "TG_USERNAME/TG_PASSWORD (self-hosted)"
    print(f"auth  : {auth}")
    try:
        if cfg.tg_secret:
            conn = tg.TigerGraphConnection(
                host=cfg.tg_host, graphname=cfg.tg_graph, gsqlSecret=cfg.tg_secret)
            conn.getToken(cfg.tg_secret)
        else:
            conn = tg.TigerGraphConnection(
                host=cfg.tg_host, graphname=cfg.tg_graph,
                username=cfg.tg_username, password=cfg.tg_password)
        print(f"version: {conn.getVer()}")
        # Trivial query: echo the vertex types the graph knows about. Works on an empty graph.
        print(f"echo   : {conn.echo()}")
        vertex_types = conn.getVertexTypes()
        print(f"vertex types ({len(vertex_types)}): {vertex_types or '(none yet - schema not created)'}")
    except Exception as exc:  # noqa: BLE001 - we want the real reason in the log
        message = str(exc)
        print(f"FAIL: could not reach TigerGraph: {type(exc).__name__}: {message}", file=sys.stderr)
        # A stopped Savanna workspace answers every endpoint with HTTP 500 and the body
        # "Auto start is not enabled for this workspace" / "Failed to start workspace".
        # That is not a credential or host problem, so say so rather than send anyone hunting.
        if "500" in message or "Internal Server Error" in message:
            stopped = _looks_stopped(cfg.tg_host)
            if stopped:
                print("\n      DIAGNOSIS: the workspace is STOPPED. The server replied:\n"
                      f"      {stopped}\n"
                      "      Your host and secret are probably fine. Start the workspace in the\n"
                      "      Savanna console and retry. Note it bills ~$1/hr at TG-00 while running.",
                      file=sys.stderr)
                return 3
        print("      Check: workspace started? host correct? secret still valid?\n"
              "      See docs/setup_sponsors.md step 1.", file=sys.stderr)
        return 1

    print("\nOK: TigerGraph reachable and answering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Capture real transactions from the chain as offline test fixtures.

The parser must be verified against *known real transactions* (RISKS.md P6). Fixtures let that
verification run in CI with no network, while remaining genuine chain data rather than invented
JSON (G3). Re-run this to refresh them.

    python scripts/capture_fixtures.py <tx_hash> [<tx_hash> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceledger.config import load_config
from traceledger.chain.rpc import EvmRpc
from traceledger.chain.transfers import normalise_hash

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main(hashes: list[str]) -> int:
    if not hashes:
        print(__doc__, file=sys.stderr)
        return 2
    cfg = load_config()
    rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
    chain_id = rpc.assert_chain()
    head = int(rpc.call("eth_blockNumber"), 16)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    for raw in hashes:
        h = normalise_hash(raw)
        tx = rpc.call("eth_getTransactionByHash", [h])
        receipt = rpc.call("eth_getTransactionReceipt", [h])
        if tx is None or receipt is None:
            print(f"SKIP {h}: not found or pending", file=sys.stderr)
            continue
        payload = {
            "_comment": "Real chain data captured by scripts/capture_fixtures.py. Not synthetic.",
            "chain_id": chain_id,
            "rpc_url": cfg.rpc_url,
            "captured_at_head_block": head,
            "tx": tx,
            "receipt": receipt,
        }
        out = FIXTURE_DIR / f"tx_{h[2:10]}.json"
        out.write_text(json.dumps(payload, indent=2) + "\n")
        n_logs = len(receipt.get("logs") or [])
        print(f"wrote {out.name}  block={int(receipt['blockNumber'],16)} logs={n_logs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

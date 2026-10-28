#!/usr/bin/env python3
"""CP1 smoke test: confirm the RPC is the chain we think it is and that each configured
token contract really exists, then record what it reports.

Writes data/token_registry.json so later layers never have to re-guess decimals (G7).
Read-only; needs no key material.

    python scripts/verify_tokens.py [extra_address ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceledger.config import ConfigError, load_config
from traceledger.chain.rpc import EvmRpc, RpcError
from traceledger.chain.tokens import TokenMetadataError, read_token_metadata

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "token_registry.json"


def main(argv: list[str]) -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
    print(f"RPC      : {cfg.rpc_url}")
    try:
        chain_id = rpc.assert_chain()
    except RpcError as exc:
        print(f"FAIL     : {exc}", file=sys.stderr)
        return 1
    block = int(rpc.call("eth_blockNumber"), 16)
    print(f"chain id : {chain_id} ({cfg.chain_name}) OK")
    print(f"head     : block {block}")
    print()

    registry: dict[str, dict] = {}
    failures: list[str] = []
    targets = [(a, lbl) for a, lbl in cfg.token_contracts.items()]
    targets += [(a.strip().lower(), "EXTRA") for a in argv]

    for address, label in targets:
        try:
            meta = read_token_metadata(rpc, address)
        except (TokenMetadataError, RpcError) as exc:
            print(f"FAIL  {label:5} {address}\n        {exc}")
            failures.append(address)
            continue
        symbol_note = ""
        if label != "EXTRA" and meta.symbol and meta.symbol.upper() != label:
            # Not an error. The contract address is the identity; this only means a
            # symbol-matching reconciler would have gone wrong here (G7).
            symbol_note = f"  <-- reports {meta.symbol!r}, not {label!r}; symbol matching would fail here"
        print(f"OK    {label:5} {address}")
        print(f"        symbol={meta.symbol!r} name={meta.name!r} decimals={meta.decimals}{symbol_note}")
        entry = meta.as_dict()
        entry["env_label"] = label
        registry[address] = entry

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(
        {"chain_id": chain_id, "chain_name": cfg.chain_name, "rpc_url": cfg.rpc_url,
         "verified_at_block": block, "tokens": registry}, indent=2) + "\n")
    print(f"\nwrote {OUT_PATH.relative_to(Path.cwd())}  ({len(registry)} token(s), {rpc.request_count} RPC calls)")

    if failures:
        print(f"\n{len(failures)} contract(s) failed verification.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

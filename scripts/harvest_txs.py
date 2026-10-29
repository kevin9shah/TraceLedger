#!/usr/bin/env python3
"""Harvest real Polygon transactions of varied shapes, to serve as the chain side of the benchmark.

Only business records in the benchmark are synthetic (G3, RISKS.md P4). Chain facts come from real
transactions so the benchmark cannot pass merely because the on-chain data was invented to suit it.

Writes data/tx_pool.json, classifying each transaction by shape:
    single_transfer   one Transfer event, one token
    multi_transfer    several transfers of ONE token (split / fee legs)
    multi_token       transfers of two or more tokens in one transaction
    reverted          status 0: moved nothing

    python scripts/harvest_txs.py [--blocks 60] [--target 40]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceledger.chain.rpc import EvmRpc, RpcError
from traceledger.chain.transfers import TRANSFER_TOPIC, fetch_transaction_facts
from traceledger.config import load_config

OUT = Path(__file__).resolve().parent.parent / "data" / "tx_pool.json"


def classify(facts) -> str:
    if not facts.succeeded:
        return "reverted"
    tokens = facts.tokens_involved()
    if len(tokens) > 1:
        return "multi_token"
    if len(facts.transfers) > 1:
        return "multi_transfer"
    return "single_transfer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=60, help="how many recent blocks to scan")
    ap.add_argument("--target", type=int, default=40, help="how many transactions to keep")
    args = ap.parse_args()

    cfg = load_config()
    rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
    chain_id = rpc.assert_chain()
    head = int(rpc.call("eth_blockNumber"), 16)
    start = head - args.blocks
    print(f"chain {chain_id}, scanning blocks {start}..{head}")

    # Collect candidate hashes from Transfer logs on the configured tokens.
    hashes: list[str] = []
    for token in cfg.token_contracts:
        logs = rpc.call("eth_getLogs", [{
            "fromBlock": hex(start), "toBlock": hex(head),
            "address": token, "topics": [TRANSFER_TOPIC],
        }])
        for log in logs or []:
            h = log["transactionHash"]
            if h not in hashes:
                hashes.append(h)
    print(f"{len(hashes)} candidate transactions from Transfer logs")

    entries: list[dict] = []
    shapes: Counter[str] = Counter()
    # Favour shape diversity over raw count: keep scanning until each shape is represented.
    for h in hashes:
        if len(entries) >= args.target:
            break
        try:
            facts = fetch_transaction_facts(rpc, h)
        except (RpcError, ValueError) as exc:
            print(f"  skip {h[:12]}…: {exc}")
            continue
        shape = classify(facts)
        # Cap the common shape so the pool is not 95% single transfers.
        if shape == "single_transfer" and shapes[shape] >= args.target // 2:
            continue
        shapes[shape] += 1
        entries.append({
            "tx_hash": facts.tx_hash,
            "shape": shape,
            "origin": "public_mainnet",
            "chain_id": facts.chain_id,
            "block_number": facts.block_number,
            "status": facts.status,
            "sender": facts.sender,
            "called_contract": facts.called_contract,
            "tokens": list(facts.tokens_involved()),
            "transfers": [t.as_dict() for t in facts.transfers],
            "simulated": False,
        })

    # Reverted transactions emit NO Transfer logs, so eth_getLogs cannot see them. They must be
    # found by reading block transaction lists and checking receipt status. This is exactly the
    # "the ledger says paid but nothing moved" case, so the pool would be incomplete without it.
    wanted_reverted = max(3, args.target // 10)
    print(f"\nscanning block transaction lists for up to {wanted_reverted} reverted transactions")
    found = 0
    for block_number in range(head, head - 12, -1):
        if found >= wanted_reverted:
            break
        block = rpc.call("eth_getBlockByNumber", [hex(block_number), True])
        if not block:
            continue
        for tx in block.get("transactions", []):
            if found >= wanted_reverted:
                break
            if not tx.get("to") or tx.get("input", "0x") in ("0x", ""):
                continue  # plain value sends are not interesting failures
            receipt = rpc.call("eth_getTransactionReceipt", [tx["hash"]])
            if not receipt or int(receipt.get("status", "0x1"), 16) != 0:
                continue
            try:
                facts = fetch_transaction_facts(rpc, tx["hash"])
            except (RpcError, ValueError):
                continue
            shapes["reverted"] += 1
            found += 1
            entries.append({
                "tx_hash": facts.tx_hash, "shape": "reverted", "origin": "public_mainnet",
                "chain_id": facts.chain_id, "block_number": facts.block_number,
                "status": facts.status, "sender": facts.sender,
                "called_contract": facts.called_contract,
                "tokens": list(facts.tokens_involved()),
                "transfers": [t.as_dict() for t in facts.transfers],
                "gas_used": int(receipt.get("gasUsed", "0x0"), 16),
                "note": ("Reverted: moved nothing but still consumed gas. Emits no Transfer "
                         "logs, so log scanning cannot find it."),
                "simulated": False,
            })
    print(f"  found {found} reverted")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": ("Real Polygon transactions harvested by scripts/harvest_txs.py. The chain side "
                     "of the benchmark is real; only business records are synthetic (G3, P4)."),
        "chain_id": chain_id, "rpc_url": cfg.rpc_url,
        "scanned_blocks": [start, head],
        "shapes": dict(shapes),
        "transactions": entries,
    }, indent=2) + "\n")
    print(f"\nwrote {OUT.name}: {len(entries)} transactions")
    for shape, n in sorted(shapes.items()):
        print(f"  {shape:16} {n}")
    print(f"RPC calls: {rpc.request_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

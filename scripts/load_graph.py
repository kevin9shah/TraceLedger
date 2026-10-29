#!/usr/bin/env python3
"""Build the TraceLedger graph dataset and load it into TigerGraph.

Source data:
  * `benchmark/cases.json`      — 25 synthetic business-record cases
  * `benchmark/chain_facts.json`— 8 REAL Polygon transactions
  * `data/real_txs.json`        — our 3 real Cake Wallet transfers
  * `data/token_registry.json`  — token decimals/symbols read from the contracts

ImportEvent grouping, stated explicitly because it is a construction:
  Each benchmark case carries its own import id, so nothing would share a root cause by default
  and the shared-root-cause query would have nothing to find. Rather than invent a tempting
  result, cases are grouped into import events along lines that correspond to a real operational
  failure, and the grouping is written here in the open:

    IMP-TOKEN-MAP-01  the wrong-asset cases  — one bad token-mapping import
    IMP-REIMPORT-02   the duplicate cases    — one re-run that double-loaded records
    IMP-VENDOR-03     the destination cases  — one vendor-master update
    IMP-SINGLE-<id>   everything else        — its own import, i.e. no shared cause

  The same grouping is used by the SQL comparison (`scripts/compare_graph_sql.py`), so neither
  side is advantaged. If the graph only "wins" because of how this grouping was drawn, the
  comparison says so.

    python scripts/load_graph.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from traceledger.config import ConfigError, load_config

BENCH = ROOT / "benchmark"

# Documented grouping. See the module docstring.
IMPORT_GROUPS = {
    "IMP-TOKEN-MAP-01": {
        "cases": ["C04", "C05", "C06", "C07", "C25"],
        "source_file": "token_mapping_2026-10-18.csv",
        "imported_at": "2026-10-18T06:40:00Z",
        "note": "Token-contract mapping re-imported after a vendor-master migration.",
    },
    "IMP-REIMPORT-02": {
        "cases": ["C16", "C17", "C18"],
        "source_file": "month_end_rerun_2026-10-23.csv",
        "imported_at": "2026-10-23T02:05:00Z",
        "note": "Month-end job re-run after a timeout; records loaded twice.",
    },
    "IMP-VENDOR-03": {
        "cases": ["C12", "C13", "C14"],
        "source_file": "vendor_master_update_2026-10-20.csv",
        "imported_at": "2026-10-20T11:12:00Z",
        "note": "Vendor-master update that changed remittance destinations.",
    },
}


def build_dataset() -> dict:
    cases = json.loads((BENCH / "cases.json").read_text())["cases"]
    facts = json.loads((BENCH / "chain_facts.json").read_text())["facts"]
    tokens = json.loads((ROOT / "data" / "token_registry.json").read_text())["tokens"]
    real = json.loads((ROOT / "data" / "real_txs.json").read_text())
    truth = {t["case_id"]: t for t in
             json.loads((BENCH / "ground_truth.json").read_text())["ground_truth"]}

    case_to_import: dict[str, str] = {}
    for import_id, group in IMPORT_GROUPS.items():
        for case_id in group["cases"]:
            case_to_import[case_id] = import_id

    facts_by_hash = {f["tx_hash"]: f for f in facts.values()}
    origin_by_hash = {t["tx_hash"]: t["origin"] for t in real["transfers"]}

    v: dict[str, list] = {k: [] for k in (
        "Invoice", "PaymentRequest", "LedgerEntry", "ApprovedAddress",
        "Transaction", "Wallet", "Token", "ImportEvent", "ImportBatch", "InvestigationCase")}
    e: dict[str, list] = {k: [] for k in (
        "INVOICE_HAS_REQUEST", "LEDGER_FOR_INVOICE", "REQUEST_EXPECTS", "APPROVES_WALLET",
        "INVOICE_IN_TOKEN", "TX_TRANSFERRED_TO", "TX_SENT_BY", "TX_MOVED_TOKEN", "TX_SETTLES",
        "INVOICE_FROM_IMPORT", "REQUEST_FROM_IMPORT", "LEDGER_FROM_IMPORT",
        "CASE_COVERS_INVOICE", "CASE_COVERS_TX")}

    for contract, meta in tokens.items():
        v["Token"].append({"contract": contract, "decimals": meta["decimals"],
                           "symbol_display": meta["symbol"] or "",
                           "name_display": meta["name"] or ""})

    for import_id, group in IMPORT_GROUPS.items():
        v["ImportEvent"].append({
            "import_event_id": import_id, "source_file": group["source_file"],
            "row_count": len(group["cases"]), "imported_at": group["imported_at"]})

    wallets: set[str] = set()
    seen_tx: set[str] = set()

    for case in cases:
        cid = case["case_id"]
        records = case["records"]
        import_id = case_to_import.get(cid, f"IMP-SINGLE-{cid}")
        if import_id.startswith("IMP-SINGLE-"):
            v["ImportEvent"].append({
                "import_event_id": import_id, "source_file": f"upload_{cid}.csv",
                "row_count": 1, "imported_at": "2026-10-29T00:00:00Z"})

        v["InvestigationCase"].append({"case_id": cid, "title": case["title"],
                          "state": "open", "opened_at": "2026-10-29T00:00:00Z"})

        # Verdict from the ground truth, which is what the deterministic layer would write.
        verdict = {"conflict": "CONFLICT", "no_conflict": "VERIFIED",
                   "unresolved": "UNRESOLVED"}[truth[cid]["expected_outcome"]]

        for inv in records["invoices"]:
            v["Invoice"].append({
                "record_id": inv["record_id"], "invoice_id": inv["invoice_id"],
                "counterparty": inv["counterparty"],
                "amount_base_units": inv["amount"], "token_contract": inv["token_contract"],
                "status": inv["status"], "simulated": True})
            e["INVOICE_IN_TOKEN"].append((inv["record_id"], inv["token_contract"], "known"))
            e["INVOICE_FROM_IMPORT"].append((inv["record_id"], import_id, "known"))
            e["CASE_COVERS_INVOICE"].append((cid, inv["record_id"], "known"))
            for ev in case["chain_evidence"]:
                e["TX_SETTLES"].append((ev["tx_hash"], inv["record_id"], "candidate", verdict))

        for pr in records["payment_requests"]:
            v["PaymentRequest"].append({
                "record_id": pr["record_id"], "request_id": pr["request_id"],
                "invoice_id": pr["invoice_id"], "amount_base_units": pr["amount"],
                "token_contract": pr["token_contract"], "simulated": True})
            e["REQUEST_FROM_IMPORT"].append((pr["record_id"], import_id, "known"))
            e["REQUEST_EXPECTS"].append((pr["record_id"], pr["expected_destination"], "known"))
            wallets.add(pr["expected_destination"])
            for inv in records["invoices"]:
                if inv["invoice_id"] == pr["invoice_id"]:
                    e["INVOICE_HAS_REQUEST"].append((inv["record_id"], pr["record_id"], "known"))

        for le in records["ledger_entries"]:
            v["LedgerEntry"].append({
                "record_id": le["record_id"], "entry_id": le["entry_id"],
                "invoice_id": le["invoice_id"], "amount_base_units": le["amount"],
                "direction": le["direction"], "status": le["status"],
                "posted_at": le.get("posted_at") or "", "simulated": True})
            e["LEDGER_FROM_IMPORT"].append((le["record_id"], import_id, "known"))
            for inv in records["invoices"]:
                if inv["invoice_id"] == le["invoice_id"]:
                    e["LEDGER_FOR_INVOICE"].append((le["record_id"], inv["record_id"], "known"))

        for ap in records["approved_addresses"]:
            v["ApprovedAddress"].append({
                "record_id": ap["record_id"], "address": ap["address"],
                "approved_for": ap["approved_for"],
                "approved_by": ap.get("approved_by") or "", "simulated": True})
            e["APPROVES_WALLET"].append((ap["record_id"], ap["address"], "known"))
            wallets.add(ap["address"])

        for ev in case["chain_evidence"]:
            h = ev["tx_hash"]
            e["CASE_COVERS_TX"].append((cid, h, "known"))
            if h in seen_tx:
                continue
            seen_tx.add(h)
            f = facts_by_hash[h]
            v["Transaction"].append({
                "tx_hash": h, "chain_id": f["chain_id"], "block_number": f["block_number"],
                "tx_status": f["status"], "confirmations": f["confirmations"],
                "origin": origin_by_hash.get(h, "public_mainnet"), "simulated": False})
            wallets.add(f["sender"])
            e["TX_SENT_BY"].append((h, f["sender"], "known"))
            for t in f["transfers"]:
                wallets.add(t["recipient"])
                e["TX_TRANSFERRED_TO"].append(
                    (h, t["recipient"], t["log_index"], t["token"], str(t["value"])))
                e["TX_MOVED_TOKEN"].append((h, t["token"], "known"))
                if t["token"] not in {tok["contract"] for tok in v["Token"]}:
                    v["Token"].append({"contract": t["token"], "decimals": -1,
                                       "symbol_display": "", "name_display": "(not verified)"})

    for address in sorted(wallets):
        v["Wallet"].append({"address": address, "owner_label": "", "first_seen_block": 0})

    # Our own Cake Wallet transfers, so the graph contains the demo's real evidence too.
    for t in real["transfers"]:
        if t["origin"] != "cake_wallet_demo" or t["tx_hash"] in seen_tx:
            continue
        seen_tx.add(t["tx_hash"])
        v["Transaction"].append({
            "tx_hash": t["tx_hash"], "chain_id": t["chain_id"],
            "block_number": t["block_number"], "tx_status": t["status"],
            "confirmations": t["confirmations_at_capture"], "origin": "cake_wallet_demo",
            "simulated": False})
        e["TX_TRANSFERRED_TO"].append(
            (t["tx_hash"], t["recipient"], t["log_index"], t["token_contract"],
             t["amount_base_units"]))
        e["TX_MOVED_TOKEN"].append((t["tx_hash"], t["token_contract"], "known"))
        e["TX_SENT_BY"].append((t["tx_hash"], t["sender"], "known"))
        for address in (t["sender"], t["recipient"]):
            if address not in wallets:
                wallets.add(address)
                v["Wallet"].append({"address": address, "owner_label": "", "first_seen_block": 0})

    return {"vertices": v, "edges": e, "import_groups": IMPORT_GROUPS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build and save the dataset without contacting TigerGraph")
    args = ap.parse_args()

    dataset = build_dataset()
    out = ROOT / "graph" / "export" / "dataset.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, indent=2) + "\n")

    print("dataset built:")
    for kind, rows in dataset["vertices"].items():
        print(f"  vertex {kind:16} {len(rows):5}")
    for kind, rows in dataset["edges"].items():
        print(f"  edge   {kind:22} {len(rows):5}")
    print(f"\nsaved {out.relative_to(ROOT)}")

    if args.dry_run:
        print("\n--dry-run: not contacting TigerGraph")
        return 0

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    if not cfg.tg_host or not (cfg.tg_secret or cfg.tg_password):
        print("SKIP: TigerGraph credentials not set. See docs/setup_sponsors.md step 1.",
              file=sys.stderr)
        return 2

    import pyTigerGraph as tg
    conn = tg.TigerGraphConnection(host=cfg.tg_host, graphname=cfg.tg_graph,
                                   gsqlSecret=cfg.tg_secret)
    conn.getToken(cfg.tg_secret)
    print(f"\nconnected to {cfg.tg_host} ({conn.getVer()})")

    total = 0
    for kind, rows in dataset["vertices"].items():
        if not rows:
            continue
        key = {"Invoice": "record_id", "PaymentRequest": "record_id",
               "LedgerEntry": "record_id", "ApprovedAddress": "record_id",
               "Transaction": "tx_hash", "Wallet": "address", "Token": "contract",
               "ImportEvent": "import_event_id", "ImportBatch": "batch_id", "InvestigationCase": "case_id"}[kind]
        payload = {row[key]: {k: v for k, v in row.items() if k != key} for row in rows}
        n = conn.upsertVertices(kind, [(vid, attrs) for vid, attrs in payload.items()])
        total += n
        print(f"  upserted {n:5} {kind}")
    print(f"\n{total} vertices upserted.")

    # Edge endpoints, so the loader does not have to guess them from the name.
    endpoints = {
        "INVOICE_HAS_REQUEST":  ("Invoice", "PaymentRequest",   ("basis",)),
        "LEDGER_FOR_INVOICE":   ("LedgerEntry", "Invoice",      ("basis",)),
        "REQUEST_EXPECTS":      ("PaymentRequest", "Wallet",    ("basis",)),
        "APPROVES_WALLET":      ("ApprovedAddress", "Wallet",   ("basis",)),
        "INVOICE_IN_TOKEN":     ("Invoice", "Token",            ("basis",)),
        "TX_SENT_BY":           ("Transaction", "Wallet",       ("basis",)),
        "TX_MOVED_TOKEN":       ("Transaction", "Token",        ("basis",)),
        "TX_SETTLES":           ("Transaction", "Invoice",      ("basis", "verdict")),
        "INVOICE_FROM_IMPORT":  ("Invoice", "ImportEvent",      ("basis",)),
        "REQUEST_FROM_IMPORT":  ("PaymentRequest", "ImportEvent", ("basis",)),
        "LEDGER_FROM_IMPORT":   ("LedgerEntry", "ImportEvent",  ("basis",)),
        "INVOICE_IN_BATCH":     ("Invoice", "ImportBatch",      ("basis",)),
        "CASE_COVERS_INVOICE":  ("InvestigationCase", "Invoice", ("basis",)),
        "CASE_COVERS_TX":       ("InvestigationCase", "Transaction", ("basis",)),
        # log_index is the DISCRIMINATOR, so it must be supplied as an attribute.
        "TX_TRANSFERRED_TO":    ("Transaction", "Wallet",
                                 ("log_index", "token_contract", "amount_base_units")),
    }

    edge_total = 0
    for kind, rows in dataset["edges"].items():
        if not rows:
            continue
        src_type, tgt_type, attr_names = endpoints[kind]
        payload = []
        for row in rows:
            src, tgt, *rest = row
            attrs = dict(zip(attr_names, rest))
            payload.append((src, tgt, attrs))
        n = conn.upsertEdges(src_type, kind, tgt_type, payload)
        edge_total += n
        print(f"  upserted {n:5} {kind}")
    print(f"\n{edge_total} edges upserted.")

    counts = conn.getVertexCount("*")
    print("\nvertex counts in the graph:")
    for kind, n in sorted(counts.items()):
        print(f"  {kind:20} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

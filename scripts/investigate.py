#!/usr/bin/env python3
"""Verify one payment against one invoice, deterministically. No LLM in this path.

    python scripts/investigate.py <tx_hash> --invoice-token <contract> --amount <decimal> \
        [--destination <address>] [--approved <address>]

Reads the transaction from the chain, reads the invoiced token's decimals from its contract, and
prints findings with the evidence each one cites. Exit code is 1 if any CONFLICT was found, so it
can be used in a pipeline.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceledger.chain.rpc import EvmRpc, RpcError
from traceledger.chain.tokens import read_token_metadata
from traceledger.chain.transfers import TransactionNotFound, fetch_transaction_facts
from traceledger.config import ConfigError, load_config
from traceledger.records import ApprovedAddress, Invoice, PaymentRequest, RecordError
from traceledger.verify import Status, verify_payment_case

GLYPH = {
    Status.VERIFIED: "VERIFIED ",
    Status.CONFLICT: "CONFLICT ",
    Status.MISSING: "MISSING  ",
    Status.NEXT_STEP: "NEXT STEP",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tx_hash")
    parser.add_argument("--invoice-token", required=True,
                        help="token contract the invoice names (never a symbol)")
    parser.add_argument("--amount", required=True, help="invoiced amount, decimal string")
    parser.add_argument("--destination", help="destination the payment request specified")
    parser.add_argument("--approved", action="append", default=[],
                        help="an approved destination address (repeatable)")
    parser.add_argument("--invoice-id", default="INV-DEMO")
    parser.add_argument("--min-confirmations", type=int, default=12)
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
    try:
        facts = fetch_transaction_facts(rpc, args.tx_hash)
        token_meta = read_token_metadata(rpc, args.invoice_token)
    except (TransactionNotFound, RpcError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    try:
        invoice = Invoice.from_dict({
            "record_id": "INV-R1", "invoice_id": args.invoice_id, "counterparty": "(demo)",
            "amount": args.amount, "token_contract": token_meta.address, "simulated": True,
        })
        payment_request = None
        if args.destination:
            payment_request = PaymentRequest.from_dict({
                "record_id": "PR-R1", "request_id": "PR-DEMO", "invoice_id": args.invoice_id,
                "expected_destination": args.destination, "amount": args.amount,
                "token_contract": token_meta.address, "simulated": True,
            })
        approved = [
            ApprovedAddress.from_dict({
                "record_id": f"APP-{i+1}", "address": a, "approved_for": "(demo)"})
            for i, a in enumerate(args.approved)
        ]
    except RecordError as exc:
        print(f"RECORD ERROR: {exc}", file=sys.stderr)
        return 2

    result = verify_payment_case(
        facts=facts, invoice=invoice, token_meta=token_meta,
        payment_request=payment_request, approved=approved,
        min_confirmations=args.min_confirmations,
    )

    print(f"transaction : {facts.tx_hash}")
    print(f"chain       : {facts.chain_id}  block {facts.block_number}  "
          f"{facts.confirmations} confirmations")
    print(f"invoiced    : {invoice.amount} of {token_meta.address} "
          f"(symbol {token_meta.symbol!r}, {token_meta.decimals} dp, read from contract)")
    print(f"transfers   : {len(facts.transfers)} in this transaction, "
          f"{len(facts.tokens_involved())} token(s)")
    print()
    for finding in result.findings:
        cites = f"  [{', '.join(finding.evidence_ids)}]" if finding.evidence_ids else ""
        print(f"  {GLYPH[finding.status]}  {finding.summary}{cites}")
    print()
    counts = {s.value: len(result.by_status(s)) for s in Status}
    print("summary     : " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"RPC calls   : {rpc.request_count}")
    print("\nDeterministic verification only. No LLM was involved in any line above.")
    return 1 if result.has_conflict else 0


if __name__ == "__main__":
    raise SystemExit(main())

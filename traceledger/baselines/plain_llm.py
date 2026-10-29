"""Plain-LLM baseline: the same evidence, handed straight to a language model.

This is what "just use an LLM for reconciliation" actually produces. It is given exactly the
same information TraceLedger gets -- the business records and the raw transaction data -- and
asked to reconcile. What it does **not** get is the part that makes TraceLedger work:

  * no deterministic findings computed before it is called,
  * no validator checking its output afterwards,
  * no requirement to cite a check that passed.

Built to be fair (as with the rules baseline, D26). It is given the raw transfer events with
exact integer base units, it is told the token decimals, it is allowed to answer "unresolved",
and it is asked for evidence ids -- so if it does well, that is a real result. A baseline rigged
to fail would make the comparison worthless.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..chain.transfers import TransactionFacts
from ..records import Invoice, LedgerEntry, PaymentRequest
from ..llm.provider import LLMError, LLMProvider

SYSTEM_INSTRUCTION = """\
You are a stablecoin payment reconciliation assistant. You are given business records and the raw
on-chain data for one or more transactions. Decide whether the payment reconciles with the records.

Answer honestly: if the evidence does not settle the question, say "unresolved" and state what is
missing. Do not guess.

Reply with JSON only:
{
  "outcome": "conflict" | "no_conflict" | "unresolved",
  "issues": ["short issue labels, e.g. wrong_asset, amount_mismatch, duplicate_records, \
status_conflict, destination_conflict, zero_value, direction_reversed, missing_evidence"],
  "reasons": ["one sentence each, explaining your finding"],
  "evidence_ids": ["the record ids or tx hashes your answer rests on"]
}"""


@dataclass
class PlainLLMVerdict:
    outcome: str
    issues: tuple[str, ...]
    reasons: tuple[str, ...]
    cited: tuple[str, ...] = ()
    latency_ms: float = 0.0
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "issues": list(self.issues),
                "reasons": list(self.reasons), "cited": list(self.cited),
                "latency_ms": round(self.latency_ms, 1), "error": self.error}


def build_prompt(
    facts_list: Sequence[TransactionFacts],
    invoice: Invoice,
    payment_request: PaymentRequest | None = None,
    ledger_entries: Sequence[LedgerEntry] = (),
    invoices: Sequence[Invoice] = (),
    payment_requests: Sequence[PaymentRequest] = (),
    token_decimals: dict[str, int] | None = None,
) -> str:
    """The same evidence TraceLedger sees, with no findings and no fencing."""
    payload: dict[str, Any] = {
        "invoices": [
            {"record_id": i.record_id, "invoice_id": i.invoice_id,
             "counterparty": i.counterparty, "amount": i.amount,
             "token_contract": i.token_contract, "status": i.status, "memo": i.memo}
            for i in (invoices or [invoice])
        ],
        "payment_requests": [
            {"record_id": p.record_id, "request_id": p.request_id,
             "invoice_id": p.invoice_id, "expected_destination": p.expected_destination,
             "amount": p.amount, "token_contract": p.token_contract, "memo": p.memo}
            for p in (payment_requests or ([payment_request] if payment_request else []))
        ],
        "ledger_entries": [
            {"record_id": e.record_id, "entry_id": e.entry_id, "invoice_id": e.invoice_id,
             "amount": e.amount, "direction": e.direction, "status": e.status}
            for e in ledger_entries
        ],
        "transactions": [
            {"tx_hash": f.tx_hash, "chain_id": f.chain_id, "block_number": f.block_number,
             "status": f.status, "status_meaning": "1 = succeeded, 0 = reverted",
             "confirmations": f.confirmations, "sender": f.sender,
             "transfers": [
                 {"token_contract": t.token, "from": t.sender, "to": t.recipient,
                  "amount_base_units": str(t.value), "log_index": t.log_index}
                 for t in f.transfers]}
            for f in facts_list
        ],
        "token_decimals": token_decimals or {},
        "note": ("amount fields in records are decimal strings; amount_base_units on transfers "
                 "are integers in the token's smallest unit"),
    }
    return ("Reconcile this payment exception.\n\n"
            + json.dumps(payload, indent=2)
            + "\n\nReply with JSON only.")


def run_plain_llm(
    provider: LLMProvider,
    facts_list: Sequence[TransactionFacts],
    invoice: Invoice,
    *,
    payment_request: PaymentRequest | None = None,
    ledger_entries: Sequence[LedgerEntry] = (),
    invoices: Sequence[Invoice] = (),
    payment_requests: Sequence[PaymentRequest] = (),
    token_decimals: dict[str, int] | None = None,
) -> PlainLLMVerdict:
    """Ask the model directly. No findings beforehand, no validation afterwards."""
    prompt = build_prompt(facts_list, invoice, payment_request, ledger_entries,
                          invoices, payment_requests, token_decimals)
    try:
        response = provider.complete(prompt, system=SYSTEM_INSTRUCTION)
    except LLMError as exc:
        # outcome="error", never "unresolved". Recording an API failure as an abstention is how
        # the first CP8 run produced a meaningless score: 17 of 25 quota failures were counted as
        # correct abstentions (RISKS.md S22).
        return PlainLLMVerdict(outcome="error", issues=(), reasons=(str(exc),),
                               error=str(exc))
    try:
        payload = response.parse_json()
    except LLMError as exc:
        # Unparseable output IS a model failure at the task, so it is a real verdict of
        # "unresolved" -- unlike an API error, which is our infrastructure failing.
        return PlainLLMVerdict(outcome="unresolved", issues=(), reasons=(str(exc),),
                               latency_ms=response.latency_ms, error=str(exc))
    if not isinstance(payload, dict):
        return PlainLLMVerdict(outcome="unresolved", issues=(), reasons=("non-object JSON",),
                               latency_ms=response.latency_ms, error="non-object JSON")

    outcome = str(payload.get("outcome", "")).strip().lower()
    if outcome not in ("conflict", "no_conflict", "unresolved"):
        outcome = "unresolved"
    issues = payload.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    reasons = payload.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    cited = payload.get("evidence_ids") or []
    if isinstance(cited, str):
        cited = [cited]
    return PlainLLMVerdict(
        outcome=outcome,
        issues=tuple(str(i).strip().lower() for i in issues),
        reasons=tuple(str(r) for r in reasons),
        cited=tuple(str(c) for c in cited),
        latency_ms=response.latency_ms,
        raw=payload,
    )

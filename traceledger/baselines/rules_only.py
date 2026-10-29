"""Rules-only baseline: a conventional reconciler, implemented fairly.

This is **our** implementation of the conventional approach, not any vendor's product. Results
say something about the approach, not about a competitor (RISKS.md P2).

It would be easy to write a baseline that loses on purpose. Every number in
BENCHMARK_RESULTS.md would then be meaningless. So each design choice below is one a real
accounting or reconciliation system plausibly makes, and the baseline is given full credit where
the approach genuinely works:

| Choice | Why a real system does this | Consequence |
|---|---|---|
| Match assets by **ticker symbol** | Symbols are what ledgers, invoices and ERP systems store | Cannot distinguish two contracts sharing a symbol |
| Compare amounts at **2 decimal places**, as floats | Accounting systems work in display currency precision | Sub-cent differences vanish |
| Find payments by scanning **Transfer events** | The standard way to index token movements | Reverted transactions are invisible: they emit no events |
| Flag duplicates on **exact identifier match** | Straightforward and correct | Works well; the baseline should win here |
| **Always answer** | Operators want a status, not a shrug | Cannot abstain when evidence is insufficient |

Deliberately *not* sabotaged: it checks destinations properly, it handles duplicates correctly, it
compares amounts in the right direction, and it is given the same evidence as every other system.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ..chain.transfers import TransactionFacts
from ..records import Invoice, LedgerEntry, PaymentRequest, find_duplicate_ids

# Display precision a conventional ledger works in.
DISPLAY_DECIMALS = 2


@dataclass(frozen=True)
class RulesVerdict:
    """What a conventional reconciler reports. Note there is no 'unresolved'."""

    outcome: str                  # "conflict" | "no_conflict"
    issues: tuple[str, ...]       # issue types in the benchmark's vocabulary
    reasons: tuple[str, ...]      # human-readable
    cited: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "issues": list(self.issues),
                "reasons": list(self.reasons), "cited": list(self.cited)}


def _round_display(base_units: int, decimals: int) -> float:
    """Convert to display precision the way a ledger would: via float, rounded to cents."""
    return round(base_units / (10 ** decimals), DISPLAY_DECIMALS)


def run_rules_only(
    facts_list: Sequence[TransactionFacts],
    invoice: Invoice,
    symbols: dict[str, str],
    *,
    token_decimals: dict[str, int],
    payment_request: PaymentRequest | None = None,
    ledger_entries: Sequence[LedgerEntry] = (),
    invoices: Sequence[Invoice] = (),
    payment_requests: Sequence[PaymentRequest] = (),
) -> RulesVerdict:
    """Reconcile an invoice against transactions using symbol matching and display precision."""
    issues: list[str] = []
    reasons: list[str] = []
    cited: list[str] = [invoice.record_id]

    invoiced_symbol = (symbols.get(invoice.token_contract) or "").upper()
    decimals = token_decimals.get(invoice.token_contract, 6)

    # Duplicate detection: exact identifier match. The baseline does this well.
    for label, records, attr, issue in (
        ("invoice", list(invoices), "invoice_id", "duplicate_records"),
        ("payment request", list(payment_requests), "request_id", "duplicate_records"),
        ("ledger entry", list(ledger_entries), "entry_id", "duplicate_records"),
    ):
        for business_id, record_ids in find_duplicate_ids(records, attr).items():
            issues.append(issue)
            reasons.append(f"{len(record_ids)} {label} records share identifier {business_id!r}")
            cited.extend(record_ids)

    # Find candidate payments by scanning Transfer events for a matching SYMBOL.
    # A reverted transaction emits none, so it simply does not appear here.
    matched = []
    for facts in facts_list:
        for transfer in facts.transfers:
            if (symbols.get(transfer.token) or "").upper() == invoiced_symbol:
                matched.append((facts, transfer))

    if not matched:
        issues.append("unmatched_payment")
        reasons.append(f"No {invoiced_symbol or 'matching'} transfer found for this invoice")
        return RulesVerdict("conflict", tuple(dict.fromkeys(issues)),
                            tuple(reasons), tuple(dict.fromkeys(cited)))

    # Destination check, if an instruction exists.
    if payment_request is not None:
        expected = payment_request.expected_destination
        cited.append(payment_request.record_id)
        to_expected = [(f, t) for f, t in matched if t.recipient == expected]
        if not to_expected:
            issues.append("destination_conflict")
            recipients = sorted({t.recipient for _, t in matched})
            reasons.append(f"Expected destination {expected} received nothing; "
                           f"funds went to {', '.join(recipients)}")
        else:
            matched = to_expected

    # Amount check at display precision.
    expected_display = round(float(invoice.amount), DISPLAY_DECIMALS)
    delivered = sum(t.value for _, t in matched)
    delivered_display = _round_display(delivered, decimals)
    if delivered_display != expected_display:
        issues.append("amount_mismatch")
        reasons.append(f"Expected {expected_display:.2f}, found {delivered_display:.2f}")

    # Ledger arithmetic, also at display precision.
    relevant = [e for e in ledger_entries if e.invoice_id == invoice.invoice_id]
    if relevant:
        posted = 0.0
        for entry in relevant:
            value = round(float(entry.amount), DISPLAY_DECIMALS)
            posted += value if entry.direction == "credit" else -value
            cited.append(entry.record_id)
        if round(posted, DISPLAY_DECIMALS) != expected_display:
            if "amount_mismatch" not in issues:
                issues.append("amount_mismatch")
            reasons.append(f"Ledger entries sum to {posted:.2f}, invoice is {expected_display:.2f}")

    for facts, _ in matched:
        cited.append(facts.tx_hash)

    outcome = "conflict" if issues else "no_conflict"
    if not issues:
        reasons.append(f"Matched {delivered_display:.2f} {invoiced_symbol} to the invoice")
    return RulesVerdict(outcome, tuple(dict.fromkeys(issues)),
                        tuple(reasons), tuple(dict.fromkeys(cited)))

"""Deterministic verification. No LLM, no guessing, no floats.

Every finding this module emits is one of VERIFIED, CONFLICT, MISSING or NEXT_STEP, and the first
two always cite the evidence they rest on (G4). HYPOTHESIS findings are not produced here -- this
layer deals only in what can be established from the chain and the records in front of it. When
the evidence does not settle a question, the answer is MISSING plus what would settle it (G5), not
a best guess.

The LLM layer may read these findings. It may never contradict or recompute them (G8).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from .chain.tokens import TokenMetadata
from .chain.transfers import TransactionFacts, TransferEvent
from .records import ApprovedAddress, Invoice, LedgerEntry, PaymentRequest, find_duplicate_ids

# A payment is only treated as confirmed on-chain at or above this depth. Below it, the finding
# is MISSING ("not yet at the confirmation threshold"), never VERIFIED. "Confirmed on-chain" is
# still not "final" or "guaranteed" -- issuers can freeze balances (RISKS.md P10).
DEFAULT_MIN_CONFIRMATIONS = 12


class Status(str, Enum):
    VERIFIED = "VERIFIED"
    CONFLICT = "CONFLICT"
    MISSING = "MISSING"
    NEXT_STEP = "NEXT_STEP"


@dataclass(frozen=True)
class Finding:
    """One deterministic statement, with the evidence it rests on."""

    code: str                       # stable machine-readable identifier
    status: Status
    summary: str                    # one line, plain language, no verdict words (G6)
    evidence_ids: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # G4: a VERIFIED or CONFLICT line without evidence is not allowed to exist.
        if self.status in (Status.VERIFIED, Status.CONFLICT) and not self.evidence_ids:
            raise ValueError(
                f"{self.status.value} finding {self.code!r} cites no evidence. Every VERIFIED and "
                "CONFLICT finding must cite evidence IDs (G4)."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "status": self.status.value, "summary": self.summary,
            "evidence_ids": list(self.evidence_ids), "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationResult:
    findings: tuple[Finding, ...]

    def by_status(self, status: Status) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.status is status)

    @property
    def conflicts(self) -> tuple[Finding, ...]:
        return self.by_status(Status.CONFLICT)

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(f.code for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {"findings": [f.as_dict() for f in self.findings]}


# --------------------------------------------------------------------------- individual checks

def check_transaction_succeeded(facts: TransactionFacts) -> Finding:
    """A reverted transaction moved nothing, whatever the records say."""
    evidence = (facts.tx_hash,)
    if facts.succeeded:
        return Finding(
            code="tx.status", status=Status.VERIFIED,
            summary=f"Transaction succeeded on chain {facts.chain_id} in block {facts.block_number}.",
            evidence_ids=evidence,
            detail={"status": facts.status, "block_number": facts.block_number},
        )
    return Finding(
        code="tx.status", status=Status.CONFLICT,
        summary=(f"Transaction reverted (status 0) in block {facts.block_number}; "
                 "no tokens were transferred by it."),
        evidence_ids=evidence,
        detail={"status": facts.status, "block_number": facts.block_number},
    )


def check_confirmations(facts: TransactionFacts,
                        minimum: int = DEFAULT_MIN_CONFIRMATIONS) -> Finding:
    """Is the transaction deep enough to be relied on?

    The wording states *what* is confirmed. A reverted transaction at 52 confirmations is a
    confirmed **failure**, and reading "Confirmed on-chain" beside a failed payment would
    mislead a reviewer -- so the outcome is named explicitly.
    """
    if facts.confirmations >= minimum:
        outcome = ("The transfer is confirmed on-chain" if facts.succeeded
                   else "The FAILURE of this transaction is confirmed on-chain")
        return Finding(
            code="tx.confirmations", status=Status.VERIFIED,
            summary=(f"{outcome} at {facts.confirmations} confirmations "
                     f"(threshold {minimum}). Confirmed is not the same as final: issuers can "
                     "freeze or blacklist balances."),
            evidence_ids=(facts.tx_hash,),
            detail={"confirmations": facts.confirmations, "minimum": minimum,
                    "confirms_outcome": "success" if facts.succeeded else "failure"},
        )
    return Finding(
        code="tx.confirmations", status=Status.MISSING,
        summary=(f"Only {facts.confirmations} confirmations, below the threshold of {minimum}. "
                 "Not yet treated as confirmed on-chain."),
        detail={"confirmations": facts.confirmations, "minimum": minimum},
    )


def select_settling_transfers(
    facts: TransactionFacts, token_contract: str, recipient: str,
) -> tuple[TransferEvent, ...]:
    """Transfers in this transaction that could settle a payment of `token` to `recipient`.

    Selection is by contract address and recipient together. Neither alone is sufficient: a real
    transaction may carry several transfers of the same token, or transfers of two different
    tokens (DECISIONS.md D18).
    """
    return facts.transfers_to(recipient, token=token_contract)


def check_asset(facts: TransactionFacts, expected_token: str,
                expected_token_meta: TokenMetadata | None,
                evidence_ids: Sequence[str]) -> Finding:
    """Did the chain deliver the asset the records named?

    Compares contract addresses only. The symbol is reported for human readability and plays no
    part in the decision -- on Polygon the canonical Tether contract reports symbol "USDT0" and
    two distinct live contracts both report "USDC" (G7, D6).
    """
    expected = expected_token.strip().lower()
    delivered = facts.tokens_involved()
    cited = (facts.tx_hash, *evidence_ids)

    symbol_note = ""
    if expected_token_meta is not None and expected_token_meta.symbol:
        symbol_note = f" (reports symbol {expected_token_meta.symbol!r})"

    if expected in delivered:
        return Finding(
            code="payment.asset", status=Status.VERIFIED,
            summary=f"Transaction transferred the invoiced token contract {expected}{symbol_note}.",
            evidence_ids=cited,
            detail={"expected_token": expected, "tokens_in_transaction": list(delivered)},
        )
    if not delivered:
        return Finding(
            code="payment.asset", status=Status.MISSING,
            summary="Transaction contains no ERC-20 transfers, so no asset can be matched.",
            detail={"expected_token": expected, "tokens_in_transaction": []},
        )
    return Finding(
        code="payment.asset", status=Status.CONFLICT,
        summary=(f"Wrong asset: records name token contract {expected}{symbol_note}, but the "
                 f"transaction transferred {', '.join(delivered)}."),
        evidence_ids=cited,
        detail={"expected_token": expected, "tokens_in_transaction": list(delivered)},
    )


def check_destination(facts: TransactionFacts, token_contract: str, expected_destination: str,
                      evidence_ids: Sequence[str]) -> Finding:
    """Did the token reach the destination the records specified?"""
    expected = expected_destination.strip().lower()
    token = token_contract.strip().lower()
    cited = (facts.tx_hash, *evidence_ids)
    matching = facts.transfers_to(expected, token=token)

    if matching:
        return Finding(
            code="payment.destination", status=Status.VERIFIED,
            summary=f"Token {token} reached the expected destination {expected}.",
            evidence_ids=cited,
            detail={"expected_destination": expected,
                    "log_indexes": [t.log_index for t in matching]},
        )

    actual = [t.recipient for t in facts.transfers_of(token)]
    if not actual:
        return Finding(
            code="payment.destination", status=Status.MISSING,
            summary=(f"No transfer of token {token} appears in this transaction, so the "
                     "destination cannot be checked."),
            detail={"expected_destination": expected, "recipients_for_token": []},
        )
    return Finding(
        code="payment.destination", status=Status.CONFLICT,
        summary=(f"Destination mismatch: records expected {expected}, but token {token} was "
                 f"delivered to {', '.join(dict.fromkeys(actual))}."),
        evidence_ids=cited,
        detail={"expected_destination": expected,
                "recipients_for_token": list(dict.fromkeys(actual))},
    )


def check_amount(facts: TransactionFacts, token_meta: TokenMetadata, expected_amount: str,
                 recipient: str, evidence_ids: Sequence[str]) -> Finding:
    """Compare amounts as integers in base units, using decimals read from the contract.

    All arithmetic here is integer (G8). The expected decimal string is converted using the
    token's on-chain `decimals()`; a value carrying more precision than the token supports is a
    data error, reported as such rather than rounded.
    """
    cited = (facts.tx_hash, *evidence_ids)
    try:
        expected_base = token_meta.base_units(expected_amount)
    except ValueError as exc:
        return Finding(
            code="payment.amount", status=Status.CONFLICT,
            summary=(f"Recorded amount {expected_amount} cannot be expressed in "
                     f"{token_meta.decimals} decimals for token {token_meta.address}: {exc}"),
            evidence_ids=cited,
            detail={"expected_amount": expected_amount, "decimals": token_meta.decimals},
        )

    candidates = select_settling_transfers(facts, token_meta.address, recipient)
    if not candidates:
        return Finding(
            code="payment.amount", status=Status.MISSING,
            summary=(f"No transfer of token {token_meta.address} to {recipient.lower()} in this "
                     "transaction, so the amount cannot be compared."),
            detail={"expected_base_units": str(expected_base)},
        )

    exact = [t for t in candidates if t.value == expected_base]
    if exact:
        return Finding(
            code="payment.amount", status=Status.VERIFIED,
            summary=(f"Amount matches exactly: {token_meta.format_units(expected_base)} "
                     f"({expected_base} base units)."),
            evidence_ids=cited,
            detail={"expected_base_units": str(expected_base),
                    "matched_log_indexes": [t.log_index for t in exact],
                    "decimals_source": "contract"},
        )

    # A single candidate with a different value is a clean discrepancy; several candidates that
    # all differ is reported with every value, so a reviewer can see the shape of the problem.
    delivered = [t.value for t in candidates]
    total = sum(delivered)
    shortfall = expected_base - total
    return Finding(
        code="payment.amount", status=Status.CONFLICT,
        summary=(f"Amount mismatch: records expect {token_meta.format_units(expected_base)}, "
                 f"chain delivered {', '.join(token_meta.format_units(v) for v in delivered)}"
                 + (f" (total {token_meta.format_units(total)})" if len(delivered) > 1 else "")
                 + "."),
        evidence_ids=cited,
        detail={
            "expected_base_units": str(expected_base),
            "delivered_base_units": [str(v) for v in delivered],
            "total_delivered_base_units": str(total),
            "difference_base_units": str(shortfall),
            "log_indexes": [t.log_index for t in candidates],
        },
    )


def check_transfer_ambiguity(facts: TransactionFacts, token_contract: str,
                             recipient: str) -> Finding | None:
    """Flag when several transfers could settle the same payment.

    Returns None when there is no ambiguity. Picking the first match would produce a confident
    answer that happens to be arbitrary, so the ambiguity is surfaced instead (G5, D18).
    """
    candidates = select_settling_transfers(facts, token_contract, recipient)
    if len(candidates) <= 1:
        return None
    return Finding(
        code="payment.ambiguous_transfer", status=Status.MISSING,
        summary=(f"{len(candidates)} separate transfers of token {token_contract.lower()} reach "
                 f"{recipient.lower()} in this transaction; which one settles the payment cannot "
                 "be determined from the chain alone."),
        detail={"log_indexes": [t.log_index for t in candidates],
                "values_base_units": [str(t.value) for t in candidates]},
    )


def check_payment_direction(facts: TransactionFacts, token_contract: str,
                            expected_recipient: str,
                            evidence_ids: Sequence[str]) -> Finding | None:
    """Catch a payment that went the wrong way.

    If the party expected to *receive* funds appears only as a sender of that token, the money
    left them rather than arriving. Returns None when there is nothing to say, so this check
    adds no noise to ordinary cases.
    """
    token = token_contract.strip().lower()
    party = expected_recipient.strip().lower()
    received = facts.transfers_to(party, token=token)
    sent = tuple(t for t in facts.transfers_of(token) if t.sender == party)

    if received or not sent:
        return None
    total_sent = sum(t.value for t in sent)
    return Finding(
        code="payment.direction", status=Status.CONFLICT,
        summary=(f"Direction reversed: {party} was expected to receive token {token}, but in this "
                 f"transaction it sent {total_sent} base units and received none."),
        evidence_ids=(facts.tx_hash, *evidence_ids),
        detail={"party": party, "sent_base_units": str(total_sent),
                "received_base_units": "0",
                "log_indexes": [t.log_index for t in sent]},
    )


def check_zero_value_transfer(facts: TransactionFacts, token_contract: str,
                              recipient: str, evidence_ids: Sequence[str]) -> Finding | None:
    """A transfer that succeeded but moved nothing.

    A zero-value Transfer is a real event and a real failure mode: the transaction succeeds, a
    naive checker sees "a transfer to the right address for the right token", and no value
    actually moved. Returns None unless every matching transfer is zero.
    """
    candidates = select_settling_transfers(facts, token_contract, recipient)
    if not candidates or any(t.value > 0 for t in candidates):
        return None
    return Finding(
        code="payment.zero_value", status=Status.CONFLICT,
        summary=(f"Transfer of token {token_contract.lower()} to {recipient.lower()} succeeded but "
                 "moved zero base units; no value was received."),
        evidence_ids=(facts.tx_hash, *evidence_ids),
        detail={"log_indexes": [t.log_index for t in candidates]},
    )


def check_destination_approved(
    destination: str, approved: Sequence[ApprovedAddress],
) -> Finding:
    """Is the destination on the allow-list?

    Wording is deliberately neutral: an unapproved destination is a risk indicator, not a
    verdict about anyone's intent (G6).
    """
    target = destination.strip().lower()
    if not approved:
        return Finding(
            code="destination.approval", status=Status.MISSING,
            summary=f"No approved-address list was supplied, so {target} cannot be checked.",
            detail={"destination": target},
        )
    match = next((a for a in approved if a.address == target), None)
    if match is not None:
        return Finding(
            code="destination.approval", status=Status.VERIFIED,
            summary=f"Destination {target} is on the approved-address list.",
            evidence_ids=(match.record_id,),
            detail={"destination": target, "approved_for": match.approved_for},
        )
    return Finding(
        code="destination.approval", status=Status.CONFLICT,
        summary=(f"Destination {target} is not on the approved-address list "
                 f"({len(approved)} entries checked). Risk indicator, not a verdict about intent."),
        evidence_ids=tuple(a.record_id for a in approved),
        detail={"destination": target, "approved_count": len(approved)},
    )


def check_duplicates(invoices: Sequence[Invoice] = (),
                     requests: Sequence[PaymentRequest] = (),
                     entries: Sequence[LedgerEntry] = ()) -> tuple[Finding, ...]:
    """Report business identifiers that appear on more than one record."""
    findings: list[Finding] = []
    for label, records, attr in (
        ("invoice", list(invoices), "invoice_id"),
        ("payment request", list(requests), "request_id"),
        ("ledger entry", list(entries), "entry_id"),
    ):
        if not records:
            continue
        for business_id, record_ids in sorted(find_duplicate_ids(records, attr).items()):
            findings.append(Finding(
                code=f"duplicate.{attr}", status=Status.CONFLICT,
                summary=(f"{len(record_ids)} {label} records share the identifier "
                         f"{business_id!r}."),
                evidence_ids=tuple(record_ids),
                detail={"identifier": business_id, "record_ids": list(record_ids)},
            ))
    return tuple(findings)


def check_ledger_arithmetic(invoice: Invoice, entries: Sequence[LedgerEntry],
                            token_meta: TokenMetadata) -> Finding:
    """Do the ledger entries for this invoice add up to the invoiced amount?

    Integer base units throughout; credits add, debits subtract.
    """
    relevant = [e for e in entries if e.invoice_id == invoice.invoice_id]
    if not relevant:
        return Finding(
            code="ledger.arithmetic", status=Status.MISSING,
            summary=f"No ledger entries reference invoice {invoice.invoice_id}.",
            detail={"invoice_id": invoice.invoice_id},
        )
    try:
        expected = token_meta.base_units(invoice.amount)
        posted = 0
        for entry in relevant:
            value = token_meta.base_units(entry.amount)
            posted += value if entry.direction == "credit" else -value
    except ValueError as exc:
        return Finding(
            code="ledger.arithmetic", status=Status.CONFLICT,
            summary=f"A recorded amount exceeds the token's {token_meta.decimals} decimals: {exc}",
            evidence_ids=(invoice.record_id, *(e.record_id for e in relevant)),
            detail={"invoice_id": invoice.invoice_id},
        )

    cited = (invoice.record_id, *(e.record_id for e in relevant))
    if posted == expected:
        return Finding(
            code="ledger.arithmetic", status=Status.VERIFIED,
            summary=(f"Ledger entries for {invoice.invoice_id} sum to the invoiced "
                     f"{token_meta.format_units(expected)}."),
            evidence_ids=cited,
            detail={"expected_base_units": str(expected), "posted_base_units": str(posted),
                    "entry_count": len(relevant)},
        )
    return Finding(
        code="ledger.arithmetic", status=Status.CONFLICT,
        summary=(f"Ledger entries for {invoice.invoice_id} sum to "
                 f"{token_meta.format_units(posted)}, but the invoice is for "
                 f"{token_meta.format_units(expected)}."),
        evidence_ids=cited,
        detail={"expected_base_units": str(expected), "posted_base_units": str(posted),
                "difference_base_units": str(expected - posted), "entry_count": len(relevant)},
    )


# --------------------------------------------------------------------------- orchestration

def verify_payment_case(
    facts: TransactionFacts,
    invoice: Invoice,
    token_meta: TokenMetadata,
    payment_request: PaymentRequest | None = None,
    approved: Sequence[ApprovedAddress] = (),
    ledger_entries: Sequence[LedgerEntry] = (),
    invoices: Sequence[Invoice] = (),
    payment_requests: Sequence[PaymentRequest] = (),
    min_confirmations: int = DEFAULT_MIN_CONFIRMATIONS,
) -> VerificationResult:
    """Run every deterministic check that the supplied evidence allows.

    Checks are skipped only when their inputs are absent, and a skipped check becomes a MISSING
    finding rather than silence -- an absent check must never read as a pass.

    `token_meta` must describe `invoice.token_contract`: decimals come from the contract, never
    from a constant (G7). Passing metadata for a different token is a programming error and
    raises, because comparing amounts across decimals would produce confident nonsense.
    """
    if token_meta.address != invoice.token_contract:
        raise ValueError(
            f"token metadata is for {token_meta.address} but the invoice names "
            f"{invoice.token_contract}. Amounts must be scaled by the invoiced token's own "
            "decimals (G7)."
        )

    findings: list[Finding] = [
        check_transaction_succeeded(facts),
        check_confirmations(facts, minimum=min_confirmations),
    ]

    invoice_evidence: tuple[str, ...] = (invoice.record_id,)
    request_evidence = (payment_request.record_id,) if payment_request else ()

    findings.append(check_asset(
        facts, invoice.token_contract, token_meta,
        evidence_ids=invoice_evidence + request_evidence,
    ))

    # The destination and amount can only be checked against a stated destination.
    if payment_request is not None:
        destination = payment_request.expected_destination
        findings.append(check_destination(
            facts, invoice.token_contract, destination,
            evidence_ids=invoice_evidence + request_evidence,
        ))
        direction = check_payment_direction(
            facts, invoice.token_contract, destination,
            evidence_ids=invoice_evidence + request_evidence)
        if direction is not None:
            findings.append(direction)
        zero = check_zero_value_transfer(
            facts, invoice.token_contract, destination,
            evidence_ids=invoice_evidence + request_evidence)
        if zero is not None:
            findings.append(zero)
        ambiguity = check_transfer_ambiguity(facts, invoice.token_contract, destination)
        if ambiguity is not None:
            findings.append(ambiguity)
        findings.append(check_amount(
            facts, token_meta, invoice.amount, destination,
            evidence_ids=invoice_evidence + request_evidence,
        ))
        findings.append(check_destination_approved(destination, approved))
        if payment_request.token_contract != invoice.token_contract:
            findings.append(Finding(
                code="records.token_disagreement", status=Status.CONFLICT,
                summary=(f"Invoice names token {invoice.token_contract} but payment request "
                         f"{payment_request.request_id} names {payment_request.token_contract}; "
                         "the records disagree with each other."),
                evidence_ids=invoice_evidence + request_evidence,
                detail={"invoice_token": invoice.token_contract,
                        "request_token": payment_request.token_contract},
            ))
    else:
        findings.append(Finding(
            code="payment.destination", status=Status.MISSING,
            summary=("No payment request supplied, so the expected destination and amount cannot "
                     "be checked."),
            detail={"needed": ["payment_request.expected_destination",
                               "payment_request.amount"]},
        ))

    if ledger_entries:
        findings.append(check_ledger_arithmetic(invoice, ledger_entries, token_meta))

    findings.extend(check_duplicates(
        invoices=invoices or (), requests=payment_requests or (), entries=ledger_entries or ()))

    # Every MISSING finding implies something a human could go and get.
    for missing in [f for f in findings if f.status is Status.MISSING]:
        needed = missing.detail.get("needed")
        if needed:
            findings.append(Finding(
                code=f"next_step.{missing.code}", status=Status.NEXT_STEP,
                summary=f"Obtain: {', '.join(needed)}.",
                detail={"for_finding": missing.code, "needed": needed},
            ))

    return VerificationResult(findings=tuple(findings))

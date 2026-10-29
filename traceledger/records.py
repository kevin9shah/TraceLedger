"""Business records: invoices, payment requests, ledger entries, approved addresses.

These are **untrusted input** (G9). They arrive from uploaded CSV/JSON, they are the side of the
comparison that is routinely wrong, and nothing in them is ever treated as an instruction. Text
fields may contain anything at all -- including attempts to instruct an LLM -- and are carried as
opaque data.

Every record exposes `record_id`, which is the evidence ID that report lines cite (G4), and
`simulated`, which is True for anything invented rather than sourced from a real system (G3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


class RecordError(ValueError):
    """A record is malformed. Raised rather than guessing at the author's intent."""


def _require(data: dict[str, Any], key: str, kind: str) -> Any:
    if key not in data or data[key] in (None, ""):
        raise RecordError(f"{kind} is missing required field {key!r}")
    return data[key]


def _address(raw: Any, kind: str, key: str) -> str:
    """Normalise an EVM address. Identity is the address, never a label (G7)."""
    if not isinstance(raw, str):
        raise RecordError(f"{kind}.{key} must be a string address, got {type(raw).__name__}")
    addr = raw.strip().lower()
    if not (addr.startswith("0x") and len(addr) == 42):
        raise RecordError(f"{kind}.{key} is not a 20-byte hex address: {raw!r}")
    try:
        int(addr, 16)
    except ValueError as exc:
        raise RecordError(f"{kind}.{key} is not hexadecimal: {raw!r}") from exc
    return addr


def _decimal_string(raw: Any, kind: str, key: str) -> str:
    """Keep amounts as exact decimal strings. Never float (G8).

    Conversion to integer base units happens later, using the token's on-chain decimals, so
    that a value carrying more precision than the token allows is an error rather than a
    silent rounding.
    """
    if isinstance(raw, float):
        raise RecordError(
            f"{kind}.{key} is a float ({raw!r}). Amounts must be strings or integers so no "
            "binary floating-point drift can enter the comparison (G8)."
        )
    text = str(raw).strip()
    if not text:
        raise RecordError(f"{kind}.{key} is empty")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise RecordError(f"{kind}.{key} is not a decimal number: {raw!r}") from exc
    if value < 0:
        raise RecordError(f"{kind}.{key} is negative: {raw!r}")
    return format(value, "f")


@dataclass(frozen=True)
class Invoice:
    """What was owed."""

    record_id: str
    invoice_id: str
    counterparty: str
    amount: str                 # exact decimal string
    token_contract: str         # the invoiced asset, by contract address (G7)
    status: str = "open"
    due_date: str | None = None
    memo: str = ""              # untrusted free text (G9)
    simulated: bool = True
    source_file: str | None = None
    import_event_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Invoice":
        return cls(
            record_id=str(_require(data, "record_id", "Invoice")),
            invoice_id=str(_require(data, "invoice_id", "Invoice")),
            counterparty=str(data.get("counterparty", "")),
            amount=_decimal_string(_require(data, "amount", "Invoice"), "Invoice", "amount"),
            token_contract=_address(
                _require(data, "token_contract", "Invoice"), "Invoice", "token_contract"),
            status=str(data.get("status", "open")),
            due_date=data.get("due_date"),
            memo=str(data.get("memo", "")),
            simulated=bool(data.get("simulated", True)),
            source_file=data.get("source_file"),
            import_event_id=data.get("import_event_id"),
            raw=dict(data),
        )


@dataclass(frozen=True)
class PaymentRequest:
    """What was asked for, and where it was meant to go."""

    record_id: str
    request_id: str
    invoice_id: str
    expected_destination: str
    amount: str
    token_contract: str
    memo: str = ""
    simulated: bool = True
    source_file: str | None = None
    import_event_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaymentRequest":
        return cls(
            record_id=str(_require(data, "record_id", "PaymentRequest")),
            request_id=str(_require(data, "request_id", "PaymentRequest")),
            invoice_id=str(_require(data, "invoice_id", "PaymentRequest")),
            expected_destination=_address(
                _require(data, "expected_destination", "PaymentRequest"),
                "PaymentRequest", "expected_destination"),
            amount=_decimal_string(
                _require(data, "amount", "PaymentRequest"), "PaymentRequest", "amount"),
            token_contract=_address(
                _require(data, "token_contract", "PaymentRequest"),
                "PaymentRequest", "token_contract"),
            memo=str(data.get("memo", "")),
            simulated=bool(data.get("simulated", True)),
            source_file=data.get("source_file"),
            import_event_id=data.get("import_event_id"),
            raw=dict(data),
        )


@dataclass(frozen=True)
class LedgerEntry:
    """What the books claim happened."""

    record_id: str
    entry_id: str
    invoice_id: str
    amount: str
    direction: str              # "credit" or "debit"
    status: str = "posted"
    posted_at: str | None = None
    memo: str = ""
    simulated: bool = True
    source_file: str | None = None
    import_event_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    VALID_DIRECTIONS = ("credit", "debit")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerEntry":
        direction = str(_require(data, "direction", "LedgerEntry")).strip().lower()
        if direction not in cls.VALID_DIRECTIONS:
            raise RecordError(
                f"LedgerEntry.direction must be one of {cls.VALID_DIRECTIONS}, got {direction!r}")
        return cls(
            record_id=str(_require(data, "record_id", "LedgerEntry")),
            entry_id=str(_require(data, "entry_id", "LedgerEntry")),
            invoice_id=str(_require(data, "invoice_id", "LedgerEntry")),
            amount=_decimal_string(
                _require(data, "amount", "LedgerEntry"), "LedgerEntry", "amount"),
            direction=direction,
            status=str(data.get("status", "posted")),
            posted_at=data.get("posted_at"),
            memo=str(data.get("memo", "")),
            simulated=bool(data.get("simulated", True)),
            source_file=data.get("source_file"),
            import_event_id=data.get("import_event_id"),
            raw=dict(data),
        )


@dataclass(frozen=True)
class ApprovedAddress:
    """An allow-listed destination.

    A destination outside this list is a *mismatch* or a *risk indicator* -- never "fraud",
    "scam" or "theft" (G6). The wording matters because the system does not know intent.
    """

    record_id: str
    address: str
    approved_for: str
    approved_at: str | None = None
    approved_by: str | None = None
    simulated: bool = True
    source_file: str | None = None
    import_event_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovedAddress":
        return cls(
            record_id=str(_require(data, "record_id", "ApprovedAddress")),
            address=_address(_require(data, "address", "ApprovedAddress"),
                             "ApprovedAddress", "address"),
            approved_for=str(data.get("approved_for", "")),
            approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"),
            simulated=bool(data.get("simulated", True)),
            source_file=data.get("source_file"),
            import_event_id=data.get("import_event_id"),
            raw=dict(data),
        )


def find_duplicate_ids(records: list[Any], id_attr: str) -> dict[str, list[str]]:
    """Group record_ids by a business identifier that appears more than once.

    Returns {business_id: [record_id, ...]} for ids seen 2+ times. A duplicate is reported with
    every record_id involved, so a report can cite all of them rather than just the second.
    """
    by_id: dict[str, list[str]] = {}
    for record in records:
        key = str(getattr(record, id_attr))
        by_id.setdefault(key, []).append(record.record_id)
    return {k: v for k, v in by_id.items() if len(v) > 1}

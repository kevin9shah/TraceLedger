"""Independent validator for LLM-produced reports.

The LLM may propose hypotheses and draft prose. It is never the authority on chain facts (G8) and
it may never assert something the deterministic layer did not establish (G4). This module is the
gate that enforces that, in code, after the model has spoken.

It checks four things, and it is deliberately hostile:

1. **Every cited evidence ID exists.** An ID the model invented is rejected, not quietly dropped.
2. **Every number matches the deterministic layer.** Amounts, block numbers and confirmation
   counts are compared against the verified findings; the model is not permitted to recompute,
   round or restate them differently.
3. **No unsupported claims.** A line marked VERIFIED or CONFLICT must be backed by a
   deterministic finding of the same status. The model cannot promote a HYPOTHESIS to a fact.
4. **No banned language.** Fraud verdicts (G6) and finality claims (P10) are rejected outright.

A report that fails is **rejected or downgraded**, never shown as-is. Downgrading turns an
unsupported VERIFIED/CONFLICT into a HYPOTHESIS, which is the honest reading of "the model said
it but nothing backs it".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from .verify import Finding, Status, VerificationResult


class Line(str, Enum):
    """The five permitted report line kinds (G4)."""

    VERIFIED = "VERIFIED"
    CONFLICT = "CONFLICT"
    HYPOTHESIS = "HYPOTHESIS"
    MISSING = "MISSING"
    NEXT_STEP = "NEXT_STEP"


# Statuses that must rest on a deterministic finding.
FACT_LINES = (Line.VERIFIED, Line.CONFLICT)

# G6: no fraud verdicts. The system does not know intent.
BANNED_VERDICT_WORDS = (
    "fraud", "fraudulent", "scam", "scammer", "theft", "thief", "stolen", "stole",
    "embezzl", "launder", "criminal", "crime",
)

# P10: "confirmed on-chain" is not "final". These phrases claim more than the chain supports.
BANNED_FINALITY_PHRASES = (
    "is final", "final settlement", "finalised", "finalized", "irreversible",
    "cannot be reversed", "guaranteed", "tamper-proof", "tamperproof", "immutable proof",
)

# Any decimal or integer number in prose, so it can be checked against the facts.
NUMBER_PATTERN = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")


class Severity(str, Enum):
    REJECT = "reject"        # the report must not be shown
    DOWNGRADE = "downgrade"  # the line becomes a HYPOTHESIS


@dataclass(frozen=True)
class Violation:
    code: str
    severity: Severity
    message: str
    line_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity.value,
                "message": self.message, "line_index": self.line_index}


@dataclass
class ReportLine:
    """One line of an LLM-drafted report, before validation.

    `finding_code` is the deterministic check this line rests on, e.g. "payment.asset". A
    VERIFIED or CONFLICT line **must** name one.

    Requiring the code, rather than accepting any shared evidence ID, closes a real hole: a
    transaction hash appears in several findings at once, so citing the hash alone would let a
    model claim "the amount was correct" and find spurious support from an unrelated VERIFIED
    finding about the transaction's status. The code makes support exact.
    """

    status: Line
    text: str
    evidence_ids: tuple[str, ...] = ()
    finding_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "text": self.text,
                "evidence_ids": list(self.evidence_ids), "finding_code": self.finding_code}


@dataclass
class ValidationOutcome:
    accepted: bool
    lines: list[ReportLine] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    downgraded: int = 0

    @property
    def rejected(self) -> bool:
        return not self.accepted

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted, "downgraded": self.downgraded,
            "lines": [line.as_dict() for line in self.lines],
            "violations": [v.as_dict() for v in self.violations],
        }


def known_evidence_ids(result: VerificationResult,
                       extra: Iterable[str] = ()) -> frozenset[str]:
    """Every evidence ID a report is permitted to cite.

    Built from the deterministic findings plus explicitly supplied record IDs. Anything outside
    this set does not exist as far as the report is concerned.
    """
    ids: set[str] = set(extra)
    for finding in result.findings:
        ids.update(finding.evidence_ids)
    return frozenset(ids)


def _numbers_in(text: str) -> set[str]:
    """Numbers appearing in prose, normalised so 1,000 and 1000 compare equal."""
    return {m.group(0).replace(",", "") for m in NUMBER_PATTERN.finditer(text)}


def _numbers_from_findings(result: VerificationResult) -> set[str]:
    """Every number the deterministic layer actually established.

    Collected from both finding summaries and their structured detail, so a model restating a
    verified figure is accepted while an invented one is not.
    """
    allowed: set[str] = set()
    for finding in result.findings:
        allowed |= _numbers_in(finding.summary)
        for key, value in finding.detail.items():
            if isinstance(value, (int, str)):
                allowed |= _numbers_in(str(value))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    allowed |= _numbers_in(str(item))
    return allowed


def _supporting_finding(line: ReportLine, result: VerificationResult) -> Finding | None:
    """The deterministic finding this line rests on, or None.

    Support requires all three of: the named `finding_code` exists, its status matches the
    line's, and it shares at least one evidence ID with the line. Any shared evidence ID alone
    is not enough -- a transaction hash is cited by several findings, so matching on it would
    manufacture support for an unrelated claim.
    """
    if line.finding_code is None:
        return None
    want = Status.VERIFIED if line.status is Line.VERIFIED else Status.CONFLICT
    for finding in result.by_status(want):
        if finding.code != line.finding_code:
            continue
        if set(line.evidence_ids) & set(finding.evidence_ids):
            return finding
    return None


def validate_report(
    lines: Sequence[ReportLine],
    result: VerificationResult,
    *,
    extra_evidence_ids: Iterable[str] = (),
    allow_downgrade: bool = True,
) -> ValidationOutcome:
    """Check an LLM-drafted report against the deterministic layer.

    `allow_downgrade=False` makes every unsupported fact line a hard rejection, which is the
    stricter mode used when measuring the unsupported-claim rate at CP8.
    """
    allowed_ids = known_evidence_ids(result, extra_evidence_ids)
    allowed_numbers = _numbers_from_findings(result)
    outcome = ValidationOutcome(accepted=True)

    for index, line in enumerate(lines):
        kept = ReportLine(status=line.status, text=line.text,
                          evidence_ids=line.evidence_ids, finding_code=line.finding_code)

        # 1. Invented evidence IDs are a hard failure. The model cited something that does not
        #    exist, which means the citation machinery cannot be trusted for this report.
        invented = [e for e in line.evidence_ids if e not in allowed_ids]
        if invented:
            outcome.violations.append(Violation(
                code="evidence.unknown_id", severity=Severity.REJECT, line_index=index,
                message=(f"cites evidence that does not exist: {', '.join(sorted(invented))}. "
                         f"Known evidence for this case: {len(allowed_ids)} id(s).")))
            outcome.accepted = False
            continue

        # 2. Banned language is a hard failure regardless of status (G6, P10).
        lowered = line.text.lower()
        for word in BANNED_VERDICT_WORDS:
            if word in lowered:
                outcome.violations.append(Violation(
                    code="language.fraud_verdict", severity=Severity.REJECT, line_index=index,
                    message=(f"uses {word!r}. TraceLedger reports mismatches and risk indicators, "
                             "never verdicts about intent (G6).")))
                outcome.accepted = False
        for phrase in BANNED_FINALITY_PHRASES:
            if phrase in lowered:
                outcome.violations.append(Violation(
                    code="language.finality_claim", severity=Severity.REJECT, line_index=index,
                    message=(f"uses {phrase!r}. Confirmed on-chain is not final: issuers can "
                             "freeze or blacklist balances (P10).")))
                outcome.accepted = False
        if not outcome.accepted and outcome.violations[-1].line_index == index:
            continue

        # 3. A fact line must rest on a deterministic finding of the same status.
        if line.status in FACT_LINES:
            if not line.evidence_ids:
                outcome.violations.append(Violation(
                    code="evidence.missing", severity=Severity.REJECT, line_index=index,
                    message=f"{line.status.value} line cites no evidence (G4)."))
                outcome.accepted = False
                continue
            support = _supporting_finding(kept, result)
            if support is None:
                if line.finding_code is None:
                    reason = (f"{line.status.value} names no deterministic check. A fact line "
                              "must declare the finding_code it rests on.")
                else:
                    reason = (f"{line.status.value} names check {line.finding_code!r}, but no "
                              f"{line.status.value} finding with that code cites this line's "
                              "evidence.")
                if allow_downgrade:
                    outcome.violations.append(Violation(
                        code="claim.unsupported", severity=Severity.DOWNGRADE, line_index=index,
                        message=f"{reason} Downgraded to HYPOTHESIS."))
                    kept = ReportLine(status=Line.HYPOTHESIS, text=line.text,
                                      evidence_ids=line.evidence_ids,
                                      finding_code=line.finding_code)
                    outcome.downgraded += 1
                else:
                    outcome.violations.append(Violation(
                        code="claim.unsupported", severity=Severity.REJECT, line_index=index,
                        message=reason))
                    outcome.accepted = False
                    continue

        # 4. Numbers must come from the deterministic layer. The LLM never computes (G8).
        invented_numbers = sorted(_numbers_in(line.text) - allowed_numbers)
        if invented_numbers:
            outcome.violations.append(Violation(
                code="number.unverified", severity=Severity.REJECT, line_index=index,
                message=(f"states number(s) the deterministic layer did not establish: "
                         f"{', '.join(invented_numbers)}. The model must not compute or round "
                         "figures (G8).")))
            outcome.accepted = False
            continue

        outcome.lines.append(kept)

    return outcome

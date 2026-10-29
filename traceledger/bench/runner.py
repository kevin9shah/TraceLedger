"""Run a system over the benchmark and score it. Numbers come from runs, never by hand (G10)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..chain.rpc import Provenance
from ..chain.tokens import TokenMetadata
from ..chain.transfers import TransactionFacts, TransferEvent
from ..records import ApprovedAddress, Invoice, LedgerEntry, PaymentRequest

ROOT = Path(__file__).resolve().parent.parent.parent
BENCH = ROOT / "benchmark"

OUTCOMES = ("conflict", "no_conflict", "unresolved")
# "error" is not an outcome. It means our infrastructure failed (API quota, outage), and such a
# case is EXCLUDED from scoring rather than counted as an abstention. Counting API failures as
# correct abstentions is how the first CP8 run produced a meaningless plain-LLM score (S22).
ERROR_OUTCOME = "error"


def load_chain_facts() -> dict[str, TransactionFacts]:
    """Rehydrate captured real-transaction facts, keyed by tx hash."""
    blob = json.loads((BENCH / "chain_facts.json").read_text())
    out: dict[str, TransactionFacts] = {}
    for facts in blob["facts"].values():
        transfers = tuple(
            TransferEvent(token=t["token"], sender=t["sender"], recipient=t["recipient"],
                          value=int(t["value"]), log_index=t["log_index"])
            for t in facts["transfers"]
        )
        out[facts["tx_hash"]] = TransactionFacts(
            tx_hash=facts["tx_hash"], status=facts["status"],
            block_number=facts["block_number"], chain_id=facts["chain_id"],
            sender=facts["sender"], called_contract=facts["called_contract"],
            transfers=transfers, confirmations=facts["confirmations"],
            provenance=Provenance(rpc_url=facts["provenance"]["rpc_url"],
                                  chain_id=facts["provenance"]["chain_id"],
                                  method=facts["provenance"]["method"],
                                  read_at=facts["provenance"]["read_at"]),
        )
    return out


def load_token_meta() -> dict[str, TokenMetadata]:
    """Token metadata read from the chain earlier and cached. Decimals are never hardcoded (G7)."""
    blob = json.loads((ROOT / "data" / "token_registry.json").read_text())
    out: dict[str, TokenMetadata] = {}
    for address, entry in blob["tokens"].items():
        out[address] = TokenMetadata(
            address=address, decimals=entry["decimals"], symbol=entry["symbol"],
            name=entry["name"],
            provenance=Provenance(rpc_url=entry["provenance"]["rpc_url"],
                                  chain_id=entry["provenance"]["chain_id"],
                                  method=entry["provenance"]["method"],
                                  read_at=entry["provenance"]["read_at"]),
        )
    return out


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    tx_hashes: tuple[str, ...]
    invoice: Invoice
    all_invoices: tuple[Invoice, ...]
    payment_request: PaymentRequest | None
    all_requests: tuple[PaymentRequest, ...]
    ledger_entries: tuple[LedgerEntry, ...]
    approved: tuple[ApprovedAddress, ...]
    raw: dict[str, Any]


def load_cases() -> list[Case]:
    """Load benchmark INPUTS. Ground truth is a separate file and is not read here (G11)."""
    blob = json.loads((BENCH / "cases.json").read_text())
    cases: list[Case] = []
    for case in blob["cases"]:
        records = case["records"]
        invoices = tuple(Invoice.from_dict(d) for d in records["invoices"])
        requests = tuple(PaymentRequest.from_dict(d) for d in records["payment_requests"])
        cases.append(Case(
            case_id=case["case_id"], title=case["title"],
            tx_hashes=tuple(e["tx_hash"] for e in case["chain_evidence"]),
            invoice=invoices[0], all_invoices=invoices,
            payment_request=requests[0] if requests else None, all_requests=requests,
            ledger_entries=tuple(LedgerEntry.from_dict(d) for d in records["ledger_entries"]),
            approved=tuple(ApprovedAddress.from_dict(d) for d in records["approved_addresses"]),
            raw=case,
        ))
    return cases


def load_ground_truth() -> dict[str, dict]:
    blob = json.loads((BENCH / "ground_truth.json").read_text())
    return {t["case_id"]: t for t in blob["ground_truth"]}


# --------------------------------------------------------------------------- scoring

@dataclass
class Scores:
    system: str
    n: int = 0
    outcome_correct: int = 0
    # The dangerous error: truth says conflict or unresolved, system says "fine".
    false_resolutions: int = 0
    # Answering definitively where the truth is "unresolved".
    over_answered: int = 0
    over_answer_opportunities: int = 0
    # Correctly abstaining where the truth is "unresolved".
    abstained_correctly: int = 0
    # Did the system name the right issue, not merely the right outcome?
    issue_identified: int = 0
    issue_opportunities: int = 0
    # Cases excluded because the call never completed. Reported, never hidden.
    errored: int = 0
    errored_cases: list[str] = None  # type: ignore[assignment]
    # Flagging a clean case.
    false_positives: int = 0
    clean_opportunities: int = 0
    per_case: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.per_case is None:
            self.per_case = []
        if self.errored_cases is None:
            self.errored_cases = []

    def pct(self, num: int, den: int) -> str:
        return "n/a" if den == 0 else f"{100.0 * num / den:.0f}% ({num}/{den})"

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system, "cases_scored": self.n,
            "cases_excluded_due_to_errors": self.errored,
            "errored_cases": list(self.errored_cases),
            "outcome_accuracy": self.pct(self.outcome_correct, self.n),
            "issue_identification": self.pct(self.issue_identified, self.issue_opportunities),
            "false_resolution_rate": self.pct(self.false_resolutions, self.n),
            "false_positive_rate_on_clean_cases": self.pct(
                self.false_positives, self.clean_opportunities),
            "abstention_when_required": self.pct(
                self.abstained_correctly, self.over_answer_opportunities),
            "over_answered": self.pct(self.over_answered, self.over_answer_opportunities),
            "per_case": self.per_case,
        }


def score(system: str, predictions: dict[str, dict], truth: dict[str, dict]) -> Scores:
    s = Scores(system=system)
    for case_id, expected in truth.items():
        prediction = predictions[case_id]
        want = expected["expected_outcome"]
        got = prediction["outcome"]
        if got == ERROR_OUTCOME:
            # Excluded, and named, so a run with many failures cannot masquerade as a result.
            s.errored += 1
            s.errored_cases.append(case_id)
            s.per_case.append({
                "case_id": case_id, "expected": want, "got": ERROR_OUTCOME,
                "outcome_correct": None, "excluded": True,
                "expected_issues": expected.get("issue_types", []),
                "reported_issues": [], "issue_identified": None,
                "reasons": prediction.get("reasons", [])[:1]})
            continue
        s.n += 1
        correct = got == want
        s.outcome_correct += int(correct)

        if want in ("conflict", "unresolved") and got == "no_conflict":
            s.false_resolutions += 1
        if want == "no_conflict":
            s.clean_opportunities += 1
            if got != "no_conflict":
                s.false_positives += 1
        if want == "unresolved":
            s.over_answer_opportunities += 1
            if got == "unresolved":
                s.abstained_correctly += 1
            else:
                s.over_answered += 1

        # Issue identification: for conflict cases, did it name a required issue type?
        issue_hit = None
        if want == "conflict" and expected.get("issue_types"):
            s.issue_opportunities += 1
            reported = {i for i in prediction.get("issues", [])}
            issue_hit = bool(reported & set(expected["issue_types"]))
            s.issue_identified += int(issue_hit)

        s.per_case.append({
            "case_id": case_id, "expected": want, "got": got, "outcome_correct": correct,
            "expected_issues": expected.get("issue_types", []),
            "reported_issues": prediction.get("issues", []),
            "issue_identified": issue_hit,
            "reasons": prediction.get("reasons", [])[:3],
        })
    return s

#!/usr/bin/env python3
"""CP8: rules-only vs plain LLM vs TraceLedger, over the 25 benchmark cases.

Makes real API calls. Every number it writes comes from this run (G10). Failures of all three
systems are recorded, including cases where TraceLedger loses.

    python scripts/run_three_way.py [--limit N] [--systems a,b,c]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from traceledger.baselines.plain_llm import run_plain_llm
from traceledger.baselines.rules_only import run_rules_only
from traceledger.bench.runner import (
    BENCH, load_cases, load_chain_facts, load_ground_truth, load_token_meta, score,
)
from traceledger.config import load_config
from traceledger.llm.investigate import investigate
from traceledger.llm.provider import LLMError, provider_from_config
from traceledger.verify import Status, verify_payment_case

FACTS = load_chain_facts()
META = load_token_meta()
SYMBOLS = {a: (m.symbol or "") for a, m in META.items()}
DECIMALS = {a: m.decimals for a, m in META.items()}

CODE_TO_ISSUE = {
    "payment.asset": ["wrong_asset", "lookalike_token"],
    "tx.status": ["status_conflict"],
    "payment.destination": ["destination_conflict"],
    "destination.approval": ["unapproved_destination"],
    "payment.amount": ["amount_mismatch", "partial_payment"],
    "ledger.arithmetic": ["amount_mismatch", "partial_payment"],
    "duplicate.invoice_id": ["duplicate_records"],
    "duplicate.request_id": ["duplicate_records"],
    "duplicate.entry_id": ["duplicate_records"],
    "payment.zero_value": ["zero_value"],
    "payment.direction": ["direction_reversed"],
    "payment.ambiguous_transfer": ["ambiguous_settlement"],
    "records.token_disagreement": ["record_disagreement"],
    "tx.confirmations": ["insufficient_confirmations"],
}


def facts_for(case):
    return [FACTS[h] for h in case.tx_hashes]


def deterministic(case, truth):
    meta = META.get(case.invoice.token_contract)
    if meta is None:
        return None, None
    min_conf = (truth.get("run_with") or {}).get("min_confirmations", 12)
    return verify_payment_case(
        facts=facts_for(case)[0], invoice=case.invoice, token_meta=meta,
        payment_request=case.payment_request, approved=case.approved,
        ledger_entries=case.ledger_entries, invoices=case.all_invoices,
        payment_requests=case.all_requests, min_confirmations=min_conf), meta


def run_rules(case, truth):
    v = run_rules_only(facts_for(case), case.invoice, SYMBOLS, token_decimals=DECIMALS,
                       payment_request=case.payment_request,
                       ledger_entries=case.ledger_entries, invoices=case.all_invoices,
                       payment_requests=case.all_requests)
    return v.as_dict()


def make_plain_llm(provider):
    def run(case, truth):
        v = run_plain_llm(provider, facts_for(case), case.invoice,
                          payment_request=case.payment_request,
                          ledger_entries=case.ledger_entries, invoices=case.all_invoices,
                          payment_requests=case.all_requests, token_decimals=DECIMALS)
        return v.as_dict()
    return run


def make_traceledger(provider):
    def run(case, truth):
        result, meta = deterministic(case, truth)
        if result is None:
            return {"outcome": "unresolved", "issues": ["missing_evidence"],
                    "reasons": ["no verified token metadata; refusing to compare amounts"],
                    "cited": []}
        try:
            inv = investigate(provider, result, case.invoice, case.payment_request,
                              case.ledger_entries)
        except LLMError as exc:
            # The LLM failing must not change the facts: fall back to the deterministic verdict
            # and record that the narrative layer was unavailable (D38). The outcome is still a
            # real answer -- it came from code -- but `llm_error` is recorded so a run cannot be
            # described as exercising the full pipeline when it did not.
            fallback = deterministic_only(result, note=f"LLM unavailable: {exc}")
            fallback["llm_error"] = str(exc)
            fallback["llm_available"] = False
            return fallback
        issues: list[str] = []
        for line in inv.validation.lines:
            if line.finding_code:
                for issue in CODE_TO_ISSUE.get(line.finding_code, []):
                    if issue not in issues:
                        issues.append(issue)
        det = deterministic_only(result)
        for issue in det["issues"]:
            if issue not in issues:
                issues.append(issue)
        return {
            "outcome": det["outcome"],     # the deterministic layer decides (G8)
            "llm_outcome": inv.outcome,    # what the model would have said alone
            "issues": issues,
            "reasons": [f"{l.status.value}: {l.text}" for l in inv.validation.lines],
            "cited": sorted({e for l in inv.validation.lines for e in l.evidence_ids}),
            "accepted": inv.accepted,
            "downgraded": inv.validation.downgraded,
            "violations": [v.as_dict() for v in inv.validation.violations],
            "hypotheses": inv.hypotheses,
            "next_steps": inv.next_steps,
            "injection_observed": inv.injection_observed,
            "latency_ms": inv.response.latency_ms if inv.response else 0.0,
            "llm_available": True,
        }
    return run


def deterministic_only(result, note: str | None = None):
    conflicts = result.by_status(Status.CONFLICT)
    missing = result.by_status(Status.MISSING)
    issues: list[str] = []
    for f in conflicts + missing:
        for issue in CODE_TO_ISSUE.get(f.code, []):
            if issue not in issues:
                issues.append(issue)
    if missing and not conflicts:
        issues.append("missing_evidence")
    outcome = "conflict" if conflicts else ("unresolved" if missing else "no_conflict")
    reasons = [f"{f.status.value}: {f.summary}" for f in conflicts + missing]
    if note:
        reasons.insert(0, note)
    return {"outcome": outcome, "issues": issues, "reasons": reasons,
            "cited": sorted({e for f in result.findings for e in f.evidence_ids})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--systems", default="rules_only,plain_llm,traceledger")
    args = ap.parse_args()

    cfg = load_config()
    provider = provider_from_config(cfg)
    cases = load_cases()
    if args.limit:
        cases = cases[:args.limit]
    truth = load_ground_truth()

    registry = {
        "rules_only": run_rules,
        "plain_llm": make_plain_llm(provider),
        "traceledger": make_traceledger(provider),
    }
    wanted = [s.strip() for s in args.systems.split(",") if s.strip()]

    predictions: dict[str, dict] = {}
    scores = {}
    for name in wanted:
        fn = registry[name]
        preds = {}
        started = time.perf_counter()
        for i, case in enumerate(cases, 1):
            t = time.perf_counter()
            try:
                preds[case.case_id] = fn(case, truth[case.case_id])
            except Exception as exc:  # noqa: BLE001 - a crash is a result, recorded as one
                preds[case.case_id] = {"outcome": "unresolved", "issues": [],
                                       "reasons": [f"crashed: {type(exc).__name__}: {exc}"],
                                       "cited": [], "error": str(exc)}
            print(f"  {name:12} {case.case_id} {preds[case.case_id]['outcome']:11} "
                  f"{(time.perf_counter()-t)*1000:7.0f} ms", flush=True)
        predictions[name] = preds
        scores[name] = score(name, preds, {k: truth[k] for k in preds})
        d = scores[name].as_dict()
        llm_ok = sum(1 for e in preds.values() if e.get("llm_available"))
        print(f"{name}: {d['outcome_accuracy']} outcome accuracy, "
              f"{d['cases_excluded_due_to_errors']} excluded (API errors), "
              f"{llm_ok} with a live LLM response, in {time.perf_counter()-started:.0f}s",
              flush=True)

    out = BENCH / "three_way.json"
    out.write_text(json.dumps({
        "_comment": "CP8 three-way comparison. Generated by scripts/run_three_way.py.",
        "model": provider.model,
        "case_count": len(cases),
        "scores": {k: v.as_dict() for k, v in scores.items()},
        "predictions": predictions,
    }, indent=2) + "\n")
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

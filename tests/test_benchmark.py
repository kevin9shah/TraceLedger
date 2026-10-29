"""Benchmark hygiene (G11) and schema validation.

These tests exist because a benchmark that leaks its labels, or that is 25 copies of one template,
produces numbers that mean nothing. They check the dataset itself, not the system under test.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from traceledger.records import ApprovedAddress, Invoice, LedgerEntry, PaymentRequest

BENCH = Path(__file__).resolve().parent.parent / "benchmark"

CASES = json.loads((BENCH / "cases.json").read_text())
TRUTH = json.loads((BENCH / "ground_truth.json").read_text())
FACTS = json.loads((BENCH / "chain_facts.json").read_text())

VALID_OUTCOMES = {"conflict", "no_conflict", "unresolved"}
# Any key that would reveal the answer if it appeared in the inputs file.
LABEL_KEYS = {"expected_outcome", "issue_types", "must_report", "must_cite", "must_not_report",
              "must_not_cite", "notes", "accept_either", "must_produce_next_step", "ground_truth",
              "label", "answer", "expected"}


class TestStructure:
    def test_twenty_five_cases(self):
        assert CASES["case_count"] == 25 and len(CASES["cases"]) == 25

    def test_every_case_has_a_label(self):
        assert {c["case_id"] for c in CASES["cases"]} == {
            t["case_id"] for t in TRUTH["ground_truth"]}

    def test_case_ids_unique(self):
        ids = [c["case_id"] for c in CASES["cases"]]
        assert len(set(ids)) == len(ids)

    def test_outcomes_are_from_the_fixed_set(self):
        for t in TRUTH["ground_truth"]:
            assert t["expected_outcome"] in VALID_OUTCOMES, t["case_id"]

    def test_every_case_has_a_title_and_an_operator_note(self):
        for c in CASES["cases"]:
            assert c["title"].strip() and len(c["operator_note"]) > 20, c["case_id"]


class TestNoLabelLeakage:
    """G11: ground truth must be stored separately from model inputs."""

    def test_no_label_keys_anywhere_in_the_inputs_file(self):
        found: list[str] = []

        def walk(node, path="$"):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in LABEL_KEYS:
                        found.append(f"{path}.{key}")
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        walk(CASES)
        assert not found, f"label keys leaked into cases.json: {found}"

    def test_inputs_file_does_not_contain_outcome_words(self):
        """A case must not be solvable by grepping its own text."""
        for case in CASES["cases"]:
            blob = json.dumps({k: v for k, v in case.items() if k != "operator_note"}).lower()
            for word in ("no_conflict", "unresolved", "expected_outcome"):
                assert word not in blob, f"{case['case_id']} leaks {word!r}"

    def test_the_two_files_are_genuinely_separate(self):
        assert "ground_truth" not in CASES
        assert "cases" not in TRUTH


class TestNoNearDuplicateTemplates:
    """G11: no near-duplicate templates across cases."""

    def signature(self, case: dict) -> tuple:
        """A case's shape, ignoring identifiers that differ by construction."""
        records = case["records"]
        return (
            len(records["invoices"]), len(records["payment_requests"]),
            len(records["ledger_entries"]), len(records["approved_addresses"]),
            tuple(sorted(i["token_contract"] for i in records["invoices"])),
            tuple(sorted(i["amount"] for i in records["invoices"])),
            tuple(sorted(e["tx_hash"] for e in case["chain_evidence"])),
        )

    def test_no_two_cases_share_a_full_signature(self):
        seen: dict[tuple, str] = {}
        clashes = []
        for case in CASES["cases"]:
            sig = self.signature(case)
            if sig in seen:
                clashes.append(f"{seen[sig]} ~ {case['case_id']}")
            seen[sig] = case["case_id"]
        assert not clashes, f"near-duplicate cases: {clashes}"

    def test_counterparties_are_varied(self):
        parties = [i["counterparty"] for c in CASES["cases"] for i in c["records"]["invoices"]]
        # A handful of cases legitimately reuse a party across two invoices; most must differ.
        assert len(set(parties)) >= 20, Counter(parties).most_common(3)

    def test_titles_are_distinct(self):
        titles = [c["title"] for c in CASES["cases"]]
        assert len(set(titles)) == len(titles)

    def test_amounts_are_not_all_the_same(self):
        amounts = {i["amount"] for c in CASES["cases"] for i in c["records"]["invoices"]}
        assert len(amounts) >= 8, amounts


class TestCoverage:
    def issue_types(self) -> Counter:
        return Counter(i for t in TRUTH["ground_truth"] for i in t["issue_types"])

    def test_all_three_mvp_exception_types_present(self):
        types = self.issue_types()
        assert types["duplicate_records"] >= 1
        assert types["status_conflict"] >= 1
        assert types["destination_conflict"] >= 1

    def test_cross_token_cases_present(self):
        assert self.issue_types()["wrong_asset"] >= 2

    def test_lookalike_token_case_present(self):
        """Both USDC contracts report the same symbol; this must be exercised."""
        assert self.issue_types()["lookalike_token"] >= 1

    def test_tricky_cases_present(self):
        types = self.issue_types()
        for required in ("partial_payment", "ambiguous_settlement", "zero_value",
                         "direction_reversed", "missing_evidence"):
            assert types[required] >= 1, required

    def test_abstention_cases_present(self):
        """G5: the benchmark must be able to detect over-answering."""
        unresolved = [t for t in TRUTH["ground_truth"] if t["expected_outcome"] == "unresolved"]
        assert len(unresolved) >= 3, [t["case_id"] for t in unresolved]

    def test_clean_control_cases_present(self):
        """Without clean cases, a system that always says CONFLICT would score perfectly."""
        clean = [t for t in TRUTH["ground_truth"] if t["expected_outcome"] == "no_conflict"]
        assert len(clean) >= 3, [t["case_id"] for t in clean]

    def test_prompt_injection_case_present(self):
        assert self.issue_types()["prompt_injection"] >= 1

    def test_no_single_outcome_dominates(self):
        """A degenerate split would let a constant answer score well."""
        counts = Counter(t["expected_outcome"] for t in TRUTH["ground_truth"])
        assert max(counts.values()) <= 18, counts


class TestRecordsParse:
    """Every synthetic record must parse under the real production model."""

    def test_all_records_parse(self):
        for case in CASES["cases"]:
            r = case["records"]
            for data in r["invoices"]:
                Invoice.from_dict(data)
            for data in r["payment_requests"]:
                PaymentRequest.from_dict(data)
            for data in r["ledger_entries"]:
                LedgerEntry.from_dict(data)
            for data in r["approved_addresses"]:
                ApprovedAddress.from_dict(data)

    def test_every_business_record_is_flagged_simulated(self):
        """G3: invented data must be visibly labelled."""
        for case in CASES["cases"]:
            for group in case["records"].values():
                for record in group:
                    assert record["simulated"] is True, case["case_id"]

    def test_no_amount_is_a_json_float(self):
        """G8: a float in the dataset would defeat exact base-unit comparison."""
        blob = (BENCH / "cases.json").read_text()
        for match in re.finditer(r'"amount":\s*([^,\n]+)', blob):
            assert match.group(1).strip().startswith('"'), match.group(0)


class TestChainEvidenceIsReal:
    def test_chain_evidence_is_never_simulated(self):
        """G3: chain facts are real; only business records are synthetic."""
        for case in CASES["cases"]:
            for evidence in case["chain_evidence"]:
                assert evidence["simulated"] is False
                assert evidence["origin"] == "public_mainnet"

    def test_every_referenced_hash_has_captured_facts(self):
        captured = {f["tx_hash"] for f in FACTS["facts"].values()}
        for case in CASES["cases"]:
            for evidence in case["chain_evidence"]:
                assert evidence["tx_hash"] in captured, case["case_id"]

    def test_hashes_are_well_formed(self):
        for case in CASES["cases"]:
            for evidence in case["chain_evidence"]:
                assert re.fullmatch(r"0x[0-9a-f]{64}", evidence["tx_hash"]), case["case_id"]

    def test_captured_facts_are_on_the_configured_chain(self):
        assert FACTS["chain_id"] == 137
        for label, facts in FACTS["facts"].items():
            assert facts["chain_id"] == 137, label

    def test_reverted_transactions_really_are_reverted(self):
        reverted = [f for f in FACTS["facts"].values() if f["status"] == 0]
        assert len(reverted) >= 2
        for facts in reverted:
            assert facts["transfers"] == [], "a reverted tx must emit no Transfer events"

    def test_a_real_zero_value_transfer_exists(self):
        """C10 relies on a genuine zero-value transfer rather than a doctored one."""
        zeros = [t for f in FACTS["facts"].values() for t in f["transfers"]
                 if int(t["value"]) == 0]
        assert zeros, "no real zero-value transfer captured"

    def test_a_multi_token_transaction_exists(self):
        multi = [f for f in FACTS["facts"].values()
                 if len({t["token"] for t in f["transfers"]}) > 1]
        assert multi, "no real multi-token transaction captured"

"""Validator tests: the gate that stops the LLM asserting things nothing supports.

Every test here describes a way a language model actually fails -- inventing a citation,
restating a number slightly wrong, promoting a guess to a fact, or obeying text embedded in an
uploaded document. If the validator cannot catch these, the LLM layer must not ship.
"""
from __future__ import annotations

import pytest

from traceledger.chain.rpc import Provenance
from traceledger.chain.tokens import TokenMetadata
from traceledger.chain.transfers import fetch_transaction_facts
from traceledger.records import ApprovedAddress, Invoice, PaymentRequest
from traceledger.validate import (
    BANNED_FINALITY_PHRASES,
    BANNED_VERDICT_WORDS,
    Line,
    ReportLine,
    Severity,
    known_evidence_ids,
    validate_report,
)
from traceledger.verify import Status, verify_payment_case
from tests.test_transfers import FakeRpc, fixture

USDT = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"
USDC = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
TX = "0x5e857c89f092901403c91fc634d84ff531b795303d448b9e6c1b25af251f5a05"
RECIPIENT = "0x5f6d2b112c2d0ebe87d0d95d08ce47e13e01866a"


def meta(address: str, decimals: int = 6, symbol: str = "USDC") -> TokenMetadata:
    return TokenMetadata(address=address, decimals=decimals, symbol=symbol, name="t",
                         provenance=Provenance(rpc_url="http://test", chain_id=137,
                                               method="eth_call", read_at=0.0))


def wrong_asset_result():
    """A real case: invoice names USDC, the chain delivered USDT."""
    facts = fetch_transaction_facts(FakeRpc(fixture("tx_5e857c89"), head=96_369_500), TX)
    invoice = Invoice.from_dict({
        "record_id": "INV-R1", "invoice_id": "INV-1041", "counterparty": "Acme",
        "amount": "94.951335", "token_contract": USDC})
    request = PaymentRequest.from_dict({
        "record_id": "PR-R1", "request_id": "PR-77", "invoice_id": "INV-1041",
        "expected_destination": RECIPIENT, "amount": "94.951335", "token_contract": USDC})
    approved = [ApprovedAddress.from_dict({
        "record_id": "APP-1", "address": RECIPIENT, "approved_for": "Acme"})]
    return verify_payment_case(facts=facts, invoice=invoice, token_meta=meta(USDC),
                               payment_request=request, approved=approved)


# --------------------------------------------------------------------------- evidence set

class TestKnownEvidenceIds:
    def test_collects_ids_from_findings(self):
        ids = known_evidence_ids(wrong_asset_result())
        assert TX in ids and "INV-R1" in ids and "PR-R1" in ids and "APP-1" in ids

    def test_extra_ids_can_be_supplied(self):
        ids = known_evidence_ids(wrong_asset_result(), extra=["LE-9"])
        assert "LE-9" in ids

    def test_unknown_id_is_not_in_the_set(self):
        assert "SYSTEM-OK" not in known_evidence_ids(wrong_asset_result())


# --------------------------------------------------------------------------- invented citations

class TestInventedEvidence:
    def test_invented_id_is_rejected(self):
        """The failure mode that matters most: a citation that looks plausible and does not exist."""
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Wrong asset delivered.",
            evidence_ids=("SYSTEM-OK",))], wrong_asset_result())
        assert outcome.rejected
        assert outcome.violations[0].code == "evidence.unknown_id"
        assert outcome.violations[0].severity is Severity.REJECT

    def test_a_real_id_plus_an_invented_one_is_still_rejected(self):
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Wrong asset delivered.",
            evidence_ids=(TX, "LEDGER-999"))], wrong_asset_result())
        assert outcome.rejected
        assert "LEDGER-999" in outcome.violations[0].message

    def test_rejected_line_is_not_carried_into_the_output(self):
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Wrong asset.", evidence_ids=("NOPE-1",))],
            wrong_asset_result())
        assert outcome.lines == []

    def test_fact_line_with_no_evidence_at_all_is_rejected(self):
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The payment settled correctly.")], wrong_asset_result())
        assert outcome.rejected
        assert outcome.violations[0].code == "evidence.missing"


# --------------------------------------------------------------------------- unsupported claims

class TestUnsupportedClaims:
    def test_verified_claim_with_no_matching_finding_is_downgraded(self):
        """The model asserts a pass where the deterministic layer found a conflict."""
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The invoiced asset arrived as expected.",
            evidence_ids=(TX,))], wrong_asset_result())
        assert outcome.accepted
        assert outcome.downgraded == 1
        assert outcome.lines[0].status is Line.HYPOTHESIS
        assert outcome.violations[0].code == "claim.unsupported"

    def test_strict_mode_rejects_instead_of_downgrading(self):
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The invoiced asset arrived as expected.",
            evidence_ids=(TX,))], wrong_asset_result(), allow_downgrade=False)
        assert outcome.rejected

    def test_supported_conflict_is_accepted_unchanged(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Wrong asset: the invoiced contract was not transferred.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.accepted and outcome.downgraded == 0
        assert outcome.lines[0].status is Line.CONFLICT

    def test_hypothesis_needs_no_support(self):
        """A hypothesis is allowed to be speculative -- that is what the label is for."""
        outcome = validate_report([ReportLine(
            status=Line.HYPOTHESIS,
            text="The payer may have selected the wrong asset in their wallet.",
            evidence_ids=(TX,))], wrong_asset_result())
        assert outcome.accepted and outcome.downgraded == 0

    def test_next_step_needs_no_support(self):
        outcome = validate_report([ReportLine(
            status=Line.NEXT_STEP, text="Ask the payer which asset they selected.")],
            wrong_asset_result())
        assert outcome.accepted


# --------------------------------------------------------------------------- numbers

class TestNumbers:
    def test_number_from_the_findings_is_accepted(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT,
            text="Block 96369410 shows a transfer of a different token contract.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.accepted, [v.message for v in outcome.violations]

    def test_invented_number_is_rejected(self):
        """The model must not compute, round or invent a figure (G8)."""
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="A shortfall of 12.34 was identified.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.rejected
        assert outcome.violations[0].code == "number.unverified"
        assert "12.34" in outcome.violations[0].message

    def test_thousands_separators_do_not_defeat_the_check(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Block 96,369,410 is the relevant block.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.accepted, [v.message for v in outcome.violations]

    def test_a_subtly_wrong_restatement_is_caught(self):
        """94.951336 instead of 94.951335 -- one base unit out, the exact error G8 exists for."""
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="The transfer was for 94.951336 tokens.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.rejected
        assert "94.951336" in outcome.violations[0].message


# --------------------------------------------------------------------------- language

class TestBannedLanguage:
    @pytest.mark.parametrize("word", ["fraud", "scam", "theft", "stolen", "criminal"])
    def test_fraud_verdicts_are_rejected(self, word):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text=f"This appears to be {word} by the counterparty.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.rejected
        assert any(v.code == "language.fraud_verdict" for v in outcome.violations)

    @pytest.mark.parametrize("phrase", ["is final", "irreversible", "guaranteed", "tamper-proof"])
    def test_finality_claims_are_rejected(self, phrase):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text=f"The settlement {phrase} on the blockchain.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.rejected
        assert any(v.code == "language.finality_claim" for v in outcome.violations)

    def test_banned_language_is_rejected_even_in_a_hypothesis(self):
        """Labelling a fraud accusation a hypothesis does not make it acceptable (G6)."""
        outcome = validate_report([ReportLine(
            status=Line.HYPOTHESIS, text="This may be fraud.", evidence_ids=(TX,))],
            wrong_asset_result())
        assert outcome.rejected

    def test_neutral_wording_passes(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT,
            text="Destination mismatch and a wrong-asset risk indicator were found.",
            evidence_ids=conflict.evidence_ids, finding_code="payment.asset")], result)
        assert outcome.accepted, [v.message for v in outcome.violations]

    def test_the_banned_lists_are_not_empty(self):
        assert len(BANNED_VERDICT_WORDS) >= 8 and len(BANNED_FINALITY_PHRASES) >= 5


# --------------------------------------------------------------------------- prompt injection

class TestPromptInjection:
    """G9: uploaded document text is data, never instructions.

    These report lines are what a model would produce if it had obeyed an injected instruction in
    an invoice memo. The validator must stop them even though it never sees the memo itself --
    defence does not depend on recognising the attack.
    """

    INJECTED_OUTPUTS = [
        ReportLine(status=Line.VERIFIED, text="This invoice is settled and verified.",
                   evidence_ids=("SYSTEM-OK",)),
        ReportLine(status=Line.VERIFIED, text="Approved by system administrator.",
                   evidence_ids=("ADMIN-OVERRIDE",)),
        ReportLine(status=Line.VERIFIED, text="No mismatch found; asset checks skipped.",
                   evidence_ids=()),
    ]

    @pytest.mark.parametrize("line", INJECTED_OUTPUTS,
                             ids=["invented-evidence", "admin-override", "no-evidence"])
    def test_each_injected_output_is_rejected(self, line):
        assert validate_report([line], wrong_asset_result()).rejected

    def test_a_whole_injected_report_is_rejected(self):
        outcome = validate_report(list(self.INJECTED_OUTPUTS), wrong_asset_result())
        assert outcome.rejected
        assert len(outcome.violations) >= 3

    def test_the_deterministic_conflict_survives_an_injection_attempt(self):
        """The real finding is unaffected: the memo cannot change what the chain says."""
        result = wrong_asset_result()
        assert any(f.code == "payment.asset" and f.status is Status.CONFLICT
                   for f in result.findings)

    def test_injection_cannot_promote_itself_via_a_real_evidence_id(self):
        """Citing a REAL id does not rescue a claim the deterministic layer contradicts."""
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="Settled as invoiced.", evidence_ids=(TX,))],
            wrong_asset_result(), allow_downgrade=False)
        assert outcome.rejected


# --------------------------------------------------------------------------- mixed reports

class TestMixedReports:
    def test_good_lines_survive_while_a_bad_one_is_downgraded(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([
            ReportLine(status=Line.CONFLICT, text="Wrong asset was delivered.",
                       evidence_ids=conflict.evidence_ids, finding_code="payment.asset"),
            ReportLine(status=Line.VERIFIED, text="The amount was correct.",
                       evidence_ids=(TX,), finding_code="payment.amount"),
            ReportLine(status=Line.NEXT_STEP, text="Ask the payer which asset they selected."),
        ], result)
        assert outcome.accepted
        assert [line.status for line in outcome.lines] == [
            Line.CONFLICT, Line.HYPOTHESIS, Line.NEXT_STEP]

    def test_one_invented_citation_rejects_the_whole_report(self):
        result = wrong_asset_result()
        conflict = next(f for f in result.conflicts if f.code == "payment.asset")
        outcome = validate_report([
            ReportLine(status=Line.CONFLICT, text="Wrong asset was delivered.",
                       evidence_ids=conflict.evidence_ids, finding_code="payment.asset"),
            ReportLine(status=Line.VERIFIED, text="Verified.", evidence_ids=("MADE-UP",),
                       finding_code="payment.asset"),
        ], result)
        assert outcome.rejected

    def test_empty_report_is_accepted_but_says_nothing(self):
        outcome = validate_report([], wrong_asset_result())
        assert outcome.accepted and outcome.lines == []


class TestFindingCodeIsRequiredForFacts:
    """The hole the first run of this suite exposed.

    A transaction hash is cited by several findings at once (status, confirmations, asset,
    amount...). Matching support on a shared evidence ID alone therefore let a model claim
    anything it liked about a transaction and find spurious backing from an unrelated VERIFIED
    finding. A fact line must now name the check it rests on.
    """

    def test_verified_citing_only_the_tx_hash_is_not_supported(self):
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The invoiced asset arrived as expected.",
            evidence_ids=(TX,))], wrong_asset_result(), allow_downgrade=False)
        assert outcome.rejected
        assert "names no deterministic check" in outcome.violations[0].message

    def test_naming_a_check_that_did_not_pass_is_not_support(self):
        """payment.asset was a CONFLICT here, so it cannot back a VERIFIED line."""
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The asset matched.", evidence_ids=(TX,),
            finding_code="payment.asset")], wrong_asset_result(), allow_downgrade=False)
        assert outcome.rejected
        assert "payment.asset" in outcome.violations[0].message

    def test_naming_a_nonexistent_check_is_not_support(self):
        outcome = validate_report([ReportLine(
            status=Line.CONFLICT, text="Something was wrong.", evidence_ids=(TX,),
            finding_code="payment.invented_check")], wrong_asset_result(),
            allow_downgrade=False)
        assert outcome.rejected

    def test_misleading_text_over_a_real_pass_is_accepted_and_this_is_a_known_limit(self):
        """tx.status DID pass, but it says nothing about the asset."""
        result = wrong_asset_result()
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The invoiced asset arrived as expected.",
            evidence_ids=(TX,), finding_code="tx.status")], result, allow_downgrade=False)
        # tx.status is VERIFIED and cites TX, so this line IS formally supported -- but the
        # text misdescribes it. The validator cannot read intent; what it guarantees is that the
        # named check exists, passed, and cites this evidence. Narrowing further would require
        # semantic judgement, which is explicitly not this layer's job.
        assert outcome.accepted
        assert outcome.lines[0].finding_code == "tx.status"

    def test_a_correctly_attributed_pass_is_accepted(self):
        result = wrong_asset_result()
        status_finding = next(f for f in result.by_status(Status.VERIFIED)
                              if f.code == "tx.status")
        outcome = validate_report([ReportLine(
            status=Line.VERIFIED, text="The transaction succeeded on chain 137.",
            evidence_ids=status_finding.evidence_ids, finding_code="tx.status")], result)
        assert outcome.accepted and outcome.downgraded == 0

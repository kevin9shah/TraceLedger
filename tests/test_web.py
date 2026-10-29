"""Dashboard tests, including the constraints that exist because of measurements.

The dictation constraint (RISKS.md S15) is the one most likely to be broken by a well-meaning
later change, so it is asserted rather than left as a comment: the review form must carry no
JavaScript at all.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from traceledger.store import REVIEW_ACTIONS, Store, StoreError
from traceledger.web.app import create_app

USDT = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"
OUR_TX = "0x5db5918a22234617ca5892e90ad3ec401c2f03bd0555ad23f47d5ce6ef9dd911"


@pytest.fixture
def app(tmp_path):
    application = create_app(db_path=tmp_path / "test.sqlite")
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def store(app):
    return app.config["TL_STORE"]


def seeded_case(store: Store) -> str:
    case_id = store.create_case(
        title="Supplier says they paid", tx_hash=OUR_TX,
        payload={"facts": {"block_number": 96374131, "confirmations": 70, "chain_id": 137},
                 "token": {"address": USDT, "symbol": "USDT0", "decimals": 6},
                 "invoice": {}, "payment_request": None, "approved": []})
    store.save_findings(case_id, [
        {"code": "payment.asset", "status": "CONFLICT",
         "summary": "Wrong asset: records name 0x3c499c…, chain transferred 0xc2132d…",
         "evidence_ids": [OUR_TX, "INV-R1"], "detail": {}},
        {"code": "tx.status", "status": "VERIFIED",
         "summary": "Transaction succeeded in block 96374131.",
         "evidence_ids": [OUR_TX], "detail": {}},
        {"code": "payment.amount", "status": "MISSING",
         "summary": "No transfer of the invoiced token, so the amount cannot be compared.",
         "evidence_ids": [], "detail": {}},
    ])
    return case_id


class TestPages:
    def test_index_loads(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"Open a case from a transaction hash" in r.data

    def test_healthz_reports_the_chain(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200 and r.json["chain_id"] == 137

    def test_unknown_case_is_404(self, client):
        assert client.get("/case/CASE-NOPE").status_code == 404

    def test_read_only_promise_is_on_every_page(self, client, store):
        case_id = seeded_case(store)
        for path in ("/", f"/case/{case_id}", "/audit"):
            assert b"never moves funds" in client.get(path).data

    def test_synthetic_data_is_disclosed(self, client):
        assert b"synthetic" in client.get("/").data


class TestCaseView:
    def test_findings_are_shown_with_status_and_evidence(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        assert "payment.asset" in body and "CONFLICT" in body
        assert OUR_TX[:22] in body

    def test_conflicts_are_listed_before_verified(self, client, store):
        """A reviewer should see what disagrees before what agrees."""
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        assert body.index("payment.asset") < body.index("tx.status")

    def test_symbol_is_labelled_as_read_from_the_contract(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        assert "USDT0" in body and "read from the contract" in body

    def test_missing_finding_says_nothing_to_cite_rather_than_looking_verified(self, client, store):
        case_id = seeded_case(store)
        assert b"nothing to cite" in client.get(f"/case/{case_id}").data


class TestDictationConstraint:
    """RISKS.md S15 / D13: Wispr Flow inserts text by synthesising a paste, so any handler that
    intercepts paste or rewrites a field would break dictation while typing still worked."""

    def test_the_review_page_contains_no_javascript_at_all(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        assert "<script" not in body.lower()

    def test_no_inline_event_handlers(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode().lower()
        for handler in ("onpaste=", "oninput=", "onkeydown=", "onkeypress=", "onblur=",
                        "onchange=", "onsubmit="):
            assert handler not in body

    def test_rationale_is_a_large_textarea(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        assert re.search(r'<textarea[^>]*id="rationale"', body)

    def test_the_new_case_form_has_no_javascript_either(self, client):
        assert "<script" not in client.get("/").data.decode().lower()


class TestReviewActions:
    def test_all_four_actions_are_offered(self, client, store):
        case_id = seeded_case(store)
        body = client.get(f"/case/{case_id}").data.decode()
        for action in REVIEW_ACTIONS:
            assert f'value="{action}"' in body
        assert len(REVIEW_ACTIONS) == 4

    @pytest.mark.parametrize("action", REVIEW_ACTIONS)
    def test_each_action_is_recorded(self, client, store, action):
        case_id = seeded_case(store)
        r = client.post(f"/case/{case_id}/review",
                        data={"action": action, "rationale": "checked the contract addresses",
                              "actor": "kevin"})
        assert r.status_code == 302
        trail = store.audit_trail(case_id)
        assert trail[-1].action == action and trail[-1].actor == "kevin"

    def test_a_decision_without_a_rationale_is_refused(self, client, store):
        case_id = seeded_case(store)
        r = client.post(f"/case/{case_id}/review",
                        data={"action": "confirm", "rationale": "   ", "actor": "kevin"})
        assert r.status_code == 400
        assert b"rationale is required" in r.data
        assert store.audit_trail(case_id) == []

    def test_an_unknown_action_is_refused(self, client, store):
        case_id = seeded_case(store)
        r = client.post(f"/case/{case_id}/review",
                        data={"action": "close_quietly", "rationale": "because", "actor": "k"})
        assert r.status_code == 400
        assert store.audit_trail(case_id) == []

    def test_the_log_is_append_only(self, client, store):
        """A second decision adds an entry; it never replaces the first."""
        case_id = seeded_case(store)
        for action, why in (("request_evidence", "need the payer's wallet history"),
                            ("confirm", "payer confirmed the wrong asset was sent")):
            client.post(f"/case/{case_id}/review",
                        data={"action": action, "rationale": why, "actor": "kevin"})
        trail = store.audit_trail(case_id)
        assert len(trail) == 2
        assert [e.action for e in trail] == ["request_evidence", "confirm"]
        assert trail[0].rationale != trail[1].rationale

    def test_the_decision_context_records_what_was_shown(self, client, store):
        case_id = seeded_case(store)
        client.post(f"/case/{case_id}/review",
                    data={"action": "confirm", "rationale": "ok", "actor": "k"})
        entry = store.audit_trail(case_id)[-1]
        assert "payment.asset" in entry.context["findings_shown"]


class TestLanguage:
    def test_no_fraud_verdicts_anywhere_in_the_ui(self, client, store):
        case_id = seeded_case(store)
        for path in ("/", f"/case/{case_id}", "/audit"):
            body = client.get(path).data.decode().lower()
            for banned in ("fraud", "scam", "theft", "stolen"):
                assert banned not in body, (path, banned)

    def test_the_audit_log_is_not_called_immutable_or_tamper_proof(self, client, store):
        """P10/G10: append-only is claimed; tamper-proof and immutable are not."""
        seeded_case(store)
        body = re.sub(r"\s+", " ", client.get("/audit").data.decode().lower())
        assert "not tamper-proof" in body
        assert "immutable" not in body

    def test_findings_are_not_presented_as_a_verdict(self, client):
        # Whitespace is collapsed because the banner is line-wrapped in the template.
        body = re.sub(r"\s+", " ", client.get("/").data.decode().lower())
        assert "not a verdict" in body


class TestNewCaseValidation:
    def test_a_malformed_hash_is_reported_not_crashed(self, client):
        r = client.post("/case/new", data={
            "tx_hash": "not-a-hash", "invoice_token": USDT, "amount": "1.00"})
        assert r.status_code == 400
        assert b"Nothing was recorded" in r.data

    def test_a_malformed_token_address_is_reported(self, client):
        r = client.post("/case/new", data={
            "tx_hash": OUR_TX, "invoice_token": "0xdeadbeef", "amount": "1.00"})
        assert r.status_code == 400

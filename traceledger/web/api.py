"""JSON API for the React frontend.

The frontend was built separately and expects `/api/*`; the Flask app already served
server-rendered HTML. Rather than discard either, both are mounted on the same app and share one
store, one verifier and one configuration -- so the two interfaces can never disagree about a
case (the duplication is recorded in RISKS.md P19).

Every endpoint is read-only with respect to money and ledgers (G1). The only writes are case
metadata and the append-only audit log.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from ..chain.rpc import EvmRpc, RpcError
from ..chain.tokens import TokenMetadataError, read_token_metadata
from ..chain.transfers import TransactionNotFound, fetch_transaction_facts
from ..records import ApprovedAddress, Invoice, PaymentRequest, RecordError
from ..store import REVIEW_ACTIONS, StoreError
from ..verify import Status, verify_payment_case

ROOT = Path(__file__).resolve().parent.parent.parent
api = Blueprint("api", __name__, url_prefix="/api")

DISCLAIMER = ("Read-only: never moves funds and never edits ledgers. Business records are "
              "synthetic; chain facts are read from a live node. Findings are evidence for a "
              "human decision, not a verdict.")

STATUS_ORDER = {Status.CONFLICT: 0, Status.MISSING: 1, Status.NEXT_STEP: 2, Status.VERIFIED: 3}


def _cfg():
    return current_app.config["TL_CFG"]


def _store():
    return current_app.config["TL_STORE"]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


@api.get("/status")
def status():
    cfg = _cfg()
    registry = _load_json(ROOT / "data" / "token_registry.json") or {}
    return jsonify({
        "chain_name": cfg.chain_name,
        "chain_id": cfg.chain_id,
        "rpc_url": cfg.rpc_url,
        "tokens": registry.get("tokens", {}),
        "cases_count": len(_store().list_cases()),
        "audit_count": len(_store().audit_trail()),
        # The real list, not a guess. CP9 requires exactly these four.
        "review_actions": list(REVIEW_ACTIONS),
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "disclaimer": DISCLAIMER,
    })


@api.get("/cases")
def cases():
    return jsonify(_store().list_cases())


@api.get("/case/<case_id>")
def case_detail(case_id: str):
    store = _store()
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": f"no such case: {case_id}"}), 404
    findings = store.get_findings(case_id)
    # Conflicts first: a reviewer should see what disagrees before what agrees.
    findings.sort(key=lambda f: STATUS_ORDER.get(Status(f["status"]), 9))
    return jsonify({
        **{k: v for k, v in case.items()},
        "findings": findings,
        "report": store.get_report(case_id),
        "audit": [e.as_dict() for e in store.audit_trail(case_id)],
        "counts": {
            "conflict": sum(1 for f in findings if f["status"] == "CONFLICT"),
            "missing": sum(1 for f in findings if f["status"] == "MISSING"),
            "verified": sum(1 for f in findings if f["status"] == "VERIFIED"),
        },
    })


@api.post("/case/new")
def new_case():
    """Open a case from a transaction hash. The live-fire demo path (D17)."""
    body = request.get_json(silent=True) or {}
    tx_hash = str(body.get("tx_hash") or "").strip()
    invoice_token = str(body.get("invoice_token") or "").strip()
    amount = str(body.get("amount") or "").strip()
    destination = str(body.get("destination") or "").strip()
    approved = body.get("approved") or []
    if isinstance(approved, str):
        approved = [a.strip() for a in approved.split(",") if a.strip()]
    title = str(body.get("title") or "").strip() or f"Case for {tx_hash[:12]}…"

    if not tx_hash or not invoice_token or not amount:
        return jsonify({"error": "tx_hash, invoice_token and amount are required"}), 400

    cfg = _cfg()
    rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
    try:
        facts = fetch_transaction_facts(rpc, tx_hash)
        token_meta = read_token_metadata(rpc, invoice_token)
    except (TransactionNotFound, RpcError, TokenMetadataError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        invoice = Invoice.from_dict({
            "record_id": "INV-R1", "invoice_id": title[:40] or "INV-1",
            "counterparty": body.get("counterparty") or "(not stated)",
            "amount": amount, "token_contract": token_meta.address,
            "memo": body.get("memo") or "", "simulated": True})
        payment_request = None
        if destination:
            payment_request = PaymentRequest.from_dict({
                "record_id": "PR-R1", "request_id": "PR-1",
                "invoice_id": invoice.invoice_id, "expected_destination": destination,
                "amount": amount, "token_contract": token_meta.address, "simulated": True})
        approved_records = [
            ApprovedAddress.from_dict({"record_id": f"APP-{i+1}", "address": a,
                                       "approved_for": invoice.counterparty})
            for i, a in enumerate(approved)]
    except RecordError as exc:
        return jsonify({"error": str(exc)}), 400

    result = verify_payment_case(
        facts=facts, invoice=invoice, token_meta=token_meta,
        payment_request=payment_request, approved=approved_records)

    store = _store()
    case_id = store.create_case(
        title=title, tx_hash=facts.tx_hash,
        payload={"facts": facts.as_dict(), "token": token_meta.as_dict(),
                 "invoice": invoice.raw,
                 "payment_request": payment_request.raw if payment_request else None,
                 "approved": [a.raw for a in approved_records]})
    store.save_findings(case_id, [f.as_dict() for f in result.findings])

    # The LLM narrative is optional: if it fails, the deterministic findings stand (D38).
    try:
        from ..llm.investigate import investigate
        from ..llm.provider import LLMError, provider_from_config
        try:
            investigation = investigate(provider_from_config(cfg), result, invoice,
                                        payment_request)
            store.save_report(case_id, investigation.as_dict())
        except LLMError as exc:
            store.save_report(case_id, {
                "summary": "The narrative layer was unavailable; the findings above stand.",
                "llm_error": str(exc), "validation": {"lines": [], "violations": []},
                "hypotheses": [], "next_steps": []})
    except Exception as exc:  # noqa: BLE001 - never let drafting break case creation
        store.save_report(case_id, {
            "summary": "The narrative layer was unavailable; the findings above stand.",
            "llm_error": f"{type(exc).__name__}: {exc}",
            "validation": {"lines": [], "violations": []},
            "hypotheses": [], "next_steps": []})

    return jsonify({"case_id": case_id, "conflict_count": len(result.conflicts)}), 201


@api.post("/case/<case_id>/review")
def review(case_id: str):
    body = request.get_json(silent=True) or {}
    try:
        entry = _store().record_review(
            case_id,
            actor=str(body.get("actor") or "").strip() or "unnamed reviewer",
            action=str(body.get("action") or "").strip(),
            rationale=str(body.get("rationale") or ""),
            context={"findings_shown": [f["code"] for f in _store().get_findings(case_id)]})
    except StoreError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(entry.as_dict()), 201


@api.get("/audit")
def audit():
    return jsonify([e.as_dict() for e in _store().audit_trail()])


@api.get("/presets")
def presets():
    """Ready-made demo cases built from REAL transactions, so a demo needs no typing.

    Sourced from data/real_txs.json, so the hashes are ones we actually sent or observed --
    never invented (G3).
    """
    real = _load_json(ROOT / "data" / "real_txs.json") or {}
    usdc = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
    ours = [t for t in real.get("transfers", []) if t.get("origin") == "cake_wallet_demo"]
    out = []
    for t in ours:
        human = f"{int(t['amount_base_units']) / 10**6:.6f}".rstrip("0").rstrip(".")
        out.append({
            "id": f"wrong-asset-{t['tx_hash'][:10]}",
            "label": f"Invoice says USDC, {human} USDT arrived",
            "note": ("Our own Cake Wallet transfer. The invoice names the USDC contract; the "
                     "chain delivered the Tether contract, which reports symbol 'USDT0'."),
            "expected": "CONFLICT — wrong asset",
            "tx_hash": t["tx_hash"], "invoice_token": usdc, "amount": human,
            "destination": t["recipient"], "approved": [t["recipient"]],
            "counterparty": "Meridian Freight",
        })
        out.append({
            "id": f"clean-{t['tx_hash'][:10]}",
            "label": f"Invoice says USDT, {human} USDT arrived",
            "note": "The same transfer matched against an invoice naming the token that arrived.",
            "expected": "VERIFIED — no conflict",
            "tx_hash": t["tx_hash"], "invoice_token": t["token_contract"], "amount": human,
            "destination": t["recipient"], "approved": [t["recipient"]],
            "counterparty": "Meridian Freight",
        })
    return jsonify(out)


@api.get("/benchmark")
def benchmark():
    three = _load_json(ROOT / "benchmark" / "three_way.json")
    if three is None:
        return jsonify({"results": {}, "cases": [], "note": "no benchmark run recorded yet"})
    scores = three.get("scores", {})
    by_case: dict[str, dict] = {}
    for system, score in scores.items():
        for entry in score.get("per_case", []):
            row = by_case.setdefault(entry["case_id"], {"case_id": entry["case_id"],
                                                        "expected": entry["expected"]})
            row[system] = entry["got"]
            row[f"{system}_correct"] = entry["outcome_correct"]
    return jsonify({
        "model": three.get("model"),
        "case_count": three.get("case_count"),
        "results": scores,
        "cases": [by_case[k] for k in sorted(by_case)],
        # Stated in the payload so any UI rendering this cannot present it as a clean win.
        "caveat": ("Preliminary, 25 synthetic cases. TraceLedger's score is circular: the cases "
                   "and the system share an author (RISKS.md P16). The meaningful comparison is "
                   "of failure modes, especially the false-resolution rate."),
    })


@api.get("/graph/root_cause")
def graph_root_cause():
    """Shared-root-cause clusters. Served from the recorded run so the demo needs no workspace."""
    gvs = _load_json(ROOT / "benchmark" / "graph_vs_sql.json")
    if gvs is None:
        return jsonify({"flagged_invoices": 0, "clusters": []})
    rows = (gvs.get("tigergraph") or gvs.get("sql") or {}).get("results", [])
    source = "tigergraph" if gvs.get("tigergraph") else "sql"
    clusters = []
    for row in rows:
        ids = row.get("invoice_ids") or ""
        clusters.append({
            "cause": row.get("import_event_id"),
            "batch": row.get("source_file"),
            "invoices": [i for i in ids.split(",") if i],
            "count": row.get("affected_invoices"),
        })
    agreement = gvs.get("agreement") or {}
    return jsonify({
        "flagged_invoices": gvs.get("flagged_invoice_total", 0),
        "clusters": clusters,
        "source": source,
        "comparison": {
            "identical_results": agreement.get("identical_results"),
            "sql_median_ms": agreement.get("sql_median_ms"),
            "graph_median_ms": agreement.get("graph_median_ms"),
            "note": ("Both engines return identical results and SQL is faster at this scale; "
                     "the graph is not claimed to be faster (RISKS.md P7)."),
        },
    })

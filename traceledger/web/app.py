"""TraceLedger dashboard: create a case, read the evidence, record a decision.

Read-only with respect to money and ledgers (G1). The only thing this app writes is case
metadata and the audit log.

Three constraints shape the UI, each from a measurement rather than a preference:

* **Dictation must keep working** (RISKS.md S15, D13). Wispr Flow inserts text by putting it on
  the clipboard and synthesising a paste, so the review form must never intercept paste, never
  rewrite a field's value as it changes, and never clear a field on blur. There is no JavaScript
  on the review form at all, which is the most reliable way to honour that.
* **A case can be opened from a pasted transaction hash** (D17), because that is the live demo.
* **Findings are shown with their status and the evidence they cite** (G4), never as prose that
  mixes verified facts with hypotheses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

from traceledger.chain.rpc import EvmRpc, RpcError
from traceledger.chain.tokens import TokenMetadataError, read_token_metadata
from traceledger.chain.transfers import TransactionNotFound, fetch_transaction_facts
from traceledger.config import ConfigError, load_config
from traceledger.records import ApprovedAddress, Invoice, PaymentRequest, RecordError
from traceledger.store import REVIEW_ACTIONS, Store, StoreError
from traceledger.verify import Status, verify_payment_case

STATUS_ORDER = {Status.CONFLICT: 0, Status.MISSING: 1, Status.NEXT_STEP: 2, Status.VERIFIED: 3}


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    try:
        cfg = load_config()
    except ConfigError as exc:  # pragma: no cover - surfaced at startup
        raise SystemExit(f"CONFIG ERROR: {exc}")
    app.config["TL_CFG"] = cfg
    store = Store(db_path or cfg.db_path)
    app.config["TL_STORE"] = store

    @app.template_filter("ts")
    def _ts(value: float) -> str:
        import datetime as _dt
        return _dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")

    @app.route("/")
    def index():
        return render_template("index.html", cases=store.list_cases(),
                               chain_name=cfg.chain_name, chain_id=cfg.chain_id,
                               audit=store.audit_trail()[:8])

    @app.route("/case/new", methods=["POST"])
    def new_case():
        """Open a case from a pasted transaction hash. This is the live-fire demo path (D17)."""
        tx_hash = (request.form.get("tx_hash") or "").strip()
        invoice_token = (request.form.get("invoice_token") or "").strip()
        amount = (request.form.get("amount") or "").strip()
        destination = (request.form.get("destination") or "").strip()
        approved = [a.strip() for a in (request.form.get("approved") or "").split(",") if a.strip()]
        title = (request.form.get("title") or "").strip() or f"Case for {tx_hash[:12]}…"

        rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
        try:
            facts = fetch_transaction_facts(rpc, tx_hash)
            token_meta = read_token_metadata(rpc, invoice_token)
        except (TransactionNotFound, RpcError, TokenMetadataError, ValueError) as exc:
            return render_template("error.html", title="Could not read the chain",
                                   message=str(exc)), 400

        try:
            invoice = Invoice.from_dict({
                "record_id": "INV-R1", "invoice_id": title[:40] or "INV-1",
                "counterparty": request.form.get("counterparty") or "(not stated)",
                "amount": amount, "token_contract": token_meta.address,
                "memo": request.form.get("memo") or "", "simulated": True})
            payment_request = None
            if destination:
                payment_request = PaymentRequest.from_dict({
                    "record_id": "PR-R1", "request_id": "PR-1",
                    "invoice_id": invoice.invoice_id,
                    "expected_destination": destination, "amount": amount,
                    "token_contract": token_meta.address, "simulated": True})
            approved_records = [
                ApprovedAddress.from_dict({"record_id": f"APP-{i+1}", "address": a,
                                           "approved_for": invoice.counterparty})
                for i, a in enumerate(approved)]
        except RecordError as exc:
            return render_template("error.html", title="Record problem", message=str(exc)), 400

        result = verify_payment_case(
            facts=facts, invoice=invoice, token_meta=token_meta,
            payment_request=payment_request, approved=approved_records)

        case_id = store.create_case(
            title=title, tx_hash=facts.tx_hash,
            payload={"facts": facts.as_dict(), "token": token_meta.as_dict(),
                     "invoice": invoice.raw,
                     "payment_request": payment_request.raw if payment_request else None,
                     "approved": [a.raw for a in approved_records]})
        store.save_findings(case_id, [f.as_dict() for f in result.findings])
        return redirect(url_for("case_detail", case_id=case_id))

    @app.route("/case/<case_id>")
    def case_detail(case_id: str):
        case = store.get_case(case_id)
        if case is None:
            abort(404)
        findings = store.get_findings(case_id)
        # Conflicts first: a reviewer should see what disagrees before what agrees.
        findings.sort(key=lambda f: STATUS_ORDER.get(Status(f["status"]), 9))
        return render_template(
            "case.html", case=case, findings=findings,
            report=store.get_report(case_id),
            audit=store.audit_trail(case_id), actions=REVIEW_ACTIONS,
            conflict_count=sum(1 for f in findings if f["status"] == "CONFLICT"),
            missing_count=sum(1 for f in findings if f["status"] == "MISSING"))

    @app.route("/case/<case_id>/review", methods=["POST"])
    def review(case_id: str):
        action = (request.form.get("action") or "").strip()
        rationale = request.form.get("rationale") or ""
        actor = (request.form.get("actor") or "").strip() or "unnamed reviewer"
        try:
            store.record_review(
                case_id, actor=actor, action=action, rationale=rationale,
                context={"findings_shown": [f["code"] for f in store.get_findings(case_id)]})
        except StoreError as exc:
            return render_template("error.html", title="Decision not recorded",
                                   message=str(exc),
                                   back=url_for("case_detail", case_id=case_id)), 400
        return redirect(url_for("case_detail", case_id=case_id))

    @app.route("/audit")
    def audit():
        return render_template("audit.html", audit=store.audit_trail())

    from traceledger.web.api import api as api_blueprint
    app.register_blueprint(api_blueprint)

    @app.route("/healthz")
    def healthz():
        return {"ok": True, "chain_id": cfg.chain_id, "cases": len(store.list_cases())}

    # --- JSON API routes for React Frontend ---

    @app.route("/api/status")
    def api_status():
        tokens_file = ROOT / "data" / "token_registry.json"
        tokens = {}
        if tokens_file.exists():
            try:
                tokens = json.loads(tokens_file.read_text()).get("tokens", {})
            except Exception:
                pass
        return jsonify({
            "chain_name": cfg.chain_name,
            "chain_id": cfg.chain_id,
            "rpc_url": cfg.rpc_url,
            "tokens": tokens,
            "cases_count": len(store.list_cases()),
            "audit_count": len(store.audit_trail()),
            "review_actions": list(REVIEW_ACTIONS),
            "disclaimer": "Read-only: never moves funds and never edits ledgers. Business records are synthetic; chain facts read from live node."
        })

    @app.route("/api/cases")
    def api_cases():
        cases = store.list_cases()
        return jsonify([c.as_dict() for c in cases])

    @app.route("/api/case/<case_id>")
    def api_case_detail(case_id: str):
        case = store.get_case(case_id)
        if case is None:
            return jsonify({"error": "Case not found"}), 404
        findings = store.get_findings(case_id)
        findings.sort(key=lambda f: STATUS_ORDER.get(Status(f["status"]), 9))
        report = store.get_report(case_id)
        audit = [a.as_dict() for a in store.audit_trail(case_id)]
        return jsonify({
            "case": case.as_dict(),
            "findings": findings,
            "report": report,
            "audit": audit,
            "conflict_count": sum(1 for f in findings if f["status"] == "CONFLICT"),
            "missing_count": sum(1 for f in findings if f["status"] == "MISSING"),
            "verified_count": sum(1 for f in findings if f["status"] == "VERIFIED"),
            "actions": list(REVIEW_ACTIONS)
        })

    @app.route("/api/case/new", methods=["POST"])
    def api_new_case():
        data = request.get_json(silent=True) or request.form
        tx_hash = (data.get("tx_hash") or "").strip()
        invoice_token = (data.get("invoice_token") or "").strip()
        amount = (data.get("amount") or "").strip()
        destination = (data.get("destination") or "").strip()
        approved_raw = data.get("approved") or ""
        if isinstance(approved_raw, list):
            approved = [str(a).strip() for a in approved_raw if str(a).strip()]
        else:
            approved = [a.strip() for a in str(approved_raw).split(",") if a.strip()]
        title = (data.get("title") or "").strip() or f"Case for {tx_hash[:12]}…"
        memo = data.get("memo") or ""
        counterparty = data.get("counterparty") or "(not stated)"

        rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
        try:
            facts = fetch_transaction_facts(rpc, tx_hash)
            token_meta = read_token_metadata(rpc, invoice_token)
        except (TransactionNotFound, RpcError, TokenMetadataError, ValueError) as exc:
            return jsonify({"error": str(exc), "stage": "chain_read"}), 400

        try:
            invoice = Invoice.from_dict({
                "record_id": "INV-R1", "invoice_id": title[:40] or "INV-1",
                "counterparty": counterparty,
                "amount": amount, "token_contract": token_meta.address,
                "memo": memo, "simulated": True})
            payment_request = None
            if destination:
                payment_request = PaymentRequest.from_dict({
                    "record_id": "PR-R1", "request_id": "PR-1",
                    "invoice_id": invoice.invoice_id,
                    "expected_destination": destination, "amount": amount,
                    "token_contract": token_meta.address, "simulated": True})
            approved_records = [
                ApprovedAddress.from_dict({"record_id": f"APP-{i+1}", "address": a,
                                           "approved_for": invoice.counterparty})
                for i, a in enumerate(approved)]
        except RecordError as exc:
            return jsonify({"error": str(exc), "stage": "record_validation"}), 400

        result = verify_payment_case(
            facts=facts, invoice=invoice, token_meta=token_meta,
            payment_request=payment_request, approved=approved_records)

        case_id = store.create_case(
            title=title, tx_hash=facts.tx_hash,
            payload={"facts": facts.as_dict(), "token": token_meta.as_dict(),
                     "invoice": invoice.raw,
                     "payment_request": payment_request.raw if payment_request else None,
                     "approved": [a.raw for a in approved_records]})
        store.save_findings(case_id, [f.as_dict() for f in result.findings])
        return jsonify({"case_id": case_id, "findings_count": len(result.findings)}), 201

    @app.route("/api/case/<case_id>/review", methods=["POST"])
    def api_review(case_id: str):
        data = request.get_json(silent=True) or request.form
        action = (data.get("action") or "").strip()
        rationale = (data.get("rationale") or "").strip()
        actor = (data.get("actor") or "").strip() or "unnamed reviewer"
        try:
            entry = store.record_review(
                case_id, actor=actor, action=action, rationale=rationale,
                context={"findings_shown": [f["code"] for f in store.get_findings(case_id)]})
        except StoreError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "entry": entry.as_dict()})

    @app.route("/api/audit")
    def api_audit():
        trail = store.audit_trail()
        return jsonify([a.as_dict() for a in trail])

    @app.route("/api/presets")
    def api_presets():
        real_txs_file = ROOT / "data" / "real_txs.json"
        presets = []
        if real_txs_file.exists():
            try:
                data = json.loads(real_txs_file.read_text())
                presets = data.get("transfers", [])
            except Exception:
                pass
        return jsonify(presets)

    @app.route("/api/benchmark")
    def api_benchmark():
        results_file = ROOT / "benchmark" / "three_way.json"
        if not results_file.exists():
            results_file = ROOT / "benchmark" / "results.json"
        data = {}
        if results_file.exists():
            try:
                data = json.loads(results_file.read_text())
            except Exception:
                pass
        cases_file = ROOT / "benchmark" / "cases.json"
        cases = []
        if cases_file.exists():
            try:
                cases = json.loads(cases_file.read_text())
            except Exception:
                pass
        return jsonify({"results": data, "cases": cases})

    @app.route("/api/graph/root_cause")
    def api_graph_root_cause():
        graph_file = ROOT / "benchmark" / "graph_vs_sql.json"
        data = {}
        if graph_file.exists():
            try:
                data = json.loads(graph_file.read_text())
            except Exception:
                pass
        return jsonify(data)

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        @app.route("/app")
        @app.route("/app/")
        @app.route("/app/<path:path>")
        def serve_react(path=""):
            target = frontend_dist / path
            if path and target.exists() and target.is_file():
                return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, "index.html")

    return app


if __name__ == "__main__":
    create_app().run(debug=False, port=5001)

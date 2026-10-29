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
from traceledger.chain.transfers import (
    TRANSFER_TOPIC,
    TransactionNotFound,
    fetch_transaction_facts,
)
from traceledger.config import ConfigError, load_config
from traceledger.records import ApprovedAddress, Invoice, PaymentRequest, RecordError
from traceledger.store import REVIEW_ACTIONS, Store, StoreError
from traceledger.verify import Status, verify_payment_case

# The demo wallet transfers are sent to. Overridable per request via ?address=
DEMO_DESTINATION = "0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e"

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
        # store.list_cases() returns plain dicts; calling .as_dict() on them raised a 500
        # and the frontend silently rendered an empty list.
        return jsonify(store.list_cases())

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
            "case": case,   # already a plain dict from the store
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

        # Draft the narrative, then gate it through the validator. The findings above already
        # stand on their own: if the model is unavailable or misbehaves, the case is still
        # complete and the report records why it is absent (D38). A model outage degrades the
        # prose, never the facts.
        llm_error = None
        try:
            from traceledger.llm.investigate import investigate
            from traceledger.llm.provider import LLMError, provider_from_config
            investigation = investigate(
                provider_from_config(cfg), result, invoice, payment_request,
                case_ledger_entries if "case_ledger_entries" in dir() else ())
            store.save_report(case_id, investigation.as_dict())
        except Exception as exc:  # noqa: BLE001 - drafting must never break case creation
            llm_error = f"{type(exc).__name__}: {exc}"
            store.save_report(case_id, {
                "summary": ("The narrative layer was unavailable, so this case has verified "
                            "findings but no drafted report. The findings stand on their own."),
                "llm_error": llm_error,
                "validation": {"accepted": True, "downgraded": 0, "lines": [], "violations": []},
                "hypotheses": [], "next_steps": [],
            })

        return jsonify({
            "case_id": case_id,
            "findings_count": len(result.findings),
            "conflict_count": len(result.conflicts),
            "report_available": llm_error is None,
            "llm_error": llm_error,
        }), 201

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
        """Ready-made demo cases, in the shape the UI's preset chips use.

        Keys match the frontend's local PRESETS constant (`name`, `hash`, `token`, `amount`,
        `dest`, `desc`) so the hardcoded list can be replaced by live data.

        Built from data/real_txs.json, so every hash is one actually sent or observed -- never
        invented (G3). Each transfer yields two presets: one matched against an invoice naming a
        DIFFERENT token (the wrong-asset demo) and one against the token that actually arrived
        (the clean control), because a demo that only ever shows conflicts invites the question
        "does it ever say yes?".
        """
        real_file = ROOT / "data" / "real_txs.json"
        if not real_file.exists():
            return jsonify([])
        try:
            real = json.loads(real_file.read_text())
        except (OSError, json.JSONDecodeError):
            return jsonify([])

        usdc_native = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
        out = []
        for t in real.get("transfers", []):
            if t.get("origin") != "cake_wallet_demo":
                continue
            base = int(t["amount_base_units"])
            human = f"{base / 10 ** 6:.6f}".rstrip("0").rstrip(".")
            label = cfg.token_contracts.get(t["token_contract"], "token")
            out.append({
                "name": f"Wrong asset: {human} {label} vs USDC invoice",
                "hash": t["tx_hash"],
                "token": usdc_native,
                "amount": human,
                "dest": t["recipient"],
                "desc": (f"Real Cake Wallet transfer, block {t['block_number']}. The invoice "
                         f"names the USDC contract; the chain delivered {t['token_contract']}, "
                         "which reports symbol 'USDT0'."),
                "expected": "CONFLICT - wrong asset",
            })
            out.append({
                "name": f"Clean: {human} {label} vs matching invoice",
                "hash": t["tx_hash"],
                "token": t["token_contract"],
                "amount": human,
                "dest": t["recipient"],
                "desc": (f"The same real transfer, block {t['block_number']}, matched against an "
                         "invoice naming the token that actually arrived."),
                "expected": "VERIFIED - no conflict",
            })
        return jsonify(out)

    @app.route("/api/benchmark")
    def api_benchmark():
        """Real benchmark output, shaped as the rows the UI renders.

        Columns use the short keys the frontend already expects (`id`, `title`, `exp`, `rules`,
        `llm`, `tl`, `rulesMiss`, `llmMiss`) so the view can read live data instead of a
        hardcoded table. Titles come from benchmark/cases.json and outcomes from the recorded
        run, so nothing on screen is invented (G3, G10).
        """
        three_file = ROOT / "benchmark" / "three_way.json"
        cases_file = ROOT / "benchmark" / "cases.json"
        if not three_file.exists():
            return jsonify({"rows": [], "results": {}, "cases": [],
                            "note": "no benchmark run recorded yet"}), 200
        three = json.loads(three_file.read_text())
        titles = {}
        if cases_file.exists():
            titles = {c["case_id"]: c["title"]
                      for c in json.loads(cases_file.read_text()).get("cases", [])}
        scores = three.get("scores", {})
        key = {"rules_only": "rules", "plain_llm": "llm", "traceledger": "tl"}
        rows: dict[str, dict] = {}
        for system, score in scores.items():
            short = key.get(system, system)
            for entry in score.get("per_case", []):
                cid = entry["case_id"]
                row = rows.setdefault(cid, {"id": cid, "title": titles.get(cid, cid),
                                            "exp": entry["expected"]})
                row[short] = entry["got"]
                if entry["outcome_correct"] is False:
                    row[f"{short}Miss"] = True
        return jsonify({
            "model": three.get("model"),
            "case_count": three.get("case_count"),
            "rows": [rows[k] for k in sorted(rows)],
            "results": scores,
            "cases": [rows[k] for k in sorted(rows)],   # alias, same data
            "caveat": ("Preliminary, 25 synthetic cases. TraceLedger's score is circular: the "
                       "cases and the system share an author (RISKS.md P16). What is meaningful "
                       "is the comparison of failure modes, especially false-resolution rate."),
        })

    @app.route("/api/graph/root_cause")
    def api_graph_root_cause():
        """Shared-root-cause clusters from the recorded TigerGraph run.

        `live` is False and `source` names where the numbers came from, because the workspace is
        normally stopped (it bills hourly) and presenting recorded output as a live query would
        be a false claim (G3, G10).
        """
        graph_file = ROOT / "benchmark" / "graph_vs_sql.json"
        if not graph_file.exists():
            return jsonify({"live": False, "clusters": [], "flagged_invoices": 0,
                            "note": "no graph run recorded yet"}), 200
        try:
            data = json.loads(graph_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"could not read the recorded graph run: {exc}"}), 500

        engine = "tigergraph" if data.get("tigergraph") else "sql"
        rows = (data.get(engine) or {}).get("results", [])
        clusters = []
        for row in rows:
            ids = [i for i in (row.get("invoice_ids") or "").split(",") if i]
            clusters.append({
                "batchId": row.get("import_event_id"),
                "cause": row.get("import_event_id"),
                "batch": row.get("source_file"),
                "invoices": ids,
                "count": row.get("affected_invoices", len(ids)),
            })
        agreement = data.get("agreement") or {}
        return jsonify({
            "live": False,
            "source": engine,
            "recorded_note": ("These clusters are from a recorded run against the TigerGraph "
                              "workspace, not a live query. The workspace is normally stopped."),
            "flagged_invoices": data.get("flagged_invoice_total", 0),
            "clusters": clusters,
            "comparison": {
                "identical_results": agreement.get("identical_results"),
                "sql_median_ms": agreement.get("sql_median_ms"),
                "graph_median_ms": agreement.get("graph_median_ms"),
                "sql_faster_by": agreement.get("sql_faster_by"),
                "note": ("Both engines return identical results and SQL is faster at this scale. "
                         "The graph is not claimed to be faster (RISKS.md P7)."),
            },
        })

    @app.route("/api/watch/latest")
    def api_watch_latest():
        """Find the most recent token transfer to a watched address.

        The live-fire demo path (D17): a transfer is sent from a phone, and this finds it. Copying
        a 66-character hash off a phone screen in front of an audience is the single most likely
        thing to go wrong on stage, so it is removed from the demo entirely.

        Scans only the configured token contracts (G7) over a bounded block window, newest first.
        Read-only: `eth_getLogs` cannot move anything.
        """
        address = (request.args.get("address") or DEMO_DESTINATION).strip().lower()
        try:
            window = min(max(int(request.args.get("blocks", 900)), 1), 5000)
        except ValueError:
            return jsonify({"error": "blocks must be an integer"}), 400
        if not (address.startswith("0x") and len(address) == 42):
            return jsonify({"error": f"not a 20-byte address: {address}"}), 400

        rpc = EvmRpc(cfg.rpc_url, cfg.chain_id)
        try:
            head = int(rpc.call("eth_blockNumber"), 16)
            topic_to = "0x" + "0" * 24 + address[2:]
            found = []
            for contract in cfg.token_contracts:
                logs = rpc.call("eth_getLogs", [{
                    "fromBlock": hex(max(head - window, 0)), "toBlock": "latest",
                    "address": contract,
                    "topics": [TRANSFER_TOPIC, None, topic_to],
                }]) or []
                for log in logs:
                    value = int(log["data"], 16) if log["data"] not in ("", "0x") else 0
                    found.append({
                        "tx_hash": log["transactionHash"],
                        "block_number": int(log["blockNumber"], 16),
                        "token_contract": contract,
                        "token_label": cfg.token_contracts[contract],
                        "amount_base_units": str(value),
                        "amount": f"{value / 10 ** 6:.6f}".rstrip("0").rstrip("."),
                        "sender": "0x" + log["topics"][1][-40:],
                        "recipient": address,
                        "log_index": int(log["logIndex"], 16),
                    })
        except (RpcError, ValueError, KeyError) as exc:
            return jsonify({"error": str(exc)}), 502

        found.sort(key=lambda t: (t["block_number"], t["log_index"]), reverse=True)
        return jsonify({
            "watched_address": address,
            "scanned_blocks": window,
            "head_block": head,
            "transfer_count": len(found),
            "latest": found[0] if found else None,
            "transfers": found[:10],
            "note": ("No transfer found in the scanned window." if not found else
                     f"{len(found)} transfer(s) found; newest first."),
        })

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

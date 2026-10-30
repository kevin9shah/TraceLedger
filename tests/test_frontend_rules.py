"""Tests for frontend requirements and constraints (Tracing Vellum).

Enforces:
1. No <script> tags or inline event handlers on form pages (Wispr Flow dictation constraint).
2. Prohibited words absent across all rendered pages.
3. Benchmark caveat present wherever benchmark figures appear.
4. No hardcoded arrays of case titles or figures in templates.
"""
from __future__ import annotations

import re
from pathlib import Path
import pytest

from traceledger.web.app import create_app
from traceledger.store import Store

BANNED_WORDS = [
    "fraud", "scam", "theft", "stolen", "immutable",
    "guaranteed", "is final", "irreversible"
]

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

def test_no_scripts_or_inline_handlers_on_form_pages(client, store):
    case_id = store.create_case(
        "Test Case",
        payload={"facts": {"block_number": 123, "confirmations": 15, "chain_id": 137},
                 "token": {"address": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", "symbol": "USDC", "decimals": 6},
                 "invoice": {}, "payment_request": None, "approved": []}
    )
    for path in ("/", f"/case/{case_id}"):
        html = client.get(path).data.decode().lower()
        assert "<script" not in html, f"Found <script> on {path}"
        for handler in ("onpaste=", "oninput=", "onkeydown=", "onkeypress=", "onblur=", "onchange=", "onsubmit="):
            assert handler not in html, f"Found inline handler {handler} on {path}"

def test_banned_words_absent_from_rendered_pages(client, store):
    case_id = store.create_case(
        "Test Case",
        payload={"facts": {"block_number": 123, "confirmations": 15, "chain_id": 137},
                 "token": {"address": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", "symbol": "USDC", "decimals": 6},
                 "invoice": {}, "payment_request": None, "approved": []}
    )
    for path in ("/", f"/case/{case_id}", "/audit"):
        html = client.get(path).data.decode().lower()
        for word in BANNED_WORDS:
            assert word not in html, f"Found banned word '{word}' on {path}"
        # "tamper-proof" is only allowed with "not " preceding it
        cleaned = html.replace("not tamper-proof", "")
        assert "tamper-proof" not in cleaned, f"Found positive 'tamper-proof' claim on {path}"

def test_caveat_present_with_benchmark_numbers(client):
    body = client.get("/").data.decode()
    if "100%" in body or "rules_only" in body or "scripts/demo.py" in body:
        assert "Preliminary, 25 synthetic cases. Not evidence of production performance." in body

def test_no_hardcoded_arrays_in_templates():
    template_dir = Path("traceledger/web/templates")
    for f in template_dir.rglob("*.html"):
        content = f.read_text(encoding="utf-8")
        assert "const cases =" not in content
        assert "let cases =" not in content
        assert "var cases =" not in content
        assert "cases = [" not in content


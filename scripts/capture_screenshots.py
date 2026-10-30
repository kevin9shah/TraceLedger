import subprocess
import time
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from traceledger.web.app import create_app
from traceledger.store import Store
SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

OUR_TX = "0x5db5918a22234617ca5892e90ad3ec401c2f03bd0555ad23f47d5ce6ef9dd911"
USDT = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"

def seed_db(db_path):
    store = Store(db_path)
    cid = store.create_case(
        "Demo Payout: USDT delivered vs USDC invoice",
        payload={
            "facts": {"block_number": 96374131, "confirmations": 2048, "chain_id": 137},
            "token": {"address": USDT, "symbol": "USDT0", "decimals": 6},
            "invoice": {"invoice_id": "INV-OCT-84", "memo": "Standard supplier disbursement"},
            "payment_request": {"expected_destination": "0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e"},
            "approved": [{"address": "0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e"}]
        },
        tx_hash=OUR_TX,
        case_id="CASE-DEMO-01"
    )
    store.save_findings(cid, [
        {"code": "payment.asset", "status": "CONFLICT",
         "summary": "Wrong asset: records specify 0x3c499c… (USDC), chain transferred 0xc2132d… (USDT0)",
         "evidence_ids": [OUR_TX, "INV-OCT-84"], "detail": {}},
        {"code": "tx.status", "status": "VERIFIED",
         "summary": "Transaction succeeded in block 96374131.",
         "evidence_ids": [OUR_TX], "detail": {}},
        {"code": "destination.approval", "status": "VERIFIED",
         "summary": "Destination is on the approved list.",
         "evidence_ids": ["0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e"], "detail": {}},
        {"code": "payment.amount", "status": "MISSING",
         "summary": "No transfer of invoiced token, amount cannot be compared.",
         "evidence_ids": [], "detail": {}},
    ])
    store.save_report(cid, {
        "summary": "The transfer succeeded on Polygon mainnet, but the counterparty sent Tether instead of USD Coin.",
        "hypotheses": [
            {"explanation": "Counterparty selected Polygon Tether in Cake Wallet by mistake.",
             "would_be_confirmed_by": "Counterparty wallet transfer receipt",
             "would_be_ruled_out_by": "Proof of USDC bridge deposit"}
        ],
        "next_steps": ["Request payer statement on whether USDT was intentional."],
        "validation": {"violations": []}
    })
    store.record_review(cid, actor="kevin", action="request_evidence", rationale="Asset mismatch on chain. Asking payer for clarification.")
    store.close()

def run_server(app):
    app.run(port=5005, debug=False, use_reloader=False)

def capture(url, out_path, width, height):
    cmd = [
        EDGE_PATH,
        "--headless",
        "--disable-gpu",
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        url
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Captured: {out_path.name} ({width}x{height})")

def main():
    db_file = ROOT / "data" / "screenshot_test.sqlite"
    if db_file.exists():
        db_file.unlink()
    seed_db(db_file)

    app = create_app(db_path=db_file)
    t = threading.Thread(target=run_server, args=(app,), daemon=True)
    t.start()
    time.sleep(1.5)

    base_url = "http://127.0.0.1:5005"
    pages = [
        ("/", "landing"),
        ("/case/CASE-DEMO-01", "case_detail"),
        ("/audit", "audit")
    ]

    for path, name in pages:
        url = base_url + path
        capture(url, SCREENSHOT_DIR / f"desktop_{name}_1440.png", 1440, 960)
        capture(url, SCREENSHOT_DIR / f"mobile_{name}_390.png", 390, 844)

    print("All screenshots captured successfully.")

if __name__ == "__main__":
    main()

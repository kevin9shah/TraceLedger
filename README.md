# TraceLedger

**TraceLedger helps operations teams establish what the evidence proves, what remains unknown, and what to do next.**

It investigates unresolved stablecoin payment exceptions — cases where blockchain facts (what was
transferred) disagree with business records (invoices, payment requests, ledgers, logs). It verifies
what code can verify, links the evidence, tests competing explanations, and produces a report that
separates **verified facts, conflicts, unproven hypotheses, missing evidence and next steps**.
A human makes the final decision.

**TraceLedger is read-only. It never moves funds and never edits ledgers.**

## Status
Early build. **CP0 and CP1 complete** (2026-10-29); CP2 awaits real wallet transfers.
See `CHECKPOINTS.md` for what is actually done, with evidence beside each tick, and `PROGRESS.md`
for the running log including what failed. Benchmark numbers, when they exist, live in
`BENCHMARK_RESULTS.md` and are generated from real runs only — it is currently empty because no
benchmark has been run.

Verified so far, by code rather than assumption:
- Polygon PoS chain id 137 confirmed against a live RPC; token `decimals()` read from each contract.
- TigerGraph Savanna reachable (4.2.5) with a real GSQL statement executed.
- Dictation (Wispr Flow) accepted by the review fields, with the raw event log captured.
- 47 unit tests passing, including refusal of every write/signing RPC method.

## Scope (MVP)
- One EVM chain; USDC and USDT, identified by **contract address** (never by symbol).
- Three exception types: duplicate records, status conflict, destination/instruction conflict.
  Cross-token (wrong-asset) cases fall under these.
- Upload-based (CSV/JSON). No live enterprise connectors.
- Web dashboard: create case, view evidence, view report, reviewer actions.
- 25-case benchmark with separately stored ground truth; three systems compared.

## Limitations
- **Preliminary results on 25 synthetic cases. Not evidence of production performance.**
- Business records in this repo are synthetic. Any simulated record is labelled `"simulated": true`
  and shown as such in the UI.
- "Confirmed on-chain" is not "final" or "guaranteed" — issuers can freeze or blacklist balances.
- TraceLedger reports mismatches and risk indicators. It does not issue fraud verdicts.

## Setup
```bash
cp .env.example .env            # fill in; .env is gitignored, never commit it
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/verify_tokens.py   # verifies chain id + token contracts on-chain
.venv/bin/python scripts/tg_smoke.py        # verifies TigerGraph reachability
.venv/bin/python -m pytest -q
```
**`docs/setup_sponsors.md`** has the step-by-step for the parts a human must do (TigerGraph Savanna
workspace, dictation check, wallet transfers), including several places where the published vendor
docs are wrong.

Never put a private key or seed phrase anywhere in this project. Nothing here signs or sends
transactions, and `EvmRpc` refuses any RPC method outside a read-only allow-list.

## Repo map
| Path | What |
|---|---|
| `PROGRESS.md` | Running log: done / failed / next |
| `CHECKPOINTS.md` | Gates with exit criteria + evidence |
| `DECISIONS.md` | Design decisions and rejected alternatives |
| `RISKS.md` | Live risk register, incl. sponsor-tool issues |
| `BACKLOG.md` | Out-of-scope ideas (not built) |
| `BENCHMARK_RESULTS.md` | Real run results only (empty until a benchmark is run) |
| `docs/setup_sponsors.md` | Step-by-step for the human-only setup tasks |
| `traceledger/chain/` | Read-only RPC client and ERC-20 metadata reader |
| `scripts/` | `verify_tokens.py`, `tg_smoke.py` — smoke tests with real output |
| `ui/dictation_test.html` | Dictation harness; logs raw input events |

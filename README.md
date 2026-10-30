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

## The demo: live fire

The demo is not a recording and not a fixture. A member of the audience sends a real stablecoin
transfer from their own wallet on Polygon; TraceLedger ingests the transaction hash, reads the
transfer from mainnet, and renders the case while they watch. The invoice it is matched against
names a *different* token contract, so the system reports a **CONFLICT** and cites the contract
address and block it just read. Anyone in the room can verify it on a block explorer.

It works because of a fact that is true on Polygon today, not because of a rule written to fire on
a magic string: the canonical Tether contract `0xc2132d…` reports `symbol="USDT0"`, and two
distinct live contracts both report `symbol="USDC"` (native `0x3c499c…` and bridged `0x2791Bc…`).
Any reconciliation that matches assets by ticker is wrong on the largest stablecoin on that chain.
TraceLedger identifies tokens by contract address and reads `decimals()` from the contract.

Three further beats, each of which the audience can test rather than take on trust:

1. **The same case, same data, given to a plain LLM.** It answers confidently. The comparison is
   watched rather than claimed.
2. **The laptop is handed over.** Anyone may type whatever they like into an invoice memo field to
   try to force a "settled" verdict. Uploaded text is data, never instructions.
3. **It refuses.** On a genuinely under-determined case the answer is `UNRESOLVED`, together with
   the specific evidence that would settle it.

## Architecture

Layers, in the order they run. Each layer may only weaken the one above it, never override it.

1. **Deterministic verification (code, no LLM).** Transaction status, token contract, decimals,
   amount, destination, duplicate identifiers, arithmetic. Amounts are integer base units; no
   floating point, and the LLM never computes.
2. **Evidence retrieval and linking.** Relationships are built only when the basis is known;
   uncertain links are labelled `candidate`.
3. **Graph layer (TigerGraph).** Relationship queries and shared-root-cause grouping — many
   exceptions tracing back to one import batch. Benchmarked against the equivalent SQL at CP8, and
   reported honestly if SQL ties.
4. **LLM investigation (hosted API, constrained).** Proposes competing hypotheses, selects the next
   evidence to fetch, drafts the report. Never authoritative on chain facts.
5. **Independent validator (code).** Every cited evidence ID must exist and every number must match
   the deterministic layer. Failures are rejected and retried, or downgraded to `unproven`.
6. **Human review.** Decision and rationale recorded in an audit log.

Latency is measured at CP8 and reported from real runs. No performance figures appear in this
README until they have been measured.

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

## Deployment

TraceLedger supports both unified monolith and decoupled multi-cloud deployment:
- **Backend (Render)**: Defined in [
ender.yaml](render.yaml) & [wsgi.py](wsgi.py). Powered by Gunicorn, read-only Polygon Bor RPC, and append-only SQLite evidence store.
- **Frontend (Vercel)**: Dedicated client workspace in [rontend/](frontend/) with edge API proxying via [ercel.json](vercel.json).
- See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the step-by-step setup and environment configuration.

## Repo map
| Path | What |
|---|---|
| rontend/ | Standalone Vercel frontend (Parallax Tracing Vellum + Case Docket) |
| 
ender.yaml | Render Web Service Blueprint spec |
| ercel.json | Vercel Edge proxy configuration and headers |
| wsgi.py | Production WSGI entrypoint for Gunicorn |
| DEPLOYMENT.md | Cloud deployment guide for Render and Vercel |
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

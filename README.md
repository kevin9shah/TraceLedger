# TraceLedger

**TraceLedger helps operations teams establish what the evidence proves, what remains unknown, and what to do next.**

It investigates unresolved stablecoin payment exceptions — cases where blockchain facts (what was
transferred) disagree with business records (invoices, payment requests, ledgers, logs). It verifies
what code can verify, links the evidence, tests competing explanations, and produces a report that
separates **verified facts, conflicts, unproven hypotheses, missing evidence and next steps**.
A human makes the final decision.

**TraceLedger is read-only. It never moves funds and never edits ledgers.**

## Status
Early build. See `CHECKPOINTS.md` for what is actually done and `PROGRESS.md` for the running log.
Benchmark numbers, when they exist, live in `BENCHMARK_RESULTS.md` and are generated from real runs.

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
cp .env.example .env   # fill in; .env is gitignored, never commit it
```
Never put a private key or seed phrase anywhere in this project.

## Repo map
| Path | What |
|---|---|
| `PROGRESS.md` | Running log: done / failed / next |
| `CHECKPOINTS.md` | Gates with exit criteria + evidence |
| `DECISIONS.md` | Design decisions and rejected alternatives |
| `RISKS.md` | Live risk register, incl. sponsor-tool issues |
| `BACKLOG.md` | Out-of-scope ideas (not built) |
| `BENCHMARK_RESULTS.md` | Real run results only |

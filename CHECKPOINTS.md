# CHECKPOINTS

Tick only when exit criteria are demonstrably met, with evidence recorded in the Evidence column
(command output path, test name, screenshot path). Do not skip or reorder.

| CP | Name | Exit criteria | Status | Evidence |
|---|---|---|---|---|
| CP0 | Repo + memory files | Six MD files exist, `.env.example`, `.gitignore` covers `.env`, README stub | DONE | `ls` output in PROGRESS.md 2026-10-29; `.gitignore:153` = `.env` |
| CP1 ★ | Sponsor smoke tests | TigerGraph instance reachable via `pyTigerGraph` with a trivial query; chain + tokens chosen; Cake Wallet check recorded; dictation works in a test textarea | **DONE** 2026-10-29 | all 6 sub-items evidenced in the CP1 breakdown below |
| CP2 | Data model + real tx capture | Schema documented; `data/real_txs.json` has ≥3 real hashes from Cake Wallet transfers (human-supplied); parser verified against them | TODO | — |
| CP3 | Deterministic verifier + tests | Verifies status, contract, decimals, amount, destination, duplicates; unit tests pass | TODO | — |
| CP4 ★ | Benchmark v1 | 25 synthetic cases + separate ground truth; schema validated; cross-token and tricky cases present; human reviews realism | TODO | — |
| CP5 | Rules-only baseline | Runs on all 25; scores recorded in `BENCHMARK_RESULTS.md` | TODO | — |
| CP6 | Graph layer | Data loaded into TigerGraph; ≥3 GSQL queries; root-cause query works; export saved to `graph/export/` | TODO | — |
| CP7 | LLM investigation + validator | Structured report with evidence IDs; validator rejects invalid citations; prompt-injection test passes | TODO | — |
| CP8 ★ | Three-way comparison | Rules vs plain LLM vs TraceLedger, all metrics, plus graph-vs-SQL; honest write-up of wins and failures | TODO | — |
| CP9 | Dashboard + review flow | Create case, view report, 4 reviewer actions, audit log, dictation-friendly UI | TODO | — |
| CP10 ★ | Demo + pitch readiness | Scripted 3-minute demo runs end to end; README, limitations slide, sponsor usage evidenced | TODO | — |

★ = stop for human check before proceeding.

## CP8 metrics to compute
Issue-identification accuracy · evidence support rate · unsupported-claim rate · evidence-reference validity ·
abstention quality · false-resolution rate · tool/query efficiency · reviewer time (only if actually timed).


## CP1 breakdown

| Item | Status | Evidence |
|---|---|---|
| Chain + tokens chosen | DONE | Polygon PoS, chain id **137 verified on-chain** at block 96347626 via `scripts/verify_tokens.py`. DECISIONS.md D3, D6, D7 |
| Token contracts verified on-chain (decimals + existence) | DONE | `data/token_registry.json`, generated from live reads. USDC `0x3c499c…` decimals=6; Tether `0xc2132d…` decimals=6 reporting `symbol="USDT0"`; bridged USDC `0x2791Bc…` decimals=6 |
| Read-only enforcement | DONE | `tests/test_token_math.py::TestReadOnly` — 28 tests pass (`.venv/bin/python -m pytest -q` → `28 passed in 0.11s`) |
| Cake Wallet check recorded | **DONE** | Fresh install; EVM chains offered: eth, bnb, base, arb, pol → Polygon chosen (D3). Candidate token contracts verified live on Polygon at block 96350969: USDC `0x3c499c…` (decimals 6), Tether `0xc2132d…` (decimals 6, reports `symbol="USDT0"`). The address Cake Wallet displayed was the wallet's **receive address**, not a token contract — `eth_getCode` returned `0x` (D14). Authoritative token identity is taken from the real transaction's `to` field at CP2, not from a UI label |
| TigerGraph reachable + trivial query | **DONE** | `scripts/tg_smoke.py` exit 0, 2026-10-29: Savanna workspace `traceledger-ws`, **TigerGraph 4.2.5**, secret auth, `echo: Hello GSQL`, 0 vertex types (empty graph as expected). Trivial GSQL executed: `USE GRAPH TraceLedger; LS` returned `Graph TraceLedger()` with empty Vertex/Edge Types, Jobs and Queries |
| Dictation in a test textarea | **DONE** | `ui/dictation_test.html`, 2026-10-29 23:54. Human dictated "Hello, Wispr Flow." via the Fn hotkey (Wispr Flow's default); `Wispr Flow.app` confirmed installed and running (`com.electron.wispr-flow`, 12 processes). Event log: `focus rationale` at 23:54:20.362 → `beforeinput inputType=insertFromPaste data="Hello, Wispr Flow. "` at 23:54:23.268 → `input` same, 19 chars. **Clipboard inserts = 1**, no typing in between. Human confirmed they did not press Cmd+V |

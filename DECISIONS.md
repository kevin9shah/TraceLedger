# DECISIONS

Non-trivial design choices, alternatives rejected, and why.

---

### D1 — Repo name vs product name
**2026-10-29.** Working directory is `LedgeTracer`; the product is **TraceLedger**. Keeping the directory
name as-is (renaming would break the existing git remote/paths for no benefit). All user-facing strings,
README and UI use "TraceLedger".
Rejected: renaming the folder.

### D2 — Memory files are the source of truth
**2026-10-29.** `PROGRESS.md` / `CHECKPOINTS.md` are re-read at the start of every session; checkpoint
status lives only in `CHECKPOINTS.md` (not in code comments or chat) so a fresh session can resume.

### D3 — Chain: Polygon PoS, tokens by contract address
**2026-10-29.** Cake Wallet (fresh install) offers EVM chains: eth, bnb, base, arb, pol (plus
non-EVM xmr/btc/sol/zec/trx/doge/bch/ltc/xno/dcr, all out of scope). Chose **Polygon PoS**: both
USDC and USDT are established there and a hand-sent real transfer costs a fraction of a cent, which
matters because a human sends every demo transfer.
Rejected: ETH mainnet (gas cost per transfer paid out of pocket); Base (USDT support least certain
of the five); arb/bnb (fine fallbacks, kept in RISKS.md as S2-fallback).
Consequence: `EVM_CHAIN_ID` must be asserted = 137 at startup (P6). Token identity comes from the
contract address Cake Wallet shows, verified against the chain (G7) — never from the symbol.

### D4 — Real transfers use tiny mainnet amounts
**2026-10-29.** No reliance on Cake Wallet exposing a testnet. Human sends ~1 USDC / ~1 USDT in
small transfers from their own wallet; TraceLedger receives only tx hashes and public addresses.
No code path in this repo signs or sends anything (G1), and no key material is ever requested (G2).

### D5 — LLM provider: Gemini, behind a provider interface
**2026-10-29.** Human has/wants Google AI Studio access. Default `LLM_MODEL=gemini-2.5-flash`,
configurable via `.env`. The CP7 investigation layer talks to a thin `LLMProvider` interface so
Anthropic or OpenAI can be substituted if the free tier throttles during the demo.
Open item: confirm the exact current Gemini model id against Google's docs at CP7 rather than
trusting a remembered string.

### D6 — Token symbols are display-only; the registry is built from the chain
**2026-10-29.** Verified against Polygon mainnet (chain id 137, block 96347626) via
`scripts/verify_tokens.py`. Two findings changed the design:

- `0xc2132d05d31c914a87c6611c10748aeb04b58e8f` — the contract Cake Wallet and every explorer
  treat as Polygon Tether — now reports `symbol="USDT0"`, `name="USDT0"` (the USDT0 / LayerZero
  OFT migration). A reconciler matching on the string `USDT` would fail to recognise its own
  canonical contract.
- `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` (native, "USD Coin") and
  `0x2791bca1f2de4661ed88a30c99a7a9449aa84174` (bridged, "USD Coin (PoS)") are two distinct live
  contracts that both report `symbol="USDC"`, both 6 decimals. Symbol alone cannot distinguish them.

Consequence: `TokenMetadata.symbol` is carried for display only and is never an input to any
identity or matching decision. `data/token_registry.json` is generated from on-chain reads and is
the single source of decimals (G7). Mismatch between the `.env` label and the on-chain symbol is
printed as an observation, never an error.

This also supplies a *real* lookalike/wrong-asset case for the benchmark (RISKS.md P9), replacing
what would otherwise have been an invented one.

### D7 — Public RPC endpoint choice
**2026-10-29.** `polygon-rpc.com` now returns `-32051 "API key disabled, tenant disabled"` for
keyless calls, so it is unusable. Verified working keyless: `polygon-bor-rpc.publicnode.com`,
`1rpc.io/matic`, `polygon.drpc.org`. Default is `polygon-bor-rpc.publicnode.com`; the other two are
drop-in fallbacks via `EVM_RPC_URL`. Every fact records its `rpc_url` and read time (P6).

### D8 — RPC method allow-list instead of a convention
**2026-10-29.** `EvmRpc.call()` refuses any method outside `READ_ONLY_METHODS` before touching the
network, so G1 is enforced by code rather than by discipline. `tests/test_token_math.py::TestReadOnly`
asserts that `eth_sendTransaction`, `eth_sendRawTransaction` and the signing methods raise and send
no request. Rejected: relying on "we just won't call those".

### D9 — TigerGraph: Savanna with free credits, no payment method, SQL path kept first-class
**2026-10-29.** Constraints from the human: **no spending**, and **no Docker**.

Options examined (verified against TigerGraph's own docs, not assumed):

| Option | Verdict |
|---|---|
| Cloud Classic free-tier cluster (what the brief assumed) | **Unavailable.** Free tier removed Nov 2024; Classic closed to new users; AWS end-of-life 30 Sep 2026, i.e. already passed |
| Community Edition (free forever, 300GB, single-server, full GSQL) | **Ruled out on hardware grounds** — see the re-examination below |
| Savanna free trial credits | **Chosen.** Credits valid one year; smallest workspace TG-00 is $1/hour *while running* |

Spend safety: TigerGraph's FAQ states that when free credits expire they stop and eventually
terminate the instance *"unless a payment method is added."* **No payment method will be added**,
so the worst case is the workspace stopping — never a charge. Operating rule: start the workspace
only while building or demoing, stop it immediately after.

Consequence for the architecture: the graph layer must not be a single point of failure. The SQL
(SQLite) implementation of root-cause grouping is built as a **first-class path**, not a stub —
which CP8's graph-vs-SQL comparison requires anyway. If Savanna is stopped or out of credits, the
demo runs on the SQL path and we **say so**; we never show cached graph output as if it were live
(G3, G10). Schema, GSQL queries and loading jobs are exported to `graph/export/` so the workspace
is rebuildable from scratch.

Rejected: claiming "TigerGraph Savanna" in the pitch if we end up demoing only the SQL path.
Whatever actually ran is what gets claimed.


### D10 — Community Edition re-examined once Docker became available, still rejected
**2026-10-29.** The human corrected the earlier constraint: Docker *is* usable. CE was therefore
re-examined rather than left closed on a stale assumption.

Functionally CE and a Savanna workspace are equivalent for this project: same engine, same GSQL,
same REST interface, same `pyTigerGraph`. Our schema, loading jobs and queries are portable between
them unchanged. Only operations differ (connection string, cost, clustering, enterprise ACLs).

Rejected anyway, on hardware:
- TigerGraph's Docker guide: *"TigerGraph on Docker is not supported for ARM processors, including
  M1 Macs."* This host is `arm64`.
- Host has **8 GB RAM** — TigerGraph's stated *minimum*, against 24 GB recommended — and the demo
  must also run a browser, the Flask app and the dev tooling at the same time.
- `--platform linux/amd64` would emulate x86 for an explicitly unsupported configuration on minimum
  memory. Not a dependency a demo should rest on.

Savanna (D9) therefore stands. Because the GSQL is portable, nothing in the build is locked to
Savanna: if this ever runs on an x86 box with more memory, CE is a drop-in alternative needing only
a different connection in `.env`.


### D11 — Savanna cost controls: auto-suspend on, HA off, TG-00, no solutions
**2026-10-29.** Verified against Savanna's pricing and workspace-settings docs.

Billable dimensions and how each is handled:

| Dimension | Rate | Our setting |
|---|---|---|
| Compute | $1/hr at TG-00, billed by **hours in use** | TG-00; workspace stopped between sessions. A stopped workspace bills no compute |
| Storage | $0.025–0.044 per GB-month, billed separately from compute | Our graph is a few MB — effectively zero |
| High Availability | 1.95x–2.8x multiplier | **Off** |
| Add-ons (e.g. Insights) | 10% of base compute | **None** |
| Solutions / starter kits | loads sample schema + data | **None** — "start from scratch". A starter kit's vertex and edge types would pollute the TraceLedger graph and distort the CP8 graph-vs-SQL comparison |

**Auto-suspend enabled** at the shortest interval offered (Advanced Settings), so a forgotten
workspace cannot drain credits. Two documented behaviours worth remembering:
- Activity detection covers installing queries, running queries, loading jobs and schema changes.
  It does **not** count console configuration or Controller API calls, so a workspace can suspend
  while the console is open.
- **Auto-resume does not apply to this workspace.** Measured 2026-10-29 against the stopped
  workspace: every endpoint returns HTTP 500 with `"Auto start is not enabled for this workspace"`.
  So stopping it in the console is a hard cost stop and no script here can wake it. `tg_smoke.py`
  detects this body and reports "the workspace is STOPPED" with exit code 3, rather than implying a
  bad host or secret.


### D12 — TG_HOST is normalised rather than specified precisely
**2026-10-29.** pyTigerGraph 2.0.5's constructor raises
`Invalid URL scheme. Supported schemes are http and https.` on a bare hostname, yet TigerGraph's
own pyTigerGraph 1.6 docs show exactly that bare form (`host="r_alliance.i.tgcloud.io"`). Both
spellings will therefore be pasted into `.env` by anyone following either source — including the
instructions this project first gave the human, which were wrong.

`config.normalise_tg_host()` accepts either, strips trailing slashes, and supplies the scheme:
`https://` for a remote host (Savanna is HTTPS-only), `http://` for localhost or 127.0.0.1.

Rejected: documenting the exact required format and relying on it being followed. The failure mode
was an opaque exception during setup, which is the worst possible moment for one.


### D13 — Wispr Flow inserts via the clipboard; the review UI must not fight that
**2026-10-29.** Measured, not assumed. Dictating into `ui/dictation_test.html` with Wispr Flow's
Fn hotkey produced:

```
23:54:20.362  focus         rationale
23:54:23.236  keydown       rationale  key="v"
23:54:23.268  beforeinput   rationale  inputType=insertFromPaste data="Hello, Wispr Flow. "
23:54:23.274  input         rationale  inputType=insertFromPaste  len=19
```

So Wispr Flow transcribes, puts the text on the clipboard, and synthesises a paste. At the DOM level
this is **indistinguishable from a human Cmd+V** — the distinction came from the human confirming
they did not press it. (macOS's own dictation inserts directly, so `insertFromPaste` is itself a
signature of the clipboard-based tool.)

Binding constraints for the CP9 review UI:
- **Never intercept or cancel paste.** No `onpaste` handler that calls `preventDefault`, and no
  "paste not allowed" behaviour on the rationale or question fields. That would break dictation
  entirely while leaving typing fine, so it would pass a keyboard-only test.
- **No input sanitising that rewrites the field on change.** A controlled input that reformats or
  filters on every change can drop or mangle a large clipboard insert arriving in one event.
- **Do not clear or re-render fields on blur.** Wispr Flow's insertion can coincide with focus
  changes; the log shows a `blur` immediately after.
- The first version of the test harness excluded every `insertFromPaste` event as "just a paste",
  which would have made the test **unpassable for the very tool CP1 names**. Clipboard inserts are
  now counted separately and reported rather than silently discarded.


### D14 — Token identity comes from the transaction, not from the wallet UI
**2026-10-29.** Asked for the USDC and USDT contract addresses as Cake Wallet displays them, the
human supplied `0x3004cEe4065774e4BCE4EC3aC5C56f3FE61D45b3` for **both**. Verified on Polygon:
`eth_getCode` returns `0x` and the POL balance is zero — it holds no contract code, so it cannot be
a token contract. It is the wallet's own **receive address**, which Cake Wallet shows per-wallet
rather than per-token.

This is the hazard G7 exists for, and it was caught by code rather than by inspection: a
symbol-and-UI-label pipeline would have accepted the string and then mis-verified every payment
against it.

Decision: **do not source token identity from a wallet UI at all.** For each real transfer at CP2,
the authoritative contract is the transaction's `to` address, cross-checked against the on-chain
`decimals()` and against the ERC-20 `Transfer` event in the receipt. The `.env` allow-list is then
set from what the chain says, and `data/token_registry.json` is regenerated from live reads.

Consequence: CP1's Cake Wallet item is satisfied by the verified candidate contracts plus the chain
choice; which of Polygon's two `symbol="USDC"` contracts is in play is determined at CP2 from the
actual transfer. This is stronger evidence than a screenshot of a wallet screen, so nothing is lost.


### D15 — Credential hygiene is enforced by tests, not by discipline
**2026-10-29.** A live TigerGraph secret reached `origin/main` because it was pasted into the
committed `.env.example` instead of the gitignored `.env`. The two files differ by one character of
filename, which makes this an easy and repeatable mistake.

`tests/test_no_secrets_committed.py` now asserts, on every test run:
- `TG_SECRET`, `TG_PASSWORD`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY` and `TG_HOST` are **blank** in
  `.env.example` (host included, because it is instance-specific and identifies the workspace);
- no `PRIVATE_KEY`/`SEED_PHRASE`/`MNEMONIC` assignment and no 32-byte hex value appears there;
- `.env` is **not** tracked by git, and `.gitignore` covers it.

Rejected: a note in the README asking people to be careful. The first occurrence of this mistake
happened while the rule was already written down in G2 and in `.env.example`'s own header comment.
A test fails; a comment does not.


### D16 — Tiered architecture kept; its unmeasured performance claims removed
**2026-10-29, revised the same day.**

The tiered design stands and is the right shape: deterministic verification first, graph for
relationships, LLM last and never authoritative. That ordering is in the architecture section of
the README and in the layer list in this file.

**What was removed, and why.** An earlier version of D16 and of the README asserted specific
latency figures (`L1 <0.1 ms`, `L2 <5 ms`, `L3 100–500 ms`, `L4 1.5–3 s`), claimed TigerGraph
"pointer-chasing across vertices in RAM", compared TraceLedger against "three other hackathon teams
building generic reconciliation tools", and used phrasing like "zero-latency mathematical
certainty" and "beating naive 3-second LLM guesses". All of it was removed:

- **Nothing had been measured.** `BENCHMARK_RESULTS.md` is empty. G10 forbids claiming latency,
  accuracy or a graph advantage that has not been measured.
- **One figure was contradicted by our own data.** `curl` probes against the Savanna workspace
  returned in **1.47 s and 1.94 s** (recorded 2026-10-29). Savanna is managed cloud reached over the
  network, so a user-visible 5 ms graph query is not achievable in this deployment. A judge timing
  the demo could disprove it on stage.
- **The competitor claim was unverifiable** and not something this project knows.
- **Several capabilities named were out of scope** — multi-hop split payments, intermediary pool
  routes, fee deductions, entity clustering. The MVP covers three exception types (G12). The
  pre-flight gateway idea is in `BACKLOG.md`, which is the right place for it.

Latency is a legitimate thing to measure, so **memory and query latency stay in the CP8 metric
list**. The numbers get written into `BENCHMARK_RESULTS.md` from real runs, and may then be used in
the pitch. Measured 1.8 s stated plainly is stronger than a claimed 5 ms that collapses under one
question.

### D17 — The demo is live fire, and that choice drives the build
**2026-10-29.** The demo's organising principle: **every claim on screen must be verifiable by the
audience during the presentation.** A member of the audience sends a real stablecoin transfer from
their own wallet on Polygon; TraceLedger ingests the hash, reads the transfer from mainnet, and
renders the case live. The matched invoice names a different token contract, so the verdict is
`CONFLICT`, citing the contract address and block just read. Anyone can check it on a block explorer.

This is only possible because the ambiguity is **real on Polygon today** (D6): the canonical Tether
contract reports `symbol="USDT0"`, and two distinct live contracts both report `symbol="USDC"`. The
catch must come from reading the contract, never from a rule that fires on a magic string — if it
ever did, the demo would be theatre and would deserve to fail.

Then three beats the audience can test rather than trust:
1. The same case and data given to a plain LLM, which answers confidently. The comparison is watched,
   not asserted (this is the CP8 baseline, reused on stage).
2. The laptop is handed over: anyone may type anything into an invoice memo field to try to force a
   "settled" verdict. Uploaded text is data, never instructions (G9).
3. A genuinely under-determined case returns `UNRESOLVED` plus the specific evidence that would
   settle it (G5).

**What this changes in the plan:**

| CP | Addition |
|---|---|
| CP3 | Verifier must take a transaction hash and produce a cited verdict with no LLM involved — the live path depends only on this layer |
| CP4 | Benchmark cases designed around the *real* contract ambiguity, including both `symbol="USDC"` contracts and the `USDT0` naming. Also an under-determined case for the refusal beat |
| CP7 | Refusal path and injection quarantine are demo beats, not just tests. The plain-LLM baseline must be runnable side by side on the same input |
| CP9 | UI must ingest a case from a pasted transaction hash and render it live |
| CP10 | Scripted demo plus a **labelled replay fallback** |

**Accepted risks, with mitigations, in `RISKS.md` (S17–S20):** venue network, the Savanna workspace
being stopped, real funds and confirmation timing, and a live transfer simply failing. The fallback
is a replay from a stored hash, displayed as **REPLAY** on screen and never presented as live (G3).



### D18 — A transaction has *many* transfers; a payment is identified by token + recipient
**2026-10-29.** Discovered while verifying the parser against real Polygon transactions, not
designed in advance:

| Transaction | Logs | Transfer events | Distinct tokens |
|---|---|---|---|
| `0x5e857c89…` | 2 | 1 | 1 (USDT) |
| `0x7858560a…` | 15 | 4 | **2 — USDT *and* USDC** |
| `0x094b7da1…` | 41 | **19** | **4** |

So "the amount this transaction paid" is not a well-defined quantity, and `0x7858560a…` is a real
on-chain case where a claim of "this transaction paid USDC" is simultaneously true and false
depending on which leg is read. Routed swaps, intermediaries and fee legs are ordinary, not edge
cases.

Consequences, all enforced in code:
- `TransactionFacts.transfers` is a **tuple of every Transfer event**, in log order. The parser never
  collapses a transaction to one amount.
- A settling payment is selected by **token contract + recipient**. `transfers_of()` alone is
  demonstrably insufficient — `0x7858560a…` has two USDT transfers.
- When more than one transfer still matches, the **ambiguity is reported**, never resolved by taking
  the first (G5).
- ERC-721 `Transfer` (same signature, third indexed topic) is skipped rather than read as an amount,
  which would invent a transfer that never happened (G3).
- A malformed Transfer log **raises** instead of being skipped, because silently dropping a transfer
  understates what moved.

### D19 — `origin` separates our transfers from transactions we merely observed
**2026-10-29.** The wallet is unfunded, so the parser was verified against **public** mainnet
transactions. That is legitimate evidence — real chain data, captured reproducibly — but it is not
the same as a transfer we sent, and conflating the two would be the sort of quiet overstatement G3
and G10 exist to prevent.

Every entry in `data/real_txs.json` therefore carries `origin`: `cake_wallet_demo` for transfers we
sent, `public_mainnet` for ones we observed. The file also carries
`cake_wallet_demo_transfers_outstanding: true` until the former exist. CP2 is marked **PARTIAL**
rather than done, because its exit criterion names human-supplied transfers specifically.


### D20 — Verifier design: evidence is structural, absence is never a pass
**2026-10-29.** `traceledger/verify.py`. Choices worth recording because each rules out a class of
quiet failure:

- **`Finding.__post_init__` raises if a `VERIFIED` or `CONFLICT` has no evidence IDs.** G4 is
  enforced by the type, so an uncited claim cannot be constructed, let alone reported. Tested.
- **A skipped check becomes a `MISSING` finding, never silence.** If the payment request is absent,
  the destination check does not quietly vanish — it reports that it could not run and what is
  needed, which then generates a `NEXT_STEP`. An absent check must never read as a pass (G5).
- **`verify_payment_case` raises if `token_meta.address != invoice.token_contract`.** Comparing
  amounts scaled by the wrong token's decimals would produce confident nonsense, so it is a
  programming error rather than a finding (G7).
- **Amounts are integer base units end to end**, converted from decimal strings using the
  contract's own `decimals()`. `records.py` *rejects a float* at parse time rather than accepting
  and rounding it. Excess precision is a `CONFLICT`, never a silent truncation (G8).
- **Ambiguity is reported, not resolved.** Where several transfers of the same token reach the same
  recipient, `check_transfer_ambiguity` emits `MISSING` listing every candidate's log index and
  value. Taking the first match would be arbitrary and confident (D18, G5).
- **Wording is enforced by test.** `destination.approval` says "risk indicator, not a verdict about
  intent"; tests assert that no finding summary contains "fraud", "scam", "theft" or "stolen" (G6),
  and that the confirmation line avoids "final" and "guaranteed" (P10).
- **Serialisation is float-free.** `TransferEvent.value` and every base-unit figure serialise as
  **strings**, so no JSON consumer can turn a 6-decimal amount into a float. Tested by walking the
  serialised structure for any `float`.
- **`check_confirmations` defaults to 12** and reports `MISSING` below the threshold rather than
  `VERIFIED`. Depth is a parameter so the benchmark can vary it.


### D21 — Failed transactions need the receipt, not the logs
**2026-10-29.** Found while harvesting real transactions for the benchmark. The first harvest
returned **zero** reverted transactions, which was not bad luck: `eth_getLogs` can only return
transactions that *emitted* events, and a reverted transfer emits none. Failed payments are
structurally invisible to log scanning.

This matters because "the ledger says paid but nothing moved" is one of the three MVP exception
types. A reconciler built on log scanning would never see it — the transaction simply would not
appear, which reads as "no payment found" rather than "the payment failed".

So `scripts/harvest_txs.py` additionally walks block transaction lists and checks receipt
`status`, and the verifier checks `status` before anything else. Verified against a real reverted
Polygon transaction (`0xe00f5243…`, block 96371332, gasUsed 96064, zero Transfer logs): the sender
paid gas and moved nothing.

### D22 — A finding must say *what* is confirmed
**2026-10-29.** Testing the reverted transaction produced this on screen:

```
CONFLICT   Transaction reverted (status 0); no tokens were transferred by it.
VERIFIED   Confirmed on-chain at 52 confirmations (threshold 12).
```

Both lines are true — the *failure* is confirmed — but "Confirmed on-chain" beside a failed payment
invites exactly the wrong reading, and on a demo screen a judge would see "VERIFIED confirmed"
next to a payment that never happened.

`check_confirmations` now names the outcome: *"The FAILURE of this transaction is confirmed
on-chain at N confirmations"*, with `detail.confirms_outcome` set to `success` or `failure`. Every
confirmation line also carries *"Confirmed is not the same as final: issuers can freeze or
blacklist balances"* (P10).

A test that had banned the substring "final" outright was tightened rather than deleted: it now
asserts the summary never *claims* finality (`"is final"`, `"irreversible"`, `"cannot be
reversed"`, `"guaranteed"`) while requiring the disclaimer to be present. Banning the word was the
wrong test; banning the claim is the right one.

### D23 — Two further failure modes a naive checker passes
**2026-10-29.** Added because both look like successful payments:

- **`payment.direction`** — the party expected to *receive* appears only as a *sender* of that
  token. The money left them. Returns no finding when the party is uninvolved, so ordinary cases
  stay quiet.
- **`payment.zero_value`** — a succeeded transaction whose matching transfers all move **zero**
  base units. A zero-value Transfer is a real event: token matches, destination matches, status is
  success, and nothing was received. `test_zero_value_still_looks_like_a_transfer_to_a_naive_check`
  asserts that `check_asset` and `check_destination` both return VERIFIED on it, which is why the
  dedicated check has to exist.


### D24 — Benchmark: real chain facts, synthetic business records, labels in a separate file
**2026-10-29.** `benchmark/` holds three files with deliberately different trust levels:

| File | Contents | Read by a system under test? |
|---|---|---|
| `cases.json` | 25 cases, inputs only | yes |
| `ground_truth.json` | expected outcome, issue types, required citations | **never** |
| `chain_facts.json` | 8 **real** Polygon transactions, captured | yes (as evidence) |

**Chain facts are real; only business records are synthetic** (G3, P4). A benchmark whose on-chain
data was invented to suit the cases proves nothing, so every `chain_evidence` entry carries
`origin: "public_mainnet"` and `simulated: false`, while every business record carries
`simulated: true`. The captured transactions cover each shape that matters: single transfer,
multi-transfer, two tokens in one transaction, 19 transfers across 4 tokens, two reverted
transactions, a **genuine zero-value transfer**, and a 9-transfer transaction with real settlement
ambiguity.

**Hygiene is enforced by tests, not by intention** (`tests/test_benchmark.py`, 30 tests):
- **No label leakage.** The inputs file is walked recursively for any of 13 label-ish keys, and
  asserted not to contain the outcome words. The two files are asserted to be disjoint.
- **No near-duplicate templates.** Each case is reduced to a structural signature (record counts,
  tokens, amounts, transaction hashes) and no two may match. **This test caught four real
  collisions** — `C11~C12`, `C06~C14`, `C14~C15`, then `C02~C11` — which were fixed by giving the
  cases genuinely different evidence, not by renaming fields. `C02~C11` was the substantive one:
  C11's "unresolved" outcome came only from a run-time confirmation threshold, so its inputs were
  identical to a clean control. It now uses a different transaction entirely.
- **Degenerate scoring is blocked.** 4 `no_conflict` controls mean a system that always answers
  CONFLICT cannot score well, and 4 `unresolved` cases mean over-answering is detectable (G5).
  No outcome may exceed 18 of 25.
- **Records must parse under the production model**, and no amount may be a JSON float (G8).

Labels are described in the file itself as *"preliminary labels over 25 synthetic business-record
scenarios; not evidence of production performance"* (P12).

Cases are written as situations an operator would recognise — each has a `title` and an
`operator_note` of at least 20 characters explaining why the case landed on someone's desk —
rather than as abstract test vectors.


### D25 — CP4 ★ realism review deferred; recorded as a limitation, not a pass
**2026-10-29.** The human reviewed the 25 cases but stated they do not know web3 or crypto and
asked the model to proceed on its own judgement. The gate therefore cannot be ticked as "human
reviews realism" in any meaningful sense: the cases were authored and reviewed by the same party.

Recorded as RISKS.md P15 rather than marked passed. What this does and does not threaten:
- **Not at issue:** the chain side. Transactions are real and independently verifiable, so shapes
  like reverted transfers, zero-value transfers and multi-token transactions are real by
  construction.
- **At issue:** whether the *business records* and operator framing resemble what an operations
  team actually sees — invoice/ledger/approval structures, and whether these are the cases that
  genuinely land on someone's desk.

Two judgement calls made in the human's place, stated so they can be overridden:
- **C13 (paid to a different but approved address) kept as a conflict.** The instruction said
  address A and the money went to address B; approval lowers severity without making it a
  non-event. It is also the case that proves `payment.destination` and `destination.approval`
  stay independent.
- **C07 ("payment in a token nobody mentioned") kept, and flagged as the weakest of the 25.** The
  chain data is a real 19-transfer swap, but the business story is thin. Flagged rather than
  quietly counted as a strong case.


### D26 — The rules-only baseline is built to be fair, and its wins are reported
**2026-10-29.** A baseline written to lose makes every number meaningless. So
`traceledger/baselines/rules_only.py` implements the conventional approach as a competent system
and documents why each choice is one a real tool makes: assets matched by **ticker symbol**
(symbols are what ledgers and ERPs store), amounts compared at **2dp as floats** (display
currency precision), payments found by **scanning Transfer events** (the standard indexing
approach), duplicates on exact identifier match, and it **always answers** because operators want
a status.

It is explicitly *our* implementation of a conventional approach, **not any vendor's product**, so
results speak to the approach and not to a competitor (P2).

**Where the baseline wins, and it is recorded:** 0% false positives on clean cases (4/4 correct),
and correct duplicate detection. It is not weak everywhere.

**Its failures are specific and reproducible**, which is the useful output:

| Case | Why the conventional approach misses it |
|---|---|
| C05 bridged vs native USDC | Both contracts report `symbol="USDC"`; symbol matching cannot distinguish them |
| C19 short by one base unit | 0.000001 vanishes when amounts are rounded to 2dp |
| C10 zero-value transfer | Expected 0.00, delivered 0.00 — the rounded comparison matches |
| C06 record disagreement | Records are never compared against each other |
| C11, C15, C23, C24 | The system cannot abstain, so it answers "fine" on insufficient evidence |

**The subtler result:** on C04, C08, C09 and C25 the baseline gets the *outcome* right but names
the wrong issue — it reports `unmatched_payment` where the truth is a wrong asset or a reverted
transaction. Outcome accuracy 68% but issue identification only 41%. Telling an operations team
"no payment found" when a payment exists but reverted, or arrived in the wrong token, sends them
hunting for the wrong thing. That gap is why issue identification is scored separately.

### D27 — A benchmark label was wrong, and the system caught it
**2026-10-29.** `C07` was labelled `wrong_asset` on the premise that the invoiced token was absent
from a 19-transfer, 4-token transaction. The verifier reported the asset check as VERIFIED, which
looked like a system failure. It was not: the transaction genuinely contains USDT
(`0xc2132d05…`), verified against the captured facts, so **the label was wrong and the verifier
was right**.

The case was rebuilt to invoice native USDC, which is genuinely absent from that transaction, and
the ground-truth note now lists all four token contracts so the premise is checkable rather than
assumed.

Recorded because it cuts both ways: it is evidence the benchmark can catch a real error, and
evidence that labels authored alongside the system can be wrong (P16).


### D28 — Two CP4 benchmarks were built in parallel; both kept pending a decision
**2026-10-29.** A teammate (GitHub @nirmitjain2110) merged PRs #1-#3 adding a second,
independent CP4 benchmark while this session was building one. Merged rather than overwritten;
nothing discarded.

This is a **coordination** problem as much as a technical one: two people built the same checkpoint
at the same time. Before starting CP6, agree who owns it.

| | `benchmark/` (this session) | `data/benchmark/` (other session) |
|---|---|---|
| Cases | 25, one inputs file + one labels file | 25, one file per case + per-case ground truth |
| Chain data | **real** Polygon transactions, verifiable on a block explorer | **fabricated** hashes (`0xa1000…00a1`), labelled `simulated: true` |
| Scenario grounding | operator notes written by the model | **FinCEN, TRM Labs, Chainalysis, OFAC, Circle, SEC** typologies cited per case |
| Categories | 15 issue types | 6 named categories incl. **sanctions/frozen assets** and **insufficient evidence** |
| Shared root cause | not covered | **D4 links to A2** — exactly what CP6's graph layer needs |
| Dataset tests | 30 (label leakage, near-duplicate signatures, float checks, records parse) | 1 function, ~55 assertions (Draft-7 schema, base-unit strings, category coverage, D4→A2 link) |
| Results generated | yes, `scripts/run_benchmark.py` → `BENCHMARK_RESULTS.md` | not yet scored |

Each is stronger exactly where the other is weak. The teammate's scenario design directly
addresses P15, the limitation I had flagged as material: its cases are grounded in published
typologies rather than invented by whoever wrote the system. Mine has chain data a judge can
verify, and tests for the failure modes a self-authored benchmark is prone to.

**What must not happen:** running both and quoting whichever scores better. That is precisely the
benchmark-hygiene failure G10 and G11 exist to prevent. Until this is resolved,
`BENCHMARK_RESULTS.md` is explicit that it covers `benchmark/` only.

**Recommended resolution:** keep the teammate's category structure, typology citations and
`tricky_reason` fields, and re-point its cases at **real** transactions — fabricated hashes cannot
be checked on a block explorer and cannot support the live-fire demo (D17). That keeps the better
scenario design and the verifiable evidence, and discards neither contribution.


### D29 — Graph vs SQL: SQL wins on latency at this scale, and that is reported
**2026-10-29.** First measurement of the comparison RISKS.md P7 demands. Both sides read the
identical dataset (`graph/export/dataset.json`) with the identical ImportEvent grouping.

**The shared-root-cause question works.** Of 18 flagged invoices, 11 collapse to three import
events:

| Import event | Flagged invoices | Source |
|---|---|---|
| `IMP-TOKEN-MAP-01` | 5 | token_mapping_2026-10-18.csv |
| `IMP-VENDOR-03` | 3 | vendor_master_update_2026-10-20.csv |
| `IMP-REIMPORT-02` | 3 | month_end_rerun_2026-10-23.csv |

**SQLite answers it in 0.146 ms** (median of 50 runs, in-memory). Our measured round trip to the
Savanna workspace is **1.47–1.94 s**. So on latency, at this data size, SQL is faster by roughly
four orders of magnitude, and no amount of in-memory graph architecture changes that while the
graph is a network call away. This is the honest answer the brief asks for, and it is the second
time a measurement has contradicted the latency story (see D16).

**Where the graph case must therefore be made, if it can be made at all:**
- **Query expressiveness.** The SQL needs 7 joins across 3 UNION branches, because an invoice can
  reach an import event by three different routes (directly, via its payment request, via its
  ledger entries). Every additional record type that carries provenance adds another UNION branch.
  The GSQL version traverses to the shared vertex without enumerating routes.
- **Variable-length paths.** Root cause through shared *wallets* or chained intermediaries is a
  recursive query in SQL and a native traversal in a graph. Not yet measured.
- **Scale.** 25 cases is far too small for any structural advantage to appear.

**What must not be claimed:** that the graph is faster. It is not, here. If the expressiveness and
variable-length-path arguments do not survive measurement either, the honest conclusion is that
SQL suffices for this MVP and the graph earns its place only at larger scale — and that is what
`BENCHMARK_RESULTS.md` will say.

### D30 — The ImportEvent grouping is a documented construction
**2026-10-29.** Each benchmark case carries its own import id, so nothing would share a root cause
by default and the shared-root-cause query would have nothing to find. Inventing a grouping that
flatters the query would be exactly the kind of result G10 forbids.

So the grouping is written in the open at the top of `scripts/load_graph.py`, corresponds to
recognisable operational failures (one bad token-mapping import, one month-end re-run that
double-loaded, one vendor-master update that changed destinations), and is used **identically by
the SQL side**, so neither implementation is advantaged. If the graph only looks good because of
how this grouping was drawn, the comparison says so.


### D31 — Graph vs SQL, final measurement: identical answers, SQL 2792x faster
**2026-10-29.** Both sides now measured against the same data and the same question
(`benchmark/graph_vs_sql.json`).

| | SQLite (in-memory) | TigerGraph 4.2.5 (Savanna, over the network) |
|---|---|---|
| Result | 3 import events, 11 invoices | **identical** |
| Median latency | **0.1 ms** (50 runs) | **280 ms** (5 runs, min 248, max 326) |
| Factor | — | SQL faster by **2792x** |

**The two engines agree exactly** — same import events, same counts, same invoice IDs. That is the
more important result than latency: it means the graph implementation is correct, and it means the
graph is not finding anything SQL cannot.

So the honest position for the pitch:
- **Do not claim the graph is faster.** It is 2792x slower here, and it is reached over a network.
- **Do not claim the graph finds things SQL misses.** On this question, measured, it does not.
- What can be said: the SQL needs **7 joins across 3 UNION branches** because an invoice reaches an
  import event by three different routes, and each new provenance-carrying record type adds another
  branch; the GSQL expresses the same thing as a traversal to a shared vertex. That is an
  argument about maintainability, not performance, and it is unmeasured.
- Variable-length paths (root cause through shared wallets or chained intermediaries) would be the
  genuine graph advantage, and are **not implemented or measured**. Recorded in `BACKLOG.md`.

At 25 cases and 172 vertices, no structural advantage could appear. Saying so plainly is better
than a claim a judge can test.

### D32 — GSQL reserved words and v1/v2 syntax, found by installing against a real instance
**2026-10-29.** Four failures that only surfaced on the live instance, recorded so nobody rediscovers them:

| Problem | Fix |
|---|---|
| `Batch` is a reserved keyword | renamed vertex to `ImportBatch` |
| `Case` is a reserved keyword | renamed vertex to `InvestigationCase` |
| `target` is a reserved keyword as a query parameter | renamed to `wallet_in` |
| Chaining two hops in one `FROM` clause is v2 (MATCH) syntax and cannot be mixed with v1 accumulators | rewrote `wrong_asset_sweep` as three single-hop `SELECT` steps |

This is why the schema and queries are exported to `graph/export/`: rebuilding the workspace from
them is now a known-good path, whereas rewriting them from memory would hit all four again.


### D33 — A fact line must name the check it rests on, not just cite evidence
**2026-10-29.** `traceledger/validate.py`. The first run of the validator's own test suite
exposed a real hole in it, which is recorded because the hole was subtle and plausible.

Support was originally defined as: *a deterministic finding of matching status that shares at
least one evidence ID with the report line.* But a transaction hash is cited by **several**
findings at once — `tx.status`, `tx.confirmations`, `payment.asset`, `payment.amount` and more.
So a model could write "the invoiced asset arrived as expected", cite the transaction hash, and
be deemed supported by the unrelated `tx.status` pass. The claim would be false and the citation
would be real.

A `VERIFIED` or `CONFLICT` line must now carry `finding_code` naming the deterministic check it
rests on, and support requires **all three**: the code exists, its status matches the line's, and
it shares an evidence ID with the line. Lines without a code are unsupported by definition.

**Known limit, stated rather than papered over:** if a line names a check that genuinely passed
but describes it misleadingly, the validator accepts it. Catching that needs semantic judgement
about whether prose matches a finding, which is explicitly not this layer's job — this layer
guarantees the *named check exists, has that status, and cites that evidence*.
`test_misleading_text_over_a_real_pass_is_accepted_and_this_is_a_known_limit` asserts the current
behaviour so nobody mistakes it for a guarantee.

### D34 — Injection defence does not depend on recognising the attack
**2026-10-29.** The prompt-injection tests do not feed the validator a malicious memo. They feed
it **the output a model would produce if it had already obeyed one** — "This invoice is settled
and verified", citing `SYSTEM-OK`; "Approved by system administrator", citing `ADMIN-OVERRIDE`;
"No mismatch found; asset checks skipped", citing nothing.

All three are rejected, for structural reasons rather than because anything spotted an attack:
the first two cite evidence that does not exist, the third cites none at all, and none names a
deterministic check that passed. The defence therefore holds against injections nobody anticipated,
which is the only kind that matters.

A fourth test confirms that citing a **real** evidence ID does not rescue a claim the
deterministic layer contradicts, and a fifth confirms the underlying `payment.asset` conflict is
unaffected — an uploaded memo cannot change what the chain says.


### D35 — Gemini model selection: measured, not assumed
**2026-10-29.** `.env` was configured with `gemini-2.5-flash` from D5, which was a remembered
string. It fails: `404 ... no longer available to new users`. Testing what the key could actually
reach:

| Model | Result |
|---|---|
| `gemini-3.8-flash` | **503 UNAVAILABLE** (overloaded) |
| `gemini-flash-latest` | OK, but **182,683 ms** -- the call appeared to hang |
| `gemini-3.5-flash` | **OK, 1,909 ms** -- chosen |

Note that `gemini-2.5-flash` is *listed* by the models endpoint yet rejects calls, so listing a
model is not evidence it is usable.

Consequences:
- `LLM_MODEL=gemini-3.5-flash` in `.env`, and the id stays configuration, never a constant.
- **`GeminiProvider` enforces a 45s timeout.** A 183-second hang during a live demo is worse than
  a failure, because the audience watches a spinner instead of an answer.
- Model availability is volatile enough to be a demo risk (RISKS.md S21). The fallback is the
  deterministic layer, which needs no model at all -- the pipeline degrades to code-only findings
  and says the narrative layer is unavailable, rather than failing the case.

### D36 — Gemini must be asked for JSON; a truncated reply is unparseable
**2026-10-29.** The first live investigation failed: the reply began
`{"summary": "The payment transaction succeeded on-chain, but there is an asset mismatch...` and
was cut off mid-key. These models spend output tokens on reasoning, so a 2048-token budget ran out
mid-object.

Two fixes, both in `GeminiProvider`:
- `response_mime_type="application/json"`, so JSON is requested natively rather than hoped for.
- `max_output_tokens` default raised to 8192, and a reply whose `finish_reason` mentions
  `MAX_TOKENS` now raises *"hit the output limit... raise max_output_tokens"* rather than a generic
  JSON decode error. The failure names its own cause.

### D37 — `no_conflict` must be earned; the LLM layer had a dangerous default
**2026-10-29.** Found by `test_compliant_verified_without_support_is_downgraded`.

`Investigation.outcome` originally read: conflict if any CONFLICT line, unresolved if any MISSING,
otherwise **no_conflict**. So a report consisting only of `HYPOTHESIS` lines -- which is exactly
what an obeyed prompt injection produces *after* the validator downgrades it -- reported
`no_conflict`. The validator would have done its job, and the outcome would still have said
"fine, close the case".

`no_conflict` now requires all of: a surviving `VERIFIED` line, no `CONFLICT`, no `MISSING`, and
**zero downgrades**. An unsupported assertion disqualifies a clean bill of health.

Four regression tests, including `test_a_clean_case_can_still_reach_no_conflict` -- without it, the
fix could have made `no_conflict` unreachable and still passed the other three.

### D38 — The deterministic layer decides the outcome, not the LLM
**2026-10-29.** In the CP8 runner, TraceLedger's reported `outcome` comes from the deterministic
findings. The LLM's own view is recorded separately as `llm_outcome`, so the two can be compared,
but it never overrides code (G8).

If the LLM call fails entirely, the pipeline returns the deterministic verdict with a note that
the narrative layer was unavailable. A model outage degrades the prose, not the facts.


### D39 — Provider switched to OpenAI; the interface made it a config change
**2026-10-29.** Gemini's free tier is **5 requests per minute**. A 25-case three-way run needs
~50 calls, so the first attempt produced 17 quota failures, and a second attempt with 13-second
pacing was still erroring after ~2 minutes per case. It was stopped rather than left to spend 40
minutes producing errors.

Switched to OpenAI `gpt-4o-mini` on the human's paid key: **2.7s per call, no pacing required**.

The point worth recording is that this cost nothing architecturally. `D5` put the LLM behind an
`LLMProvider` protocol precisely so the model could be swapped without touching the investigation
layer, and that held: `OpenAIProvider` was added, `LLM_PROVIDER` changed, and
`traceledger/llm/investigate.py`, the validator and every test were untouched. 261 tests passed
before and after.

Two details carried over from the Gemini work because they are provider-agnostic problems:
- **JSON requested natively** (`response_format={"type":"json_object"}`), since a truncated reply
  is unparseable (D36).
- **A truncated reply names its own cause** rather than surfacing as a JSON decode error.

One OpenAI-specific wrinkle handled: reasoning models fix temperature at 1 and reject any other
value, so the provider retries once without the parameter instead of failing on something it does
not need.

### D40 — Per-provider key lookup, so a stale key cannot be picked up silently
**2026-10-29.** `config.load_config()` previously read
`GOOGLE_API_KEY or ANTHROPIC_API_KEY`, whichever was set. With both a Google and an OpenAI key in
`.env`, that would hand the OpenAI provider a Google key and produce a confusing auth error.

The key is now looked up **by the selected provider's name** (`_PROVIDER_KEY_VARS`), so
`LLM_PROVIDER=openai` reads only `OPENAI_API_KEY`. A leftover key for another provider is ignored
rather than misused.

This also surfaced a real setup trap: a variable named `LLM_PROVIDER2` is simply not read, so the
configuration silently stayed on the Gemini default while a `gpt-4o-mini` model id was set — a
combination that would have failed with a misleading model error rather than a configuration one.


### D41 — The review form carries no JavaScript, by design
**2026-10-29.** D13 measured that Wispr Flow inserts dictated text by putting it on the clipboard
and synthesising a paste. Any handler that intercepts paste, rewrites a field as it changes, or
clears a field on blur would therefore break dictation **while typing continued to work** -- a bug
that passes every keyboard-based test and only shows up on stage.

The most reliable way to honour that is to have no JavaScript on the review path at all, so the
dashboard's forms are plain HTML posts. Two tests assert it rather than trusting the comment:
`test_the_review_page_contains_no_javascript_at_all` and `test_no_inline_event_handlers`, the
latter checking for `onpaste`, `oninput`, `onkeydown`, `onblur`, `onchange` and `onsubmit`.

Cost: no client-side validation, and a full page reload per action. Worth it -- the alternative is
a demo where the reviewer dictates a rationale and the text silently vanishes.

### D42 — The audit log is append-only, and is not called tamper-proof
**2026-10-29.** `traceledger/store.py`. A reviewer decision records what a human concluded at a
point in time, so it is never updated or deleted; a later decision is a new row. No `UPDATE` or
`DELETE` statement against `audit_log` exists in the codebase, and `test_the_log_is_append_only`
asserts that a second decision adds an entry rather than replacing the first.

**What is deliberately not claimed:** it is a SQLite file on disk and anyone with filesystem
access can edit it. Describing it as immutable or tamper-proof would be an unearned claim (G10,
P10), so the UI says *"append-only... stored in a SQLite file, so it is not tamper-proof and is
not claimed to be"*, and a test asserts the word "immutable" appears nowhere in the interface.

A rationale is **required** for every decision: `record_review` raises on a blank one, because a
decision with no stated reason cannot be reviewed later, which defeats the point of having a human
in the loop. The dashboard returns 400 and logs nothing.

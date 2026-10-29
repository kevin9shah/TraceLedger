# PROGRESS

Running log. Append after every meaningful step. Newest entries at the bottom of each session block.

---

## 2026-10-29 — Session 1

### Done
- Read master prompt. Confirmed repo is effectively empty (initial commit: `.gitignore`, `README.md` stub).
- Verified `.gitignore` already covers `.env` (line 153).
- CP0: created the six memory files (`PROGRESS.md`, `CHECKPOINTS.md`, `DECISIONS.md`, `RISKS.md`, `BACKLOG.md`, `BENCHMARK_RESULTS.md`), `.env.example`, README stub expanded.

### Failed / blocked
- Nothing attempted yet that failed.

### Open questions for the human (blocking CP1)
1. Which EVM chain does your Cake Wallet build support for **both** USDC and USDT? (Needs to be confirmed in the app, not assumed.)
2. Testnet available for that chain in Cake Wallet, or do we use tiny mainnet amounts?
3. Which hosted LLM API will we use (key provider), so CP7 can be scoped?

### Next
- CP1 sponsor smoke tests, once the chain question is answered.

### Done (continued, 2026-10-29)
- Decisions recorded: Polygon PoS (D3), tiny mainnet transfers (D4), Gemini behind a provider
  interface (D5), symbols are display-only (D6), RPC endpoint choice (D7), RPC method allow-list (D8).
- Built `traceledger/config.py` (startup assertions; refuses env vars that look like key material),
  `traceledger/chain/rpc.py` (read-only JSON-RPC, method allow-list, per-fact provenance),
  `traceledger/chain/tokens.py` (ERC-20 metadata from the contract, exact integer base-unit maths).
- `scripts/verify_tokens.py` ran green against Polygon mainnet: chain id 137 confirmed, block
  96347626, three contracts read. Output committed to `data/token_registry.json`.
- 28 unit tests pass (`.venv/bin/python -m pytest -q`), covering base-unit arithmetic with no float
  drift, ABI string/uint decoding, config guardrails and refusal of write/signing RPC methods.
- `ui/dictation_test.html`: dictation-friendly review fields that distinguish typed from injected
  input (dictation fires `input` with no `keydown`). Passive listeners only; nothing calls
  `preventDefault`. No Wispr Flow API or SDK anywhere — it is OS-level dictation (RISKS.md S4).
- `scripts/tg_smoke.py`: written, correctly exits 2 with a SKIP while `TG_HOST` is unset.

### Failed / notable
- `polygon-rpc.com` is unusable keyless: `-32051 "API key disabled, tenant disabled"`. Switched to
  `polygon-bor-rpc.publicnode.com` (D7).
- **Unexpected real-world finding:** the canonical Polygon Tether contract reports `symbol="USDT0"`,
  and two distinct live contracts both report `symbol="USDC"`. Symbol matching is demonstrably
  unsafe. Recorded as D6 / RISKS.md P9 and will be used as a real benchmark case instead of an
  invented lookalike (P4, P9).

### Next (blocked on human, see CP1 breakdown in CHECKPOINTS.md)
1. TigerGraph Savanna free instance + credentials in `.env`, then `python scripts/tg_smoke.py`.
2. Open `ui/dictation_test.html`, dictate into both fields, report the `Injected` counter.
3. Copy the USDC and USDT contract addresses as Cake Wallet shows them on Polygon (RISKS.md P13).

### 2026-10-29 — sponsor setup research (while CP1 human tasks are outstanding)
- Checked TigerGraph's own docs rather than trusting the brief. **The brief's "free tier" assumption
  is wrong:** Savanna offers *free credits, no free instances*; a running workspace consumes credits
  and then costs money. Recorded as RISKS.md S1; mitigation is smallest size + keep it stopped +
  export everything to `graph/export/`.
- Also found Savanna authenticates with a **database secret** (`gsqlSecret`), not username/password.
  The smoke test as first written would have failed against a perfectly healthy workspace. Fixed:
  `scripts/tg_smoke.py` uses `gsqlSecret` for Savanna, username/password only for self-hosted.
  `.env.example` reordered to make `TG_SECRET` the primary path. RISKS.md S6 (closed).
- Wrote `docs/setup_sponsors.md`: step-by-step for the three human CP1 tasks, with pass/fail criteria
  for the dictation counters and the expected Polygon token addresses to sanity-check Cake Wallet against.

### 2026-10-29 — TigerGraph deployment decided (constraints: no spend, no Docker)
- Checked a pasted summary claiming Cloud Classic still offers a free cluster. **It does not** —
  free tier removed Nov 2024, Classic closed to new users, AWS EOL 30 Sep 2026 (already passed).
  Recorded as RISKS.md S7 so no one follows an outdated guide.
- Community Edition would be ideal (free forever, 300GB, full GSQL) but is Docker-only with no
  native macOS install, and Docker is ruled out. RISKS.md S8 (accepted, not pursued).
- Decision D9: **Savanna free credits, no payment method ever added.** TigerGraph's FAQ confirms
  expiry stops/terminates the instance "unless a payment method is added" — so the worst case is a
  stopped workspace, not a bill. TG-00 is $1/hr *while running*, so the workspace stays stopped
  except while building or demoing.
- Architectural consequence: the SQLite root-cause path becomes first-class rather than a stub, so a
  stopped workspace degrades the demo honestly instead of breaking it. CP8's graph-vs-SQL comparison
  needed that path anyway. RISKS.md S9.

### 2026-10-29 — Community Edition re-examined (Docker turned out to be available)
- Human corrected the no-Docker constraint, so CE was re-checked rather than left rejected on a
  stale premise. Conclusion: still not viable **here**, for hardware reasons, not preference.
  TigerGraph's Docker guide states Docker is "not supported for ARM processors, including M1 Macs";
  this host is arm64 with 8 GB RAM against a recommended 24 GB, and the Docker daemon is not running.
- Confirmed CE and Savanna are functionally equivalent for this project (same GSQL, REST and
  pyTigerGraph), so nothing we build is Savanna-locked — only `.env` would change. DECISIONS.md D10,
  RISKS.md S8 (closed).
- Savanna (D9) stands as the graph deployment.

### 2026-10-29 — TigerGraph client readiness (our side of CP1)
- Installed **pyTigerGraph 2.0.5** (the docs I read were 1.6, so the API was re-verified against the
  installed version rather than assumed). `TigerGraphConnection` accepts `gsqlSecret`, and every
  method the smoke test and CP6 need is present: `getVer`, `echo`, `getVertexTypes`, `getToken`,
  `gsql`, `runInstalledQuery`, `getSchema`.
- `requirements.txt` pinned to `pyTigerGraph>=2.0,<3` with the verified version noted.
- `scripts/tg_smoke.py` is ready; it exits 2 with an actionable SKIP until `TG_HOST`/`TG_SECRET` are set.
- Walkthrough for the human is in `docs/setup_sponsors.md` step 1. Still outstanding: the human
  creating the Savanna workspace, graph `TraceLedger` and a database secret.

### 2026-10-29 — Savanna cost controls verified
- Compute is billed by hours **in use**, so stopping the workspace stops the $1/hr TG-00 charge.
  Storage is billed separately at $0.025–0.044/GB-month; our graph is a few MB, so effectively zero.
- **Auto-suspend** (Advanced Settings) enabled at the shortest interval — the main guard against a
  forgotten workspace draining credits. HA off (1.95x–2.8x multiplier), no add-ons, no starter-kit
  solutions (they would pollute the graph and distort the CP8 graph-vs-SQL comparison).
- Noted two documented behaviours: auto-suspend does not treat console configuration as activity,
  and **auto-resume can silently restart a suspended workspace** when a script hits its REST API —
  so `scripts/tg_smoke.py` can itself resume billing. RISKS.md S10, DECISIONS.md D11.

### 2026-10-29 — TG_HOST format bug found before it could bite
- The setup instructions this project originally gave ("no `https://`") were **wrong** for the
  installed client: pyTigerGraph 2.0.5 raises `Invalid URL scheme. Supported schemes are http and
  https.` on a bare hostname. TigerGraph's own pyTigerGraph 1.6 docs show the bare form, so both
  spellings will reach `.env` depending on which source someone follows.
- Fixed by normalising instead of specifying: `config.normalise_tg_host()` accepts either form,
  strips trailing slashes, and adds `https://` for remote hosts / `http://` for localhost.
- Tests now 41 passing, including `test_bare_host_would_have_failed_without_normalisation`, which
  asserts the raise really happens, and a test that the normalised value constructs a real
  `TigerGraphConnection`. RISKS.md S11 (closed), DECISIONS.md D12.
- Also documented where the host actually lives in the Savanna UI: workspace **Connect** →
  **Connect from API**, or read it off the GraphStudio URL.

### 2026-10-29 — Savanna host discovery made robust
- The human could not find the endpoint in the console, and the URL they found
  (`tgcloud.io/groups/<uuid>`) is a **workgroup** UUID, not the workspace id. The endpoint is
  `https://<workspace-id>.i.tgcloud.io` where the id is 32 hex chars with no dashes.
- Rather than give more navigation instructions, `normalise_tg_host()` now also accepts a bare
  32-hex workspace id and expands it. A dashed UUID deliberately does not match, so a workgroup id
  fails visibly instead of silently producing a wrong endpoint. RISKS.md S12.
- **Test-isolation bug found and fixed:** `load_dotenv()` does not override variables already in
  `os.environ`, so a `TG_HOST` leaked by an earlier test beat the `.env` written by a later one —
  the test passed alone and failed in the suite. All managed keys are now cleared in the autouse
  fixture. This is also a real-world trap: a stale exported `TG_HOST` would silently beat `.env`.
  RISKS.md S13 (closed).
- Tests: 47 passing, stable across repeated runs.

### 2026-10-29 — TigerGraph CP1 item PASSED
- `scripts/tg_smoke.py` exit 0 against Savanna workspace `traceledger-ws`:
  **TigerGraph 4.2.5**, secret auth, `echo: Hello GSQL`, 0 vertex types (empty graph, as expected).
- Trivial GSQL executed end to end: `USE GRAPH TraceLedger; LS` → `Graph TraceLedger()` with empty
  Vertex Types, Edge Types, Jobs and Queries. CP1's "trivial query" criterion is met by a real GSQL
  statement, not just the handshake.
- **Setup lessons recorded (RISKS.md S14), because they cost real time:**
  - The actual workspace host is `tg-<uuid>.tg-<number>.i.tgcloud.io`, *not* the
    `<32-hex-id>.i.tgcloud.io` that TigerGraph's docs and third-party guides describe. Do not
    construct it; copy it.
  - Secrets come from the console's **Database Secrets** sidebar screen, not `CREATE SECRET` in a
    GSQL shell.
  - `tgcloud.io/groups/<uuid>` is a workgroup, not a workspace.
- Workspace is **running and billing at $1/hr** — stop it between sessions (D11).

### Next
- CP1 remaining: dictation counter (`ui/dictation_test.html`), Cake Wallet contract addresses.
- Then CP3 (deterministic verifier) — unblocked and independent of both.

### 2026-10-29 — stopped-workspace behaviour measured; cost risk closed
- Human stopped the workspace; the smoke test then failed with HTTP 500 on `/gsql/v1/tokens`.
  Diagnosed rather than guessed: the server's own body is
  `"Auto start is not enabled for this workspace"` / `"Failed to start workspace"`, on every
  endpoint including unauthenticated `/api/ping`. The secret in `.env` was verified intact.
- **RISKS.md S10 closed with a measurement, replacing an assumption.** The docs describe auto-resume
  waking a workspace on REST access; this workspace has auto-start **off**, so no script in this
  repo can restart it or cause a charge. Stopping it in the console is a hard cost stop.
- `scripts/tg_smoke.py` now probes `/api/ping` on any 500 and reports
  "DIAGNOSIS: the workspace is STOPPED" with exit code 3, instead of vaguely blaming the free tier.
  Saves the next person from debugging a host or secret that was never wrong.

### 2026-10-29 — dictation test harness corrected after first real run
- Wispr Flow is **not installed** on the machine (nothing in `/Applications`, no process). The mic
  hardware is fine (`MacBook Air Microphone, Default Input Device: Yes`), so the earlier "mic not
  working" was simply no dictation app present.
- First real run of `ui/dictation_test.html` showed text arriving as `inputType=insertFromPaste`
  preceded by `keydown key="v"` — i.e. a manual Cmd+V, not dictation. `Injected=0` was correct.
- Two defects in the harness, both fixed:
  1. **False-positive SILENT WRITE.** The poller reported any length change, including ones that had
     fired proper events, so every ordinary paste looked like a silent write. It now reports only
     changes that fired no event at all.
  2. **Paste exclusion could never pass.** Wispr Flow and similar macOS tools insert text by putting
     it on the clipboard and synthesising Cmd+V, which is indistinguishable from a human paste at the
     DOM level. Excluding `insertFromPaste` outright would have made the test unpassable for the very
     tool CP1 names. There is now a separate **Clipboard inserts** counter, and the verdict states
     what was observed and asks the operator whether they pressed Cmd+V — rather than silently
     deciding. Pass = `Injected > 0`, or `Clipboard inserts > 0` without a human Cmd+V.


### 2026-10-29 — CP1 dictation item PASSED
- `Wispr Flow.app` installed and running (`com.electron.wispr-flow`). Human dictated
  "Hello, Wispr Flow." with the Fn hotkey into `ui/dictation_test.html`.
- Event log evidence: `focus` 23:54:20.362 → `beforeinput inputType=insertFromPaste
  data="Hello, Wispr Flow. "` 23:54:23.268 → `input` 19 chars. **Clipboard inserts = 1**, zero
  typing in between, and the human confirmed no Cmd+V. Recorded in CHECKPOINTS.md.
- **Finding that constrains CP9 (DECISIONS.md D13, RISKS.md S15):** Wispr Flow inserts via the
  clipboard, which is indistinguishable from a human paste in the DOM. So the review UI must never
  block paste, never rewrite field values on change, and never clear fields on blur. Any of those
  would break dictation while still passing a keyboard-only test.
- No Wispr Flow API or SDK is used anywhere; this remains OS-level dictation (S4).

### CP1 status: 5 of 6 done
Remaining: the two Cake Wallet token contract addresses (RISKS.md P13).


### 2026-10-29 — CP1 ★ COMPLETE (6/6)
- Human supplied `0x3004cEe4065774e4BCE4EC3aC5C56f3FE61D45b3` as **both** the USDC and USDT contract
  from Cake Wallet. Verified on Polygon: `eth_getCode` → `0x`, balance 0. It holds no contract code —
  it is the wallet's **receive address**, not a token contract. Caught by code, not by eye
  (RISKS.md P14).
- Design change D14: **token identity is never sourced from a wallet UI.** The authoritative contract
  for each real transfer is the transaction's `to` address, cross-checked against on-chain
  `decimals()` and the ERC-20 `Transfer` event in the receipt. Stronger evidence than a UI label, so
  CP1 closes without it and the native-vs-bridged USDC question is settled at CP2 from the real tx.
- **CP1 ★ now DONE, all six sub-items evidenced** in CHECKPOINTS.md: chain + tokens verified on-chain
  (Polygon 137, block 96350969), read-only enforcement (47 tests), TigerGraph 4.2.5 reachable with a
  real GSQL query, dictation via Wispr Flow with event-log evidence, Cake Wallet check recorded.

### Next: CP3 (deterministic verifier + tests)
CP2 needs the human's real transfers, so CP3 is taken first — it depends only on data shape. CP2 will
slot in when the tx hashes arrive.


### 2026-10-29 — SECURITY: committed TigerGraph secret (RISKS.md S16)
- Auditing the human's `CP1` commit (`22573dd`) found a **live TigerGraph database secret in
  `.env.example`**, which is tracked — it had been pasted there instead of into the gitignored
  `.env`. The commit is on `origin/main` at `github.com/kevin9shah/TraceLedger`.
- Exposure assessed, not assumed: GitHub returns **404 unauthenticated**, so the repo is private.
  Limited to the owner and any collaborators; not public.
- Actions taken: secret removed from `.env.example` (commit pending).
- **Action required from the human: rotate the secret** in Savanna's Database Secrets screen.
  Removing a secret from a file does not un-expose it; only replacement does.
- Prevented from recurring: `tests/test_no_secrets_committed.py` asserts every credential field in
  `.env.example` is blank, that no key material appears there, and that `.env` is untracked and
  ignored. Tests now **57 passing**. DECISIONS.md D15.
- History rewrite deliberately **not** performed — it needs a force push, which is destructive and
  needs explicit approval (G13), and it is unnecessary once the old secret is dead.

### 2026-10-29 — CP4 Benchmark Dataset Built & Validated (branch `cp4/benchmark-cases`)
- Designed and approved 25 real-pattern benchmark cases across 6 distinct categories based on
  FinCEN, TRM Labs, Chainalysis, OFAC SDN actions, Circle docs, and SEC advisories:
  - Category A: Destination Conflict (6 cases: BEC, address poisoning, unapproved address change, similar-name routing, contract destination, stale cache)
  - Category B: Status / Amount Conflict (6 cases: reverted tx, 1 micro-unit off-by-one, USDT paid on USDC invoice, split payment, webhook retry duplicate, gas-spike delayed tx duplicate)
  - Category C: Wrong Asset / Contract (4 cases: bridged USDC.e vs native USDC, canonical Tether USDT0 symbol mismatch, native POL vs ERC-20, counterfeit fake USDC)
  - Category D: Duplicate / Shared-Root-Cause (4 cases: single tx on two invoices, refund misclassified as payment, recurring invoice collision, multi-hop shared root cause linking to case A2)
  - Category E: Sanctions / Frozen Asset (3 cases: post-settlement OFAC blacklist, incoming SDN strict liability, smart contract blacklist revert)
  - Category F: Insufficient Evidence (2 cases: non-existent Polygon tx hash, dual-control concurrent approval/revocation race condition)
- All 25 input case files (`data/benchmark/cases/*.json`) and 25 ground-truth files (`data/benchmark/ground_truth/*.json`) created with separate directories.
- Built `data/benchmark/schema.json` with strict Draft-7 schemas for `#case` and `#ground_truth`.
- Built `data/benchmark/manifest.json` indexing all 25 cases, categories, tricky reasons, and ground-truth pairings.
- Built `scripts/validate_benchmark.py` and automated test `tests/test_benchmark_dataset.py`.
- Automated test suite: **55 passing**, 3 skipped. All 25 cases strictly validate against JSON Schema Draft-7. All token addresses use verified tokens or explicitly annotated wrong assets. All tricky case criteria satisfied. D4 shared-root-cause link to A2 verified.


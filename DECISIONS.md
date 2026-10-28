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

# Sponsor setup — the three CP1 tasks that need a human

Everything here is done by you, not by TraceLedger. The code is read-only and never asks for
key material (G1, G2). Work through the tasks in any order; paste the results back and I'll
record them as CP1 evidence in `CHECKPOINTS.md`.

---

## 1. TigerGraph Savanna

> **Two corrections to the original plan, both verified against TigerGraph's docs (DECISIONS.md D9):**
> - The **Cloud Classic free-tier cluster no longer exists** (removed Nov 2024, Classic closed to new
>   users, AWS end-of-life 30 Sep 2026). Ignore any guide that mentions it.
> - Savanna gives **free credits, not a free instance**. The smallest workspace, **TG-00, is $1/hour
>   while running**, and credits are valid one year.
>
> **You will not be charged.** TigerGraph's FAQ: when free credits expire they stop and eventually
> terminate the instance *"unless a payment method is added."* So the rule is simple:
> **never add a card.** Worst case is the workspace stopping.
>
> **Stop the workspace whenever you're not working.** Running it overnight burns ~$24 of credits.

1. Sign up at **[tgcloud.io](https://tgcloud.io)**. **Do not add a payment method** at any point.
2. Complete the onboarding tasks it offers — that's what grants extra free credits.
3. Create a **workgroup** first; the workspace form follows it.
4. In the workspace form:
   - **Name**: anything, e.g. `traceledger-ws`
   - **Runtime**: the default version
   - **Size**: **TG-00**, the smallest. Our graph is tens of vertices; nothing bigger is justified
   - **Database**: *Create a new database* (attaching to an existing one makes the workspace
     read-only, which blocks loading data at CP6)
   - **Solutions / starter kits**: **none — start from scratch.** A starter kit loads its own sample
     schema and data, which would pollute the TraceLedger graph and distort the CP8 graph-vs-SQL
     comparison
   - **Advanced Settings → Auto-Suspend**: **enable it, shortest interval offered.** This is the main
     protection against a forgotten workspace draining credits. Auto-resume brings it back when you
     use it, so there is no downside
   - **High Availability**: **off** (it is a 1.95x–2.8x cost multiplier)
   - **Add-ons** (e.g. Insights): **none**
5. Click **Create**, wait for the **General** tab to show it active.
6. **Create a graph named `TraceLedger`** (GraphStudio, or GSQL: `CREATE GRAPH TraceLedger()`).
   An empty graph is fine — CP6 builds the schema.
7. **Get a database secret.** Savanna connects with a secret, *not* a username and password.
   Use the console's **Database Secrets** item in the left sidebar (not the GSQL shell — that is
   where the published docs send you, but the console screen is the working route). Create a secret
   for graph `TraceLedger` and copy it; it is typically shown only once.
8. Find the **host** on the workspace page. It looks like `something.i.tgcloud.io` —
   no `https://`, no trailing slash.
9. Put both into `.env`:
   ```
   TG_HOST=your-thing.i.tgcloud.io
   TG_GRAPH=TraceLedger
   TG_SECRET=the-secret-string
   ```
10. Run it and paste me the output:
    ```
    .venv/bin/pip install pyTigerGraph
    .venv/bin/python scripts/tg_smoke.py
    ```
    A pass prints the version, an echo response, and the vertex-type list (empty is expected).
11. **When you stop working: stop the workspace** in the Savanna console.

### What actually costs money

| Dimension | Stopped workspace | Note |
|---|---|---|
| Compute ($1/hr at TG-00) | **not billed** — charged by hours in use | The only meaningful cost |
| Storage ($0.025–0.044/GB-month) | billed | Our graph is a few MB, so effectively zero |
| HA / add-ons | not enabled | Keep them off |

Two documented surprises:
- **Auto-suspend ignores some activity.** Running queries, installing queries, loading jobs and
  schema changes count as active. Console configuration and Controller API calls do *not*, so the
  workspace can suspend while you are clicking around in settings.
- **Auto-resume can wake it.** Running `scripts/tg_smoke.py` against a suspended workspace will
  likely resume it and start billing compute. Not pressing "start" is not the same as it being
  stopped — check the console.

**If it fails:** paste the error verbatim. Don't tidy it up — the exact message distinguishes a bad
host format from a bad secret, a wrong graph name, or a stopped workspace.

**If credits run out or the workspace won't start:** not a blocker for the demo. The SQLite
root-cause path is built as a first-class equivalent (D9), so the demo degrades to it and we say
plainly that the graph layer is offline. We never show cached graph output as if it were live.

## 2. Dictation check (Wispr Flow)

TraceLedger has **no** Wispr Flow integration — no API, no SDK, no dependency (RISKS.md S4).
Wispr Flow is system-wide dictation: it types into whatever field has focus. This test only
proves our review fields accept that, and that we haven't broken the input path.

1. Open the page:
   ```
   open ui/dictation_test.html
   ```
2. Make sure Wispr Flow is running and you know its hotkey.
3. Click into **Reviewer rationale**, dictate two or three sentences.
4. Click into **Investigation question**, dictate one more.
5. Also **type** a few characters, to confirm the keyboard path still works.
6. Read the four counters and tell me the **"Injected (no keydown)"** number.

| Result | Meaning |
|---|---|
| Injected > 0 | **Pass.** Dictated text arrives through the insertion path. CP1 item satisfied. |
| Injected = 0, text appeared | Dictation is delivering as synthetic keystrokes. Still usable; tell me and I'll note it. |
| No text appeared | Fail. Likely Wispr Flow permissions (macOS Accessibility), not our page. |

Pasting from the clipboard is deliberately excluded from the Injected count, so a paste can't be
mistaken for a dictation pass.

---

## 3. Cake Wallet — token contract addresses

Polygon has **two** live contracts that both report `symbol="USDC"`, and the canonical Tether
contract now reports `symbol="USDT0"` (DECISIONS.md D6). So I need the addresses, not the names.

1. Open your **Polygon** wallet in Cake Wallet.
2. If USDC and USDT aren't in the asset list, find **Add token / Manage tokens** (a `+` or pencil
   near the bottom of the list) and add them.
3. Tap **USDC** → find its **contract address** → copy it.
4. Tap **USDT** → same.
5. Paste both to me. I'll re-verify them on-chain and set `.env` from what you send.

Expected, so you can sanity-check what you see:

| Token | Address | On-chain name |
|---|---|---|
| USDC (native) | `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` | USD Coin |
| USDC.e (bridged) | `0x2791bca1f2de4661ed88a30c99a7a9449aa84174` | USD Coin (PoS) |
| USDT | `0xc2132d05d31c914a87c6611c10748aeb04b58e8f` | USDT0 |

If Cake Wallet shows something not on this list, that's worth knowing — paste it and I'll check
what it actually is on-chain before we trust it.

**Funding, for CP2 later:** you'll need a little POL for gas plus ~1 USDC and ~1 USDT. Gas on
Polygon is a fraction of a cent. **I never need your seed phrase or private key** — only public
addresses and transaction hashes.

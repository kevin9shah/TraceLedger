# BACKLOG

Out-of-scope ideas. Add here instead of building. Nothing in this file is implemented.

## Deliberately excluded from MVP
- Multi-chain support; Tron, Bitcoin, Monero.
- Live enterprise connectors (ERP, Netsuite, QuickBooks, bank feeds).
- Fund movement, signing, settlement, ledger modification — permanently excluded (G1).
- Auth / multi-tenant / RBAC.
- Voice backend of any kind (dictation stays at OS level).
- Model fine-tuning. *Hypothesis only: with a real labelled corpus, a fine-tuned classifier might beat prompting on issue typing. No data to justify it now.*

## Deferred from the demo design (D17)
- Multi-hop split-payment tracing, intermediary pool routes, fee-deduction attribution and entity
  clustering. These were described in an earlier architecture draft as if built; they are not in the
  MVP's three exception types (G12). Genuinely interesting, and the graph layer is the right place
  for them later.

## Where the graph might actually earn its place (unmeasured)
- **Variable-length path queries**: root cause through shared *wallets*, chained intermediaries or
  multi-hop fund splits. Recursive in SQL, native in a graph. This is the only graph advantage that
  has not been ruled out by measurement (D31) — but it is not implemented, not measured, and must
  not be claimed until it is.
- Scale: at 172 vertices no structural advantage can appear. Any such claim needs a dataset orders
  of magnitude larger.

## Validation paths (post-MVP, for the pitch as future work)
- Continuous monitoring mode: watch a wallet + ledger feed, open cases automatically.
- API / webhook so exceptions can be pushed from an existing recon tool.
- Reviewer-time study with real ops staff (needed before any "time saved" claim, G10).
- **Pre-flight destination check**: query the entity graph *before* a transfer is signed or staged, to
  flag a destination that is a lookalike token contract or an unapproved address. Attractive because
  it moves TraceLedger from after-the-fact investigation to prevention. Out of scope for the MVP:
  TraceLedger is read-only and sits nowhere near the signing path (G1), and the latency budget such a
  check would need has not been measured — no figure should be attached to this idea until it is.

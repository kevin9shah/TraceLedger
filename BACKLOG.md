# BACKLOG

Out-of-scope ideas. Add here instead of building. Nothing in this file is implemented.

## Deliberately excluded from MVP
- Multi-chain support; Tron, Bitcoin, Monero.
- Live enterprise connectors (ERP, Netsuite, QuickBooks, bank feeds).
- Fund movement, signing, settlement, ledger modification — permanently excluded (G1).
- Auth / multi-tenant / RBAC.
- Voice backend of any kind (dictation stays at OS level).
- Model fine-tuning. *Hypothesis only: with a real labelled corpus, a fine-tuned classifier might beat prompting on issue typing. No data to justify it now.*

## Validation paths (post-MVP, for the pitch as future work)
- Continuous monitoring mode: watch a wallet + ledger feed, open cases automatically.
- API / webhook so exceptions can be pushed from an existing recon tool.
- Reviewer-time study with real ops staff (needed before any "time saved" claim, G10).

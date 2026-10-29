# CP4 Benchmark Design: Real-Pattern Case Taxonomy

## Research Sources Used
All 25 cases are constructed from documented real-world exception patterns, not invented behavior.

| Source Type | What Was Mined |
|---|---|
| Chainalysis 2023/2024 Crypto Crime Reports | Address poisoning mechanics, scale, targeting profile |
| TRM Labs Stablecoin Threat Intelligence | B2B fraud taxonomy: BEC, APP fraud, sanctions exposure, velocity anomalies |
| OFAC SDN enforcement actions (2022–2024) | Sanctions-tainted address, post-freeze payment failure, strict liability |
| Polygonscan forensic guides + Circle docs | Native vs. bridged USDC confusion, decimal mismatch, reverted tx, wrong-asset |
| SEC/FinCEN advisories on stablecoin payment processors | Invoice-record conflicts, duplicate payment cascade, split-destination layering |

---

## Exception Category Taxonomy (6 categories → 25 cases)

### Category A — Destination Conflict (6 cases)
*Root cause: payment reaches an address that is not the approved payee. On-chain fact is clean; business record is wrong or was changed.*

| # | Pattern | Real-world source |
|---|---|---|
| A1 | Payment sent to BEC-substituted address (fraudster replaced vendor bank/wallet via compromised email) | FinCEN BEC advisories; TRM APP fraud |
| A2 | Address poisoning — attacker's vanity address matches first-4/last-4 of approved vendor | Chainalysis 2023 crime report; Polygonscan forensics |
| A3 | Vendor legitimately changed their wallet address 48h before payment, but approval was never recorded | TRM velocity/behavioral anomaly category |
| A4 | Internal ops error — two vendors share similar display name; payment routed to wrong vendor's approved address | SEC payment processor misrepresentation cases |
| A5 | Payment to a contract address (e.g., a DEX router), not a wallet; funds inaccessible | Polygonscan forensic guide — `eth_getCode` returns non-empty, no withdrawal key |
| A6 | Vendor address changed and approved, but payer's system cached the old address from a previous invoice | TRM behavioral anomaly + BEC pattern |

### Category B — Status / Amount Conflict (6 cases)
*Root cause: on-chain fact (amount, token, success/failure) disagrees with what the business ledger records.*

| # | Pattern | Real-world source |
|---|---|---|
| B1 | Transaction reverted (gas ran out); ledger marks invoice "Paid" because the tx hash was submitted, not confirmed | Polygonscan forensic guide — "Failed/Reverted" status |
| B2 | Off-by-one in base-unit arithmetic: system sent 100.000001 USDC instead of 100.000000; invoice flagged underpaid | Decimal mismatch research; TraceLedger D6 |
| B3 | Amount sent in USDT matches invoice denominated in USDC numerically, but they are different assets; reconciler accepted it | Polygonscan multi-stablecoin checkout case |
| B4 | Payment split across two transactions (partial first, remainder second); ERP only matched first tx; second orphaned | TRM velocity anomaly + duplicate-invoice cascade |
| B5 | Merchant's backend webhook timed out; second payment attempt submitted; both confirmed; now two payments on-chain for one invoice | FinCEN idempotency failure case |
| B6 | Pending transaction (low gas) mined 4 hours late; ERP auto-generated a duplicate payout after 2-hour timeout | Polygonscan "Pending/Dropped" state forensics |

### Category C — Wrong Asset / Contract (4 cases)
*Root cause: the correct amount arrived, but the token contract address does not match what the invoice specifies.*

| # | Pattern | Real-world source |
|---|---|---|
| C1 | Customer paid in USDC.e (bridged, `0x2791bc…`) but merchant's gateway only listened on native USDC (`0x3c499c…`); both 6 decimals; merchant ledger shows zero receipt | Circle native vs. bridged USDC docs; Polygon reconciliation failure |
| C2 | Payment made in USDT0 (Tether now branded USDT0 on Polygon, `0xc2132d…`) but invoice says "USDT"; internal system rejected it as unknown token | TraceLedger D6: canonical Tether contract reports `symbol="USDT0"` |
| C3 | Payer accidentally sent native MATIC/POL instead of USDC; tx succeeded; amounts numerically match at spot price but token contract is chain-native, not ERC-20 | Polygonscan wrong-asset case |
| C4 | Attacker-issued counterfeit USDC token (different contract, same symbol) sent to victim's address; victim's ledger auto-credited it as real USDC | Chainalysis address poisoning + counterfeit token variant |

### Category D — Duplicate / Shared-Root-Cause (4 cases)
*Root cause: same underlying event appears multiple times in records, or two seemingly separate cases share one root cause.*

| # | Pattern | Real-world source |
|---|---|---|
| D1 | Single tx hash referenced on two different invoices (copy-paste error in ERP; only one payment exists on-chain) | FinCEN invoice-fraud advisories |
| D2 | Refund processed as new payment; original and refund now both recorded as "Paid" against the same invoice | TRM layered intermediary pattern |
| D3 | Two distinct invoices, same vendor, same amount, same week — legitimate batch; only one tx on-chain; ambiguous which invoice it satisfies | Real-world B2B batch settlement ambiguity |
| D4 | Three cases in the same session (A2 + B5 + D1) share the same poisoned attacker address as the root cause — graph query must identify shared entity | Graph-layer test case for CP6/CP8 graph-vs-SQL |

### Category E — Sanctions / Frozen Asset (3 cases)
*Root cause: on-chain address or token is subject to an OFAC designation or issuer freeze.*

| # | Pattern | Real-world source |
|---|---|---|
| E1 | Payment successfully sent on-chain; destination address is later found on OFAC SDN list; transfer froze within 24h by Circle | OFAC/Tornado Cash precedent; Circle blacklist mechanism |
| E2 | Incoming payment from a sanctions-listed counterparty; strict-liability exposure even though recipient did not know | OFAC strict-liability doctrine (Kraken/Bittrex precedents) |
| E3 | USDC transfer attempt fails at ERC-20 level (`transfer()` returns false); on-chain event log shows `isBlacklisted` flag; business record shows "Payment failed — reason unknown" | OFAC/Circle technical freeze implementation |

### Category F — Insufficient / Contradictory Evidence (2 cases)
*Root cause: the verifier cannot reach a determination because critical evidence is absent or internally contradictory.*

| # | Pattern | Real-world source |
|---|---|---|
| F1 | Invoice references a tx hash that does not exist on Polygon (possibly submitted to wrong chain or typo) | Polygonscan forensic guide — null hash lookup |
| F2 | Two approvers recorded conflicting decisions on the same payment request within minutes of each other; audit log is ambiguous | SEC/FinCEN internal-controls advisories |

---

## Ground Truth Schema (per case)

```json
{
  "case_id": "A1",
  "category": "destination_conflict",
  "pattern_name": "BEC vendor address substitution",
  "real_world_source": "FinCEN BEC advisory + TRM APP fraud typology",
  "chain_id": 137,
  "chain_name": "polygon-pos",
  "token_contract": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
  "token_symbol_display": "USDC",
  "invoice": {
    "invoice_id": "INV-2024-A1-001",
    "vendor_id": "VEN-0042",
    "amount_usdc": "5000.000000",
    "amount_base_units": "5000000000",
    "approved_destination": "0x<approved_address>",
    "approval_timestamp": "2024-03-10T09:00:00Z"
  },
  "transaction": {
    "tx_hash": "0x<real_or_constructed_hash>",
    "block_number": null,
    "status": "success",
    "from": "0x<payer_address>",
    "to": "0x<token_contract>",
    "recipient": "0x<bec_attacker_address>",
    "amount_base_units": "5000000000",
    "decimals": 6,
    "timestamp": "2024-03-10T14:23:11Z"
  },
  "ground_truth": {
    "verdict": "CONFLICT",
    "conflict_types": ["destination_mismatch"],
    "verified_facts": [
      "tx status: success",
      "amount matches invoice",
      "token contract matches",
      "recipient does NOT match approved_destination"
    ],
    "unverified": [],
    "missing_evidence": [],
    "explanation": "Payment executed successfully on-chain but to an attacker-controlled address substituted via BEC. Funds not recoverable without issuer freeze action.",
    "recommended_action": "Flag for immediate issuer freeze request; open BEC investigation with vendor"
  },
  "is_tricky": true,
  "tricky_reason": "On-chain tx is valid; amount and token are correct. Conflict is purely at destination level. A rules-only system that only checks amount+token will pass this as clean."
}
```

---

## Tricky / Edge Cases (for CP8 evaluation quality)
These are designed to separate TraceLedger from rules-only and plain LLM:

| Case | Why it's tricky |
|---|---|
| A2 (address poisoning) | Poisoned address shares prefix+suffix with approved address. String equality check catches it; prefix-only check misses it |
| B3 (USDT paid on USDC invoice) | Amount numerically identical; only the ERC-20 contract address differs |
| C1 (USDC.e vs native USDC) | Both 6 decimals, both called "USDC" in wallet UIs; only the contract address differs |
| C2 (USDT0 symbol) | Token reports `symbol="USDT0"` not "USDT"; a symbol-matching rule rejects a valid canonical contract |
| D4 (shared-root-cause across 3 cases) | Graph layer required to link A2+B5+D1 to same attacker address; SQL cannot do it without pre-joining |
| E3 (silent freeze) | `transfer()` returned false; tx receipt status is "success" (gas was consumed); only event log reveals the freeze |

---

## File Layout

```
data/
  benchmark/
    cases/
      A1.json  ... F2.json    # 25 case input files (tx + invoice + business records)
    ground_truth/
      A1_gt.json ... F2_gt.json  # Separate ground truth (not fed to the system under test)
    manifest.json              # Lists all 25 cases with category, is_tricky, source
    schema.json                # JSON Schema for both case and ground-truth files
```

---

## Validation Rules (for CP4 exit criteria)
- [ ] Every case has a `real_world_source` field citing the documented pattern
- [ ] Every case's `token_contract` is in `data/token_registry.json` (verified on-chain at CP1)
- [ ] `amount_base_units` passes TraceLedger's integer math check (no float)
- [ ] Ground truth files are in a separate directory from case inputs
- [ ] At least one case per category includes an `is_tricky: true` flag
- [ ] D4 case references the same attacker address as A2 (shared-root-cause link)
- [ ] Human reviews all 25 for realism before CP4 ★ is ticked (required by checkpoint)

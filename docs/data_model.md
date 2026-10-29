# Data model

Two kinds of record, kept rigorously apart:

| | Chain facts | Business records |
|---|---|---|
| Source | an EVM node, read-only | uploaded CSV/JSON (synthetic in this repo) |
| Trust | verified; carries `provenance` | **untrusted input** — data, never instructions (G9) |
| Can be wrong? | only if the RPC lied (chain id asserted, source logged) | yes, routinely — that is the whole problem |
| Marked | `"simulated": false` | `"simulated": true` where invented (G3) |

A conflict is a disagreement between the two. TraceLedger never edits either side (G1).

---

## Chain facts

### `TransactionFacts` — `traceledger/chain/transfers.py`
What the chain says about one transaction.

| Field | Type | Notes |
|---|---|---|
| `tx_hash` | str | normalised `0x…`, 32 bytes |
| `status` | int | `1` succeeded, `0` reverted. Absent status is an error, never assumed success |
| `block_number` | int | |
| `chain_id` | int | asserted against config before any fact is trusted (P6) |
| `sender` | str | the EOA that signed |
| `called_contract` | str \| None | `tx.to`; for a token transfer this is the token contract |
| `transfers` | tuple[`TransferEvent`] | **all** Transfer events, in log order |
| `confirmations` | int | head − block + 1, so a head-block tx has 1 |
| `provenance` | `Provenance` | rpc_url, chain_id, method, read_at |
| `simulated` | bool | always `False` — this type only ever holds real chain data |

### `TransferEvent`
| Field | Type | Notes |
|---|---|---|
| `token` | str | contract address, lowercase. **The only token identity** (G7) |
| `sender` / `recipient` | str | lowercase addresses |
| `value` | int | **integer base units.** Serialised as a string so no consumer floats it (G8) |
| `log_index` | int | position in the receipt; disambiguates repeated transfers |

**Why `transfers` is a list, not a single transfer.** Verified on live Polygon data:
`0x7858560a…` moves **both USDT and USDC** in one transaction (4 transfers), and
`0x094b7da1…` has **19 transfers across 4 tokens**. So "the amount this transaction paid" is not
well defined. A settling payment is identified by *token contract + recipient*, and when more than
one transfer still matches, the ambiguity is reported rather than resolved by taking the first.

### `TokenMetadata` — `traceledger/chain/tokens.py`
`address`, `decimals` (read from the contract), `symbol`, `name`, `provenance`.
**`symbol` and `name` are display-only** and never inputs to a matching decision — on Polygon the
canonical Tether contract reports `symbol="USDT0"` and two distinct live contracts both report
`symbol="USDC"` (D6). Cached in `data/token_registry.json`, regenerated from live reads.

---

## Business records (synthetic; uploaded)

All carry `record_id` (the evidence ID that reports cite), `source_file`, `imported_at`,
`import_event_id`, and `simulated: true`.

| Entity | Key fields | Why it exists |
|---|---|---|
| `Invoice` | `invoice_id`, `counterparty`, `amount`, `token_contract`, `due_date`, `status` | What was owed. `token_contract`, never a ticker |
| `PaymentRequest` | `request_id`, `invoice_id`, `expected_destination`, `amount`, `token_contract` | What was asked for, and where |
| `LedgerEntry` | `entry_id`, `invoice_id`, `amount`, `direction`, `posted_at`, `status` | What the books claim happened |
| `Wallet` | `address`, `owner_label`, `first_seen` | A party. Address is identity |
| `ApprovedAddress` | `address`, `approved_for`, `approved_at`, `approved_by` | Allow-list; a destination outside it is a mismatch, **not** "fraud" (G6) |
| `Batch` | `batch_id`, `created_at`, `record_ids` | Group of records processed together |
| `ImportEvent` | `import_event_id`, `source_file`, `row_count`, `imported_at` | Provenance of an upload — the shared-root-cause anchor |
| `Case` | `case_id`, `opened_at`, `linked_record_ids`, `linked_tx_hashes`, `state` | One investigation |

### Amounts
Stored as **decimal strings** in files and converted to integer base units using the token's
on-chain `decimals()` before any comparison. `TokenMetadata.base_units()` raises if a value carries
more precision than the token allows, rather than rounding — a payment file claiming
`0.0000001 USDC` is a data error, not something to silently truncate.

### Linking
An edge is built only when its basis is known. Anything inferred is labelled `candidate` and may
not be cited as `VERIFIED`. Report lines are exactly one of `VERIFIED`, `CONFLICT`, `HYPOTHESIS`,
`MISSING`, `NEXT_STEP`; the first two must cite evidence IDs (G4).

---

## `data/real_txs.json`
Real transaction hashes used as on-chain evidence. Every entry records where it came from, so a
public mainnet transaction is never presented as one of our own transfers.

| Field | Meaning |
|---|---|
| `tx_hash` | the hash |
| `origin` | `cake_wallet_demo` (sent by us) or `public_mainnet` (observed, not ours) |
| `chain_id`, `block_number` | as verified |
| `token_contract`, `amount_base_units`, `sender`, `recipient` | read from the chain, not typed in |
| `verified_at` | when we last read it |
| `simulated` | always `false` in this file |

Regenerate with `scripts/capture_fixtures.py <hash>`; offline fixtures live in `tests/fixtures/`.

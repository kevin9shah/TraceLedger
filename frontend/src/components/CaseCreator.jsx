import React, { useState } from 'react';
import { Terminal, Send, RefreshCw, AlertCircle, Sparkles, ExternalLink } from 'lucide-react';
import { createCase } from '../api';

const PRESETS = [
  {
    name: 'Cake Wallet 0.10 USDT',
    hash: '0x3e1b6243f0f74ef16ab02a6f62a92b30763ee8556d684cf908459d33cb63fd4a',
    amount: '0.10',
    token: '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
    desc: 'Mainnet Cake Wallet transfer from human (Block 96374114)',
    dest: '0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e'
  },
  {
    name: 'Cake Wallet 1.00 USDT',
    hash: '0x5db5918a22234617ca5892e90ad3ec401c2f03bd0555ad23f47d5ce6ef9dd911',
    amount: '1.00',
    token: '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
    desc: 'Mainnet Cake Wallet transfer (Block 96374131)',
    dest: '0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e'
  },
  {
    name: 'Multi-Transfer (USDC + USDT)',
    hash: '0x7858560a69a9448f2b7a97753eb026858e775191a27e7f9754cae8f3bfa658d2',
    amount: '100.00',
    token: '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359',
    desc: '4 transfers across 2 tokens in 1 tx — tests transfer ambiguity',
    dest: ''
  },
  {
    name: 'Reverted Tx (Failed Payment)',
    hash: '0xe00f5243ecaa68a623a35a6aa87747761002ca745348bb95ea7c44933a30349f',
    amount: '50.00',
    token: '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
    desc: 'Status 0; gas spent, 0 tokens transferred (Block 96371332)',
    dest: ''
  },
  {
    name: 'Wrong Asset (USDC invoice vs USDT tx)',
    hash: '0x3e1b6243f0f74ef16ab02a6f62a92b30763ee8556d684cf908459d33cb63fd4a',
    amount: '0.10',
    token: '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359',
    desc: 'Invoice names native USDC contract, tx transferred USDT0',
    dest: '0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e'
  }
];

export default function CaseCreator({ onCaseCreated, onOpenCaseDetail }) {
  const [txHash, setTxHash] = useState(PRESETS[0].hash);
  const [invoiceToken, setInvoiceToken] = useState(PRESETS[0].token);
  const [amount, setAmount] = useState(PRESETS[0].amount);
  const [destination, setDestination] = useState(PRESETS[0].dest);
  const [approved, setApproved] = useState('0xdad4d0ee4260c1a9a25bb61099c9e518b5033e8e');
  const [counterparty, setCounterparty] = useState('Vendor Apex Ltd');
  const [title, setTitle] = useState('Supplier payment reconciliation');
  const [memo, setMemo] = useState('Standard payment for Invoice #INV-2026-902');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const applyPreset = (preset) => {
    setTxHash(preset.hash);
    setAmount(preset.amount);
    setInvoiceToken(preset.token);
    setDestination(preset.dest || '');
    if (preset.dest) setApproved(preset.dest);
    setTitle(`${preset.name} investigation`);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await createCase({
        tx_hash: txHash,
        invoice_token: invoiceToken,
        amount: amount,
        destination: destination,
        approved: approved,
        counterparty: counterparty,
        title: title,
        memo: memo,
      });

      if (onCaseCreated) onCaseCreated();
      if (onOpenCaseDetail) onOpenCaseDetail(res.case_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">
            <Terminal size={18} />
            <span>Open a Case from a Transaction Hash</span>
          </div>
          <div className="panel-subtitle">
            Reads the transaction facts directly from Polygon mainnet and verifies them against business records.
          </div>
        </div>
      </div>

      {/* Preset Chips */}
      <div style={{ marginBottom: '1.25rem' }}>
        <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.4rem', fontWeight: 600 }}>
          Load Real Mainnet Presets
        </div>
        <div className="preset-list">
          {PRESETS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              className={`preset-chip ${txHash === p.hash && invoiceToken === p.token ? 'active' : ''}`}
              onClick={() => applyPreset(p)}
            >
              <Sparkles size={11} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
              {p.name}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Polygon Transaction Hash (EVM Chain 137)</label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              className="form-control mono"
              required
              value={txHash}
              onChange={(e) => setTxHash(e.target.value)}
              placeholder="0x…"
              autoComplete="off"
            />
            {txHash && (
              <a
                href={`https://polygonscan.com/tx/${txHash}`}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
                title="View on Polygonscan"
              >
                <ExternalLink size={14} />
              </a>
            )}
          </div>
          <div className="form-help">
            Must be a valid 66-character hex hash on Polygon PoS.
          </div>
        </div>

        <div className="grid-2">
          <div className="form-group">
            <label className="form-label">Invoiced Token Contract Address</label>
            <select
              className="form-control mono"
              value={invoiceToken}
              onChange={(e) => setInvoiceToken(e.target.value)}
            >
              <option value="0x3c499c542cef5e3811e1192ce70d8cc03d5c3359">
                0x3c499c… — Native USDC (USD Coin, 6 decimals)
              </option>
              <option value="0xc2132d05d31c914a87c6611c10748aeb04b58e8f">
                0xc2132d… — Canonical Tether (USDT0, 6 decimals)
              </option>
              <option value="0x2791bca1f2de4661ed88a30c99a7a9449aa84174">
                0x2791bc… — Bridged USDC.e (USD Coin PoS, 6 decimals)
              </option>
            </select>
            <div className="form-help">
              Never match by ticker. Two contracts report "USDC"; Tether reports "USDT0".
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Invoiced Amount</label>
            <input
              type="text"
              className="form-control mono"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="100.00"
              autoComplete="off"
            />
            <div className="form-help">
              Converted to integer base units via contract decimals (exact math, no float drift).
            </div>
          </div>
        </div>

        <div className="grid-2">
          <div className="form-group">
            <label className="form-label">Expected Destination Address (Optional)</label>
            <input
              type="text"
              className="form-control mono"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="0x…"
              autoComplete="off"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Approved Addresses (Comma separated, optional)</label>
            <input
              type="text"
              className="form-control mono"
              value={approved}
              onChange={(e) => setApproved(e.target.value)}
              placeholder="0x…, 0x…"
              autoComplete="off"
            />
          </div>
        </div>

        <div className="grid-2">
          <div className="form-group">
            <label className="form-label">Counterparty Name</label>
            <input
              type="text"
              className="form-control"
              value={counterparty}
              onChange={(e) => setCounterparty(e.target.value)}
              placeholder="Acme Corp"
              autoComplete="off"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Case Title</label>
            <input
              type="text"
              className="form-control"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Supplier says they paid"
              autoComplete="off"
            />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Invoice Memo / Free Text Data</label>
          <textarea
            className="form-control mono"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            rows={2}
            placeholder="Free text from the uploaded record. Treated as DATA, never as instructions."
          />
        </div>

        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: '6px', color: '#fca5a5', marginBottom: '1rem' }}>
            <AlertCircle size={18} />
            <div>{error}</div>
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? (
            <>
              <RefreshCw className="spin" size={16} />
              <span>Verifying Against Live Polygon Chain…</span>
            </>
          ) : (
            <>
              <Send size={16} />
              <span>Verify and Open Case</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
}

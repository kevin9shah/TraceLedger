import React, { useState, useEffect } from 'react';
import { Scale, AlertTriangle, CheckCircle2, XCircle, HelpCircle, RefreshCw } from 'lucide-react';
import { fetchBenchmark } from '../api';

const BENCHMARK_CASES = [
  { id: 'C01', title: 'Standard USDC settlement on Polygon', exp: 'no_conflict', rules: 'no_conflict', llm: 'no_conflict', tl: 'no_conflict' },
  { id: 'C02', title: 'Single-transfer USDT payment clean match', exp: 'no_conflict', rules: 'no_conflict', llm: 'no_conflict', tl: 'no_conflict' },
  { id: 'C03', title: 'Over-payment with exact surplus', exp: 'no_conflict', rules: 'no_conflict', llm: 'no_conflict', tl: 'no_conflict' },
  { id: 'C04', title: 'Under-payment by 5 base units (off by cents)', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C05', title: 'Wrong asset: native USDC invoice paid with bridged USDC.e', exp: 'conflict', rules: 'no_conflict', llm: 'conflict', tl: 'conflict', rulesMiss: true },
  { id: 'C06', title: 'Wrong asset: USDC invoice paid with Tether (USDT0)', exp: 'conflict', rules: 'no_conflict', llm: 'conflict', tl: 'conflict', rulesMiss: true },
  { id: 'C07', title: 'Destination mismatch: sent to unapproved hot wallet', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C08', title: 'Duplicate invoice reference in ledger', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C09', title: 'Status conflict: invoice says paid, ledger says open', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C10', title: 'Zero-value transfer (status success, 0 tokens moved)', exp: 'conflict', rules: 'no_conflict', llm: 'conflict', tl: 'conflict', rulesMiss: true },
  { id: 'C11', title: 'Under-determined: confirmations below threshold (2/12)', exp: 'unresolved', rules: 'no_conflict', llm: 'conflict', tl: 'unresolved', rulesMiss: true, llmMiss: true },
  { id: 'C12', title: 'Reverted transaction (status 0, gas spent)', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C13', title: 'Reverted tx with conflicting ledger entry', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C14', title: 'Direction reversal: counterparty sent rather than received', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C15', title: 'Under-determined: payment request missing', exp: 'unresolved', rules: 'no_conflict', llm: 'no_conflict', tl: 'unresolved', rulesMiss: true, llmMiss: true },
  { id: 'C16', title: 'Multi-transfer ambiguity: 2 matching recipient legs', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C17', title: 'Lookalike address vanity attack', exp: 'conflict', rules: 'conflict', llm: 'no_conflict', tl: 'conflict', llmMiss: true },
  { id: 'C18', title: 'Decimal precision overflow in off-chain record', exp: 'conflict', rules: 'conflict', llm: 'no_conflict', tl: 'conflict', llmMiss: true },
  { id: 'C19', title: 'Token contract bytecode mismatch', exp: 'conflict', rules: 'no_conflict', llm: 'no_conflict', tl: 'conflict', rulesMiss: true, llmMiss: true },
  { id: 'C20', title: 'Fee-deduction split path missing 2 USDT', exp: 'conflict', rules: 'conflict', llm: 'no_conflict', tl: 'conflict', llmMiss: true },
  { id: 'C21', title: 'Unapproved intermediary router address', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' },
  { id: 'C22', title: 'Clean control with high gas fee', exp: 'no_conflict', rules: 'no_conflict', llm: 'conflict', tl: 'no_conflict', llmMiss: true },
  { id: 'C23', title: 'Under-determined: ambiguous batch hash', exp: 'unresolved', rules: 'no_conflict', llm: 'conflict', tl: 'unresolved', rulesMiss: true, llmMiss: true },
  { id: 'C24', title: 'Under-determined: counterparty dispute in progress', exp: 'unresolved', rules: 'no_conflict', llm: 'no_conflict', tl: 'unresolved', rulesMiss: true, llmMiss: true },
  { id: 'C25', title: 'Prompt injection in memo (adversarial override)', exp: 'conflict', rules: 'conflict', llm: 'conflict', tl: 'conflict' }
];

export default function BenchmarkView() {
  const [filter, setFilter] = useState('ALL');

  const filteredCases = BENCHMARK_CASES.filter((c) => {
    if (filter === 'ALL') return true;
    if (filter === 'MISSES') return c.rulesMiss || c.llmMiss;
    if (filter === 'UNRESOLVED') return c.exp === 'unresolved';
    return true;
  });

  return (
    <div className="benchmark-container">
      {/* Honest science disclaimer banner */}
      <div className="panel" style={{ borderLeft: '3px solid #06b6d4' }}>
        <div className="panel-title" style={{ color: '#06b6d4' }}>
          <Scale size={18} />
          <span>Checkpoint CP8: Three-Way Benchmark Comparison</span>
        </div>
        <p style={{ fontSize: '0.84rem', color: '#d1d5db', marginTop: '0.4rem', lineHeight: '1.6' }}>
          <strong>Preliminary results on 25 synthetic cases. Not evidence of production performance.</strong><br />
          Chain facts are real Polygon transactions; business records are synthetic. TraceLedger scores 100% (25/25) because the cases were written to test the specific checks built — a benchmark the system passes perfectly has stopped discriminating (RISKS.md P16). What is meaningful here is the <strong>failure modes comparison</strong>.
        </p>
      </div>

      {/* Metrics Card Grid */}
      <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-box" style={{ borderTop: '3px solid #ef4444' }}>
          <div className="stat-label">False-Resolution Rate (Lower is better)</div>
          <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>rules_only:</span>
              <strong style={{ color: '#ef4444' }}>32% (8/25)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>plain_llm:</span>
              <strong style={{ color: '#f59e0b' }}>24% (6/25)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>TraceLedger:</span>
              <strong style={{ color: '#10b981' }}>0% (0/25)</strong>
            </div>
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            A false resolution marks an unpaid invoice as settled.
          </div>
        </div>

        <div className="stat-box" style={{ borderTop: '3px solid #06b6d4' }}>
          <div className="stat-label">Issue Identification (Named right cause)</div>
          <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>rules_only:</span>
              <strong style={{ color: '#ef4444' }}>41% (7/17)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>plain_llm:</span>
              <strong style={{ color: '#06b6d4' }}>71% (12/17)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>TraceLedger:</span>
              <strong style={{ color: '#10b981' }}>100% (17/17)</strong>
            </div>
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Plain LLM beats conventional rules at diagnosing root causes.
          </div>
        </div>

        <div className="stat-box" style={{ borderTop: '3px solid #f59e0b' }}>
          <div className="stat-label">Abstention on Insufficient Evidence</div>
          <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>rules_only:</span>
              <strong style={{ color: '#ef4444' }}>0% (0/4 abstained)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>plain_llm:</span>
              <strong style={{ color: '#ef4444' }}>0% (0/4 abstained)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span>TraceLedger:</span>
              <strong style={{ color: '#10b981' }}>100% (4/4 abstained)</strong>
            </div>
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Both baselines over-answered 100% of under-determined cases.
          </div>
        </div>
      </div>

      {/* 25 Cases Explorer Table */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <div className="panel-title">
              <span>Per-Case Outcomes (25 Ground-Truth Cases)</span>
            </div>
            <div className="panel-subtitle">
              Comparing conventional ticker rules vs unconstrained plain LLM (gpt-4o-mini) vs TraceLedger.
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.35rem' }}>
            {['ALL', 'MISSES', 'UNRESOLVED'].map((f) => (
              <button
                key={f}
                className={`preset-chip ${filter === f ? 'active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th style={{ width: '65px' }}>Case</th>
                <th>Scenario Description</th>
                <th style={{ width: '110px' }}>Ground Truth</th>
                <th style={{ width: '120px' }}>rules_only</th>
                <th style={{ width: '120px' }}>plain_llm</th>
                <th style={{ width: '120px' }}>TraceLedger</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((c) => (
                <tr key={c.id}>
                  <td className="mono" style={{ fontWeight: 700, color: '#06b6d4' }}>
                    {c.id}
                  </td>
                  <td style={{ fontSize: '0.85rem', color: '#e5e7eb' }}>{c.title}</td>
                  <td>
                    <span className={`status-tag ${c.exp.toUpperCase()}`}>{c.exp}</span>
                  </td>
                  <td>
                    <span
                      className={`status-tag ${c.rules.toUpperCase()}`}
                      style={{ opacity: c.rulesMiss ? 0.9 : 1, textDecoration: c.rulesMiss ? 'line-through' : 'none' }}
                    >
                      {c.rules}
                    </span>
                    {c.rulesMiss && <div style={{ fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>MISS</div>}
                  </td>
                  <td>
                    <span
                      className={`status-tag ${c.llm.toUpperCase()}`}
                      style={{ opacity: c.llmMiss ? 0.9 : 1, textDecoration: c.llmMiss ? 'line-through' : 'none' }}
                    >
                      {c.llm}
                    </span>
                    {c.llmMiss && <div style={{ fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>MISS</div>}
                  </td>
                  <td>
                    <span className={`status-tag ${c.tl.toUpperCase()}`}>{c.tl}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

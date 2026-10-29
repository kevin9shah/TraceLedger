import React, { useState, useEffect } from 'react';
import { History, ShieldCheck, Search, ExternalLink, ArrowRight } from 'lucide-react';
import { fetchAudit } from '../api';

export default function AuditView({ onSelectCase }) {
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadAudit = async () => {
    setLoading(true);
    try {
      const data = await fetchAudit();
      setAudit(data);
    } catch (err) {
      console.warn('Failed to fetch audit:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudit();
  }, []);

  const filtered = audit.filter((entry) => {
    const s = search.toLowerCase();
    return (
      entry.case_id.toLowerCase().includes(s) ||
      entry.actor.toLowerCase().includes(s) ||
      entry.action.toLowerCase().includes(s) ||
      entry.rationale.toLowerCase().includes(s)
    );
  });

  return (
    <div className="audit-container">
      {/* Disclaimer Banner per D42 */}
      <div className="panel" style={{ borderLeft: '3px solid #f59e0b' }}>
        <div className="panel-title" style={{ color: '#f59e0b' }}>
          <History size={18} />
          <span>Append-Only Decision History</span>
        </div>
        <p style={{ fontSize: '0.84rem', color: '#d1d5db', marginTop: '0.4rem', lineHeight: '1.6' }}>
          A reviewer decision records what a human concluded at a point in time. It is never updated or deleted; a subsequent decision is appended as a new row. Stored in a local SQLite file &mdash; <strong>it is not tamper-proof, and is not claimed to be</strong> (Decision D42, Risk P10).
        </p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div>
            <div className="panel-title">
              <span>All Decision Entries ({audit.length})</span>
            </div>
            <div className="panel-subtitle">
              Every decision requires a recorded rationale and logs the exact findings shown to the reviewer.
            </div>
          </div>

          <div style={{ position: 'relative', minWidth: '220px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '9px', color: 'var(--text-muted)' }} />
            <input
              type="text"
              className="form-control"
              style={{ paddingLeft: '2rem', padding: '0.45rem 0.75rem 0.45rem 2rem', fontSize: '0.82rem' }}
              placeholder="Search audit trail…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="table-container">
          {filtered.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th style={{ width: '150px' }}>Timestamp</th>
                  <th style={{ width: '120px' }}>Case ID</th>
                  <th style={{ width: '130px' }}>Action</th>
                  <th style={{ width: '150px' }}>Reviewer</th>
                  <th>Rationale</th>
                  <th style={{ width: '160px' }}>Entry ID</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((entry, idx) => (
                  <tr key={idx}>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {new Date(entry.at * 1000).toLocaleString()}
                    </td>
                    <td className="mono">
                      <button
                        onClick={() => onSelectCase && onSelectCase(entry.case_id)}
                        style={{ background: 'none', border: 'none', color: '#06b6d4', cursor: 'pointer', padding: 0, font: 'inherit', fontWeight: 600 }}
                      >
                        {entry.case_id}
                      </button>
                    </td>
                    <td>
                      <span className="status-tag NEXT_STEP" style={{ fontSize: '0.72rem' }}>
                        {entry.action}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{entry.actor}</td>
                    <td style={{ fontSize: '0.85rem', color: '#d1d5db', lineHeight: '1.5' }}>
                      {entry.rationale}
                    </td>
                    <td className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      {entry.entry_id}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
              No audit entries recorded yet. Open a case and submit a decision to see append-only logs.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

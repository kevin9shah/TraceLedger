import React, { useState } from 'react';
import { Activity, Search, ExternalLink, ArrowRight, ShieldCheck, AlertTriangle } from 'lucide-react';

export default function CaseList({ cases, onSelectCase, onNewCaseClick }) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('ALL');

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.case_id.toLowerCase().includes(search.toLowerCase()) ||
      c.title.toLowerCase().includes(search.toLowerCase()) ||
      (c.tx_hash && c.tx_hash.toLowerCase().includes(search.toLowerCase()));

    if (!matchesSearch) return false;
    if (filter === 'ALL') return true;
    return c.state.toUpperCase() === filter;
  });

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">
            <Activity size={18} />
            <span>Investigated Cases ({cases.length})</span>
          </div>
          <div className="panel-subtitle">
            All cases opened and verified against the live chain.
          </div>
        </div>

        <button className="btn btn-primary btn-sm" onClick={onNewCaseClick}>
          <span>+ Open New Case</span>
        </button>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: '240px' }}>
          <Search size={15} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-muted)' }} />
          <input
            type="text"
            className="form-control"
            style={{ paddingLeft: '2rem' }}
            placeholder="Search by Case ID, title, or tx hash…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.4rem' }}>
          {['ALL', 'OPEN', 'RESOLVED', 'CLOSED'].map((f) => (
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

      {/* Table */}
      <div className="table-container">
        {filteredCases.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Title</th>
                <th>State</th>
                <th>Polygon Transaction</th>
                <th>Opened</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((c) => (
                <tr key={c.case_id} style={{ cursor: 'pointer' }} onClick={() => onSelectCase(c.case_id)}>
                  <td className="mono" style={{ color: '#06b6d4', fontWeight: 600 }}>
                    {c.case_id}
                  </td>
                  <td style={{ fontWeight: 500, color: '#fff' }}>{c.title}</td>
                  <td>
                    <span
                      className={`status-tag ${
                        c.state === 'open' ? 'MISSING' : c.state === 'conflict' ? 'CONFLICT' : 'VERIFIED'
                      }`}
                    >
                      {c.state}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    {c.tx_hash ? (
                      <span title={c.tx_hash}>
                        {c.tx_hash.slice(0, 10)}…{c.tx_hash.slice(-8)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {new Date(c.created_at * 1000).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectCase(c.case_id);
                      }}
                    >
                      <span>Review</span>
                      <ArrowRight size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
            <p>No cases match your filter.</p>
          </div>
        )}
      </div>
    </div>
  );
}

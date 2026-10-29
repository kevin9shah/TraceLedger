import React, { useState, useEffect } from 'react';
import { ArrowLeft, ExternalLink, ShieldAlert, CheckCircle2, AlertTriangle, HelpCircle, ArrowRight, Mic, Send, RefreshCw, History, ShieldCheck } from 'lucide-react';
import { fetchCase, submitReview } from '../api';

export default function CaseDetail({ caseId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Review form state
  const [action, setAction] = useState('confirm');
  const [rationale, setRationale] = useState('');
  const [actor, setActor] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState(null);

  const loadCase = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchCase(caseId);
      setData(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCase();
  }, [caseId]);

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    if (!rationale.trim()) {
      setReviewError('Rationale is required for every decision.');
      return;
    }

    setSubmitting(true);
    setReviewError(null);
    try {
      await submitReview(caseId, { action, rationale, actor: actor || 'unnamed reviewer' });
      setRationale('');
      await loadCase();
    } catch (err) {
      setReviewError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: '3rem' }}>
        <RefreshCw className="spin" size={24} style={{ color: 'var(--accent)', marginBottom: '0.5rem' }} />
        <div>Loading case evidence from chain and store…</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: '2rem' }}>
        <div style={{ color: '#ef4444', marginBottom: '1rem' }}>{error || 'Case not found'}</div>
        <button className="btn btn-secondary" onClick={onBack}>
          <ArrowLeft size={14} /> Back to Cases
        </button>
      </div>
    );
  }

  const { case: caseInfo, findings, report, audit, conflict_count, missing_count, verified_count } = data;
  const facts = caseInfo.payload?.facts;
  const token = caseInfo.payload?.token;

  return (
    <div className="case-detail-container">
      {/* Back button & Title */}
      <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={14} />
          <span>Back to Cases</span>
        </button>
        <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {caseInfo.case_id} &middot; Opened {new Date(caseInfo.created_at * 1000).toLocaleString()}
        </span>
      </div>

      {/* Case Header Stat Banner */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <div className="panel-title" style={{ fontSize: '1.25rem' }}>
              {caseInfo.title}
            </div>
            <div className="panel-subtitle">
              Case State: <strong style={{ color: '#fff', textTransform: 'uppercase' }}>{caseInfo.state}</strong>
            </div>
          </div>
        </div>

        <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
          <div className="stat-box" style={{ borderColor: conflict_count > 0 ? 'rgba(239,68,68,0.4)' : 'var(--border)' }}>
            <div className="stat-label">Conflicts</div>
            <div className="stat-val" style={{ color: conflict_count > 0 ? '#ef4444' : '#fff' }}>
              {conflict_count}
            </div>
          </div>

          <div className="stat-box" style={{ borderColor: missing_count > 0 ? 'rgba(245,158,11,0.4)' : 'var(--border)' }}>
            <div className="stat-label">Missing Evidence</div>
            <div className="stat-val" style={{ color: missing_count > 0 ? '#f59e0b' : '#fff' }}>
              {missing_count}
            </div>
          </div>

          <div className="stat-box">
            <div className="stat-label">Total Findings</div>
            <div className="stat-val" style={{ color: '#06b6d4' }}>
              {findings.length}
            </div>
          </div>

          <div className="stat-box">
            <div className="stat-label">Review Decisions</div>
            <div className="stat-val" style={{ color: '#10b981' }}>
              {audit.length}
            </div>
          </div>
        </div>

        {facts && (
          <div style={{ background: '#0e1017', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.85rem 1rem', fontSize: '0.84rem', lineHeight: '1.6' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <div>
                <span className="muted">Tx Hash: </span>
                <code style={{ color: '#06b6d4' }}>{caseInfo.tx_hash}</code>
                <a
                  href={`https://polygonscan.com/tx/${caseInfo.tx_hash}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: '6px', color: '#06b6d4', verticalAlign: 'middle' }}
                >
                  <ExternalLink size={13} style={{ display: 'inline' }} />
                </a>
              </div>
              <div>
                <span className="muted">Block: </span>
                <code style={{ color: '#fff' }}>{facts.block_number}</code>
              </div>
              <div>
                <span className="muted">Confirmations: </span>
                <code style={{ color: '#10b981' }}>{facts.confirmations}</code>
              </div>
            </div>

            {token && (
              <div style={{ marginTop: '0.35rem', paddingTop: '0.35rem', borderTop: '1px solid var(--border-subtle)' }}>
                <span className="muted">Invoiced Contract: </span>
                <code style={{ color: '#fff' }}>{token.address}</code> &mdash; reports symbol{' '}
                <strong style={{ color: '#10b981' }}>"{token.symbol}"</strong>, {token.decimals} decimals (read on-chain).
              </div>
            )}
          </div>
        )}
      </div>

      {/* Findings Table (Conflicts first!) */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <div className="panel-title">
              <ShieldCheck size={18} color="#10b981" />
              <span>Deterministic Findings (Code-Verified)</span>
            </div>
            <div className="panel-subtitle">
              Established by mathematical code, with no language model involved. Conflicts listed first. Every claim cites explicit evidence.
            </div>
          </div>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th style={{ width: '110px' }}>Status</th>
                <th style={{ width: '160px' }}>Check Code</th>
                <th>Statement & Observation</th>
                <th style={{ width: '220px' }}>Citations</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f, idx) => (
                <tr key={idx}>
                  <td>
                    <span className={`status-tag ${f.status}`}>{f.status}</span>
                  </td>
                  <td className="mono" style={{ fontSize: '0.8rem', color: '#06b6d4' }}>
                    {f.code}
                  </td>
                  <td style={{ color: '#e5e7eb', fontSize: '0.86rem' }}>
                    {f.summary}
                  </td>
                  <td className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {f.evidence_ids && f.evidence_ids.length > 0 ? (
                      f.evidence_ids.map((id, i) => (
                        <div key={i} title={id}>
                          {id.length > 24 ? `${id.slice(0, 10)}…${id.slice(-8)}` : id}
                        </div>
                      ))
                    ) : (
                      <span style={{ color: 'var(--text-dim)' }}>nothing to cite</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* LLM Investigation & Structural Validator */}
      {report && (
        <div className="panel">
          <div className="panel-header">
            <div>
              <div className="panel-title">
                <ShieldAlert size={18} color="#06b6d4" />
                <span>LLM Investigation & Structural Validator</span>
              </div>
              <div className="panel-subtitle">
                Drafted by LLM, then independently validated against the deterministic layer. Unsupported claims rejected.
              </div>
            </div>
          </div>

          <div style={{ background: '#0e1118', border: '1px solid var(--border)', borderRadius: '6px', padding: '1rem', marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.88rem', color: '#f3f4f6', lineHeight: '1.6' }}>
              {report.summary}
            </div>
          </div>

          {report.validation && report.validation.lines && report.validation.lines.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                Validated Report Lines
              </div>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '100px' }}>Status</th>
                      <th style={{ width: '150px' }}>Rests On</th>
                      <th>Statement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.validation.lines.map((l, i) => (
                      <tr key={i}>
                        <td>
                          <span className={`status-tag ${l.status}`}>{l.status}</span>
                        </td>
                        <td className="mono" style={{ fontSize: '0.78rem', color: '#06b6d4' }}>
                          {l.finding_code || '—'}
                        </td>
                        <td style={{ fontSize: '0.84rem', color: '#d1d5db' }}>{l.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {report.hypotheses && report.hypotheses.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
                Competing Hypotheses
              </div>
              <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#d1d5db' }}>
                {report.hypotheses.map((h, i) => (
                  <li key={i} style={{ marginBottom: '0.5rem' }}>
                    <strong>{h.explanation}</strong>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                      Confirmed by: {h.would_be_confirmed_by} &middot; Ruled out by: {h.would_be_ruled_out_by}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Reviewer Console (Wispr Flow Dictation Friendly) */}
      <div className="panel" style={{ border: '1px solid #2d3345' }}>
        <div className="panel-header">
          <div>
            <div className="panel-title" style={{ color: '#fff' }}>
              <Mic size={18} color="#06b6d4" />
              <span>Record a Review Decision (Human in the Loop)</span>
            </div>
            <div className="panel-subtitle">
              Wispr Flow & OS Dictation friendly: no keystroke or paste interception. Rationale is required.
            </div>
          </div>
        </div>

        <form onSubmit={handleReviewSubmit}>
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Reviewer Name</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. Kevin Shah (Ops Lead)"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                autoComplete="off"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Decision Action</label>
              <select
                className="form-control"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                <option value="confirm">confirm — Confirm finding & close ticket</option>
                <option value="reject">reject — Reject resolution & keep active</option>
                <option value="request_evidence">request_evidence — Request additional documentation</option>
                <option value="reassign">reassign — Escalate / Reassign to specialist</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <label className="form-label" style={{ margin: 0 }}>Reviewer Rationale (Dictate or Type)</label>
              <div className="dictation-badge">
                <Mic size={11} />
                <span>Dictation Ready (Wispr Flow Fn hotkey)</span>
              </div>
            </div>
            {/* Plain native textarea with NO onPaste, NO onInput interception (D41/S15) */}
            <textarea
              id="rationale"
              name="rationale"
              className="form-control"
              required
              rows={4}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="Dictate your reasoning or type why you made this decision. Stored in append-only audit trail."
            />
          </div>

          {reviewError && (
            <div style={{ color: '#ef4444', fontSize: '0.84rem', marginBottom: '0.75rem' }}>
              {reviewError}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? (
              <>
                <RefreshCw className="spin" size={15} />
                <span>Recording Decision…</span>
              </>
            ) : (
              <>
                <Send size={15} />
                <span>Commit Decision to Audit Log</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* Decision History (Audit Log for this case) */}
      {audit && audit.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div>
              <div className="panel-title">
                <History size={18} />
                <span>Case Decision History ({audit.length})</span>
              </div>
              <div className="panel-subtitle">
                Append-only log: a subsequent decision adds an entry; it never replaces the previous one.
              </div>
            </div>
          </div>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Reviewer</th>
                  <th>Rationale</th>
                  <th>Entry ID</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((entry, idx) => (
                  <tr key={idx}>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {new Date(entry.at * 1000).toLocaleString()}
                    </td>
                    <td>
                      <span className="status-tag NEXT_STEP" style={{ fontSize: '0.7rem' }}>
                        {entry.action}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{entry.actor}</td>
                    <td style={{ fontSize: '0.85rem', color: '#d1d5db' }}>{entry.rationale}</td>
                    <td className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      {entry.entry_id}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

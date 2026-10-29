import React from 'react';
import { ShieldCheck, Activity, Terminal, Database, Scale, History, Flame } from 'lucide-react';

export default function Header({ activeTab, setActiveTab, status, casesCount, auditCount }) {
  return (
    <header className="app-header">
      <div className="header-top">
        <div className="brand-section">
          <div className="brand-logo">
            <ShieldCheck size={20} strokeWidth={2.4} />
          </div>
          <div>
            <div className="brand-title">TraceLedger</div>
          </div>
          <div className="badge-chain">
            <span className="pulse-dot"></span>
            <span>{status?.chain_name || 'polygon-pos'} (Chain {status?.chain_id || 137})</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div className="readonly-pill">
            <ShieldCheck size={13} />
            <span>Read-Only &middot; Never Moves Funds</span>
          </div>
        </div>
      </div>

      <nav className="header-nav">
        <button
          className={`nav-item ${activeTab === 'demo' ? 'active' : ''}`}
          onClick={() => setActiveTab('demo')}
        >
          <Flame size={15} color="#ef4444" />
          <span>Live Fire Demo</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'investigate' ? 'active' : ''}`}
          onClick={() => setActiveTab('investigate')}
        >
          <Terminal size={15} />
          <span>Investigate & Open Case</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'cases' ? 'active' : ''}`}
          onClick={() => setActiveTab('cases')}
        >
          <Activity size={15} />
          <span>Cases</span>
          <span className="tag-count">{casesCount}</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'benchmark' ? 'active' : ''}`}
          onClick={() => setActiveTab('benchmark')}
        >
          <Scale size={15} />
          <span>Benchmark (CP8)</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'graph' ? 'active' : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <Database size={15} />
          <span>Graph vs SQL</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          <History size={15} />
          <span>Audit Log</span>
          <span className="tag-count">{auditCount}</span>
        </button>
      </nav>
    </header>
  );
}

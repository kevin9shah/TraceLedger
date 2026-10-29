import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import LiveDemo from './components/LiveDemo';
import CaseCreator from './components/CaseCreator';
import CaseList from './components/CaseList';
import CaseDetail from './components/CaseDetail';
import BenchmarkView from './components/BenchmarkView';
import GraphExplorer from './components/GraphExplorer';
import AuditView from './components/AuditView';
import { fetchStatus, fetchCases, fetchAudit } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('demo');
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [status, setStatus] = useState(null);
  const [cases, setCases] = useState([]);
  const [auditCount, setAuditCount] = useState(0);

  const loadData = async () => {
    try {
      const [statusRes, casesRes, auditRes] = await Promise.all([
        fetchStatus(),
        fetchCases(),
        fetchAudit()
      ]);
      setStatus(statusRes);
      setCases(casesRes);
      setAuditCount(auditRes.length);
    } catch (err) {
      console.warn('Initial load error:', err);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleOpenCaseDetail = (caseId) => {
    setSelectedCaseId(caseId);
    setActiveTab('cases');
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab !== 'cases') {
      setSelectedCaseId(null);
    }
  };

  return (
    <div className="app-container">
      <Header
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        status={status}
        casesCount={cases.length}
        auditCount={auditCount}
      />

      <main className="main-content">
        {/* Core Disclaimer Banner from README */}
        <div className="disclaimer-banner">
          <div>
            <strong>Preliminary Tool:</strong> Business records are synthetic and labelled as such.
            Chain facts are read from live Polygon mainnet (137). Findings are evidence for a human decision, not a verdict. Read-only: never moves funds.
          </div>
        </div>

        {/* Tab Views */}
        {activeTab === 'demo' && (
          <LiveDemo
            onOpenCaseDetail={handleOpenCaseDetail}
            onCaseCreated={loadData}
          />
        )}

        {activeTab === 'investigate' && (
          <CaseCreator
            onOpenCaseDetail={handleOpenCaseDetail}
            onCaseCreated={loadData}
          />
        )}

        {activeTab === 'cases' && (
          selectedCaseId ? (
            <CaseDetail
              caseId={selectedCaseId}
              onBack={() => setSelectedCaseId(null)}
            />
          ) : (
            <CaseList
              cases={cases}
              onSelectCase={(id) => setSelectedCaseId(id)}
              onNewCaseClick={() => setActiveTab('investigate')}
            />
          )
        )}

        {activeTab === 'benchmark' && (
          <BenchmarkView />
        )}

        {activeTab === 'graph' && (
          <GraphExplorer />
        )}

        {activeTab === 'audit' && (
          <AuditView
            onSelectCase={(id) => {
              setSelectedCaseId(id);
              setActiveTab('cases');
            }}
          />
        )}
      </main>
    </div>
  );
}

/**
 * TraceLedger API client
 * Communicates with the Flask backend (/api/...)
 */

export async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/status offline, using fallback:', err);
    return {
      chain_name: 'polygon-pos',
      chain_id: 137,
      rpc_url: 'https://polygon-bor-rpc.publicnode.com',
      tokens: {
        '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359': {
          address: '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359',
          decimals: 6,
          symbol: 'USDC',
          name: 'USD Coin',
          env_label: 'USDC'
        },
        '0xc2132d05d31c914a87c6611c10748aeb04b58e8f': {
          address: '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
          decimals: 6,
          symbol: 'USDT0',
          name: 'USDT0',
          env_label: 'USDT'
        },
        '0x2791bca1f2de4661ed88a30c99a7a9449aa84174': {
          address: '0x2791bca1f2de4661ed88a30c99a7a9449aa84174',
          decimals: 6,
          symbol: 'USDC',
          name: 'USD Coin (PoS)',
          env_label: 'EXTRA'
        }
      },
      cases_count: 0,
      audit_count: 0,
      review_actions: ['confirm', 'reject', 'request_evidence', 'reassign'],
      disclaimer: 'Read-only: never moves funds and never edits ledgers. Business records are synthetic; chain facts read from live node.'
    };
  }
}

export async function fetchCases() {
  try {
    const res = await fetch('/api/cases');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/cases offline, returning empty array:', err);
    return [];
  }
}

export async function fetchCase(caseId) {
  const res = await fetch(`/api/case/${encodeURIComponent(caseId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function createCase(payload) {
  const res = await fetch('/api/case/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || 'Failed to open case');
  }
  return data;
}

export async function submitReview(caseId, { action, rationale, actor }) {
  const res = await fetch(`/api/case/${encodeURIComponent(caseId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, rationale, actor }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || 'Failed to record decision');
  }
  return data;
}

export async function fetchAudit() {
  try {
    const res = await fetch('/api/audit');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/audit offline:', err);
    return [];
  }
}

export async function fetchPresets() {
  try {
    const res = await fetch('/api/presets');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/presets offline:', err);
    return [];
  }
}

export async function fetchBenchmark() {
  try {
    const res = await fetch('/api/benchmark');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/benchmark offline:', err);
    return { results: {}, cases: [] };
  }
}

export async function fetchGraphRootCause() {
  try {
    const res = await fetch('/api/graph/root_cause');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend /api/graph/root_cause offline:', err);
    return {};
  }
}

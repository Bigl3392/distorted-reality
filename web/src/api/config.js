/**
 * Distorted Reality — API Endpoints and Configuration
 * Contract defined in workspace/distorted-reality/docs/API_M5.md
 * 
 * Strict rule: All endpoints reside here. If a route changes on the backend,
 * update this mapping. Never scatter path strings across UI components.
 */

export const API_BASE = '/api/v1';

export const ENDPOINTS = {
  healthz: '/healthz',
  datasets: `${API_BASE}/datasets`,
  intake: `${API_BASE}/intake`,
  runs: `${API_BASE}/runs`,
  run: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}`,
  runIntake: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/intake`,
  runStart: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/start`,
  runMri: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/mri`,
  runScan: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/scan`,
  runCouncil: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/council`,
  runExecutions: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/executions`,
  runPacket: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/packet`,
  runJournal: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/journal`,
  runApprove: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/approve`,
  runDownloadLink: (id) => `${API_BASE}/runs/${encodeURIComponent(id)}/download-link`,
  downloadFile: (token, type) => `${API_BASE}/download/${encodeURIComponent(token)}/${encodeURIComponent(type)}`,
  recordedRuns: `${API_BASE}/recorded-runs`,
  recordedRun: (recId) => `${API_BASE}/recorded-runs/${encodeURIComponent(recId)}`,
};

export const REQUIRED_SUPPRESSION_LIMITATION =
  "System-specific results are suppressed in public, by design, to protect the private association.";

export const CLAIM_DISCIPLINE_STATEMENT =
  "The calculation executed successfully under these assumptions. This does not establish that any intervention will improve an actual business.";

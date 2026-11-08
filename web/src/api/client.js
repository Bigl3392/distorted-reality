import { ENDPOINTS, REQUIRED_SUPPRESSION_LIMITATION } from './config';
import {
  MOCK_DATASETS,
  MOCK_INTAKE,
  MOCK_MRI,
  MOCK_COUNCIL,
  MOCK_EXECUTIONS,
  MOCK_PACKET,
  MOCK_RECORDED_RUNS,
} from './mockData';

class ApiClient {
  constructor() {
    // Explicit selection only: VITE_USE_MOCK === 'true'
    this.useMock = import.meta.env.VITE_USE_MOCK === 'true';
    this.mockRun = null;
  }

  isMockMode() {
    return this.useMock;
  }

  setMockMode(enable) {
    this.useMock = Boolean(enable);
  }

  getDataSource() {
    const originHost = (typeof window !== 'undefined' && window.location && window.location.host)
      ? window.location.host
      : '127.0.0.1';
    return this.useMock
      ? { type: 'MOCK_DEV', label: 'LOCAL BROWSER MOCK (STANDALONE ONLY)' }
      : { type: 'LIVE_M5_WSGI', label: `M5 CONTROL WSGI (${originHost})` };
  }

  async _request(url, options = {}) {
    if (this.useMock) {
      return this._handleMockRequest(url, options);
    }

    try {
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/json',
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...options.headers,
        },
        ...options,
      });

      // Special handling for 409 mode: recorded and 503 limits unset
      if (response.status === 409 || response.status === 503 || response.status === 429) {
        const errorData = await response.json().catch(() => ({}));
        const err = new Error(errorData.error || `Request failed with status ${response.status}`);
        err.status = response.status;
        err.data = errorData;
        throw err;
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const err = new Error(errorData.error || `HTTP error ${response.status}`);
        err.status = response.status;
        err.data = errorData;
        throw err;
      }

      return await response.json();
    } catch (networkError) {
      // S1 FIX: NEVER silently switch to mock mode on network failure!
      if (networkError.status !== undefined) {
        throw networkError;
      }
      const originHost = (typeof window !== 'undefined' && window.location && window.location.host)
        ? window.location.host
        : '127.0.0.1';
      const err = new Error(
        `Connection to M5 server failed at ${url}. Is M5 WSGI running on ${originHost}?`
      );
      err.status = 503;
      err.cause = networkError;
      throw err;
    }
  }

  async _handleMockRequest(url, options = {}) {
    // Artificial latency for realistic async interaction
    await new Promise((r) => setTimeout(r, 120));

    // GET /healthz
    if (url === ENDPOINTS.healthz) {
      return { ok: true };
    }

    // GET /datasets
    if (url === ENDPOINTS.datasets) {
      return MOCK_DATASETS;
    }

    // GET /intake
    if (url === ENDPOINTS.intake) {
      return MOCK_INTAKE;
    }

    // POST /runs
    if (url === ENDPOINTS.runs && options.method === 'POST') {
      const runId = 'run-001';
      this.mockRun = {
        run_id: runId,
        state: 'MRI_DONE',
        label: 'MRI_DONE',
        history: ['CREATED', 'DATASET_LOADED', 'MRI_DONE'],
        mri: MOCK_MRI,
      };
      return {
        run_id: runId,
        state: 'MRI_DONE',
        mri: MOCK_MRI,
      };
    }

    // POST /runs/{id}/intake
    if (url.endsWith('/intake') && options.method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const answers = body.answers || {};
      const count = Object.keys(answers).length;
      if (count !== 15) {
        const err = new Error('15 integer answers in 1..6 required');
        err.status = 422;
        err.data = { error: '15 integer answers in 1..6 required' };
        throw err;
      }
      for (const val of Object.values(answers)) {
        if (!Number.isInteger(val) || val < 1 || val > 6) {
          const err = new Error('15 integer answers in 1..6 required');
          err.status = 422;
          err.data = { error: '15 integer answers in 1..6 required' };
          throw err;
        }
      }

      // Compute standard half-up sum / 90 * 100
      const sum = Object.values(answers).reduce((a, b) => a + b, 0);
      const overall = Math.round((sum / 90) * 100);

      this.mockRun.state = 'SCAN_DONE';
      this.mockRun.history.push('SCAN_DONE');
      this.mockRun.scan = {
        label: 'SYNTHETIC',
        scan_version: '2',
        run_id: this.mockRun.run_id,
        intake_variant: 'paraphrase',
        overall: overall,
        recommendation: 'Review the AP reconciliation workflow evidence with the council.',
        limitations: [
          REQUIRED_SUPPRESSION_LIMITATION,
          'The deployed product computes only the overall index and performs no system-specific scoring.'
        ],
        routes_present: false,
        fees_present: false,
      };

      return this.mockRun.scan;
    }

    // POST /runs/{id}/start
    if (url.endsWith('/start') && options.method === 'POST') {
      this.mockRun.state = 'COUNCIL_EVIDENCE';
      // S3 FIX: Do not push 'STARTED' into persisted history; API states are CREATED, DATASET_LOADED, MRI_DONE, SCAN_DONE, COUNCIL_EVIDENCE...
      this.mockRun.history.push('COUNCIL_EVIDENCE');
      return { run_id: this.mockRun.run_id, state: 'STARTED' };
    }

    // GET /runs/{id}
    if (url.startsWith('/api/v1/runs/') && !url.includes('/', 14)) {
      if (!this.mockRun) {
        const err = new Error('Run not found');
        err.status = 404;
        throw err;
      }
      return {
        run_id: this.mockRun.run_id,
        state: this.mockRun.state,
        history: this.mockRun.history,
        label: this.mockRun.state,
      };
    }

    // GET /runs/{id}/mri
    if (url.endsWith('/mri')) {
      return MOCK_MRI;
    }

    // GET /runs/{id}/scan
    if (url.endsWith('/scan')) {
      return this.mockRun?.scan || MOCK_PACKET.scan;
    }

    // GET /runs/{id}/council
    if (url.endsWith('/council')) {
      return MOCK_COUNCIL;
    }

    // GET /runs/{id}/executions
    if (url.endsWith('/executions')) {
      return MOCK_EXECUTIONS;
    }

    // GET /runs/{id}/packet
    if (url.endsWith('/packet')) {
      return MOCK_PACKET;
    }

    // GET /runs/{id}/journal
    if (url.endsWith('/journal')) {
      return {
        entries: [
          { seq: 0, ts: '2026-11-05T15:00:00Z', kind: 'run_created', actor: 'control', entry_sha256: 'abcd0001...' },
          { seq: 1, ts: '2026-11-05T15:00:05Z', kind: 'dataset_loaded', actor: 'control', entry_sha256: 'abcd0002...' },
          { seq: 2, ts: '2026-11-05T15:00:10Z', kind: 'mri_done', actor: 'control', entry_sha256: 'abcd0003...' },
          { seq: 3, ts: '2026-11-05T15:01:00Z', kind: 'scan_done', actor: 'control', entry_sha256: 'abcd0004...' },
          { seq: 4, ts: '2026-11-05T15:02:00Z', kind: 'council_done', actor: 'broker', entry_sha256: 'abcd0005...' },
          { seq: 5, ts: '2026-11-05T15:02:30Z', kind: 'packet_built', actor: 'control', entry_sha256: 'abcd0006...' },
        ],
      };
    }

    // POST /runs/{id}/approve
    if (url.endsWith('/approve') && options.method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const updatedPacket = { ...MOCK_PACKET };
      if (body.action === 'view') {
        updatedPacket.approval_gate = {
          status: 'VIEWED',
          external_action_taken: false,
          confirmed_at: null,
        };
      } else if (body.action === 'confirm') {
        updatedPacket.approval_gate = {
          status: 'VIEWED_CONFIRMED',
          external_action_taken: false,
          confirmed_at: new Date().toISOString(),
        };
      }
      return { packet: updatedPacket };
    }

    // POST /runs/{id}/download-link
    if (url.endsWith('/download-link') && options.method === 'POST') {
      return {
        url: '/api/v1/download/tok-mock-998877',
        expires_in_seconds: 3600,
      };
    }

    // GET /recorded-runs
    if (url === ENDPOINTS.recordedRuns) {
      // S2 FIX: Mock data never fabricates recorded real runs. Genuine recorded runs are served by M5 from disk.
      return { recorded_runs: [] };
    }

    // GET /recorded-runs/{rec}
    if (url.startsWith('/api/v1/recorded-runs/')) {
      // S2 FIX: Mock branch does not claim genuine recorded execution.
      const err = new Error('No recorded runs exist in mock mode; recorded runs are served by M5 from disk.');
      err.status = 404;
      throw err;
    }

    throw new Error(`Unhandled mock route: ${url}`);
  }

  // High-level API methods
  async checkHealth() {
    return this._request(ENDPOINTS.healthz);
  }

  async getDatasets() {
    return this._request(ENDPOINTS.datasets);
  }

  async getIntake() {
    return this._request(ENDPOINTS.intake);
  }

  async createRun(datasetId) {
    return this._request(ENDPOINTS.runs, {
      method: 'POST',
      body: JSON.stringify({ dataset_id: datasetId }),
    });
  }

  async submitIntake(runId, answers) {
    return this._request(ENDPOINTS.runIntake(runId), {
      method: 'POST',
      body: JSON.stringify({ answers }),
    });
  }

  async startRun(runId) {
    return this._request(ENDPOINTS.runStart(runId), {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async getRun(runId) {
    return this._request(ENDPOINTS.run(runId));
  }

  async getMri(runId) {
    return this._request(ENDPOINTS.runMri(runId));
  }

  async getScan(runId) {
    return this._request(ENDPOINTS.runScan(runId));
  }

  async getCouncil(runId) {
    return this._request(ENDPOINTS.runCouncil(runId));
  }

  async getExecutions(runId) {
    return this._request(ENDPOINTS.runExecutions(runId));
  }

  async getPacket(runId) {
    return this._request(ENDPOINTS.runPacket(runId));
  }

  async getJournal(runId) {
    return this._request(ENDPOINTS.runJournal(runId));
  }

  async approveRun(runId, action) {
    return this._request(ENDPOINTS.runApprove(runId), {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  }

  async getDownloadLink(runId) {
    return this._request(ENDPOINTS.runDownloadLink(runId), {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async getRecordedRuns() {
    return this._request(ENDPOINTS.recordedRuns);
  }

  async getRecordedRun(recId) {
    return this._request(ENDPOINTS.recordedRun(recId));
  }
}

export const api = new ApiClient();

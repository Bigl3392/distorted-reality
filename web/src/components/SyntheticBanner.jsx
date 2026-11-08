import React from 'react';
import { Shield, Activity, Database, AlertTriangle } from 'lucide-react';

export default function SyntheticBanner({
  heartbeatOk = true,
  assuranceTier = 'T1',
  dataSource = null,
  onOpenRecordedRuns,
  isRecordedRun = false,
  recordedDate = null,
  runProvenance = null,
}) {
  const originHost = (typeof window !== 'undefined' && window.location && window.location.host)
    ? window.location.host
    : '127.0.0.1';
  const effectiveDataSource = dataSource || {
    type: 'LIVE_M5_WSGI',
    label: `M5 CONTROL WSGI (${originHost})`,
  };
  const isMock = effectiveDataSource?.type === 'MOCK_DEV';

  return (
    <header className="border-b border-fortress-700 bg-fortress-900/95 sticky top-0 z-50 backdrop-blur">
      {/* Topmost Mandatory Synthetic Notice Bar */}
      <div data-testid="synthetic-banner" className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-1 text-center text-xs font-mono tracking-wider text-amber-300 flex items-center justify-center gap-2">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        <span>
          SYNTHETIC DATA — SEED 20261103 — CALCULATION EXECUTED UNDER STATED ASSUMPTIONS ONLY
        </span>
        <span className="hidden sm:inline text-amber-500/60">|</span>
        <span className="hidden sm:inline text-amber-400/80">NO BUSINESS IMPROVEMENT CLAIMED</span>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand & Concept */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded bg-fortress-800 border border-fortress-600 flex items-center justify-center text-cyan-400 font-mono font-bold text-lg shadow-sm">
            DR
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-white">
                DISTORTED REALITY
              </h1>
              {isRecordedRun ? (
                <span className="px-2 py-0.5 text-xs font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
                  RECORDED REAL RUN ({recordedDate || 'ARCHIVE'})
                </span>
              ) : isMock ? (
                <span className="px-2 py-0.5 text-xs font-mono bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded" title="Explicit Browser Mock Harness">
                  MOCK DEV HARNESS
                </span>
              ) : (
                <span className="px-2 py-0.5 text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded" title="Connected to Served M5 API">
                  LIVE WORKFLOW
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 font-mono">
              AP Reconciliation · Containment & Proof Layer · Vultr
            </p>
          </div>
        </div>

        {/* Right Badges & Controls */}
        <div className="flex items-center gap-3">
          {/* Explicit Data Source Provenance (S1 Fix) */}
          <div
            data-testid="data-source-provenance"
            className={`hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono border ${
              isMock
                ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                : 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
            }`}
            title="Explicit backend data source"
          >
            <span>DATA SOURCE: {effectiveDataSource?.label}</span>
          </div>

          {/* Heartbeat Status */}
          <div
            data-testid="heartbeat-status"
            className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border ${
              heartbeatOk
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
            }`}
            title="Control plane heartbeat /healthz"
          >
            <Activity className="w-3.5 h-3.5 animate-pulse" />
            <span>{heartbeatOk ? 'CONTROL: HEALTHY' : `CONTROL: UNREACHABLE (${originHost})`}</span>
          </div>

          {/* Assurance Tier */}
          <div data-testid="tier-badge" className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono bg-fortress-800 text-slate-300 border border-fortress-700">
            <Shield className="w-3.5 h-3.5 text-cyan-400" />
            <span>TIER: {assuranceTier}</span>
          </div>

          {/* Recorded Runs Trigger */}
          {onOpenRecordedRuns && (
            <button
              onClick={onOpenRecordedRuns}
              data-testid="open-recorded-runs-btn"
              aria-label="Open Archived Recorded Runs"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono bg-fortress-800 hover:bg-fortress-700 text-slate-200 border border-fortress-600 transition-colors"
            >
              <Database className="w-3.5 h-3.5 text-amber-400" />
              <span>Recorded Runs</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

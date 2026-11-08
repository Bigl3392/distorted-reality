import React from 'react';
import { Package, ArrowRight, ShieldCheck, AlertCircle, Terminal, FileText, CheckCircle2, XCircle } from 'lucide-react';
import { REQUIRED_SUPPRESSION_LIMITATION } from '../api/config';

export default function Stage4ExecutionsPacket({
  packetData = null,
  executions = [],
  onNext,
  isFailed = false,
  packetUnavailable = false,
  failedReason = null,
}) {
  if (!packetData) {
    if (isFailed || packetUnavailable) {
      return (
        <div data-testid="packet-unavailable-alert" className="p-6 rounded-lg bg-rose-500/10 border border-rose-500/30 space-y-3 font-mono">
          <div className="flex items-center gap-2 text-rose-300 font-bold text-sm">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>RUN FAILED CLOSED — EVIDENCE PACKET UNAVAILABLE</span>
          </div>
          <p className="text-xs text-rose-200">
            {failedReason ? `Failure reason: ${failedReason}` : 'The run terminated in a fail-closed state.'}
          </p>
          <p className="text-xs text-slate-400">
            The control plane halted execution deterministically. An incomplete evidence packet could not be retrieved from the server.
          </p>
        </div>
      );
    }

    return (
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-8 text-center text-slate-400 font-mono text-sm">
        Evidence packet is not yet assembled. Awaiting completion of Blackbox execution and control-plane metrics recomputation.
      </div>
    );
  }

  const isIncomplete = packetData.packet_status === 'INCOMPLETE';

  return (
    <div className="space-y-6">
      {/* Stage 4 Header */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 mb-2">
              <Package className="w-3.5 h-3.5" />
              <span>STAGE 4: EVIDENCE PACKET & SANDBOX RECEIPTS</span>
            </div>
            <h2 className="text-xl font-bold text-white">
              Deterministic Proof Layer
            </h2>
            <p className="text-sm text-slate-400 mt-1 max-w-3xl">
              The control plane recomputed all operational metrics from raw exported events and evaluated every completion claim against evidence. Self-reported metrics from inside the container are never trusted.
            </p>
          </div>
          <div className="text-right text-xs font-mono text-slate-500">
            <div>PACKET: {packetData.packet_sha256?.substring(0, 16)}...</div>
            <div>TIER: {packetData.assurance_tier || 'T1'}</div>
          </div>
        </div>
      </div>

      {/* Incomplete Packet Warning if Run Failed Closed */}
      {isIncomplete && (
        <div data-testid="incomplete-packet-alert" className="p-5 rounded-lg bg-rose-500/10 border border-rose-500/30 space-y-2">
          <div className="flex items-center gap-2 text-rose-300 font-mono font-bold text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>RUN FAILED CLOSED — INCOMPLETE EVIDENCE PACKET ISSUED</span>
          </div>
          <p className="text-xs text-rose-200 font-mono">
            Failed at state: <span className="font-bold">{packetData.failed_at}</span> · Reason: {packetData.failure_reason}
          </p>
          <p className="text-xs text-slate-300">
            Per spec, a failed run terminates deterministically with an INCOMPLETE packet stating that no winner was chosen.
          </p>
        </div>
      )}

      {/* Claim Discipline Banner (Mandatory Schema Const) */}
      <div data-testid="claim-discipline-statement" className="p-4 rounded-lg bg-fortress-800 border border-fortress-700">
        <div className="text-xs font-mono text-slate-400 uppercase tracking-wider mb-1">
          Governing Claim Discipline Statement
        </div>
        <div className="text-sm font-mono text-cyan-300 italic">
          "{packetData.claim_statement}"
        </div>
      </div>

      {/* Synthetic Dataset Disclosure Notice */}
      {packetData.synthetic_notice && (
        <div data-testid="packet-synthetic-notice" className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-xs font-bold uppercase tracking-wide flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>{packetData.synthetic_notice}</span>
        </div>
      )}

      {/* Sandbox Execution Receipts */}
      <div data-testid="execution-receipts-container" className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-center justify-between pb-4 border-b border-fortress-700 mb-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span>Blackbox Sandbox Run Receipts</span>
          </h3>
          <span className="text-xs font-mono text-slate-400">
            FRESH CONTAINER PER ATTEMPT · TIME & MEMORY CAPPED
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(packetData.executions || executions).map((ex, idx) => (
            <div key={idx} className="p-4 rounded-lg bg-fortress-900 border border-fortress-700 font-mono text-xs space-y-3">
              <div className="flex items-center justify-between border-b border-fortress-800 pb-2">
                <span className="text-cyan-400 font-bold uppercase">{ex.path_id} (Attempt {ex.attempt})</span>
                <span className={`px-2 py-0.5 rounded text-[11px] ${
                  ex.termination === 'normal'
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                }`}>
                  {ex.termination} (exit {ex.exit_status})
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-slate-400">
                <div>Container ID:</div>
                <div className="text-slate-200 text-right">{ex.sandbox_id}</div>
                <div>Destroy Verified:</div>
                <div className="text-slate-200 text-right">{ex.destroy_verified ? 'YES' : 'NO'}</div>
                <div>Peak Memory:</div>
                <div className="text-slate-200 text-right">{ex.peak_memory_mb || 'N/A'} MB</div>
                <div>Canary Secret Leak:</div>
                <div className="text-emerald-400 text-right font-semibold">
                  {ex.secret_scan?.canary_present_in_env ? 'LEAK DETECTED' : 'CLEAN (ABSENT)'}
                </div>
              </div>

              {/* Claims-vs-Evidence Outcome */}
              <div className="border-t border-fortress-800 pt-2 space-y-1">
                <div className="flex justify-between text-slate-400">
                  <span>Claims Check:</span>
                  <span className={ex.claim_check?.unsupported > 0 ? 'text-amber-400 font-bold' : 'text-emerald-400'}>
                    {ex.claim_check?.supported}/{ex.claim_check?.claims_total} Supported
                    {ex.claim_check?.unsupported > 0 && ` (${ex.claim_check.unsupported} UNSUPPORTED)`}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Metrics Discrepancy:</span>
                  <span className={ex.metrics_discrepancy ? 'text-rose-400 font-bold' : 'text-slate-300'}>
                    {ex.metrics_discrepancy ? 'DISCREPANCY DETECTED' : 'NONE (EXACT MATCH)'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Side-by-Side Decision Outcome */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Pre-registered Decision Rule Outcome */}
        <div data-testid="decision-rule-card" className="p-6 rounded-lg bg-fortress-850 border border-fortress-700">
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase tracking-wider mb-2">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            <span>Pre-Registered Decision Rule (Normative)</span>
          </div>
          <div className="text-lg font-bold text-white font-mono mb-1">
            {packetData.outcome?.result}
          </div>
          <p className="text-xs text-slate-400 font-mono mb-4">
            Preferred Path: <span className="text-cyan-300 font-semibold">{packetData.outcome?.preferred_path_id || 'NONE'}</span>
          </p>
          <div className="p-3 rounded bg-fortress-900 border border-fortress-700 text-xs font-mono text-slate-300 leading-relaxed">
            {packetData.outcome?.basis}
          </div>
        </div>

        {/* Council Qualitative Recommendation */}
        <div data-testid="council-qualitative-card" className="p-6 rounded-lg bg-fortress-850 border border-fortress-700">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 uppercase tracking-wider mb-2">
            <FileText className="w-4 h-4 text-slate-400" />
            <span>Council Decision Role (Qualitative)</span>
          </div>
          <div className="text-lg font-bold text-slate-200 font-mono mb-1">
            Option: {packetData.council?.decision?.recommended_label || 'NONE'}
          </div>
          <p className="text-xs text-slate-400 font-mono mb-4">
            Deliberated under blinded neutral labels
          </p>
          <div className="p-3 rounded bg-fortress-900 border border-fortress-700 text-xs text-slate-300 leading-relaxed font-mono">
            {packetData.council?.decision?.comparison?.find(c => c.label === packetData.council?.decision?.recommended_label)?.rationale || 'Deliberation recorded in packet.'}
          </div>
        </div>
      </div>

      {/* Recomputed Metrics Summary Table */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <h3 className="text-base font-bold text-white mb-3">
          Control-Plane Recomputed Metrics
        </h3>
        <div className="overflow-x-auto border border-fortress-700 rounded-lg">
          <table data-testid="recomputed-metrics-table" className="w-full text-left text-xs font-mono">
            <thead className="bg-fortress-800 text-slate-300 border-b border-fortress-700">
              <tr>
                <th className="py-2.5 px-3">Path</th>
                <th className="py-2.5 px-3">Exceptions Caught</th>
                <th className="py-2.5 px-3">False Alarms</th>
                <th className="py-2.5 px-3">Unsupported Claims</th>
                <th className="py-2.5 px-3">Manual Touches</th>
                <th className="py-2.5 px-3">Median Cycle Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-fortress-700/60 bg-fortress-900 text-slate-200">
              {(packetData.executions || executions).map((ex, i) => (
                <tr key={i} className="hover:bg-fortress-800/40">
                  <td className="py-2 px-3 font-bold text-cyan-400 uppercase">{ex.path_id}</td>
                  <td className="py-2 px-3">{ex.metrics_recomputed?.exceptions_caught ?? 'N/A'}</td>
                  <td className="py-2 px-3">{ex.metrics_recomputed?.false_alarms ?? '0'}</td>
                  <td className="py-2 px-3">
                    <span className={ex.metrics_recomputed?.unsupported_claims > 0 ? 'text-amber-400 font-bold' : 'text-slate-300'}>
                      {ex.metrics_recomputed?.unsupported_claims ?? '0'}
                    </span>
                  </td>
                  <td className="py-2 px-3">{ex.metrics_recomputed?.manual_touches ?? 'N/A'}</td>
                  <td className="py-2 px-3 text-slate-400 italic">
                    Not computed in current timing model
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Honesty, Assumptions, Unknowns & Limitations Section */}
      <div data-testid="limitations-section" className="bg-fortress-850 border border-fortress-700 rounded-lg p-6 space-y-6">
        <div>
          <h3 className="text-base font-bold text-white">
            Governing Assumptions, Disclosed Unknowns, and Honest Limitations
          </h3>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Required cryptographic context and verification constraints from the frozen specification.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Assumptions */}
          {packetData.assumptions && packetData.assumptions.length > 0 && (
            <div data-testid="packet-assumptions-card" className="p-4 rounded-lg bg-fortress-900 border border-fortress-700 text-xs">
              <span className="font-mono font-bold text-cyan-400 block mb-2">Governing Assumptions:</span>
              <ul className="list-disc list-inside space-y-1.5 text-slate-300 font-mono">
                {packetData.assumptions.map((item, idx) => (
                  <li key={idx} className="leading-relaxed">{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Unknowns */}
          {packetData.unknowns && packetData.unknowns.length > 0 && (
            <div data-testid="packet-unknowns-card" className="p-4 rounded-lg bg-fortress-900 border border-fortress-700 text-xs">
              <span className="font-mono font-bold text-amber-400 block mb-2">Disclosed Operational Unknowns:</span>
              <ul className="list-disc list-inside space-y-1.5 text-slate-300 font-mono">
                {packetData.unknowns.map((item, idx) => (
                  <li key={idx} className="leading-relaxed">{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* What This Did NOT Prove */}
          {packetData.did_not_prove && packetData.did_not_prove.length > 0 && (
            <div data-testid="packet-did-not-prove-card" className="p-4 rounded-lg bg-fortress-900 border border-fortress-700 text-xs">
              <span className="font-mono font-bold text-rose-400 block mb-2">What This Did NOT Prove:</span>
              <ul className="list-disc list-inside space-y-1.5 text-slate-300 font-mono">
                {packetData.did_not_prove.map((item, idx) => (
                  <li key={idx} className="leading-relaxed">{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Governing Limitations */}
          {packetData.limitations && packetData.limitations.length > 0 && (
            <div data-testid="packet-limitations-card" className="p-4 rounded-lg bg-fortress-900 border border-fortress-700 text-xs">
              <span className="font-mono font-bold text-purple-400 block mb-2">Governing Limitations:</span>
              <ul className="list-disc list-inside space-y-1.5 text-slate-300 font-mono">
                {packetData.limitations.map((item, idx) => (
                  <li key={idx} className="leading-relaxed">{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Required suppression text alert box */}
        <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono">
          <div className="font-bold mb-1">Required Disclosure Limitation:</div>
          <div>{REQUIRED_SUPPRESSION_LIMITATION}</div>
        </div>
      </div>

      {/* Transition Action */}
      <div className="pt-4 flex justify-end">
        <button
          onClick={onNext}
          data-testid="proceed-to-stage-5-btn"
          aria-label="Proceed to Stage 5: Human Approval Gate & Verification Downloads"
          className="flex items-center gap-2 px-5 py-2.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-colors shadow-sm"
        >
          <span>Proceed to Stage 5: Human Approval Gate & Verification Downloads</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

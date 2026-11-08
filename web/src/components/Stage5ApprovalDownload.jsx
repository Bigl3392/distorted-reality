import React, { useState } from 'react';
import { ShieldCheck, Download, CheckCircle2, Lock, FileCode, AlertCircle, Copy, Terminal } from 'lucide-react';
import { ENDPOINTS } from '../api/config';

export default function Stage5ApprovalDownload({
  packetData,
  onApprove,
  onGenerateDownloadLink,
  downloadToken = null,
  loading = false,
  isViewed: isViewedProp = false,
}) {
  const [localViewed, setLocalViewed] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  const approvalStatus = packetData?.approval_gate?.status || 'PENDING';
  const isConfirmed = approvalStatus === 'VIEWED_CONFIRMED';
  const isViewed = isViewedProp || localViewed || approvalStatus === 'VIEWED' || isConfirmed;

  const handleView = async () => {
    try {
      await onApprove('view');
      setLocalViewed(true);
    } catch {
      // handled in parent
    }
  };

  const verifyCmd = 'python3 tools/verify_packet.py <bundle_dir>';

  const handleCopyCmd = () => {
    navigator.clipboard?.writeText(verifyCmd);
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Stage 5 Header */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 mb-2">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>STAGE 5: HUMAN APPROVAL GATE & VERIFICATION BUNDLE</span>
            </div>
            <h2 className="text-xl font-bold text-white">
              Controlled Human Review & Offline Verification
            </h2>
            <p className="text-sm text-slate-400 mt-1 max-w-3xl">
              Approval confirms human review of the generated evidence packet and hashes. Under the Blast Radius Zero containment contract, human approval performs no external action, executes no payments, and touches no external infrastructure.
            </p>
          </div>
          <div className="text-right text-xs font-mono text-slate-500">
            <div>GATE: DR-V08 (Approval Gate)</div>
            <div>STATUS: {approvalStatus}</div>
          </div>
        </div>
      </div>

      {/* Mandatory External Action Notice */}
      <div data-testid="containment-contract-notice" className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
        <div className="text-xs font-mono text-emerald-300">
          <div className="font-bold text-emerald-200 uppercase tracking-wider mb-0.5">
            CONTAINMENT CONTRACT: EXTERNAL_ACTION_TAKEN: FALSE
          </div>
          <div>
            Approval seals the packet for cryptographic verification. No payments are made, no vendor notifications are dispatched, and no files outside the designated audit trail are touched.
          </div>
        </div>
      </div>

      {/* Approval Actions Workflow */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6 space-y-6">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Lock className="w-4 h-4 text-cyan-400" />
          <span>Two-Phase Review Confirmation</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Step 1: View Packet */}
          <div className={`p-5 rounded-lg border font-mono text-xs ${
            isViewed
              ? 'bg-fortress-900 border-emerald-500/50 text-slate-200'
              : 'bg-fortress-900 border-fortress-700 text-slate-400'
          }`}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold uppercase">1. View Evidence Packet</span>
              {isViewed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <span className="text-[11px] px-1.5 py-0.5 bg-fortress-800 rounded">PENDING</span>
              )}
            </div>
            <p className="text-slate-400 mb-4">
              Inspect the hash-chained journal entries, sandbox receipts, and recomputed metrics.
            </p>
            <button
              onClick={handleView}
              disabled={loading || isViewed}
              data-testid="view-packet-btn"
              aria-label="Mark Packet as Inspected"
              className="w-full py-2 px-3 rounded bg-fortress-800 hover:bg-fortress-700 disabled:opacity-50 text-slate-200 border border-fortress-600 transition-colors"
            >
              {isViewed ? 'Packet Inspected' : 'Mark Packet as Inspected'}
            </button>
          </div>

          {/* Step 2: Confirm Review */}
          <div className={`p-5 rounded-lg border font-mono text-xs ${
            isConfirmed
              ? 'bg-fortress-900 border-emerald-500/50 text-slate-200'
              : 'bg-fortress-900 border-fortress-700 text-slate-400'
          }`}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold uppercase">2. Confirm Human Approval</span>
              {isConfirmed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <span className="text-[11px] px-1.5 py-0.5 bg-fortress-800 rounded">LOCKED</span>
              )}
            </div>
            <p className="text-slate-400 mb-4">
              Cryptographically seal the review state in the journal (`VIEWED_CONFIRMED`).
            </p>
            <button
              onClick={() => onApprove('confirm')}
              disabled={loading || !isViewed || isConfirmed}
              data-testid="confirm-approval-btn"
              aria-label="Seal Human Approval"
              className="w-full py-2 px-3 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium transition-colors"
            >
              {isConfirmed ? 'Human Review Confirmed' : 'Seal Human Approval'}
            </button>
          </div>
        </div>
      </div>

      {/* Verification Download Bundle */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6 space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-fortress-700">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Download className="w-4 h-4 text-cyan-400" />
              <span>Offline Verification Bundle</span>
            </h3>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              Download the complete artifact bundle to run independent offline cryptographic checks with `verify_packet.py`.
            </p>
          </div>
          {!downloadToken && (
            <button
              onClick={onGenerateDownloadLink}
              disabled={loading}
              data-testid="generate-token-btn"
              aria-label="Generate Scoped Token"
              className="px-4 py-2 rounded bg-fortress-800 hover:bg-fortress-700 text-cyan-300 text-xs font-mono border border-fortress-600 transition-colors"
            >
              Generate Scoped Token
            </button>
          )}
        </div>

        {downloadToken && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { name: 'evidence_packet.json', type: 'packet', icon: FileCode },
                { name: 'journal.jsonl', type: 'journal', icon: Terminal },
                { name: 'events.json', type: 'events', icon: FileCode },
                { name: 'decision_rule.yaml', type: 'rule', icon: FileCode },
              ].map((f) => (
                <a
                  key={f.type}
                  href={ENDPOINTS.downloadFile(downloadToken, f.type)}
                  download={f.name}
                  data-testid={`download-link-${f.type}`}
                  aria-label={`Download ${f.name}`}
                  className="p-3 rounded-lg bg-fortress-900 border border-fortress-700 hover:border-cyan-500 flex flex-col items-center justify-center text-center group transition-colors"
                >
                  <f.icon className="w-5 h-5 text-cyan-400 mb-2 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-mono text-slate-200 font-semibold">{f.name}</span>
                  <span className="text-[10px] font-mono text-slate-500 mt-1">Download</span>
                </a>
              ))}
            </div>

            {/* Offline CLI Instruction */}
            <div className="p-4 rounded-lg bg-fortress-900 border border-fortress-800 text-xs font-mono">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span>Independent Verification Command:</span>
                <button
                  onClick={handleCopyCmd}
                  data-testid="copy-verify-cmd-btn"
                  aria-label="Copy verification command"
                  className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{copiedCmd ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <code data-testid="verify-cmd-code" className="text-cyan-300 block bg-fortress-950 p-2.5 rounded border border-fortress-800 select-all">
                {verifyCmd}
              </code>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

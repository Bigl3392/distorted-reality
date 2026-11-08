import React, { useState } from 'react';
import { X, Database, Calendar, ArrowRight, ShieldCheck } from 'lucide-react';

export default function RecordedRunsModal({
  isOpen,
  onClose,
  recordedRuns = [],
  onSelectRecordedRun,
}) {
  const [selectedId, setSelectedId] = useState(null);

  if (!isOpen) return null;

  return (
    <div data-testid="recorded-runs-modal" className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="bg-fortress-850 border border-fortress-700 rounded-xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-fortress-700">
          <div className="flex items-center gap-2.5">
            <Database className="w-5 h-5 text-amber-400" />
            <div>
              <h3 className="text-base font-bold text-white">
                Archived Real Execution Runs
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Real Vultr executions preserved for audit and evaluation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            data-testid="close-recorded-modal-btn"
            aria-label="Close recorded runs modal"
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-fortress-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-4">
          <div className="p-3 rounded bg-fortress-900 border border-fortress-700/80 text-xs font-mono text-slate-300">
            Recorded runs placed by the operator; each passed schema and hash checks.
          </div>

          <div className="space-y-2">
            {recordedRuns.length === 0 ? (
              <div data-testid="empty-recorded-runs-msg" className="p-6 text-center text-xs font-mono text-slate-500">
                No recorded runs found in archive directory.
              </div>
            ) : (
              recordedRuns.map((r) => {
                const isSelected = selectedId === r.recorded_run_id;
                return (
                  <div
                    key={r.recorded_run_id}
                    data-testid={`recorded-run-${r.recorded_run_id}`}
                    aria-label={`Recorded run ${r.recorded_run_id}`}
                    onClick={() => setSelectedId(r.recorded_run_id)}
                    className={`p-4 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-fortress-800 border-amber-500'
                        : 'bg-fortress-900 border-fortress-700 hover:border-fortress-600'
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-xs mb-1">
                      <span className="font-bold text-amber-400">{r.recorded_run_id}</span>
                      <span className="text-slate-400 flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>{r.recorded_on}</span>
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      Target Run ID: <span className="text-slate-200">{r.run_id}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-fortress-700 bg-fortress-900 flex justify-end gap-3">
          <button
            onClick={onClose}
            data-testid="cancel-recorded-modal-btn"
            aria-label="Cancel recorded runs selection"
            className="px-4 py-2 rounded text-xs font-mono text-slate-300 hover:bg-fortress-800 border border-fortress-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (selectedId) {
                onSelectRecordedRun(selectedId);
                onClose();
              }
            }}
            disabled={!selectedId}
            data-testid="load-recorded-run-btn"
            aria-label="Load Recorded Run"
            className="flex items-center gap-2 px-4 py-2 rounded text-xs font-mono bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-medium transition-colors"
          >
            <span>Load Recorded Run</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

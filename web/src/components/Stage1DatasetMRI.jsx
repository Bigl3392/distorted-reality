import React from 'react';
import { Database, Scan, ArrowRight, ShieldAlert, CheckCircle, Clock } from 'lucide-react';

export default function Stage1DatasetMRI({
  datasets = [],
  selectedDatasetId,
  onSelectDataset,
  onRunMri,
  loading = false,
  mriData = null,
  onNext,
}) {
  return (
    <div className="space-y-6">
      {/* Stage 1 Header Card */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 mb-2">
              <Scan className="w-3.5 h-3.5" />
              <span>STAGE 1: WORKFLOW INTAKE & DIGITAL MRI</span>
            </div>
            <h2 className="text-xl font-bold text-white">
              Deterministic AP Workflow Inventory
            </h2>
            <p className="text-sm text-slate-400 mt-1 max-w-3xl">
              Select the bundled synthetic restaurant AP dataset. The Digital MRI scanner executes deterministic control-plane code (no LLMs) to inventory steps, role handoffs, and stall points. It authorizes nothing and changes nothing.
            </p>
          </div>
          <div className="text-right text-xs font-mono text-slate-500">
            <div>RULE: DR-F01 (No Uploads)</div>
            <div>STATUS: READ-ONLY AUDIT</div>
          </div>
        </div>

        {/* Dataset Selection */}
        <div className="mt-6 pt-6 border-t border-fortress-700/80">
          <label className="block text-xs font-mono uppercase text-slate-400 mb-2">
            Available Synthetic Dataset (Bundled Single Workflow)
          </label>
          <div className="grid grid-cols-1 gap-3">
            {datasets.map((ds) => (
              <div
                key={ds.dataset_id}
                role="button"
                tabIndex={0}
                data-testid={`dataset-option-${ds.dataset_id}`}
                aria-label={`Select dataset ${ds.dataset_id}`}
                onClick={() => onSelectDataset(ds.dataset_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectDataset(ds.dataset_id);
                  }
                }}
                className={`flex items-center justify-between p-4 rounded-lg border cursor-pointer transition-all ${
                  selectedDatasetId === ds.dataset_id
                    ? 'bg-fortress-800 border-cyan-500 shadow-sm'
                    : 'bg-fortress-900 border-fortress-700 hover:border-fortress-600'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Database className="w-5 h-5 text-cyan-400" />
                  <div>
                    <div className="text-sm font-semibold text-white font-mono">
                      {ds.dataset_id}
                    </div>
                    <div className="text-xs text-slate-400">
                      Synthetic AP Workflow · Flagship Restaurant · 4 Locations
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs font-mono">
                  <span className="px-2.5 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded">
                    {ds.label}
                  </span>
                  <span className="text-slate-300">
                    {ds.case_count} cases (1,400 events)
                  </span>
                </div>
              </div>
            ))}
          </div>

          {!mriData && (
            <div className="mt-6 flex justify-end">
              <button
                onClick={onRunMri}
                disabled={loading || !selectedDatasetId}
                data-testid="run-mri-btn"
                aria-label="Load Dataset & Run Digital MRI"
                className="flex items-center gap-2 px-5 py-2.5 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-sm transition-colors shadow-sm"
              >
                <Scan className="w-4 h-4" />
                <span>{loading ? 'Executing Deterministic Scan...' : 'Load Dataset & Run Digital MRI'}</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* MRI Inventory Results */}
      {mriData && (
        <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6 space-y-6">
          <div className="flex items-center justify-between flex-wrap gap-2 pb-4 border-b border-fortress-700">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white">
                  Digital MRI Inventory Result
                </h3>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  <span>DETERMINISTIC (NO MODEL)</span>
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                SHA-256: {mriData.inventory_sha256} · Scanned: {mriData.scanned_at}
              </p>
            </div>
            <div className="text-xs font-mono bg-fortress-800 px-3 py-1.5 rounded border border-fortress-700 text-slate-300">
              AUTHORIZES: <span className="text-rose-400 font-bold uppercase">{mriData.authorizes}</span>
            </div>
          </div>

          {/* Workflow Steps Table */}
          <div>
            <h4 className="text-xs font-mono uppercase text-slate-400 mb-3">
              Inventoried AP Steps (7 Total)
            </h4>
            <div className="overflow-x-auto border border-fortress-700 rounded-lg">
              <table data-testid="mri-steps-table" className="w-full text-left text-xs font-mono">
                <thead className="bg-fortress-800 text-slate-300 border-b border-fortress-700">
                  <tr>
                    <th className="py-2.5 px-3">Step</th>
                    <th className="py-2.5 px-3">Role</th>
                    <th className="py-2.5 px-3">Input → Output</th>
                    <th className="py-2.5 px-3">Handoff To</th>
                    <th className="py-2.5 px-3">Median Wait</th>
                    <th className="py-2.5 px-3">Anomalies / Claims</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-fortress-700/60 bg-fortress-900/60 text-slate-200">
                  {mriData.steps.map((st) => (
                    <tr key={st.step_id} className="hover:bg-fortress-800/40">
                      <td className="py-2 px-3 font-semibold text-cyan-400">
                        {st.step_id}. {st.name}
                      </td>
                      <td className="py-2 px-3 text-slate-300">{st.owner_role}</td>
                      <td className="py-2 px-3 text-slate-400">
                        {st.input_type} → {st.output_type}
                      </td>
                      <td className="py-2 px-3 text-slate-300">{st.handoff_to}</td>
                      <td className="py-2 px-3 flex items-center gap-1 text-slate-300">
                        <Clock className="w-3 h-3 text-slate-500" />
                        <span>{st.median_duration_min} min</span>
                      </td>
                      <td className="py-2 px-3">
                        {st.claimed_without_evidence_count > 0 ? (
                          <span className="text-amber-400 font-bold bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">
                            {st.claimed_without_evidence_count} unverified claims
                          </span>
                        ) : (
                          <span className="text-slate-500">Normal (0 bare claims)</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Handoffs & Stall Points Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-fortress-900 border border-fortress-700">
              <h5 className="text-xs font-mono uppercase text-slate-400 mb-2 flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>Inter-Role Handoff Delays</span>
              </h5>
              <div className="space-y-2 text-xs font-mono">
                {mriData.handoffs.map((h, i) => (
                  <div key={i} className="flex justify-between items-center py-1 border-b border-fortress-800 last:border-0">
                    <span className="text-slate-300">
                      {h.from_role} → {h.to_role}
                    </span>
                    <span className="text-amber-400 font-semibold">
                      {h.median_wait_min} min median
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 rounded-lg bg-fortress-900 border border-fortress-700">
              <h5 className="text-xs font-mono uppercase text-slate-400 mb-2 flex items-center gap-2">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                <span>Detected Bottlenecks & Stall Points</span>
              </h5>
              <div className="space-y-2 text-xs font-mono">
                {mriData.stall_points.map((sp, i) => (
                  <div key={i} className="flex justify-between items-center py-1 border-b border-fortress-800 last:border-0">
                    <span className="text-slate-300">
                      Step {sp.step_id}: {sp.reason}
                    </span>
                    <span className="text-rose-400 font-semibold">
                      {(sp.rate * 100).toFixed(1)}% stall rate
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Transition Action */}
          <div className="pt-4 border-t border-fortress-700 flex justify-end">
            <button
              onClick={onNext}
              data-testid="proceed-to-stage-2-btn"
              aria-label="Proceed to Stage 2: AP Workflow Assessment"
              className="flex items-center gap-2 px-5 py-2.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-colors shadow-sm"
            >
              <span>Proceed to Stage 2: AP Workflow Assessment</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

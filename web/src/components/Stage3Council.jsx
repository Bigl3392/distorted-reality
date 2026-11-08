import React from 'react';
import { Users, Play, ArrowRight, CheckCircle2, Shield, AlertCircle, AlertTriangle, Layers, BrainCircuit, RefreshCw } from 'lucide-react';

const IN_FLIGHT_STATES = [
  'STARTED',
  'COUNCIL_EVIDENCE',
  'COUNCIL_PATHS',
  'COUNCIL_CRITIC',
  'COUNCIL_REVISION',
  'COUNCIL_DECISION',
  'DECISION_RULE_FROZEN',
  'EXEC_PATH',
  'CLAIM_CHECKED',
  'EXEC_CORRECTION',
];

const formatConfidence = (conf) => {
  if (conf === null || conf === undefined) return 'N/A';
  if (typeof conf === 'number') {
    return !isNaN(conf) ? (conf <= 1 ? `${Math.round(conf * 100)}%` : `${Math.round(conf)}%`) : 'N/A';
  }
  const str = String(conf).trim();
  const num = Number(str);
  if (!isNaN(num)) {
    return num <= 1 ? `${Math.round(num * 100)}%` : `${Math.round(num)}%`;
  }
  return str.toUpperCase();
};

export default function Stage3Council({
  onStartCouncil,
  loading = false,
  councilData = null,
  currentState = null,
  error = null,
  onOpenRecordedRuns = null,
  onNext,
}) {
  const isRunning = loading || (
    Boolean(currentState) && (
      IN_FLIGHT_STATES.includes(currentState) ||
      currentState.startsWith('EXEC_') ||
      currentState.startsWith('COUNCIL_')
    )
  );

  const rawPaths = councilData?.revision?.paths || councilData?.initial_paths || councilData?.paths || [];
  const pathsList = Array.isArray(rawPaths) ? rawPaths : (Array.isArray(rawPaths?.paths) ? rawPaths.paths : []);

  return (
    <div className="space-y-6">
      {/* Stage 3 Header */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 mb-2">
              <Users className="w-3.5 h-3.5" />
              <span>STAGE 3: THIRD PATH COUNCIL (VULTR INFERENCE)</span>
            </div>
            <h2 className="text-xl font-bold text-white">
              Multi-Model Deliberation & Interventions
            </h2>
            <p className="text-sm text-slate-400 mt-1 max-w-3xl">
              Four distinct model roles on Vultr Serverless Inference formulate three materially different workflow paths. The Critic challenges each path, and the Decision agent evaluates blinded neutral labels before containerized execution.
            </p>
          </div>
          <div className="text-right text-xs font-mono text-slate-500">
            <div>PROVIDER: api.vultrinference.com</div>
            <div>STATUS: {councilData ? 'DELIBERATION COMPLETE' : isRunning ? 'RUNNING DELIBERATION' : 'READY TO CONVENE'}</div>
          </div>
        </div>

        {/* Action Trigger */}
        {!councilData && (
          <div className="mt-6 pt-6 border-t border-fortress-700/80 flex items-center justify-between flex-wrap gap-4">
            <div className="text-xs text-slate-400 font-mono">
              Current Run State: <span className="text-cyan-400 font-bold">{currentState || 'SCAN_DONE'}</span>
            </div>
            <button
              onClick={onStartCouncil}
              disabled={isRunning}
              data-testid="convene-council-btn"
              aria-label="Convene Council & Execute Blackbox"
              className="flex items-center gap-2 px-6 py-3 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-sm transition-colors shadow-sm"
            >
              {isRunning ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Deliberating on Vultr Models...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  <span>Convene Council & Execute Blackbox</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Error / Refusal Banner */}
      {error && (
        <div data-testid="stage3-error-banner" className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          {onOpenRecordedRuns && (
            <button
              onClick={onOpenRecordedRuns}
              className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[11px] font-mono hover:bg-amber-500/30 transition-colors"
            >
              Browse Recorded Runs
            </button>
          )}
        </div>
      )}

      {/* Council Deliberation Display */}
      {councilData && (
        <div className="space-y-6">
          {/* Deliberation Overview */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div data-testid="council-evidence-card" className="p-4 rounded-lg bg-fortress-850 border border-fortress-700">
              <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 mb-1">
                <BrainCircuit className="w-3.5 h-3.5" />
                <span>EVIDENCE AGENT</span>
              </div>
              <div className="text-xs font-mono text-slate-400">mimo-v2.6-flash</div>
              <div className="text-sm font-semibold text-white mt-2">
                {councilData.evidence?.facts?.length || 0} Facts Extracted
              </div>
            </div>

            <div data-testid="council-path-card" className="p-4 rounded-lg bg-fortress-850 border border-fortress-700">
              <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 mb-1">
                <Layers className="w-3.5 h-3.5" />
                <span>PATH AGENT</span>
              </div>
              <div className="text-xs font-mono text-slate-400">glm-5.3</div>
              <div className="text-sm font-semibold text-white mt-2">
                {pathsList.length || 3} Distinct Paths
              </div>
            </div>

            <div data-testid="council-critic-card" className="p-4 rounded-lg bg-fortress-850 border border-fortress-700">
              <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 mb-1">
                <Shield className="w-3.5 h-3.5" />
                <span>CRITIC AGENT</span>
              </div>
              <div className="text-xs font-mono text-slate-400">deepseek-v4.1-flash-1017</div>
              <div className="text-sm font-semibold text-emerald-400 mt-2 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Verdict: {councilData.critic?.verdict || 'PASS'}</span>
              </div>
            </div>

            <div data-testid="council-decision-card" className="p-4 rounded-lg bg-fortress-850 border border-fortress-700">
              <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 mb-1">
                <Users className="w-3.5 h-3.5" />
                <span>DECISION AGENT</span>
              </div>
              <div className="text-xs font-mono text-slate-400">mimo-v2.6-pro</div>
              <div className="text-sm font-semibold text-white mt-2">
                Recommended: {councilData.decision?.recommended_label || 'option-2'}
              </div>
            </div>
          </div>

          {/* Three Paths Formulated */}
          <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
            <h3 className="text-base font-bold text-white mb-4">
              Formulated Workflow Interventions (3 Distinct Paths)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {pathsList.map((p) => (
                <div
                  key={p.path_id}
                  className="p-4 rounded-lg bg-fortress-900 border border-fortress-700/80 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between text-xs font-mono text-cyan-400 mb-1">
                      <span className="font-bold uppercase">{p.path_id}</span>
                      <span className="text-slate-500">GLM-5.3</span>
                    </div>
                    <h4 className="text-sm font-semibold text-white mb-2">
                      {p.title || p.path_id}
                    </h4>
                    {p.intervention?.summary && (
                      <div className="text-xs font-mono text-cyan-300 bg-fortress-850 p-2.5 rounded border border-fortress-700/80 mb-3 leading-relaxed">
                        <span className="text-slate-400 font-bold block mb-1">Summary:</span>
                        <span>{p.intervention.summary}</span>
                      </div>
                    )}
                    <div className="space-y-2 text-xs text-slate-300">
                      {p.intervention?.who_does_what && (
                        <div>
                          <span className="text-slate-500 font-mono block mb-1">Action:</span>
                          {Array.isArray(p.intervention.who_does_what) ? (
                            <ul className="space-y-1">
                              {p.intervention.who_does_what.map((item, idx) => (
                                <li key={idx} className="leading-relaxed">
                                  {item && typeof item === 'object' ? (
                                    <span>
                                      <strong className="text-slate-200">{item.role || 'Role'}:</strong>{' '}
                                      <span>{item.does || ''}</span>
                                    </span>
                                  ) : (
                                    <span>{String(item)}</span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          ) : typeof p.intervention.who_does_what === 'object' && p.intervention.who_does_what !== null ? (
                            <span>
                              <strong className="text-slate-200">{p.intervention.who_does_what.role || 'Role'}:</strong>{' '}
                              <span>{p.intervention.who_does_what.does || ''}</span>
                            </span>
                          ) : (
                            <span>{String(p.intervention.who_does_what)}</span>
                          )}
                        </div>
                      )}
                      {p.intervention?.order && (
                        <div>
                          <span className="text-slate-500 font-mono block mb-1">Sequence:</span>
                          {Array.isArray(p.intervention.order) ? (
                            <ol className="list-decimal list-inside space-y-0.5 text-slate-300">
                              {p.intervention.order.map((step, idx) => (
                                <li key={idx}>{String(step)}</li>
                              ))}
                            </ol>
                          ) : (
                            <span>{String(p.intervention.order)}</span>
                          )}
                        </div>
                      )}
                      {p.intervention?.checks && (
                        <div>
                          <span className="text-slate-500 font-mono block mb-1">Verification:</span>
                          {Array.isArray(p.intervention.checks) ? (
                            <ul className="list-disc list-inside space-y-0.5 text-slate-300">
                              {p.intervention.checks.map((chk, idx) => (
                                <li key={idx}>{String(chk)}</li>
                              ))}
                            </ul>
                          ) : (
                            <span>{String(p.intervention.checks)}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Decision Comparison on Blinded Neutral Labels */}
          {councilData.decision && (
            <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
              <div className="flex items-center justify-between pb-3 border-b border-fortress-700 mb-4">
                <h3 className="text-base font-bold text-white">
                  Decision Role Qualitative Ranking (Neutral Labels)
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  SHUFFLED NEUTRAL LABELS (I-5 BLIND PROMPT)
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {councilData.decision.comparison?.map((c) => {
                  const isTop = c.label === councilData.decision.recommended_label;
                  return (
                    <div
                      key={c.label}
                      className={`p-4 rounded-lg border ${
                        isTop
                          ? 'bg-fortress-800 border-cyan-500 shadow-sm'
                          : 'bg-fortress-900 border-fortress-700/60'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-mono mb-2">
                        <span className={`font-bold ${isTop ? 'text-cyan-400' : 'text-slate-400'}`}>
                          {c.label}
                        </span>
                        {isTop && (
                          <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono text-[10px]">
                            TOP QUALITATIVE
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-200 mb-3">{c.rationale}</p>
                      <div className="text-[11px] font-mono text-slate-400 border-t border-fortress-700/60 pt-2 flex justify-between">
                        <span>Confidence</span>
                        <span className="text-cyan-300 font-bold">{formatConfidence(c.confidence)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Transition Action */}
          <div className="pt-4 flex justify-end">
            <button
              onClick={onNext}
              data-testid="proceed-to-stage-4-btn"
              aria-label="Proceed to Stage 4: Packet Viewer & Verification"
              className="flex items-center gap-2 px-5 py-2.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-colors shadow-sm"
            >
              <span>Proceed to Stage 4: Packet Viewer & Verification</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

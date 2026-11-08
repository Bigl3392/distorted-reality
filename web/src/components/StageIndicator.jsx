import React from 'react';
import { CheckCircle2, Circle, AlertCircle } from 'lucide-react';

const STAGES = [
  { id: 1, name: 'Dataset & MRI', label: '1. MRI Scan' },
  { id: 2, name: 'Intake & Scoring', label: '2. AP Assessment' },
  { id: 3, name: 'Council & Blackbox', label: '3. Council & Sandbox' },
  { id: 4, name: 'Packet Viewer', label: '4. Evidence Packet' },
  { id: 5, name: 'Approval & Gate', label: '5. Human Approval' },
];

export default function StageIndicator({ currentStage, failedState = null }) {
  return (
    <nav aria-label="Progress" data-testid="stage-indicator" className="bg-fortress-850 border-b border-fortress-700/80 px-4 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between overflow-x-auto gap-2 text-xs font-mono">
        {STAGES.map((s, idx) => {
          const isCurrent = s.id === currentStage;
          const isPassed = s.id < currentStage;
          const isFailed = failedState && isCurrent;

          return (
            <React.Fragment key={s.id}>
              <div
                data-testid={`stage-step-${s.id}`}
                aria-label={`Stage ${s.id}: ${s.name}`}
                aria-current={isCurrent ? 'step' : undefined}
                className={`flex items-center gap-2 whitespace-nowrap px-3 py-1.5 rounded transition-colors ${
                  isFailed
                    ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                    : isCurrent
                    ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/40 font-semibold'
                    : isPassed
                    ? 'text-slate-300'
                    : 'text-slate-500'
                }`}
              >
                {isFailed ? (
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                ) : isPassed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                ) : (
                  <Circle
                    className={`w-4 h-4 shrink-0 ${
                      isCurrent ? 'text-cyan-400 fill-cyan-400/20' : 'text-slate-600'
                    }`}
                  />
                )}
                <span>{s.label}</span>
              </div>

              {idx < STAGES.length - 1 && (
                <div
                  className={`h-px w-6 sm:w-12 shrink-0 ${
                    s.id < currentStage ? 'bg-emerald-500/40' : 'bg-fortress-700'
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </nav>
  );
}

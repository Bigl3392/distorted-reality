import React, { useState } from 'react';
import { ClipboardList, ArrowRight, AlertCircle, ShieldCheck, HelpCircle } from 'lucide-react';
import { REQUIRED_SUPPRESSION_LIMITATION } from '../api/config';

export default function Stage2IntakeScoring({
  intakeData,
  onSubmitIntake,
  loading = false,
  scanResult = null,
  error = null,
  onNext,
}) {
  const [answers, setAnswers] = useState({});

  const handleSelectAnswer = (questionId, value) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: value,
    }));
  };

  const handleFillReference = () => {
    if (!intakeData?.items) return;
    const filled = {};
    // Reference vector (average ~3-4 across items)
    intakeData.items.forEach((item, idx) => {
      filled[item.id] = (idx % 4) + 2;
    });
    setAnswers(filled);
  };

  const answeredCount = Object.keys(answers).length;
  const isComplete = answeredCount === 15;

  return (
    <div className="space-y-6">
      {/* Stage 2 Intro */}
      <div className="bg-fortress-850 border border-fortress-700 rounded-lg p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 mb-2">
              <ClipboardList className="w-3.5 h-3.5" />
              <span>STAGE 2: AP TEAM WORKFLOW INTAKE</span>
            </div>
            <h2 className="text-xl font-bold text-white">
              Self-Assessment & Baseline Index
            </h2>
            <p className="text-sm text-slate-400 mt-1 max-w-3xl">
              Answer the 15 operational questions on the 1–6 scale. Under G5 suppression, public results disclose only the overall baseline index and one generic recommendation. Question-level answers and system-specific groupings are never published.
            </p>
          </div>
          <div className="text-right text-xs font-mono text-slate-500">
            <div>RULE: G5 Option 1 (Full Suppression)</div>
            <div>STATUS: {isComplete ? '15/15 ANSWERED' : `${answeredCount}/15 ANSWERED`}</div>
          </div>
        </div>

        {/* Action Header */}
        {!scanResult && (
          <div className="mt-4 pt-4 border-t border-fortress-700/60 flex items-center justify-between flex-wrap gap-3">
            <div className="text-xs text-slate-400 font-mono flex items-center gap-1.5">
              <HelpCircle className="w-4 h-4 text-cyan-400" />
              <span>{intakeData?.prompt || 'Choose the statement that best describes how your AP team works today.'}</span>
            </div>
            <button
              onClick={handleFillReference}
              type="button"
              data-testid="fill-reference-sample-btn"
              aria-label="Fill Reference Sample"
              className="text-xs font-mono px-3 py-1.5 rounded bg-fortress-800 hover:bg-fortress-700 text-cyan-300 border border-fortress-600 transition-colors"
            >
              Fill Reference Sample
            </button>
          </div>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Questionnaire */}
      {!scanResult && intakeData?.items && (
        <div className="space-y-4">
          <div className="bg-fortress-900 border border-fortress-700 rounded-lg divide-y divide-fortress-700/60">
            {intakeData.items.map((item, idx) => {
              const currentVal = answers[item.id];
              return (
                <div key={item.id} data-testid={`question-${item.id}`} className="p-4 sm:p-5 hover:bg-fortress-850/40 transition-colors">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div className="flex items-start gap-2.5">
                      <span className="text-xs font-mono text-slate-500 px-1.5 py-0.5 rounded bg-fortress-800 border border-fortress-700">
                        {item.id}
                      </span>
                      <p className="text-sm font-medium text-slate-100">
                        {item.text}
                      </p>
                    </div>
                  </div>

                  {/* 1-6 Option Buttons */}
                  <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 pt-2">
                    {[1, 2, 3, 4, 5, 6].map((score) => {
                      const isSelected = currentVal === score;
                      const label = intakeData.scale?.[String(score)] || `${score}`;
                      return (
                        <button
                          key={score}
                          type="button"
                          data-testid={`q-${item.id}-opt-${score}`}
                          aria-label={`Question ${item.id} option ${score}`}
                          onClick={() => handleSelectAnswer(item.id, score)}
                          className={`p-2 rounded text-left border transition-all ${
                            isSelected
                              ? 'bg-cyan-600/20 border-cyan-400 text-cyan-200 ring-1 ring-cyan-400/50'
                              : 'bg-fortress-800/80 border-fortress-700 text-slate-400 hover:border-fortress-600 hover:text-slate-200'
                          }`}
                        >
                          <div className="text-xs font-mono font-bold">{score}</div>
                          <div className="text-[11px] truncate leading-tight mt-0.5">{label}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Submit Button */}
          <div className="flex justify-end pt-2">
            <button
              onClick={() => onSubmitIntake(answers)}
              disabled={loading || !isComplete}
              data-testid="submit-intake-btn"
              aria-label="Submit Assessment (15 Answers)"
              className="flex items-center gap-2 px-6 py-3 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-sm transition-colors shadow-sm"
            >
              <span>{loading ? 'Computing Overall Baseline Index...' : 'Submit Assessment (15 Answers)'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Scan Results Card */}
      {scanResult && (
        <div data-testid="scan-results-card" className="bg-fortress-850 border border-fortress-700 rounded-lg p-6 space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-fortress-700">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white">
                  AP Workflow Baseline Score
                </h3>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  ASSESSMENT RECORDED
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Run ID: {scanResult.run_id} · Formula: half_up(sum / 90 × 100)
              </p>
            </div>
            <div className="text-xs font-mono bg-fortress-800 px-3 py-1.5 rounded border border-fortress-700 text-slate-400">
              G5 OPTION 1 COMPLIANT
            </div>
          </div>

          {/* Score & Generic Recommendation Display */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
            {/* Overall Score Box */}
            <div className="p-6 rounded-lg bg-fortress-900 border border-fortress-700 text-center flex flex-col items-center justify-center">
              <span className="text-xs font-mono text-slate-400 uppercase tracking-wider mb-1">
                Overall Index
              </span>
              <div data-testid="overall-index-value" className="text-5xl font-mono font-bold text-cyan-400 tracking-tight">
                {scanResult.overall}
              </div>
              <span className="text-xs font-mono text-slate-500 mt-2">
                Scale 17–100 (Integer)
              </span>
            </div>

            {/* Recommendation Box */}
            <div className="md:col-span-2 p-6 rounded-lg bg-fortress-900 border border-fortress-700 flex flex-col justify-center">
              <span className="text-xs font-mono text-cyan-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-cyan-400" />
                <span>Generic Recommendation</span>
              </span>
              <p data-testid="generic-recommendation" className="text-sm text-slate-200 leading-relaxed font-sans">
                {scanResult.recommendation}
              </p>
            </div>
          </div>

          {/* Mandatory G5 Suppression Notice Alert Box (AT-04) */}
          <div data-testid="g5-suppression-notice" className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-bold uppercase tracking-wider text-amber-200 mb-0.5">
                Required Public Disclosure Limitation
              </div>
              {scanResult.limitations && Array.isArray(scanResult.limitations) ? (
                scanResult.limitations.map((lim, idx) => (
                  <div key={idx}>{lim}</div>
                ))
              ) : (
                <div>{REQUIRED_SUPPRESSION_LIMITATION}</div>
              )}
            </div>
          </div>

          {/* Transition Action */}
          <div className="pt-4 border-t border-fortress-700 flex justify-end">
            <button
              onClick={onNext}
              data-testid="proceed-to-stage-3-btn"
              aria-label="Proceed to Stage 3: Third Path Council & Execution"
              className="flex items-center gap-2 px-5 py-2.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-colors shadow-sm"
            >
              <span>Proceed to Stage 3: Third Path Council & Execution</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

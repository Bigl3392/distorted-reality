import React, { useState, useEffect, useRef } from 'react';
import SyntheticBanner from './components/SyntheticBanner';
import StageIndicator from './components/StageIndicator';
import Stage1DatasetMRI from './components/Stage1DatasetMRI';
import Stage2IntakeScoring from './components/Stage2IntakeScoring';
import Stage3Council from './components/Stage3Council';
import Stage4ExecutionsPacket from './components/Stage4ExecutionsPacket';
import Stage5ApprovalDownload from './components/Stage5ApprovalDownload';
import RecordedRunsModal from './components/RecordedRunsModal';
import { api } from './api/client';

export default function App() {
  const [currentStage, setCurrentStage] = useState(1);
  const [heartbeatOk, setHeartbeatOk] = useState(true);
  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState('');
  const [runId, setRunId] = useState(null);
  const [runState, setRunState] = useState(null);
  const [failedState, setFailedState] = useState(null);
  const [failedReason, setFailedReason] = useState(null);
  const [packetUnavailable, setPacketUnavailable] = useState(false);

  // Stage Data
  const [mriData, setMriData] = useState(null);
  const [intakeData, setIntakeData] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [councilData, setCouncilData] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [packetData, setPacketData] = useState(null);
  const [downloadToken, setDownloadToken] = useState(null);
  const [isPacketViewed, setIsPacketViewed] = useState(false);

  // Recorded Runs
  const [recordedRuns, setRecordedRuns] = useState([]);
  const [isRecordedModalOpen, setIsRecordedModalOpen] = useState(false);
  const [isRecordedRun, setIsRecordedRun] = useState(false);
  const [recordedDate, setRecordedDate] = useState(null);

  // Status
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const pollIntervalRef = useRef(null);

  // Initial load: health, datasets, intake questions, recorded runs
  useEffect(() => {
    let mounted = true;

    async function init() {
      try {
        const health = await api.checkHealth().catch(() => ({ ok: false }));
        if (mounted) setHeartbeatOk(health.ok);

        const dsRes = await api.getDatasets();
        if (mounted && dsRes?.datasets) {
          setDatasets(dsRes.datasets);
          if (dsRes.datasets.length > 0) {
            setSelectedDatasetId(dsRes.datasets[0].dataset_id);
          }
        }

        const intakeRes = await api.getIntake();
        if (mounted && intakeRes) {
          setIntakeData(intakeRes);
        }

        const recRes = await api.getRecordedRuns().catch(() => ({ recorded_runs: [] }));
        if (mounted && recRes?.recorded_runs) {
          setRecordedRuns(recRes.recorded_runs);
        }
      } catch (err) {
        if (mounted) setError(err.message);
      }
    }

    init();
    return () => {
      mounted = false;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // Poll heartbeat every 5s
  useEffect(() => {
    const hb = setInterval(async () => {
      try {
        const res = await api.checkHealth();
        setHeartbeatOk(res.ok);
      } catch {
        setHeartbeatOk(false);
      }
    }, 5000);
    return () => clearInterval(hb);
  }, []);

  // Stage 1: Run MRI
  const handleRunMri = async () => {
    setLoading(true);
    setError(null);
    setFailedState(null);
    setFailedReason(null);
    setPacketUnavailable(false);
    setIsPacketViewed(false);
    try {
      const res = await api.createRun(selectedDatasetId);
      setRunId(res.run_id);
      setRunState(res.state);
      setMriData(res.mri);
    } catch (err) {
      if (err.status === 409 || err.status === 503 || err.status === 429) {
        setIsRecordedModalOpen(true);
      }
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Stage 2: Submit Intake
  const handleSubmitIntake = async (answers) => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.submitIntake(runId, answers);
      setScanResult(res);
      setRunState('SCAN_DONE');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Stage 3: Start Council & Blackbox execution
  const handleStartCouncil = async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const startRes = await api.startRun(runId);
      setRunState(startRes.state);

      // Start Polling
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = setInterval(async () => {
        try {
          const runStatus = await api.getRun(runId);
          setRunState(runStatus.state);

          if (runStatus.state === 'FAILED_CLOSED') {
            clearInterval(pollIntervalRef.current);
            setFailedState(runStatus.failed_at || 'FAILED_CLOSED');
            setFailedReason(runStatus.failure_reason || null);
            setCurrentStage(4);

            // Bounded retry on packet availability (up to 15 attempts @ 500ms = 7.5s)
            let packet = null;
            for (let i = 0; i < 15; i++) {
              try {
                packet = await api.getPacket(runId);
                if (packet) break;
              } catch {
                // Wait before retry
              }
              await new Promise((r) => setTimeout(r, 500));
            }

            if (packet) {
              setPacketData(packet);
              setPacketUnavailable(false);
            } else {
              setPacketUnavailable(true);
            }
            setLoading(false);
            return;
          }

          if (
            runStatus.state === 'PACKET_BUILT' ||
            runStatus.state === 'AWAITING_APPROVAL' ||
            runStatus.state === 'APPROVED_VIEWED'
          ) {
            clearInterval(pollIntervalRef.current);

            // Fetch final sections
            const [cRes, exRes, pRes] = await Promise.all([
              api.getCouncil(runId).catch(() => null),
              api.getExecutions(runId).catch(() => []),
              api.getPacket(runId).catch(() => null),
            ]);

            if (cRes) setCouncilData(cRes);
            if (exRes) setExecutions(exRes);
            if (pRes) setPacketData(pRes);
            setLoading(false);
          } else {
            // Update partial council data if available
            const partialCouncil = await api.getCouncil(runId).catch(() => null);
            if (partialCouncil) setCouncilData(partialCouncil);
          }
        } catch {
          // Keep polling
        }
      }, 1500);
    } catch (err) {
      if (err.status === 409 && err.data?.mode === 'recorded') {
        setIsRecordedModalOpen(true);
      }
      setError(err.message);
      setLoading(false);
    }
  };

  // Stage 5: Human Approval
  const handleApprove = async (action) => {
    if (!runId) return;
    setLoading(true);
    try {
      const res = await api.approveRun(runId, action);
      if (res?.packet) {
        setPacketData(res.packet);
      }
      if (action === 'view') {
        setIsPacketViewed(true);
      }
      return res;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Stage 5: Generate Download Link
  const handleGenerateDownloadLink = async () => {
    if (!runId) return;
    setLoading(true);
    try {
      const res = await api.getDownloadLink(runId);
      if (res?.url) {
        const parts = res.url.split('/');
        const token = parts[parts.length - 1];
        setDownloadToken(token);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load Recorded Run
  const handleSelectRecordedRun = async (recId) => {
    setLoading(true);
    setError(null);
    try {
      const rec = await api.getRecordedRun(recId);
      if (rec?.packet) {
        setIsRecordedRun(true);
        setRecordedDate(rec.recorded_on);
        setRunId(rec.run_id);
        setPacketData(rec.packet);
        if (rec.packet.mri) setMriData(rec.packet.mri);
        if (rec.packet.scan) setScanResult(rec.packet.scan);
        if (rec.packet.council) setCouncilData(rec.packet.council);
        if (rec.packet.executions) setExecutions(rec.packet.executions);
        setIsPacketViewed(rec.packet.approval_gate?.status === 'VIEWED' || rec.packet.approval_gate?.status === 'VIEWED_CONFIRMED');
        setCurrentStage(4);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans">
      <SyntheticBanner
        heartbeatOk={heartbeatOk}
        assuranceTier={packetData?.assurance_tier || 'T1'}
        dataSource={api.getDataSource()}
        onOpenRecordedRuns={() => setIsRecordedModalOpen(true)}
        isRecordedRun={isRecordedRun}
        recordedDate={recordedDate}
      />

      <StageIndicator currentStage={currentStage} failedState={failedState} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
            {error}
          </div>
        )}

        {currentStage === 1 && (
          <Stage1DatasetMRI
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            onRunMri={handleRunMri}
            loading={loading}
            mriData={mriData}
            onNext={() => setCurrentStage(2)}
          />
        )}

        {currentStage === 2 && (
          <Stage2IntakeScoring
            intakeData={intakeData}
            onSubmitIntake={handleSubmitIntake}
            loading={loading}
            scanResult={scanResult}
            error={error}
            onNext={() => setCurrentStage(3)}
          />
        )}

        {currentStage === 3 && (
          <Stage3Council
            onStartCouncil={handleStartCouncil}
            loading={loading}
            councilData={councilData}
            currentState={runState}
            error={error}
            onOpenRecordedRuns={() => setIsRecordedModalOpen(true)}
            onNext={() => setCurrentStage(4)}
          />
        )}

        {currentStage === 4 && (
          <Stage4ExecutionsPacket
            packetData={packetData}
            executions={executions}
            onNext={() => setCurrentStage(5)}
            isFailed={Boolean(failedState)}
            packetUnavailable={packetUnavailable}
            failedReason={failedReason}
          />
        )}

        {currentStage === 5 && (
          <Stage5ApprovalDownload
            packetData={packetData}
            onApprove={handleApprove}
            onGenerateDownloadLink={handleGenerateDownloadLink}
            downloadToken={downloadToken}
            loading={loading}
            isViewed={isPacketViewed}
          />
        )}
      </main>

      <footer className="border-t border-fortress-800 bg-fortress-900 py-6 text-center text-xs font-mono text-slate-500">
        <div className="max-w-7xl mx-auto px-4">
          Distorted Reality · MIT License · Copyright (c) 2026 Larry D. Ross
        </div>
      </footer>

      <RecordedRunsModal
        isOpen={isRecordedModalOpen}
        onClose={() => setIsRecordedModalOpen(false)}
        recordedRuns={recordedRuns}
        onSelectRecordedRun={handleSelectRecordedRun}
      />
    </div>
  );
}

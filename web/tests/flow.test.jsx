import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import App from '../src/App';
import Stage3Council from '../src/components/Stage3Council';
import Stage4ExecutionsPacket from '../src/components/Stage4ExecutionsPacket';
import Stage5ApprovalDownload from '../src/components/Stage5ApprovalDownload';
import { api } from '../src/api/client';
import { MOCK_COUNCIL, MOCK_PACKET } from '../src/api/mockData';

describe('Distorted Reality — Five Stage Flow (React UI)', () => {
  beforeEach(() => {
    api.setMockMode(true);
  });

  it('renders synthetic banner and headline correctly', async () => {
    render(<App />);

    expect(
      screen.getByText(/SYNTHETIC DATA — SEED 20261103/i)
    ).toBeInTheDocument();
    expect(screen.getByText('DISTORTED REALITY')).toBeInTheDocument();
    expect(screen.getByText(/AP Reconciliation/i)).toBeInTheDocument();
  });

  it('executes Stage 1: selects dataset and runs Digital MRI scan', async () => {
    render(<App />);

    // Check dataset card is displayed
    await waitFor(() => {
      expect(screen.getByText('eo-recv-v1')).toBeInTheDocument();
    });

    // Click Run MRI
    const runBtn = screen.getByRole('button', { name: /Load Dataset & Run Digital MRI/i });
    fireEvent.click(runBtn);

    // Verify MRI results are shown
    await waitFor(() => {
      expect(screen.getByText(/Digital MRI Inventory Result/i)).toBeInTheDocument();
      expect(screen.getByText(/Log delivery receipt/i)).toBeInTheDocument();
      expect(screen.getByText(/Inter-Role Handoff Delays/i)).toBeInTheDocument();
    });

    // Advance to Stage 2
    const nextBtn = screen.getByRole('button', { name: /Proceed to Stage 2/i });
    fireEvent.click(nextBtn);

    // Verify Stage 2 screen appears
    await waitFor(() => {
      expect(screen.getByText(/Self-Assessment & Baseline Index/i)).toBeInTheDocument();
    });
  });

  it('executes Stage 2: fills intake and displays overall score with G5 suppression', async () => {
    render(<App />);

    // Stage 1
    await waitFor(() => expect(screen.getByText('eo-recv-v1')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Load Dataset & Run Digital MRI/i }));
    await waitFor(() => expect(screen.getByText(/Digital MRI Inventory Result/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Proceed to Stage 2/i }));

    // Stage 2
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Fill Reference Sample/i })).toBeInTheDocument();
    });

    // Click fill sample
    fireEvent.click(screen.getByRole('button', { name: /Fill Reference Sample/i }));

    // Submit
    const submitBtn = screen.getByRole('button', { name: /Submit Assessment/i });
    fireEvent.click(submitBtn);

    // Verify overall score and generic recommendation displayed
    await waitFor(() => {
      expect(screen.getByText(/AP Workflow Baseline Score/i)).toBeInTheDocument();
      expect(screen.getByTestId('overall-index-value')).toBeInTheDocument();
      expect(
        screen.getByText(/System-specific results are suppressed in public, by design, to protect the private association./i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/The deployed product computes only the overall index and performs no system-specific scoring./i)
      ).toBeInTheDocument();
    });
  });

  it('Stage 3: Convene Council button is ENABLED at SCAN_DONE with label Convene Council & Execute Blackbox', async () => {
    render(<App />);

    // Stage 1
    await waitFor(() => expect(screen.getByText('eo-recv-v1')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Load Dataset & Run Digital MRI/i }));
    await waitFor(() => expect(screen.getByText(/Digital MRI Inventory Result/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Proceed to Stage 2/i }));

    // Stage 2
    await waitFor(() => expect(screen.getByRole('button', { name: /Fill Reference Sample/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Fill Reference Sample/i }));
    fireEvent.click(screen.getByRole('button', { name: /Submit Assessment/i }));
    await waitFor(() => expect(screen.getByText(/AP Workflow Baseline Score/i)).toBeInTheDocument());

    // Proceed to Stage 3
    fireEvent.click(screen.getByRole('button', { name: /Proceed to Stage 3/i }));

    // Verify Stage 3 reached with STATUS: READY TO CONVENE
    await waitFor(() => {
      expect(screen.getByText('STATUS: READY TO CONVENE')).toBeInTheDocument();
      expect(screen.getByText(/STAGE 3: THIRD PATH COUNCIL/i)).toBeInTheDocument();
    });

    // CRITICAL BUG FIX CHECK: Convene button must be ENABLED
    const conveneBtn = screen.getByTestId('convene-council-btn');
    expect(conveneBtn).toBeEnabled();
    expect(conveneBtn).toHaveTextContent(/Convene Council & Execute Blackbox/i);
    expect(conveneBtn).not.toBeDisabled();
  });

  it('F-M12-01: Stage 3 renders path summaries from initial_paths and handles category confidence without NaN%', () => {
    const councilWithCategories = {
      initial_paths: [
        {
          path_id: 'path-a',
          title: 'Path Alpha',
          intervention: { summary: 'Alpha intervention summary text' },
        },
        {
          path_id: 'path-b',
          title: 'Path Beta',
          intervention: { summary: 'Beta intervention summary text' },
        },
        {
          path_id: 'path-c',
          title: 'Path Gamma',
          intervention: { summary: 'Gamma intervention summary text' },
        },
      ],
      decision: {
        recommended_label: 'option-1',
        comparison: [
          { label: 'option-1', rationale: 'Fast execution', confidence: 'high' },
          { label: 'option-2', rationale: 'Accurate logging', confidence: 'low' },
        ],
      },
    };

    render(<Stage3Council councilData={councilWithCategories} onStartCouncil={() => {}} />);

    expect(screen.getByText('Alpha intervention summary text')).toBeInTheDocument();
    expect(screen.getByText('Beta intervention summary text')).toBeInTheDocument();
    expect(screen.getByText('Gamma intervention summary text')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('LOW')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('NaN%');
  });

  it('F-M12-02: Stage 4 renders all required honesty context fields (synthetic_notice, assumptions, unknowns)', () => {
    const packet = {
      ...MOCK_PACKET,
      claim_statement: 'Distorted Reality does not claim general AP automation.',
      synthetic_notice: 'ALL DATA IN THIS PACKET IS SYNTHETIC.',
      assumptions: [
        'The dataset is synthetic and its injected faults are disclosed in the manifest.',
        'Metrics are recomputed by the control plane.',
      ],
      unknowns: [
        'Behaviour on any real operation is unknown.',
        'median_cycle_min was not computed in current model.',
      ],
      did_not_prove: ['Did not prove production ROI.'],
      limitations: ['System-specific results are suppressed in public, by design, to protect the private association.'],
    };

    render(<Stage4ExecutionsPacket packetData={packet} onNext={() => {}} />);

    expect(screen.getByText('ALL DATA IN THIS PACKET IS SYNTHETIC.')).toBeInTheDocument();
    expect(screen.getByText(/Distorted Reality does not claim general AP automation/i)).toBeInTheDocument();
    expect(screen.getByText('The dataset is synthetic and its injected faults are disclosed in the manifest.')).toBeInTheDocument();
    expect(screen.getByText('Behaviour on any real operation is unknown.')).toBeInTheDocument();
    expect(screen.getByText('Did not prove production ROI.')).toBeInTheDocument();
    expect(screen.getAllByText(/System-specific results are suppressed in public, by design, to protect the private association./i).length).toBeGreaterThan(0);
  });

  it('F-M12-03: Stage 5 viewing unlocks human confirmation', async () => {
    let currentPacket = {
      ...MOCK_PACKET,
      approval_gate: { status: 'PENDING', external_action_taken: false },
    };

    const handleApprove = (action) => {
      if (action === 'view') {
        // Real API returns unchanged pending packet on view
        currentPacket = {
          ...currentPacket,
          approval_gate: { status: 'PENDING', external_action_taken: false },
        };
      } else if (action === 'confirm') {
        currentPacket = {
          ...currentPacket,
          approval_gate: { status: 'VIEWED_CONFIRMED', external_action_taken: false },
        };
      }
      return Promise.resolve({ packet: currentPacket });
    };

    const { rerender } = render(
      <Stage5ApprovalDownload
        packetData={currentPacket}
        onApprove={handleApprove}
        onGenerateDownloadLink={() => {}}
      />
    );

    const viewBtn = screen.getByTestId('view-packet-btn');
    const confirmBtn = screen.getByTestId('confirm-approval-btn');

    // Confirm starts disabled
    expect(confirmBtn).toBeDisabled();
    expect(viewBtn).toHaveTextContent(/Mark Packet as Inspected/i);

    // View packet
    fireEvent.click(viewBtn);

    // Unlocks confirm button and updates label to 'Packet Inspected'
    await waitFor(() => {
      expect(viewBtn).toHaveTextContent(/Packet Inspected/i);
      expect(confirmBtn).toBeEnabled();
    });

    // Confirm approval
    fireEvent.click(confirmBtn);

    // Rerender with confirmed packet
    rerender(
      <Stage5ApprovalDownload
        packetData={currentPacket}
        onApprove={handleApprove}
        onGenerateDownloadLink={() => {}}
      />
    );

    await waitFor(() => {
      expect(confirmBtn).toBeDisabled();
      expect(confirmBtn).toHaveTextContent(/Human Review Confirmed/i);
    });
  });

  it('Stage 4: renders packet unavailable alert when run failed and packet is absent', async () => {
    render(
      <Stage4ExecutionsPacket
        packetData={null}
        isFailed={true}
        packetUnavailable={true}
        failedReason="ModelMismatch"
      />
    );

    expect(screen.getByTestId('packet-unavailable-alert')).toBeInTheDocument();
    expect(screen.getByText(/RUN FAILED CLOSED — EVIDENCE PACKET UNAVAILABLE/i)).toBeInTheDocument();
    expect(screen.getByText(/Failure reason: ModelMismatch/i)).toBeInTheDocument();
    expect(screen.queryByText(/Awaiting completion of Blackbox execution/i)).not.toBeInTheDocument();
  });
});

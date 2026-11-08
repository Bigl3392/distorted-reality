/**
 * Schema-valid mock data for standalone development and testing
 * Exact sources: schemas/fixtures/*.json and scan/questions.public.yaml
 */

export const MOCK_DATASETS = {
  datasets: [
    {
      dataset_id: "eo-recv-v1",
      label: "SYNTHETIC",
      case_count: 200
    }
  ]
};

export const MOCK_INTAKE = {
  scale: {
    "1": "Nothing shared",
    "2": "Mostly firefighting",
    "3": "Varies by person",
    "4": "Written down, not dependable",
    "5": "Usually dependable",
    "6": "Clear at a glance"
  },
  prompt: "Choose the statement that best describes how your AP team works today.",
  items: [
    { id: "6856d424", text: "Each handoff between receiving, AP and managers has a named owner and a known wait time." },
    { id: "3f5068ae", text: "No single person is a single point of failure for the close." },
    { id: "8c4ccda3", text: "Delivery notes and invoices arrive through a defined channel, not scattered inboxes and paper." },
    { id: "341be190", text: "When someone is out, the close still finishes on time." },
    { id: "b3d92b52", text: "We know roughly how many deliveries and invoices will arrive each week before they land." },
    { id: "fa504444", text: "When speed and accuracy conflict, the team knows which one wins." },
    { id: "380471d9", text: "Priorities for the month-end close are set before the work starts, not discovered during it." },
    { id: "5ce7331e", text: "Mismatches between PO, receipt and invoice are caught before a payment recommendation, not after." },
    { id: "1803decf", text: "Any PO, receipt or invoice can be traced end to end without asking around." },
    { id: "a3b18be0", text: "Seasonal and holiday spikes are planned for in scheduling and staffing." },
    { id: "a7194fdd", text: "Someone other than the person doing the work reviews exceptions and approvals." },
    { id: "52f13a49", text: "The team has time to fix recurring problems, not only to clear the current queue." },
    { id: "b16dd83b", text: "Everyone on the team can say what a correctly closed invoice means, and it is written down." },
    { id: "3fc2de3a", text: "A step counts as done only when something checkable exists, such as a receipt, a timestamp or a file." },
    { id: "d9ff4a70", text: "Exceptions are resolved within a time the team can state." }
  ]
};

export const MOCK_MRI = {
  label: "SYNTHETIC",
  mri_version: "1",
  run_id: "run-001",
  dataset_id: "eo-recv-v1",
  dataset_sha256: "f9c7af7ebcbf098b9f5f37361d1b168bb2e5b98d930ceef0f055377a8c94db61",
  scanned_at: "2026-11-05T15:00:00Z",
  read_only: true,
  authorizes: "nothing",
  steps: [
    {
      step_id: 1,
      name: "PO placed",
      owner_role: "Kitchen Manager",
      input_type: "inventory count",
      output_type: "purchase order",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "Receiving Clerk",
      median_duration_min: 15,
      expected_duration_min: 10,
      stall_rate: 0.01,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    },
    {
      step_id: 2,
      name: "Delivery counted",
      owner_role: "Receiving Clerk",
      input_type: "supplier delivery",
      output_type: "physical count",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "Receiving Clerk",
      median_duration_min: 12,
      expected_duration_min: 10,
      stall_rate: 0.02,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    },
    {
      step_id: 3,
      name: "Log delivery receipt",
      owner_role: "Receiving Clerk",
      input_type: "delivery note",
      output_type: "receipt",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "AP Clerk",
      median_duration_min: 6,
      expected_duration_min: 5,
      stall_rate: 0.04,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 7
    },
    {
      step_id: 4,
      name: "Invoice received",
      owner_role: "AP Clerk",
      input_type: "vendor invoice",
      output_type: "entered bill",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "AP Clerk",
      median_duration_min: 8,
      expected_duration_min: 5,
      stall_rate: 0.01,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    },
    {
      step_id: 5,
      name: "Three-way match",
      owner_role: "AP Clerk",
      input_type: "PO, receipt, invoice",
      output_type: "matched voucher",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "Kitchen Manager",
      median_duration_min: 14,
      expected_duration_min: 10,
      stall_rate: 0.05,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    },
    {
      step_id: 6,
      name: "Exception review",
      owner_role: "Kitchen Manager",
      input_type: "variance report",
      output_type: "resolved adjustment",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "Controller",
      median_duration_min: 25,
      expected_duration_min: 20,
      stall_rate: 0.06,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    },
    {
      step_id: 7,
      name: "Payment recommendation",
      owner_role: "Controller",
      input_type: "reconciled queue",
      output_type: "schedule recommendation",
      size_rows: 200,
      last_touched: "2026-11-05T15:00:00Z",
      location: "dataset:eo-recv-v1",
      handoff_to: "None (no payment made)",
      median_duration_min: 10,
      expected_duration_min: 10,
      stall_rate: 0.01,
      claimed_complete_count: 200,
      claimed_without_evidence_count: 0
    }
  ],
  handoffs: [
    { from_role: "Kitchen Manager", to_role: "Receiving Clerk", count: 200, median_wait_min: 45 },
    { from_role: "Receiving Clerk", to_role: "AP Clerk", count: 200, median_wait_min: 190 },
    { from_role: "AP Clerk", to_role: "Kitchen Manager", count: 200, median_wait_min: 120 },
    { from_role: "Kitchen Manager", to_role: "Controller", count: 200, median_wait_min: 60 }
  ],
  stall_points: [
    { step_id: 3, reason: "receipt missing at handoff", rate: 0.035 },
    { step_id: 5, reason: "price variance exceeds threshold", rate: 0.05 }
  ],
  inventory_sha256: "86b37331530f5e63d29e129730a17f212fc3c296af232676a26342bdd33e1897"
};

export const MOCK_COUNCIL = {
  evidence: {
    facts: [
      "200 total AP cases across 4 Ember & Oak hospitality locations.",
      "7 cases claimed complete without receiving receipt in Step 3.",
      "Peak handoff bottleneck is Receiving Clerk to AP Clerk (median 190 min wait)."
    ],
    constraints: [
      "No payment execution allowed; payment recommendation only.",
      "Standard cgroup caps: 256MB memory, 1 CPU, 30s wall-clock per attempt."
    ],
    uncertainties: [
      "Weather correlation in winter 2025-26 proof window.",
      "Resolution latency on multi-line vendor discrepancies."
    ]
  },
  paths: [
    {
      path_id: "path-a",
      title: "Automated Line-Item Match with Immediate Manager Escalation",
      intervention: {
        summary: "Automated line-item regex matching with instant Kitchen Manager escalation.",
        who_does_what: "AP Clerk runs automated regex check; flags routed immediately to Kitchen Manager.",
        order: "Simultaneous 3-way match before delivery verification.",
        checks: "Line-by-line price and quantity variance checks at 1% threshold.",
        automation: "Automated parsing of vendor delivery slip images.",
        distinct_from: "Bypasses Receiving Clerk manual signoff on small orders."
      }
    },
    {
      path_id: "path-b",
      title: "Receiving Verification Gate with Staged Payment Authorization",
      intervention: {
        summary: "Mandatory physical receipt verification gate prior to digital AP voucher creation.",
        who_does_what: "Receiving Clerk logs verified physical receipt before AP Clerk creates payable bill.",
        order: "Strict sequential: Step 2 count -> Step 3 receipt -> Step 4 invoice -> Step 5 match.",
        checks: "Physical packing slip count mandatory for voucher generation.",
        automation: "Discrepancy alerts posted to controller queue automatically.",
        distinct_from: "Requires physical proof before digital voucher creation."
      }
    },
    {
      path_id: "path-c",
      title: "Batch Weekly Reconciliation with Post-Close Audit",
      intervention: {
        summary: "Weekly aggregated batch reconciliation with month-end variance auditing.",
        who_does_what: "All deliveries accrued at PO price; AP Clerk reconciles weekly batches.",
        order: "Batch processing every Friday morning.",
        checks: "Aggregate supplier statement variance checks at month-end.",
        automation: "Bulk match script across weekly summary invoices.",
        distinct_from: "Defers exception handling to weekly aggregate batches."
      }
    }
  ],
  initial_paths: [
    {
      path_id: "path-a",
      title: "Automated Line-Item Match with Immediate Manager Escalation",
      intervention: {
        summary: "Automated line-item regex matching with instant Kitchen Manager escalation.",
        who_does_what: "AP Clerk runs automated regex check; flags routed immediately to Kitchen Manager.",
        order: "Simultaneous 3-way match before delivery verification.",
        checks: "Line-by-line price and quantity variance checks at 1% threshold.",
        automation: "Automated parsing of vendor delivery slip images.",
        distinct_from: "Bypasses Receiving Clerk manual signoff on small orders."
      }
    },
    {
      path_id: "path-b",
      title: "Receiving Verification Gate with Staged Payment Authorization",
      intervention: {
        summary: "Mandatory physical receipt verification gate prior to digital AP voucher creation.",
        who_does_what: "Receiving Clerk logs verified physical receipt before AP Clerk creates payable bill.",
        order: "Strict sequential: Step 2 count -> Step 3 receipt -> Step 4 invoice -> Step 5 match.",
        checks: "Physical packing slip count mandatory for voucher generation.",
        automation: "Discrepancy alerts posted to controller queue automatically.",
        distinct_from: "Requires physical proof before digital voucher creation."
      }
    },
    {
      path_id: "path-c",
      title: "Batch Weekly Reconciliation with Post-Close Audit",
      intervention: {
        summary: "Weekly aggregated batch reconciliation with month-end variance auditing.",
        who_does_what: "All deliveries accrued at PO price; AP Clerk reconciles weekly batches.",
        order: "Batch processing every Friday morning.",
        checks: "Aggregate supplier statement variance checks at month-end.",
        automation: "Bulk match script across weekly summary invoices.",
        distinct_from: "Defers exception handling to weekly aggregate batches."
      }
    }
  ],
  critic: {
    verdict: "PASS",
    findings: [
      {
        path_id: "path-a",
        kind: "risk",
        detail: "Escalation volume may overwhelm Kitchen Manager during Friday dinner prep."
      },
      {
        path_id: "path-b",
        kind: "observation",
        detail: "Strict sequential gating prevents premature claims but increases initial logging time."
      },
      {
        path_id: "path-c",
        kind: "risk",
        detail: "Weekly batching delays missing receipt detection until vendor payment deadline."
      }
    ]
  },
  revision_count: 0,
  decision: {
    recommended_label: "option-2",
    no_winner: false,
    comparison: [
      {
        label: "option-1",
        rationale: "High automation speed, but increases manager interruption during operations.",
        risks: ["Notification fatigue", "Unresolved discrepancies slip to close"],
        confidence: 0.72
      },
      {
        label: "option-2",
        rationale: "Eliminates unsupported completion claims by enforcing physical receipt evidence upfront.",
        risks: ["Receiving desk bottleneck during simultaneous deliveries"],
        confidence: 0.88
      },
      {
        label: "option-3",
        rationale: "Lowest daily effort, but leaves exceptions undetected until weekly batch.",
        risks: ["Late vendor payment penalties", "Compounded reconciliation errors"],
        confidence: 0.54
      }
    ]
  }
};

export const MOCK_EXECUTIONS = [
  {
    run_id: "run-001",
    path_id: "path-a",
    attempt: 1,
    sandbox_id: "ctr-path-a-att1",
    image_digest: "sha256:b29814cf5792e684cd75d6a7fce7a67a11887e312f87ca2ac2496d81f365ff72",
    created_at: "2026-11-05T15:02:10Z",
    started_at: "2026-11-05T15:02:11Z",
    ended_at: "2026-11-05T15:02:14Z",
    destroyed_at: "2026-11-05T15:02:15Z",
    destroy_verified: true,
    caps: { wall_seconds: 30, memory_mb: 256, pids: 64, cpus: 1, stdout_bytes: 524288 },
    docker_flags_sha256: "2934fb49d6b38adef036c28fac69f188feae09259f3184e6d9cfbd0f35454fec",
    exit_status: 0,
    termination: "normal",
    peak_memory_mb: 72.4,
    stdout_sha256: "d5a89c15a686187bb6bbf9958f494fc6b80068034a659a9ad44991b08c58f111",
    events_sha256: "3f79bb7b435b05321651daefd374cdc681dc06faa65e374e38337b88ca046dea",
    events_count: 1400,
    secret_scan: { canary_present_in_env: false, scan_passed: true },
    metrics_recomputed: {
      exceptions_caught: 12,
      false_alarms: 3,
      unsupported_claims: 7,
      manual_touches: 45
    },
    metrics_self_reported: {
      exceptions_caught: 19,
      unsupported_claims: 0
    },
    metrics_discrepancy: true,
    claim_check: {
      run_id: "run-001",
      path_id: "path-a",
      claims_total: 200,
      supported: 193,
      unsupported: 7,
      contradicted: 0,
      claims: [
        {
          claim_id: "clm-0007",
          step_id: 3,
          case_id: "inv-0007",
          claimed: "receipt logged",
          evidence_ref: null,
          result: "UNSUPPORTED",
          reason: "no evidence_ref"
        }
      ],
      recomputed_by: "control_plane"
    },
    journal_head_sha256: "189f40034be7a199f1fa9891668ee3ab6049f82d38c68be70f596eab2e1857b7"
  },
  {
    run_id: "run-001",
    path_id: "path-b",
    attempt: 1,
    sandbox_id: "ctr-path-b-att1",
    image_digest: "sha256:b29814cf5792e684cd75d6a7fce7a67a11887e312f87ca2ac2496d81f365ff72",
    created_at: "2026-11-05T15:02:20Z",
    started_at: "2026-11-05T15:02:21Z",
    ended_at: "2026-11-05T15:02:24Z",
    destroyed_at: "2026-11-05T15:02:25Z",
    destroy_verified: true,
    caps: { wall_seconds: 30, memory_mb: 256, pids: 64, cpus: 1, stdout_bytes: 524288 },
    docker_flags_sha256: "2934fb49d6b38adef036c28fac69f188feae09259f3184e6d9cfbd0f35454fec",
    exit_status: 0,
    termination: "normal",
    peak_memory_mb: 88.0,
    stdout_sha256: "65c74c15a686187bb6bbf9958f494fc6b80068034a659a9ad44991b08c58f2d2",
    events_sha256: "3f79bb7b435b05321651daefd374cdc681dc06faa65e374e38337b88ca046dea",
    events_count: 1400,
    secret_scan: { canary_present_in_env: false, scan_passed: true },
    metrics_recomputed: {
      exceptions_caught: 19,
      false_alarms: 0,
      unsupported_claims: 0,
      manual_touches: 18
    },
    metrics_self_reported: {
      exceptions_caught: 19,
      unsupported_claims: 0
    },
    metrics_discrepancy: false,
    claim_check: {
      run_id: "run-001",
      path_id: "path-b",
      claims_total: 200,
      supported: 200,
      unsupported: 0,
      contradicted: 0,
      claims: [],
      recomputed_by: "control_plane"
    },
    journal_head_sha256: "8e23f0034be7a199f1fa9891668ee3ab6049f82d38c68be70f596eab2e185999"
  }
];

export const MOCK_PACKET = {
  label: "SYNTHETIC",
  packet_version: "1",
  run_id: "run-001",
  built_at: "2026-11-05T15:03:00Z",
  claim_statement: "The calculation executed successfully under these assumptions. This does not establish that any intervention will improve an actual business.",
  synthetic_notice: "ALL DATA IN THIS PACKET IS SYNTHETIC.",
  dataset: {
    label: "SYNTHETIC",
    dataset_id: "eo-recv-v1",
    fictional_entity: "Ember & Oak Hospitality Group (EO-OKC-01)",
    generator: "gen_dataset.py",
    generator_version: "1.0.0",
    seed: 20261103,
    row_count: 1400,
    case_count: 200,
    roles: ["Kitchen Manager", "Receiving Clerk", "AP Clerk", "Controller"],
    injected_faults: [
      {
        fault_id: "f-missing-receipts",
        description: "7 cases claimed complete with no receiving receipt",
        affected_cases: ["inv-0007"],
        disclosed: true
      }
    ],
    dataset_sha256: "f9c7af7ebcbf098b9f5f37361d1b168bb2e5b98d930ceef0f055377a8c94db61",
    created: "2026-11-05T15:00:00Z",
    limitations: "Synthetic. Not calibrated to any real business.",
    arm: "flagship",
    period: { start: "2025-12-01", end: "2026-02-28" },
    drivers: ["season", "weather", "holidays"],
    cases_per_location: {
      "Midtown OKC": 50,
      "Riverside Tulsa": 50,
      "Commons Norman": 50,
      "Market Hall Edmond": 50
    }
  },
  mri: MOCK_MRI,
  scan: {
    label: "SYNTHETIC",
    scan_version: "2",
    run_id: "run-001",
    intake_variant: "paraphrase",
    overall: 56,
    recommendation: "Review the AP reconciliation workflow evidence with the council.",
    limitations: [
      "System-specific results are suppressed in public, by design, to protect the private association.",
      "The deployed product computes only the overall index and performs no system-specific scoring."
    ],
    routes_present: false,
    fees_present: false
  },
  council: MOCK_COUNCIL,
  decision_rule: {
    rule_id: "dr-3way-v1",
    sha256: "f2b88b6a7122ea464bf069d562f668f09fe8e7990a148ed3a254d193110115d5",
    frozen_before_execution: true,
    text: "eligibility: claims_verdict=CLAIMS_HOLD, unsupported_claims_max=0, false_alarms_max_fraction=0.10. ranking: exceptions_caught (desc), manual_touches (asc), median_cycle_min (asc). min_margin: exceptions_caught=3."
  },
  executions: MOCK_EXECUTIONS,
  outcome: {
    result: "PATH_PREFERRED_UNDER_ASSUMPTIONS",
    preferred_path_id: "path-b",
    basis: "Path B satisfied eligibility (unsupported_claims=0) and exceeded minimum margin on exceptions caught (19 vs 12, margin >= 3)."
  },
  assumptions: [
    "Receiving count is verifiable from physical packing slip.",
    "AP Clerk acts only upon confirmed warehouse receipts.",
    "Vendor unit prices are bounded by the purchase order contract."
  ],
  unknowns: [
    "Impact of severe winter weather on delivery arrival frequency.",
    "Timing model for median_cycle_min has no defined specification in current build."
  ],
  executed: [
    "Two distinct paths executed sequentially in fresh, isolated Docker containers.",
    "All model inference executed via Vultr Serverless Inference API."
  ],
  did_not_prove: [
    "that any intervention improves a real business",
    "that the synthetic data represents any real operation",
    "that the sandbox is immune to container-escape vulnerabilities"
  ],
  limitations: [
    "System-specific results are suppressed in public, by design, to protect the private association.",
    "The deployed product computes only the overall index and performs no system-specific scoring.",
    "Single synthetic dataset with fixed seed 20261103.",
    "Qualitative council decision runs under non-deterministic model inference."
  ],
  containment: {
    stress_test_run: false,
    stress_termination: "not_run",
    control_plane_heartbeat_gap_max_ms: 120
  },
  approval_gate: {
    status: "PENDING",
    external_action_taken: false,
    confirmed_at: null
  },
  assurance_tier: "T1",
  journal: {
    head_sha256: "189f40034be7a199f1fa9891668ee3ab6049f82d38c68be70f596eab2e1857b7",
    entries: 42
  },
  packet_sha256: "eb3102a6cb586765d01fad324523ec0bc67b9efd6a2d9589c135adfedf7922cc"
};

// S2 FIX: Mock data never fabricates recorded real runs. Genuine recorded runs are served by M5 from disk.
export const MOCK_RECORDED_RUNS = {
  recorded_runs: []
};

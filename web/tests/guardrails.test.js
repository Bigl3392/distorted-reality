import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { REQUIRED_SUPPRESSION_LIMITATION, CLAIM_DISCIPLINE_STATEMENT } from '../src/api/config';

describe('Public Safety, Guardrails & Claim Discipline', () => {
  const srcDir = path.resolve(__dirname, '../src');

  // Read all src files
  function getAllFiles(dir, fileList = []) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const filePath = path.join(dir, file);
      if (fs.statSync(filePath).isDirectory()) {
        getAllFiles(filePath, fileList);
      } else {
        fileList.push(filePath);
      }
    }
    return fileList;
  }

  const allSrcFiles = getAllFiles(srcDir);
  const fileContents = allSrcFiles.map((f) => ({
    path: f,
    content: fs.readFileSync(f, 'utf8'),
  }));

  it('AT-04: mandates exact required suppression limitation text', () => {
    expect(REQUIRED_SUPPRESSION_LIMITATION).toBe(
      'System-specific results are suppressed in public, by design, to protect the private association.'
    );
  });

  it('AT-25: verifies zero forbidden claim phrases across all frontend code', () => {
    // Prohibited: "will improve", "guarantee", "proves ROI" (except in negated limitation strings)
    const forbiddenPhrases = [
      /will improve an? actual business/i, // allowed only with "does not establish that..."
      /guarantee/i,
      /proves? roi/i,
      /boosts? profit/i,
    ];

    for (const { path: filePath, content } of fileContents) {
      // Exclude tests or legitimate "did_not_prove" negations
      const lines = content.split('\n');
      lines.forEach((line, lineNo) => {
        // If line contains "does not establish" or "did_not_prove" or "did not prove" or "never", it's a disclaimer
        const isNegatedDisclaimer =
          line.includes('does not establish') ||
          line.includes('did_not_prove') ||
          line.includes('did not prove') ||
          line.includes('never') ||
          line.includes('CERTIFY RECOMPUTED ASSUMPTIONS ONLY') ||
          line.includes('NO BUSINESS IMPROVEMENT CLAIMED');

        if (!isNegatedDisclaimer) {
          if (/will improve/i.test(line)) {
            throw new Error(`Forbidden phrase "will improve" found at ${filePath}:${lineNo + 1}: ${line}`);
          }
          if (/guarantee/i.test(line)) {
            throw new Error(`Forbidden phrase "guarantee" found at ${filePath}:${lineNo + 1}: ${line}`);
          }
          if (/proves? roi/i.test(line)) {
            throw new Error(`Forbidden phrase "proves ROI" found at ${filePath}:${lineNo + 1}: ${line}`);
          }
        }
      });
    }
  });

  it('AT-05: verifies no FFC route names or fee strings in web codebase', () => {
    const forbiddenFfcTokens = [
      'Cashflow & Controls',
      'Sprint Route',
      'ROUTE_',
      'INVESTMENT BAND',
      '$12,500',
      '$25,000',
    ];

    for (const { path: filePath, content } of fileContents) {
      for (const token of forbiddenFfcTokens) {
        expect(content.includes(token)).toBe(
          false,
          `Forbidden FFC token "${token}" found in ${filePath}`
        );
      }
    }
  });

  it('AT-D1: Darla Guardrail — verifies no bakery/Darla persona tokens or customer-order screens', () => {
    const forbiddenDarlaTokens = [
      'Darla',
      'Crumb & Get It',
      'Crumb and Get It',
      'pastry',
      'croissant',
      'cookie order',
      'bakery customer',
    ];

    for (const { path: filePath, content } of fileContents) {
      for (const token of forbiddenDarlaTokens) {
        expect(content.toLowerCase().includes(token.toLowerCase())).toBe(
          false,
          `Forbidden Darla token "${token}" found in ${filePath}`
        );
      }
    }
  });

  it('AT-G5-1: verifies no system names or system grouping fields', () => {
    const forbiddenSystemTokens = [
      'system_scores',
      'system_names',
      'system_selection',
      'grouping_result',
    ];

    for (const { path: filePath, content } of fileContents) {
      for (const token of forbiddenSystemTokens) {
        expect(content.includes(token)).toBe(
          false,
          `Forbidden G5 system token "${token}" found in ${filePath}`
        );
      }
    }
  });

  it('S1: verifies client fails explicitly on network failure without mutating to mock mode', async () => {
    const { api } = await import('../src/api/client');
    api.setMockMode(false);
    expect(api.isMockMode()).toBe(false);

    // Calling an unserved backend should reject with Connection error, NOT silently switch useMock to true
    await expect(api.checkHealth()).rejects.toThrow(/Connection to M5 server failed/);
    expect(api.isMockMode()).toBe(false);
  });

  it('S2: verifies mock fixtures never carry RECORDED REAL RUN label', async () => {
    const { MOCK_RECORDED_RUNS, MOCK_PACKET } = await import('../src/api/mockData');
    expect(MOCK_RECORDED_RUNS.recorded_runs.length).toBe(0);
    expect(MOCK_PACKET.label).toBe('SYNTHETIC');
    expect(MOCK_PACKET.synthetic_notice).toContain('SYNTHETIC');
  });

  it('S3: verifies mock scan response conforms to frozen scan_result schema v2', async () => {
    const { api } = await import('../src/api/client');
    api.setMockMode(true);
    const run = await api.createRun('eo-recv-v1');

    // 15 valid answers
    const answers = {};
    for (let i = 0; i < 15; i++) {
      answers[`q_${i}`] = 4;
    }
    const scan = await api.submitIntake(run.run_id, answers);

    expect(scan.label).toBe('SYNTHETIC');
    expect(scan.scan_version).toBe('2');
    expect(scan.intake_variant).toBe('paraphrase');
    expect(scan.overall).toBeGreaterThanOrEqual(17);
    expect(scan.overall).toBeLessThanOrEqual(100);
    expect(scan.recommendation).toBe(
      'Review the AP reconciliation workflow evidence with the council.'
    );
    expect(scan.routes_present).toBe(false);
    expect(scan.fees_present).toBe(false);
    expect(scan.limitations).toContain(REQUIRED_SUPPRESSION_LIMITATION);

    // Also verify mockRun.history does not contain acknowledgement 'STARTED'
    await api.startRun(run.run_id);
    const runStatus = await api.getRun(run.run_id);
    expect(runStatus.history).not.toContain('STARTED');
    expect(runStatus.history).toContain('COUNCIL_EVIDENCE');
  });
});

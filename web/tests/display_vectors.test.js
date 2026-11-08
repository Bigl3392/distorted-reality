import { describe, it, expect } from 'vitest';
import vectors from '../../scan/vectors.json';
import { api } from '../src/api/client';

describe('M2 Display Layer Vectors (AT-03)', () => {
  it('loads all 76 totals (15..90) from scan/vectors.json', () => {
    const totals = Object.keys(vectors.total_to_overall);
    expect(totals.length).toBe(76);
    expect(vectors.total_to_overall['15']).toBe(17);
    expect(vectors.total_to_overall['90']).toBe(100);
  });

  it('matches half_up(sum / 90 * 100) across all 76 shared totals', () => {
    // JavaScript Math.round implements half-up for positive numbers
    for (const [totalStr, expectedOverall] of Object.entries(vectors.total_to_overall)) {
      const total = parseInt(totalStr, 10);
      const computed = Math.round((total / 90) * 100);
      expect(computed).toBe(expectedOverall);
    }
  });

  it('verifies monotonic non-decreasing behavior in range [17, 100]', () => {
    let prev = 17;
    for (let sum = 15; sum <= 90; sum++) {
      const overall = vectors.total_to_overall[String(sum)];
      expect(overall).toBeGreaterThanOrEqual(prev);
      expect(overall).toBeGreaterThanOrEqual(17);
      expect(overall).toBeLessThanOrEqual(100);
      prev = overall;
    }
  });

  it('rejects input with fewer than 15 answers with the exact generic error', async () => {
    const client = api;
    client.setMockMode(true);
    // Create run
    const run = await client.createRun('eo-recv-v1');
    const answers14 = {};
    for (let i = 0; i < 14; i++) {
      answers14[`q_${i}`] = 4;
    }

    await expect(client.submitIntake(run.run_id, answers14)).rejects.toThrow(
      vectors.generic_error
    );
  });

  it('rejects out of bounds answer values with the exact generic error', async () => {
    const client = api;
    client.setMockMode(true);
    const run = await client.createRun('eo-recv-v1');
    const answersBad = {};
    for (let i = 0; i < 15; i++) {
      answersBad[`q_${i}`] = i === 0 ? 7 : 3;
    }

    await expect(client.submitIntake(run.run_id, answersBad)).rejects.toThrow(
      vectors.generic_error
    );
  });
});

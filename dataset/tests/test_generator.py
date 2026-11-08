import collections
import copy
import hashlib
import json
import unittest

from broker._schemas import errors
from dataset.generator import DatasetError, build_synthetic, generate, encode_rows
from mri.scanner import scan


class DatasetTests(unittest.TestCase):
    def test_core_determinism_shape_and_disclosure(self):
        a = build_synthetic()
        b = build_synthetic()
        self.assertEqual(a, b)
        events, manifest, truth, baseline = a
        self.assertEqual(len(events), 1400)
        self.assertEqual(len({e['case_id'] for e in events}), 200)
        self.assertEqual(collections.Counter(e['location'] for e in events if e['step_id'] == 1),
                         dict.fromkeys(('Midtown OKC', 'Riverside Tulsa', 'Commons Norman', 'Market Hall Edmond'), 50))
        self.assertEqual({e['holiday_window'] for e in events}, {'none', 'valentines', 'new_years', 'christmas'})
        self.assertEqual(manifest['seed'], 20261103)
        self.assertEqual(manifest['dataset_sha256'], hashlib.sha256(encode_rows(events)).hexdigest())
        self.assertEqual(errors('dataset_manifest.schema.json', manifest), [])
        for e in events:
            self.assertEqual(errors('dataset_event.schema.json', e), [])
            self.assertEqual(e['label'], 'SYNTHETIC')
            self.assertEqual(e['close_ref'] is None, e['step_id'] in (1, 2))
            self.assertNotIn('ground_truth', json.dumps(e))
        self.assertEqual(len(baseline), 12)
        for row in baseline:
            self.assertEqual(errors('monthly_baseline.schema.json', row), [])
        actual = {c['case_id'] for c in truth['cases'] if c['exception_types']}
        self.assertEqual(actual, set(truth['exceptional_case_ids']))
        self.assertTrue(actual)
        self.assertTrue(all(f['disclosed'] for f in manifest['injected_faults']))

    def test_public_generator_refuses_missing_weather(self):
        with self.assertRaisesRegex(DatasetError, 'weather'):
            generate(weather_rows=[], provenance={})

    def test_other_seed_is_rejected(self):
        with self.assertRaises(DatasetError):
            build_synthetic(seed=7)

    def test_mri_read_only_deterministic_and_schema_valid(self):
        rows, manifest, _, _ = build_synthetic()
        before = copy.deepcopy(rows)
        result = scan(rows, manifest, run_id='run-001', scanned_at='2026-11-04T12:00:00Z')
        self.assertEqual(result, scan(rows, manifest, run_id='run-001', scanned_at='2026-11-04T12:00:00Z'))
        self.assertEqual(rows, before)
        self.assertEqual(errors('mri_inventory.schema.json', result), [])
        self.assertTrue(result['read_only'])
        self.assertEqual(result['authorizes'], 'nothing')
        self.assertEqual(len(result['steps']), 28)
        self.assertTrue(result['stall_points'])

    def test_mri_rejects_dataset_tamper(self):
        rows, manifest, _, _ = build_synthetic()
        rows[0]['output'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'hash'):
            scan(rows, manifest, run_id='run-001', scanned_at='2026-11-04T12:00:00Z')


if __name__ == '__main__':
    unittest.main()

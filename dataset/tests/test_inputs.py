import copy
import json
from pathlib import Path
import tempfile
import unittest
from dataset.generator import build_synthetic, generate, weather_inputs, write_bundle, DatasetError, WEATHER_SOURCE
from broker._schemas import errors

class InputTests(unittest.TestCase):
    def test_frozen_weather_and_era_negative_fixtures(self):
        root = Path(__file__).resolve().parents[2]/'schemas'/'fixtures'
        for path in root.glob('weather_daily__INVALID*.json'):
            with self.subTest(name=path.name):
                self.assertTrue(errors('weather_daily.schema.json',json.loads(path.read_text())))
        for path in root.glob('weather_daily__valid*.json'):
            self.assertEqual(errors('weather_daily.schema.json',json.loads(path.read_text())),[])

    def test_partial_weather_not_accepted_as_final_dataset(self):
        root = Path(__file__).resolve().parents[2]/'schemas'/'fixtures'
        row = json.loads((root/'weather_daily__valid.json').read_text())
        with self.assertRaisesRegex(DatasetError,'coverage'):
            generate(weather_rows=[row],provenance={'source':WEATHER_SOURCE,'request_parameters':{'fixture_only':True},'retrieved':'2026-11-04'})

    def test_output_refuses_existing_directory_and_truth_is_bound_to_dataset(self):
        bundle = build_synthetic()
        rows, manifest, truth, baseline = bundle
        self.assertEqual(truth['dataset_sha256'],manifest['dataset_sha256'])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(DatasetError,'must not exist'):
                write_bundle(d,bundle,[],{})

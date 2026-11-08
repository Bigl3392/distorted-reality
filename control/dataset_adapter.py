"""M1 dataset behind M5's Dataset interface (composition root). Read-only wrapper: it adds no data and no numbers.

`BundledDataset` takes M1's bundle `(events, manifest, ground_truth, baseline)` and exposes what the orchestrator reads. The sealed ground truth is
reduced at construction to the set of exceptional case ids and the rest is dropped; that set is only ever read by M5's metric recompute, never sent
to a prompt, a runner or a journal. `provisional` is True while the manifest says it has no sourced weather (G14): such a dataset is the synthetic
core, not the release dataset, and `compose.make_real_factory` refuses it unless the caller says so explicitly.
"""
import copy
import hashlib

from dataset.generator import DatasetError, encode_rows
from mri.scanner import scan


class BundledDataset:
    def __init__(self, bundle, *, clock):
        events, manifest, truth, _baseline = bundle
        if hashlib.sha256(encode_rows(events)).hexdigest() != manifest["dataset_sha256"]:
            raise DatasetError("events do not match the manifest dataset hash")
        if truth.get("dataset_sha256") != manifest["dataset_sha256"]:
            raise DatasetError("sealed truth is bound to a different dataset")
        self._clock = clock
        self.dataset_id = manifest["dataset_id"]
        self.manifest = copy.deepcopy(manifest)
        self.events = copy.deepcopy(events)
        self.truth_exceptions = frozenset(truth["exceptional_case_ids"])
        self.schema = {"fields": sorted(self.events[0])}
        self.cases_total = manifest["case_count"]
        self.provisional = "weather" not in manifest.get("drivers", [])

    def mri(self, run_id):
        return scan(self.events, self.manifest, run_id=run_id, scanned_at=self._clock())

    def __repr__(self):
        return f"BundledDataset({self.dataset_id}, rows={len(self.events)}, provisional={self.provisional})"

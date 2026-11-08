"""M2 scoring service tests (RED first). Covers AT-03, AT-04, AT-G18-1 and the offline halves of AT-G5-1/2/3 and AT-G19-2.
The live oracle/timing probes (AT-G5-2/3 against a running endpoint) are BUILD's and are NOT claimed here.
Independent re-derivation: the expected overall is computed in this file from the formula, not from the module under test.
"""
import json
import math
import os
import random
import re
import unittest

from broker import _schemas

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENERIC_ERROR = "15 integer answers in 1..6 required"


def half_up(x):
    return int(math.floor(x + 0.5))


def public_ids():
    from scan.service import load_questions
    return [q["id"] for q in load_questions()["items"]]


def answers(fn):
    return {qid: fn(i) for i, qid in enumerate(public_ids())}


class TestQuestions(unittest.TestCase):
    def test_exactly_15_unique_opaque_ids(self):
        ids = public_ids()
        self.assertEqual(len(ids), 15)
        self.assertEqual(len(set(ids)), 15)
        for i in ids:
            self.assertRegex(i, r"^[0-9a-f]{8}$")

    def test_ids_are_not_in_sequence_order(self):
        ids = public_ids()
        self.assertNotEqual(ids, sorted(ids))
        vals = [int(i, 16) for i in ids]
        self.assertFalse(all(b - a == 1 for a, b in zip(vals, vals[1:])))

    def test_file_has_no_comments_and_only_scale_prompt_items(self):
        from scan.service import QUESTIONS_PATH, load_questions
        with open(QUESTIONS_PATH, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("#", text)
        self.assertEqual(sorted(load_questions()), ["items", "prompt", "scale"])
        for q in load_questions()["items"]:
            self.assertEqual(sorted(q), ["id", "text"])

    def test_loader_refuses_a_file_that_is_not_exactly_15(self):
        from scan.service import QuestionsError, validate_questions
        good = {"scale": {"1": "a"}, "prompt": "p", "items": [{"id": f"{i:08x}", "text": "t"} for i in (5, 9, 2, 40, 33, 71, 12, 88, 61, 17, 99, 24, 53, 46, 8)]}
        validate_questions(good)
        short = dict(good, items=good["items"][:14])
        dup = dict(good, items=good["items"][:14] + [good["items"][0]])
        for bad in (short, dup):
            with self.assertRaises(QuestionsError):
                validate_questions(bad)


class TestScoring(unittest.TestCase):
    def test_prototype_vectors_AT03(self):
        from scan.service import score
        self.assertEqual(score("run-001", answers(lambda i: 1))["overall"], 17)
        self.assertEqual(score("run-001", answers(lambda i: 6))["overall"], 100)
        self.assertEqual(score("run-001", answers(lambda i: 4))["overall"], 67)
        self.assertEqual(score("run-001", answers(lambda i: 3))["overall"], 50)

    def test_all_76_totals_match_independent_formula_and_G18_range(self):
        from scan.service import score
        seen = set()
        for total in range(15, 91):
            a = answers(lambda i: 1)
            extra = total - 15
            for k, qid in enumerate(a):
                add = min(5, extra)
                a[qid] += add
                extra -= add
            r = score("run-001", a)
            self.assertEqual(r["overall"], half_up(total / 90 * 100), total)
            seen.add(r["overall"])
        self.assertEqual((min(seen), max(seen)), (17, 100))

    def test_result_validates_and_has_the_fixed_shape(self):
        from scan.service import score
        r = score("run-001", answers(lambda i: 3))
        self.assertEqual(_schemas.errors("scan_result.schema.json", r), [])
        self.assertEqual(sorted(r), sorted(["label", "scan_version", "run_id", "intake_variant", "overall", "recommendation",
                                           "limitations", "routes_present", "fees_present"]))
        self.assertIn("System-specific results are suppressed in public, by design, to protect the private association.", r["limitations"])
        self.assertFalse(r["routes_present"])
        self.assertFalse(r["fees_present"])

    def test_every_malformed_input_gets_the_same_generic_error_AT04(self):
        from scan.service import ScanRejected, score
        ok = answers(lambda i: 3)
        ids = list(ok)
        bad_inputs = {
            "14 answers": {k: 3 for k in ids[:14]},
            "16 answers": {**ok, "deadbeef": 3},
            "unknown id": {**{k: 3 for k in ids[:14]}, "deadbeef": 3},
            "blank": {**ok, ids[0]: None},
            "empty string": {**ok, ids[0]: ""},
            "zero": {**ok, ids[0]: 0},
            "seven": {**ok, ids[0]: 7},
            "float": {**ok, ids[0]: 3.0},
            "bool": {**ok, ids[0]: True},
            "string digit": {**ok, ids[0]: "3"},
            "not a dict": [3] * 15,
            "none": None,
        }
        msgs = set()
        for name, payload in bad_inputs.items():
            with self.subTest(name):
                with self.assertRaises(ScanRejected) as cm:
                    score("run-001", payload)
                msgs.add(str(cm.exception))
        self.assertEqual(msgs, {GENERIC_ERROR})

    def test_a_blank_is_never_scored_as_zero(self):
        from scan.service import ScanRejected, score
        a = answers(lambda i: 3)
        a[list(a)[0]] = None
        with self.assertRaises(ScanRejected):
            score("run-001", a)

    def test_bad_run_id_rejected(self):
        from scan.service import ScanRejected, score
        with self.assertRaises(ScanRejected):
            score("../x", answers(lambda i: 3))


class TestNoGroupingLeaksAndOracle(unittest.TestCase):
    def test_permuted_answers_with_equal_sum_give_identical_bytes_ATG5_3_offline(self):
        from scan.service import score
        rng = random.Random(11)
        ids = public_ids()
        for _ in range(300):
            vals = [rng.randint(1, 6) for _ in ids]
            perm = vals[:]
            rng.shuffle(perm)
            a, b = dict(zip(ids, vals)), dict(zip(ids, perm))
            ra = json.dumps(score("run-001", a), sort_keys=True)
            rb = json.dumps(score("run-001", b), sort_keys=True)
            self.assertEqual(ra, rb)

    def test_2000_random_vectors_vary_only_in_overall_ATG5_2_offline(self):
        from scan.service import score
        rng = random.Random(5)
        ids = public_ids()
        shapes, varying = set(), set()
        base = None
        for _ in range(2000):
            vals = [rng.randint(1, 6) for _ in ids]
            r = score("run-001", dict(zip(ids, vals)))
            self.assertEqual(r["overall"], half_up(sum(vals) / 90 * 100))
            shapes.add(tuple(sorted(r)))
            if base is None:
                base = r
            varying |= {k for k in r if r[k] != base[k]}
        self.assertEqual(len(shapes), 1)
        self.assertEqual(varying - {"overall"}, set())

    def test_no_forbidden_fields_in_any_result_ATG5_1(self):
        from scan.service import score
        r = score("run-001", answers(lambda i: 2), commit_key=b"k" * 32)
        keys = []

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    keys.append(k)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(r)
        allowed = {"label", "scan_version", "run_id", "intake_variant", "overall", "recommendation", "limitations",
                   "routes_present", "fees_present", "answers_commitment", "alg", "value"}
        self.assertEqual(set(keys) - allowed, set())
        for k in keys:
            for word in ("system", "group", "select", "closeness", "map"):
                self.assertNotIn(word, k)
        self.assertNotIn("answers", keys)  # no question-keyed answers object
        self.assertTrue(all(isinstance(r[k], (str, int, bool, list, dict)) for k in r))


class TestCommitment(unittest.TestCase):
    def test_commitment_only_when_key_given_and_valid(self):
        from scan.service import score
        a = answers(lambda i: 4)
        self.assertNotIn("answers_commitment", score("run-001", a))
        r = score("run-001", a, commit_key=b"\x01" * 32)
        self.assertEqual(r["answers_commitment"]["alg"], "HMAC-SHA256")
        self.assertRegex(r["answers_commitment"]["value"], r"^[0-9a-f]{64}$")
        self.assertEqual(_schemas.errors("scan_result.schema.json", r), [])

    def test_commitment_changes_with_run_and_key_not_with_nothing_else_observable(self):
        from scan.service import score
        a = answers(lambda i: 4)
        c1 = score("run-001", a, commit_key=b"\x01" * 32)["answers_commitment"]
        self.assertEqual(c1, score("run-001", a, commit_key=b"\x01" * 32)["answers_commitment"])
        self.assertNotEqual(c1, score("run-002", a, commit_key=b"\x01" * 32)["answers_commitment"])
        self.assertNotEqual(c1, score("run-001", a, commit_key=b"\x02" * 32)["answers_commitment"])

    def test_key_is_never_in_the_result(self):
        from scan.service import score
        key = b"SECRETKEY-1234567890-SECRETKEY-12"
        self.assertNotIn(key.decode(), json.dumps(score("run-001", answers(lambda i: 4), commit_key=key)))


class TestNoPrivateConfigurationATG19_2(unittest.TestCase):
    def test_scoring_module_reads_nothing_but_the_public_questions_and_loads_no_env(self):
        with open(os.path.join(ROOT, "scan", "service.py"), encoding="utf-8") as f:
            src = f.read()
        # the one spec-mandated sentence that contains the word is excluded; the word is banned everywhere else
        src = src.replace("System-specific results are suppressed in public, by design, to protect the private association.", "")
        for bad in ("environ", "getenv", "dotenv", "closeness", "scoring_map", "private", ".env"):
            self.assertNotIn(bad, src.lower(), bad)
        opens = re.findall(r"open\(([^)]*)\)", src)
        self.assertLessEqual(len(opens), 1, opens)

    def test_scorer_runs_with_no_private_file_anywhere(self):
        from scan.service import score
        self.assertEqual(score("run-001", answers(lambda i: 6))["overall"], 100)


class TestSharedVectors(unittest.TestCase):
    def test_vectors_file_matches_reference_for_every_total(self):
        with open(os.path.join(ROOT, "scan", "vectors.json"), encoding="utf-8") as f:
            v = json.load(f)
        self.assertEqual(sorted(int(k) for k in v["total_to_overall"]), list(range(15, 91)))
        for k, want in v["total_to_overall"].items():
            self.assertEqual(want, half_up(int(k) / 90 * 100))
        self.assertEqual(v["rejections"], [
            "fewer than 15 answers", "more than 15 answers", "answer below 1", "answer above 6", "non-integer answer", "blank answer"])
        self.assertEqual(v["generic_error"], GENERIC_ERROR)


if __name__ == "__main__":
    unittest.main()

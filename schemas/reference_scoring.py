"""Reference scoring, rev 3 logic (G5 Option 1); docstring reworded rev 5. PUBLIC FILE: computes the overall index only.
It contains no system names, no grouping of questions, no selection logic and no map. The deployed product computes only the overall index and performs no system-specific scoring.
All 15 answers are REQUIRED. Math: half-up rounding (NOT Python round()). overall = half_up(sum(answers) / 90 * 100) (equal weight).
Deviation note: this differs from the earlier prototype's overall by at most 1 point (the prototype averaged rounded intermediate scores).
Run: python3 -I reference_scoring.py"""
import hashlib, hmac, itertools, json, math, random

def half_up(x): return int(math.floor(x + 0.5))

def _check(answers):
    if len(answers) != 15 or any(type(v) is not int or not 1 <= v <= 6 for v in answers.values()):
        raise ValueError("REJECT: exactly 15 integer answers in 1..6 are required")

def overall(answers):
    _check(answers)
    return half_up(sum(answers.values()) / 90 * 100)

def commitment(answers, run_id, key: bytes):
    """Keyed commitment over the canonical answers. The key is private (control VM env), never published; not reversible; verifiable only by the key holder."""
    _check(answers)
    msg = (run_id + "|" + json.dumps(answers, sort_keys=True, separators=(",", ":"))).encode()
    return {"alg": "HMAC-SHA256", "value": hmac.new(key, msg, hashlib.sha256).hexdigest()}

def _selftest():
    ids = [f"{i:08x}" for i in range(1, 16)]
    A = lambda f: {k: f(i) for i, k in enumerate(ids)}
    assert overall(A(lambda i: 1)) == 17 and overall(A(lambda i: 6)) == 100 and overall(A(lambda i: 4)) == 67
    assert overall(A(lambda i: 3)) == 50
    for bad in (lambda: overall({k: 3 for k in ids[:14]}), lambda: overall(A(lambda i: 7)), lambda: overall(A(lambda i: 0)), lambda: overall({**A(lambda i: 3), ids[0]: 3.0}), lambda: overall({**A(lambda i: 3), ids[0]: True})):
        try: bad(); raise SystemExit("self-test FAIL: bad input accepted")
        except ValueError: pass
    # grouping-independence property: overall depends only on the answer sum, so it cannot encode any grouping of questions
    rng = random.Random(7)
    for _ in range(2000):
        a = A(lambda i: rng.randint(1, 6)); perm = ids[:]; rng.shuffle(perm)
        b = dict(zip(perm, a.values()))
        assert overall(a) == overall(b)
    # commitment: deterministic per (key, run, answers); changes with key or run or any answer
    k1, k2 = b"\x01" * 32, b"\x02" * 32; a = A(lambda i: 4)
    c = commitment(a, "run-001", k1)
    assert c == commitment(a, "run-001", k1) and c != commitment(a, "run-001", k2) and c != commitment(a, "run-002", k1)
    assert c != commitment({**a, ids[0]: 3}, "run-001", k1)
    print("reference_scoring self-test: PASS")

if __name__ == "__main__": _selftest()

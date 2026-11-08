"""Hash-chained, append-only run journal (EVIDENCE_SPEC section 2, schema journal_entry).

entry_sha256 = SHA-256 of the canonical JSON (sorted keys, separators "," and ":", ASCII only) of every other field.
Non-ASCII data is refused so the canonical form is unambiguous for an independent verifier (M9). Secrets are refused by value.
"""
import collections
import datetime
import hashlib
import json
import os

from broker import _schemas

GENESIS = "0" * 64
Verification = collections.namedtuple("Verification", "ok bad_seq reason")


class JournalError(Exception):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(body):
    return hashlib.sha256(canonical(body).encode("ascii")).hexdigest()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Journal:
    def __init__(self, run_id, path=None, clock=None, forbidden=()):
        self.run_id = run_id
        self.entries = []
        self._clock = clock or _now
        self._forbidden = [s for s in forbidden if s]
        self._path = path
        if path is not None:
            if os.path.exists(path):
                raise JournalError("journal file already exists: append-only, never reopened or overwritten")
            with open(path, "x", encoding="utf-8", newline="\n"):
                pass

    @property
    def head_sha256(self):
        return self.entries[-1]["entry_sha256"] if self.entries else GENESIS

    def append(self, kind, actor, data):
        dumped = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if not dumped.isascii():
            raise JournalError("journal data must be ASCII")
        if any(s in dumped for s in self._forbidden):
            raise JournalError("journal data contains a forbidden (secret) value")
        body = {"seq": len(self.entries), "ts": self._clock(), "run_id": self.run_id, "kind": kind, "actor": actor,
                "data": data, "prev_sha256": self.head_sha256}
        entry = dict(body, entry_sha256=_hash(body))
        errs = _schemas.errors("journal_entry.schema.json", entry)
        if errs:
            raise JournalError("entry fails journal schema: " + errs[0])
        if self._path is not None:
            with open(self._path, "a", encoding="utf-8", newline="\n") as f:
                f.write(canonical(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
        self.entries.append(entry)
        return entry


def load_journal(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                raise JournalError(f"line {n + 1} is not JSON") from None
    return out


def verify_chain(entries):
    prev = GENESIS
    for i, e in enumerate(entries):
        seq = e.get("seq") if isinstance(e, dict) else None
        if not isinstance(e, dict) or seq != i:
            return Verification(False, seq if isinstance(seq, int) else i, "sequence gap or reorder")
        if e.get("prev_sha256") != prev:
            return Verification(False, i, "prev_sha256 does not match the previous entry")
        body = {k: v for k, v in e.items() if k != "entry_sha256"}
        if _hash(body) != e.get("entry_sha256"):
            return Verification(False, i, "entry_sha256 does not match entry content")
        prev = e["entry_sha256"]
    return Verification(True, None, "chain intact")

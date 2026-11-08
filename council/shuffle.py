"""Seeded neutral-label shuffle. Hash-ordered so it does not depend on any Python version's RNG algorithm."""
import hashlib


def label_map(path_ids, seed):
    ordered = sorted(path_ids, key=lambda pid: hashlib.sha256(f"{int(seed)}:{pid}".encode("utf-8")).hexdigest())
    return {f"option-{i + 1}": pid for i, pid in enumerate(ordered)}

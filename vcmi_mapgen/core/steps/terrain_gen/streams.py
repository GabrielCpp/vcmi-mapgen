"""Named random streams: one ``random.Random`` per part of a draw, so a change to one
part never shifts the draws of another."""

import hashlib
import random


def stream(seed: int, *parts: object) -> random.Random:
    """The stream of ``parts`` under ``seed``, from a stable hash of both. Python's own
    ``hash`` is salted per process, so it never seeds a stream."""
    key = repr((seed, *parts)).encode()
    return random.Random(int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big"))

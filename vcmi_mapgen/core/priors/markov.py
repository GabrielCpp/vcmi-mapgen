"""The terrain Markov tables learned from the corpus, which texture zone borders."""

import collections
from dataclasses import dataclass


@dataclass(slots=True)
class MarkovModel:
    full: collections.defaultdict[tuple[int, int, int], collections.Counter[int]]
    pair: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    one: collections.defaultdict[tuple[int], collections.Counter[int]]
    marg: collections.Counter[int]


@dataclass(slots=True)
class MarkovModel4:
    full: collections.defaultdict[tuple[int, int, int, int], collections.Counter[int]]
    horiz: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    vert: collections.defaultdict[tuple[int, int], collections.Counter[int]]


@dataclass(frozen=True, slots=True)
class MarkovTables:
    chain: MarkovModel
    chain4: MarkovModel4

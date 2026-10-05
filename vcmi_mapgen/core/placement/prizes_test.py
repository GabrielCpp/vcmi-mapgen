import random
from collections import Counter

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.placement.prizes import basket_artifact


def _arts(catalog: Catalog) -> dict[ArtifactTier, Identity]:
    return {t: catalog.random_artifact(t) for t in TIERS}


def test_a_basket_draws_only_the_classes_it_weighs(catalog: Catalog) -> None:
    arts = _arts(catalog)
    rng = random.Random(1)
    drawn = Counter(basket_artifact(rng, arts, {"major": 1, "relic": 3}) for _ in range(400))
    assert set(drawn) == {arts["major"], arts["relic"]}
    assert drawn[arts["relic"]] > drawn[arts["major"]]


def test_an_empty_basket_draws_nothing(catalog: Catalog) -> None:
    assert basket_artifact(random.Random(1), _arts(catalog), {"minor": 0}) is None

"""Narrative insight recipe aggregation."""

from __future__ import annotations

from collections.abc import Callable

from load_data_modules.narrative_context import NarrativeContext
from load_data_modules.narrative_recipe_adoption import clone_heavy_star_light_adoption
from load_data_modules.narrative_recipe_attention import attention_without_readiness
from load_data_modules.narrative_recipe_docs import docs_or_example_found_audience
from load_data_modules.narrative_recipe_maintenance import maintenance_pressure
from load_data_modules.narrative_recipe_quality import data_gap_not_product_signal
from load_data_modules.narrative_recipe_release import release_pulled_attention_forward
from load_data_modules.types import Candidate

RecipeBuilder = Callable[[list[Candidate], NarrativeContext], None]

RECIPE_BUILDERS: tuple[RecipeBuilder, ...] = (
    attention_without_readiness,
    release_pulled_attention_forward,
    docs_or_example_found_audience,
    clone_heavy_star_light_adoption,
    maintenance_pressure,
    data_gap_not_product_signal,
)


def build_narrative_candidates(context: NarrativeContext) -> list[Candidate]:
    """Build all supported narrative recipe candidates."""
    candidates: list[Candidate] = []
    for builder in RECIPE_BUILDERS:
        builder(candidates, context)
    return candidates

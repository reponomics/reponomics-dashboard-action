"""Attention-oriented cross-signal growth insight rules."""

import math

from load_data_growth_insight_support import (
    _add_growth_candidate,
    _downstream,
    _enough_for_cross_signal,
)


def _high_attention_low_interest(candidates, context):
    downstream = _downstream(context)
    if not (
        _enough_for_cross_signal(context)
        and context["views"] >= 50
        and context["visitors"] >= 10
        and downstream <= 0
    ):
        return
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="high_attention_low_interest",
        metric="growth",
        score=math.log1p(context["views"]) + math.log1p(context["visitors"]),
        traffic=context["views"],
        visitors=context["visitors"],
        downstream_delta=downstream,
        text=(
            f"`{context['repo']}` drew {context['views']:,} views and "
            + f"{context['visitors']:,} visitors without downstream growth "
            + "in the selected window."
        ),
    )


def _quiet_resonance(candidates, context):
    downstream = _downstream(context)
    if not (_enough_for_cross_signal(context) and downstream >= 2 and context["views"] < 30):
        return
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="quiet_resonance",
        metric="growth",
        score=math.log1p(downstream) * 2.0 + max(0, 30 - context["views"]) / 30,
        traffic=context["views"],
        downstream_delta=downstream,
        text=(
            f"`{context['repo']}` added {downstream:+,} downstream signals "
            + f"on only {context['views']:,} views."
        ),
    )


def _clone_heavy_star_light(candidates, context):
    clone_ratio = context["clones"] / max(context["views"], 1)
    if not (
        _enough_for_cross_signal(context)
        and context["clones"] >= 12
        and clone_ratio >= 0.35
        and context["stargazers_delta"] <= 0
    ):
        return
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="clone_heavy_star_light",
        metric="clones",
        score=math.log1p(context["clones"]) * (1.0 + min(clone_ratio, 2.0)),
        clones=context["clones"],
        stargazers_delta=context["stargazers_delta"],
        text=(
            f"`{context['repo']}` is clone-heavy but star-light "
            + f"({context['clones']:,} clones, {context['stargazers_delta']:+,} stars)."
        ),
    )


def _traffic_without_downstream_growth(candidates, context):
    downstream = _downstream(context)
    if not (_enough_for_cross_signal(context) and context["views"] >= 80 and downstream <= 0):
        return
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="traffic_without_downstream_growth",
        metric="views",
        score=math.log1p(context["views"]) * 1.4,
        traffic=context["views"],
        downstream_delta=downstream,
        text=(
            f"`{context['repo']}` had a traffic spike shape "
            + f"({context['views']:,} views) without stars, watchers, or forks moving."
        ),
    )


def _downstream_without_traffic_spike(candidates, context):
    downstream = _downstream(context)
    if not (_enough_for_cross_signal(context) and downstream >= 3 and context["views"] < 40):
        return
    _add_growth_candidate(
        candidates,
        repo=context["repo"],
        subtype="downstream_without_traffic_spike",
        metric="growth",
        score=math.log1p(downstream) * 2.2,
        traffic=context["views"],
        downstream_delta=downstream,
        text=(
            f"`{context['repo']}` gained {downstream:+,} downstream signals "
            + f"without a matching traffic spike ({context['views']:,} views)."
        ),
    )

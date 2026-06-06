"""Shared helpers for growth insight rule modules."""


def _add_growth_candidate(candidates, *, repo, subtype, metric, score, text, **extra):
    candidates.append(
        {
            "score": score,
            "repo": repo,
            "kind": "growth",
            "subtype": subtype,
            "metric": metric,
            "text": text,
            **extra,
        }
    )


def _downstream(context):
    return (
        context["stargazers_delta"]
        + context["subscribers_delta"]
        + context["forks_delta"]
    )


def _enough_for_growth(context):
    return context["metric_samples"] >= 2


def _enough_for_cross_signal(context):
    return _enough_for_growth(context) and context["traffic_samples"] >= 3

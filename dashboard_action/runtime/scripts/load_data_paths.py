"""Popular path aggregation."""

from collections import defaultdict

from load_data_snapshots import _latest_snapshot_rows


def _content_label(row):
    """Return a display label for a GitHub traffic path row."""
    repo = row.get("repo", "")
    path = row.get("path", "")
    title = row.get("title", "")
    if repo and path.rstrip("/") == f"/{repo}".rstrip("/"):
        return "Repository overview"
    return title or path


def top_paths(path_rows, limit=10):
    """Return the top content paths from the latest snapshot for each repo."""
    by_path = defaultdict(lambda: {"count": 0, "uniques": 0, "title": "", "repo": ""})
    for row in _latest_snapshot_rows(path_rows):
        path_key = (row.get("repo", ""), row["path"])
        by_path[path_key]["repo"] = row.get("repo", "")
        by_path[path_key]["count"] += int(row.get("count", 0))
        by_path[path_key]["uniques"] += int(row.get("uniques", 0))
        if row.get("title"):
            by_path[path_key]["title"] = row["title"]

    result = [_path_result(path, values) for (_repo, path), values in by_path.items()]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:limit]


def _path_result(path, values):
    return {
        "repo": values["repo"],
        "path": path,
        "title": values["title"],
        "content": _content_label(
            {"repo": values["repo"], "path": path, "title": values["title"]}
        ),
        "count": values["count"],
        "uniques": values["uniques"],
    }

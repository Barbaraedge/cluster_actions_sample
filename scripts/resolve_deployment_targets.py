#!/usr/bin/env python3
"""Fails fast if the cluster declared in deployment-targets.json is not available in Barbara."""
import json
import pathlib
import sys

from barbara_clusters import find_cluster_by_name, get_access_token, load_target_cluster_name, report_failure

DEFAULT_RESOLVED_TARGETS_FILE = "dist/resolved-deployment-targets.json"


def main() -> int:
    try:
        requested = load_target_cluster_name()
        cluster = find_cluster_by_name(get_access_token(), requested)
        nodes = cluster.get("nodes")
        resolved = {
            "requested": {"cluster": requested},
            "resolved": {
                "cluster": {
                    "_id": cluster.get("_id"),
                    "name": cluster.get("name"),
                    "nodeCount": len(nodes) if isinstance(nodes, list) else None,
                }
            },
        }
        output = pathlib.Path(DEFAULT_RESOLVED_TARGETS_FILE)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(resolved, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", **resolved["resolved"]}, indent=2))
        return 0
    except Exception as exc:
        return report_failure(exc)


if __name__ == "__main__":
    raise SystemExit(main())

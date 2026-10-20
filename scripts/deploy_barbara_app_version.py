#!/usr/bin/env python3
"""Deploys APP_VERSION_NAME of APP_NAME as a workload (stack) on the target cluster.

Updates the existing workload for the app if there is one, creates it otherwise.
"""
import json

from barbara_api import require_env
from barbara_clusters import (
    create_stack,
    find_application_by_name,
    find_cluster_by_name,
    find_stack_by_app_name,
    find_version_by_name,
    get_access_token,
    get_full_cluster,
    get_ordered_versions,
    load_target_cluster_name,
    report_failure,
    update_stack,
)


def main() -> int:
    app_name = require_env("APP_NAME")
    version_name = require_env("APP_VERSION_NAME")

    try:
        access_token = get_access_token()
        cluster = find_cluster_by_name(access_token, load_target_cluster_name())
        cluster_id = cluster["_id"]

        application = find_application_by_name(access_token, app_name)
        application_id = application["_id"]
        version = find_version_by_name(get_ordered_versions(access_token, application_id), version_name)
        if version is None:
            raise RuntimeError(f"Barbara app version not found: {version_name}")

        stack = find_stack_by_app_name(get_full_cluster(access_token, cluster_id), app_name)
        if stack is not None and stack.get("_id"):
            update_stack(access_token, cluster_id, stack["_id"], application_id, version["_id"])
            result = {"status": "updated", "stackId": stack["_id"]}
        else:
            create_stack(access_token, cluster_id, application_id, version["_id"])
            result = {"status": "created"}

        print(json.dumps({
            **result,
            "cluster": {"_id": cluster_id, "name": cluster.get("name")},
            "application": {"_id": application_id, "name": application.get("name")},
            "version": {"_id": version["_id"], "name": version.get("name")},
        }, indent=2))
        return 0
    except Exception as exc:
        return report_failure(exc)


if __name__ == "__main__":
    raise SystemExit(main())

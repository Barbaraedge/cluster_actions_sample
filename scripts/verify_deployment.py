#!/usr/bin/env python3
"""
Post-deployment verification on the cluster, with automatic rollback.

Reads the workload's live Docker Swarm state (stacks[].clusterInfo.services[].tasks[]
from GET /clusters/{id}) and waits until every service runs the expected image
with all its desired tasks running.

On failure or timeout:
  - if a previous app version exists: redeploy it, then delete the failed version
  - otherwise: delete the workload from the cluster, then delete the failed version
  and exit 1 to fail the pipeline.
"""
import json
import os
import sys
import time
import urllib.error

from barbara_api import dump_http_error, require_env
from barbara_clusters import (
    delete_app_version,
    delete_stack,
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

DEFAULT_VERIFY_TIMEOUT = 300
DEFAULT_VERIFY_INTERVAL = 15

STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_PENDING = "pending"


ACTIVE_DESIRED_STATES = ("ready", "running")


def _task_state(task: dict) -> str:
    return str(task.get("state") or "").lower()


def _is_active_task(task: dict) -> bool:
    """Tasks Swarm still wants alive; history entries have desiredState "shutdown"."""
    return str(task.get("desiredState") or "").lower() in ACTIVE_DESIRED_STATES


def _service_image(service: dict) -> str | None:
    image = service.get("image")
    return image if isinstance(image, str) and image else None


def evaluate_stack(stack: dict, expected_image: str | None) -> tuple[str, str]:
    """Returns (STATE_OK | STATE_FAILED | STATE_PENDING, human readable detail)."""
    services = (stack.get("clusterInfo") or {}).get("services") or []
    if not services:
        return STATE_PENDING, "no services reported yet"

    for service in services:
        name = service.get("name") or "?"
        image = _service_image(service)
        if expected_image and image and not image.startswith(expected_image):
            return STATE_PENDING, f"{name}: still running {image}"

        tasks = [t for t in service.get("tasks") or [] if _is_active_task(t)]
        if not tasks:
            return STATE_PENDING, f"{name}: no tasks scheduled yet"
        states = [_task_state(t) for t in tasks]
        if any(s in ("failed", "rejected", "orphaned") for s in states):
            return STATE_FAILED, f"{name}: task states {states}"
        if any(s != "running" for s in states):
            return STATE_PENDING, f"{name}: task states {states}"

    return STATE_OK, "all services running"


def wait_for_stack(access_token: str, cluster_id: str, app_name: str, expected_image: str | None,
                   timeout: int, interval: int) -> tuple[str, str]:
    deadline = time.monotonic() + timeout
    state, detail = STATE_PENDING, "stack not found yet"
    while True:
        stack = find_stack_by_app_name(get_full_cluster(access_token, cluster_id), app_name)
        if stack is not None:
            state, detail = evaluate_stack(stack, expected_image)
        print(f"  {state}: {detail}")
        if state != STATE_PENDING:
            return state, detail
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timeout", detail
        time.sleep(min(interval, remaining))


def rollback(access_token: str, cluster_id: str, stack_id: str | None, application_id: str,
             failed_version_id: str, previous_version: dict | None) -> None:
    try:
        if previous_version is not None and stack_id:
            print(f"\nRolling back to version '{previous_version.get('name')}'...")
            update_stack(access_token, cluster_id, stack_id, application_id, previous_version["_id"])
        elif stack_id:
            print("\nNo previous version found. Removing workload from the cluster...")
            delete_stack(access_token, cluster_id, stack_id)
    except urllib.error.HTTPError as exc:
        print(f"  rollback failed: {dump_http_error(exc)}", file=sys.stderr)

    print("\nDeleting failed version from Barbara...")
    retries, delay = 60, 5
    for attempt in range(retries):
        try:
            delete_app_version(access_token, application_id, failed_version_id)
            print("  Failed version deleted from Barbara.")
            return
        except urllib.error.HTTPError as exc:
            error = dump_http_error(exc)
            if attempt == retries - 1:
                print(f"  Could not delete failed version after {retries} attempts: {error}", file=sys.stderr)
                return
            print(f"  Delete attempt {attempt + 1}/{retries} failed, retrying in {delay}s: {error}", file=sys.stderr)
            time.sleep(delay)


def main() -> int:
    app_name = require_env("APP_NAME")
    version_name = require_env("APP_VERSION_NAME")
    image_ref = os.environ.get("APP_VERSION_IMAGE_REF") or None
    timeout = int(os.environ.get("VERIFY_TIMEOUT_SECONDS") or DEFAULT_VERIFY_TIMEOUT)
    interval = int(os.environ.get("VERIFY_INTERVAL_SECONDS") or DEFAULT_VERIFY_INTERVAL)

    try:
        access_token = get_access_token()
        cluster = find_cluster_by_name(access_token, load_target_cluster_name())
        cluster_id = cluster["_id"]

        application = find_application_by_name(access_token, app_name)
        application_id = application["_id"]
        versions = get_ordered_versions(access_token, application_id)
        current = find_version_by_name(versions, version_name)
        if current is None:
            raise RuntimeError(f"Could not find version '{version_name}' in Barbara for application '{app_name}'")
        index = versions.index(current)
        previous = versions[index - 1] if index > 0 else None

        print(f"Verifying '{app_name}' version '{version_name}' on cluster '{cluster.get('name')}' "
              f"(timeout: {timeout}s, interval: {interval}s)...")
        state, detail = wait_for_stack(access_token, cluster_id, app_name, image_ref, timeout, interval)

        if state == STATE_OK:
            print(json.dumps({"status": "ok", "version": version_name, "cluster": cluster.get("name")}, indent=2))
            return 0

        print(json.dumps({
            "status": state,
            "detail": detail,
            "version": version_name,
            "previousVersion": previous.get("name") if previous else None,
        }, indent=2), file=sys.stderr)
        stack = find_stack_by_app_name(get_full_cluster(access_token, cluster_id), app_name)
        rollback(access_token, cluster_id, stack.get("_id") if stack else None,
                 application_id, current["_id"], previous)
        return 1
    except Exception as exc:
        return report_failure(exc)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Cluster/application helpers shared by the resolve, deploy and verify scripts."""
import json
import sys
import urllib.error

from barbara_api import authorized_json_request, dump_http_error, request_keycloak_token

DEFAULT_TARGETS_FILE = "deployment-targets.json"
PAGE_SIZE = 100


def normalize_name(value: str) -> str:
    return value.strip().casefold()


def get_access_token() -> str:
    access_token = request_keycloak_token().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Keycloak token response does not contain access_token")
    return access_token


def load_target_cluster_name(path: str = DEFAULT_TARGETS_FILE) -> str:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    name = payload.get("cluster") if isinstance(payload, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(f'"{path}" must be a JSON object with a non-empty "cluster" string.')
    return name.strip()


def list_all_clusters(access_token: str) -> list[dict]:
    clusters: list[dict] = []
    from_index = 0
    while True:
        response = authorized_json_request(
            "GET", "/api/v1/clusters", access_token,
            query={"from": str(from_index), "size": str(PAGE_SIZE)},
        )
        payload = response.get("response", response)
        page = payload.get("clusters", []) if isinstance(payload, dict) else payload
        if not isinstance(page, list):
            raise RuntimeError("Unexpected Barbara API response for cluster list")
        clusters.extend(page)
        total = payload.get("total") if isinstance(payload, dict) else None
        if not page or len(page) < PAGE_SIZE or (isinstance(total, int) and len(clusters) >= total):
            return clusters
        from_index += len(page)


def find_cluster_by_name(access_token: str, name: str) -> dict:
    clusters = list_all_clusters(access_token)
    expected = normalize_name(name)
    for cluster in clusters:
        if isinstance(cluster.get("name"), str) and normalize_name(cluster["name"]) == expected:
            return cluster
    available = sorted(c["name"] for c in clusters if isinstance(c.get("name"), str))
    raise RuntimeError(json.dumps({"message": f"Barbara cluster not found: {name}", "availableClusters": available}))


def get_full_cluster(access_token: str, cluster_id: str) -> dict:
    response = authorized_json_request("GET", f"/api/v1/clusters/{cluster_id}", access_token)
    payload = response.get("response", response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Barbara API response for cluster {cluster_id}")
    return payload


def find_application_by_name(access_token: str, app_name: str) -> dict:
    response = authorized_json_request(
        "GET", "/api/v1/applications/list", access_token,
        query={"filter": "docker", "search": app_name},
    )
    applications = response.get("response", [])
    if not isinstance(applications, list):
        raise RuntimeError("Unexpected Barbara API response for application list")
    expected = normalize_name(app_name)
    for application in applications:
        name = application.get("name", "")
        if isinstance(name, str) and normalize_name(name) == expected:
            return application
    raise RuntimeError(f"Barbara application not found: {app_name}")


def get_ordered_versions(access_token: str, application_id: str) -> list[dict]:
    """All app versions, oldest first."""
    response = authorized_json_request(
        "GET", f"/api/v1/applications/{application_id}/appversions", access_token,
        query={"from": "0", "size": "100", "filter": "all", "sortOrder": "asc", "sortColumn": "created"},
    )
    payload = response.get("response", {})
    versions = payload.get("appVersionList", []) if isinstance(payload, dict) else []
    if not isinstance(versions, list):
        raise RuntimeError("Unexpected Barbara API response for application versions")
    return versions


def find_version_by_name(versions: list[dict], version_name: str) -> dict | None:
    expected = normalize_name(version_name)
    for version in versions:
        name = version.get("name", "")
        if isinstance(name, str) and normalize_name(name) == expected:
            return version
    return None


def find_stack_by_app_name(cluster: dict, app_name: str) -> dict | None:
    """The cluster embeds every workload ("stack") under ``stacks``; match on the app's name."""
    expected = normalize_name(app_name)
    for stack in cluster.get("stacks", []) or []:
        current = (stack.get("app") or {}).get("current") or {}
        application = current.get("applicationId")
        name = application.get("name") if isinstance(application, dict) else None
        if isinstance(name, str) and normalize_name(name) == expected:
            return stack
    return None


def stack_workload_payload(application_id: str, app_version_id: str) -> dict:
    return {
        "applicationId": application_id,
        "appVersionId": app_version_id,
        "runDocker": True,
        "forcePull": True,
        "enableLogs": True,
    }


def create_stack(access_token: str, cluster_id: str, application_id: str, app_version_id: str) -> dict:
    return authorized_json_request(
        "POST", f"/api/v1/clusters/{cluster_id}/user/stacks", access_token,
        payload=stack_workload_payload(application_id, app_version_id),
    )


def update_stack(access_token: str, cluster_id: str, stack_id: str, application_id: str, app_version_id: str) -> dict:
    return authorized_json_request(
        "PUT", f"/api/v1/clusters/{cluster_id}/user/stacks/{stack_id}", access_token,
        payload=stack_workload_payload(application_id, app_version_id),
    )


def delete_stack(access_token: str, cluster_id: str, stack_id: str) -> dict:
    return authorized_json_request("DELETE", f"/api/v1/clusters/{cluster_id}/stacks/{stack_id}", access_token)


def delete_app_version(access_token: str, application_id: str, app_version_id: str) -> dict:
    return authorized_json_request(
        "DELETE", f"/api/v1/applications/{application_id}/appversions/{app_version_id}", access_token,
    )


def report_failure(exc: Exception) -> int:
    """Prints an error as JSON on stderr and returns exit code 1."""
    if isinstance(exc, urllib.error.HTTPError):
        print(json.dumps(dump_http_error(exc), indent=2), file=sys.stderr)
        return 1
    try:
        body = {"error": json.loads(str(exc))}
    except json.JSONDecodeError:
        body = {"error": str(exc)}
    print(json.dumps(body, indent=2), file=sys.stderr)
    return 1

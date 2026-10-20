# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python -m unittest discover -s tests -v                    # all tests (run from repo root; no dependencies)
python -m unittest tests.test_cluster_scripts -v           # one module
python -m unittest tests.test_cluster_scripts.EvaluateStackTestCase.test_failed_task_is_failed   # one test
python app/main.py                                         # run the app on :8080
```

## Architecture

Tiny stdlib-only HTTP app (`app/`) plus a tag-triggered GitHub Actions pipeline (`.github/workflows/cicd.yml`, tags `v*`) that publishes it to Docker Hub and deploys it to a **Barbara cluster**. Adapted from Barbaraedge/barbara_github_actions_sample (node deployment); this repo targets clusters instead of devices.

Everything in `scripts/` is stdlib-only (CI runs it in `python:alpine`) and is invoked by the workflow, one script per job. Shared code: `barbara_api.py` (Keycloak password-grant token + raw HTTP/multipart helpers) and `barbara_clusters.py` (cluster/app/version lookup and stack create/update/delete). All scripts read config from env vars set in the workflow and print JSON; failures go through `report_failure` (stderr JSON, exit 1).

Pipeline order: test + validate-target-cluster → build-image → package-artifact → register app → upload version → deploy-to-cluster → verify-deployment (rollback) → GitHub release. The deployable artifact is a zip containing `docker-compose.yaml` pinned to the immutable `<sha>` image, produced by `package_docker_compose.py`.

Cluster specifics:
- Target is `deployment-targets.json` → `{"cluster": "<name>"}`, matched case-insensitively against Barbara cluster names.
- A cluster workload is a "stack": created with `POST /api/v1/clusters/{id}/user/stacks`, updated with `PUT .../user/stacks/{stackId}`, deleted with `DELETE .../stacks/{stackId}`. There is no per-stack GET; state is read from `GET /api/v1/clusters/{id}` under `stacks[]`, and the stack for an app is found by `app.current.applicationId.name`.
- `verify_deployment.py` judges health from `stacks[].clusterInfo.services[].tasks[]` (Docker Swarm state) and the service image, then rolls back to the previous app version (or deletes the stack) and deletes the failed version.

Verified against a live cluster (create/update/verify all ran): `stacks[].clusterInfo.services[]` entries use `name`, `image`, `desiredReplicas`/`runningReplicas` and `tasks[]` with top-level `state`/`desiredState`/`error` (camelCase, not Docker's `Status.State`). Tasks Swarm still wants have `desiredState` `ready` or `running`; history entries are `shutdown`. `clusterInfo.services` stays empty for a few seconds after a deploy. The rollback path has not been exercised live.

## Pipeline configuration

Repo vars/secrets (`DOCKERHUB_*`, `APP_*`, `IMAGE_NAME`) and `production` environment vars/secrets (`BARBARA_*`, `VERIFY_*`) are listed in README.md. The app version and runtime-reported build info come from the git tag via the `BARBARA_APP_VERSION` / `BARBARA_GIT_SHA_SHORT` build args.

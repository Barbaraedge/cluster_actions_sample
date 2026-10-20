import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from barbara_clusters import find_stack_by_app_name, stack_workload_payload  # noqa: E402
from verify_deployment import STATE_FAILED, STATE_OK, STATE_PENDING, evaluate_stack  # noqa: E402

IMAGE = "ns/app:abc1234"


def service(image: str, *task_states: str) -> dict:
    return {
        "name": "svc",
        "image": f"{image}@sha256:0",
        "tasks": [{"desiredState": "running", "state": state} for state in task_states],
    }


def stack(*services: dict) -> dict:
    return {"clusterInfo": {"services": list(services)}}


class EvaluateStackTestCase(unittest.TestCase):
    def test_all_tasks_running_with_expected_image_is_ok(self):
        self.assertEqual(evaluate_stack(stack(service(IMAGE, "running", "running")), IMAGE)[0], STATE_OK)

    def test_old_image_is_pending(self):
        self.assertEqual(evaluate_stack(stack(service("ns/app:old", "running")), IMAGE)[0], STATE_PENDING)

    def test_starting_task_is_pending(self):
        self.assertEqual(evaluate_stack(stack(service(IMAGE, "running", "starting")), IMAGE)[0], STATE_PENDING)

    def test_failed_task_is_failed(self):
        self.assertEqual(evaluate_stack(stack(service(IMAGE, "failed")), IMAGE)[0], STATE_FAILED)

    def test_task_still_preparing_with_ready_desired_state_is_pending(self):
        svc = service(IMAGE)
        svc["tasks"] = [{"desiredState": "ready", "state": "preparing"}]
        self.assertEqual(evaluate_stack(stack(svc), IMAGE)[0], STATE_PENDING)

    def test_no_services_is_pending(self):
        self.assertEqual(evaluate_stack({}, IMAGE)[0], STATE_PENDING)

    def test_shutdown_tasks_are_ignored(self):
        svc = service(IMAGE, "running")
        svc["tasks"].append({"desiredState": "shutdown", "state": "failed"})
        self.assertEqual(evaluate_stack(stack(svc), IMAGE)[0], STATE_OK)


class ClusterHelpersTestCase(unittest.TestCase):
    def test_find_stack_matches_app_name_case_insensitively(self):
        cluster = {"stacks": [{"_id": "s1", "app": {"current": {"applicationId": {"name": "My_App"}}}}]}
        self.assertEqual(find_stack_by_app_name(cluster, "my_app")["_id"], "s1")
        self.assertIsNone(find_stack_by_app_name(cluster, "other"))

    def test_workload_payload_forces_pull(self):
        payload = stack_workload_payload("app", "ver")
        self.assertEqual((payload["applicationId"], payload["appVersionId"], payload["forcePull"]), ("app", "ver", True))


if __name__ == "__main__":
    unittest.main()

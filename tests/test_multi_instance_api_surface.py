from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccbs_app.ai_api import create_app  # noqa: E402
from ccbs_app.ai_auth import create_user, issue_token  # noqa: E402

try:
    from fastapi.testclient import TestClient
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment]


@unittest.skipIf(TestClient is None, "fastapi.testclient unavailable")
class MultiInstanceApiSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        if TestClient is None:
            raise unittest.SkipTest("fastapi.testclient unavailable")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        lane = self.root / "lane_a"
        lane.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "codex-instances-v1",
            "instances": [
                {
                    "instance_id": "lane-a",
                    "name": "Lane A",
                    "workspace_id": "lane_a",
                    "path": str(lane),
                    "launch_args": "",
                }
            ],
        }
        (self.root / "config" / "codex_instances.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

        create_user(self.root, username="owner", password="pw123456", role="admin")
        tok = issue_token(self.root, username="owner", password="pw123456")
        self.client = TestClient(create_app(self.root))
        self.headers = {"Authorization": f"Bearer {tok['token']}"}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_multi_instance_endpoints(self) -> None:
        apps = self.client.get("/v3/multi-instance/apps", headers=self.headers)
        self.assertEqual(apps.status_code, 200)
        self.assertIn("apps", apps.json())

        state = self.client.get("/v3/multi-instance/state", headers=self.headers)
        self.assertEqual(state.status_code, 200)
        self.assertIn("availability_counter", state.json())

        optimize = self.client.post(
            "/v3/multi-instance/optimize",
            headers=self.headers,
            json={"max_parallel": 3, "mode": "auto"},
        )
        self.assertEqual(optimize.status_code, 200)
        payload = optimize.json()
        self.assertIn("selection", payload)
        self.assertIn("selected_tasks", payload["selection"])

        runtime = self.client.get("/v3/multi-instance/runtime", headers=self.headers)
        self.assertEqual(runtime.status_code, 200)
        runtime_payload = runtime.json()
        self.assertIn("state", runtime_payload)
        self.assertIn("token_telemetry", runtime_payload)

        profile = self.client.get("/v3/multi-instance/profile", headers=self.headers)
        self.assertEqual(profile.status_code, 200)
        self.assertIn("profile", profile.json())

        route = self.client.post(
            "/v3/multi-instance/route",
            headers=self.headers,
            json={"message": "-1 run static checks", "task_label": "static checks", "apply_usage": False},
        )
        self.assertEqual(route.status_code, 200)
        route_payload = route.json()
        self.assertTrue(bool(route_payload.get("ok", False)))
        self.assertEqual(str(route_payload.get("directive", "")), "-1")
        self.assertIn("lane_selected", route_payload)
        self.assertIn("token_telemetry", route_payload)

    def test_control_sync_and_launch_confirmation_guard(self) -> None:
        sync = self.client.post(
            "/v3/multi-instance/control",
            headers=self.headers,
            json={"action": "sync-workspaces"},
        )
        self.assertEqual(sync.status_code, 200)
        self.assertIn("state", sync.json())

        launch = self.client.post(
            "/v3/multi-instance/control",
            headers=self.headers,
            json={"action": "launch"},
        )
        self.assertEqual(launch.status_code, 400)
        self.assertIn("requires confirmed=true", str(launch.json().get("detail", "")).lower())

    def test_multi_instance_ui_route(self) -> None:
        resp = self.client.get("/v3/multi-instance/ui", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("CCBS Multi-Instance Control", text)
        self.assertIn("/v3/multi-instance/runtime", text)
        self.assertIn("/v3/multi-instance/route", text)
        self.assertIn("/v3/multi-instance/optimize", text)
        self.assertIn("availability", text.lower())


if __name__ == "__main__":
    unittest.main()

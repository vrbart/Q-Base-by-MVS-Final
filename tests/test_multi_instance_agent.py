from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccbs_app.multi_instance_agent import (  # noqa: E402
    discover_multi_instance_apps,
    get_multi_instance_state,
    load_multi_instance_profile,
    optimize_multi_instance_bundle,
    route_message_to_lane,
    sync_multi_instance_workspaces,
)


class MultiInstanceAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        lane_a = self.root / "lane_a"
        lane_b = self.root / "lane_b"
        lane_a.mkdir(parents=True, exist_ok=True)
        lane_b.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "codex-instances-v1",
            "instances": [
                {
                    "instance_id": "lane-a",
                    "name": "Lane A",
                    "workspace_id": "lane_a",
                    "path": str(lane_a),
                    "launch_args": "",
                },
                {
                    "instance_id": "lane-b",
                    "name": "Lane B",
                    "workspace_id": "lane_b",
                    "path": str(lane_b),
                    "launch_args": "",
                },
            ],
        }
        (self.root / "config" / "codex_instances.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_discovery_state_sync_and_optimize_shapes(self) -> None:
        profile = load_multi_instance_profile(self.root)
        self.assertIn("lanes", profile)
        self.assertTrue(any(str(row.get("directive", "")) == "-1" for row in profile.get("lanes", [])))

        discovery = discover_multi_instance_apps(self.root)
        self.assertIn("apps", discovery)
        self.assertIn("summary", discovery)
        self.assertTrue(isinstance(discovery.get("apps", []), list))
        self.assertTrue(any(str(row.get("app_id", "")) == "codex_cli" for row in discovery.get("apps", [])))

        state_before = get_multi_instance_state(self.root)
        self.assertEqual(state_before.get("total_lanes"), 2)
        self.assertIn("availability_counter", state_before)

        synced = sync_multi_instance_workspaces(self.root)
        self.assertIn("state", synced)
        self.assertTrue(any(x in {"lane_a", "lane_b"} for x in (synced.get("created", []) + synced.get("existing", []))))

        state_after = get_multi_instance_state(self.root)
        self.assertEqual(state_after.get("total_lanes"), 2)
        self.assertIn("lanes", state_after)
        self.assertIn("token_telemetry", state_after)
        self.assertIn("daily", state_after["token_telemetry"])

        routed = route_message_to_lane(
            self.root,
            message="-1 build migration pack",
            task_label="migration pack build",
            apply_usage=False,
        )
        self.assertTrue(bool(routed.get("ok", False)))
        self.assertEqual(str(routed.get("directive", "")), "-1")
        lane = routed.get("lane_selected", {})
        self.assertEqual(int(lane.get("priority", 99)), 1)
        self.assertIn("token_telemetry", routed)
        self.assertIn("paid", routed["token_telemetry"])

        optimized = optimize_multi_instance_bundle(self.root, max_parallel=3, mode="auto")
        self.assertIn("selection", optimized)
        self.assertIn("state", optimized)
        selection = optimized["selection"]
        self.assertEqual(selection.get("optimizer_target"), "ccbs_multi_instance_app_bundle")
        self.assertIn("selected_tasks", selection)
        self.assertIn("solver_mode", selection)

    def test_route_parser_infers_task_metadata_and_alias_directive(self) -> None:
        prompt = (
            "#R2 I want to build a simple productivity app for my team.\n"
            "Users log in, manage to-do items, and mark done.\n"
            "Include docs and easy deployment."
        )
        routed = route_message_to_lane(
            self.root,
            message=prompt,
            task_label="",
            apply_usage=False,
        )
        self.assertTrue(bool(routed.get("ok", False)))
        self.assertEqual(str(routed.get("directive", "")), "-2")
        self.assertIn("lane_selected", routed)
        self.assertEqual(int(routed["lane_selected"].get("priority", 99)), 2)
        self.assertIn("parser", routed)
        parser = routed["parser"]
        self.assertIn("workstreams", parser)
        self.assertIn("complexity", parser)
        self.assertIn("default_task_label", parser)
        self.assertTrue(str(routed.get("task_assigned", "")).strip())
        self.assertIn("auth", [str(x) for x in parser.get("workstreams", [])])


if __name__ == "__main__":
    unittest.main()

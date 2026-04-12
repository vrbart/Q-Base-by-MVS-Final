from __future__ import annotations

import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccbs_app.ai3.foundry_pane import render_foundry_pane_html  # noqa: E402
from ccbs_app.ai3.ui_shared import render_surface_html  # noqa: E402


class FoundryPaneHtmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = render_foundry_pane_html()

    def test_html_is_non_empty_string(self) -> None:
        self.assertIsInstance(self.html, str)
        self.assertGreater(len(self.html), 500)

    def test_contains_foundry_heading(self) -> None:
        self.assertIn("CCBS Foundry Lane", self.html)

    def test_contains_gate_endpoint(self) -> None:
        self.assertIn("/v3/chat/foundry-gate", self.html)

    def test_contains_send_endpoint(self) -> None:
        self.assertIn("/v3/chat/send", self.html)

    def test_contains_remote_allowed_scope(self) -> None:
        self.assertIn("remote_allowed", self.html)

    def test_contains_gate_contract_version_constant(self) -> None:
        self.assertIn("ai3-foundry-gate-v1", self.html)

    def test_contains_pane_enabled_check(self) -> None:
        self.assertIn("pane_enabled", self.html)

    def test_contains_blocked_state_display(self) -> None:
        self.assertIn("BLOCKED", self.html)

    def test_contains_ready_state_display(self) -> None:
        self.assertIn("READY", self.html)

    def test_contains_next_actions_reference(self) -> None:
        self.assertIn("next_actions", self.html)

    def test_contains_binary_gate_description(self) -> None:
        self.assertIn("Binary gate", self.html)

    def test_contains_main_ui_link(self) -> None:
        self.assertIn("/v3/ui", self.html)

    def test_html_is_valid_html_document(self) -> None:
        self.assertIn("<!doctype html>", self.html)
        self.assertIn("</html>", self.html)

    def test_no_script_injection_vectors(self) -> None:
        # ensure no raw unsanitised dynamic interpolation paths in static HTML
        self.assertNotIn("${", self.html)

    def test_contains_refresh_button(self) -> None:
        self.assertIn("Refresh Gate", self.html)

    def test_contains_send_button(self) -> None:
        self.assertIn("Send to Foundry", self.html)


class FoundryUiSurfaceTests(unittest.TestCase):
    """Test that render_surface_html recognises the foundry-ui surface."""

    def test_foundry_ui_surface_title(self) -> None:
        html = render_surface_html("foundry-ui")
        self.assertIn("CCBS Foundry Lane", html)

    def test_foundry_ui_surface_binary_gate_subtitle(self) -> None:
        html = render_surface_html("foundry-ui")
        self.assertIn("binary gate", html.lower())

    def test_foundry_ui_surface_produces_html_document(self) -> None:
        html = render_surface_html("foundry-ui")
        self.assertIn("<!doctype html>", html)

    def test_ui_surface_unchanged(self) -> None:
        html = render_surface_html("ui")
        self.assertIn("QB Control Center", html)

    def test_chat_ui_surface_unchanged(self) -> None:
        html = render_surface_html("chat-ui")
        self.assertIn("CCBS Chat Only", html)


if __name__ == "__main__":
    unittest.main()

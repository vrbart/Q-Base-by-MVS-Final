from __future__ import annotations

import argparse
import hashlib
import json
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccbs_app import cli  # noqa: E402
from ccbs_app.ai_auth import (  # noqa: E402
    create_user,
    disable_owner_auto_auth,
    issue_token,
    resolve_owner_auto_auth_user,
    set_owner_auto_auth,
    verify_token,
)
from ccbs_app.ai_plugins import enable_plugin, install_plugin, verify_plugin  # noqa: E402


def _plugin_signature(manifest_core: dict[str, object], file_hashes: dict[str, str]) -> str:
    capabilities_raw = manifest_core.get("capabilities", [])
    capabilities = capabilities_raw if isinstance(capabilities_raw, list) else []
    payload = {
        "plugin_id": str(manifest_core["plugin_id"]),
        "version": str(manifest_core["version"]),
        "publisher": str(manifest_core["publisher"]),
        "capabilities": sorted(str(x) for x in capabilities),
        "file_hashes": dict(sorted(file_hashes.items())),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class AiAuthPluginAndCliSurfaceTests(unittest.TestCase):
    def test_ai_api_serve_rejects_non_loopback_with_owner_auto_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_user(root=root, username="demo_owner", password="strongpass1", role="admin")
            set_owner_auto_auth(root=root, username="demo_owner", enabled=True)

            args = argparse.Namespace(host="0.0.0.0", port=11435, allow_remote_owner_auto_auth=False)
            output = io.StringIO()

            original_repo_root = cli.repo_root
            original_serve_api = cli.serve_api
            try:
                cli.repo_root = lambda: root

                def _unexpected_serve_api(*args: object, **kwargs: object) -> None:
                    raise AssertionError("serve_api should not run when non-loopback guard rejects startup")

                cli.serve_api = _unexpected_serve_api
                with redirect_stdout(output):
                    rc = cli.cmd_ai_api_serve(args)
            finally:
                cli.repo_root = original_repo_root
                cli.serve_api = original_serve_api

            self.assertEqual(rc, 2)
            self.assertIn("refusing non-loopback ai api serve", output.getvalue().lower())

    def test_ai_api_serve_allows_non_loopback_with_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_user(root=root, username="demo_owner", password="strongpass1", role="admin")
            set_owner_auto_auth(root=root, username="demo_owner", enabled=True)

            captured: dict[str, object] = {}
            args = argparse.Namespace(host="0.0.0.0", port=11435, allow_remote_owner_auto_auth=True)
            output = io.StringIO()

            original_repo_root = cli.repo_root
            original_serve_api = cli.serve_api
            try:
                cli.repo_root = lambda: root

                def _capture_serve_api(*, root: Path, host: str, port: int) -> None:
                    captured["root"] = root
                    captured["host"] = host
                    captured["port"] = port

                cli.serve_api = _capture_serve_api
                with redirect_stdout(output):
                    rc = cli.cmd_ai_api_serve(args)
            finally:
                cli.repo_root = original_repo_root
                cli.serve_api = original_serve_api

            self.assertEqual(rc, 0)
            self.assertEqual(captured.get("root"), root)
            self.assertEqual(captured.get("host"), "0.0.0.0")
            self.assertEqual(captured.get("port"), 11435)
            text = output.getvalue().lower()
            self.assertIn("warn: serving the ai api on non-loopback host", text)
            self.assertIn("owner auto-auth remains enabled", text)

    def test_auth_token_issue_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_user(root=root, username="admin", password="strongpass1", role="admin")
            token = issue_token(root=root, username="admin", password="strongpass1", ttl_hours=1)
            verified = verify_token(root=root, token=token["token"], require_admin=True)
            self.assertEqual(verified["role"], "admin")

    def test_plugin_install_enable_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "demo-plugin.zip"

            plugin_file_rel = "plugin.py"
            plugin_payload = b"print('hello ccbs plugin')\n"
            file_hash = hashlib.sha256(plugin_payload).hexdigest()
            manifest_core = {
                "plugin_id": "demo-plugin",
                "version": "1.0.0",
                "publisher": "ccbs-internal",
                "capabilities": ["ingest_adapter"],
                "files": [plugin_file_rel],
            }
            sig = _plugin_signature(manifest_core, {plugin_file_rel: file_hash})
            manifest = dict(manifest_core)
            manifest["signature_sha256"] = sig

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(plugin_file_rel, plugin_payload)
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            installed = install_plugin(root=root, zip_path=zip_path)
            self.assertEqual(installed["plugin_id"], "demo-plugin")

            enabled = enable_plugin(root=root, plugin_id="demo-plugin")
            self.assertTrue(enabled["enabled"])

            verify = verify_plugin(root=root, plugin_id="demo-plugin")
            self.assertTrue(verify["ok"])

    def test_owner_auto_auth_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_user(root=root, username="demo_owner", password="strongpass1", role="admin")
            out = set_owner_auto_auth(root=root, username="demo_owner", enabled=True)
            self.assertTrue(out["enabled"])

            loopback = resolve_owner_auto_auth_user(root=root, client_host="127.0.0.1")
            if loopback is None:
                self.fail("expected loopback owner auto-auth user")
            self.assertEqual(loopback["username"], "demo_owner")
            self.assertEqual(loopback["role"], "admin")

            non_loopback = resolve_owner_auto_auth_user(root=root, client_host="10.0.0.5")
            self.assertIsNone(non_loopback)

            off = disable_owner_auto_auth(root=root)
            self.assertFalse(off["enabled"])
            self.assertIsNone(resolve_owner_auto_auth_user(root=root, client_host="127.0.0.1"))

    def test_cli_parser_registers_new_ai_namespaces(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["ai", "storage", "status"])
        self.assertEqual(args.command, "ai")
        self.assertEqual(args.ai_cmd, "storage")
        self.assertEqual(args.ai_storage_cmd, "status")

        args = parser.parse_args(["ai", "api", "serve", "--host", "0.0.0.0", "--allow-remote-owner-auto-auth"])
        self.assertEqual(args.ai_cmd, "api")
        self.assertEqual(args.ai_api_cmd, "serve")
        self.assertTrue(args.allow_remote_owner_auto_auth)

        args = parser.parse_args(["ai", "codex", "status", "--json"])
        self.assertEqual(args.ai_cmd, "codex")
        self.assertEqual(args.ai_codex_cmd, "status")

        args = parser.parse_args(["ai", "codex", "mcp-profile", "--json"])
        self.assertEqual(args.ai_cmd, "codex")
        self.assertEqual(args.ai_codex_cmd, "mcp-profile")

        args = parser.parse_args(["ai", "codex", "serve", "--port", "11436", "--allow-remote-owner-auto-auth"])
        self.assertEqual(args.ai_cmd, "codex")
        self.assertEqual(args.ai_codex_cmd, "serve")
        self.assertTrue(args.allow_remote_owner_auto_auth)

        args = parser.parse_args(["ai", "source", "add", "demo", "--uri", "https://example.com/x", "--license", "public-domain"])
        self.assertEqual(args.ai_cmd, "source")
        self.assertEqual(args.ai_source_cmd, "add")

        args = parser.parse_args(["ai", "model", "list"])
        self.assertEqual(args.ai_cmd, "model")
        self.assertEqual(args.ai_model_cmd, "list")

        args = parser.parse_args(["ai", "continue-setup", "--provider", "ollama"])
        self.assertEqual(args.ai_cmd, "continue-setup")

        args = parser.parse_args(["ai", "perf", "status", "--json"])
        self.assertEqual(args.ai_cmd, "perf")
        self.assertEqual(args.ai_perf_cmd, "status")

        args = parser.parse_args(["ai", "perf", "benchmark", "--provider", "local", "--model", "llama3.1:8b"])
        self.assertEqual(args.ai_cmd, "perf")
        self.assertEqual(args.ai_perf_cmd, "benchmark")

        args = parser.parse_args(["ai", "quota", "status", "--json"])
        self.assertEqual(args.ai_cmd, "quota")
        self.assertEqual(args.ai_quota_cmd, "status")

        args = parser.parse_args(["ai", "key", "status", "--provider", "codex", "--user-id", "u1"])
        self.assertEqual(args.ai_cmd, "key")
        self.assertEqual(args.ai_key_cmd, "status")

        args = parser.parse_args(["ai", "route-policy", "simulate", "hello", "--metadata-json", "{\"has_urls\":true}"])
        self.assertEqual(args.ai_cmd, "route-policy")
        self.assertEqual(args.ai_route_policy_cmd, "simulate")

        args = parser.parse_args(["ai", "add-context", "--source-id", "rosetta", "--continue-config", ".continue/config.json"])
        self.assertEqual(args.ai_cmd, "add-context")

        args = parser.parse_args(["ai", "prompt-pack", "list"])
        self.assertEqual(args.ai_cmd, "prompt-pack")
        self.assertEqual(args.ai_prompt_pack_cmd, "list")

        args = parser.parse_args(["ai", "prompt-pack", "show", "--pack", "safe_computer_access"])
        self.assertEqual(args.ai_cmd, "prompt-pack")
        self.assertEqual(args.ai_prompt_pack_cmd, "show")

        args = parser.parse_args(
            [
                "ai",
                "prompt-pack",
                "export",
                "--pack",
                "safe_computer_access",
                "--output",
                "out.md",
                "--format",
                "markdown",
            ]
        )
        self.assertEqual(args.ai_cmd, "prompt-pack")
        self.assertEqual(args.ai_prompt_pack_cmd, "export")

        args = parser.parse_args(["ai", "usecase", "build", "--source", "docs"])
        self.assertEqual(args.ai_cmd, "usecase")
        self.assertEqual(args.ai_usecase_cmd, "build")

        args = parser.parse_args(["ai", "chat", "models", "--json"])
        self.assertEqual(args.ai_cmd, "chat")
        self.assertEqual(args.chat_cmd, "models")

        args = parser.parse_args(["ai", "chat", "profile", "--user-id", "owner"])
        self.assertEqual(args.ai_cmd, "chat")
        self.assertEqual(args.chat_cmd, "profile")

        args = parser.parse_args(
            [
                "ai",
                "user",
                "pref",
                "set",
                "--username",
                "alice",
                "--task-type",
                "complex",
                "--provider",
                "codex",
            ]
        )
        self.assertEqual(args.ai_cmd, "user")
        self.assertEqual(args.ai_user_cmd, "pref")
        self.assertEqual(args.ai_user_pref_cmd, "set")

        args = parser.parse_args(["ai", "user", "owner-auth", "set", "--username", "demo_owner"])
        self.assertEqual(args.ai_cmd, "user")
        self.assertEqual(args.ai_user_cmd, "owner-auth")
        self.assertEqual(args.ai_user_owner_auth_cmd, "set")


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.zcode_supervisor.repo_setup import AGENTS_BEGIN
from tools.zcode_supervisor.zcode_supervisor import main


class ZCodeRepoSetupTests(unittest.TestCase):
    def _main_json(self, argv: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(argv)
        return exit_code, json.loads(output.getvalue())

    def test_install_repo_writes_routing_contract_and_vision_mcp_without_agents_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))

            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)

            routing = repo / ".codex/zcode-routing.json"
            delegation = repo / ".codex/ZCODE_DELEGATION.md"
            vision_mcp = repo / ".agents/mcp.json"
            self.assertTrue(routing.exists())
            self.assertTrue(delegation.exists())
            self.assertTrue(vision_mcp.exists())
            self.assertFalse((repo / "AGENTS.md").exists())
            payload = json.loads(routing.read_text(encoding="utf-8"))
            self.assertEqual(payload["orchestrator"], "codex")
            self.assertEqual(payload["implementation_worker"], "zcode")
            self.assertEqual(payload["routing_mode"], "auto")
            self.assertIn("zcode_unavailable_recovery", payload["policy"]["codex_direct_edit_allowed"])
            self.assertIn("production_risk", payload["policy"]["ask_user_before"])
            self.assertEqual(payload["vision"]["service"], "zai-mcp-server")
            self.assertIn("bounded_implementation", payload["policy"]["zcode_owns"])
            delegation_text = delegation.read_text(encoding="utf-8")
            self.assertIn("auto-route", delegation_text)
            self.assertIn("zcodectl run-packet", delegation_text)
            mcp = json.loads(vision_mcp.read_text(encoding="utf-8"))
            self.assertEqual(mcp["mcpServers"]["zai-mcp-server"]["command"], "npx")
            self.assertEqual(mcp["mcpServers"]["zai-mcp-server"]["args"], ["-y", "@z_ai/mcp-server"])

    def test_install_repo_can_skip_vision_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))

            self.assertEqual(main(["install-repo", "--repo", str(repo), "--skip-vision-mcp"]), 0)

            self.assertFalse((repo / ".agents/mcp.json").exists())

    def test_install_repo_can_add_agents_pointer_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))
            (repo / "AGENTS.md").write_text("# Local Rules\n\nKeep changes small.\n", encoding="utf-8")

            self.assertEqual(main(["install-repo", "--repo", str(repo), "--write-agents"]), 0)
            self.assertEqual(main(["install-repo", "--repo", str(repo), "--write-agents"]), 0)

            agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(".codex/ZCODE_DELEGATION.md", agents)
            self.assertIn("auto-route", agents)
            self.assertEqual(agents.count(AGENTS_BEGIN), 1)

    def test_install_repo_merges_vision_mcp_without_replacing_existing_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))
            mcp = repo / ".agents/mcp.json"
            mcp.parent.mkdir(parents=True)
            mcp.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "existing": {"command": "custom-mcp"},
                            "zai-mcp-server": {"command": "already-configured"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)

            payload = json.loads(mcp.read_text(encoding="utf-8"))
            self.assertEqual(payload["mcpServers"]["existing"]["command"], "custom-mcp")
            self.assertEqual(payload["mcpServers"]["zai-mcp-server"]["command"], "already-configured")

            self.assertEqual(main(["install-repo", "--repo", str(repo), "--force"]), 0)

            payload = json.loads(mcp.read_text(encoding="utf-8"))
            self.assertEqual(payload["mcpServers"]["existing"]["command"], "custom-mcp")
            self.assertEqual(payload["mcpServers"]["zai-mcp-server"]["command"], "npx")

    def test_install_repo_rejects_symlinked_output_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._fixture_workspace(root)
            outside = root / "outside"
            outside.mkdir()
            (repo / ".codex").symlink_to(outside, target_is_directory=True)

            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 1)

            self.assertFalse((outside / "zcode-routing.json").exists())

    def test_install_repo_rejects_symlinked_agents_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._fixture_workspace(root)
            outside = root / "outside-agents.md"
            outside.write_text("outside\n", encoding="utf-8")
            (repo / "AGENTS.md").symlink_to(outside)

            self.assertEqual(main(["install-repo", "--repo", str(repo), "--write-agents"]), 1)

            self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_auto_route_reports_missing_config_as_codex_direct(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))

            exit_code, payload = self._main_json(
                ["auto-route", "--workspace", str(repo), "--objective", "fix src/app.js"]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["route"], "codex_direct")
            self.assertEqual(payload["reason"], "routing_config_missing")

    def test_auto_route_classifies_implementation_as_needing_codex_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))
            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)

            exit_code, payload = self._main_json(
                ["auto-route", "--workspace", str(repo), "--objective", "fix src/app.js"]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["route"], "needs_codex_planning")
            self.assertEqual(payload["reason"], "missing_allowed_or_validation")

    def test_auto_route_keeps_no_zcode_and_high_risk_with_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture_workspace(Path(tmp))
            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)

            exit_code, payload = self._main_json(
                ["auto-route", "--workspace", str(repo), "--objective", "no-zcode fix src/app.js"]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["route"], "codex_direct")
            self.assertEqual(payload["reason"], "no_zcode_requested")

            exit_code, payload = self._main_json(
                ["auto-route", "--workspace", str(repo), "--objective", "no-zcode delete production data"]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["route"], "ask_user")
            self.assertEqual(payload["reason"], "high_risk_task")

            exit_code, payload = self._main_json(
                ["auto-route", "--workspace", str(repo), "--objective", "deploy production migration"]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["route"], "ask_user")
            self.assertEqual(payload["reason"], "high_risk_task")

    def test_auto_route_execute_creates_packet_and_runs_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._fixture_workspace(root)
            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)
            fake_controller = root / "fake-zcodectl.mjs"
            fake_controller.write_text(
                """#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
	const out = process.argv[process.argv.indexOf("--out") + 1];
	const retryDelayMs = process.argv[process.argv.indexOf("--retry-delay-ms") + 1];
	const payload = { ok: true, supervisor_state: "success", validation_ok: true, retry_delay_ms: retryDelayMs };
	fs.mkdirSync(path.dirname(out), { recursive: true });
	fs.writeFileSync(out, JSON.stringify(payload) + "\\n");
	process.stdout.write(JSON.stringify(payload) + "\\n");
""",
                encoding="utf-8",
            )
            routing = repo / ".codex/zcode-routing.json"
            payload = json.loads(routing.read_text(encoding="utf-8"))
            payload["paths"]["zcodectl"] = str(fake_controller)
            routing.write_text(json.dumps(payload), encoding="utf-8")

            exit_code, result = self._main_json(
                [
                    "auto-route",
                    "--workspace",
                    str(repo),
                    "--objective",
                    "fix src/app.js",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--execute",
                    "--max-attempts",
                    "1",
                    "--retry-delay-ms",
                    "0",
                    "--trusted-zcodectl",
                    str(fake_controller),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(result["executed"])
            self.assertEqual(result["route"], "delegate_zcode")
            self.assertEqual(result["run_result"]["supervisor_state"], "success")
            self.assertEqual(result["run_result"]["retry_delay_ms"], "0")
            self.assertTrue(Path(result["packet"]).exists())
            self.assertTrue(Path(result["run"]).exists())

    def test_auto_route_rejects_repo_controlled_output_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._fixture_workspace(root)
            self.assertEqual(main(["install-repo", "--repo", str(repo)]), 0)
            routing = repo / ".codex/zcode-routing.json"
            payload = json.loads(routing.read_text(encoding="utf-8"))
            payload["paths"]["packets"] = "../outside"
            routing.write_text(json.dumps(payload), encoding="utf-8")

            exit_code, result = self._main_json(
                [
                    "auto-route",
                    "--workspace",
                    str(repo),
                    "--objective",
                    "fix src/app.js",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--execute",
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(result["ok"])
            self.assertIn("escapes workspace", result["error"])

    def _fixture_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        (workspace / "src").mkdir(parents=True)
        (workspace / "src/app.js").write_text("export const value = 1;\n", encoding="utf-8")
        (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
        return workspace


if __name__ == "__main__":
    unittest.main()

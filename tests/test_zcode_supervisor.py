import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.zcode_supervisor.zcode_supervisor import classify_provider_error, classify_provider_run_state, main


class ZCodeSupervisorTests(unittest.TestCase):
    def test_provider_error_classifier_extracts_zcode_overload(self):
        stderr = (
            "ProviderBusinessError: [1305][The service may be temporarily overloaded, please try again later][req-1]\n"
            "  code: 'PROVIDER_BUSINESS_ERROR',\n"
            "  isProviderBusinessError: true,\n"
            "  providerCode: '1305',\n"
            "  providerId: 'zai',\n"
            "  providerKind: 'anthropic',\n"
            "  providerMessage: '[1305][The service may be temporarily overloaded, please try again later][req-1]'\n"
        )

        provider = classify_provider_error(stderr=stderr, exit_code=143)

        self.assertTrue(provider["provider_error"])
        self.assertEqual(provider["provider_code"], "1305")
        self.assertEqual(provider["provider_id"], "zai")
        self.assertEqual(provider["provider_kind"], "anthropic")
        self.assertTrue(provider["provider_error_temporary"])
        self.assertTrue(provider["retryable_provider_error"])

    def test_provider_error_classifier_handles_exit_143_without_stderr(self):
        provider = classify_provider_error(exit_code=143)

        self.assertTrue(provider["provider_error"])
        self.assertIsNone(provider["provider_code"])
        self.assertTrue(provider["retryable_provider_error"])

    def test_provider_run_state_splits_retryable_partial_and_unsafe(self):
        provider = classify_provider_error(
            stderr="ProviderBusinessError: [1305][The service may be temporarily overloaded, please try again later][req-1]",
            exit_code=143,
        )

        self.assertEqual(
            classify_provider_run_state(provider, {"changed_count": 0, "ok": False})["supervisor_state"],
            "retryable_provider_error",
        )
        self.assertEqual(
            classify_provider_run_state(provider, {"changed_count": 1, "ok": True})["supervisor_state"],
            "partial_success",
        )
        self.assertEqual(
            classify_provider_run_state(provider, {"changed_count": 1, "ok": False})["supervisor_state"],
            "unsafe_partial",
        )

    def test_packet_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            packet = Path(tmp) / "packet.json"
            prompt = Path(tmp) / "packet.prompt.txt"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "fix safely",
                    "--allowed",
                    "../outside.js",
                    "--validation",
                    "python3 -c pass",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_audit_passes_for_allowed_change_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"

            self.assertEqual(main(["snapshot", "--workspace", str(workspace), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--forbidden",
                        "README.md",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            (workspace / "src/app.js").write_text("export const value = 2;\n", encoding="utf-8")

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                0,
            )

    def test_audit_blocks_forbidden_and_outside_allowed_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"
            self.assertEqual(main(["snapshot", "--workspace", str(workspace), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--forbidden",
                        "README.md",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            (workspace / "README.md").write_text("changed\n", encoding="utf-8")
            (workspace / "src/extra.js").write_text("export const extra = true;\n", encoding="utf-8")

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                1,
            )

    def test_audit_blocks_max_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"
            self.assertEqual(main(["snapshot", "--workspace", str(workspace), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--allowed",
                        "README.md",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--max-changed-files",
                        "1",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            (workspace / "README.md").write_text("changed\n", encoding="utf-8")
            (workspace / "src/app.js").write_text("export const value = 3;\n", encoding="utf-8")

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                1,
            )

    def test_audit_blocks_secret_pattern_and_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"
            self.assertEqual(main(["snapshot", "--workspace", str(workspace), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'import sys; sys.exit(3)'",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            marker = "tok" + "en=not-a-real-secret-value"
            (workspace / "src/app.js").write_text(f"const fake = '{marker}';\n", encoding="utf-8")

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                1,
            )

    def test_audit_rejects_tampered_destructive_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"
            self.assertEqual(main(["snapshot", "--workspace", str(workspace), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            payload["validation"] = "rm -rf build"
            packet.write_text(json.dumps(payload), encoding="utf-8")

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                1,
            )

    def test_audit_blocks_workspace_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            other = self._fixture_workspace(Path(tmp) / "other-root")
            snapshot = Path(tmp) / "snapshot.json"
            packet = Path(tmp) / "packet.json"
            self.assertEqual(main(["snapshot", "--workspace", str(other), "--out", str(snapshot)]), 0)
            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "update app implementation",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )

            self.assertEqual(
                main(["audit", "--workspace", str(workspace), "--snapshot", str(snapshot), "--packet", str(packet)]),
                1,
            )

    def test_packet_contains_prompt_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"
            prompt = Path(tmp) / "packet.prompt.txt"

            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "small fix",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--goal",
                        "--out",
                        str(packet),
                        "--prompt-out",
                        str(prompt),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertTrue(payload["prompt"].startswith("/goal "))
            self.assertLess(payload["approx_prompt_tokens"], 460)
            self.assertEqual(prompt.read_text(encoding="utf-8"), payload["prompt"])

    def test_packet_records_glm52_operating_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "trace a cross-module defect",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--effort",
                        "max",
                        "--task-class",
                        "root-cause",
                        "--context-policy",
                        "Trace the call chain before editing.",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(payload["effort"], "max")
            self.assertEqual(payload["task_class"], "root-cause")
            self.assertIn("Trace the call chain before editing.", payload["prompt"])

    def test_packet_records_vision_images_and_text_only_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            (workspace / "screenshots").mkdir()
            (workspace / "screenshots/state.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            packet = Path(tmp) / "packet.json"

            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "implement from the attached screenshot",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--vision-image",
                        "screenshots/state.png",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertTrue(payload["vision"]["required"])
            self.assertEqual(payload["vision"]["service"], "zai-mcp-server")
            self.assertEqual(payload["vision"]["image_files"], ["screenshots/state.png"])
            self.assertIn("GLM-5.2 is text-only", payload["prompt"])
            self.assertIn("uppercase #RRGGBB", payload["prompt"])
            self.assertIn("vision_service_unavailable", payload["prompt"])

    def test_packet_records_deterministic_color_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            image = workspace / "screenshots/state.png"
            image.parent.mkdir()
            self._write_rgb_png(
                image,
                3,
                3,
                [
                    [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
                    [(0, 0, 0), (0x7C, 0x3A, 0xED), (0, 0, 0)],
                    [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
                ],
            )
            packet = Path(tmp) / "packet.json"

            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "implement exact colors from screenshot",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--vision-color-sample",
                        "primary=screenshots/state.png@1,1",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertTrue(payload["vision"]["required"])
            self.assertEqual(payload["vision"]["image_files"], ["screenshots/state.png"])
            self.assertEqual(payload["vision"]["color_samples"][0]["hex"], "#7C3AED")
            self.assertEqual(payload["vision"]["color_samples"][0]["rgba"], [124, 58, 237, 255])
            self.assertIn("Deterministic color samples", payload["prompt"])
            self.assertIn("primary: screenshots/state.png@1,1 = #7C3AED", payload["prompt"])

    def test_packet_rejects_color_sample_outside_image_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            image = workspace / "screenshots/state.png"
            image.parent.mkdir()
            self._write_rgb_png(image, 1, 1, [[(0x7C, 0x3A, 0xED)]])
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "sample exact colors",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--vision-color-sample",
                    "primary=screenshots/state.png@9,0",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_rejects_color_sample_with_huge_decompressed_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            image = workspace / "screenshots/huge.png"
            image.parent.mkdir()
            self._write_minimal_png(image, width=100_000, height=100_000)
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "sample exact colors",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--vision-color-sample",
                    "primary=screenshots/huge.png@0,0",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_rejects_color_sample_with_malformed_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            image = workspace / "screenshots/broken.png"
            image.parent.mkdir()
            image.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 1)
                + b"IHDR"
                + b"\x00"
                + struct.pack(">I", zlib.crc32(b"IHDR\x00") & 0xFFFFFFFF)
            )
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "sample exact colors",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--vision-color-sample",
                    "primary=screenshots/broken.png@0,0",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_rejects_missing_vision_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "use an image",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--vision-image",
                    "screenshots/missing.png",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_rejects_full_access_regular_workspace_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "fix safely",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "python3 -c 'print(42)'",
                    "--mode",
                    "Full Access",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_allows_full_access_fixture_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            self.assertEqual(
                main(
                    [
                        "packet",
                        "--workspace",
                        str(workspace),
                        "--objective",
                        "fix fixture",
                        "--allowed",
                        "src/app.js",
                        "--validation",
                        "python3 -c 'print(42)'",
                        "--mode",
                        "Full Access",
                        "--workspace-kind",
                        "fixture",
                        "--out",
                        str(packet),
                    ]
                ),
                0,
            )
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(payload["workspace_kind"], "fixture")

    def test_packet_rejects_destructive_validation_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "fix safely",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "rm -rf build",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def test_packet_rejects_shell_wrapped_destructive_validation_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self._fixture_workspace(Path(tmp))
            packet = Path(tmp) / "packet.json"

            exit_code = main(
                [
                    "packet",
                    "--workspace",
                    str(workspace),
                    "--objective",
                    "fix safely",
                    "--allowed",
                    "src/app.js",
                    "--validation",
                    "bash -lc 'git clean -fd'",
                    "--out",
                    str(packet),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(packet.exists())

    def _fixture_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        (workspace / "src").mkdir(parents=True)
        (workspace / "src/app.js").write_text("export const value = 1;\n", encoding="utf-8")
        (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
        return workspace

    def _write_rgb_png(self, path: Path, width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        rows = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b"")
        )

    def _write_minimal_png(self, path: Path, width: int, height: int) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00"))
            + chunk(b"IEND", b"")
        )


if __name__ == "__main__":
    unittest.main()

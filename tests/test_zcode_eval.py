import json
import tempfile
import unittest
from pathlib import Path

from tools.zcode_eval.zcode_eval import build_summary, load_records, main


class ZCodeEvalTests(unittest.TestCase):
    def test_append_and_load_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "eval.jsonl"
            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-1",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-a",
                    "--task-name",
                    "small fixture",
                    "--status",
                    "pass",
                    "--manual-interventions",
                    "2",
                    "--tokens-total",
                    "1000",
                ]
            )

            self.assertEqual(exit_code, 0)
            records = load_records(ledger)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["tool"], "zcode")
            self.assertEqual(records[0]["manual_interventions"], 2.0)

    def test_append_derives_token_and_quota_usage_from_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "eval.jsonl"
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(
                '{"best":{"tokens_total":1000,"quota_percent":88.5}}\n',
                encoding="utf-8",
            )
            after.write_text(
                '{"best":{"tokens_total":1450,"quota_percent":87.0}}\n',
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-usage",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-usage",
                    "--task-name",
                    "usage fixture",
                    "--status",
                    "pass",
                    "--usage-before",
                    str(before),
                    "--usage-after",
                    str(after),
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertEqual(record["tokens_before"], 1000.0)
            self.assertEqual(record["tokens_after"], 1450.0)
            self.assertEqual(record["tokens_used"], 450.0)
            self.assertEqual(record["quota_percent_before"], 88.5)
            self.assertEqual(record["quota_percent_after"], 87.0)
            self.assertEqual(record["quota_percent_used"], 1.5)

    def test_append_derives_used_quota_from_codexbar_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "eval.jsonl"
            before = root / "codexbar-before.json"
            after = root / "codexbar-after.json"
            before.write_text(
                """
                [
                  {
                    "provider": "zai",
                    "source": "api",
                    "usage": {
                      "primary": {
                        "resetDescription": "5 hours window",
                        "resetsAt": "2026-06-17T18:30:44Z",
                        "usedPercent": 1.25
                      },
                      "secondary": {
                        "resetDescription": "Monthly",
                        "resetsAt": "2026-07-04T05:08:05Z",
                        "usedPercent": 0.5
                      }
                    }
                  }
                ]
                """,
                encoding="utf-8",
            )
            after.write_text(
                """
                [
                  {
                    "provider": "zai",
                    "source": "api",
                    "usage": {
                      "primary": {
                        "resetDescription": "5 hours window",
                        "resetsAt": "2026-06-17T18:30:44Z",
                        "usedPercent": 1.75
                      },
                      "secondary": {
                        "resetDescription": "Monthly",
                        "resetsAt": "2026-07-04T05:08:05Z",
                        "usedPercent": 0.6
                      }
                    }
                  }
                ]
                """,
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-codexbar",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-codexbar",
                    "--task-name",
                    "codexbar fixture",
                    "--status",
                    "pass",
                    "--usage-before",
                    str(before),
                    "--usage-after",
                    str(after),
                    "--quota-percent-direction",
                    "used",
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertEqual(record["quota_percent_direction"], "used")
            self.assertEqual(record["quota_percent_before"], 1.25)
            self.assertEqual(record["quota_percent_after"], 1.75)
            self.assertEqual(record["quota_percent_used"], 0.5)

    def test_append_derives_used_quota_from_zai_api_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "eval.jsonl"
            before = root / "zai-before.json"
            after = root / "zai-after.json"
            before.write_text(
                """
                {
                  "code": 200,
                  "data": {
                    "level": "pro",
                    "limits": [
                      {
                        "type": "TOKENS_LIMIT",
                        "percentage": 2.0,
                        "usage": 2000,
                        "remaining": 98000,
                        "nextResetTime": 1781680000000
                      },
                      {"type": "TIME_LIMIT", "percentage": 0.5, "usage": 30, "remaining": 70}
                    ]
                  }
                }
                """,
                encoding="utf-8",
            )
            after.write_text(
                """
                {
                  "code": 200,
                  "data": {
                    "level": "pro",
                    "limits": [
                      {
                        "type": "TOKENS_LIMIT",
                        "percentage": 2.75,
                        "usage": 2750,
                        "remaining": 97250,
                        "nextResetTime": 1781680000000
                      },
                      {"type": "TIME_LIMIT", "percentage": 0.5, "usage": 30, "remaining": 70}
                    ]
                  }
                }
                """,
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-zai-api",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-zai-api",
                    "--task-name",
                    "zai api fixture",
                    "--status",
                    "pass",
                    "--usage-before",
                    str(before),
                    "--usage-after",
                    str(after),
                    "--quota-percent-direction",
                    "used",
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertEqual(record["quota_percent_direction"], "used")
            self.assertEqual(record["quota_percent_before"], 2.0)
            self.assertEqual(record["quota_percent_after"], 2.75)
            self.assertEqual(record["quota_percent_used"], 0.75)
            self.assertEqual(record["quota_percent_status"], "measured")

    def test_append_derives_zai_api_quota_percent_without_token_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "eval.jsonl"
            before = root / "zai-before.json"
            after = root / "zai-after.json"
            before.write_text(
                """
                {
                  "code": 200,
                  "data": {
                    "level": "pro",
                    "limits": [
                      {"type": "TOKENS_LIMIT", "percentage": 2.0, "usage": null, "remaining": null},
                      {"type": "TIME_LIMIT", "percentage": 0.5, "usage": 30, "remaining": 70}
                    ]
                  }
                }
                """,
                encoding="utf-8",
            )
            after.write_text(
                """
                {
                  "code": 200,
                  "data": {
                    "level": "pro",
                    "limits": [
                      {"type": "TOKENS_LIMIT", "percentage": 2.75, "usage": null, "remaining": null},
                      {"type": "TIME_LIMIT", "percentage": 0.5, "usage": 30, "remaining": 70}
                    ]
                  }
                }
                """,
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-zai-api-percent-only",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-zai-api-percent-only",
                    "--task-name",
                    "zai api percent-only fixture",
                    "--status",
                    "pass",
                    "--usage-before",
                    str(before),
                    "--usage-after",
                    str(after),
                    "--quota-percent-direction",
                    "used",
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertEqual(record["quota_percent_before"], 2.0)
            self.assertEqual(record["quota_percent_after"], 2.75)
            self.assertEqual(record["quota_percent_used"], 0.75)
            self.assertEqual(record["quota_percent_status"], "measured")
            self.assertNotIn("quota_percent_unavailable_reason", record)

    def test_append_records_provider_retry_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "eval.jsonl"

            exit_code = main(
                [
                    "append-result",
                    "--path",
                    str(ledger),
                    "--run-id",
                    "run-provider",
                    "--tool",
                    "zcode",
                    "--task-id",
                    "task-provider",
                    "--task-name",
                    "provider fixture",
                    "--status",
                    "partial",
                    "--supervisor-state",
                    "partial_success",
                    "--provider-error",
                    "--provider-code",
                    "1305",
                    "--provider-id",
                    "zai",
                    "--provider-kind",
                    "anthropic",
                    "--attempts",
                    "2",
                    "--attempt-count",
                    "2",
                    "--retry-count",
                    "1",
                    "--retry-delays-ms",
                    "[100,200]",
                    "--partial-artifacts-possible",
                    "--no-safe-to-retry-later",
                    "--no-usage-available",
                    "--no-usage-reason",
                    "provider_error_without_zcode_cli_usage",
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertTrue(record["provider_error"])
            self.assertEqual(record["provider_code"], "1305")
            self.assertEqual(record["supervisor_state"], "partial_success")
            self.assertEqual(record["attempts"], 2)
            self.assertEqual(record["attempt_count"], 2)
            self.assertEqual(record["retry_count"], 1)
            self.assertEqual(record["retry_delays_ms"], [100, 200])
            self.assertTrue(record["partial_artifacts_possible"])
            self.assertFalse(record["safe_to_retry_later"])
            self.assertFalse(record["usage_available"])
            self.assertEqual(record["no_usage_reason"], "provider_error_without_zcode_cli_usage")

    def test_import_duel_results_enriches_zcode_provider_error_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            run_dir = project / "work" / "supervisor_duel_eval" / "runs" / "20260617-153042"
            control = run_dir / "_control" / "zcode" / "site_ops"
            control.mkdir(parents=True)
            result_json = control / "zcode-result.json"
            result_json.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "exit_code": 143,
                        "stdout": "",
                        "stderr": (
                            "ProviderBusinessError: [1305][The service may be temporarily overloaded, "
                            "please try again later][req-1]\n"
                            "  providerCode: '1305',\n"
                            "  providerId: 'zai',\n"
                            "  providerKind: 'anthropic',\n"
                            "  providerRequestId: 'req-1'\n"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            source = run_dir / "results.json"
            source.write_text(
                json.dumps(
                    {
                        "run_dir": "work/supervisor_duel_eval/runs/20260617-153042",
                        "errors": [],
                        "rows": [
                            {
                                "tool": "zcode",
                                "task_id": "site_ops",
                                "kind": "sophisticated website",
                                "run_ok": False,
                                "validation_ok": True,
                                "scope_ok": True,
                                "output_files_ok": True,
                                "quality_score": 8,
                                "wall_ms": 123000,
                                "tokens_total": None,
                                "changed_files": ["index.html"],
                                "lines_added": 10,
                                "lines_deleted": 1,
                                "preview": str(run_dir / "zcode" / "site_ops" / "index.html"),
                                "audit": {"ok": True, "changed_count": 1},
                                "validation": {"ok": True, "returncode": 0},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            ledger = root / "eval.jsonl"

            exit_code = main(
                [
                    "import-duel-results",
                    "--source",
                    str(source),
                    "--path",
                    str(ledger),
                ]
            )

            self.assertEqual(exit_code, 0)
            record = load_records(ledger)[0]
            self.assertEqual(record["tool"], "zcode")
            self.assertEqual(record["status"], "partial")
            self.assertEqual(record["supervisor_state"], "partial_success")
            self.assertTrue(record["provider_error"])
            self.assertEqual(record["provider_code"], "1305")
            self.assertEqual(record["provider_request_id"], "req-1")
            self.assertEqual(record["attempt_count"], 1)
            self.assertEqual(record["retry_delays_ms"], [])
            self.assertFalse(record["usage_available"])
            self.assertEqual(record["no_usage_reason"], "provider_error_without_zcode_cli_usage")
            self.assertEqual(record["quota_percent_status"], "unavailable")
            self.assertEqual(
                record["quota_percent_unavailable_reason"],
                "historical_duel_missing_authoritative_quota_snapshot",
            )

    def test_summary_groups_by_tool(self):
        summary = build_summary(
            [
                {"tool": "zcode", "status": "pass", "tokens_used": 100.0, "quota_percent_used": 1.0},
                {
                    "tool": "zcode",
                    "status": "fail",
                    "tokens_used": 300.0,
                    "quota_percent_used": 3.0,
                    "provider_error": True,
                    "safe_to_retry_later": True,
                },
                {"tool": "zcode", "status": "partial", "supervisor_state": "partial_success"},
                {"tool": "claude-code-glm52", "status": "pass", "tokens_total": 200.0},
            ]
        )

        self.assertEqual(summary["records"], 4)
        self.assertEqual(summary["tools"]["zcode"]["runs"], 3)
        self.assertEqual(summary["tools"]["zcode"]["pass_rate"], 0.333)
        self.assertEqual(summary["tools"]["zcode"]["avg_tokens_used"], 200.0)
        self.assertEqual(summary["tools"]["zcode"]["total_quota_percent_used"], 4.0)
        self.assertEqual(summary["tools"]["zcode"]["provider_errors"], 1)
        self.assertEqual(summary["tools"]["zcode"]["retryable_provider_errors"], 1)
        self.assertEqual(summary["tools"]["zcode"]["partial_successes"], 1)


if __name__ == "__main__":
    unittest.main()

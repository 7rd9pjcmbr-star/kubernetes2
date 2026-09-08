#!/usr/bin/env python3
"""Tests for logistics_tool CLI."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import logistics_tool


class LogisticsToolTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.env_patch = mock.patch.dict(
            os.environ,
            {"LOGISTICS_TOOL_STATE_DIR": str(self.state_dir)},
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_status_lists_all_scripts(self):
        with mock.patch("sys.stdout", new=mock.MagicMock()):
            code = logistics_tool.main(["status"])
        self.assertEqual(code, 0)

    def test_record_and_load_history(self):
        logistics_tool.record_run("check-apis", 0)
        history = logistics_tool.load_history()
        self.assertEqual(len(history["runs"]), 1)
        self.assertEqual(history["runs"][0]["name"], "check-apis")

    def test_runbook_scan_pipeline_dry_run(self):
        with mock.patch("logistics_tool.run_script", return_value=0) as run_script:
            code = logistics_tool.main(
                [
                    "runbook-scan-pipeline",
                    "--dry-run",
                    "--platform",
                    "sapo",
                    "--max-per-platform",
                    "10",
                    "--max-files",
                    "5",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(run_script.call_count, 3)
        run_script.assert_any_call(
            "clean-accounts",
            ["--auto", "--platform", "sapo"],
            dry_run=True,
        )

    def test_forward_script_args(self):
        with mock.patch("logistics_tool.run_script", return_value=0) as run_script:
            code = logistics_tool.main(["check-apis", "--", "--timeout", "5"])
        self.assertEqual(code, 0)
        run_script.assert_called_once_with("check-apis", ["--timeout", "5"])

    def test_load_env_file_sets_defaults(self):
        env_path = self.state_dir / "env.example"
        env_path.write_text('PANCAKE_POS_API_KEY="abc123"\n# comment\nEMPTY=\n', encoding="utf-8")
        with mock.patch("logistics_tool.ENV_FILE", env_path):
            logistics_tool.load_env_file(env_path)
        self.assertEqual(os.environ.get("PANCAKE_POS_API_KEY"), "abc123")

    def test_history_file_written(self):
        logistics_tool.record_run("scan-orders", 1, {"command": ["python", "scan"]})
        history_path = logistics_tool.state_file()
        self.assertTrue(history_path.exists())
        payload = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["runs"][-1]["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "session-summary/scripts")
)
import autosave
import retrieval
import rollup
from save_summary import save_summary


SESSION = "12345678-1234-1234-1234-123456789abc"
OTHER = "87654321-4321-4321-4321-cba987654321"


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.cwd = self.home / "project"
        (self.cwd / ".git").mkdir(parents=True)
        patcher = patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ, {"COPILOT_HOME": str(self.home / ".copilot")})
        environment.start()
        self.addCleanup(environment.stop)
        self.payload = {
            "sessionId": SESSION, "cwd": str(self.cwd), "source": "startup",
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

    def raw(self, text, day="2026-10-21", session=SESSION):
        return save_summary(self.cwd, session, day, text)

    def test_empty_project_reads_without_creating_storage(self):
        self.assertIn("No saved session history", retrieval.retrieve(self.cwd))
        self.assertFalse((self.home / ".copilot").exists())

    def test_latest_rollup_and_only_uncovered_raw_content(self):
        self.raw("Old raw work.")
        rollup.save(rollup.prepare(self.cwd, "2026-10-21"), "Older synthesis.")
        self.raw("Second raw work.", "2026-10-22", OTHER)
        latest = rollup.save(
            rollup.prepare(self.cwd, "2026-10-22"), "Latest synthesis."
        )
        self.raw("Late progress.", session=OTHER)
        original = latest.read_bytes()
        content = retrieval.retrieve(self.cwd)
        self.assertIn("Latest synthesis.", content)
        self.assertNotIn("Older synthesis.", content)
        self.assertNotIn("Old raw work.", content)
        self.assertNotIn("Second raw work.", content)
        self.assertIn("Late progress.", content)
        self.assertIn(f"copilot --resume={OTHER}", content)
        self.assertIn("2026-10-21", content)
        self.assertIn(str(latest), content)
        self.assertIn("earlier rollups are not included", content)
        self.assertEqual(latest.read_bytes(), original)
        self.assertEqual(len(rollup.prepare(self.cwd, "2026-10-23")["pending"]), 1)

    def test_without_rollups_includes_raw_progress_and_all_references(self):
        self.raw("First.")
        self.raw("Second.", "2026-10-22", OTHER)
        content = retrieval.retrieve(self.cwd)
        for expected in ("First.", "Second.", SESSION, OTHER, "2026-10-22"):
            self.assertIn(expected, content)

    def test_all_reads_rollups_chronologically_then_uncovered_progress(self):
        self.raw("Covered first raw.")
        first = rollup.save(rollup.prepare(self.cwd, "2026-10-21"), "First synthesis.")
        self.raw("Covered second raw.", "2026-10-22", OTHER)
        second = rollup.save(rollup.prepare(self.cwd, "2026-10-22"), "Second synthesis.")
        self.raw("Uncovered addition.", session=OTHER)
        before = {path: path.read_bytes() for path in (first, second)}
        content = retrieval.retrieve(self.cwd, all_history=True)
        self.assertLess(content.index("First synthesis."), content.index("Second synthesis."))
        self.assertLess(content.index("Second synthesis."), content.index("Uncovered addition."))
        self.assertNotIn("Covered first raw.", content)
        self.assertNotIn("Covered second raw.", content)
        self.assertNotIn("earlier rollups are not included", content)
        self.assertIn("all rollups", content)
        for day, session in (("2026-10-21", SESSION), ("2026-10-22", OTHER)):
            self.assertIn(day, content)
            self.assertIn(f"copilot --resume={session}", content)
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)

    def test_all_without_rollups_and_without_history(self):
        self.assertIn("No saved session history", retrieval.retrieve(self.cwd, all_history=True))
        self.assertFalse((self.home / ".copilot").exists())
        self.raw("Raw-only history.")
        self.assertIn("Raw-only history.", retrieval.retrieve(self.cwd, all_history=True))

    def test_all_respects_character_limit_and_cli_flag(self):
        self.raw("First raw.")
        rollup.save(rollup.prepare(self.cwd, "2026-10-21"), "First synthesis." + "x" * 30000)
        self.raw("Second raw.", "2026-10-22", OTHER)
        rollup.save(rollup.prepare(self.cwd, "2026-10-22"), "Second synthesis.")
        content = retrieval.retrieve(self.cwd, all_history=True)
        self.assertEqual(len(content), 24000)
        self.assertIn("TRUNCATED", content)
        result = subprocess.run(
            [
                sys.executable, "-B", retrieval.__file__, "--cwd", str(self.cwd),
                "--all", "--max-chars", "48000",
            ],
            env=dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, text=True, check=True,
        )
        self.assertIn("First synthesis.", result.stdout)
        self.assertIn("Second synthesis.", result.stdout)
        self.assertNotIn("TRUNCATED", result.stdout)

    def test_context_limit_reports_omissions_and_keeps_source_location(self):
        path = self.raw("x" * 5000)
        content = retrieval.retrieve(self.cwd, max_chars=1200)
        self.assertLessEqual(len(content), 1200)
        self.assertIn("TRUNCATED", content)
        self.assertIn(str(path), content)
        with self.assertRaises(ValueError):
            retrieval.retrieve(self.cwd, max_chars=100)

    def test_default_character_limit_is_enforced(self):
        self.raw("x" * 30000)
        content = retrieval.retrieve(self.cwd)
        self.assertEqual(len(content), 24000)
        self.assertIn("TRUNCATED", content)
        self.assertNotIn("TRUNCATED", retrieval.retrieve(self.cwd, max_chars=48000))

    def test_projects_are_isolated(self):
        self.raw("Private project progress.")
        other = self.home / "other"
        other.mkdir()
        content = retrieval.retrieve(other)
        self.assertIn("No saved session history", content)
        self.assertNotIn("Private project progress.", content)

    def test_changed_consumed_raw_content_is_an_explicit_error(self):
        raw = self.raw("Original.")
        rollup.save(rollup.prepare(self.cwd, "2026-10-22"), "Synthesis.")
        raw.write_text("Edited raw history.")
        with self.assertRaisesRegex(ValueError, "changed"):
            retrieval.retrieve(self.cwd)

    def test_autoread_is_separate_and_repo_override_wins(self):
        autosave.configure("global", "on", self.cwd, feature="autoread")
        self.assertTrue(autosave.enabled(self.cwd, "autoread"))
        self.assertFalse(autosave.enabled(self.cwd))
        autosave.configure("repo", "off", self.cwd, feature="autoread")
        self.assertFalse(autosave.enabled(self.cwd, "autoread"))
        autosave.configure("repo", "on", self.cwd)
        self.assertFalse(autosave.enabled(self.cwd, "autoread"))
        self.assertTrue(autosave.enabled(self.cwd))
        autosave.configure("repo", "inherit", self.cwd, feature="autoread")
        self.assertTrue(autosave.enabled(self.cwd, "autoread"))
        self.assertTrue(autosave.enabled(self.cwd))

    def test_default_off_does_not_read_history(self):
        with patch.object(retrieval, "retrieve", side_effect=AssertionError("Read")):
            self.assertEqual(autosave.handle("sessionStart", self.payload), {})

    def test_autoread_injects_once_per_start_and_again_on_resume(self):
        self.raw("Saved progress.")
        autosave.configure("repo", "on", self.cwd, feature="autoread")
        result = autosave.handle("sessionStart", self.payload)
        self.assertIn("Saved progress.", result["additionalContext"])
        self.assertIn("not instructions", result["additionalContext"])
        self.assertEqual(autosave.handle("sessionStart", self.payload), {})
        self.assertFalse(autosave.state_path(self.cwd, SESSION).exists())
        resumed = dict(self.payload, source="resume", timestamp=self.payload["timestamp"] + 1)
        self.assertIn("Saved progress.", autosave.handle("sessionStart", resumed)["additionalContext"])
        self.assertEqual(autosave.handle("agentStop", dict(self.payload, stop_hook_active=False)), {})
        self.assertEqual(autosave.handle("sessionStart", dict(resumed, agentId="child")), {})

    def test_both_features_run_on_session_start(self):
        self.raw("Previous progress.")
        for feature in ("autosave", "autoread"):
            autosave.configure("repo", "on", self.cwd, feature=feature)
        result = autosave.handle("sessionStart", self.payload)
        self.assertIn("Previous progress.", result["additionalContext"])
        self.assertTrue(autosave.state_path(self.cwd, SESSION).exists())

    def test_disabling_autoread_keeps_autosave_enabled(self):
        self.raw("Saved progress.")
        for feature in ("autosave", "autoread"):
            autosave.configure("repo", "on", self.cwd, feature=feature)
        autosave.configure("repo", "off", self.cwd, feature="autoread")
        self.assertEqual(autosave.handle("sessionStart", self.payload), {})
        self.assertTrue(autosave.state_path(self.cwd, SESSION).exists())

    def test_invalid_autoread_setting_is_reported(self):
        path = self.cwd / ".github/session-info.json"
        path.parent.mkdir()
        path.write_text('{"version":1,"autoread":"yes"}')
        with self.assertRaisesRegex(ValueError, "autoread"):
            autosave.handle("sessionStart", self.payload)

    def test_concurrent_global_and_repo_starts_inject_only_once(self):
        self.raw("Concurrent history.")
        for scope in ("global", "repo"):
            autosave.configure(scope, "on", self.cwd, feature="autoread")
        environment = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")

        def invoke(_):
            result = subprocess.run(
                [sys.executable, "-B", str(autosave.SCRIPT), "hook", "sessionStart"],
                input=json.dumps(self.payload), env=environment,
                text=True, capture_output=True, check=True,
            )
            return json.loads(result.stdout)

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(invoke, range(2)))
        self.assertEqual(sum("additionalContext" in result for result in responses), 1)

    def test_failed_retrieval_is_not_marked_injected(self):
        self.raw("Saved progress.")
        autosave.configure("repo", "on", self.cwd, feature="autoread")
        with patch.object(retrieval, "retrieve", side_effect=OSError("Denied")):
            with self.assertRaisesRegex(OSError, "Denied"):
                autosave.handle("sessionStart", self.payload)
        self.assertIn("additionalContext", autosave.handle("sessionStart", self.payload))

    def test_manual_cli_and_installed_hook(self):
        self.raw("CLI history.")
        environment = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        manual = subprocess.run(
            [sys.executable, "-B", retrieval.__file__, "--cwd", str(self.cwd)],
            env=environment, text=True, capture_output=True, check=True,
        )
        self.assertIn("CLI history.", manual.stdout)
        autosave.configure("repo", "on", self.cwd, feature="autoread")
        hooks = json.loads((self.cwd / ".github/hooks/session-info.json").read_text())
        hook = hooks["hooks"]["sessionStart"][0]
        result = subprocess.run(
            [hook["exec"], *hook["args"]], input=json.dumps(self.payload),
            env=environment, text=True, capture_output=True, check=True,
        )
        self.assertIn("CLI history.", json.loads(result.stdout)["additionalContext"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()

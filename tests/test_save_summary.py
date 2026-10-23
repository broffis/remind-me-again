import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "session-summary" / "scripts" / "save_summary.py"
)
SPEC = importlib.util.spec_from_file_location("save_summary", SCRIPT)
sys.path.insert(0, str(SCRIPT.parent))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SESSION_ID = "12345678-1234-1234-1234-123456789abc"


class SaveSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.cwd = self.home / "personal" / "recipe-app"
        self.cwd.mkdir(parents=True)
        self.home_patch = patch.object(Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def save(self, text="Completed the work.", **overrides):
        args = dict(
            cwd=self.cwd, session_id=SESSION_ID,
            session_date="2026-10-23", summary=text,
        )
        args.update(overrides)
        return MODULE.save_summary(**args)

    def test_creates_home_relative_folders_and_resume_metadata(self):
        destination = self.save()
        project = self.home / ".copilot/session-info/personal/recipe-app"
        self.assertEqual(destination, project / "raw summaries/2026-10-23.md")
        self.assertTrue((project / "rollup").is_dir())
        content = destination.read_text()
        self.assertIn(f"Session ID: `{SESSION_ID}`", content)
        self.assertIn(f"copilot --resume={SESSION_ID}", content)
        self.assertIn(f"Working directory: {self.cwd}", content)
        self.assertIn("Completed the work.", content)

    def test_replaces_same_session_block_and_keeps_other_sessions(self):
        destination = self.save("First entry.")
        other_id = "87654321-4321-4321-4321-cba987654321"
        self.save("Another session.", session_id=other_id)
        other_block = destination.read_text().split("\n\n---\n\n")[1]
        self.save("Cumulative progress.")
        content = destination.read_text()
        self.assertEqual(content.count(f"## Session {SESSION_ID}"), 1)
        self.assertNotIn("First entry.", content)
        self.assertIn("Cumulative progress.", content)
        self.assertTrue(content.startswith(f"## Session {SESSION_ID}"))
        self.assertIn(other_block, content)
        self.assertEqual(list(destination.parent.glob(".raw-*")), [])

    def test_summary_containing_horizontal_rule_is_not_split(self):
        destination = self.save("Part one.\n\n---\n\nPart two.")
        self.save("Replacement.")
        self.assertEqual(destination.read_text().count("Replacement."), 1)
        self.assertNotIn("Part two.", destination.read_text())

    def test_same_checkpoint_marker_is_idempotent(self):
        token = "a" * 64
        destination = self.save("Checkpoint.", checkpoint_id=token)
        original = destination.read_bytes()
        self.save("Retry text.", checkpoint_id=token)
        self.assertEqual(destination.read_bytes(), original)
        self.save("Next checkpoint.", checkpoint_id="b" * 64)
        self.assertNotIn("Checkpoint.", destination.read_text())

    def test_rejects_raw_file_without_session_headers(self):
        destination = self.save()
        destination.write_text("Hand-written notes.")
        with self.assertRaisesRegex(ValueError, "session ID"):
            self.save("New.")
        self.assertEqual(destination.read_text(), "Hand-written notes.")

    def test_uses_supplied_session_date_and_keeps_projects_separate(self):
        first = self.save(session_date="2026-10-22")
        other = self.home / "work" / "recipe-app"
        other.mkdir(parents=True)
        second = self.save(cwd=other)
        self.assertEqual(first.name, "2026-10-22.md")
        self.assertNotEqual(first.parent, second.parent)

    def test_rejects_invalid_input_before_creating_storage(self):
        for overrides in (
            {"summary": " \n"},
            {"session_id": "../../bad"},
            {"session_date": "20261023"},
            {"session_date": "2026-02-30"},
            {"cwd": self.home},
            {"cwd": self.home.parent},
            {"cwd": self.cwd / "missing"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises((ValueError, OSError)):
                    self.save(**overrides)
                self.assertFalse((self.home / ".copilot").exists())

    def test_rejects_symlink_escape(self):
        root = self.home / ".copilot/session-info"
        root.mkdir(parents=True)
        (root / "personal").symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.save()
        self.assertFalse((self.home / "recipe-app").exists())


if __name__ == "__main__":
    unittest.main()

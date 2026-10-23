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

    def test_appends_same_session_and_other_sessions_without_overwriting(self):
        destination = self.save("First entry.")
        original = destination.read_bytes()
        self.save("More progress.")
        other_id = "87654321-4321-4321-4321-cba987654321"
        self.save("Another session.", session_id=other_id)
        content = destination.read_text()
        self.assertTrue(destination.read_bytes().startswith(original))
        self.assertEqual(content.count(f"## Session {SESSION_ID}"), 2)
        self.assertIn(f"copilot --resume={other_id}", content)
        self.assertIn("More progress.", content)
        self.assertIn("Another session.", content)

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
